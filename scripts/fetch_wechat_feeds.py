#!/usr/bin/env python3
"""微信公众号「文章形态」采集器 —— 基于 Wechat2RSS 公开 feed。

为什么用这条源：
- 本机微信客户端 GUI 无法把页面文字读回自动化程序（截图不回传、AX 树不含正文、
  后台键盘事件被丢弃、复制剪贴板为空），不能作为稳定数据源。
- Wechat2RSS（https://wechat2rss.xlab.app，1665★ 开源项目 ttttmr/Wechat2RSS 的公开服务）
  把公众号文章转成 RSS，含真实 mp.weixin.qq.com 原文直链、完整正文、图片、发布时间。
  只收录有深度的长文，正好适合做「文章形态」的结构基准。
- 局限：它不含「贴图/图片消息」（小绿书），也不含阅读/点赞数。
  阅读数一律写「不可见」，绝不编造；贴图形态由单独的客户端通道处理，拿不到就留空。

输入：data/wechat-feeds.json  （账号名 -> feed URL；只放真实存在的 feed）
输出：data/viral-inbox/wechat-feeds-YYYYMMDD.json （gzh-article 条目，供 ingest_viral.py 合并）

用法：
  python3 scripts/fetch_wechat_feeds.py            # 采集当天
  python3 scripts/fetch_wechat_feeds.py --days 3   # 只收近 3 天发布
  python3 scripts/fetch_wechat_feeds.py --limit 2  # 每个号最多取 2 条
"""
import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDS_CONF = ROOT / "data" / "wechat-feeds.json"
INBOX = ROOT / "data" / "viral-inbox"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

TIER_C = "C"


def now_iso():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def parse_date(s):
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return dt.astimezone(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    except Exception:
        m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s)
        if m:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}T00:00:00+08:00"
        return None


def strip_tags(s):
    s = re.sub(r"<\s*br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</\s*p\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


def parse_feed(url, account_hint=""):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode("utf-8", "ignore")
    ch = re.search(r"<channel>(.*?)</channel>", raw, re.S)
    if not ch:
        return []
    channel = ch.group(1)
    m = re.search(r"<title>(.*?)</title>", channel, re.S)
    account = html.unescape(m.group(1)).strip() if m else (account_hint or "未知公众号")
    out = []
    for blob in re.findall(r"<item>(.*?)</item>", channel, re.S):
        def grab(tag, blob=blob):
            mm = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", blob, re.S)
            return html.unescape(mm.group(1)).strip() if mm else ""

        title = grab("title")
        link = grab("link").replace("&amp;", "&")
        pub = parse_date(grab("pubDate"))
        desc = strip_tags(grab("description")).strip()
        cdata = re.search(r"<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>", blob, re.S)
        body_html = cdata.group(1) if cdata else ""
        body = strip_tags(body_html)
        body_clean = re.sub(r"[ \t]+", " ", body)
        word_count = len(re.sub(r"\s", "", body_clean))
        images = len(re.findall(r"<img\s", body_html))
        # 小标题：h2/h3 或 strong 独占一行的段落
        subheads = len(re.findall(r"<h[23][^>]*>", body_html, re.I))
        paragraphs = len(re.findall(r"<p[^>]*>", body_html, re.I))
        if not title or not link:
            continue
        if "mp.weixin.qq.com" not in link:
            continue  # 平台闸门：只收真微信原文
        out.append({
            "title": title,
            "form": "gzh-article",
            "platform": "微信公众号",
            "account": account,
            "url": link,
            "publishedAt": pub,
            "collectedAt": now_iso(),
            "category": "综合",
            "region": "国内",
            "summary": (desc or body_clean[:180]).strip()[:200],
            "signals": {k: "不可见" for k in ("views", "likes", "comments", "shares", "favorites", "wow", "source")},
            "ranking": None,
            "viralScore": {
                "total": 3,
                "tier": TIER_C,
                "breakdown": [
                    {"label": "阅读信号", "points": 0, "note": "微信外部页面无阅读数，不可见，不编造"},
                    {"label": "互动信号", "points": 0, "note": "无可见点赞/在看/评论计数"},
                    {"label": "榜单信号", "points": 0, "note": "未取得该文上榜证据"},
                    {"label": "传播广度", "points": 3, "note": "被 Wechat2RSS 收录为公开 feed，单一来源"},
                    {"label": "时效性", "points": 0, "note": "由采集步骤按发布日期重算"},
                ],
                "method": "五维加权：阅读30+互动25+榜单20+传播15+时效10，逐项见 breakdown",
            },
            "anatomy": {
                "wordCount": word_count,
                "paragraphs": paragraphs,
                "subheads": subheads,
                "images": images,
                "titlePattern": "",     # 由下方的规则标注
                "hook": desc[:120] if desc else "",
                "structure": [],
                "highlightSkills": [],
                "lessons": [],
            },
            "verification": {
                "status": "部分核实",
                "method": "Wechat2RSS 公开 RSS（源项目 ttttmr/Wechat2RSS）",
                "notes": "原文为 mp.weixin.qq.com 真实直链，正文/字数/图数来自 RSS 全文；阅读与互动数外部不可见，未取得上榜证据；仅作公众号文章形态基准，不冒充爆款。",
            },
            "tags": ["微信文章", "feed采集", "形态基准"],
            "_rawBody": body_clean[:1200],
        })
    return out


def guess_title_pattern(title):
    rules = [
        (r"\d", "数字+结果"),
        (r"[？?]", "痛点+反问"),
        (r"[！!]", "强情绪判断"),
        (r"为什么|为何|真相|原来", "悬念+揭秘"),
        (r"如何|怎么|攻略|指南|教程", "方法论承诺"),
        (r"我|我们|亲身|实测", "第一人称经历"),
    ]
    for pat, label in rules:
        if re.search(pat, title):
            return label
    return "热点借势+观点判断"


def freshness_points(pub, now):
    if not pub:
        return 0
    try:
        dt = datetime.fromisoformat(pub)
        days = (now - dt).days
        if days <= 1:
            return 10
        if days <= 7:
            return 6
        return 2
    except Exception:
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="只收近 N 天发布的文章，0 表示不限")
    ap.add_argument("--limit", type=int, default=2, help="每个公众号最多取几条")
    args = ap.parse_args()

    if not FEEDS_CONF.exists():
        print(f"[error] 缺少 {FEEDS_CONF}", file=sys.stderr)
        sys.exit(1)
    conf = json.loads(FEEDS_CONF.read_text(encoding="utf-8"))
    feeds = conf.get("feeds", [])
    if not feeds:
        print("[error] feed 列表为空", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone(timedelta(hours=8)))
    collected = []
    for f in feeds:
        name, url = f.get("name", ""), f.get("url", "")
        if not url:
            continue
        try:
            rows = parse_feed(url, name)
        except Exception as exc:
            print(f"[warn] {name}: {exc}")
            continue
        rows.sort(key=lambda r: r.get("publishedAt") or "", reverse=True)
        kept = 0
        for it in rows:
            if args.days > 0 and freshness_points(it.get("publishedAt"), now) == 0:
                continue
            # 字数区间过滤：超长深度长文(>5000)和纯通知(<300)都不当常规文章基准，避免拉偏中位数
            wc = it["anatomy"].get("wordCount") or 0
            if wc < 300 or wc > 5000:
                continue
            # 时效分回写
            fp = freshness_points(it.get("publishedAt"), now)
            it["viralScore"]["breakdown"][-1]["points"] = fp
            it["viralScore"]["breakdown"][-1]["note"] = (
                f"发布于 {it.get('publishedAt') or '未知'}，距采集 {fp and (str(fp)+' 分档') or '超期'}"
            )
            it["viralScore"]["total"] = sum(b["points"] for b in it["viralScore"]["breakdown"])
            it["anatomy"]["titlePattern"] = guess_title_pattern(it["title"])
            it.pop("_rawBody", None)
            collected.append(it)
            kept += 1
            if kept >= args.limit:
                break
        print(f"[ok] {name}: {len(rows)} 篇可解析，取 {kept}")

    INBOX.mkdir(parents=True, exist_ok=True)
    out = INBOX / f"wechat-feeds-{now.strftime('%Y%m%d')}.json"
    out.write_text(json.dumps(collected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 写入 {out.name}：{len(collected)} 条（全部 gzh-article，阅读数不可见）")


if __name__ == "__main__":
    main()
