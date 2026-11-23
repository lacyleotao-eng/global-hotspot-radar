#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以「今天真正出的稿」为准生成今日选题池（公众号 6 / 今日头条 8）。

为什么要这个脚本：
    rank_leads.py 是按线索打分「选未来要做的选题」；到了发布环节，真正能发的是已经出稿、
   已经过自检的那几篇。两者混用会出现「选题池里有稿没做、发布池里有稿没选题」的错位。
   所以出稿之后，用本脚本把选题池对齐到实际产出：一个成品稿 = 一条今日选题，
   这样「出稿覆盖」天然 100%，发布池的每一篇都能追到选题。

用法:
    python3 scripts/build_picks_from_ready.py            # 今天的稿
    python3 scripts/build_picks_from_ready.py --date 2026-11-22
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "data" / "ready"
ITEMS = ROOT / "data" / "items.json"
AUDIT = ROOT / "data" / "audit.json"
OUT = ROOT / "data" / "picks.json"
EMBED = ROOT / "data" / "picks-embed.js"

SH = timezone(timedelta(hours=8))
TARGETS = {"公众号": 6, "今日头条": 8}
# 形态配额：公众号 3 文章 + 3 贴图；头条 4 文章 + 4 微头条
QUOTA = {"公众号": [("gzh-article", 3), ("gzh-poster", 3)],
         "今日头条": [("tt-article", 4), ("tt-micro", 4)]}
# 同一个选题要产出多个形态时，保留哪个：长文优先（信息量更大），再按自检分
FORM_ORDER = {"gzh-article": 0, "gzh-poster": 1, "tt-article": 0, "tt-micro": 1}
FORM_LABEL = {"gzh-article": "公众号文章", "gzh-poster": "公众号贴图",
              "tt-article": "头条文章", "tt-micro": "微头条"}


def now_local() -> str:
    return datetime.now(SH).replace(microsecond=0).isoformat()


def load_audit() -> dict:
    try:
        a = json.loads(AUDIT.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {f"{p.get('file')}::{p.get('form')}": p for p in a.get("pieces") or []}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(SH).strftime("%Y-%m-%d"))
    date = ap.parse_args().date

    items = {i.get("id"): i for i in json.loads(ITEMS.read_text(encoding="utf-8")).get("items", [])}
    audit = load_audit()

    rows = {"公众号": [], "今日头条": []}
    for path in sorted(READY.glob(f"{date}-*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("date") != date:
            continue
        it = items.get(d.get("sourceItemId")) or {}
        leads = it.get("leads") or []
        for piece in d.get("pieces") or []:
            fid = piece.get("id")
            target = "公众号" if str(fid).startswith("gzh") else "今日头条"
            # 配图没就绪的稿不进今日选题：宁可少一条，也不把自制信息卡混进发布池
            imgs = piece.get("images") or []
            if not imgs or any("自制信息卡" in str(im.get("caption") or "") for im in imgs):
                print(f"[skip] 配图未就绪：{path.name} {fid}")
                continue
            rec = audit.get(f"{path.name}::{fid}") or {}
            # 优先用与原选题匹配的 lead；没有就按稿件自身重建一份可读的 brief
            lead = next((l for l in leads if l.get("target") == target), None)
            if not lead and leads:
                lead = leads[0]
            if not lead:
                lead = {
                    "target": target,
                    "headline": piece.get("title"),
                    "angle": piece.get("digest") or "",
                    "outline": [b.get("text") for b in piece.get("blocks") or [] if b.get("type") == "h2"][:6],
                    "audience": "关注该话题的普通读者",
                    "timeliness": "当日",
                    "priority": "高" if target == "今日头条" else "中",
                    "risk": "按来源报道口径写，不推测未公布信息",
                    "basis": (it.get("verification") or {}).get("method") or d.get("verificationNote") or "",
                }
            # 选题卡上要看到的是「这篇稿的标题」，不是原始新闻标题；角度用导语
            lead = dict(lead)
            lead["headline"] = piece.get("title") or lead.get("headline")
            lead["angle"] = piece.get("digest") or lead.get("angle") or ""
            lead["outline"] = [b.get("text") for b in piece.get("blocks") or [] if b.get("type") == "h2"][:6] or lead.get("outline") or []
            lead["basis"] = lead.get("basis") or d.get("verificationNote") or ""
            rows[target].append({
                "itemId": d.get("sourceItemId"),
                "target": target,
                "pieceId": fid,
                "form": FORM_LABEL.get(fid, fid),
                "rank": 0,
                "score": rec.get("score"),
                "grade": rec.get("grade"),
                "sourceTitle": d.get("sourceTitle") or it.get("title"),
                "platform": it.get("platform") or d.get("sourceUrl") or "",
                "url": it.get("url") or d.get("sourceUrl") or "",
                "region": it.get("region") or "国内",
                "verification": d.get("verification") or (it.get("verification") or {}).get("status") or "未核实",
                "heatStage": (it.get("heat") or {}).get("stage") or "未知",
                "lead": lead,
                "breakdown": [],
                "docFile": path.name,
            })

    # ---- 一条情报只能出一篇稿 ----
    # 同一个 sourceItemId 出了多种形态（文章 + 贴图 + 微头条…）时，只留一篇，
    # 其余的记进 duplicates，由页面显示"因重复被合并"。发布人拿到的 14 篇必须是 14 件事。
    by_story: dict[str, list[dict]] = {}
    for target in rows:
        for r in rows[target]:
            by_story.setdefault(r["itemId"] or r["docFile"], []).append(r)

    best_of: dict[str, dict] = {}
    duplicates: list[dict] = []
    for story, candidates in by_story.items():
        candidates.sort(key=lambda r: (FORM_ORDER.get(r["pieceId"], 9), -(r["score"] or 0)))
        best_of[story] = candidates[0]
        for dup in candidates[1:]:
            duplicates.append({
                "itemId": story,
                "keptPiece": candidates[0]["pieceId"],
                "pieceId": dup["pieceId"],
                "form": dup["form"],
                "title": dup["lead"].get("headline"),
                "score": dup["score"],
                "reason": "同一选题已有一篇，不重复出稿",
            })

    # ---- 按形态配额挑，每个选题只用一次 ----
    groups: dict[str, list[dict]] = {}
    caps: dict[str, int] = {}
    used: set[str] = set()
    for target, cap in TARGETS.items():
        quota = QUOTA[target]
        pool = [r for r in best_of.values() if r["target"] == target]
        chosen: list[dict] = []
        for fid, limit in quota:
            bucket = sorted([r for r in pool if r["pieceId"] == fid and r["itemId"] not in used],
                            key=lambda r: -(r["score"] or 0))
            for r in bucket[:limit]:
                used.add(r["itemId"])
                chosen.append(r)
        if len(chosen) < cap:
            rest = sorted([r for r in pool if r["itemId"] not in used], key=lambda r: -(r["score"] or 0))
            for r in rest[: cap - len(chosen)]:
                used.add(r["itemId"])
                chosen.append(r)
        chosen.sort(key=lambda r: (FORM_ORDER.get(r["pieceId"], 9), -(r["score"] or 0)))
        for i, r in enumerate(chosen, 1):
            r["rank"] = i
            r["breakdown"] = []
        groups[target] = chosen
        caps[target] = cap

    out = {
        "version": 2,
        "date": date,
        "generatedAt": now_local(),
        "source": "ready",  # 以实际成品稿为准，不是线索预测
        "totalScored": sum(len(i.get("leads") or []) for i in items.values()),
        "topPerTarget": caps,
        "weights": {},
        "groups": groups,
        "duplicates": duplicates,
        "rule": "一条情报只出一篇稿：同一选题不跨形态、不跨平台重复",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    EMBED.write_text("window.__PICKS__=" + json.dumps(out, ensure_ascii=False) + ";\n", encoding="utf-8")

    print(f"[picks] {date} 以成品稿为准生成选题池（一选题一篇）")
    if duplicates:
        print(f"[dedupe] 合并掉 {len(duplicates)} 篇重复稿：")
        for d in duplicates:
            print(f"  - {d['form']}《{str(d['title'])[:28]}》与 {d['keptPiece']} 同源")
    for target, group in groups.items():
        print(f"[{target} {len(group)}/{caps[target]}]")
        for r in group:
            print(f"  {r['rank']}. {r['score'] or 0:5.1f} {r['form']:<5} {str(r['lead'].get('headline'))[:30]}")


if __name__ == "__main__":
    main()
