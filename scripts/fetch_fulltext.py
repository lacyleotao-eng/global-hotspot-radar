#!/usr/bin/env python3
"""抓原文全文并量化结构，供「出稿核对事实」与「爆款对标算准字数」两处使用。

为什么需要它：采集/出稿环节目前靠 WebFetch，返回的是被模型摘要过的 markdown，
数字、引语、段落结构都会丢失甚至走样。爆款对标的 anatomy.wordCount 因此只能靠估，
实测与记录偏差可达 ±15%，85 分闸门的基准就不可信。

用法（必须用装了 crawl4ai 的解释器）：
    /Users/lee/.wb-tools/crawl4ai-venv/bin/python scripts/fetch_fulltext.py --date 2026-11-26
    /Users/lee/.wb-tools/crawl4ai-venv/bin/python scripts/fetch_fulltext.py --url https://xxx --slug test
    /Users/lee/.wb-tools/crawl4ai-venv/bin/python scripts/fetch_fulltext.py --viral 6   # 校验最近 6 条爆款样本

输出：
    data/fulltext/<date>/<slug>.md    干净正文（写稿时读这个，不要读摘要）
    data/fulltext/<date>/<slug>.json  {url, ok, cjk, paras, subheads, images, note}
    data/fulltext/<date>/_index.json  本轮汇总

已知边界（实测 2026-11-26）：
    - 微信公众号：默认 UA 会拿到「环境异常」页，必须伪装桌面 Chrome UA 才通。
    - 今日头条 / 微博 / 小红书 / 抖音：结构性反爬或需登录态，headless 一律拿不到，
      这些站继续走 ego-browser（带已登录 profile），不要用本脚本硬试。
    - markdown 里的图片受懒加载影响会漏，所以图片数改从 HTML 里数 <img>（含 data-src）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SH = timezone(timedelta(hours=8))
CJK = re.compile(r"[\u4e00-\u9fff]")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# 这些站在 headless 下必被拦，试也没用，直接跳过并说明原因
HARD_BLOCK = ("toutiao.com", "weibo.com", "xiaohongshu.com", "douyin.com", "zhihu.com")


def today() -> str:
    return datetime.now(SH).strftime("%Y-%m-%d")


def plan_events(date: str) -> list[dict]:
    p = DATA / "plan" / f"{date}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("events") or []


def url_of(event: dict) -> str:
    for key in ("sourceUrl", "url"):
        if event.get(key):
            return event[key]
    for c in event.get("citations") or []:
        u = c.get("url") if isinstance(c, dict) else ""
        if u and "mp.weixin.qq.com" in u:
            return u
    for c in event.get("citations") or []:
        u = c.get("url") if isinstance(c, dict) else ""
        if u:
            return u
    return ""


def html_img_count(html: str) -> int:
    """从 HTML 数正文图片：优先 data-src（微信/头条懒加载），再去重。"""
    urls = set()
    for attr in ("data-src", "data-original", "data-lazy-src", "src"):
        for m in re.finditer(rf'<img[^>]+{attr}="([^"]+)"', html or ""):
            u = m.group(1)
            if u.startswith("data:") or len(u) < 20:
                continue
            urls.add(u.split("?")[0])
    return len(urls)


def md_stats(md: str) -> dict:
    lines = [l.strip() for l in md.splitlines() if l.strip()]
    paras = [
        l for l in lines
        if not l.startswith(("#", "|", "!", "```", "- ", "* ", ">", "1.", "2.", "3.", "4.", "5."))
    ]
    subs = [l for l in lines if l.startswith(("## ", "### "))]
    return {
        "cjk": len(CJK.findall(md)),
        "paras": len(paras),
        "subheads": len(subs),
        "mdChars": len(md),
    }


async def crawl(jobs: list[dict], out_dir: Path, date: str) -> list[dict]:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    out_dir.mkdir(parents=True, exist_ok=True)
    browser = BrowserConfig(headless=True, user_agent=UA, verbose=False)
    run = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=45000)
    index: list[dict] = []

    async with AsyncWebCrawler(config=browser) as c:
        for job in jobs:
            slug, url = job["slug"], job["url"]
            note = ""
            if any(h in url for h in HARD_BLOCK):
                row = {"slug": slug, "url": url, "ok": False, "note": "强反爬/需登录，改用 ego-browser"}
                index.append(row)
                print(f"[skip] {slug}: 强反爬站点，改用 ego-browser")
                continue
            try:
                r = await c.arun(url=url, config=run)
                md = r.markdown.raw_markdown if r.success else ""
                if not r.success or len(CJK.findall(md)) < 60:
                    note = (str(r.error_message)[:120] if not r.success else "正文过短（可能被拦或页面改版）")
                    index.append({"slug": slug, "url": url, "ok": False, "note": note})
                    print(f"[fail] {slug}: {note}")
                    continue
                st = md_stats(md)
                imgs = html_img_count(getattr(r, "html", "") or "")
                row = {"slug": slug, "url": url, "ok": True, "images": imgs, **st, "note": note}
                (out_dir / f"{slug}.md").write_text(md, encoding="utf-8")
                (out_dir / f"{slug}.json").write_text(
                    json.dumps({**row, "fetchedAt": datetime.now(SH).isoformat(timespec="seconds")},
                               ensure_ascii=False, indent=1), encoding="utf-8")
                index.append(row)
                print(f"[ok]   {slug}: 汉字 {st['cjk']} / 段 {st['paras']} / 小标题 {st['subheads']} / 图 {imgs}")
            except Exception as e:  # noqa: BLE001
                index.append({"slug": slug, "url": url, "ok": False, "note": f"{type(e).__name__}: {e}"[:160]})
                print(f"[err]  {slug}: {type(e).__name__} {str(e)[:100]}")
    (out_dir / "_index.json").write_text(
        json.dumps({"date": date, "generatedAt": datetime.now(SH).isoformat(timespec="seconds"),
                    "rows": index}, ensure_ascii=False, indent=1), encoding="utf-8")
    return index


def viral_jobs(n: int) -> list[dict]:
    jobs = []
    for f in sorted((DATA / "viral-inbox").glob("*.json"))[-n:]:
        d = json.loads(f.read_text(encoding="utf-8"))
        items = d if isinstance(d, list) else [d]
        for it in items:
            u = it.get("url") or it.get("sourceUrl") or ""
            if u:
                title = (it.get("title") or f.stem)[:14]
                jobs.append({"slug": re.sub(r"[^\w\u4e00-\u9fff-]", "", f.stem)[:28] + "-" + title,
                             "url": u, "recorded": (it.get("anatomy") or {}).get("wordCount")})
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today())
    ap.add_argument("--slug", default="", help="只抓这些 slug，逗号分隔")
    ap.add_argument("--url", default="", help="直接指定正文 URL，配合 --slug 使用")
    ap.add_argument("--viral", type=int, default=0, help="校验最近 N 个爆款样本的真实字数")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    if a.url:
        jobs = [{"slug": a.slug or "adhoc", "url": a.url}]
    elif a.viral:
        jobs = viral_jobs(a.viral)
    else:
        want = {s.strip() for s in a.slug.split(",") if s.strip()}
        jobs = [{"slug": e["slug"], "url": url_of(e)} for e in plan_events(a.date)
                if (not want or e["slug"] in want) and url_of(e)]
        missing = [e["slug"] for e in plan_events(a.date) if (not want or e["slug"] in want) and not url_of(e)]
        if missing:
            print(f"[warn] 无可用链接，跳过：{', '.join(missing)}")
    if a.limit:
        jobs = jobs[: a.limit]
    if not jobs:
        print("没有可抓的 URL")
        sys.exit(0)

    out_dir = DATA / "fulltext" / a.date
    index = asyncio.run(crawl(jobs, out_dir, a.date))

    if a.viral:
        print("\n=== 爆款字数：记录值 vs 实测 ===")
        rec = {j["slug"]: j.get("recorded") for j in jobs}
        for row in index:
            if not row.get("ok"):
                continue
            old = {j["slug"]: j.get("recorded") for j in jobs}.get(row["slug"])
            if old:
                print(f"  {row['slug'][:34]:<34} 记录 {old:>5} → 实测 {row['cjk']:>5} "
                      f"({(row['cjk'] - old) / max(old, 1) * 100:+.0f}%)")

    ok = sum(1 for r in index if r.get("ok"))
    print(f"\n完成 {ok}/{len(index)}，输出目录 {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
