#!/usr/bin/env python3
"""把 data/inbox/*.json 合并进 data/items.json。

用法:
    python3 scripts/ingest.py            # 合并并归档已处理 inbox 文件
    python3 scripts/ingest.py --dry-run  # 只检查不写入

输入文件格式: JSON 数组，或 {"items": [...]}。
去重键: 规范化 URL + 规范化标题（同一聚合页不同条目不能误合并）。
来源池与线索产出规则见 data/sources.md，字段规范见 data/schema.json。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "inbox"
ARCHIVE = INBOX / "archive"
ITEMS = ROOT / "data" / "items.json"
META = ROOT / "data" / "meta.json"
MAX_ITEMS = 600

TYPES = {"hotspot", "news", "discussion", "resource", "demand", "idea", "other"}
REGIONS = {"国内", "海外"}
STATUS = {"已核实", "部分核实", "待核实", "未核实"}


def norm_url(url):
    if not isinstance(url, str) or not url.strip():
        return ""
    u = url.strip().split("#")[0].split("?")[0].lower()
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u.rstrip("/")


def make_id(item):
    # 同一篇早报/聚合页常包含多条不同信息，必须用 URL + 标题去重
    key = norm_url(item.get("url")) + "\n" + re.sub(r"\s+", "", str(item.get("title") or ""))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clean(item):
    if not isinstance(item, dict):
        return None
    if not item.get("title") or not item.get("url"):
        return None
    item = dict(item)
    item["type"] = item.get("type") if item.get("type") in TYPES else "other"
    item["region"] = item.get("region") if item.get("region") in REGIONS else "海外"
    item["platform"] = str(item.get("platform") or "未知来源")
    item["summary"] = str(item.get("summary") or "")
    item["collectedAt"] = item.get("collectedAt") or now_iso()
    item["id"] = make_id(item)
    item.setdefault("subtype", "")
    item.setdefault("publishedAt", None)
    item.setdefault("image", None)
    item.setdefault("tags", [])
    item.setdefault("needs", [])
    item.setdefault("citations", [])
    item.setdefault("leads", [])
    if not isinstance(item.get("heat"), dict):
        item["heat"] = {"stage": "未知", "signals": {}}
    else:
        item["heat"].setdefault("stage", "未知")
        item["heat"].setdefault("signals", {})
    v = item.get("verification") if isinstance(item.get("verification"), dict) else {}
    v["status"] = v.get("status") if v.get("status") in STATUS else "未核实"
    v.setdefault("method", "")
    v.setdefault("verifiedAt", None)
    v.setdefault("notes", "")
    item["verification"] = v
    e = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
    e.setdefault("editor", "")
    e.setdefault("community", "")
    e.setdefault("sentiment", "未知")
    e.setdefault("source", "")
    item["evaluation"] = e
    if not isinstance(item.get("tags"), list):
        item["tags"] = []
    if not isinstance(item.get("needs"), list):
        item["needs"] = []
    if not isinstance(item.get("citations"), list):
        item["citations"] = []
    if not isinstance(item.get("leads"), list):
        item["leads"] = []
    clean_leads = []
    for lead in item["leads"]:
        if not isinstance(lead, dict) or not lead.get("headline"):
            continue
        target = lead.get("target")
        if target not in {"公众号", "今日头条"}:
            continue
        outline = lead.get("outline")
        outline = [str(x) for x in outline] if isinstance(outline, list) else []
        clean_leads.append({
            "target": target,
            "headline": str(lead.get("headline") or ""),
            "angle": str(lead.get("angle") or ""),
            "outline": outline[:6],
            "audience": str(lead.get("audience") or ""),
            "timeliness": str(lead.get("timeliness") or "长期"),
            "priority": lead.get("priority") if lead.get("priority") in {"高", "中", "低"} else "中",
            "risk": str(lead.get("risk") or "无"),
            "basis": str(lead.get("basis") or ""),
        })
    item["leads"] = clean_leads
    return item


def load_inbox():
    files = sorted(INBOX.glob("*.json"))
    added = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[warn] 跳过无法解析的 {f.name}: {exc}", file=sys.stderr)
            continue
        rows = data.get("items", []) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            print(f"[warn] 跳过结构错误的 {f.name}", file=sys.stderr)
            continue
        n = 0
        for row in rows:
            c = clean(row)
            if c:
                added.append(c)
                n += 1
        print(f"[read] {f.name}: {n} 条")
    return added, files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    incoming, files = load_inbox()
    existing = []
    if ITEMS.exists():
        try:
            existing = json.loads(ITEMS.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                existing = existing.get("items", [])
        except Exception as exc:
            print(f"[warn] 现有 items.json 解析失败，将重建: {exc}", file=sys.stderr)
            existing = []

    merged = {}
    for it in existing + incoming:
        merged[it["id"]] = it  # 后写入的覆盖旧的，保留最新采集信息

    rows = sorted(
        merged.values(),
        key=lambda x: (str(x.get("collectedAt") or ""), str(x.get("publishedAt") or "")),
        reverse=True,
    )[:MAX_ITEMS]

    counts = {}
    by_target = {"公众号": 0, "今日头条": 0}
    leads_total = 0
    for it in rows:
        counts[it["type"]] = counts.get(it["type"], 0) + 1
        for lead in it.get("leads", []):
            leads_total += 1
            if lead.get("target") in by_target:
                by_target[lead["target"]] += 1

    meta = {
        "updatedAt": now_iso(),
        "total": len(rows),
        "byType": counts,
        "sources": sorted({it["platform"] for it in rows}),
        "leadsTotal": leads_total,
        "byTarget": by_target,
        "lastBatch": len(incoming),
    }

    if args.dry_run:
        print(f"[dry-run] 合并后 {len(rows)} 条，新增 {len(incoming)} 条")
        return

    ITEMS.write_text(
        json.dumps({"version": 2, "items": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 同时生成内联脚本，保证 file:// 本地预览也能读到数据
    payload = json.dumps({"version": 2, "items": rows}, ensure_ascii=False)
    embed = ROOT / "data" / "embed.js"
    embed.write_text(
        "window.__ITEMS__=" + payload + ";\n"
        + "window.__META__=" + json.dumps(meta, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in files:
        target = ARCHIVE / f"{stamp}-{f.name}"
        shutil.move(str(f), str(target))
    print(f"[done] items.json 共 {len(rows)} 条；本次并入 {len(incoming)} 条；{len(files)} 个 inbox 文件已归档")


if __name__ == "__main__":
    main()
