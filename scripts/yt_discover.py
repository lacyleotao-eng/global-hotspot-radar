#!/usr/bin/env python3
"""YouTube 选题发现：按类型轮换搜索，输出当天候选清单。

只做发现，不下载、不转写。候选写进 data/yt-digest/inbox/<日期>.json，
后续写稿任务从里面挑。加 --plan 时直接产出当天 10 条选题计划（每天目标见 DAILY_TARGET）。

用法：
  python3 scripts/yt_discover.py                                    # 今天，采 10 类候选
  python3 scripts/yt_discover.py --plan                             # 今天，产出 10 条选题计划
  python3 scripts/yt_discover.py --types food,money,tech --per 4
  python3 scripts/yt_discover.py --plan --n-types 5                 # 只排 5 条（试跑/补缺）

注意：
  - 需要 /tmp/yt_cookies.txt（scripts/yt_export_cookies.js 生成），否则 YouTube 会要求登录验证。
  - 只用 yt-dlp 的 flat search 拿元信息，速度快；个别条目缺 view_count 时按 0 处理。
  - 已经出过稿的 videoId 会自动排除（读 data/yt-digest/index.json），避免重复拆解。
"""
import argparse
import json
import random
import re
import subprocess
import sys
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "yt-digest" / "inbox"
INDEX = ROOT / "data" / "yt-digest" / "index.json"
COOKIES = "/tmp/yt_cookies.txt"

# 每天要发的篇数（站点、选题、质检都读这个口径）
DAILY_TARGET = 10

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


# 标题打分：一天 10 篇全靠机器选，必须优先「讲流程/价格/参数」的攻略型片子，
# 压掉 vlog、闲聊、reaction 这类看着热但抽不出可执行动作的。
GOOD_WORDS = [
    "攻略", "教程", "指南", "步骤", "方法", "清单", "避坑", "怎么", "如何", "教你", "手把手",
    "预算", "费用", "价格", "成本", "省钱", "对比", "实测", "测评", "入门", "基础", "计划",
    "guide", "tutorial", "how to", "how i", "tips", "steps", "cost", "budget", "price",
    "explained", "beginner", "routine", "checklist", "review", "vs ",
]
BAD_WORDS = [
    "vlog", "日常", "我的一天", "跟我", "记录", "闲聊", "聊天", "直播", "reaction", "反应",
    "开箱", "unboxing", "prank", "挑战", "第一次", "哭", "感动", "治愈", "沉浸式",
]


def title_score(title: str) -> int:
    t = (title or "").lower()
    score = 0
    for w in GOOD_WORDS:
        if w in t:
            score += 2
    for w in BAD_WORDS:
        if w in t:
            score -= 3
    return score


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


def used_video_ids():
    """已经出过稿的 videoId，选题时排除，避免同一支片子被拆两次。"""
    if not INDEX.exists():
        return set()
    try:
        data = json.loads(INDEX.read_text("utf-8"))
    except Exception:
        return set()
    return {d.get("videoId") for d in (data.get("docs") or []) if d.get("videoId")}


def slugify(text, maxlen=42):
    """标题 → 目录 slug（只留安全字符，中文标题时用 videoId 兜底）。"""
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", "-", text or "").strip("-").lower()
    s = re.sub(r"-{2,}", "-", s)
    return s[:maxlen].strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", default="", help="逗号分隔的类型 key，默认按日期轮换 10 类")
    ap.add_argument("--n-types", type=int, default=DAILY_TARGET, help="轮换多少个类型（=每天篇数）")
    ap.add_argument("--per", type=int, default=4, help="每个类型保留几条候选")
    ap.add_argument("--plan", action="store_true", help="产出选题计划 inbox/<日期>-plan.json（每个类型 1 条）")
    ap.add_argument("--min-views", type=int, default=10000)
    ap.add_argument("--max-days", type=int, default=45, help="只要最近 N 天发布的（0 = 不限）")
    ap.add_argument("--min-dur", type=int, default=360)
    ap.add_argument("--max-dur", type=int, default=2400)
    args = ap.parse_args()

    n_types = max(1, min(args.n_types, len(QUERIES)))
    if args.types:
        types = [t.strip() for t in args.types.split(",") if t.strip()]
    else:
        keys = list(QUERIES.keys())
        seed = int(date.today().strftime("%Y%m%d"))
        rnd = random.Random(seed)
        types = rnd.sample(keys, min(n_types, len(keys)))

    cookie_args = []
    if Path(COOKIES).exists():
        cookie_args = ["--cookies", COOKIES]
    else:
        print("[warn] 没有 cookie 文件，YouTube 很可能要求登录验证")

    cutoff = None
    if args.max_days > 0:
        cutoff = date.today() - timedelta(days=args.max_days)

    used = used_video_ids()
    if used:
        print(f"[dedup] 已出稿 {len(used)} 支，本次跳过")

    picks = []
    seen = set(used)
    for t in types:
        qs = QUERIES.get(t, [])
        if not qs:
            print(f"[warn] 未知类型 {t}")
            continue
        # 用 crc32 而不是内置 hash：内置 hash 每个进程都变，同一天跑两次会选到不同搜索词
        q = random.Random(int(date.today().strftime("%Y%m%d")) + zlib.crc32(t.encode()) % 999).choice(qs)
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
        for r in rows:
            r["score"] = title_score(r["title"])
        # 先看是不是攻略型，再看播放量：纯热度会把 vlog 顶上来，抽帧时全是博主出镜
        rows.sort(key=lambda x: (x["score"], x["views"]), reverse=True)
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
        print(f"  · [{p['categoryKey']}] {p['views']:>7} 播放｜{p['duration']//60:>2} 分｜分 {p.get('score', 0):>2}｜{p['title'][:52]}")
    if not picks:
        sys.exit(1)

    if args.plan:
        write_plan(today, picks, types)


def plan_slug(today, item):
    """目录名：英文标题尽量用可读 slug；中文/过长标题退回「类型-videoId」，避免超长文件名与 URL 转义。"""
    s = slugify(item["title"], 30)
    if len(s) < 8 or not re.search(r"[a-z]{3,}", s):
        s = f"{item['categoryKey']}-{item['videoId'][:8].lower()}"
    return f"{ymd(today)}-{s}"


def write_plan(today, picks, types):
    """每个类型取播放最高的一条，凑成当天计划；已有计划则合并（不覆盖已写的进度）。"""
    path = INBOX / f"{ymd(today)}-plan.json"
    old = {}
    if path.exists():
        try:
            for it in (json.loads(path.read_text("utf-8")).get("items") or []):
                old[it.get("videoId")] = it
        except Exception:
            pass
    items = []
    for t in types:
        cand = [p for p in picks if p["categoryKey"] == t]
        if not cand:
            continue
        best = cand[0]
        prev = old.get(best["videoId"]) or {}
        items.append({
            **best,
            "slug": prev.get("slug") or plan_slug(today, best),
            "status": prev.get("status", "pending"),
        })
    plan = {
        "date": ymd(today),
        "target": DAILY_TARGET,
        "planned": len(items),
        "items": items,
    }
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), "utf-8")
    print(f"[plan] {len(items)} 条选题（目标 {DAILY_TARGET} 篇）→ {path.relative_to(ROOT)}")
    for it in items:
        print(f"  · [{it['categoryKey']}] {it['title'][:56]}")
    if len(items) < DAILY_TARGET:
        print(f"[warn] 只排到 {len(items)} 条，缺 {DAILY_TARGET - len(items)} 条，需要换类型重跑")
        return 1
    return 0


if __name__ == "__main__":
    main()
