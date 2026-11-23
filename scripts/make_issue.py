#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成当日素材包（issue）：公众号池 + 今日头条池，由发布人自行挑选时段。

为什么是池而不是固定排班：
  发布人每天 9:30 发 1 篇公众号、10:30 / 14:30 / 19:30 各发 1 篇头条，
  但「哪篇配哪个时段」需要人来判断（时效、调性、当天舆情）。
  所以这里只保证「素材够、素材齐、拿到就能发」，不替人做排期。

目标容量（TARGETS 可调）：
  公众号 3 篇（其中至少 1 篇贴图，方便想发图的时候有得选）
  今日头条 6 篇（文章与微头条都要有）

产物：
  data/issue.json        当天素材包
  data/issue-embed.js    <script> 注入版，file:// 打开也能用
  data/issues/YYYY-MM-DD.json  按日存档
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READY_DIR = os.path.join(ROOT, "data", "ready")
PICKS = os.path.join(ROOT, "data", "picks.json")
OUT_JSON = os.path.join(ROOT, "data", "issue.json")
OUT_EMBED = os.path.join(ROOT, "data", "issue-embed.js")
ARCHIVE_DIR = os.path.join(ROOT, "data", "issues")

SH = timezone(timedelta(hours=8))
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

FORM_LABEL = {
    "gzh-article": "公众号文章",
    "gzh-poster": "公众号贴图",
    "tt-article": "头条文章",
    "tt-micro": "微头条",
}
FORM_SHORT = {
    "gzh-article": "文章", "gzh-poster": "贴图",
    "tt-article": "文章", "tt-micro": "微头条",
}

TARGETS = {"公众号": 3, "今日头条": 6}
CAPS = {"公众号": 4, "今日头条": 6}


def now_iso() -> str:
    return datetime.now(SH).replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now(SH).strftime("%Y-%m-%d")


def wc(text: str) -> int:
    return len(CJK_RE.findall(text or ""))


def piece_words(piece: dict) -> int:
    parts = [piece.get("title") or "", piece.get("digest") or ""]
    for b in piece.get("blocks") or []:
        if b.get("text"):
            parts.append(b["text"])
        for x in b.get("items") or []:
            parts.append(x)
    return wc("".join(parts))


def plain_text(piece: dict) -> str:
    """可直接粘贴进公众号/头条编辑器的纯文本。"""
    lines = [piece.get("title") or ""]
    if piece.get("digest"):
        lines += ["", piece["digest"]]
    for b in piece.get("blocks") or []:
        t = b.get("type")
        if t == "h2":
            lines += ["", b.get("text") or ""]
        elif t in ("para", "note"):
            lines += ["", b.get("text") or ""]
        elif t == "list":
            for i, x in enumerate(b.get("items") or [], 1):
                lines.append(f"{i}. {x}")
    imgs = piece.get("images") or []
    if imgs:
        lines += ["", "—— 配图（按顺序插入正文）——"]
        for i, im in enumerate(imgs, 1):
            lines.append(f"图{i}：{im.get('caption') or ''}")
    return "\n".join(lines).strip()


def load_ready() -> list[dict]:
    docs = []
    for path in sorted(glob.glob(os.path.join(READY_DIR, "*.json"))):
        if os.path.basename(path) == "index.json":
            continue
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        d["_file"] = os.path.basename(path)
        docs.append(d)
    return docs


def asset_of(doc: dict, piece: dict, rank: int) -> dict:
    fid = piece.get("id") or ""
    return {
        "itemId": doc.get("sourceItemId") or "",
        "slug": os.path.splitext(doc.get("_file") or "")[0],
        "docFile": doc.get("_file") or "",
        "pieceId": fid,
        "formLabel": FORM_LABEL.get(fid, fid),
        "formShort": FORM_SHORT.get(fid, fid),
        "title": piece.get("title") or "",
        "digest": piece.get("digest") or "",
        "words": piece_words(piece),
        "images": piece.get("images") or [],
        "imageCount": len(piece.get("images") or []),
        "verification": doc.get("verification") or "",
        "verificationNote": doc.get("verificationNote") or "",
        "imageNote": doc.get("imageNote") or "",
        "sourceTitle": doc.get("sourceTitle") or "",
        "sourceUrl": doc.get("sourceUrl") or "",
        "date": doc.get("date") or "",
        "batch": doc.get("batch") or "morning",
        "rank": rank,
        "text": plain_text(piece),
    }


def main() -> None:
    date = today()
    docs = load_ready()
    if not docs:
        print("[issue] 没有任何成品稿，无法生成素材包")
        sys.exit(1)

    today_docs = [d for d in docs if d.get("date") == date]
    pool_docs = today_docs or docs
    stale = not today_docs

    order: dict[str, int] = {}
    picks_date = None
    try:
        picks = json.load(open(PICKS, encoding="utf-8"))
        picks_date = picks.get("date")
        n = 0
        for target in ("公众号", "今日头条"):
            for pick in (picks.get("groups") or {}).get(target) or []:
                iid = pick.get("itemId")
                if iid and iid not in order:
                    n += 1
                    order[iid] = n
    except Exception as exc:
        print(f"[issue] warn: 读 picks 失败 {exc}")

    def doc_rank(d: dict) -> tuple:
        iid = d.get("sourceItemId") or ""
        return (order.get(iid, 999), -(len(d.get("pieces") or [])))

    ordered_docs = sorted(pool_docs, key=doc_rank)

    pools = {}
    for target, forms in (("公众号", ("gzh-article", "gzh-poster")),
                          ("今日头条", ("tt-article", "tt-micro"))):
        assets: list[dict] = []
        rank = 0
        for d in ordered_docs:
            for fid in forms:
                for p in d.get("pieces") or []:
                    if p.get("id") != fid:
                        continue
                    rank += 1
                    assets.append(asset_of(d, p, rank))
        cap = CAPS[target]
        existed = len(assets)
        if target == "公众号" and existed > cap:
            posters = [a for a in assets if a["pieceId"] == "gzh-poster"]
            articles = [a for a in assets if a["pieceId"] != "gzh-poster"]
            assets = (articles[:cap - 1] + posters[:1]) if posters else articles[:cap]
        else:
            assets = assets[:cap]
        pools[target] = {
            "target": TARGETS[target],
            "available": len(assets),
            "totalExisted": existed,
            "done": len(assets) >= TARGETS[target],
            "items": assets,
        }

    ok = all(v["done"] for v in pools.values())
    status = "ready" if ok and not stale else ("partial" if any(v["items"] for v in pools.values()) else "missing")
    note_parts = []
    if stale:
        note_parts.append(f"今天还没有成品稿，下面是最近一版（{pool_docs[0].get('date')}）")
    for t, v in pools.items():
        if not v["done"]:
            note_parts.append(f"{t}只备了 {v['available']} 篇（目标 {v['target']}）")

    out = {
        "date": date,
        "generatedAt": now_iso(),
        "stale": stale,
        "status": status,
        "picksDate": picks_date,
        "targets": TARGETS,
        "usage": {
            "公众号": "每天 09:30 发 1 篇，从公众号池里挑",
            "今日头条": "每天 10:30 / 14:30 / 19:30 各 1 篇，从头条池里挑 3 篇",
        },
        "pools": pools,
        "note": "；".join(note_parts),
    }

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    for path in (OUT_JSON, os.path.join(ARCHIVE_DIR, f"{date}.json")):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")
    with open(OUT_EMBED, "w", encoding="utf-8") as f:
        f.write("window.__ISSUE__ = ")
        json.dump(out, f, ensure_ascii=False)
        f.write(";\n")

    print(f"[issue] {date} 素材包 {status}" + (f"  {out['note']}" if out["note"] else ""))
    for t, v in pools.items():
        flag = "OK" if v["done"] else "缺"
        print(f"  [{flag}] {t} {v['available']}/{v['target']} 篇（库里共 {v['totalExisted']} 篇）")
        for a in v["items"]:
            print(f"        {a['formShort']:<3} {a['words']:>4}字 {a['imageCount']}图  {a['title'][:26]}")
    if status != "ready":
        sys.exit(2)


if __name__ == "__main__":
    main()
