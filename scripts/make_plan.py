#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「今天的候选情报」排成一份可执行的出稿计划（一条情报只出一篇稿）。

为什么需要这个脚本：
    出稿任务被 90 分钟运行上限卡死过好几次。根因不是产能不够，而是每个任务都要
    从 200KB 的 items.json 重新挑题、重新推理，光"想清楚写什么"就吃掉半小时。
    所以把机械部分（筛时间窗、去重、配额、排序、摘事实锚点）固化成脚本，
    智能部分（定标题、写正文）交给出稿任务，任务只读这份 plan。

产物：
    data/plan/YYYY-MM-DD.json   机器可读，出稿任务按 status 续跑
    data/plan/YYYY-MM-DD.md     人/模型可读的一页纸 brief

用法：
    python3 scripts/make_plan.py                 # 今天，窗口 40 小时
    python3 scripts/make_plan.py --date 2026-11-24 --hours 48
    python3 scripts/make_plan.py --keep          # 保留已有 plan 里已完成的 status

配额（与 build_picks_from_ready.py 一致）：
    公众号   文章 3 + 贴图 3
    今日头条 文章 4 + 微头条 4
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
READY = ROOT / "data" / "ready"
PLAN_DIR = ROOT / "data" / "plan"
SH = timezone(timedelta(hours=8))

QUOTA = [("公众号", "gzh-article", 3), ("公众号", "gzh-poster", 3),
         ("今日头条", "tt-article", 4), ("今日头条", "tt-micro", 4)]
FORM_LABEL = {"gzh-article": "公众号文章", "gzh-poster": "公众号贴图",
              "tt-article": "头条文章", "tt-micro": "微头条"}

TIMELINESS = {"当日": 25, "本周": 18, "长期": 8}
HEAT = {"上升": 20, "新出现": 15, "成熟": 12, "平稳": 8}
VERIFY = {"已核实": 20, "部分核实": 12, "待核实": 5, "未核实": 0}
PRIORITY = {"高": 20, "中": 12, "低": 5}
BAD_TITLE = re.compile(r"招聘|抽奖|广告|优惠券|带货|直播预告")


def now() -> datetime:
    return datetime.now(SH)


def parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=SH)
    except Exception:
        return None


def score_lead(lead: dict) -> int:
    return (TIMELINESS.get(lead.get("timeliness"), 8)
            + PRIORITY.get(lead.get("priority"), 5)
            + (10 if lead.get("outline") and len(lead["outline"]) >= 3 else 4))


def item_score(it: dict) -> int:
    v = (it.get("verification") or {}).get("status") or it.get("verification") or ""
    if isinstance(v, dict):
        v = v.get("status") or ""
    heat = ((it.get("heat") or {}).get("trend") or "")
    return VERIFY.get(v, 0) + HEAT.get(heat, 8)


def slugify(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:40] or fallback


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=now().strftime("%Y-%m-%d"))
    ap.add_argument("--hours", type=int, default=40)
    ap.add_argument("--keep", action="store_true", help="保留已有 plan 的 status / slug")
    args = ap.parse_args()

    data = json.loads(ITEMS.read_text(encoding="utf-8"))
    items = data.get("items") or []
    cutoff = now() - timedelta(hours=args.hours)

    # 0. 已经出过稿的情报不再用（同一天自己的 ready 除外，那是本计划的产物）
    seen_ids: set[str] = set()
    if READY.is_dir():
        for p in READY.glob("*.json"):
            if p.name.startswith(args.date):
                continue
            try:
                seen_ids.add(json.loads(p.read_text(encoding="utf-8")).get("sourceItemId") or "")
            except Exception:
                pass
    seen_ids.discard("")

    # 1. 候选：时间窗内的条目；一条情报最多进一次。没有 leads 的条目也进候选（兜底用），
    #    因为 leads 只是"建议角度"，不构成出稿的必要条件。
    cands = []
    for it in items:
        dt = parse_dt(it.get("publishedAt") or it.get("collectedAt") or "")
        if dt and dt < cutoff:
            continue
        if BAD_TITLE.search(it.get("title") or ""):
            continue
        iid = it.get("id") or ""
        if not iid or iid in seen_ids:
            continue
        leads = it.get("leads") or []
        best = max(leads, key=lambda l: score_lead(l)) if leads else {}
        cands.append({"item": it, "leads": leads, "lead": best,
                      "score": score_lead(best) + item_score(it)})
    cands.sort(key=lambda c: -c["score"])

    # 2. 按配额分配：一个 sourceItemId 只用一次，形态配额独立。
    #    先用「lead 明确指向该平台」的条目，不够再用别的条目补（角度取编辑判断）。
    used_item: set[str] = set()
    filled = {f: 0 for _, f, _ in QUOTA}
    events = []

    def pick(leads: list, target: str) -> dict:
        same = [l for l in leads if l.get("target") == target]
        return max(same, key=score_lead) if same else {}

    for target, form, cap in QUOTA:
        need = cap - filled[form]
        ordered = ([c for c in cands if any(l.get("target") == target for l in c["leads"])]
                   + [c for c in cands if not any(l.get("target") == target for l in c["leads"])])
        for c in ordered:
            if need <= 0:
                break
            it = c["item"]
            iid = it.get("id") or ""
            if not iid or iid in used_item:
                continue
            lead = pick(c["leads"], target)
            events.append({
                "slug": slugify(lead.get("headline") or it.get("title") or "", f"e{len(events)+1}-{iid[:6]}"),
                "sourceItemId": iid,
                "sourceTitle": it.get("title") or "",
                "sourceUrl": it.get("url") or "",
                "sourcePlatform": it.get("platform") or "",
                "publishedAt": it.get("publishedAt") or "",
                "region": it.get("region") or "",
                "type": it.get("type") or "",
                "verification": (it.get("verification") or {}).get("status") if isinstance(it.get("verification"), dict) else (it.get("verification") or ""),
                "verificationNote": (it.get("verification") or {}).get("notes") if isinstance(it.get("verification"), dict) else "",
                "summary": it.get("summary") or "",
                "heat": it.get("heat") or {},
                "citations": (it.get("citations") or [])[:4],
                "target": target,
                "form": form,
                "formLabel": FORM_LABEL[form],
                "status": "todo",
                "leadHeadline": lead.get("headline") or "",
                "angle": lead.get("angle") or ((it.get("evaluation") or {}).get("editor") or ""),
                "outline": lead.get("outline") or [],
                "audience": lead.get("audience") or "",
                "risk": lead.get("risk") or "",
                "basis": lead.get("basis") or "",
                "hasLead": bool(lead),
                "score": c["score"],
            })
            used_item.add(iid)
            need -= 1
            filled[form] += 1

    # 3. 已有 plan 里已完成的条目保留 status 与 slug
    out_json = PLAN_DIR / f"{args.date}.json"
    prev = {}
    if args.keep and out_json.exists():
        try:
            prev = {e["sourceItemId"]: e for e in json.loads(out_json.read_text(encoding="utf-8")).get("events") or []}
        except Exception:
            prev = {}
    for e in events:
        p = prev.get(e["sourceItemId"])
        if p:
            e["status"] = p.get("status") or "todo"
            e["slug"] = p.get("slug") or e["slug"]
            if p.get("title"):
                e["title"] = p["title"]

    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    doc = {
        "date": args.date,
        "generatedAt": now().replace(microsecond=0).isoformat(),
        "windowHours": args.hours,
        "rule": "一条情报 = 一篇稿 = 一个平台 = 一种形态；同一 sourceItemId 不得出现第二次",
        "quota": {f: c for _, f, c in QUOTA},
        "events": events,
    }
    out_json.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    # 4. 一页纸 brief
    lines = [f"# {args.date} 出稿计划", "",
             f"配额：{'、'.join(f'{FORM_LABEL[f]} {c}' for _, f, c in QUOTA)}（共 {sum(c for _,_,c in QUOTA)} 篇）",
             "铁律：一条情报只出一篇稿，`images` 一律留空由 rebind 统一绑图。", ""]
    for i, e in enumerate(events, 1):
        lines += [f"## {i}. {e['formLabel']}｜{e['sourceTitle']}",
                  f"- slug：`{e['slug']}`　itemId：`{e['sourceItemId']}`　状态：{e['status']}",
                  f"- 来源：{e['sourcePlatform']}　核实：{e['verification']}",
                  f"- 原文：{e['sourceUrl']}",
                  f"- 事实：{e['summary'][:300]}",
                  f"- 核实缺口：{e['verificationNote'][:160]}",
                  f"- 建议角度：{e['angle']}",
                  f"- 建议提纲：{' / '.join(e['outline'][:5])}",
                  f"- 风险：{e['risk']}", ""]
    (PLAN_DIR / f"{args.date}.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"[plan] {args.date} 共 {len(events)} 篇 -> {out_json}")
    for _, f, c in QUOTA:
        got = sum(1 for e in events if e["form"] == f)
        flag = "OK" if got == c else "缺"
        print(f"  [{flag}] {FORM_LABEL[f]} {got}/{c}")
    if len(events) < sum(c for _, _, c in QUOTA):
        print("  [warn] 候选不足，检查 items.json 最近时间窗是否有新条目或 leads")


if __name__ == "__main__":
    main()
