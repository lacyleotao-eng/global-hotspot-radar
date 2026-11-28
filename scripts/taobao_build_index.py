#!/usr/bin/env python3
"""选品情报构建器 v2：以「1688 供应商商品」为核心，按规格级算成本。

数据链路（改这一块必读）：
  data/t1688-offers.json  供应商商品真源：每个 offer 的全部规格 + 每个规格的价格/库存
                          + 阶梯价 + 发货地 + 运费（scripts/t1688_specs.js 抓取）
  data/t1688-plan.json    新产品定义（人改）：每个新产品规格 = 若干「offer + 该 offer 的规格名 + 数量」
  data/tb-bands.json      淘宝真实在售价带（scripts/tb_market.js 抓 → scripts/tb_band.py 算）
  data/taobao.json        商品层文案：名字、适配分、为什么、怎么打、翻车点、上架窗口（人改）
  ↓
  data/taobao-index.json + data/taobao-embed.js

成本桥（唯一口径）：
  货价   = Σ(该规格单价 × 数量)
  快递   = Σ(该店铺的 1688 报价运费)；同一家店多件只算一笔；缺失才回退到假设值
  包装   = pack × 包裹数（包裹数 = 不同店铺数）
  全成本 = 货价 + 快递 + 包装
  净利   = 售价 − 全成本 − 售价 × (平台率 + 广告率 + 退货率 × 报废率)
  保本价 = 全成本 ÷ (1 − 平台率 − 广告率 − 退货率 × 报废率)
  按市场价卖 = 用淘宝同类的 p50 当售价，看还剩多少净利（这一步才是判断「这个品能不能做」的关键）

规格必须精确命中：plan 里写的规格名在 offer 的 specs 里找不到，就标 specPending，
不给这个 SKU 出成本，也不许用均价糊过去。
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "data" / "taobao.json"
OFFERS = ROOT / "data" / "t1688-offers.json"
PLAN = ROOT / "data" / "t1688-plan.json"
BANDS = ROOT / "data" / "tb-bands.json"
OUT_JSON = ROOT / "data" / "taobao-index.json"
OUT_JS = ROOT / "data" / "taobao-embed.js"

BULK_UNIT = 0.3  # 单价低于这个数的规格，基本是「按张/按个」的批量报价，不能直接当一件代发成本


def load(p):
    return json.loads(Path(p).read_text("utf-8"))


def parse_date(s):
    if not s:
        return None
    try:
        y, m, d = (int(x) for x in str(s)[:10].split("-"))
        return date(y, m, d)
    except Exception:
        return None


def find_spec(offer, want):
    """在 offer 的 specs 里精确找规格；退一步允许唯一包含匹配。"""
    specs = offer.get("specs") or []
    if not want:
        return None, "missing"
    want = want.strip()
    for s in specs:
        if (s.get("name") or "").strip() == want:
            return s, "exact"
    hits = [s for s in specs if want in (s.get("name") or "")]
    if len(hits) == 1:
        return hits[0], "fuzzy"
    return None, "ambiguous" if hits else "notfound"


def money(v):
    return None if v is None else round(float(v) + 1e-9, 2)


MIN_BAND_N = 10  # 少于 10 个有效样本的价带不用，宁可不给参照也不要给错参照


def pick_band(bands, pid, kind, sku_id, n_parts=1):
    """给一个 SKU 选参照价带。

    优先级：该 SKU 的专属词（只对单组件 SKU 成立）→ 同形态主词 → 借用（标 loose）。
    组合 SKU 不能拿组件词当参照：组件词只搜到单个零件，会把自己的成本说成「贵得离谱」。
    """
    cands = [b for b in bands.values() if b.get("product") == pid and (b.get("n") or 0) >= MIN_BAND_N]
    if not cands:
        return None, "none"
    own = [b for b in cands if b.get("sku") and b.get("sku") == sku_id]
    if own and n_parts <= 1:
        return max(own, key=lambda b: b.get("n") or 0), "sku"
    lvl = "bundle" if kind == "bundle" else "single"
    same = [b for b in cands if not b.get("sku") and (b.get("level") or "single") == lvl]
    if same:
        return max(same, key=lambda b: b.get("n") or 0), lvl
    rest = [b for b in cands if not b.get("sku")]
    if rest:
        return max(rest, key=lambda b: b.get("n") or 0), "loose"
    return None, "none"


def position(price, band):
    """我们的价落在同类价带的哪个位置。"""
    if not price or not band:
        return None
    if price < band["p25"]:
        return "below"
    if price <= band["p75"]:
        return "in"
    if price <= band["p90"]:
        return "high"
    return "top"


def build():
    core = load(CORE)
    offers_doc = load(OFFERS)
    plan_doc = load(PLAN) if PLAN.exists() else {"items": {}}
    bands_doc = load(BANDS) if BANDS.exists() else {"bands": {}}
    bands = bands_doc.get("bands") or {}
    offers = offers_doc.get("offers") or {}
    assume = plan_doc.get("assumptions") or {}
    a_express = float(assume.get("express", 3.5))
    a_pack = float(assume.get("pack", 0.6))
    a_platform = float(assume.get("platformRate", 0.012))
    a_ad = float(assume.get("adRate", 0.10))
    a_refund = float(assume.get("refundRate", 0.06))
    a_loss = float(assume.get("refundLossRatio", 0.5))
    cost_rate = a_platform + a_ad + a_refund * a_loss
    keep_rate = 1 - cost_rate

    today = date.today()
    warns = []
    items = []

    for it in core.get("items") or []:
        pid = it.get("id")
        pitem = (plan_doc.get("items") or {}).get(pid) or {}
        skus = []
        supplier_ids = []

        for sku in pitem.get("skus") or []:
            parts = []
            pending = []
            goods = 0.0
            shops = {}  # 店铺 -> {"freight": 抓到的运费 or None, "src": "1688"/"假设", "n": 件数}
            for p in sku.get("parts") or []:
                o = offers.get(str(p.get("offer")))
                if not o:
                    pending.append(f"offer {p.get('offer')} 未抓取")
                    continue
                sp, how = find_spec(o, p.get("spec"))
                sid = str(p.get("offer"))
                if sid not in supplier_ids:
                    supplier_ids.append(sid)
                qty = int(p.get("qty") or 1)
                unit = sp.get("price") if sp else None
                bulk = bool(unit is not None and unit < BULK_UNIT)
                if unit is None:
                    pending.append(f"{o.get('shop', '')[:12]} 的规格「{p.get('spec')}」未命中({how})")
                else:
                    goods += unit * qty

                fr = o.get("freight")
                try:
                    fr = float(fr) if fr not in (None, "") else None
                except Exception:
                    fr = None
                shopname = o.get("shop") or sid
                rec = shops.setdefault(shopname, {"freight": None, "src": "假设", "n": 0})
                rec["n"] += 1
                if fr is not None:
                    rec["freight"] = fr if rec["freight"] is None else max(rec["freight"], fr)
                    rec["src"] = "1688"

                parts.append({
                    "label": p.get("label") or "",
                    "offerId": sid,
                    "shop": o.get("shop") or "",
                    "offerTitle": o.get("title") or "",
                    "url": o.get("url") or f"https://detail.1688.com/offer/{sid}.html",
                    "spec": sp.get("name") if sp else (p.get("spec") or ""),
                    "specWant": p.get("spec") or "",
                    "unitPrice": money(unit),
                    "stock": sp.get("stock") if sp else None,
                    "qty": qty,
                    "fee": money(unit * qty) if unit is not None else None,
                    "match": how,
                    "shipFrom": o.get("shipFrom") or "",
                    "ladderLo": o.get("ladderLo"),
                    "bulk": bulk,
                    "band": p.get("band"),
                })

            factories = len({p["offerId"] for p in parts}) or 1
            # 包裹数：同一家店多件合成一单（1688 同一卖家默认合并发货）；plan 里写死就按写的
            if sku.get("packages"):
                packages = int(sku["packages"])
                express = round(a_express * packages, 2)
                ship_plan = [{"shop": "（按 plan 指定包裹数）", "freight": a_express, "src": "假设", "n": 0}] * packages
            else:
                packages = len(shops) or 1
                express = 0.0
                ship_plan = []
                for shopname, rec in shops.items():
                    fee = rec["freight"] if rec["freight"] is not None else a_express
                    express += fee
                    ship_plan.append({"shop": shopname, "freight": round(fee, 2), "src": rec["src"], "n": rec["n"]})
                express = round(express, 2)
            pack = round(a_pack * packages, 2)
            cost_all = money(goods + express + pack) if not pending else None
            price = float(sku.get("price") or 0) or None
            net = money(price - cost_all - price * cost_rate) if (price and cost_all is not None) else None
            be = money(cost_all / keep_rate) if cost_all is not None else None
            rate = round(net / price, 3) if (net is not None and price) else None

            # 市场价带：这个 SKU 该跟哪条淘宝价带比
            band, band_lvl = pick_band(
                bands, pid, pitem.get("kind") or "single", sku.get("id"), len(parts)
            )
            market = None
            if band:
                market = {
                    "n": band.get("n"),
                    "p25": band.get("p25"),
                    "p50": band.get("p50"),
                    "p75": band.get("p75"),
                    "p90": band.get("p90"),
                    "kw": band.get("kw"),
                    "level": band.get("level") or "single",
                    "id": band.get("id"),
                    "fetchedAt": band.get("fetchedAt"),
                    "match": band_lvl,   # sku=专属词 / single|bundle=同形态主词 / loose=勉强借用的词
                    "tmall": band.get("tmall"),
                    "zhejiang": band.get("zhejiang"),
                }
            pos = position(price, band)
            net_at_p50 = None
            if band and cost_all is not None:
                net_at_p50 = money(band["p50"] - cost_all - band["p50"] * cost_rate)

            # 市场参照价：单件=自己词的中位；组合=各组件在淘宝散买的中位相加
            ref_parts = []
            for p in parts:
                bid = p.get("band")
                bd = bands.get(bid) if bid else None
                if bd and (bd.get("n") or 0) >= MIN_BAND_N:
                    ref_parts.append({
                        "label": p["label"], "band": bid, "kw": bd.get("kw"),
                        "p50": bd.get("p50"), "n": bd.get("n"), "qty": p["qty"],
                    })
            # 同名多件（如「横幅 ×3」）不能按「一套」的价乘件数：同名只算一次，并标不完整
            dedup, seen = [], set()
            dup = False
            for r in ref_parts:
                k = (r["label"], r["band"])
                if k in seen:
                    dup = True
                    continue
                seen.add(k)
                dedup.append(r)
            known = sum(r["p50"] * r["qty"] for r in dedup)
            ref_price, ref_partial, ref_src = None, False, ""
            if dedup and len(dedup) == len(parts) and not dup:
                ref_price, ref_src = money(known), "basket"
            elif not dedup and len(parts) == 1 and band:
                ref_price, ref_src = money(band["p50"]), "product"
            elif dedup:
                ref_price, ref_partial, ref_src = money(known), True, "basket-partial"
            premium = round(price / ref_price, 2) if (price and ref_price) else None
            net_at_ref = money(ref_price - cost_all - ref_price * cost_rate) if (ref_price and cost_all is not None) else None

            flags = []
            if pending:
                flags.append("cost-pending")
            if any(p["bulk"] for p in parts):
                flags.append("bulk-price")
            if any(s["src"] == "假设" for s in ship_plan):
                flags.append("freight-assumed")
            if net is not None and net < 0:
                flags.append("loss")
            if net_at_ref is not None and net_at_ref < 0:
                flags.append("market-loss")
            if premium is not None and premium > 1.3:
                flags.append("price-high")
            elif pos in ("high", "top"):
                flags.append("price-high")

            health = "unknown"
            if net is not None:
                health = "loss" if net < 0 else ("thin" if rate < 0.15 else "ok")

            skus.append({
                "id": sku.get("id") or f"s{len(skus) + 1}",
                "name": sku.get("name") or "",
                "role": sku.get("role") or "",
                "price": money(price),
                "goods": money(goods) if not pending else None,
                "express": express,
                "pack": pack,
                "packages": packages,
                "factories": factories,
                "costAllIn": cost_all,
                "net": net,
                "rate": rate,
                "breakEven": be,
                "health": health,
                "market": market,
                "pos": pos,
                "netAtP50": net_at_p50,
                "refPrice": ref_price,
                "refPartial": ref_partial,
                "refSrc": ref_src,
                "refParts": ref_parts,
                "premium": premium,
                "netAtRef": net_at_ref,
                "flags": flags,
                "shipPlan": ship_plan,
                "parts": parts,
                "pending": pending,
                "note": sku.get("note") or "",
            })
            for w in pending:
                warns.append(f"{pid}/{sku.get('name')}: {w}")

        suppliers = []
        for sid in supplier_ids:
            o = offers.get(sid) or {}
            suppliers.append({
                "id": sid,
                "shop": o.get("shop") or "",
                "title": o.get("title") or "",
                "url": o.get("url") or f"https://detail.1688.com/offer/{sid}.html",
                "shipFrom": o.get("shipFrom") or "",
                "freight": o.get("freight"),
                "sold": o.get("sold") or "",
                "ladder": o.get("ladder") or [],
                "ladderLo": o.get("ladderLo"),
                "dims": o.get("dims") or [],
                "specs": o.get("specs") or [],
                "specLo": o.get("specLo"),
                "specHi": o.get("specHi"),
                "fetchedAt": o.get("fetchedAt") or "",
            })

        valid = [s for s in skus if s["costAllIn"] is not None]
        netlo = min((s["net"] for s in valid), default=None)
        netHi = max((s["net"] for s in valid), default=None)
        costlo = min((s["costAllIn"] for s in valid), default=None)
        costHi = max((s["costAllIn"] for s in valid), default=None)
        peak = parse_date(it.get("peakAt"))
        sf, st = parse_date(it.get("shelfFrom")), parse_date(it.get("shelfTo"))
        health = "unknown"
        if valid:
            health = "loss" if netlo < 0 else ("thin" if all((s["rate"] or 0) < 0.15 for s in valid) else "ok")

        # 产品级：用主推规格的价带当这个产品的市场参照，供卡片头部显示
        head = next((s for s in skus if s.get("role") == "主推"), skus[0] if skus else None)
        flags = sorted({f for s in skus for f in s.get("flags") or []})

        items.append({
            **it,
            "rank": len(items) + 1,
            "kind": pitem.get("kind") or "single",
            "specCount": len(skus),
            "skus": skus,
            "market": (head or {}).get("market"),
            "flags": flags,
            "suppliers": suppliers,
            "supplierCount": len(suppliers),
            "specCountTotal": sum(len(s["specs"]) for s in suppliers),
            "costLo": costlo,
            "costHi": costHi,
            "netLo": netlo,
            "netHi": netHi,
            "health": health,
            "pendingCost": not valid,
            "specPending": any(s["pending"] for s in skus),
            "daysToPeak": (peak - today).days if peak else None,
            "inWindow": bool(sf and st and sf <= today <= st),
            "windowPassed": bool(st and today > st),
            "stale": bool(it.get("shotAt") and (today - parse_date(it["shotAt"])).days > 14) if it.get("shotAt") else False,
            "shotDaysAgo": (today - parse_date(it["shotAt"])).days if it.get("shotAt") else None,
        })

    counts = {
        "total": len(items),
        "do": sum(1 for x in items if x.get("verdict") == "做"),
        "watch": sum(1 for x in items if x.get("verdict") == "观望"),
        "drop": sum(1 for x in items if x.get("verdict") == "放弃"),
        "inWindow": sum(1 for x in items if x.get("inWindow")),
        "stale": sum(1 for x in items if x.get("stale")),
        "pendingCost": sum(1 for x in items if x.get("pendingCost")),
        "healthLoss": sum(1 for x in items if x.get("health") == "loss"),
        "healthThin": sum(1 for x in items if x.get("health") == "thin"),
        "healthOk": sum(1 for x in items if x.get("health") == "ok"),
        "specPending": sum(1 for x in items if x.get("specPending")),
        "skuCount": sum(len(x.get("skus") or []) for x in items),
        "supplierCount": len({s["id"] for x in items for s in x.get("suppliers") or []}),
        "specRows": sum(x.get("specCountTotal", 0) for x in items),
        "withLinks": sum(1 for x in items if x.get("suppliers")),
        "priceHigh": sum(1 for x in items if "price-high" in (x.get("flags") or [])),
        "marketLoss": sum(1 for x in items if "market-loss" in (x.get("flags") or [])),
        "bulkPrice": sum(1 for x in items if "bulk-price" in (x.get("flags") or [])),
        "banded": sum(1 for x in items if x.get("market")),
        "bandSamples": sum((x.get("market") or {}).get("n") or 0 for x in items),
    }

    doc = {
        "generatedAt": today.isoformat(),
        "model": core.get("model") or {},
        "assumptions": {
            "express": a_express, "pack": a_pack, "platformRate": a_platform,
            "adRate": a_ad, "refundRate": a_refund, "refundLossRatio": a_loss,
        },
        "assumptionsWhy": assume.get("why") or "",
        "assumptionsWarn": assume.get("warn") or "",
        "offersFetchedAt": offers_doc.get("fetchedAt") or "",
        "bandsFetchedAt": bands_doc.get("fetchedAt") or "",
        "bandsMethod": bands_doc.get("method") or "",
        "calendar": core.get("calendar") or [],
        "counts": counts,
        "items": items,
    }
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
    OUT_JS.write_text("window.__TB__ = " + json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + ";\n", "utf-8")

    print(f"[ok] {counts['total']} 个产品 / {counts['skuCount']} 个产品规格 / "
          f"{counts['supplierCount']} 家供应商 / {counts['specRows']} 行供应商规格")
    print(f"     做 {counts['do']} / 观望 {counts['watch']} / 放弃 {counts['drop']}"
          f"｜净利健康 {counts['healthOk']}｜薄利 {counts['healthThin']}｜亏 {counts['healthLoss']}｜规格待核 {counts['specPending']}")
    print(f"     价带 {counts['banded']}/{counts['total']} 个产品有淘宝实时样本（共 {counts['bandSamples']} 条）"
          f"｜定价偏高 {counts['priceHigh']}｜按市场价必亏 {counts['marketLoss']}｜批量价存疑 {counts['bulkPrice']}")
    for x in items:
        m = x.get("market") or {}
        print(f"  {x['rank']:>2}. {x.get('verdict')} {x.get('name')[:20]}｜{x['kind']}｜"
              f"规格 {x['specCount']}｜供应商 {x['supplierCount']}｜全成本 {x['costLo']}–{x['costHi']}"
              f"｜淘宝 n={m.get('n')} p25–p75 {m.get('p25')}–{m.get('p75')}（{m.get('kw')}）")
        for s in x["skus"]:
            flag = "" if not s["pending"] else "  ⚠ " + "; ".join(s["pending"])[:60]
            mk = s.get("market") or {}
            print(f"       - {s['name'][:20]:<22} 卖 {s['price']} 成本 {s['costAllIn']} "
                  f"净利 {s['net']} 保本 {s['breakEven']}｜参照价 {s.get('refPrice')}{'(缺组件)' if s.get('refPartial') else ''} "
                  f"溢价 {s.get('premium')}x 按参照价卖净利 {s.get('netAtRef')}"
                  f"{' [' + ','.join(s['flags']) + ']' if s['flags'] else ''}{flag}")
    if warns:
        print(f"\n[warn] {len(warns)} 条规格未命中：")
        for w in warns[:20]:
            print("   ", w)


if __name__ == "__main__":
    build()
