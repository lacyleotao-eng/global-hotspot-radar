#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把新生成的配图挂到对应成品稿上（幂等：按文件名去重，缺图跳过并告警）。"""
import json
import os

ROOT = "/Users/lee/WorkBuddy/hotspot-radar"

PLAN = {
    "2026-11-22-minimind.json": {
        "gzh-poster": [
            ("minimind-poster.jpeg", "封面：时间与成本压在神经网络上（AI 生成场景示意）"),
            ("minimind-poster-2.jpeg", "原文的硬件前提是单张消费级显卡（AI 生成场景示意）"),
            ("minimind-poster-3.jpeg", "它刻意把模型做得很小，才跑得这么快（AI 生成场景示意）"),
            ("minimind-poster-4.jpeg", "数据和流程才是训练真正的主体（AI 生成场景示意）"),
            ("minimind-poster-5.jpeg", "换个数据、改个参数，时间就不是那个时间（AI 生成场景示意）"),
            ("minimind-poster-6.jpeg", "3 元只算了租卡那一段，不含调试与重跑（AI 生成场景示意）"),
            ("minimind-poster-7.jpeg", "数字被转发的速度，远快于限定条件（AI 生成场景示意）"),
            ("minimind-poster-8.jpeg", "64M 与千亿参数，本就不是同一件事（AI 生成场景示意）"),
            ("minimind-poster-9.jpeg", "动手之前，先照着清单核一遍（AI 生成场景示意）"),
        ],
        "gzh-article": [
            ("minimind-article.jpeg", "开发者桌前的神经网络与代码（AI 生成场景示意）"),
            ("minimind-article-2.jpeg", "README 里写明的限定，比标题更长（AI 生成场景示意）"),
            ("minimind-poster-2.jpeg", "原文的硬件前提是单张消费级显卡（AI 生成场景示意）"),
            ("minimind-poster-6.jpeg", "3 元只覆盖租卡那一段，不含调试与重跑（AI 生成场景示意）"),
            ("minimind-poster-3.jpeg", "它刻意把模型做得很小，才跑得这么快（AI 生成场景示意）"),
            ("minimind-poster-8.jpeg", "64M 与千亿参数，本就不是同一件事（AI 生成场景示意）"),
        ],
    },
    "2026-11-22-downjacket.json": {
        "gzh-poster": [
            ("down-jacket-3.jpeg", "封面：货架更满、折扣更多（AI 生成场景示意）"),
            ("down-jacket-poster-2.jpeg", "上一季的货，还在仓库里等出清（AI 生成场景示意）"),
            ("down-jacket-poster-3.jpeg", "吊牌上的三个数，比促销语有用（AI 生成场景示意）"),
            ("down-jacket-poster-4.jpeg", "绒朵的蓬松程度，决定它撑不撑得住（AI 生成场景示意）"),
            ("down-jacket-poster-5.jpeg", "同款在不同渠道的价差，常比折扣更大（AI 生成场景示意）"),
            ("down-jacket-poster-6.jpeg", "洗护一次几十块，能多穿两年（AI 生成场景示意）"),
            ("down-jacket-poster-7.jpeg", "通勤件和极寒件，本来就该分两件买（AI 生成场景示意）"),
            ("down-jacket-poster-8.jpeg", "先比参数，再比价格，顺序别反（AI 生成场景示意）"),
            ("down-jacket-poster-9.jpeg", "冬天真正需要的是一件穿得住的外套（AI 生成场景示意）"),
        ],
        "gzh-article": [
            ("down-jacket-1.jpeg", "羽绒服货架与折扣标（AI 生成场景示意）"),
            ("down-jacket-2.jpeg", "秋冬服饰促销区（AI 生成场景示意）"),
            ("down-jacket-article-3.jpeg", "原料端的检验与称量，是成本的第一环（AI 生成场景示意）"),
            ("down-jacket-article-4.jpeg", "先盘家里已有的，往往能省下一笔（AI 生成场景示意）"),
            ("down-jacket-article-5.jpeg", "正确收纳，是延长寿命最有效的一步（AI 生成场景示意）"),
            ("down-jacket-article-6.jpeg", "同一件衣服，场景不同，要求完全不同（AI 生成场景示意）"),
        ],
    },
}

missing = []
for fname, per_piece in PLAN.items():
    path = os.path.join(ROOT, "data", "ready", fname)
    doc = json.load(open(path, encoding="utf-8"))
    for pc in doc.get("pieces", []):
        plan = per_piece.get(pc.get("id"))
        if not plan:
            continue
        imgs = []
        for src, cap in plan:
            rel = "assets/images/" + src
            full = os.path.join(ROOT, rel)
            if not os.path.exists(full) or os.path.getsize(full) < 20000:
                missing.append(src)
                continue
            imgs.append({"src": rel, "caption": cap})
        pc["images"] = imgs
        print(f"{fname} {pc['id']}: {len(imgs)} 图")
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

if missing:
    print("[warn] 缺图未挂：", ", ".join(sorted(set(missing))))
else:
    print("[ok] 全部配图已挂载")
