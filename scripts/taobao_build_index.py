#!/usr/bin/env python3
"""选品情报构建器 v2：以「1688 供应商商品」为核心，按规格级算成本。

数据链路（改这一块必读）：
  data/t1688-offers.json  供应商商品真源：每个 offer 的全部规格 + 每个规格的价格/库存
                          + 阶梯价 + 发货地 + 运费（scripts/t1688_specs.js 抓取）
  data/t1688-plan.json    新产品定义（人改）：每个新产品规格 = 若干「offer + 该 offer 的规格名 + 数量」
  data/taobao.json        商品层文案：名字、适配分、为什么、怎么打、翻车点、上架窗口（人改）
  ↓
  data/taobao-index.json + data/taobao-embed.js

成本桥（唯一口径）：
  货价   = Σ(该规格单价 × 数量)
  快递   = express × 包裹数（默认 = 不同厂家数，几家工厂就几笔运费）
  包装   = pack × 包裹数
  全成本 = 货价 + 快递 + 包装
  净利   = 售价 − 全成本 − 售价 × (平台率 + 广告率 + 退货率 × 报废率)
  保本价 = 全成本 ÷ (1 − 平台率 − 广告率 − 退货率 × 报废率)

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
OUT_JSON = ROOT / "data" / "taobao-index.json"
OUT_JS = ROOT / "data" / "taobao-embed.js"


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


def build():
    core = load(CORE)
    offers_doc = load(OFFERS)
    plan_doc = load(PLAN) if PLAN.exists() else {"items": {}}
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
                if unit is None:
                    pending.append(f"{o.get('shop', '')[:12]} 的规格「{p.get('spec')}」未命中({how})")
                else:
                    goods += unit * qty
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
                })

            factories = len({p["offerId"] for p in parts}) or 1
            packages = int(sku.get("packages") or factories)
            express = round(a_express * packages, 2)
            pack = round(a_pack * packages, 2)
            cost_all = money(goods + express + pack) if not pending else None
            price = float(sku.get("price") or 0) or None
            net = money(price - cost_all - price * cost_rate) if (price and cost_all is not None) else None
            be = money(cost_all / keep_rate) if cost_all is not None else None
            rate = round(net / price, 3) if (net is not None and price) else None
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

        items.append({
            **it,
            "rank": len(items) + 1,
            "kind": pitem.get("kind") or "single",
            "specCount": len(skus),
            "skus": skus,
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
    for x in items:
        print(f"  {x['rank']:>2}. {x.get('verdict')} {x.get('name')[:20]}｜{x['kind']}｜"
              f"规格 {x['specCount']}｜供应商 {x['supplierCount']}｜全成本 {x['costLo']}–{x['costHi']}")
        for s in x["skus"]:
            flag = "" if not s["pending"] else "  ⚠ " + "; ".join(s["pending"])[:60]
            print(f"       - {s['name'][:20]:<22} 卖 {s['price']} 成本 {s['costAllIn']} "
                  f"净利 {s['net']} 保本 {s['breakEven']}{flag}")
    if warns:
        print(f"\n[warn] {len(warns)} 条规格未命中：")
        for w in warns[:20]:
            print("   ", w)


if __name__ == "__main__":
    build()
