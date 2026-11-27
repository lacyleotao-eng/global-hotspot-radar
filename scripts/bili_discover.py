#!/usr/bin/env python3
"""B 站视频拆解 · 选片（按 data/yt-brief.md 第十二节「分区供给池与可拆性判据」）

用法：
    python3 scripts/bili_discover.py --n 3
    python3 scripts/bili_discover.py --n 5 --out data/bili-plan/2026-11-28.json

做什么：
1. 抓 B 站几个一级分区的排行榜（ranking/v2，无需登录，带 buvid3 即可）；
2. 按「能不能改写成别人照着做的步骤」打分：标题形态 > 分区属性 > 时长 > 热度；
3. 排除已出稿的 bvid（读 data/yt-digest/*/meta.json）与违法/红线题材；
4. 输出 top N，写 JSON 供出稿轮次直接取用。

注意：这里只做**题材初筛**。人物占比、能否凑够 8 张配图，要等取流后用帧探针再看，
本脚本不替那一步下结论。
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timezone, timedelta

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CST = timezone(timedelta(hours=8))

# 一级分区 rid：知识 36、科技 188、美食 211、生活 160、时尚 155、动物 217、汽车 223、运动 234
RIDS = [36, 188, 211, 160, 155, 223, 234]

# 二级分区（tname）基础分：越像「能拆成步骤」的越高；纯娱乐负分
TNAME_SCORE = {
    "美食制作": 9, "美食测评": 8, "田园美食": 7, "美食侦探": 5, "美食记录": 2,
    "野生技能协会": 10, "手工": 7, "出行": 5, "日常": 3, "亲子": 3, "绘画": 3, "三农": 4,
    "数码": 6, "计算机技术": 9, "软件应用": 9, "科工机械": 6, "极客DIY": 10,
    "校园学习": 9, "科学科普": 4, "财经商业": 6, "社科·法律·心理": 3, "人文历史": 1, "设计·创意": 4,
    "健身": 6, "运动": 3, "汽车": 5, "喵星人": 1, "汪星人": 1,
    "搞笑": -8, "明星综合": -6, "综艺": -6, "鬼畜剧场": -9,
}

# 标题正向：出自「教程 / 实测 / 配方 / 清单」这几种形态
GOOD = [
    "教程", "入门", "指南", "怎么", "如何", "步骤", "流程", "配方", "做法", "实测", "测评",
    "避坑", "教你", "手把手", "零基础", "一次搞懂", "一次讲完", "多少钱", "成本", "清单",
    "技巧", "方法", "攻略", "全套", "原理", "对比", "拆解", "还原", "改造", "维修", "自制",
    "教程向", "保姆级", "干货", "怎么选", "值不值", "够不够", "实测数据",
]

# 标题负向：以人为主 / 以观点为主 / 以作品为主
BAD = [
    "挑战", "吃播", "vlog", "日常", "记录", "鬼畜", "整活", "reaction", "反应",
    "解说", "泪", "感人", "故事", "新闻", "发布会", "活动", "投稿", "招募", "直播回放",
    "预告", "花絮", "合集", "明星", "演唱会", "跟拍", "我的一天", "生日", "婚礼",
    "分手", "恋爱", "前女友", "前男友", "道歉", "回应", "官方", "大赛", "公开赛",
    "颁奖", "纪录片", "混剪", "二创", "同人", "直播", "来了", "官宣",
]

# 红线：违法 / 高风险，永不入选
HARD_BAN = [
    "造枪", "枪支", "弹药", "炸药", "毒品", "赌博", "代孕", "偷渡", "洗钱",
    "荐股", "涨停", "开挂", "外挂", "破解版", "免登录", "翻墙", "爬取私密",
]


def http_json(url, buvid3=None):
    headers = {"User-Agent": UA, "Referer": "https://www.bilibili.com/",
               "Accept": "application/json, text/plain, */*"}
    if buvid3:
        headers["Cookie"] = f"buvid3={buvid3}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def get_buvid3():
    try:
        d = http_json("https://api.bilibili.com/x/frontend/finger/spi")
        return (d.get("data") or {}).get("b_3")
    except Exception:
        return None


def used_bvids():
    out = set()
    base = os.path.join(ROOT, "data", "yt-digest")
    if not os.path.isdir(base):
        return out
    for name in os.listdir(base):
        p = os.path.join(base, name, "meta.json")
        if not os.path.isfile(p):
            continue
        try:
            m = json.load(open(p, "utf-8"))
        except Exception:
            continue
        if m.get("bvid"):
            out.add(m["bvid"])
    return out


def pool_of(tname):
    """归到第十二节的六个供给池"""
    if tname in ("美食制作", "美食测评", "田园美食", "美食侦探", "美食记录"):
        return "美食"
    if tname in ("计算机技术", "软件应用"):
        return "人工智能"
    if tname in ("数码", "科工机械", "极客DIY", "设计·创意"):
        return "科技"
    if tname in ("野生技能协会", "出行", "日常", "亲子"):
        return "生活经验"
    if tname in ("手工", "绘画", "三农"):
        return "生活兴趣"
    if tname in ("健身", "运动"):
        return "健康"
    if tname in ("校园学习", "科学科普", "财经商业", "社科·法律·心理"):
        return "知识"
    return "其他"


POOL_WEIGHT = {"生活经验": 10, "人工智能": 10, "科技": 8, "美食": 7,
               "知识": 6, "生活兴趣": 5, "健康": 2, "其他": 0}


def score(item, now):
    title = item.get("title") or ""
    tname = item.get("tname") or ""
    dur = int(item.get("duration") or 0)
    view = int(((item.get("stat") or {}).get("view") or 0))
    pool = pool_of(tname)
    s = 30 + TNAME_SCORE.get(tname, 2) + POOL_WEIGHT.get(pool, 0)

    hits, miss = [], []
    low = title.lower()
    for w in GOOD:
        if w in low:
            s += 7
            hits.append(w)
    for w in BAD:
        if w.lower() in low:
            s -= 9
            miss.append(w)

    # 竖屏排除：竖屏的原片截帧裁成横图后有效像素太少，站内排版也很难看
    dim = item.get("dimension") or {}
    w, h = int(dim.get("width") or 0), int(dim.get("height") or 0)
    if w and h and h > w * 1.05:
        s -= 16
        miss.append("竖屏")

    # 时长：7–10 步的稿子，2 分钟以下基本写不满
    if dur < 120:
        s -= 14
    elif dur < 180:
        s -= 6
    elif dur <= 2400:
        s += 6
    else:
        s -= 10

    # 热度：B 站门槛比 YouTube 低，1 万算起步
    if view >= 1_000_000:
        s += 10
    elif view >= 100_000:
        s += 7
    elif view >= 10_000:
        s += 3
    else:
        s -= 12

    # 新鲜度：14 天内加分；超过 18 个月降权（攻略不过期，但不该天天推两年前的片）
    pub = int(item.get("pubdate") or 0)
    age = (now - datetime.fromtimestamp(pub, CST)).days if pub else 9999
    if age <= 14:
        s += 4
    elif age <= 180:
        s += 1
    elif age > 540:
        s -= 6

    # 器材类软降权：合法（射箭/户外），但站内分发与合规都更敏感，不硬禁
    for w in ("复合弓", "反曲弓", "弩", "弹弓", "甩棍", "战术刀", "军用刀", "匕首"):
        if w in title:
            s -= 8
            miss.append(w)

    reason = []
    if hits:
        reason.append("标题:" + "/".join(hits[:3]))
    if miss:
        reason.append("扣分:" + "/".join(miss[:3]))
    return s, pool, reason


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--min-view", type=int, default=10000)
    ap.add_argument("--out", default="")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    now = datetime.now(CST)
    b3 = get_buvid3()
    done = used_bvids()

    rows, seen = [], set()
    for rid in RIDS:
        try:
            j = http_json(
                f"https://api.bilibili.com/x/web-interface/ranking/v2?rid={rid}&type=all", b3)
        except Exception as e:
            print(f"[warn] rid={rid} 抓取失败：{e}", file=sys.stderr)
            continue
        if j.get("code") != 0:
            print(f"[warn] rid={rid} code={j.get('code')}", file=sys.stderr)
            continue
        for it in ((j.get("data") or {}).get("list") or []):
            bv = it.get("bvid")
            if not bv or bv in seen or bv in done:
                continue
            seen.add(bv)
            title = it.get("title") or ""
            if any(w in title for w in HARD_BAN):
                print(f"[ban] {bv} {title[:28]}", file=sys.stderr)
                continue
            if int(((it.get("stat") or {}).get("view") or 0)) < args.min_view:
                continue
            s, pool, reason = score(it, now)
            rows.append({
                "bvid": bv,
                "aid": it.get("aid"),
                "cid": it.get("cid"),
                "title": title,
                "tname": it.get("tname"),
                "pool": pool,
                "score": s,
                "duration": it.get("duration"),
                "view": ((it.get("stat") or {}).get("view") or 0),
                "danmaku": ((it.get("stat") or {}).get("danmaku") or 0),
                "pubdate": datetime.fromtimestamp(int(it.get("pubdate") or 0), CST).strftime("%Y-%m-%d"),
                "owner": (it.get("owner") or {}).get("name"),
                "desc": (it.get("desc") or "")[:120],
                "url": f"https://www.bilibili.com/video/{bv}",
                "reason": "；".join(reason),
            })

    rows.sort(key=lambda x: -x["score"])
    # 每个池子最多 2 条，避免全是美食
    picked, per = [], {}
    for r in rows:
        if per.get(r["pool"], 0) >= 2:
            continue
        per[r["pool"]] = per.get(r["pool"], 0) + 1
        picked.append(r)
        if len(picked) >= args.n:
            break

    print(f"候选池 {len(rows)} 条，取 {len(picked)} 条（已排除 {len(done)} 条已出稿）\n")
    for i, r in enumerate(picked, 1):
        m, sec = divmod(int(r["duration"] or 0), 60)
        print(f"[{i}] {r['score']}分 | {r['pool']}/{r['tname']} | {m}:{sec:02d} | "
              f"{r['view'] / 10000:.1f}万播放 | {r['pubdate']}")
        print(f"    {r['title']}")
        print(f"    {r['url']}  · {r['owner']}")
        print(f"    {r['reason']}\n")

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump({"date": args.date, "generatedAt": now.isoformat(timespec="seconds"),
                   "items": picked, "candidates": len(rows)},
                  open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"写入 {args.out}")
    if not picked:
        print("没有可用候选，放宽 --min-view 或换一天再取", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
