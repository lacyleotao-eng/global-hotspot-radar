#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 11-23 成品稿的配图从「自制信息卡」换成豆包生成的 AI 示意图，并按形态控制张数。

豆包一次生成 3 张，同一选题两轮共 6 张（a 组主场景 + b 组细节），够 4 种形态各取所需。
caption 一律标明「AI 生成示意图，非新闻现场」，避免读者误认成现场照片。
"""
import json
from pathlib import Path

ROOT = Path("/Users/lee/WorkBuddy/hotspot-radar")
READY = ROOT / "data" / "ready"

POOLS = {
    "ai-server-price": [
        ("assets/images/ais-a-1.jpeg", "AI 生成示意图：深夜数据中心机房，成排服务器机柜（非新闻现场）"),
        ("assets/images/ais-a-2.jpeg", "AI 生成示意图：数据中心机柜走廊，指示灯密集闪烁"),
        ("assets/images/ais-a-3.jpeg", "AI 生成示意图：机房地面反光，冷蓝色调"),
        ("assets/images/ais-b-1.jpeg", "AI 生成示意图：服务器主板上的 GPU 加速卡特写"),
        ("assets/images/ais-b-2.jpeg", "AI 生成示意图：GPU 散热鳍片与金色触点，微距"),
        ("assets/images/ais-b-3.jpeg", "AI 生成示意图：服务器内部结构与冷白光源"),
    ],
    "margin-ratio": [
        ("assets/images/mgn-a-1.jpeg", "AI 生成示意图：证券营业部大厅的行情大屏（非新闻现场）"),
        ("assets/images/mgn-a-2.jpeg", "AI 生成示意图：营业部大厅，屏幕内容虚化不可辨"),
        ("assets/images/mgn-a-3.jpeg", "AI 生成示意图：营业部门口的行情屏与冷调灯光"),
        ("assets/images/mgn-b-1.jpeg", "AI 生成示意图：金融区写字楼幕墙映出行情光"),
        ("assets/images/mgn-b-2.jpeg", "AI 生成示意图：雨夜金融区街道，玻璃幕墙反光"),
        ("assets/images/mgn-b-3.jpeg", "AI 生成示意图：夜间写字楼群，红绿光斑虚化"),
    ],
    "orchard-livestream": [
        ("assets/images/orc-a-1.jpeg", "AI 生成示意图：秋日苹果园，果树成排（非新闻现场）"),
        ("assets/images/orc-a-2.jpeg", "AI 生成示意图：清晨薄雾中的果园与挂果枝条"),
        ("assets/images/orc-a-3.jpeg", "AI 生成示意图：果园地面与落果，侧逆光"),
        ("assets/images/orc-b-1.jpeg", "AI 生成示意图：果园里的直播三脚架与补光灯"),
        ("assets/images/orc-b-2.jpeg", "AI 生成示意图：手机支架与果树背景"),
        ("assets/images/orc-b-3.jpeg", "AI 生成示意图：田间地头的直播设备特写"),
    ],
    "property-fee": [
        ("assets/images/prf-a-1.jpeg", "AI 生成示意图：小区地下停车场入口道闸（非新闻现场）"),
        ("assets/images/prf-a-2.jpeg", "AI 生成示意图：地库坡道与减速带"),
        ("assets/images/prf-a-3.jpeg", "AI 生成示意图：地下车库日光灯照明与混凝土墙面"),
        ("assets/images/prf-b-1.jpeg", "AI 生成示意图：小区内部道路与单元门口"),
        ("assets/images/prf-b-2.jpeg", "AI 生成示意图：小区绿化带与电动车棚"),
        ("assets/images/prf-b-3.jpeg", "AI 生成示意图：住宅楼外立面与阴天光线"),
    ],
    "shenzhou-24": [
        ("assets/images/sz-a-1.jpeg", "AI 生成示意图：夜空下的发射塔架与火箭（非新闻现场）"),
        ("assets/images/sz-a-2.jpeg", "AI 生成示意图：塔架灯光与地面泛光"),
        ("assets/images/sz-a-3.jpeg", "AI 生成示意图：发射区远景，地平线微亮"),
        ("assets/images/sz-b-1.jpeg", "AI 生成示意图：航天器总装厂房内部"),
        ("assets/images/sz-b-2.jpeg", "AI 生成示意图：白色整流罩与银色舱段"),
        ("assets/images/sz-b-3.jpeg", "AI 生成示意图：洁净厂房的工业照明与地标线"),
    ],
}

# 各形态取图张数：文章要够撑结构，贴图要多，微头条一张封面即可
COUNT = {"gzh-article": 5, "gzh-poster": 6, "tt-article": 3, "tt-micro": 1}

IMG_NOTE = ("配图为豆包 Seedream 生成的 AI 示意图，不是新闻现场照片，画面中人物与场景均为生成，"
            "仅作版面配图；图中不含任何可读文字，事实与数字以来源报道为准。")

changed = 0
for slug, pool in POOLS.items():
    path = READY / f"2026-11-23-{slug}.json"
    if not path.exists():
        print("[miss]", path.name)
        continue
    if not all((ROOT / s).exists() for s, _ in pool):
        print("[skip] 图还没备齐:", slug)
        continue
    d = json.loads(path.read_text(encoding="utf-8"))
    for piece in d["pieces"]:
        n = COUNT.get(piece["id"], 2)
        picked = pool[:n]
        piece["images"] = [{"src": s, "caption": c} for s, c in picked]
        changed += 1
    d["imageNote"] = IMG_NOTE
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", path.name, [(p["id"], len(p["images"])) for p in d["pieces"]])

print("pieces updated:", changed)
