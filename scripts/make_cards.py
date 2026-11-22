#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自制信息卡渲染器：把卡片规格渲染成 1080x1440 的 JPEG，用作成品稿配图。

用法：
    python3 scripts/make_cards.py data/card-specs/<name>.json

规格文件格式：
{
  "prefix": "riemann-card",
  "cards": [
    {"kind": "cover",  "theme": "dark",  "kicker": "…", "title": "…", "sub": "…"},
    {"kind": "stat",   "theme": "light", "kicker": "…", "value": "25", "unit": "万页", "label": "…", "sub": "…"},
    {"kind": "steps",  "theme": "dark",  "kicker": "…", "title": "…", "items": ["…", "…"]},
    {"kind": "points", "theme": "light", "kicker": "…", "title": "…", "items": ["…", "…"]},
    {"kind": "list",   "theme": "dark",  "kicker": "…", "title": "…", "items": ["…", "…"]},
    {"kind": "closing","theme": "accent","kicker": "…", "title": "…", "sub": "…"}
  ]
}
输出：assets/images/{prefix}-{序号}.jpeg，并打印每张的字节数。
"""
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "images"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1080, 1440

THEMES = {
    "dark": {"bg": "#0b1220", "ink": "#eef3fb", "muted": "#93a4bf", "accent": "#5eead4", "line": "rgba(255,255,255,.14)", "chip": "rgba(94,234,212,.12)"},
    "light": {"bg": "#f6f8fc", "ink": "#0f172a", "muted": "#5b6b85", "accent": "#0f766e", "line": "rgba(15,23,42,.12)", "chip": "rgba(15,118,110,.09)"},
    "accent": {"bg": "#0f766e", "ink": "#f0fdfa", "muted": "rgba(240,253,250,.78)", "accent": "#bbf7e8", "line": "rgba(255,255,255,.22)", "chip": "rgba(255,255,255,.14)"},
}

BASE_CSS = """
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
html,body{margin:0;padding:0;width:%(w)dpx;height:%(h)dpx}
body{background:%(bg)s;color:%(ink)s;font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.frame{width:%(w)dpx;height:%(h)dpx;padding:88px 84px 76px;display:flex;flex-direction:column;justify-content:space-between}
.top{display:flex;justify-content:space-between;align-items:center}
.brand{font-size:20px;letter-spacing:.16em;color:%(muted)s}
.idx{font-size:20px;letter-spacing:.1em;color:%(muted)s}
.kicker{align-self:flex-start;display:inline-block;font-size:21px;letter-spacing:.26em;color:%(accent)s;background:%(chip)s;
        padding:9px 16px;border-radius:8px;font-weight:600}
h1{font-size:74px;line-height:1.24;margin:34px 0 0;font-weight:800;letter-spacing:-.5px}
h1.sm{font-size:60px;line-height:1.34}
.sub{font-size:29px;line-height:1.68;color:%(muted)s;margin:26px 0 0;font-weight:400}
.body{display:flex;flex-direction:column;justify-content:center;flex:1;padding:40px 0 30px}
.value{font-size:210px;line-height:.96;font-weight:800;letter-spacing:-6px;color:%(accent)s;
       display:flex;align-items:baseline;gap:14px}
.value .unit{font-size:60px;font-weight:700;letter-spacing:0}
.label{font-size:35px;line-height:1.5;margin-top:26px;font-weight:600;max-width:880px}
.foot{border-top:1px solid %(line)s;padding-top:22px;display:flex;justify-content:space-between;gap:24px;
      font-size:19px;line-height:1.55;color:%(muted)s}
.foot .src{max-width:760px}
.items{display:flex;flex-direction:column;gap:22px;margin-top:34px}
.item{display:flex;gap:20px;align-items:flex-start;font-size:30px;line-height:1.62}
.item .n{flex:none;width:52px;height:52px;border-radius:14px;background:%(chip)s;color:%(accent)s;
         font-size:24px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:3px}
.item .t{flex:1}
.steps{display:flex;flex-direction:column;gap:18px;margin-top:34px}
.step{display:flex;gap:22px;align-items:flex-start;background:%(chip)s;border-radius:16px;padding:26px 28px}
.step .sn{flex:none;font-size:26px;font-weight:800;color:%(accent)s;min-width:52px}
.step .st{font-size:29px;line-height:1.55}
""" % {"w": W, "h": H, "bg": "%(bg)s", "ink": "%(ink)s", "muted": "%(muted)s",
       "accent": "%(accent)s", "chip": "%(chip)s", "line": "%(line)s"}


def esc(s):
    return html.escape(str(s or ""))


def card_html(card, idx, total):
    th = THEMES.get(card.get("theme") or "dark", THEMES["dark"])
    css = BASE_CSS % th
    kind = card.get("kind") or "points"
    kicker = card.get("kicker") or ""
    title = card.get("title") or ""
    sub = card.get("sub") or ""
    items = card.get("items") or []
    source = card.get("source") or ""

    inner = ""
    if kind == "cover":
        cls = "sm" if len(title) > 22 else ""
        inner = (
            '<div class="kicker">%s</div><h1 class="%s">%s</h1>%s'
            % (esc(kicker), cls, esc(title), ('<p class="sub">%s</p>' % esc(sub)) if sub else "")
        )
    elif kind == "stat":
        inner = (
            '<div class="kicker">%s</div>'
            '<div class="value">%s<span class="unit">%s</span></div>'
            '<div class="label">%s</div>%s'
            % (esc(kicker), esc(card.get("value")), esc(card.get("unit")),
               esc(card.get("label")), ('<p class="sub">%s</p>' % esc(sub)) if sub else "")
        )
    elif kind in ("steps", "points", "list"):
        rows = []
        for i, it in enumerate(items, 1):
            if kind == "steps":
                rows.append('<div class="step"><div class="sn">%02d</div><div class="st">%s</div></div>' % (i, esc(it)))
            else:
                rows.append('<div class="item"><div class="n">%d</div><div class="t">%s</div></div>' % (i, esc(it)))
        cls = "sm" if len(title) > 18 else ""
        wrap = "steps" if kind == "steps" else "items"
        inner = '<div><div class="kicker">%s</div><h1 class="%s">%s</h1><div class="%s">%s</div></div>' % (
            esc(kicker), cls, esc(title), wrap, "".join(rows))
    elif kind == "closing":
        inner = '<h1>%s</h1>%s' % (esc(title), ('<p class="sub">%s</p>' % esc(sub)) if sub else "")
    else:
        inner = '<h1>%s</h1>' % esc(title)

    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>'
        '<div class="frame">'
        '<div class="top"><div class="brand">全球热点情报站 · 自制信息卡</div><div class="idx">%02d / %02d</div></div>'
        '<div class="body">%s</div>'
        '<div class="foot"><div class="src">%s</div><div>%s</div></div>'
        '</div></body></html>'
        % (css, idx, total, inner, esc(source), esc(card.get("footer") or "不构成结论，仅整理公开信息"))
    )


def render(spec_path):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    prefix = spec["prefix"]
    cards = spec["cards"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="cards-"))
    ok = 0
    for i, card in enumerate(cards, 1):
        page = tmp / ("%02d.html" % i)
        page.write_text(card_html(card, i, len(cards)), encoding="utf-8")
        png = tmp / ("%02d.png" % i)
        out = OUT_DIR / ("%s-%d.jpeg" % (prefix, i))
        profile = tmp / ("profile-%02d" % i)
        cmd = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
               "--force-device-scale-factor=1", "--user-data-dir=%s" % profile,
               "--window-size=%d,%d" % (W, H), "--screenshot=%s" % png, page.as_uri()]
        subprocess.run(cmd, capture_output=True, timeout=90)
        if not png.exists() or png.stat().st_size < 8000:
            print("[fail] %s 渲染失败" % out.name)
            continue
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82",
                        str(png), "--out", str(out)], capture_output=True)
        if out.exists():
            ok += 1
            print("[ok] %s %dKB" % (out.name, out.stat().st_size // 1024))
        else:
            print("[fail] %s 转码失败" % out.name)
    shutil.rmtree(tmp, ignore_errors=True)
    print("[done] %d / %d" % (ok, len(cards)))
    return 0 if ok == len(cards) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(render(sys.argv[1]))
