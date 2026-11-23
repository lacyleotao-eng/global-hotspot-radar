#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原文配图质检：尺寸/体积/重复/裁边，出拼版图供人工（或 agent 视觉）过一眼，再批准入库。

流程（出稿任务里按序执行）：
  1) ego-browser nodejs < scripts/fetch_source_images.js      # 抓原图
  2) python3 scripts/finalize_source_images.py                # 质检 + 拼版，生成候选
  3) 看一眼 data/source-images/<slug>-sheet.jpg
  4) python3 scripts/finalize_source_images.py --approve property-fee --use 1,2 --drop 3 --note "3 有平台水印"
  5) python3 scripts/rebind_images.py                          # 按「原文图 > 豆包 > ChatGPT > 自制卡」绑图

判定口径：
  - 宽度 <900 或高宽比异常 → 淘汰（像素太差，改让 AI 生成）
  - 小于 60KB → 淘汰（多为缩略图/占位图）
  - md5 相同 → 去重
  - 底部/顶部平台浮层水印：可用 --crop-top / --crop-bottom 裁掉一条，裁切比例写进记录；
    若水印压在画面中间，不要裁，直接 --drop，改用豆包/ChatGPT 生成。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "source-image-raw.json"
OUTDIR = ROOT / "data" / "source-images"
SRCDIR = ROOT / "assets" / "source"
SH = timezone(timedelta(hours=8))

MIN_W, MIN_H = 800, 380
MIN_BYTES = 35000
MAX_W = 1600


def ahash(path: Path) -> int:
    """8x8 均值哈希：同一条视频截出来的两帧、同图不同压缩，都能判重。"""
    im = Image.open(path).convert("L").resize((8, 8), Image.LANCZOS)
    px = list(im.tobytes())
    avg = sum(px) / len(px)
    bits = 0
    for i, v in enumerate(px):
        if v > avg:
            bits |= 1 << i
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def sheet(files: list[dict], out: Path, title: str) -> None:
    """把候选图拼成一张带编号的图，一张图就能看完所有候选。"""
    cols = 3
    cell_w, cell_h = 420, 260
    rows = max(1, (len(files) + cols - 1) // cols)
    canvas = Image.new("RGB", (cols * cell_w, rows * (cell_h + 34) + 56), "#f3f5f9")
    d = ImageDraw.Draw(canvas)
    d.text((16, 18), title, fill="#111827")
    for i, f in enumerate(files):
        cx, cy = (i % cols) * cell_w + 8, 56 + (i // cols) * (cell_h + 34)
        try:
            im = Image.open(ROOT / f["file"]).convert("RGB")
            im.thumbnail((cell_w - 16, cell_h))
            canvas.paste(im, (cx, cy))
        except Exception:
            d.text((cx + 10, cy + 10), "读取失败", fill="#b23b2c")
        d.text((cx + 4, cy + cell_h + 6), f"#{f['index']}  {f['w']}x{f['h']}  {f['bytes'] // 1024}KB  {f['status']}", fill="#111827")
    canvas.save(out, quality=86)


def build(date: str) -> None:
    if not RAW.exists():
        print("[finalize] 没有 data/source-image-raw.json，先跑 fetch_source_images.js")
        raise SystemExit(1)
    raw = json.loads(RAW.read_text(encoding="utf-8")).get("items") or {}
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for slug, arr in raw.items():
        seen: set[str] = set()
        hashes: list[int] = []
        rows: list[dict] = []
        for i, it in enumerate(arr, 1):
            p = ROOT / it["file"]
            if not p.exists():
                continue
            try:
                im = Image.open(p)
                w, h = im.size
            except Exception:
                continue
            md5 = hashlib.md5(p.read_bytes()).hexdigest()
            status, why = "candidate", ""
            ah = ahash(p)
            if md5 in seen:
                status, why = "drop", "与前面重复"
            elif any(hamming(ah, prev) <= 5 for prev in hashes):
                status, why = "drop", "与前面近似重复（同一场景）"
            elif w < MIN_W or h < MIN_H:
                status, why = "drop", f"像素不足 {w}x{h}"
            elif p.stat().st_size < MIN_BYTES:
                status, why = "drop", "体积过小（缩略图）"
            seen.add(md5)
            hashes.append(ah)
            # 压到网页可用尺寸
            if status != "drop" and w > MAX_W:
                im = im.convert("RGB")
                im.thumbnail((MAX_W, MAX_W * 3))
                jp = p.with_suffix(".jpeg")
                im.save(jp, quality=84)
                if jp != p:
                    p.unlink(missing_ok=True)
                it["file"] = str(jp.relative_to(ROOT))
                w, h = im.size
            rows.append({
                "index": i, "file": it["file"], "bytes": p.stat().st_size if p.exists() else it.get("bytes", 0),
                "w": w, "h": h, "url": it.get("url"), "page": it.get("page"),
                "alt": it.get("alt") or "", "md5": md5, "status": status, "reason": why,
                "crop": "", "approved": False,
            })
        payload = {
            "slug": slug, "date": date,
            "builtAt": datetime.now(SH).isoformat(timespec="seconds"),
            "candidates": rows,
        }
        (OUTDIR / f"{slug}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ok = [r for r in rows if r["status"] == "candidate"]
        if ok:
            sheet(rows, OUTDIR / f"{slug}-sheet.jpg", f"{slug} 原文配图候选（{date}）· #编号 尺寸 体积 状态")
        print(f"[ok] {slug}: 候选 {len(rows)}，可用 {len(ok)} → {OUTDIR / (slug + '-sheet.jpg') if ok else '无拼版图'}")


def approve(slug: str, use: list[int], drop: list[int], note: str, crop_top: int, crop_bottom: int) -> None:
    p = OUTDIR / f"{slug}.json"
    if not p.exists():
        print(f"[approve] 没有 {p}")
        raise SystemExit(1)
    d = json.loads(p.read_text(encoding="utf-8"))
    final: list[dict] = []
    for r in d["candidates"]:
        i = r["index"]
        if i in drop:
            r["status"], r["approved"] = "drop", False
            r["reason"] = r["reason"] or "人工淘汰" + (f"：{note}" if note else "")
            continue
        if i not in use:
            continue
        src = ROOT / r["file"]
        if not src.exists():
            # 拼版/压缩后扩展名变了，按同名前缀找一个能读的
            alt = next(iter(sorted(src.parent.glob(src.stem + ".*"))), None)
            if not alt or not alt.is_file():
                print(f"[approve] 跳过缺失文件 {r['file']}")
                continue
            src = alt
            r["file"] = str(alt.relative_to(ROOT))
        im = Image.open(src)
        w, h = im.size
        if crop_top or crop_bottom:
            top = int(h * crop_top / 100)
            bottom = h - int(h * crop_bottom / 100)
            im = im.crop((0, top, w, bottom))
            out = src.with_name(src.stem.replace("raw", "use") + ".jpeg")
            im.convert("RGB").save(out, quality=85)
            src.unlink(missing_ok=True)
            r["file"] = str(out.relative_to(ROOT))
            r["w"], r["h"] = im.size
            r["bytes"] = out.stat().st_size
            r["crop"] = f"top {crop_top}% bottom {crop_bottom}%".strip()
        r["status"], r["approved"] = "approved", True
        r["reason"] = note or ""
        final.append(r)
    d["candidates"] = d["candidates"]
    d["approved"] = final
    d["approvedAt"] = datetime.now(SH).isoformat(timespec="seconds")
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[approve] {slug}: 采用 {len(final)} 张 → {[f['file'] for f in final]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(SH).strftime("%Y-%m-%d"))
    ap.add_argument("--approve", metavar="SLUG")
    ap.add_argument("--use", default="")
    ap.add_argument("--drop", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--crop-top", type=int, default=0, help="裁掉顶部百分比（去平台浮层）")
    ap.add_argument("--crop-bottom", type=int, default=0)
    a = ap.parse_args()
    if a.approve:
        nums = lambda s: [int(x) for x in str(s).replace("，", ",").split(",") if x.strip().isdigit()]
        approve(a.approve, nums(a.use), nums(a.drop), a.note, a.crop_top, a.crop_bottom)
    else:
        build(a.date)


if __name__ == "__main__":
    main()
