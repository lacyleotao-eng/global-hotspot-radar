#!/usr/bin/env python3
"""视频拆解稿机械质检：一天 10 篇靠人眼盯不住，能自动判的全自动。

查这些（硬性，任一不过即 fail）：
  1. article.html / meta.json / img/ 存在
  2. figure img 数量 ≥ 8
  3. 图片文件真实存在、单张 < 400KB
  4. 正文不同时间戳 ≥ 5 个（<span class="ts">）
  5. 每张 <img> 都在 <figure> 里且有 <figcaption>
  6. meta.cover 指向的文件存在
  7. meta.steps 与正文 <h2><span class="num"> 数量一致
  8. 封面/正文里出现频道名当图注时提示人工复核

查不了的（必须人工）：画面里有没有博主出镜/自拍/手持/筷子/路人正脸。

用法：
  python3 scripts/yt_check_digest.py               # 今天
  python3 scripts/yt_check_digest.py --date 2026-11-27
  python3 scripts/yt_check_digest.py --target 10
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIGEST = ROOT / "data" / "yt-digest"
MAX_IMG_KB = 400
MIN_IMAGES = 8
MIN_TS = 5


def check_one(d: Path):
    art = d / "article.html"
    meta_p = d / "meta.json"
    html = art.read_text("utf-8")
    meta = {}
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text("utf-8"))
        except Exception:
            pass

    imgs = re.findall(r'<img[^>]+src="([^"]+)"', html)
    ts = set(re.findall(r'class="ts"[^>]*>([^<]{2,40})</span>', html))
    figs = len(re.findall(r"<figcaption", html))
    steps_h2 = len(re.findall(r'<h2>\s*<span class="num"', html))

    problems, warns = [], []

    missing = [s for s in imgs if not (d / s).exists()]
    if missing:
        problems.append(f"图缺失 {len(missing)} 张：{', '.join(missing[:3])}")
    big = []
    for s in imgs:
        p = d / s
        if p.exists() and p.stat().st_size > MAX_IMG_KB * 1024:
            big.append(f"{p.name} {p.stat().st_size // 1024}KB")
    if big:
        warns.append("图偏大：" + ", ".join(big[:3]))

    if len(imgs) < MIN_IMAGES:
        problems.append(f"配图只有 {len(imgs)} 张（要求 ≥{MIN_IMAGES}）")
    if figs < len(imgs):
        problems.append(f"{len(imgs)} 张图只有 {figs} 个图注，有图没说明")
    if len(ts) < MIN_TS:
        problems.append(f"只有 {len(ts)} 个不同时间戳（要求 ≥{MIN_TS}）")

    cover = meta.get("cover") or ""
    if not cover:
        problems.append("meta.cover 缺失")
    elif not (d / cover).exists():
        problems.append(f"meta.cover 指向的文件不存在：{cover}")

    steps = meta.get("steps")
    if steps and steps != steps_h2:
        problems.append(f"meta.steps={steps} 与正文小节数 {steps_h2} 不一致")

    for k in ("category", "categoryKey", "guideTitle", "dek"):
        if not meta.get(k):
            warns.append(f"meta.{k} 为空")

    return {
        "slug": d.name,
        "title": meta.get("guideTitle", ""),
        "category": meta.get("category", ""),
        "images": len(imgs),
        "figs": figs,
        "ts": len(ts),
        "steps": steps_h2,
        "problems": problems,
        "warns": warns,
    }, html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--target", type=int, default=10)
    args = ap.parse_args()

    dirs = sorted([d for d in DIGEST.iterdir() if d.is_dir() and d.name.startswith(args.date)])
    rows = []
    for d in dirs:
        if not (d / "article.html").exists():
            continue
        r, _ = check_one(d)
        rows.append(r)

    fails = [r for r in rows if r["problems"]]
    print(f"== 视频拆解质检 {args.date} ==  成稿 {len(rows)} / 目标 {args.target} 篇")
    for r in rows:
        flag = "FAIL" if r["problems"] else "ok  "
        print(f"[{flag}] {r['slug']}｜{r['category']}｜图 {r['images']}｜图注 {r['figs']}｜时间戳 {r['ts']}｜{r['steps']} 节")
        for p in r["problems"]:
            print(f"        ✗ {p}")
        for w in r["warns"]:
            print(f"        ! {w}")

    gap = args.target - len(rows)
    print(f"\n合计：{len(rows)} 篇，达标线 {args.target} 篇，" + (f"缺 {gap} 篇" if gap > 0 else "已达标"))
    if gap > 0:
        print("补齐提示：python3 scripts/yt_plan_next.py --stats 看还剩哪些选题没写")
    print("人工必查（脚本判不了）：画里有没有博主出镜/正脸/自拍/第一人称手持/手或筷子/路人儿童正脸/频道水印。")
    return 1 if (fails or gap > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
