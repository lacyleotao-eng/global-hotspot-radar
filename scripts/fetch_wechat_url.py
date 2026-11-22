#!/usr/bin/env python3
"""微信公众号单链接解析器 —— 支持文章与贴图（图片消息）。

【为什么需要这个脚本】
2026-11-22 用户实测：本机微信客户端里点开任意公众号文章/贴图，右键「复制链接」
拿到的就是 mp.weixin.qq.com/s/xxx 真实直链。实测抓取该直链，HTML 内嵌了完整的
cgiDataNew 对象，含 nick_name/title/content_noencode/create_time/图片 CDN 链接，
以及形态标识 type 与 item_show_type。这推翻了「贴图没有公开链接」的旧结论——
贴图有直链，只是不被搜索引擎收录，只能从微信客户端复制。

【能拿到 / 拿不到】
- 能拿：标题、账号、真实原文直链、发布时间、正文全文、字数、段落数、图片数、形态标识。
- 拿不到：阅读数/点赞数（HTML 里 readNum=0 是占位，真实值走客户端接口，外部不可见）。
  若用户从微信客户端截图里读到互动数，可用 --engagement 补录，并写明来源=客户端页面可见。
- 铁律：任何互动数字必须有来源，拿不到一律「不可见」，绝不编造。

用法：
  python3 scripts/fetch_wechat_url.py --url https://mp.weixin.qq.com/s/xxx
  python3 scripts/fetch_wechat_url.py --urls-file data/wechat-urls.txt
  python3 scripts/fetch_wechat_url.py --url URL --engagement '{"likes":218,"shares":645,"wow":57,"comments":10}' --engagement-source '微信客户端页面可见(用户截图)'
  python3 scripts/fetch_wechat_url.py --url URL --out data/viral-inbox/xxx.json
"""
import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "viral-inbox"
# 微信客户端 UA，网页端 UA 拿到的正文可能被裁剪
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x18003128) NetType/WIFI Language/zh_CN"


def now_iso():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def decode_wx(s):
    """还原微信正文里的转义：\\x0a 换行、\\x26lt/gt/quot 等 HTML 实体。"""
    if not s:
        return ""
    s = s.replace("\\x0a", "\n").replace("\\x0d", "")
    s = s.replace("\\x26lt;", "<").replace("\\x26gt;", ">")
    s = s.replace("\\x26quot;", '"').replace("\\x26amp;", "&")
    s = html.unescape(s)
    return s


def grab_field(seg, key):
    """从 cgiDataNew 片段里取一个字符串字段（单引号或双引号）。"""
    m = re.search(r"\b" + re.escape(key) + r"\s*:\s*'((?:[^'\\]|\\.)*)'", seg)
    if not m:
        m = re.search(r'\b' + re.escape(key) + r'\s*:\s*"((?:[^"\\]|\\.)*)"', seg)
    return m.group(1) if m else None


def grab_num(seg, key):
    m = re.search(r"\b" + re.escape(key) + r"\s*:\s*'(\d+)'\s*\*\s*1", seg)
    if not m:
        m = re.search(r"\b" + re.escape(key) + r"\s*:\s*(\d+)", seg)
    return int(m.group(1)) if m else None


def parse_pubdate(raw):
    if not raw:
        return None
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", str(raw))
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm = int(m.group(4) or 0), int(m.group(5) or 0)
        return f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}:00+08:00"
    if re.fullmatch(r"\d{10}", str(raw)):
        dt = datetime.fromtimestamp(int(raw), timezone(timedelta(hours=8)))
        return dt.isoformat(timespec="seconds")
    return None


def guess_form(type_, item_show_type, word_count, image_count):
    """形态判定：type=9 / item_show_type=8 是微信图片消息(贴图/小绿书)。"""
    if type_ == 9 or item_show_type == 8:
        return "gzh-poster"
    return "gzh-article"


def title_pattern(title):
    rules = [
        (r"\d", "数字+结果"),
        (r"[？?]", "痛点+反问"),
        (r"[！!]", "强情绪判断"),
        (r"为什么|为何|真相|原来", "悬念+揭秘"),
        (r"如何|怎么|攻略|指南|教程", "方法论承诺"),
        (r"我|我们|亲身|实测", "第一人称经历"),
        (r"决定|不|别|停止", "反常识断言"),
    ]
    for pat, label in rules:
        if re.search(pat, title):
            return label
    return "热点借势+观点判断"


def freshness_points(pub):
    if not pub:
        return 0
    try:
        dt = datetime.fromisoformat(pub)
        days = (datetime.now(timezone(timedelta(hours=8))) - dt).days
        if days <= 1:
            return 10
        if days <= 7:
            return 6
        return 2
    except Exception:
        return 0


def parse_url(url, engagement=None, engagement_source=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode("utf-8", "ignore")

    if "当前环境异常" in raw or "去验证" in raw:
        raise RuntimeError("微信返回验证页，采集失败")
    i = raw.find("window.cgiDataNew = {")
    if i < 0:
        raise RuntimeError("页面未找到 cgiDataNew 数据对象，可能是文章已删除或链接失效")
    seg = raw[i:i + 30000]

    title = grab_field(seg, "title")
    account = grab_field(seg, "nick_name")
    content = decode_wx(grab_field(seg, "content_noencode") or "")
    desc = decode_wx(grab_field(seg, "desc") or "")
    cdn = grab_field(seg, "cdn_url") or ""
    pub_raw = grab_field(seg, "create_time")
    type_ = grab_num(seg, "type")
    item_show_type = grab_num(seg, "item_show_type")
    show_cover = grab_num(seg, "show_cover_pic")

    if not title:
        raise RuntimeError("未解析到标题")

    # 正文：优先 content_noencode，其次 desc
    body = content or desc
    body_lines = [l.strip() for l in body.split("\n") if l.strip()]
    word_count = len(re.sub(r"\s", "", body))
    paragraphs = len(body_lines)
    # 图片数：正文里的 img 标签 + CDN 封面（贴图通常正文图多）
    body_imgs = len(re.findall(r"<img\b", content, flags=re.I))
    all_mmimg = set(re.findall(r"https?://mmbiz\.qpic\.cn/[^\s'\"<>]+", raw))
    image_count = max(body_imgs, 1 if cdn else 0, len(all_mmimg) if form_is_poster(type_, item_show_type) else 0)
    form = guess_form(type_, item_show_type, word_count, image_count)

    pub = parse_pubdate(pub_raw)
    fp = freshness_points(pub)

    # 互动数据：默认不可见；只有用户从客户端读到并显式传入时才写入，且写明来源
    signals = {k: "不可见" for k in ("views", "likes", "comments", "shares", "favorites", "wow")}
    source_note = "微信外部页面无阅读/互动数（HTML 内 readNum=0 为占位），不可见，未编造"
    if engagement:
        label_map = {"views": "阅读", "likes": "点赞", "comments": "评论", "shares": "分享", "favorites": "收藏", "wow": "在看"}
        for k, v in engagement.items():
            if k in signals and v not in (None, "", "不可见"):
                signals[k] = f"{v}（来源：{engagement_source or '用户提供'}）"
        source_note = f"互动数字由用户提供，来源：{engagement_source or '用户提供'}；阅读数仍不可见"
    signals["source"] = engagement_source or "微信客户端复制链接+网页解析正文"

    # 爆款指数：阅读/互动不可见则对应维度 0 分；有客户端互动数则按可见信号给基础分
    read_pts = 0
    inter_pts = 0
    if engagement and (engagement.get("likes") or engagement.get("shares") or engagement.get("comments")):
        inter_pts = 8  # 客户端可见互动，给基础分，但不冒充榜单/爆款认证
    breakdown = [
        {"label": "阅读信号", "points": read_pts, "note": "微信外部页面无阅读数，不可见，不编造"},
        {"label": "互动信号", "points": inter_pts, "note": source_note},
        {"label": "榜单信号", "points": 0, "note": "未取得该文上榜证据"},
        {"label": "传播广度", "points": 5, "note": "从微信客户端复制的真实原文直链，可回溯核验"},
        {"label": "时效性", "points": fp, "note": f"发布于 {pub or '未知'}，距采集 {fp or '超期'}"},
    ]
    total = sum(b["points"] for b in breakdown)
    tier = "S" if total >= 85 else "A" if total >= 70 else "B" if total >= 55 else "C"

    notes = "原文为 mp.weixin.qq.com 真实直链（用户从微信客户端复制），正文/字数/图数/发布时间来自页面内嵌 cgiDataNew。"
    if form == "gzh-poster":
        notes += f" 形态判定：type={type_}/item_show_type={item_show_type}，微信图片消息(贴图)。"
    notes += " " + source_note + "。仅作形态/结构基准，不冒充当期爆款。"

    return {
        "title": title,
        "form": form,
        "platform": "微信公众号",
        "account": account or "未知公众号",
        "url": url,
        "publishedAt": pub,
        "collectedAt": now_iso(),
        "category": "综合",
        "region": "国内",
        "summary": (desc or body[:180]).strip()[:200],
        "signals": signals,
        "ranking": None,
        "viralScore": {
            "total": total,
            "tier": tier,
            "breakdown": breakdown,
            "method": "五维加权：阅读30+互动25+榜单20+传播15+时效10，逐项见 breakdown",
        },
        "anatomy": {
            "wordCount": word_count,
            "paragraphs": paragraphs,
            "subheads": 0,
            "images": image_count,
            "titlePattern": title_pattern(title),
            "hook": body_lines[0][:120] if body_lines else "",
            "structure": [],
            "highlightSkills": [],
            "lessons": [],
        },
        "verification": {
            "status": "部分核实",
            "method": "微信客户端复制链接 + 网页 cgiDataNew 解析",
            "notes": notes,
        },
        "tags": ["微信文章" if form == "gzh-article" else "微信贴图", "客户端复制链接", "形态基准"],
        "_type": type_,
        "_itemShowType": item_show_type,
        "_bodyPreview": body[:200],
    }


def form_is_poster(type_, item_show_type):
    return type_ == 9 or item_show_type == 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", action="append", default=[], help="mp.weixin.qq.com/s/xxx 直链，可重复")
    ap.add_argument("--urls-file", help="每行一个链接的文本文件")
    ap.add_argument("--engagement", help="互动数 JSON，如 '{\"likes\":218,\"shares\":645}'")
    ap.add_argument("--engagement-source", help="互动数来源说明，如 '微信客户端页面可见(用户截图)'")
    ap.add_argument("--out", help="输出 inbox 文件路径，默认 data/viral-inbox/wechat-urls-YYYYMMDD.json")
    args = ap.parse_args()

    urls = list(args.url)
    if args.urls_file:
        p = Path(args.urls_file)
        if not p.is_absolute():
            p = ROOT / p
        urls += [l.strip() for l in p.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]

    if not urls:
        print("[error] 需要 --url 或 --urls-file", file=sys.stderr)
        sys.exit(1)

    engagement = json.loads(args.engagement) if args.engagement else None
    out_rows = []
    for u in urls:
        if "mp.weixin.qq.com" not in u:
            print(f"[skip] 非微信链接：{u[:60]}")
            continue
        try:
            row = parse_url(u, engagement, args.engagement_source)
            row.pop("_bodyPreview", None)
            row.pop("_type", None)
            row.pop("_itemShowType", None)
            out_rows.append(row)
            a = row["anatomy"]
            print(f"[ok] {row['form']:12} {a['wordCount']:5}字 {a['images']:3}图 | {row['title'][:36]}")
        except Exception as exc:
            print(f"[error] {u[:60]} -> {exc}")

    if not out_rows:
        print("[done] 无有效条目，未写文件")
        return

    INBOX.mkdir(parents=True, exist_ok=True)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = ROOT / out
    else:
        out = INBOX / f"wechat-urls-{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')}.json"
    out.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 写入 {out.name}：{len(out_rows)} 条")


if __name__ == "__main__":
    main()
