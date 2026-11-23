#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成当日素材包（issue）：公众号池 + 今日头条池，由发布人自行挑选时段。

链路定位：这是流水线的倒数第二环——「达标自检 → 今日发布」。
  - 只收当天（date == today）的成品稿；没有当天稿就回退最近一版并标 stale。
  - 只收自检 ≥ PASS_SCORE 的稿；低于 85 分一律判「淘汰」，不出现发布池里。
  - 没跑过自检的稿按「待检」处理，宁可少发也不放未质检的稿出去。

目标容量：
  公众号 6 篇（文章最多 4 + 贴图最多 3，总数 6，形态必须混搭）
  今日头条 8 篇（文章最多 4 + 微头条最多 4）

产物：
  data/issue.json        当天素材包（含 funnel 漏斗数字，供前端流水线展示）
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
ITEMS = os.path.join(ROOT, "data", "items.json")
AUDIT = os.path.join(ROOT, "data", "audit.json")
OUT_JSON = os.path.join(ROOT, "data", "issue.json")
OUT_EMBED = os.path.join(ROOT, "data", "issue-embed.js")
ARCHIVE_DIR = os.path.join(ROOT, "data", "issues")

SH = timezone(timedelta(hours=8))
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 自检达标线（与 audit_ready.py 的 PASS_SCORE 保持一致）
PASS_SCORE = 85

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

TARGETS = {"公众号": 6, "今日头条": 8}
# 每个去向的形态配额：总数满即停，各形态有上限，保证「文章 + 图文短稿」混搭
QUOTA = {
    "公众号": [("gzh-article", 4), ("gzh-poster", 3)],
    "今日头条": [("tt-article", 4), ("tt-micro", 4)],
}


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


def load_scores() -> tuple[dict, str | None]:
    """(file::form) -> {score, grade, gaps}。没有自检数据时返回空表，全部当待检。"""
    try:
        a = json.load(open(AUDIT, encoding="utf-8"))
    except Exception:
        return {}, None
    table = {}
    for p in a.get("pieces") or []:
        key = f"{p.get('file')}::{p.get('form')}"
        table[key] = {
            "score": p.get("score"),
            "grade": p.get("grade"),
            "gaps": p.get("gaps") or [],
        }
    return table, a.get("updatedAt")


def asset_of(doc: dict, piece: dict, rank: int, audit: dict) -> dict:
    fid = piece.get("id") or ""
    rec = audit.get(f"{doc.get('_file')}::{fid}") or {}
    score = rec.get("score")
    passed = score is not None and score >= PASS_SCORE
    return {
        "itemId": doc.get("sourceItemId") or "",
        "slug": os.path.splitext(doc.get("_file") or "")[0],
        "docFile": doc.get("_file") or "",
        "pieceId": fid,
        "formLabel": FORM_LABEL.get(fid, fid),
        "formShort": FORM_SHORT.get(fid, fid),
        "target": "公众号" if fid.startswith("gzh") else "今日头条",
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
        "score": score,
        "passed": passed,
        "grade": rec.get("grade") or ("待检" if score is None else ""),
        "gaps": rec.get("gaps") or [],
        "text": plain_text(piece),
    }


def load_intel() -> tuple[int, int]:
    """(情报条数, 选题线索条数)。漏斗第一、二格的数字必须来自原始情报，不用下游的派生值。"""
    try:
        items = (json.load(open(ITEMS, encoding="utf-8")).get("items")) or []
    except Exception:
        return 0, 0
    leads = sum(len(i.get("leads") or []) for i in items)
    return len(items), leads


def main() -> None:
    date = today()
    docs = load_ready()
    if not docs:
        print("[issue] 没有任何成品稿，无法生成素材包")
        sys.exit(1)

    audit, audit_updated = load_scores()

    today_docs = [d for d in docs if d.get("date") == date]
    pool_docs = today_docs or docs
    stale = not today_docs

    order: dict[str, int] = {}
    allowed: set[tuple[str, str]] = set()
    picks_date = None
    picks_total = 0
    leads_total = 0
    try:
        picks = json.load(open(PICKS, encoding="utf-8"))
        picks_date = picks.get("date")
        leads_total = picks.get("totalScored") or 0
        n = 0
        for target in ("公众号", "今日头条"):
            rows = (picks.get("groups") or {}).get(target) or []
            picks_total += len(rows)
            for pick in rows:
                iid = pick.get("itemId")
                if iid and iid not in order:
                    n += 1
                    order[iid] = n
                # build_picks_from_ready 产出的 picks 带 pieceId：发布池必须是选题池的子集
                if iid and pick.get("pieceId"):
                    allowed.add((iid, pick["pieceId"]))
    except Exception as exc:
        print(f"[issue] warn: 读 picks 失败 {exc}")

    def doc_rank(d: dict) -> tuple:
        iid = d.get("sourceItemId") or ""
        return (order.get(iid, 999), -(len(d.get("pieces") or [])))

    ordered_docs = sorted(pool_docs, key=doc_rank)

    # 先把当天所有成品稿摊平，再按「自检闸门 + 形态配额」挑进发布池
    all_assets: list[dict] = []
    rank = 0
    for d in ordered_docs:
        for p in d.get("pieces") or []:
            rank += 1
            all_assets.append(asset_of(d, p, rank, audit))

    rejected = [a for a in all_assets if a["score"] is not None and not a["passed"]]
    pending = [a for a in all_assets if a["score"] is None]
    passed_assets = [a for a in all_assets if a["passed"]]
    # 选题池是「计划」，发布池是「交付」：有 pieceId 的 picks 就是硬约束，发布池只能从里面取
    if allowed:
        outside = [a for a in passed_assets if (a["itemId"], a["pieceId"]) not in allowed]
        if outside:
            print(f"[issue] 有 {len(outside)} 篇过了自检但不在今日选题里，不进发布池")
        passed_assets = [a for a in passed_assets if (a["itemId"], a["pieceId"]) in allowed]

    pools = {}
    for target, quota in QUOTA.items():
        cap = TARGETS[target]
        chosen: list[dict] = []
        for fid, limit in quota:
            bucket = [a for a in passed_assets if a["pieceId"] == fid]
            take = bucket[: max(0, min(limit, cap - len(chosen)))]
            chosen.extend(take)
        # 配额填不满时用同去向其他形态补，总数不超 cap
        if len(chosen) < cap:
            rest = [a for a in passed_assets if a["target"] == target and a not in chosen]
            chosen.extend(rest[: cap - len(chosen)])
        pools[target] = {
            "target": TARGETS[target],
            "available": len(chosen),
            "totalExisted": len([a for a in all_assets if a["target"] == target]),
            "rejected": len([a for a in rejected if a["target"] == target]),
            "pending": len([a for a in pending if a["target"] == target]),
            "done": len(chosen) >= cap,
            "items": chosen,
        }

    ok = all(v["done"] for v in pools.values())
    status = "ready" if ok and not stale else ("partial" if any(v["items"] for v in pools.values()) else "missing")
    note_parts = []
    if stale:
        note_parts.append(f"今天还没有成品稿，下面是最近一版（{pool_docs[0].get('date')}）")
    for t, v in pools.items():
        if not v["done"]:
            note_parts.append(f"{t}只过了 {v['available']} 篇（目标 {v['target']}）")
        if v["rejected"]:
            note_parts.append(f"{t}自检淘汰 {v['rejected']} 篇")
        if v["pending"]:
            note_parts.append(f"{t}{v['pending']} 篇还没跑自检")
    if not audit:
        note_parts.append("没有自检数据，发布池为空——先跑 scripts/audit_ready.py")

    intel_n, lead_n = load_intel()
    funnel = {
        "intel": intel_n,
        "leads": lead_n or leads_total,
        "picks": picks_total,
        "drafted": len(all_assets),
        "passed": len(passed_assets),
        "rejected": len(rejected),
        "pending": len(pending),
        "publishable": sum(v["available"] for v in pools.values()),
    }

    out = {
        "date": date,
        "generatedAt": now_iso(),
        "stale": stale,
        "status": status,
        "picksDate": picks_date,
        "auditUpdatedAt": audit_updated,
        "passScore": PASS_SCORE,
        "targets": TARGETS,
        "funnel": funnel,
        "usage": {
            "公众号": "公众号每天 1 篇，从这 6 篇里挑",
            "今日头条": "头条每天 3 篇，从这 8 篇里挑",
        },
        "pools": pools,
        "rejected": [
            {
                "title": a["title"], "formLabel": a["formLabel"], "target": a["target"],
                "score": a["score"], "gaps": a["gaps"][:2], "docFile": a["docFile"],
                "pieceId": a["pieceId"],
            }
            for a in rejected
        ],
        "pending": [
            {"title": a["title"], "formLabel": a["formLabel"], "target": a["target"], "docFile": a["docFile"]}
            for a in pending
        ],
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
    print(f"[funnel] 情报 {funnel['intel']} → 线索 {funnel['leads']} → 选题 {funnel['picks']} "
          f"→ 成稿 {funnel['drafted']} → 自检通过 {funnel['passed']}（淘汰 {funnel['rejected']}，待检 {funnel['pending']}）"
          f" → 可发布 {funnel['publishable']}")
    for t, v in pools.items():
        flag = "OK" if v["done"] else "缺"
        print(f"  [{flag}] {t} {v['available']}/{v['target']} 篇"
              f"（成稿 {v['totalExisted']}，淘汰 {v['rejected']}，待检 {v['pending']}）")
        for a in v["items"]:
            print(f"        {a['formShort']:<3} {a['words']:>4}字 {a['imageCount']}图 {a['score']:>5.1f}分  {a['title'][:24]}")
    if rejected:
        print("  [淘汰]")
        for a in rejected:
            print(f"        {a['formLabel']:<6} {a['score']:>5.1f}分  {a['title'][:30]}")
    if status != "ready":
        sys.exit(2)


if __name__ == "__main__":
    main()
