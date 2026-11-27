#!/usr/bin/env python3
"""从当天选题计划里取「下 N 篇还没写的」，或把已完成的标成 done。

一天 10 篇要拆成 5 个轮次跑，每轮不该自己重新选题——统一读 inbox/<日期>-plan.json。

用法：
  python3 scripts/yt_plan_next.py --n 2      # 打印下 2 条的 JSON（给写稿任务消费）
  python3 scripts/yt_plan_next.py --sync     # 按实际 article.html 回写 status=done
  python3 scripts/yt_plan_next.py --stats    # 人看的进度摘要

判定「已写」= data/yt-digest/<slug>/article.html 存在。
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "yt-digest" / "inbox"
DIGEST = ROOT / "data" / "yt-digest"


def load_plan(day):
    path = INBOX / f"{day}-plan.json"
    if not path.exists():
        return None, path
    try:
        return json.loads(path.read_text("utf-8")), path
    except Exception as e:
        print(f"[error] {path} 解析失败：{e}", file=sys.stderr)
        return None, path


def is_done(item):
    return (DIGEST / item["slug"] / "article.html").exists()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--n", type=int, default=2, help="取几条（默认 2，一轮的产出上限）")
    ap.add_argument("--sync", action="store_true", help="按实际文件回写 status")
    ap.add_argument("--stats", action="store_true", help="打印进度摘要")
    args = ap.parse_args()

    plan, path = load_plan(args.date)
    if plan is None:
        print(json.dumps({"error": "no-plan", "path": str(path), "items": []}, ensure_ascii=False))
        return 2

    items = plan.get("items") or []
    for it in items:
        if is_done(it):
            it["status"] = "done"
    done = [it for it in items if it.get("status") == "done"]
    pending = [it for it in items if it.get("status") != "done"]
    target = plan.get("target") or 10

    if args.sync or args.stats:
        plan["items"] = items
        plan["planned"] = len(items)
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), "utf-8")
        print(f"[plan] {args.date}：{len(done)} / {target} 篇完成，还剩 {len(pending)} 条待写")
        for it in pending:
            print(f"  · [{it.get('categoryKey')}] {it.get('title','')[:56]}")
        if args.sync:
            return 0

    if args.n > 0 and not args.stats:
        out = {
            "date": args.date,
            "target": target,
            "done": len(done),
            "remaining": len(pending),
            "gapToTarget": max(0, target - len(done)),
            "items": pending[: args.n],
            "planPath": str(path.relative_to(ROOT)),
        }
        print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
