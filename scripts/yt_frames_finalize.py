#!/usr/bin/env python3
"""把抽出来的帧裁切、压缩成站点用配图。

上一步 scripts/yt_grab_frames.js 产出 1920x1080 的 png（含博主出镜的废帧），
这一步只处理人工挑过的帧：裁掉手/杂物 → 缩到 1000–1200 宽 → jpg 压缩。

用法：
  python3 scripts/yt_frames_finalize.py \
    --src /tmp/yt-frames/frames \
    --out data/yt-digest/2026-11-27-xxx/img \
    --picks picks.json

picks.json：
[
  {"src": "t0300.png", "out": "01-hotel-entrance.jpg"},
  {"src": "t1260.png", "out": "05-fengzhao.jpg", "crop": [0.42, 0.42, 0.93, 0.80]}
]
crop 用相对比例 [left, top, right, bottom]，省略即原图。
"""
import argparse
import json
import os
from pathlib import Path

from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="png 帧目录")
    ap.add_argument("--out", required=True, help="输出 img 目录")
    ap.add_argument("--picks", required=True, help="挑选清单 json")
    ap.add_argument("--width", type=int, default=1100)
    ap.add_argument("--quality", type=int, default=84)
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    picks = json.loads(Path(args.picks).read_text("utf-8"))

    total = 0
    for p in picks:
        f = src / p["src"]
        if not f.exists():
            print(f"[skip] 缺帧 {f}")
            continue
        im = Image.open(f).convert("RGB")
        crop = p.get("crop")
        if crop:
            w, h = im.size
            im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
        w, h = im.size
        if w > args.width:
            im = im.resize((args.width, int(h * args.width / w)), Image.LANCZOS)
        dest = out / p["out"]
        im.save(dest, quality=args.quality, optimize=True, progressive=True)
        kb = os.path.getsize(dest) / 1024
        total += kb
        print(f"[ok] {p['out']}  {im.size[0]}x{im.size[1]}  {kb:.0f}KB")
    print(f"[total] {total/1024:.2f}MB / {len(picks)} 张")


if __name__ == "__main__":
    main()
