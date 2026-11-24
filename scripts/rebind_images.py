#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给成品稿绑配图，严格按优先级取图，并逐图记录来源。

优先级（用户定，2026-11-23）：
  1. 原文图     data/source-images/<slug>.json 里 approved 的图（原文自己刊发的照片/画面）
  2. 豆包       data/image-map.json（豆包 Seedream）
  3. ChatGPT    data/chatgpt-map.json
  4. 自制信息卡 data/card-specs/<slug>.json 对应的 assets/images/<slug>-*.jpeg

规则：
  - 一个形态要 N 张图时，先用原文图，不够再用 AI 图补；两者都不够才退回自制卡。
  - 不含水印、像素够的原文图优先；原文图被裁过（裁台标/字幕条）要在图注里说明。
  - 每张图写 origin（source|doubao|chatgpt|card），页面据此显示"原文图/AI 生成"。

用法:
    python3 scripts/rebind_images.py --date 2026-11-23
    python3 scripts/rebind_images.py --date 2026-11-23 --only property-fee
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "data" / "ready"
SRC_IMGS = ROOT / "data" / "source-images"
IMG_MAP = ROOT / "data" / "image-map.json"
CGPT_MAP = ROOT / "data" / "chatgpt-map.json"
CARDS = ROOT / "data" / "card-specs"
SH = timezone(timedelta(hours=8))

COUNT = {"gzh-article": 5, "gzh-poster": 6, "tt-article": 1, "tt-micro": 1}
STRIP = re.compile(r"^(纪实摄影|摄影|微距摄影|夜景摄影|插画|图片)[:：]\s*")
ORIGIN_LABEL = {"source": "原文图", "doubao": "豆包生成", "chatgpt": "ChatGPT 生成", "card": "自制信息卡"}


def scene_of(prompt: str, limit: int = 34) -> str:
    t = STRIP.sub("", (prompt or "").strip())
    return re.split(r"[，,]", t)[0][:limit]


def load_json(path: Path, key: str = "items") -> dict:
    try:
        return (json.loads(path.read_text(encoding="utf-8")).get(key) or {})
    except Exception:
        return {}


def platform_of(doc: dict) -> str:
    try:
        items = json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8")).get("items") or []
        for it in items:
            if it.get("id") == doc.get("sourceItemId"):
                return it.get("platform") or ""
    except Exception:
        pass
    return ""


def source_images(slug: str, doc: dict) -> list[dict]:
    """已批准的原文图。图注优先用文章里的 alt，其次用出处说明。"""
    try:
        d = json.loads((SRC_IMGS / f"{slug}.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    platform = doc.get("sourcePlatform") or platform_of(doc)
    out = []
    for it in d.get("approved") or []:
        alt = (it.get("alt") or "").strip()
        src_name = platform or "原文"
        cap = alt if len(alt) >= 6 else f"原文刊发的现场画面（图源：{src_name}）"
        if it.get("crop"):
            cap += "，已裁去台标/字幕条"
        out.append({"src": it["file"], "caption": cap, "origin": "source"})
    return out


def ai_images(pool: list[dict], tag: str) -> list[dict]:
    return [{
        "src": it["src"],
        "caption": f"AI 生成示意图：{scene_of(it.get('prompt'))}（{tag}，非新闻现场）",
        "origin": "doubao" if tag.startswith("豆包") else "chatgpt",
    } for it in pool]


AI_SUFFIX = re.compile(r"-(db|cg|c)-\d+\.jpe?g$", re.I)


def card_images(slug: str) -> list[dict]:
    """自制信息卡。必须排除 AI 生成图：豆包图叫 <slug>-db-1.jpeg、ChatGPT 图叫 <slug>-cg-1.jpeg，
    它们和卡住在同一个目录，只按 <slug>-*.jpeg 匹配会把 AI 图误判成自制卡，
    进而让整篇稿在 make_issue 里被当成"用卡凑数"排除掉。"""
    files = [f for f in sorted((ROOT / "assets" / "images").glob(f"{slug}-*.jpeg"))
             if not AI_SUFFIX.search(f.name)]
    return [{"src": str(f.relative_to(ROOT)), "caption": "自制信息卡（非新闻图片）", "origin": "card"} for f in files]


def pick(pool: list[dict], n: int) -> list[dict]:
    if not pool:
        return []
    if n <= len(pool):
        return pool[:n]
    out = list(pool)
    i = 0
    while len(out) < n:  # 不够就循环补，但同篇内尽量不重复
        out.append(pool[i % len(pool)])
        i += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(SH).strftime("%Y-%m-%d"))
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = {s.strip() for s in a.only.split(",") if s.strip()}

    doubao = load_json(IMG_MAP)
    chatgpt = load_json(CGPT_MAP)
    stats = {"source": 0, "doubao": 0, "chatgpt": 0, "card": 0}

    for path in sorted(READY.glob(f"{a.date}-*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        slug = d.get("slug") or path.stem.replace(f"{a.date}-", "")
        if only and slug not in only:
            continue

        src_pool = source_images(slug, d)
        db_pool = ai_images(doubao.get(slug) or [], "豆包 Seedream")
        cg_pool = ai_images(chatgpt.get(slug) or [], "ChatGPT")
        card_pool = card_images(slug)
        # 逐级兜底：原文图 + 豆包 拼一起 → 再不行加 ChatGPT → 最后自制卡
        ladder = [src_pool, db_pool, cg_pool, card_pool]

        for piece in d.get("pieces") or []:
            n = COUNT.get(piece.get("id"), 2)
            imgs: list[dict] = []
            for level in ladder:
                if len(imgs) >= n:
                    break
                imgs.extend(level)
            imgs = imgs[:n]
            for im in imgs:
                stats[im["origin"]] = stats.get(im["origin"], 0) + 1
            piece["images"] = imgs
            got = [ORIGIN_LABEL.get(i["origin"], "配图") for i in imgs]
            piece["imageNote"] = f"{len(imgs)} 张配图：" + "、".join(f"{k}{got.count(k)} 张" for k in dict.fromkeys(got))

        all_origin = {i["origin"] for p in d.get("pieces") or [] for i in (p.get("images") or [])}
        parts = []
        if "source" in all_origin:
            parts.append("原文图优先，已核对无水印/像素达标")
        if "doubao" in all_origin or "chatgpt" in all_origin:
            parts.append("原文图不足部分用 AI 生成示意图补足，非新闻现场")
        if "card" in all_origin:
            parts.append("含自制信息卡（非新闻图片）")
        d["imageNote"] = "；".join(parts) or d.get("imageNote") or ""
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("[ok]", path.name, [(p["id"], len(p.get("images") or []), p.get("imageNote")) for p in d.get("pieces") or []])

    print("[stats] " + "，".join(f"{ORIGIN_LABEL[k]} {v} 张" for k, v in stats.items() if v))


if __name__ == "__main__":
    main()
