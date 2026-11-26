#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成品稿达标自检：把 data/ready/*.json 的每篇稿子，对照 data/viral/benchmark.json 的真实爆款基准逐项打分。

五维（满分 100）：
  字数 25 / 配图 25 / 结构 20 / 标题 15 / 开头钩子 15

输出：
  data/audit.json        逐篇明细 + 汇总
  data/audit-embed.js    前端内联数据（window.__AUDIT__）

铁律：只做「自家稿 vs 爆款中位数」的量化对比，不编造爆款数据；
      基准样本不足的形态，结论要标注「样本少，仅供参考」。
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READY_DIR = os.path.join(ROOT, "data", "ready")
BENCH = os.path.join(ROOT, "data", "viral", "benchmark.json")
VIRAL = os.path.join(ROOT, "data", "viral", "items.json")
PICKS = os.path.join(ROOT, "data", "picks.json")
OUT_JSON = os.path.join(ROOT, "data", "audit.json")
OUT_EMBED = os.path.join(ROOT, "data", "audit-embed.js")

FORM_LABEL = {
    "gzh-article": "微信公众号 · 文章",
    "gzh-poster": "微信公众号 · 贴图",
    "tt-article": "今日头条 · 文章",
    "tt-micro": "今日头条 · 微头条",
}

CJK = re.compile(r"[\u4e00-\u9fff]")
NUM = re.compile(r"\d+(?:\.\d+)?")


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0).isoformat()


def text_of(blocks) -> str:
    parts = []
    for b in blocks or []:
        t = b.get("type")
        if t in ("para", "h2", "h3", "quote"):
            parts.append(str(b.get("text") or ""))
        elif t == "list":
            parts.extend(str(x) for x in (b.get("items") or []))
    return "".join(parts)


def metrics(piece: dict) -> dict:
    blocks = piece.get("blocks") or []
    body = text_of(blocks)
    cjk = len(CJK.findall(body))
    paras = [str(b.get("text") or "") for b in blocks if b.get("type") == "para"]
    h2 = [str(b.get("text") or "") for b in blocks if b.get("type") in ("h2", "h3")]
    lists = [b for b in blocks if b.get("type") == "list"]
    quotes = [b for b in blocks if b.get("type") == "quote"]
    images = piece.get("images") or []
    first = paras[0] if paras else ""
    title = str(piece.get("title") or "")
    # 首段是否含具体锚点（数字/时间/机构/引号原话），这是爆款开头的共性
    anchor = bool(NUM.search(first)) or any(
        k in first for k in ("月", "日", "年", "%", "元", "万", "GitHub", "README", "榜")
    )
    return {
        "wordCount": cjk,
        "images": len(images),
        "subheads": len(h2),
        "paragraphs": len(paras),
        "lists": len(lists),
        "quotes": len(quotes),
        "numbers": len(NUM.findall(body)),
        "firstParaLen": len(CJK.findall(first)),
        "firstParaAnchor": anchor,
        "titleLen": len(CJK.findall(title)),
        "titleHasNumber": bool(NUM.search(title)),
        "titleHasQuestion": ("？" in title or "?" in title),
        "avgParaLen": round(cjk / max(1, len(paras))),
        "imageCaptions": len([i for i in images if str(i.get("caption") or "").strip()]),
    }


def ratio_score(value: float, target: float, weight: float, low: float = 0.9, high: float = 1.4) -> tuple:
    """落在 [low, high] 倍区间拿满分；不足按比例给分；过长轻微扣分（信息冗余）。"""
    if target <= 0:
        return weight * 0.6, "基准缺失"
    r = value / target
    if r < low:
        s = weight * (r / low)
        return round(s, 1), f"为基准的 {r:.0%}"
    if r > high:
        s = max(weight * 0.72, weight - (r - high) * weight * 0.5)
        return round(s, 1), f"为基准的 {r:.0%}（偏长）"
    return weight, f"为基准的 {r:.0%}"


def check_structure(form: str, m: dict, viral: dict) -> tuple:
    """结构分：按形态判断该有的骨架是否齐。"""
    notes = []
    score = 0.0
    if form in ("gzh-article", "tt-article"):
        # 长文：小标题分节 + 段落数 + 至少一个列表或引用
        if m["subheads"] >= 3:
            score += 8
            notes.append(f"小标题 {m['subheads']} 个，分节清晰")
        elif m["subheads"] >= 2:
            score += 5
            notes.append(f"小标题仅 {m['subheads']} 个，分节偏弱")
        else:
            notes.append("缺少小标题，长文没有分节")
        if m["paragraphs"] >= 8:
            score += 7
            notes.append(f"段落 {m['paragraphs']} 段，节奏可读")
        elif m["paragraphs"] >= 5:
            score += 4
            notes.append(f"段落仅 {m['paragraphs']} 段，偏少")
        else:
            notes.append("段落过少，读起来像一大块")
        if m["lists"] or m["quotes"]:
            score += 5
            notes.append("有列表/引用块，信息可扫读")
        else:
            notes.append("没有列表或引用块，缺少可扫读的结构锚点")
    elif form == "gzh-poster":
        # 贴图：字少图多、每段短、靠图承载信息
        if m["images"] >= 6:
            score += 10
            notes.append(f"配图 {m['images']} 张，符合贴图多图形态")
        elif m["images"] >= 3:
            score += 5
            notes.append(f"配图 {m['images']} 张，仍少于爆款")
        else:
            notes.append("配图过少，单图撑不起贴图形态")
        if 3 <= m["paragraphs"] <= 8:
            score += 5
            notes.append(f"段落 {m['paragraphs']} 段，节奏合适")
        else:
            notes.append(f"段落 {m['paragraphs']} 段，与贴图短段节奏不符")
        if m["avgParaLen"] <= 220:
            score += 5
            notes.append(f"平均每段 {m['avgParaLen']} 字，适合截图阅读")
        else:
            notes.append(f"平均每段 {m['avgParaLen']} 字，太长不适合贴图")
    else:  # tt-micro
        if m["paragraphs"] >= 3:
            score += 8
            notes.append(f"段落 {m['paragraphs']} 段，符合短讯节奏")
        else:
            notes.append("段落过少")
        if m["firstParaLen"] <= 90:
            score += 7
            notes.append(f"首段 {m['firstParaLen']} 字，开口干脆")
        elif m["firstParaLen"] <= 140:
            score += 4
            notes.append(f"首段 {m['firstParaLen']} 字，略长")
        else:
            notes.append(f"首段 {m['firstParaLen']} 字，铺垫太多")
        if m["images"] >= 1:
            score += 5
            notes.append("有配图")
        else:
            notes.append("无配图")
    return round(min(20, score), 1), notes


def check_title(form: str, m: dict, title: str) -> tuple:
    score = 0.0
    notes = []
    if 12 <= m["titleLen"] <= 32:
        score += 6
        notes.append(f"标题 {m['titleLen']} 字，长度合适")
    elif 8 <= m["titleLen"] <= 40:
        score += 3
        notes.append(f"标题 {m['titleLen']} 字，边界可接受")
    else:
        notes.append(f"标题 {m['titleLen']} 字，偏离可读区间")
    if m["titleHasQuestion"]:
        score += 5
        notes.append("标题带疑问，制造信息缺口")
    elif m["titleHasNumber"]:
        score += 5
        notes.append("标题带具体数字，有确定感")
    else:
        notes.append("标题既无数字也无疑问，缺钩子")
    # 反差/转折词
    if any(k in title for k in ("但", "却", "其实", "原来", "前提", "真相", "别急", "先", "？")):
        score += 4
        notes.append("标题有转折/悬念词")
    else:
        notes.append("标题缺少转折或悬念词")
    return round(min(15, score), 1), notes


def check_hook(m: dict, first: str) -> tuple:
    score = 0.0
    notes = []
    if m["firstParaLen"] <= 120:
        score += 6
        notes.append(f"首段 {m['firstParaLen']} 字，开场利落")
    elif m["firstParaLen"] <= 180:
        score += 4
        notes.append(f"首段 {m['firstParaLen']} 字，稍长但可接受")
    else:
        notes.append(f"首段 {m['firstParaLen']} 字，开头太拖")
    if m["firstParaAnchor"]:
        score += 5
        notes.append("首段有具体事实/数字锚点")
    else:
        notes.append("首段缺具体锚点，偏议论")
    if any(k in first for k in ("这两天", "今天", "刚刚", "最近", "上周", "昨天")):
        score += 4
        notes.append("首段有时间锚，贴近热点")
    else:
        notes.append("首段无时间锚，时效感弱")
    return round(min(15, score), 1), notes


def grade_of(score: float) -> str:
    if score >= 85:
        return "达标"
    if score >= 70:
        return "接近"
    return "不达标"


def build_gaps(form: str, m: dict, viral: dict, checks: dict) -> list:
    gaps = []
    wc_t = viral.get("wordCount") or 0
    img_t = viral.get("images") or 0
    if wc_t and m["wordCount"] < wc_t * 0.9:
        gaps.append(
            {
                "dim": "字数",
                "gap": f"{m['wordCount']} 字 / 基准 {wc_t:.0f} 字，差 {wc_t - m['wordCount']:.0f} 字",
                "fix": f"补到 {int(wc_t * 0.95)}–{int(wc_t * 1.25)} 字：优先加具体案例、逐条解释、反方观点与回应",
            }
        )
    if img_t and m["images"] < img_t * 0.7:
        gaps.append(
            {
                "dim": "配图",
                "gap": f"{m['images']} 张 / 基准 {img_t:.0f} 张",
                "fix": f"补到 {int(img_t)} 张左右：一张封面 + 每 2–3 段一张场景图，图间要有信息递进而非重复",
            }
        )
    for key in ("structure", "title", "hook"):
        if checks[key]["score"] < checks[key]["weight"] * 0.7:
            detail = "；".join([n for n in checks[key]["notes"] if n.startswith(("缺少", "没有", "无", "首段", "段落", "配图过少", "标题既"))]) or "得分偏低"
            gaps.append({"dim": checks[key]["label"], "gap": detail, "fix": checks[key]["fix"]})
    return gaps


def coverage_report(docs):
    """选题覆盖：今日选题池（公众号 6 + 头条 8）里每个选题都必须有对应成品稿，缺一条就是出稿漏了。"""
    try:
        picks = json.load(open(PICKS, encoding="utf-8"))
    except Exception as exc:
        print(f"[warn] 读不到 picks.json：{exc}")
        return None
    have = {d.get("sourceItemId") for d in docs if d.get("sourceItemId")}
    rows = []
    total = covered = 0
    seen_all = set()   # 跨去向去重：同一事件出公众号版和头条版，只算一个选题
    for target, group in (picks.get("groups") or {}).items():
        t_total = t_cov = 0
        missing = []
        seen = set()
        for pick in group:
            iid = pick.get("itemId")
            if not iid or iid in seen:
                continue
            seen.add(iid)
            t_total += 1
            if iid in have:
                t_cov += 1
            else:
                missing.append({
                    "itemId": iid,
                    "rank": pick.get("rank"),
                    "score": pick.get("score"),
                    "headline": (pick.get("lead") or {}).get("headline") or pick.get("sourceTitle"),
                })
            if iid not in seen_all:
                seen_all.add(iid)
                total += 1
                if iid in have:
                    covered += 1
        rows.append({"target": target, "total": t_total, "covered": t_cov, "missing": missing})
    return {
        "date": picks.get("date"),
        "total": total,
        "covered": covered,
        "ok": total > 0 and covered == total,
        "byTarget": rows,
    }


def main() -> None:
    bench = json.load(open(BENCH, encoding="utf-8")) if os.path.exists(BENCH) else {"rows": []}
    bench_by_form = {r["form"]: r for r in bench.get("rows", [])}
    viral_items = []
    if os.path.exists(VIRAL):
        viral_items = json.load(open(VIRAL, encoding="utf-8")).get("items", [])

    pieces_out = []
    docs = []
    for path in sorted(glob.glob(os.path.join(READY_DIR, "*.json"))):
        if path.endswith("index.json"):
            continue
        doc = json.load(open(path, encoding="utf-8"))
        docs.append(doc)
        for pc in doc.get("pieces", []):
            form = pc.get("id")
            if form not in FORM_LABEL:
                continue
            row = bench_by_form.get(form, {})
            viral = row.get("viral", {}) or {}
            sample = row.get("viralSample", 0)
            m = metrics(pc)
            first = next((str(b.get("text") or "") for b in pc.get("blocks", []) if b.get("type") == "para"), "")

            wc_score, wc_note = ratio_score(m["wordCount"], viral.get("wordCount") or 0, 25)
            img_score, img_note = ratio_score(m["images"], viral.get("images") or 0, 25, low=0.7, high=2.5)
            st_score, st_notes = check_structure(form, m, viral)
            ti_score, ti_notes = check_title(form, m, str(pc.get("title") or ""))
            hk_score, hk_notes = check_hook(m, first)

            checks = {
                "wordCount": {
                    "label": "字数",
                    "score": wc_score,
                    "weight": 25,
                    "target": viral.get("wordCount"),
                    "value": m["wordCount"],
                    "notes": [wc_note],
                    "fix": "补具体案例与逐条解释，不要靠形容词堆字数",
                },
                "images": {
                    "label": "配图",
                    "score": img_score,
                    "weight": 25,
                    "target": viral.get("images"),
                    "value": m["images"],
                    "notes": [img_note],
                    "fix": "封面定调 + 每 2–3 段一张场景图，图要有信息增量",
                },
                "structure": {
                    "label": "结构",
                    "score": st_score,
                    "weight": 20,
                    "target": viral.get("subheads"),
                    "value": m["subheads"],
                    "notes": st_notes,
                    "fix": "长文按 3–5 个小标题分节，每节一个结论；贴图控制短段、多图",
                },
                "title": {
                    "label": "标题",
                    "score": ti_score,
                    "weight": 15,
                    "target": None,
                    "value": pc.get("title"),
                    "notes": ti_notes,
                    "fix": "标题 12–30 字，带数字或疑问，再加一个转折词",
                },
                "hook": {
                    "label": "开头钩子",
                    "score": hk_score,
                    "weight": 15,
                    "target": None,
                    "value": m["firstParaLen"],
                    "notes": hk_notes,
                    "fix": "首段 120 字内给出时间锚 + 具体事实，别先讲道理",
                },
            }
            total = round(sum(c["score"] for c in checks.values()), 1)
            gaps = build_gaps(form, m, viral, checks)
            pieces_out.append(
                {
                    "file": os.path.basename(path),
                    "date": doc.get("date"),
                    "form": form,
                    "formLabel": FORM_LABEL[form],
                    "target": pc.get("target"),
                    "title": pc.get("title"),
                    "score": total,
                    "grade": grade_of(total),
                    "viralSample": sample,
                    "benchmarkReliable": sample >= 5,
                    "bench": {
                        "wordCount": viral.get("wordCount"),
                        "images": viral.get("images"),
                        "subheads": viral.get("subheads"),
                    },
                    "metrics": m,
                    "checks": checks,
                    "gaps": gaps,
                }
            )

    # 汇总
    by_form = {}
    for p in pieces_out:
        d = by_form.setdefault(p["form"], {"form": p["form"], "formLabel": p["formLabel"], "count": 0, "avgScore": 0, "min": 100, "max": 0})
        d["count"] += 1
        d["avgScore"] += p["score"]
        d["min"] = min(d["min"], p["score"])
        d["max"] = max(d["max"], p["score"])
    for d in by_form.values():
        d["avgScore"] = round(d["avgScore"] / d["count"], 1)
        d["grade"] = grade_of(d["avgScore"])

    grades = {"达标": 0, "接近": 0, "不达标": 0}
    for p in pieces_out:
        grades[p["grade"]] += 1

    # 一选题一篇：同一个 sourceItemId 出了多种形态 = 重复，属于结构性问题
    dup_rows = []
    by_story = {}
    for p in pieces_out:
        doc = next((d for d in docs if d.get("sourceItemId") and p["file"] == f"{d.get('date')}-{d.get('slug')}.json"), None)
        # 按「日期 + 选题」分组：历史批次不再追究，只看当天的重复
        key = f"{p.get('date')}::{(doc or {}).get('sourceItemId') or p['file']}"
        by_story.setdefault(key, []).append(p)
    today_iso = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    for key, group in by_story.items():
        if len(group) > 1 and key and key.startswith(today_iso):
            for extra in group[1:]:
                dup_rows.append({"itemId": key, "title": extra["title"], "formLabel": extra["formLabel"],
                                 "score": extra["score"], "file": extra["file"]})
    if dup_rows:
        print(f"[dedupe] {len(dup_rows)} 篇属于同一选题的重复形态（一选题只应出一篇）：" +
              "；".join(f"《{str(d['title'])[:20]}》{d['formLabel']}" for d in dup_rows[:6]))

    # 全文底稿覆盖：写稿该读原文全文，而不是摘要。这里只统计、不扣分（2026-11-26 新增）
    ft_have, ft_missing, ft_total = 0, [], 0
    for p in pieces_out:
        if not str(p.get("file") or "").startswith(today_iso):
            continue  # 只看当天的稿，历史批次不追溯
        ft_total += 1
        doc = next((d for d in docs if p["file"] == f"{d.get('date')}-{d.get('slug')}.json"), None) or {}
        date = doc.get("date") or (p.get("file") or "")[:10]
        slug = doc.get("slug") or (p.get("file") or "")[11:-5]
        md = Path(ROOT) / "data" / "fulltext" / str(date) / f"{slug}.md"
        if md.exists() and md.stat().st_size > 400:
            ft_have += 1
        else:
            ft_missing.append(p["file"])
    out_ft = {"have": ft_have, "total": ft_total, "missing": ft_missing}
    if ft_total:
        print(f"[fulltext] 原文全文底稿 {ft_have}/{ft_total} 篇" +
              ("" if not ft_missing else "；缺 " + "、".join(x[11:-5] for x in ft_missing[:5])))

    cov = coverage_report(docs)
    if cov:
        missing_rows = [m for r in cov["byTarget"] for m in r["missing"]]
        print(f"[coverage] 今日选题池 {cov['covered']}/{cov['total']} 个事件有成品稿" +
              ("".join([f"；缺 {m['itemId']}（{(m['headline'] or '')[:24]}）" for m in missing_rows]) if missing_rows else "，无遗漏"))

    out = {
        "updatedAt": now_iso(),
        "coverage": cov,
        "fulltext": out_ft,
        "duplicates": dup_rows,
        "benchmarkUpdatedAt": bench.get("updatedAt"),
        "total": len(pieces_out),
        "avgScore": round(statistics.mean([p["score"] for p in pieces_out]), 1) if pieces_out else 0,
        "grades": grades,
        "byForm": sorted(by_form.values(), key=lambda x: x["form"]),
        "pieces": sorted(pieces_out, key=lambda x: (x["form"], x["score"])),
        "viralTotal": len(viral_items),
    }
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(OUT_EMBED, "w", encoding="utf-8") as f:
        f.write("window.__AUDIT__=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")

    print(f"[audit] {out['total']} 篇，均分 {out['avgScore']}，达标 {grades['达标']} / 接近 {grades['接近']} / 不达标 {grades['不达标']}")
    for p in out["pieces"]:
        print(f"  {p['score']:5.1f} {p['grade']:3} {p['formLabel']:14} 字{p['metrics']['wordCount']:5} 图{p['metrics']['images']:2} | {str(p['title'])[:30]}")
        for g in p["gaps"]:
            print(f"        · {g['dim']}：{g['gap']}")

    if "--strict" in sys.argv:
        problems = []
        if not cov or not cov["ok"]:
            problems.append("选题池存在没有成品稿的条目（出稿漏了）")
        if dup_rows:
            problems.append(f"{len(dup_rows)} 篇与同选题重复（一选题只能出一篇、一个平台、一种形态）")
        # 只看当天：历史稿分数低不该一直卡住今天的验收
        today_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
        today_pieces = [p for p in out["pieces"] if p.get("date") == today_str]
        if today_pieces:
            passed = [p for p in today_pieces if p["score"] >= 85]
            rate = len(passed) / len(today_pieces)
            if rate < 0.6:
                problems.append(f"今日 {len(today_pieces)} 篇里只有 {len(passed)} 篇达标（{rate:.0%}），低于 60% 说明出稿质量崩了")
        else:
            problems.append("今天还没有成品稿")
        if problems:
            print("[strict] 未通过：" + "；".join(problems))
            sys.exit(1)
        print(f"[strict] 通过：选题全覆盖，今日 {len(today_pieces)} 篇中 {len(passed)} 篇达标（未达标的进淘汰池，不发布）")


if __name__ == "__main__":
    main()
