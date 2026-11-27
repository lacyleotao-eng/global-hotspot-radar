#!/usr/bin/env python3
"""从当天选题计划里取「下 N 篇还没写的」，或把已完成的标成 done。

一天 10 篇要拆成 5 个轮次跑，每轮不该自己重新选题——统一读 inbox/<日期>-plan.json。

用法：
  python3 scripts/yt_plan_next.py --n 2      # 打印下 2 条的 JSON（给写稿任务消费）
  python3 scripts/yt_plan_next.py --sync     # 按实际 article.html 回写 status=done
  python3 scripts/yt_plan_next.py --abandon <slug> --reason "无字幕"   # 标记废稿选题
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
    ap.add_argument("--abandon", default="", help="把某个 slug 标成废（无字幕/全片人物/凑不到图），不再重试")
    ap.add_argument("--reason", default="", help="废掉的原因，写进 plan 里备查")
    args = ap.parse_args()

    plan, path = load_plan(args.date)
    if plan is None:
        print(json.dumps({"error": "no-plan", "path": str(path), "items": []}, ensure_ascii=False))
        return 2

    items = plan.get("items") or []

    if args.abandon:
        hit = 0
        for it in items:
            if it.get("slug") == args.abandon:
                it["status"] = "abandoned"
                it["notes"] = args.reason or "未写原因"
                hit += 1
        if not hit:
            print(f"[warn] 计划里没有 slug={args.abandon}")
        else:
            path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), "utf-8")
            print(f"[abandon] {args.abandon}｜{args.reason}")

    for it in items:
        if it.get("status") != "abandoned" and is_done(it):
            it["status"] = "done"
    dead = [it for it in items if it.get("status") == "abandoned"]
    pending = [it for it in items if it.get("status") not in ("done", "abandoned")]
    target = plan.get("target") or 10

    # 进度一律按磁盘上今天的稿子数算：计划重排会丢掉已完成条目，不能拿计划当账本
    on_disk = sorted(d.name for d in DIGEST.glob(f"{args.date}-*")
                     if d.is_dir() and (d / "article.html").exists())
    done_n = len(on_disk)

    if args.sync or args.stats:
        plan["items"] = items
        plan["planned"] = len(items)
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), "utf-8")
        print(f"[plan] {args.date}：{done_n} / {target} 篇完成，待写 {len(pending)} 条，作废 {len(dead)} 条")
        for it in pending:
            print(f"  · [{it.get('categoryKey')}] {it.get('title','')[:56]}")
        for it in dead:
            print(f"  × [{it.get('categoryKey')}] {it.get('title','')[:44]}｜{it.get('notes','')}")
        if args.sync:
            return 0

    if args.n > 0 and not args.stats:
        out = {
            "date": args.date,
            "target": target,
            "done": done_n,
            "doneSlugs": on_disk,
            "remaining": len(pending),
            "gapToTarget": max(0, target - done_n),
            "items": pending[: args.n],
            "planPath": str(path.relative_to(ROOT)),
        }
        print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
