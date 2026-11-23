#!/usr/bin/env python3
"""对 data/items.json 中的选题线索按「时效/热度/核实/优先级/完整度/来源」打分，
选出公众号与今日头条各自的 TOP N，写入 data/picks.json 与 data/picks-embed.js。

评分是确定性的：同样的输入永远得到同样的分数，便于复核。
风险提示只做扣分，不自动删除；高风险条目仍会出现，但分数靠后并带明显标记。

用法:
    python3 scripts/rank_leads.py              # 公众号 6 条、今日头条 8 条（默认）
    python3 scripts/rank_leads.py --top 5      # 两个去向都取 5 条（临时压测用）

为什么是 6 / 8：
    发布人每天发 1 篇公众号 + 3 篇头条，但需要留出「自检淘汰 + 临时换稿」的余量，
    所以选题池按 6 / 8 备，最终进「今日发布」的只保留自检 ≥85 分的。
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
PICKS = ROOT / "data" / "picks.json"
EMBED = ROOT / "data" / "picks-embed.js"

TIMELINESS = {"当日": 25, "本周": 18, "长期": 8}
HEAT = {"上升": 20, "新出现": 15, "成熟": 12, "平稳": 8}
VERIFY = {"已核实": 20, "部分核实": 12, "待核实": 5, "未核实": 0}
PRIORITY = {"高": 20, "中": 12, "低": 5}

# 每个去向的选题池容量：公众号 6（文章+贴图可混），今日头条 8（文章+微头条可混）
TARGET_TOP = {"公众号": 6, "今日头条": 8}

SEVERE_RISK = ["未获独立验证", "不得使用", "必须写清", "未取得", "未公开", "不指名", "避免写成", "尚无", "未经核实", "不能确认"]
MILD_RISK = ["核对", "注明", "须", "勿", "谨慎", "以原文为准", "避免"]
AUTHORITATIVE = ["官方", "央视", "新华", "部委", "政府", "研究院", "中国地震台网", "工业和信息化部", "中央气象台"]
AGGREGATED = ["经", "整理", "聚合", "榜单", "汇总"]


def now_local():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def day_diff(iso_str):
    """采集日期距今天数，解析失败按 3 天以上处理。"""
    if not iso_str:
        return 9
    try:
        s = str(iso_str).replace("Z", "+00:00")
        d = datetime.fromisoformat(s).date()
    except Exception:
        return 9
    return max(0, (date.today() - d).days)


def risk_penalty(risk):
    text = str(risk or "")
    if not text or text.strip() in {"无", "无明确", "低", "无风险"}:
        return 0, "无风险提示"
    hits = [k for k in SEVERE_RISK if k in text]
    if hits:
        return -6, "高风险提示（" + hits[0] + "）"
    hits = [k for k in MILD_RISK if k in text]
    if hits:
        return -3, "需核对/注明（" + hits[0] + "）"
    return -2, "存在提示性风险"


def score(it, lead):
    parts = []
    t = TIMELINESS.get(lead.get("timeliness"), 8)
    parts.append(("时效性：" + str(lead.get("timeliness") or "长期"), t))

    stage = (it.get("heat") or {}).get("stage")
    h = HEAT.get(stage, 6)
    parts.append(("热度阶段：" + str(stage or "未知"), h))

    v = (it.get("verification") or {}).get("status")
    vs = VERIFY.get(v, 0)
    parts.append(("核实状态：" + str(v or "未核实"), vs))

    p = lead.get("priority")
    ps = PRIORITY.get(p, 5)
    parts.append(("编辑优先级：" + str(p or "中"), ps))

    complete = 0
    outline = lead.get("outline") or []
    if len(outline) >= 3:
        complete += 3
    if lead.get("basis"):
        complete += 2
    if lead.get("audience"):
        complete += 2
    if len(str(lead.get("angle") or "")) >= 15:
        complete += 3
    parts.append(("线索完整度", complete))

    platform = str(it.get("platform") or "")
    src = 0
    if any(k in platform for k in AUTHORITATIVE):
        src = 5
    elif any(k in platform for k in AGGREGATED):
        src = -3
    parts.append(("来源权威度", src))

    diff = day_diff(it.get("collectedAt"))
    rec = 5 if diff == 0 else (3 if diff == 1 else (1 if diff == 2 else 0))
    parts.append(("采集新鲜度", rec))

    penalty, risk_reason = risk_penalty(lead.get("risk"))
    parts.append(("风险扣分：" + risk_reason, penalty))

    total = sum(x[1] for x in parts)
    return max(0, min(100, total)), parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=0, help="两个去向都取 N 条；不填则用 TARGET_TOP（公众号 6 / 头条 8）")
    args = ap.parse_args()

    data = json.loads(ITEMS.read_text(encoding="utf-8"))
    items = data.get("items", [])
    by_id = {it.get("id"): it for it in items}

    scored = []
    for it in items:
        for lead in it.get("leads", []):
            if lead.get("target") not in {"公众号", "今日头条"}:
                continue
            s, parts = score(it, lead)
            scored.append({
                "score": s,
                "breakdown": [{"label": k, "points": v} for k, v in parts],
                "itemId": it.get("id"),
                "region": it.get("region"),
                "sourceTitle": it.get("title"),
                "platform": it.get("platform"),
                "url": it.get("url"),
                "verification": (it.get("verification") or {}).get("status"),
                "heatStage": (it.get("heat") or {}).get("stage"),
                "lead": lead,
            })

    scored.sort(key=lambda x: (-x["score"], str(x["sourceTitle"])))
    groups = {}
    caps = {}
    for target in ["公众号", "今日头条"]:
        cap = args.top or TARGET_TOP[target]
        caps[target] = cap
        rows = [x for x in scored if x["lead"].get("target") == target]
        seen = set()
        picked = []
        for row in rows:
            key = row["itemId"]
            if key in seen:
                continue
            seen.add(key)
            rank = len(picked) + 1
            row = dict(row)
            row["rank"] = rank
            row["target"] = target
            picked.append(row)
            if len(picked) >= cap:
                break
        groups[target] = picked

    result = {
        "version": 1,
        "date": date.today().isoformat(),
        "generatedAt": now_local(),
        "totalScored": len(scored),
        "topPerTarget": caps,
        "weights": {
            "timeliness": TIMELINESS, "heat": HEAT, "verification": VERIFY,
            "priority": PRIORITY, "completenessMax": 10, "sourceMax": 5,
            "recencyMax": 5, "riskPenaltyMin": -6,
        },
        "groups": groups,
    }
    PICKS.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    EMBED.write_text(
        "window.__PICKS__=" + json.dumps(result, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"[done] 评分 {len(scored)} 条线索")
    for target, rows in groups.items():
        print(f"[{target} TOP{len(rows)}]")
        for r in rows:
            print(f"  {r['rank']}. {r['score']} 分 | {r['lead']['headline'][:38]} | {r['verification']}")
    print("by_id", len(by_id))


if __name__ == "__main__":
    main()
