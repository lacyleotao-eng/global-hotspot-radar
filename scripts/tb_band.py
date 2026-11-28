#!/usr/bin/env python3
"""把淘宝采样（data/tb-market.json）算成价带（data/tb-bands.json）。

口径（改这一块必读）：
  - 样本 = 搜索结果前 40-50 个链接，去重后按「N人付款」加权；
  - 价格 = 列表展示价（通常是该链接最低价规格，可能带「首单价」优惠），所以价带整体偏低；
    用它判断「我们贵不贵」是保守的：真实成交价只会比它高，不会更低；
  - 剔除虚拟商品（剪纸素材/模板/源文件/教程），这类词会被设计素材淹没；
  - 报价 <0.5 或 >2000 视为异常剔除（运费补差、样品链接）。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "tb-market.json"
QUERIES = ROOT / "data" / "tb-queries.json"
OUT = ROOT / "data" / "tb-bands.json"

VIRTUAL = re.compile(
    r"素材|模板|源文件|矢量|psd|cdr|电子版|高清图|设计图|代画|代做|教程|课程|视频教学|字体|插件|"
    r"打印文件|图片下载|网盘|发货\s*素材",
    re.I,
)


def wq(pairs, q):
    """pairs=[(price, weight)]，按价格升序的加权分位。"""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    acc = 0.0
    for p, w in pairs:
        acc += w
        if acc >= total * q:
            return round(p, 2)
    return round(pairs[-1][0], 2)


WEIGHT_CAP = 8000  # 单个链接最多算 8000 件，防止「20万+付款」一个样本吃掉整条价带


def clean(items, must=None):
    kept, dropped = [], []
    seen = set()
    must_re = re.compile(must) if must else None
    for x in items:
        pid = x.get("id") or x.get("href")
        if pid in seen:
            continue
        seen.add(pid)
        price = x.get("price")
        title = x.get("title", "") or ""
        if not isinstance(price, (int, float)):
            dropped.append((title, price, "no-price"))
            continue
        if price < 0.5 or price > 2000:
            dropped.append((title, price, "outlier"))
            continue
        if VIRTUAL.search(title):
            dropped.append((title, price, "virtual"))
            continue
        if must_re and not must_re.search(title):
            dropped.append((title, price, "offtopic"))
            continue
        kept.append(x)
    return kept, dropped


def band(kept, raw_n):
    if not kept:
        return None
    pairs = [(x["price"], min(max(int(x.get("sales") or 0), 8), WEIGHT_CAP)) for x in kept]
    prices = sorted(x["price"] for x in kept)
    n = len(kept)
    return {
        "n": n,
        "nRaw": raw_n,
        "p10": wq(pairs, 0.10),
        "p25": wq(pairs, 0.25),
        "p50": wq(pairs, 0.50),
        "p75": wq(pairs, 0.75),
        "p90": wq(pairs, 0.90),
        "rawP25": round(prices[n // 4], 2),
        "rawP50": round(prices[n // 2], 2),
        "rawP75": round(prices[(n * 3) // 4], 2),
        "min": prices[0],
        "max": prices[-1],
        "tmall": round(sum(1 for x in kept if x.get("tmall")) / n, 3),
        "zhejiang": round(sum(1 for x in kept if x.get("prov") == "浙江") / n, 3),
        "firstPrice": round(sum(1 for x in kept if x.get("firstPrice")) / n, 3),
        "salesSum": sum(int(x.get("sales") or 0) for x in kept),
        "top": [
            {"price": x["price"], "sales": x.get("salesText"), "shop": x.get("shop"), "title": x.get("title", "")[:46]}
            for x in sorted(kept, key=lambda y: -int(y.get("sales") or 0))[:5]
        ],
    }


def main():
    src = json.loads(SRC.read_text("utf-8"))
    qcfg = {q["id"]: q for q in json.loads(QUERIES.read_text("utf-8"))["queries"]}
    out = {}
    dropped_total = 0
    for q in src.get("queries", []):
        cfg = qcfg.get(q["id"], {})
        kept, dropped = clean(q.get("items") or [], cfg.get("must"))
        dropped_total += len(dropped)
        b = band(kept, q.get("n") or len(q.get("items") or []))
        if not b:
            print(f"  !! {q['id']} 无有效样本（must={cfg.get('must')}）")
            continue
        b.update(
            {
                "id": q["id"],
                "product": q.get("product"),
                "sku": q.get("sku"),
                "level": q.get("level") or cfg.get("level") or "single",
                "kw": q.get("kw"),
                "must": cfg.get("must"),
                "why": q.get("why") or cfg.get("why"),
                "fetchedAt": q.get("fetchedAt"),
                "dropped": len(dropped),
                "droppedSample": [{"t": t[:38], "p": p, "why": w} for t, p, w in dropped[:3]],
            }
        )
        out[q["id"]] = b
        print(
            f"{q['id']:<12} n={b['n']:<3} drop={b['dropped']:<3} "
            f"p25={b['p25']:<7} p50={b['p50']:<7} p75={b['p75']:<7} "
            f"(raw {b['rawP25']}/{b['rawP50']}/{b['rawP75']}) "
            f"天猫{b['tmall']*100:.0f}% 浙江{b['zhejiang']*100:.0f}% 首单{b['firstPrice']*100:.0f}%"
        )

    doc = {
        "fetchedAt": src.get("fetchedAt"),
        "source": src.get("source"),
        "method": "按 N人付款 加权分位；剔除虚拟商品与异常价；价格为列表展示价（通常是最低价规格，可能含首单价）",
        "droppedTotal": dropped_total,
        "bands": out,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
    print(f"\n{len(out)} 个价带 -> {OUT.relative_to(ROOT)}（共剔除 {dropped_total} 条）")


if __name__ == "__main__":
    main()
