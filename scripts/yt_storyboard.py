#!/usr/bin/env python3
"""用 storyboard 做「人物出镜占比」预判——写稿之前就知道这支片子有没有客观镜头。

背景：视频流已关，但 YouTube 仍给 storyboard（sb0，20 张 960×540 均匀抽帧，
一个 mhtml ~700KB）。抽出来拼成一张联络表，人眼一眼就能看出「是不是全程一张脸」。

为什么值得：11-27 实测 10 条计划里 5 条死在「全片人物出镜 / 只有文字卡」，
写完整篇才发现，白烧一轮。这个探针约 10 秒/条，能在选题阶段就把它们剔掉。

用法：
  python3 scripts/yt_storyboard.py --ids LCO58Qvm3ig,fKjgRlBiK9A
  python3 scripts/yt_storyboard.py --plan                 # 读当天计划里所有 pending 条目
  python3 scripts/yt_storyboard.py --plan --limit 15

产出：data/yt-digest/inbox/probe/<slug>.jpg（5×4 联络表），终端打印路径与帧数。
看完判断：人物/脸占比 > 50% 或几乎全是文字卡 → 写稿轮次直接 --abandon，别开工。
"""
import argparse
import io
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "yt-digest" / "inbox"
PROBE = INBOX / "probe"
COOKIES = "/tmp/yt_cookies.txt"

COLS, ROWS = 5, 4
TW, TH = 320, 180


def load_plan(day):
    p = INBOX / f"{day}-plan.json"
    if not p.exists():
        return []
    try:
        items = json.loads(p.read_text("utf-8")).get("items") or []
    except Exception:
        return []
    return [it for it in items if it.get("status", "pending") == "pending"]


def fetch_mhtml(video_id: str, work: Path) -> Path | None:
    out = work / f"{video_id}.mhtml"
    if out.exists() and out.stat().st_size > 10000:
        return out
    cmd = ["yt-dlp", "--no-warnings", "-f", "sb0",
           "-o", str(work / f"{video_id}.%(ext)s"),
           f"https://www.youtube.com/watch?v={video_id}"]
    if Path(COOKIES).exists():
        cmd[1:1] = ["--cookies", COOKIES]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print(f"  [timeout] {video_id}")
        return None
    if not out.exists():
        msg = (r.stderr or "").strip().splitlines()[-1:] or ["?"]
        print(f"  [fail] {video_id}｜{msg[0][:110]}")
        return None
    return out


def extract_frames(mhtml: Path) -> list[Image.Image]:
    raw = mhtml.read_bytes()
    m = re.search(rb'boundary="?([^"\r\n;]+)"?', raw)
    if not m:
        return []
    body = raw.split(b"--" + m.group(1))
    frames = []
    for part in body:
        head, _, payload = part.partition(b"\r\n\r\n")
        if b"image/" not in head:
            continue
        try:
            frames.append(Image.open(io.BytesIO(payload.rstrip(b"\r\n"))).convert("RGB"))
        except Exception:
            continue
    return frames


def build_sheet(frames: list[Image.Image], out: Path) -> int:
    sheet = Image.new("RGB", (TW * COLS, TH * ROWS), "white")
    for i, im in enumerate(frames[: COLS * ROWS]):
        sheet.paste(im.resize((TW, TH)), ((i % COLS) * TW, (i // COLS) * TH))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=80, optimize=True)
    return len(frames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="逗号分隔的 videoId")
    ap.add_argument("--plan", action="store_true", help="读当天计划里所有 pending 条目")
    ap.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--work", default="/tmp/yt-storyboard")
    args = ap.parse_args()

    rows = []
    if args.ids:
        rows = [{"videoId": x.strip(), "slug": x.strip()} for x in args.ids.split(",") if x.strip()]
    if args.plan:
        for it in load_plan(args.date):
            rows.append({"videoId": it.get("videoId"), "slug": it.get("slug")})
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("[warn] 没有可探测的条目")
        return 1

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    ok = 0
    for r in rows:
        vid, slug = r["videoId"], r["slug"]
        mh = fetch_mhtml(vid, work)
        if not mh:
            continue
        frames = extract_frames(mh)
        if not frames:
            print(f"  [fail] {vid}｜storyboard 解析不出图")
            continue
        out = PROBE / f"{slug}.jpg"
        n = build_sheet(frames, out)
        ok += 1
        print(f"[sheet] {n} 帧 → {out.relative_to(ROOT)}")
    print(f"\n完成 {ok}/{len(rows)} 条。用图片查看工具看每张联络表：人物/脸占比 > 50% 或几乎全是文字卡 → 直接 --abandon。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
