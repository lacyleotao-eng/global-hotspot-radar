#!/usr/bin/env python3
"""把 YouTube 视频拆成「结构化文字」，供二次创作或攻略改写。

为什么需要它：视频里的信息密度很高（价格、时间、门牌、口播经验），
但模型不能直接"看"视频。字幕是唯一便宜且可核验的入口：
字幕带时间戳，写文章时每一句都能回到"第几分第几秒"，避免编造。

两条前置条件（缺一不可）：
1. 视频有字幕轨（人工字幕或自动字幕均可）。没有就只能下音频做 ASR，走另一条路。
2. yt-dlp 需要 cookie：YouTube 对无 cookie 的请求返回 "Sign in to confirm you're not a bot"。
   cookie 从 ego 浏览器导出（脚本 scripts/yt_export_cookies.js）：
       ego-browser nodejs < scripts/yt_export_cookies.js
   得到 /tmp/yt_cookies.txt 后再跑本脚本。

用法：
    python3 scripts/yt_transcript.py --url "https://www.youtube.com/watch?v=XXXX" \
        --cookies /tmp/yt_cookies.txt --out data/yt-digest/YYYY-MM-DD-<slug>

输出（--out 目录下）：
    meta.json        标题/频道/时长/观看数/发布日期/描述/章节
    transcript.txt   带时间戳的逐句字幕（[00:12:31] 文本）
    transcript.json  同上，结构化
    subs/*.vtt       原始字幕

注意：-f sb0 不是笔误。很多视频在当前客户端只返回 storyboard 格式，
yt-dlp 会因为"没有可下载格式"在取字幕前就报错，指定 sb0 可绕过。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[\u4e00-\u9fff]")


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def fetch_meta(url: str, cookies: str | None) -> dict:
    cmd = ["yt-dlp", "--no-warnings", "-f", "sb0", "--skip-download", "--dump-single-json", url]
    if cookies:
        cmd[1:1] = ["--cookies", cookies]
    code, out = run(cmd)
    if code != 0:
        raise SystemExit(f"[fail] 取元数据失败：{out.strip()[-300:]}")
    d = json.loads(out.strip().splitlines()[-1])
    return {
        "id": d.get("id"),
        "title": d.get("title"),
        "channel": d.get("channel") or d.get("uploader"),
        "duration": d.get("duration"),
        "viewCount": d.get("view_count"),
        "uploadDate": d.get("upload_date"),
        "description": d.get("description") or "",
        "chapters": [{"start": c.get("start_time"), "title": c.get("title")} for c in (d.get("chapters") or [])],
        "language": d.get("language") or "",
        "subLangs": sorted((d.get("subtitles") or {}).keys()),
        "autoLangs": sorted((d.get("automatic_captions") or {}).keys())[:20],
        "webpage": d.get("webpage_url") or url,
    }


def candidate_langs(meta: dict, override: str) -> list[str]:
    """按「人工轨 → 原语言自动轨 → 英文」排优先级，逐个试。

    坑：以前默认 `yue,zh-Hans,zh-Hant,zh,en` 一起要，YouTube 会为缺失语言现场做机器翻译，
    翻译轨端点会被 429 限流，整条指令直接失败。现在一次只要一种语言，且优先原轨。
    """
    if override:
        return [x.strip() for x in override.split(",") if x.strip()]
    man = meta.get("subLangs") or []
    auto = meta.get("autoLangs") or []
    orig = (meta.get("language") or "").split("-")[0].lower()
    out: list[str] = []
    out += man[:2]
    if orig:
        for a in auto:
            al = a.lower()
            if al == orig or al.startswith(orig + "-"):
                out.append(a)
                break
    if "en" in auto:
        out.append("en")
    out += [a for a in auto if a.lower().startswith("zh")][:2]
    if not out:
        out = ["en"]
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def fetch_subs(url: str, cookies: str | None, langs: str, out_dir: Path) -> list[Path]:
    sub = out_dir / "subs"
    sub.mkdir(parents=True, exist_ok=True)
    cmd = ["yt-dlp", "--no-warnings", "-f", "sb0", "--write-subs", "--write-auto-subs",
           "--sub-langs", langs, "--sub-format", "vtt", "--skip-download",
           "-o", str(sub / "%(id)s.%(ext)s"), url]
    if cookies:
        cmd[1:1] = ["--cookies", cookies]
    code, out = run(cmd)
    if code != 0 and "Requested format" in out:
        raise SystemExit("[fail] 该视频没有可下载的字幕轨，需改用音频转写（AudioTranscribe）")
    files = sorted(sub.glob("*.vtt"))
    if not files:
        raise SystemExit(f"[fail] 没下到字幕：{out.strip()[-300:]}")
    return files


def parse_vtt(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    rows = []
    for block in re.split(r"\n{2,}", raw):
        lines = [l for l in block.split("\n") if l.strip()]
        i = next((k for k, l in enumerate(lines) if "-->" in l), None)
        if i is None:
            continue
        start = lines[i].split("-->")[0].strip().split(".")[0]
        text = re.sub(r"<[^>]+>", "", " ".join(lines[i + 1:])).strip()
        if text:
            rows.append({"t": start, "text": text})
    # 自动字幕会重复上一行，做一次相邻去重
    dedup = []
    for r in rows:
        if dedup and r["text"] == dedup[-1]["text"]:
            continue
        dedup.append(r)
    return dedup


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--cookies", default="")
    ap.add_argument("--langs", default="yue,zh-Hans,zh-Hant,zh,en")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    meta = fetch_meta(a.url, a.cookies or None)
    out_dir = Path(a.out) if a.out else ROOT / "data" / "yt-digest" / (meta["id"] or "video")
    out_dir.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    last_err = ""
    for lang in candidate_langs(meta, a.langs):
        try:
            files = fetch_subs(a.url, a.cookies or None, lang, out_dir)
            if files:
                print(f"[subs] 命中语言轨：{lang}")
                break
        except SystemExit as e:
            last_err = str(e)
            print(f"[subs] {lang} 失败：{last_err[:120]}")
        if "Requested format" in last_err:
            break
    if not files:
        raise SystemExit(f"[fail] 所有语言轨都没拿到：{last_err[:300]}")
    # 优先人工字幕：文件名里含 yue/zh 且不带 .auto
    rows, used = [], None
    for f in files:
        r = parse_vtt(f)
        if len(r) > len(rows):
            rows, used = r, f.name

    text_all = "".join(x["text"] for x in rows)
    meta["cjk"] = len(CJK.findall(text_all))
    meta["segments"] = len(rows)
    meta["usedSubtitle"] = used
    meta["fetchedAt"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")

    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "transcript.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "transcript.txt").write_text(
        "\n".join(f'[{x["t"]}] {x["text"]}' for x in rows), encoding="utf-8")

    print(f"标题：{meta['title']}")
    print(f"频道：{meta['channel']} ｜ 时长 {meta['duration']} 秒 ｜ 观看 {meta['viewCount']}")
    print(f"字幕：{used} ｜ 句段 {meta['segments']} ｜ 汉字 {meta['cjk']}")
    if meta["chapters"]:
        print("章节：")
        for c in meta["chapters"][:12]:
            print(f"  {c['start']} {c['title']}")
    print(f"输出：{out_dir}")


if __name__ == "__main__":
    main()
