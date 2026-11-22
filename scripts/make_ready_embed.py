#!/usr/bin/env python3
"""把 data/ready/*.json 汇总成 data/ready-embed.js，供 file:// 本地预览读取。
线上站点由前端 fetch data/ready/index.json，二者内容一致。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "data" / "ready"
EMBED = ROOT / "data" / "ready-embed.js"
INDEX = READY / "index.json"


def main():
    files = sorted(READY.glob("*.json"))
    docs = []
    for f in files:
        if f.name == "index.json":
            continue
        try:
            docs.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"[warn] 跳过 {f.name}: {exc}")
    INDEX.write_text(json.dumps({"docs": docs}, ensure_ascii=False, indent=2), encoding="utf-8")
    EMBED.write_text(
        "window.__READY__=" + json.dumps({"docs": docs}, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    pieces = sum(len(d.get("pieces", [])) for d in docs)
    print(f"[done] {len(docs)} 套成品稿，共 {pieces} 个形态")


if __name__ == "__main__":
    main()
