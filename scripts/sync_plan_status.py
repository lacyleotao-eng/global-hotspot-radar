#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 data/ready 里实际落盘的稿子，回写 data/plan/<日期>.json 的 status。

为什么需要它：出稿是分段跑的（05:40 公众号、06:50 头条），每段结束都要把
plan 里对应条目标成 done。但两段可能同时在跑，各写各的 plan 文件会互相覆盖。
所以 status 不靠任务自己维护，统一由这个脚本按「稿子是否存在且自检达标」重算。

用法：
    python3 scripts/sync_plan_status.py            # 今天
    python3 scripts/sync_plan_status.py --date 2026-11-24
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "data" / "ready"
PLAN_DIR = ROOT / "data" / "plan"
AUDIT = ROOT / "data" / "audit.json"
SH = timezone(timedelta(hours=8))
PASS = 85


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(SH).strftime("%Y-%m-%d"))
    a = ap.parse_args()

    plan_path = PLAN_DIR / f"{a.date}.json"
    if not plan_path.exists():
        print(f"[skip] 没有 {plan_path.name}")
        return
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    # 自检分：按 file::form 索引
    scores = {}
    try:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        for p in audit.get("pieces") or []:
            scores[f"{p.get('file')}::{p.get('form')}"] = p.get("score") or 0
    except Exception:
        pass

    filed: dict[str, dict] = {}
    for path in sorted(READY.glob(f"{a.date}-*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        iid = d.get("sourceItemId") or ""
        pieces = d.get("pieces") or []
        if not iid or not pieces:
            continue
        form = pieces[0].get("id") or ""
        sc = scores.get(f"{path.name}::{form}")
        filed[iid] = {"file": path.name, "form": form, "score": sc,
                      "passed": (sc is None or sc >= PASS)}

    done = 0
    for e in plan.get("events") or []:
        hit = filed.get(e.get("sourceItemId") or "")
        if hit:
            e["status"] = "done" if hit["passed"] else "rejected"
            e["readyFile"] = hit["file"]
            if hit["score"] is not None:
                e["auditScore"] = hit["score"]
            if hit["passed"]:
                done += 1
        else:
            e["status"] = e.get("status") if e.get("status") in ("todo",) else "todo"

    plan["syncedAt"] = datetime.now(SH).replace(microsecond=0).isoformat()
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")

    total = len(plan.get("events") or [])
    todo = [e["slug"] for e in plan.get("events") or [] if e.get("status") == "todo"]
    rej = [e["slug"] for e in plan.get("events") or [] if e.get("status") == "rejected"]
    print(f"[sync] {a.date}: {done}/{total} done")
    if rej:
        print(f"  [rejected] 自检未达标：{', '.join(rej)}")
    if todo:
        print(f"  [todo] 还没出稿：{', '.join(todo)}")


if __name__ == "__main__":
    main()
