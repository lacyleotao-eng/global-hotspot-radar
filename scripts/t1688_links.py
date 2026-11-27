#!/usr/bin/env python3
"""选品情报 · 1688 采购链接采集

用法：
    python3 scripts/t1688_links.py              # 用缓存（>3 天自动重抓）
    python3 scripts/t1688_links.py --refresh    # 强制重抓
    python3 scripts/t1688_links.py --list 磁吸对联   # 只抓一个词，打印候选，用于人工挑货

数据来源
    1688 的公开聚合页 https://www.1688.com/chanpin/-<关键词GBK十六进制>.html
    这个页面不需要登录、可以直接 curl，一页约 240 条，带真实挂牌价 / 起订 /
    已售 / 店铺名 / 回头率。detail.1688.com 的详情页和 s.1688.com 的搜索页
    对未登录请求一律拦截（bixi punish / 登录墙），所以不走那两条路。

产物
    data/t1688-pool/<gbk>.json   抓取缓存（每条 offer 的标题/价格/店铺/已售/回头率）
    data/t1688-links.json        按 data/t1688-queries.json 挑好并并表的结果
    各 item 的 links 由 taobao_build_index.py 并进前端数据。
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
POOL_DIR = DATA / "t1688-pool"
QUERIES = DATA / "t1688-queries.json"
OUT = DATA / "t1688-links.json"
CACHE_DAYS = 3
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

CARD_SPLIT_RE = re.compile(r'<article class="pcCardContainer[^"]*">(.*?)</article>', re.S)
OFFER_RE = re.compile(r'href="https://detail\.1688\.com/offer/(\d+)\.html"')
ARIA_RE = re.compile(r'aria-label="(.*?)"')
PRICE_RE = re.compile(r'<span class="pcPrice[^"]*"><span>¥</span><strong>(.*?)</strong><span>(.*?)</span></span>')
MOQ_RE = re.compile(r'data-testid="product-sales-or-moq">(.*?)<')
SUPPLIER_RE = re.compile(r'data-testid="product-supplier" title="(.*?)"')
REPEAT_RE = re.compile(r'title="回头率: (\d+)%"')
IMG_RE = re.compile(r'<img class="pcImage[^"]*" src="(.*?)"')


def gbk_hex(kw):
    return kw.encode("gbk").hex().upper()


def fetch(kw):
    url = f"https://www.1688.com/chanpin/-{gbk_hex(kw)}.html"
    out = subprocess.run(
        ["curl", "-s", "-m", "45", "-A", UA, "-H", "Accept-Language: zh-CN,zh;q=0.9", url],
        capture_output=True,
    )
    html = out.stdout.decode("utf-8", "ignore")
    if "punish" in html and len(html) < 5000:
        raise RuntimeError(f"[blocked] {kw} 被 1688 拦截，稍后再试")
    return url, html


def parse(html):
    rows = []
    for chunk in CARD_SPLIT_RE.findall(html):
        m_id = OFFER_RE.search(chunk)
        if not m_id:
            continue
        oid = m_id.group(1)
        title = ARIA_RE.search(chunk)
        title = re.sub(r"<[^>]+>", "", title.group(1) if title else "").strip()
        m_price = PRICE_RE.search(chunk)
        price = None
        if m_price:
            yuan, cent = m_price.group(1), m_price.group(2).strip(".")
            try:
                price = float(f"{yuan}.{cent or '0'}")
            except ValueError:
                price = None
        m_moq = MOQ_RE.search(chunk)
        m_shop = SUPPLIER_RE.search(chunk)
        m_rep = REPEAT_RE.search(chunk)
        m_img = IMG_RE.search(chunk)
        rows.append({
            "id": oid,
            "title": title,
            "price": price,
            "moq": re.sub(r"\s+", " ", m_moq.group(1)).strip() if m_moq else "",
            "shop": m_shop.group(1).strip() if m_shop else "",
            "repeat": int(m_rep.group(1)) if m_rep else None,
            "img": m_img.group(1) if m_img else "",
            "url": f"https://detail.1688.com/offer/{oid}.html",
        })
    return rows


def pool_path(kw):
    return POOL_DIR / f"{gbk_hex(kw)}.json"


def get_pool(kw, refresh=False):
    p = pool_path(kw)
    if p.exists() and not refresh:
        cached = json.loads(p.read_text("utf-8"))
        age = datetime.now() - datetime.strptime(cached["fetchedAt"][:10], "%Y-%m-%d")
        if age < timedelta(days=CACHE_DAYS):
            return cached
    url, html = fetch(kw)
    offers = parse(html)
    if not offers:
        raise RuntimeError(f"[empty] {kw} 没解析出商品，页面结构可能变了")
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "keyword": kw,
        "url": url,
        "fetchedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(offers),
        "offers": offers,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    return payload


def score(o, want, avoid):
    """人工挑货时的排序分：标题命中要的词的加权，命中要避开的词直接出局"""
    t = o["title"]
    if any(a and a in t for a in avoid):
        return -1
    s = sum(2 for w in want if w and w in t)
    sold = o["moq"] or ""
    n = re.search(r"([\d.]+)(万|w)?\+?", sold)
    if n:
        v = float(n.group(1)) * (10000 if n.group(2) else 1)
        s += min(v / 1000, 6)
    if o["repeat"]:
        s += min(o["repeat"] / 25, 3)
    return s


def main():
    args = sys.argv[1:]
    refresh = "--refresh" in args

    if "--list" in args:
        kw = args[args.index("--list") + 1]
        pool = get_pool(kw, refresh=refresh)
        print(f"# {kw} · {pool['count']} 条 · {pool['fetchedAt']} · {pool['url']}")
        for o in sorted(pool["offers"], key=lambda x: -(score(x, [], []) or 0))[:40]:
            print(f"{o['id']}  ¥{o['price']:<7} {o['moq'][:12]:<13} {o['shop'][:20]:<22}"
                  f"回头{(o['repeat'] or '-')}%  {o['title'][:34]}")
        return

    q = json.loads(QUERIES.read_text("utf-8"))
    comps = q["components"]
    pools = {}
    for key, c in comps.items():
        try:
            pools[key] = get_pool(c["keyword"], refresh=refresh)
            print(f"[pool] {key:<18} {c['keyword']:<14} {pools[key]['count']:>4} 条")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {key}: {e}", file=sys.stderr)
            pools[key] = None
        time.sleep(0.8)

    out = {"generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "items": {}}
    missing = []
    for item_id, groups in q["items"].items():
        rows = []
        for g in groups:
            pool = pools.get(g["component"])
            idx = {o["id"]: o for o in (pool["offers"] if pool else [])}
            picks = []
            for oid in g.get("picks") or []:
                o = idx.get(str(oid))
                if not o:
                    missing.append(f"{item_id}/{g['component']}/{oid}")
                    continue
                picks.append({
                    "id": o["id"],
                    "url": o["url"],
                    "title": o["title"],
                    "shop": o["shop"],
                    "price": o["price"],
                    "moq": o["moq"],
                    "repeat": o["repeat"],
                    "img": o["img"],
                })
            if picks:
                rows.append({
                    "component": g["component"],
                    "label": comps[g["component"]]["label"],
                    "role": g.get("role") or "主件",
                    "note": g.get("note") or "",
                    "keyword": comps[g["component"]]["keyword"],
                    "searchUrl": f"https://s.1688.com/selloffer/offer_search.htm?keywords={quote(comps[g['component']]['keyword'])}",
                    "picks": picks,
                })
        if rows:
            out["items"][item_id] = rows

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    n = sum(len(g["picks"]) for rows in out["items"].values() for g in rows)
    print(f"[ok] {len(out['items'])} 个商品 / {n} 条 1688 链接 → data/t1688-links.json")
    for item_id, rows in out["items"].items():
        print(f"  {item_id}")
        for g in rows:
            prices = [p["price"] for p in g["picks"] if p["price"]]
            print(f"    {g['label']}：{len(g['picks'])} 家"
                  f"（¥{min(prices):g}–{max(prices):g}）" if prices else f"    {g['label']}：{len(g['picks'])} 家")
    if missing:
        print(f"[warn] {len(missing)} 个 id 在池子里没找到（可能下架或换了词）：{', '.join(missing[:6])}",
              file=sys.stderr)


def quote(s):
    from urllib.parse import quote as _q
    return _q(s)


if __name__ == "__main__":
    main()
