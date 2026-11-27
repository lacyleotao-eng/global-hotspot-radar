#!/usr/bin/env python3
"""选品情报 · 派生字段计算 + 生成前端数据

用法：
    python3 scripts/taobao_build_index.py

输入：data/taobao.json（人改这个，字段定义见「选品模块设计说明.md」第 3 节）
输出：data/taobao-index.json（可 curl 校验）+ data/taobao-embed.js（window.__TB__，前端读）

只算不改：
  - days / inWindow（节点日历）
  - daysToPeak（距峰值天数）
  - landed（到手成本 = 最便宜那家的货价 + 运费）
  - gross / rate（毛利额与毛利率，扣 0.6% 软件服务费）
  - stale（核价超过 staleAfterDays 天要复核）
  - counts（结论分布、窗口内数量、待复核数量）

派生字段一律不写回源文件——源文件是人写的，脚本只读。
"""
import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "taobao.json"
LINKS = ROOT / "data" / "t1688-links.json"
OUT_JSON = ROOT / "data" / "taobao-index.json"
OUT_JS = ROOT / "data" / "taobao-embed.js"

FEE_RATE = 0.006  # 淘宝基础软件服务费


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
    items = []
    for it in data.get("items") or []:
        srcs = it.get("sources") or []
        landed, landed_shop = None, None
        for s in srcs:
            if is_pending(s):
                continue
            p, fr = float(s.get("price") or 0), float(s.get("freight") or 0)
            if p <= 0:
                continue
            v = round(p + fr, 2)
            if landed is None or v < landed:
                landed, landed_shop = v, s.get("shop")

        mkt = it.get("market") or {}
        n_sample = int(mkt.get("n") or 0)
        peak = parse_date(it.get("peakAt"))
        sf, st = parse_date(it.get("shelfFrom")), parse_date(it.get("shelfTo"))
        shot = parse_date(it.get("shotAt"))

        pricing = []
        for p in it.get("pricing") or []:
            price = float(p.get("price") or 0)
            cost = float(p.get("cost") or 0)
            gross = round(price - cost - price * FEE_RATE, 2) if price else None
            pricing.append({
                **p,
                "gross": gross,
                "rate": round(gross / price, 3) if (gross is not None and price) else None,
            })

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
            "daysToPeak": (peak - today).days if peak else None,
            "inWindow": bool(sf and st and sf <= today <= st),
            "windowPassed": bool(st and today > st),
            "landed": landed,
            "landedShop": landed_shop,
            "pendingCost": landed is None,
            "priceApprox": n_sample == 0,
            "pricing": pricing,
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
    }

    payload = {
        "updatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "dataAsOf": data.get("dataAsOf"),
        "generatedAtSource": data.get("generatedAt"),
        "staleAfterDays": stale_days,
        "model": data.get("model") or {},
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
        tag = []
        if x.get("pendingCost"):
            tag.append("待核价")
        if x.get("stale"):
            tag.append(f"{x.get('shotDaysAgo')}天前核价")
        if x.get("windowPassed"):
            tag.append("窗口已过")
        print(f"  {x['rank']:>2}. {flag} {x.get('score'):>5} {x.get('name')[:22]}"
              f"｜峰值 {x.get('daysToPeak')} 天｜{' / '.join(tag) if tag else 'ok'}")


if __name__ == "__main__":
    build()
