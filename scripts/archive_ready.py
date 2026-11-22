#!/usr/bin/env python3
"""成品稿归档与图片瘦身。

站点每天新增 1 套成品稿 + 8 张 1080×1440 信息卡，长期跑下去 data/ready/*.json
与 assets/images/ 会线性膨胀（一年约 365 套、2900 张图、300MB 量级），
GitHub Pages 首屏加载与仓库体积都会受影响。

本脚本做两件事，都不删正文、不删图片：
1) 归档：把早于 --keep-days 的成品稿 JSON 从 data/ready/ 移到 data/archive/ready/，
   摘要累积到 data/archive/ready-index.json（含日期、slug、标题、形态、自检分）。
2) 瘦身：把早于 --compress-days 且体积超阈值的配图压到 1200px / q78（原图覆盖，
   文件名不变，所以历史稿件引用不会断）。

用法：
    python3 scripts/archive_ready.py                    # 按默认阈值执行
    python3 scripts/archive_ready.py --dry-run           # 只看会动什么
    python3 scripts/archive_ready.py --keep-days 45 --compress-days 21
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "data" / "ready"
ARCHIVE = ROOT / "data" / "archive" / "ready"
ARCHIVE_INDEX = ROOT / "data" / "archive" / "ready-index.json"
IMAGES = ROOT / "assets" / "images"
AUDIT = ROOT / "data" / "audit.json"

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.json$")
FORM_LABEL = {
    "gzh-article": "公众号·文章",
    "gzh-poster": "公众号·贴图",
    "tt-article": "头条·文章",
    "tt-micro": "头条·微头条",
}


def human(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return f"{nbytes:.1f}{unit}" if unit != "B" else f"{nbytes}B"
        nbytes /= 1024
    return f"{nbytes:.1f}GB"


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def audit_scores() -> dict:
    """sourceItemId -> 最优自检分，归档时留档，方便以后画历史曲线。"""
    out = {}
    data = load_json(AUDIT, {})
    for piece in data.get("pieces") or []:
        sid = piece.get("sourceItemId")
        if not sid:
            continue
        out[sid] = max(out.get(sid, 0), piece.get("score") or 0)
    return out


def summarize(doc: dict, filename: str) -> dict:
    pieces = doc.get("pieces") or []
    return {
        "file": f"data/archive/ready/{filename}",
        "date": doc.get("date") or filename[:10],
        "slug": doc.get("slug") or filename[11:-5],
        "sourceItemId": doc.get("sourceItemId"),
        "sourceTitle": doc.get("sourceTitle"),
        "sourceUrl": doc.get("sourceUrl"),
        "forms": [p.get("id") for p in pieces],
        "formLabels": [FORM_LABEL.get(p.get("id"), p.get("id")) for p in pieces],
        "titles": {p.get("id"): p.get("title") for p in pieces},
        "pieces": len(pieces),
    }


def archive(keep_days: int, dry_run: bool) -> tuple[int, int]:
    cutoff = date.today() - timedelta(days=keep_days)
    scores = audit_scores()
    index = load_json(ARCHIVE_INDEX, {"docs": []})
    known = {d.get("file") for d in index.get("docs") or []}
    moved = 0
    freed = 0

    for f in sorted(READY.glob("*.json")):
        if f.name == "index.json":
            continue
        m = DATE_RE.match(f.name)
        if not m:
            continue
        try:
            fdate = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if fdate >= cutoff:
            continue
        doc = load_json(f, None)
        if not doc:
            print(f"  [skip] {f.name} 读不出来，先不动")
            continue
        row = summarize(doc, f.name)
        row["auditScore"] = scores.get(row.get("sourceItemId"))
        if not dry_run:
            ARCHIVE.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(ARCHIVE / f.name))
        freed += f.stat().st_size
        if row["file"] not in known:
            index.setdefault("docs", []).append(row)
            known.add(row["file"])
        moved += 1
        print(f"  [archive] {f.name} → data/archive/ready/（{row['date']}，{row['pieces']} 形态）")

    if moved and not dry_run:
        index["docs"].sort(key=lambda d: (d.get("date") or "", d.get("slug") or ""))
        index["updatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        index["total"] = len(index["docs"])
        ARCHIVE_INDEX.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVE_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return moved, freed


def compress(compress_days: int, min_kb: int, dry_run: bool) -> tuple[int, int]:
    if not IMAGES.is_dir():
        return 0, 0
    if not shutil.which("magick"):
        print("  [warn] 没装 ImageMagick（magick），跳过图片瘦身")
        return 0, 0
    cutoff = datetime.now() - timedelta(days=compress_days)
    changed = 0
    freed = 0
    for f in sorted(IMAGES.iterdir()):
        if f.suffix.lower() not in (".jpeg", ".jpg", ".png"):
            continue
        st = f.stat()
        if datetime.fromtimestamp(st.st_mtime) >= cutoff:
            continue
        if st.st_size < min_kb * 1024:
            continue
        before = st.st_size
        if not dry_run:
            tmp = f.with_suffix(".tmp" + f.suffix)
            try:
                subprocess.run(
                    ["magick", str(f), "-resize", "1200x1600>", "-quality", "78", "-strip", str(tmp)],
                    check=True, capture_output=True,
                )
            except subprocess.CalledProcessError as exc:
                print(f"  [warn] {f.name} 压缩失败：{exc.stderr.decode()[:120]}")
                tmp.unlink(missing_ok=True)
                continue
            if tmp.stat().st_size >= before:
                tmp.unlink(missing_ok=True)
                continue
            tmp.replace(f)
            after = f.stat().st_size
        else:
            after = int(before * 0.6)
        freed += before - after
        changed += 1
        print(f"  [slim] {f.name} {human(before)} → {human(after)}")
    return changed, freed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-days", type=int, default=45, help="主目录保留最近多少天的成品稿")
    ap.add_argument("--compress-days", type=int, default=21, help="超过多少天的配图参与瘦身")
    ap.add_argument("--min-kb", type=int, default=260, help="小于该体积的图不动")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ready_before = dir_size(READY)
    img_before = dir_size(IMAGES)
    print(f"[start] data/ready {human(ready_before)} / assets/images {human(img_before)}"
          + ("  （dry-run）" if args.dry_run else ""))

    moved, freed_json = archive(args.keep_days, args.dry_run)
    slimmed, freed_img = compress(args.compress_days, args.min_kb, args.dry_run)

    ready_after = dir_size(READY)
    img_after = dir_size(IMAGES)
    print(f"[archive] {moved} 套移入 data/archive/ready/，主目录 {human(ready_before)} → {human(ready_after)}")
    print(f"[slim] {slimmed} 张图瘦身，assets/images {human(img_before)} → {human(img_after)}")
    print(f"[done] 本次释放约 {human(freed_json + freed_img)}")
    if moved and not args.dry_run:
        print("       下一步：python3 scripts/make_ready_embed.py 重建索引后再 git push")


if __name__ == "__main__":
    main()
