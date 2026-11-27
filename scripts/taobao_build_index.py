#!/usr/bin/env python3
"""选品情报 · 派生字段计算 + 生成前端数据

用法：
    python3 scripts/taobao_build_index.py

输入：data/taobao.json（人改这个，字段定义见「选品模块设计说明.md」第 3 节）
输出：data/taobao-index.json（可 curl 校验）+ data/taobao-embed.js（window.__TB__，前端读）

只算不改：
  - days / inWindow（节点日历）
  - daysToPeak（距峰值天数）
  - 成本桥（每 SKU 一条）：货价（绑 1688 offer）→ +快递×包裹数 → +包装 → 平台费 → 退货损耗 → 广告 → 净利
  - breakEven（保本售价）、net / rate（净利与净利率）、health（亏/薄利/健康）
  - stale（核价超过 staleAfterDays 天要复核）
  - counts（结论分布、窗口内数量、待复核数量）

成本一律从 data/taobao-sku.json 的 SKU 绑定推出来，绑定不上就不算成本、只标「规格待核」。
taobao.json 里手写的 cost / sources 只作历史留档，不参与任何计算——两套数并存是上一版最致命的问题。

派生字段一律不写回源文件——源文件是人写的，脚本只读。
"""
import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "taobao.json"
LINKS = ROOT / "data" / "t1688-links.json"
SKUS = ROOT / "data" / "taobao-sku.json"
OUT_JSON = ROOT / "data" / "taobao-index.json"
OUT_JS = ROOT / "data" / "taobao-embed.js"

FEE_RATE = 0.006  # 淘宝基础软件服务费（保留给旧字段兼容）

DEFAULT_ASSUME = {
    "mode": "1688 一件代发",
    "express": 3.5,
    "pack": 0.6,
    "refundRate": 0.06,
    "refundLossRatio": 0.5,
    "platformRate": 0.012,
    "adRate": 0.1,
}


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def is_pending(src):
    """供应商没落定（写的是「待定」「待核价」这类）"""
    shop = (src.get("shop") or "").strip()
    if not shop:
        return True
    return shop.startswith("待") or "待核价" in shop or "待定" in shop


def offer_index(links_map):
    """所有已采链接按 offer id 建索引，成本只认这里的价格"""
    idx = {}
    for rows in (links_map or {}).values():
        for g in rows:
            for p in g.get("picks") or []:
                idx[str(p["id"])] = p
    return idx


def compute_skus(plan, offers, a, packages, keep_rate):
    """一条 SKU = 一条真实成本桥。绑不到 offer 就不给成本，绝不估。"""
    out = []
    for s in plan.get("skus") or []:
        parts, goods, miss = [], 0.0, []
        for pt in s.get("parts") or []:
            o = offers.get(str(pt.get("offer")))
            qty = float(pt.get("qty") or 1)
            if not o or o.get("price") is None:
                miss.append(str(pt.get("offer")))
                continue
            sub = float(o["price"]) * qty
            goods += sub
            parts.append({
                "as": pt.get("as") or "",
                "offer": o["id"],
                "shop": o.get("shop"),
                "qty": qty,
                "price": o["price"],
                "sub": round(sub, 2),
            })
        price = float(s.get("price") or 0)
        if miss or not parts or not price:
            out.append({
                "name": s.get("name"), "price": price, "role": s.get("role"),
                "parts": parts, "missOffers": miss, "specNote": s.get("specNote") or "",
                "specPending": bool(s.get("specPending")) or bool(miss),
                "goods": None, "express": None, "pack": None, "costAllIn": None,
                "platform": None, "ad": None, "refund": None,
                "net": None, "rate": None, "breakEven": None, "health": "unknown",
            })
            continue
        express = round(a["express"] * packages, 2)
        pack = float(a["pack"])
        base = goods + express + pack
        plat = round(price * a["platformRate"], 2)
        ad = round(price * a["adRate"], 2)
        refund = round(price * a["refundRate"] * a["refundLossRatio"], 2)
        net = round(price - base - plat - ad - refund, 2)
        rate = round(net / price, 3)
        health = "loss" if net < 0 else ("thin" if rate < 0.15 else "ok")
        out.append({
            "name": s.get("name"), "price": price, "role": s.get("role"),
            "parts": parts, "missOffers": [],
            "specNote": s.get("specNote") or "",
            "specPending": bool(s.get("specPending")),
            "goods": round(goods, 2), "express": express, "pack": pack,
            "costAllIn": round(base, 2),
            "platform": plat, "ad": ad, "refund": refund,
            "net": net, "rate": rate,
            "breakEven": round(base / keep_rate, 2),
            "health": health,
        })
    return out


def worst_health(skus):
    hs = [s.get("health") for s in skus or []]
    if "loss" in hs:
        return "loss"
    if "thin" in hs:
        return "thin"
    if hs and all(h == "unknown" for h in hs):
        return "unknown"
    return "ok"


def build():
    today = date.today()
    data = json.loads(SRC.read_text("utf-8"))
    stale_days = int(data.get("staleAfterDays") or 14)

    # ---- 1688 采购链接（scripts/t1688_links.py 抓的，抓不到就留空）----
    links_map, links_at = {}, None
    if LINKS.exists():
        lk = json.loads(LINKS.read_text("utf-8"))
        links_map, links_at = lk.get("items") or {}, lk.get("generatedAt")

    # ---- 节点日历 ----
    cal = []
    for c in data.get("calendar") or []:
        d = parse_date(c.get("date"))
        f, t = parse_date(c.get("shelfFrom")), parse_date(c.get("shelfTo"))
        cal.append({
            **c,
            "days": (d - today).days if d else None,
            "inWindow": bool(f and t and f <= today <= t),
            "passed": bool(t and today > t),
        })
    cal.sort(key=lambda x: x.get("days") if x.get("days") is not None else 9999)

    # ---- 选品卡片 ----
    sku_src = json.loads(SKUS.read_text("utf-8")) if SKUS.exists() else {"items": {}}
    assume = {**DEFAULT_ASSUME, **(sku_src.get("assumptions") or {})}
    offers = offer_index(links_map)
    keep_rate = 1 - assume["platformRate"] - assume["adRate"] - assume["refundRate"] * assume["refundLossRatio"]

    items = []
    for it in data.get("items") or []:
        srcs = it.get("sources") or []
        legacy_landed = None
        for s in srcs:
            if is_pending(s):
                continue
            p, fr = float(s.get("price") or 0), float(s.get("freight") or 0)
            if p <= 0:
                continue
            v = round(p + fr, 2)
            if legacy_landed is None or v < legacy_landed:
                legacy_landed = v

        mkt = it.get("market") or {}
        n_sample = int(mkt.get("n") or 0)
        peak = parse_date(it.get("peakAt"))
        sf, st = parse_date(it.get("shelfFrom")), parse_date(it.get("shelfTo"))
        shot = parse_date(it.get("shotAt"))

        # ---- 成本桥 ----
        plan = (sku_src.get("items") or {}).get(it.get("id")) or {}
        packages = int(plan.get("packages") or 1)
        skus = compute_skus(plan, offers, assume, packages, keep_rate)
        landed_list = [s["costAllIn"] for s in skus if s.get("costAllIn") is not None]
        nets = [s["net"] for s in skus if s.get("net") is not None]
        main_sku = next((s for s in skus if s.get("role") == "主推"), skus[0] if skus else None)
        health = worst_health(skus)

        rows = links_map.get(it.get("id")) or []
        picks_all = [p for r in rows for p in (r.get("picks") or [])]
        prices = [p["price"] for p in picks_all if p.get("price") is not None]
        main_row = next((r for r in rows if "主件" in (r.get("role") or "")), rows[0] if rows else None)
        main_prices = [p["price"] for p in (main_row or {}).get("picks") or [] if p.get("price") is not None]
        link_stats = {
            "count": len(picks_all),
            "shops": len({p.get("shop") for p in picks_all}),
            "groups": len(rows),
            "lo": min(prices) if prices else None,
            "hi": max(prices) if prices else None,
            "mainLo": min(main_prices) if main_prices else None,
            "fetchedAt": links_at,
        }

        items.append({
            **it,
            "links": rows,
            "linkStats": link_stats,
            "skus": skus,
            "packages": packages,
            "packagesNote": plan.get("packagesNote") or "",
            "mainLanded": main_sku.get("costAllIn") if main_sku else None,
            "costLo": min(landed_list) if landed_list else None,
            "costHi": max(landed_list) if landed_list else None,
            "netLo": min(nets) if nets else None,
            "netHi": max(nets) if nets else None,
            "health": health,
            "specPending": any(s.get("specPending") for s in skus),
            "daysToPeak": (peak - today).days if peak else None,
            "inWindow": bool(sf and st and sf <= today <= st),
            "windowPassed": bool(st and today > st),
            "legacyLanded": legacy_landed,
            "pendingCost": not skus,
            "priceApprox": n_sample == 0,
            "stale": bool(shot and (today - shot).days > stale_days),
            "shotDaysAgo": (today - shot).days if shot else None,
            "sourceCount": len([s for s in srcs if not is_pending(s)]),
        })

    items.sort(key=lambda x: -(x.get("score") or 0))
    for i, x in enumerate(items, 1):
        x["rank"] = i

    counts = {
        "total": len(items),
        "do": sum(1 for x in items if x.get("verdict") == "做"),
        "watch": sum(1 for x in items if x.get("verdict") == "观望"),
        "drop": sum(1 for x in items if x.get("verdict") == "放弃"),
        "inWindow": sum(1 for x in items if x.get("inWindow")),
        "expired": sum(1 for x in items if x.get("windowPassed") and x.get("verdict") != "放弃"),
        "stale": sum(1 for x in items if x.get("stale")),
        "pendingCost": sum(1 for x in items if x.get("pendingCost")),
        "withLinks": sum(1 for x in items if (x.get("linkStats") or {}).get("count")),
        "linkCount": sum((x.get("linkStats") or {}).get("count", 0) for x in items),
        "healthLoss": sum(1 for x in items if x.get("health") == "loss"),
        "healthThin": sum(1 for x in items if x.get("health") == "thin"),
        "healthOk": sum(1 for x in items if x.get("health") == "ok"),
        "specPending": sum(1 for x in items if x.get("specPending")),
        "skuCount": sum(len(x.get("skus") or []) for x in items),
    }

    payload = {
        "updatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "dataAsOf": data.get("dataAsOf"),
        "generatedAtSource": data.get("generatedAt"),
        "staleAfterDays": stale_days,
        "model": data.get("model") or {},
        "assumptions": assume,
        "assumptionsWhy": (sku_src.get("assumptions") or {}).get("why") or "",
        "assumptionsWarn": (sku_src.get("assumptions") or {}).get("warn") or "",
        "calendar": cal,
        "items": items,
        "counts": counts,
    }

    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    OUT_JS.write_text(
        "/* 自动生成：scripts/taobao_build_index.py */\nwindow.__TB__ = "
        + json.dumps(payload, ensure_ascii=False)
        + ";\n",
        "utf-8",
    )

    print(f"[ok] {counts['total']} 张候选卡 → data/taobao-index.json + data/taobao-embed.js")
    print(f"     做 {counts['do']} / 观望 {counts['watch']} / 放弃 {counts['drop']}"
          f"｜窗口内 {counts['inWindow']}｜待复核 {counts['stale']}｜成本待核 {counts['pendingCost']}"
          f"｜1688 链接 {counts['linkCount']} 条 / {counts['withLinks']} 张卡")
    for x in items:
        flag = "做  " if x.get("verdict") == "做" else ("观望" if x.get("verdict") == "观望" else "放弃")
        hm = {"loss": "亏钱", "thin": "薄利", "ok": "健康", "unknown": "无成本"}.get(x.get("health"), "?")
        print(f"  {x['rank']:>2}. {flag} {x.get('score'):>5} {x.get('name')[:22]}"
              f"｜全成本 {x.get('costLo')}–{x.get('costHi')}"
              f"｜净利 {x.get('netLo')}–{x.get('netHi')}｜{hm}"
              f"{'｜规格待核' if x.get('specPending') else ''}")
        for s_ in x.get("skus") or []:
            print(f"        - {s_['name'][:18]:<20} 售价 {s_.get('price')} 成本 {s_.get('costAllIn')}"
                  f" 净利 {s_.get('net')} 保本 {s_.get('breakEven')}"
                  f" {'【亏】' if s_.get('health') == 'loss' else ('【薄】' if s_.get('health') == 'thin' else '')}")


if __name__ == "__main__":
    build()
