#!/usr/bin/env python3
"""YouTube 选题发现：按类型轮换搜索，输出当天候选清单。

只做发现，不下载、不转写。候选写进 data/yt-digest/inbox/<日期>.json，
后续写稿任务从里面挑。

用法：
  python3 scripts/yt_discover.py                 # 今天，采 3 类
  python3 scripts/yt_discover.py --types food,money,tech
  python3 scripts/yt_discover.py --per 6 --min-views 10000 --days 30

注意：
  - 需要 /tmp/yt_cookies.txt（scripts/yt_export_cookies.js 生成），否则 YouTube 会要求登录验证。
  - 只用 yt-dlp 的 flat search 拿元信息，速度快；个别条目缺 view_count 时按 0 处理。
"""
import argparse
import json
import random
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "yt-digest" / "inbox"
COOKIES = "/tmp/yt_cookies.txt"

# 类型 → 搜索词（每条给 2–4 个角度，避免每次都是同一批片子）
QUERIES = {
    "food": ["探店 人均", "街头美食 攻略", "restaurant review local food guide", "家常菜 教程 步骤"],
    "travel": ["城市攻略 一日游", "旅行 路线 避坑", "travel guide itinerary tips", "小众 城市 散步"],
    "money": ["副业 实操 收入", "小生意 成本 利润", "side hustle breakdown", "摆摊 真实 流水"],
    "invest": ["理财 入门 常识", "基金 费用 规则", "personal finance basics explained"],
    "work": ["职场 升职 方法", "效率 工作流 工具", "career advice promotion"],
    "tech": ["AI 工具 实测", "AI workflow tutorial", "效率 软件 组合", "本地 部署 教程"],
    "gadget": ["数码 测评 选购", "gadget review comparison", "手机 笔记本 怎么选"],
    "life": ["人生 经验 总结", "life lessons practical", "中年人 转行 经历"],
    "health": ["减脂 训练 计划", "健身 动作 教学", "home workout beginner guide"],
    "home": ["装修 预算 顺序", "收纳 改造 小户型", "home renovation cost"],
    "parenting": ["育儿 方法 年龄", "亲子 沟通 技巧", "parenting tips toddler"],
    "study": ["英语 学习 方法", "备考 计划 安排", "language learning routine"],
    "diy": ["手工 制作 教程", "维修 自己 动手", "DIY repair tutorial"],
    "car": ["买车 避坑 攻略", "用车 保养 常识", "car buying tips"],
    "outdoor": ["露营 装备 新手", "钓鱼 钓点 技巧", "camping gear beginner"],
    "pet": ["养猫 新手 攻略", "训狗 方法", "puppy training basics"],
    "fashion": ["穿搭 基础 搭配", "通勤 穿搭 预算", "outfit formula capsule wardrobe"],
    "create": ["剪辑 教程 流程", "摄影 参数 设置", "video editing workflow"],
    "film": ["纪录片 解读 信息", "电影 幕后 制作", "documentary breakdown"],
    "law": ["办事 流程 材料", "合同 避坑 常识", "consumer rights how to"],
}


def ymd(d):
    return d.strftime("%Y-%m-%d")


def run_search(query, n, cookie_args):
    cmd = [
        "yt-dlp", "--flat-playlist", "-J", "--no-warnings",
        *cookie_args,
        f"ytsearch{n}:{query}",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return []
    if out.returncode != 0:
        print(f"  [warn] 搜索失败：{query}｜{out.stderr.strip().splitlines()[-1][:120] if out.stderr.strip() else ''}")
        return []
    try:
        data = json.loads(out.stdout)
    except Exception:
        return []
    return data.get("entries") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", default="", help="逗号分隔的类型 key，默认按日期轮换 3 类")
    ap.add_argument("--per", type=int, default=4, help="每个类型保留几条候选")
    ap.add_argument("--min-views", type=int, default=10000)
    ap.add_argument("--max-days", type=int, default=45, help="只要最近 N 天发布的（0 = 不限）")
    ap.add_argument("--min-dur", type=int, default=360)
    ap.add_argument("--max-dur", type=int, default=2400)
    args = ap.parse_args()

    if args.types:
        types = [t.strip() for t in args.types.split(",") if t.strip()]
    else:
        keys = list(QUERIES.keys())
        seed = int(date.today().strftime("%Y%m%d"))
        rnd = random.Random(seed)
        types = rnd.sample(keys, min(3, len(keys)))

    cookie_args = []
    if Path(COOKIES).exists():
        cookie_args = ["--cookies", COOKIES]
    else:
        print("[warn] 没有 cookie 文件，YouTube 很可能要求登录验证")

    cutoff = None
    if args.max_days > 0:
        cutoff = date.today() - timedelta(days=args.max_days)

    picks = []
    seen = set()
    for t in types:
        qs = QUERIES.get(t, [])
        if not qs:
            print(f"[warn] 未知类型 {t}")
            continue
        q = random.Random(int(date.today().strftime("%Y%m%d")) + hash(t) % 999).choice(qs)
        print(f"[search] {t} ← {q}")
        entries = run_search(q, 15, cookie_args)
        rows = []
        for e in entries:
            vid = e.get("id")
            if not vid or vid in seen:
                continue
            dur = e.get("duration") or 0
            if dur and not (args.min_dur <= dur <= args.max_dur):
                continue
            views = e.get("view_count") or 0
            up = e.get("upload_date") or ""
            if cutoff and up:
                try:
                    if datetime.strptime(up, "%Y%m%d").date() < cutoff:
                        continue
                except Exception:
                    pass
            if views and views < args.min_views:
                continue
            rows.append({
                "videoId": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": e.get("title") or "",
                "channel": e.get("channel") or e.get("uploader") or "",
                "duration": dur,
                "views": views,
                "publishedAt": up,
                "categoryKey": t,
            })
        rows.sort(key=lambda x: x["views"], reverse=True)
        for r in rows[: args.per]:
            seen.add(r["videoId"])
            picks.append(r)

    INBOX.mkdir(parents=True, exist_ok=True)
    today = date.today()
    out = {
        "date": ymd(today),
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "types": types,
        "candidates": picks,
    }
    path = INBOX / f"{ymd(today)}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    print(f"[ok] {len(picks)} 条候选 → {path.relative_to(ROOT)}")
    for p in picks:
        print(f"  · [{p['categoryKey']}] {p['views']:>7} 播放｜{p['duration']//60:>2} 分｜{p['title'][:52]}")
    if not picks:
        sys.exit(1)


if __name__ == "__main__":
    main()
