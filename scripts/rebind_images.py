#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把成品稿的配图绑定到豆包生成的图（data/image-map.json），按形态控制张数。

约定（05:40 出稿任务按这个来）：
  data/image-jobs.json 里每个选题写两轮，job.name = slug，prefix = assets/images/<slug>-a / -b。
  doubao_images.js 跑完会写 data/image-map.json（job.name → [{src, prompt}]）。
  本脚本按 slug 取图，自动生成「AI 生成示意图：<场景>（非新闻现场）」的图注。

用法:
    python3 scripts/rebind_images.py                # 今天的稿
    python3 scripts/rebind_images.py --date 2026-11-24
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "data" / "ready"
IMG_MAP = ROOT / "data" / "image-map.json"
SH = timezone(timedelta(hours=8))

# 形态 → 取图张数（对齐爆款中位数：公众号文章 5-6、贴图多图、头条文章 1 图、微头条 1 图）
COUNT = {"gzh-article": 5, "gzh-poster": 6, "tt-article": 1, "tt-micro": 1}

IMG_NOTE = ("配图为豆包 Seedream 生成的 AI 示意图，不是新闻现场照片，画面中人物与场景均为生成，"
            "仅作版面配图；图中不含可读文字，事实与数字以来源报道为准。")

# 去掉 prompt 里的摄影指令，只留场景，做图注
STRIP = re.compile(r"^(纪实摄影|摄影|微距摄影|夜景摄影)[:：]\s*")


def scene_of(prompt: str, limit: int = 34) -> str:
    t = STRIP.sub("", (prompt or "").strip())
    t = re.split(r"[，,]", t)[0]
    return t[:limit]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(SH).strftime("%Y-%m-%d"))
    date = ap.parse_args().date

    try:
        img_map = json.loads(IMG_MAP.read_text(encoding="utf-8")).get("items") or {}
    except Exception:
        print("[rebind] 没有 data/image-map.json，先跑 scripts/doubao_images.js")
        raise SystemExit(1)

    total = 0
    for path in sorted(READY.glob(f"{date}-*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        slug = d.get("slug") or path.stem.replace(f"{date}-", "")
        pool = img_map.get(slug) or img_map.get(path.stem.replace(f"{date}-", "")) or []
        if not pool:
            print(f"[skip] {path.name}：image-map 里没有 {slug} 的图")
            continue
        for piece in d.get("pieces") or []:
            n = COUNT.get(piece.get("id"), 2)
            # 图不够就循环取，保证每篇都有图；但同一篇内不重复同一张
            n = min(n, len(pool))
            picked = pool[:n]
            piece["images"] = [{
                "src": it["src"],
                "caption": "AI 生成示意图：" + scene_of(it.get("prompt")) + "（非新闻现场）",
            } for it in picked]
            total += 1
        d["imageNote"] = IMG_NOTE
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("[ok]", path.name, [(p["id"], len(p.get("images") or [])) for p in d.get("pieces") or []])

    print("pieces updated:", total)


if __name__ == "__main__":
    main()
