#!/usr/bin/env python3
"""把 data/picks.json 的 TOP 选题转成可编辑的成稿草稿（Markdown），存入 drafts/。

只产出草稿与待发布队列清单，不调用任何发布脚本、不登录任何平台、不生成或下载图片。
草稿是「机器初稿骨架」——事实取自线索的 basis/outline，发布前必须由人核实并改写。

用法:
    python3 scripts/make_drafts.py
"""
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICKS = ROOT / "data" / "picks.json"
ITEMS = ROOT / "data" / "items.json"
DRAFTS = ROOT / "drafts"
QUEUE = DRAFTS / "queue.json"


def now_local():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def slug(text):
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", str(text or "")).strip("-")
    return (s[:24] or "untitled")


def guess_city(item):
    tags = " ".join(item.get("tags") or [])
    cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "南京", "西安", "苏州", "长沙"]
    for c in cities:
        if c in tags or c in item.get("title", ""):
            return c
    return ""


def build_outline_text(lead, item):
    """按提纲把事实串成草稿段落；只搬运已记录事实，不编造数字与引语。"""
    outline = lead.get("outline") or []
    basis = lead.get("basis") or ""
    angle = lead.get("angle") or ""
    blocks = []
    if angle:
        blocks.append(angle)
    for i, point in enumerate(outline):
        para = "【第%d段要点】%s" % (i + 1, point)
        if i == 0 and basis:
            para += "\n依据：" + basis
        blocks.append(para)
    return "\n\n".join(blocks)


def gzh_draft(row, item):
    lead = row["lead"]
    cites = item.get("citations") or []
    cite_lines = "\n".join(
        "- %s（%s）%s" % (c.get("title") or "来源", c.get("publisher") or "", c.get("url") or "")
        for c in cites[:5]
    ) or "- 无独立引用，以原文为准"
    return (
        "---\n"
        "status: 待核实改写\n"
        "target: 公众号\n"
        "score: %d\n"
        "sourceItemId: %s\n"
        "sourceUrl: %s\n"
        "verification: %s\n"
        "risk: %s\n"
        "createdAt: %s\n"
        "---\n\n"
        "# %s\n\n"
        "> 选题角度：%s\n\n"
        "## 导语\n\n%s\n\n"
        "## 正文骨架（按提纲扩写）\n\n%s\n\n"
        "## 核实与引用\n\n"
        "核实状态：%s\n\n核实说明：%s\n\n"
        "风险提示：%s\n\n"
        "引用来源：\n%s\n\n"
        "---\n机器人初稿，仅作骨架；点击发布前须人工核实、改写、替换配图。\n"
    ) % (
        row["score"], row["itemId"], row.get("url") or "", row.get("verification") or "未核实",
        str(lead.get("risk") or "无").replace("\n", " "), now_local(),
        lead.get("headline") or item.get("title", ""),
        lead.get("angle") or "",
        item.get("summary") or lead.get("angle") or "",
        build_outline_text(lead, item),
        row.get("verification") or "未核实",
        (item.get("verification") or {}).get("method") or "未记录",
        lead.get("risk") or "无",
        cite_lines,
    )


def toutiao_draft(row, item):
    lead = row["lead"]
    outline = lead.get("outline") or []
    basis = lead.get("basis") or ""
    angle = lead.get("angle") or ""
    paras = [angle] if angle else []
    for point in outline:
        paras.append(point)
    if basis:
        paras.append("事实依据：" + basis)
    body = "\n\n".join(p for p in paras if p)
    city = guess_city(item)
    return (
        "标题：%s\n"
        "定位：%s\n"
        "封面图：\n"
        "正文：\n"
        "%s\n\n"
        "（发布前必读）核实状态：%s；风险：%s；原文：%s\n"
    ) % (
        lead.get("headline") or item.get("title", ""),
        city,
        body,
        row.get("verification") or "未核实",
        lead.get("risk") or "无",
        row.get("url") or "",
    )


def main():
    if not PICKS.exists():
        print("[error] 未找到 data/picks.json，请先运行 scripts/rank_leads.py", file=sys.stderr)
        sys.exit(1)
    picks = json.loads(PICKS.read_text(encoding="utf-8"))
    items = {it.get("id"): it for it in json.loads(ITEMS.read_text(encoding="utf-8")).get("items", [])}
    day = picks.get("date") or date.today().isoformat()
    outdir = DRAFTS / day
    outdir.mkdir(parents=True, exist_ok=True)

    queue_existing = []
    if QUEUE.exists():
        try:
            loaded = json.loads(QUEUE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                queue_existing = loaded.get("entries", [])
            elif isinstance(loaded, list):
                queue_existing = loaded
        except Exception:
            queue_existing = []

    entries = []
    for target, rows in picks.get("groups", {}).items():
        prefix = "gzh" if target == "公众号" else "tt"
        for row in rows:
            item = items.get(row["itemId"], {})
            name = "%s-%02d-%s.md" % (prefix, row["rank"], slug(row["lead"].get("headline")))
            path = outdir / name
            text = gzh_draft(row, item) if target == "公众号" else toutiao_draft(row, item)
            path.write_text(text, encoding="utf-8")
            entry = {
                "date": day,
                "target": target,
                "rank": row["rank"],
                "score": row["score"],
                "headline": row["lead"].get("headline"),
                "verification": row.get("verification"),
                "risk": row["lead"].get("risk"),
                "sourceUrl": row.get("url"),
                "draftPath": str(path.relative_to(ROOT)),
                "status": "待核实改写",
                "published": False,
            }
            entries.append(entry)
            print("[draft]", entry["draftPath"], row["score"], "分")

    others = [e for e in queue_existing if e.get("date") != day]
    queue = {
        "updatedAt": now_local(),
        "note": "待发布队列。status=已成稿待发布 且 published=false 为可发布候选；此脚本从不代发。",
        "entries": others + entries,
    }
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[done] 今日草稿 %d 篇；队列总计 %d 篇" % (len(entries), len(queue["entries"])))


if __name__ == "__main__":
    main()
