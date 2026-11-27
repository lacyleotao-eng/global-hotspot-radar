#!/usr/bin/env python3
"""汇总 data/yt-digest/* 里的视频拆解稿，生成站点用的索引。

产出：
  data/yt-digest/index.json   —— 供前端/脚本读取的清单
  data/yt-embed.js            —— window.__YT__，站点离线也能看

每篇拆解稿目录约定：
  meta.json     视频元信息 + category / categoryKey / guideTitle / dek / steps / images / cover
  article.html  正文（相对路径引 img/）
  img/          配图

用法：python3 scripts/yt_build_index.py
"""
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIGEST = ROOT / "data" / "yt-digest"


def count_steps(html: str) -> int:
    """正文里 <h2><span class="num">N</span> 的个数就是步骤数（含第 0 步结论）。"""
    return len(re.findall(r'<h2>\s*<span class="num"', html))


def count_images(html: str) -> int:
    return len(re.findall(r"<img\s", html))


def parse_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def build():
    docs = []
    for d in sorted(DIGEST.iterdir()):
        if not d.is_dir():
            continue
        art = d / "article.html"
        meta_path = d / "meta.json"
        if not art.exists():
            continue
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text("utf-8"))
            except Exception as e:
                print(f"[warn] {meta_path} 解析失败：{e}")
        html = art.read_text("utf-8")
        cover = meta.get("cover") or ""
        if not cover:
            m = re.search(r'<img[^>]+src="([^"]+)"', html)
            cover = m.group(1) if m else ""
        steps = meta.get("steps") or count_steps(html)
        images = meta.get("images") or count_images(html)
        docs.append({
            "slug": d.name,
            "url": f"data/yt-digest/{d.name}/article.html",
            "title": meta.get("guideTitle") or parse_title(html) or d.name,
            "dek": meta.get("dek", ""),
            "category": meta.get("category", "未分类"),
            "categoryKey": meta.get("categoryKey", "other"),
            "place": meta.get("city", ""),
            "channel": meta.get("channel", ""),
            "videoId": meta.get("id", ""),
            "videoUrl": meta.get("webpage", ""),
            "duration": meta.get("duration", 0),
            "views": meta.get("viewCount", 0),
            "publishedAt": meta.get("uploadDate", ""),
            "steps": steps,
            "images": images,
            "cover": f"data/yt-digest/{d.name}/{cover}" if cover else "",
            "digestAt": meta.get("digestAt", d.name[:10]),
        })

    docs.sort(key=lambda x: (x["digestAt"], x["slug"]), reverse=True)
    payload = {
        "updatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(docs),
        "docs": docs,
    }
    (DIGEST / "index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), "utf-8"
    )
    js = "/* 自动生成：scripts/yt_build_index.py */\nwindow.__YT__ = " + json.dumps(
        payload, ensure_ascii=False
    ) + ";\n"
    (ROOT / "data" / "yt-embed.js").write_text(js, "utf-8")
    print(f"[ok] {len(docs)} 篇 → data/yt-digest/index.json + data/yt-embed.js")
    for x in docs:
        print(f"  - {x['slug']}｜{x['category']}｜{x['steps']} 步｜{x['images']} 图")


if __name__ == "__main__":
    build()
