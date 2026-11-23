#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为今天的成品稿生成「原文抓图请求」：每个选题给 1-3 个原文链接。

为什么要有这一步：头条文章页在未登录/反爬状态下会跳回首页，抓不到正文图；
但成品稿的 citations 里通常有真正的出处（微信公众号原文、新浪、澎湃、地方媒体），
那里的图才是原始图。所以按「微信公众号原文 > 通讯社/央媒 > 地方媒体 > 门户转载」排序取前 3 个。

用法：
    python3 scripts/build_source_image_requests.py --date 2026-11-23
    python3 scripts/build_source_image_requests.py --only property-fee,orchard-livestream
输出：data/source-image-requests.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "data" / "ready"
OUT = ROOT / "data" / "source-image-requests.json"
SH = timezone(timedelta(hours=8))

# 出图质量：优先级数字越小越优先
RANK = [
    (r"mp\.weixin\.qq\.com", 1),          # 公众号原文，图最全
    (r"(xinhuanet|news\.cn|people\.com\.cn|cctv|chinanews|thepaper|bjnews|caixin)", 2),
    (r"(sina|163|qq|sohu|ifeng|guancha|jiemian|yicai|stcn|cls\.cn)", 3),
    (r"toutiao\.com", 6),                  # 头条自身反而抓不到，放最后
]
SKIP = (r"(weibo\.com|zhihu\.com|douyin\.com|xiaohongshu\.com|bilibili\.com|github\.com|"
        r"youtube\.com|twitter\.com|x\.com|reddit\.com|medium\.com|apps\.apple\.com)")


def rank_of(url: str) -> int:
    import re
    for pat, r in RANK:
        if re.search(pat, url):
            return r
    return 4


def usable(url: str) -> bool:
    import re
    if not url or not url.startswith("http"):
        return False
    if re.search(SKIP, url):
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(SH).strftime("%Y-%m-%d"))
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = {s.strip() for s in a.only.split(",") if s.strip()}

    # items.json 里的 citations 比成品稿更全，合并进来
    item_cites: dict[str, list[str]] = {}
    try:
        for it in (json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8")).get("items") or []):
            item_cites[it.get("id") or ""] = [c.get("url") for c in (it.get("citations") or []) if c.get("url")]
    except Exception:
        pass

    jobs = []
    for path in sorted(READY.glob(f"{a.date}-*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        slug = d.get("slug") or path.stem.replace(f"{a.date}-", "")
        if only and slug not in only:
            continue
        urls: list[tuple[int, str]] = []
        for c in d.get("citations") or []:
            u = c.get("url") or ""
            if usable(u):
                urls.append((rank_of(u), u))
        for u in item_cites.get(d.get("sourceItemId") or "", []):
            if usable(u):
                urls.append((rank_of(u), u))
        su = d.get("sourceUrl") or ""
        if usable(su):
            urls.append((rank_of(su), su))
        urls.sort(key=lambda x: x[0])
        seen, picked = set(), []
        for _, u in urls:
            key = urlparse(u).netloc + urlparse(u).path[:40]
            if key in seen:
                continue
            seen.add(key)
            picked.append(u)
            if len(picked) >= 3:
                break
        if not picked:
            print(f"[skip] {slug}: 没有可抓的原文链接")
            continue
        jobs.append({"slug": slug, "urls": picked})
        print(f"[ok] {slug}: {len(picked)} 个链接 → {[urlparse(u).netloc for u in picked]}")

    OUT.write_text(json.dumps({"builtAt": datetime.now(SH).isoformat(timespec="seconds"), "jobs": jobs},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[done] {len(jobs)} 个选题 → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
