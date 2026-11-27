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
# 备胎数量：实测约 1/3 的候选会死在「无字幕 / 全片人物出镜 / 凑不到 8 张客观镜头」，
# 所以计划要比目标多排几条，写稿轮次才有得换。
PLAN_BUFFER = 5
# 人物出镜风险高的类型：健身、穿搭、宠物训练、亲子、人生感悟基本都是「人对着镜头讲」，
# 客观镜头（物件/招牌/场景）少，排计划时放后面，缺口留给它们。
PERSON_RISK = {"health", "fashion", "pet", "parenting", "life"}

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


def probe_subs(url, cookie_args):
    """探一下这支片子有没有字幕轨（人工或自动）。实测 5 秒/条，比写完稿才发现没字幕便宜得多。"""
    cmd = ["yt-dlp", "--list-subs", "--skip-download", "--no-warnings", *cookie_args, url]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return None
    txt = (out.stdout or "") + (out.stderr or "")
    if "has no subtitles" in txt and "has no automatic captions" in txt:
        return False
    if "Available subtitles" in txt or "Available automatic captions" in txt:
        return True
    return None


def used_video_ids():
    """已经出过稿、或当天已被判死的 videoId，选题时一律排除。

    「判死」= 计划里 status=abandoned（无字幕 / 全片人物出镜 / 凑不到 8 张客观镜头）。
    不排除的话每次重跑都会把它们又排进来，白占名额。
    """
    ids = set()
    if INDEX.exists():
        try:
            data = json.loads(INDEX.read_text("utf-8"))
            ids |= {d.get("videoId") for d in (data.get("docs") or []) if d.get("videoId")}
        except Exception:
            pass
    plan_path = INBOX / f"{ymd(date.today())}-plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text("utf-8"))
            ids |= {it.get("videoId") for it in (plan.get("items") or [])
                    if it.get("status") == "abandoned" and it.get("videoId")}
        except Exception:
            pass
    return ids


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
    ap.add_argument("--plan", action="store_true", help="产出选题计划 inbox/<日期>-plan.json")
    ap.add_argument("--no-probe", dest="probe", action="store_false", help="跳过字幕探测（快，但会把没字幕的片子排进计划）")
    ap.set_defaults(probe=True)
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

        kept = 0
        probed = 0
        for r in rows:
            if kept >= args.per or probed >= args.per * 3:
                break
            if args.probe:
                probed += 1
                has = probe_subs(r["url"], cookie_args)
                if has is False:
                    print(f"    [skip] 无字幕：{r['title'][:36]}")
                    seen.add(r["videoId"])
                    continue
                r["hasSubs"] = has
            seen.add(r["videoId"])
            picks.append(r)
            kept += 1

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
    """排当天计划：先给每个类型 1 条，再补到「目标 + 备胎」。

    - 类型按人物出镜风险排序（person-risk 的放后面），缺口优先落在这些类型上。
    - 计划条数 = DAILY_TARGET + PLAN_BUFFER，给写稿轮次留替换余地。
    - 已有计划时保留原 slug 与 status（不覆盖当天已写/已弃的进度）。
    """
    path = INBOX / f"{ymd(today)}-plan.json"
    old = {}
    if path.exists():
        try:
            for it in (json.loads(path.read_text("utf-8")).get("items") or []):
                old[it.get("videoId")] = it
        except Exception:
            pass

    by_type = {}
    for p in picks:
        by_type.setdefault(p["categoryKey"], []).append(p)
    ordered = sorted(types, key=lambda t: (t in PERSON_RISK, t))

    want = DAILY_TARGET + PLAN_BUFFER
    chosen = []
    taken = set()

    # 第一轮：每个类型 1 条
    for t in ordered:
        if len(chosen) >= want:
            break
        for c in by_type.get(t, []):
            if c["videoId"] in taken:
                continue
            chosen.append(c)
            taken.add(c["videoId"])
            break

    # 后续轮：按类型轮流补备胎
    while len(chosen) < want:
        added = False
        for t in ordered:
            if len(chosen) >= want:
                break
            for c in by_type.get(t, []):
                if c["videoId"] in taken:
                    continue
                chosen.append(c)
                taken.add(c["videoId"])
                added = True
                break
        if not added:
            break

    items = []
    for c in chosen:
        prev = old.get(c["videoId"]) or {}
        items.append({
            **c,
            "slug": prev.get("slug") or plan_slug(today, c),
            "status": prev.get("status", "pending"),
            "notes": prev.get("notes", ""),
            "buffer": 1 if len(items) >= DAILY_TARGET else 0,
        })

    plan = {
        "date": ymd(today),
        "target": DAILY_TARGET,
        "buffer": max(0, len(items) - DAILY_TARGET),
        "planned": len(items),
        "items": items,
    }
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), "utf-8")
    print(f"[plan] {len(items)} 条（目标 {DAILY_TARGET} + 备胎 {len(items) - DAILY_TARGET}）→ {path.relative_to(ROOT)}")
    for it in items:
        tag = "备胎" if it["buffer"] else "正选"
        print(f"  · [{tag}][{it['categoryKey']}] {it['title'][:52]}")
    if len(items) < DAILY_TARGET:
        print(f"[warn] 正选只排到 {len(items)} 条，缺 {DAILY_TARGET - len(items)} 条，需要换类型重跑")
        return 1
    return 0


if __name__ == "__main__":
    main()
