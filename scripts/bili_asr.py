#!/usr/bin/env python3
"""本地转写：视频/音频 → 带时间戳的分段文本（B 站拆解线的事实源）

为什么不用平台 AI 字幕：
  B 站 x/player/v2 返回的 ai-zh 字幕地址不稳定（实测约 40% 是别的视频），
  且即便命中，AI 字幕仍有错字。事实源优先本地 ASR，平台字幕只作参考。

用法：
  python3 scripts/bili_asr.py <媒体文件> <产出目录> [--lang zh] [--model small]

产出：
  <产出目录>/transcript.json  {"language": "zh", "duration": 310.4, "segments": [{start,end,text}]}
  <产出目录>/transcript.txt   "[00:00:04] 如何最快速的获取茄丁"

依赖：~/.wb-tools/whisper-venv（uv + faster-whisper）, ffmpeg
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import wave

VENV_PY = os.path.expanduser("~/.wb-tools/whisper-venv/bin/python")


def ensure_venv():
    """用 venv 解释器重跑自己，避免污染系统环境。"""
    if os.path.realpath(sys.executable) != os.path.realpath(VENV_PY) and os.path.exists(VENV_PY):
        os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])


def to_wav(src, dst):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", dst],
        check=True,
    )


def hms(sec):
    sec = max(0, int(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("outdir")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--model", default="small")
    args = ap.parse_args()

    import numpy as np
    # 模型缓存固定在 ~/.wb-tools/whisper-models，避免每次重新下载 461MB
    os.environ.setdefault("HF_HOME", os.path.expanduser("~/.wb-tools/whisper-models"))
    from faster_whisper import WhisperModel

    os.makedirs(args.outdir, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    to_wav(args.media, tmp.name)

    with wave.open(tmp.name, "rb") as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
        duration = w.getnframes() / float(sr)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        audio, language=args.lang, beam_size=5, vad_filter=True,
        initial_prompt="以下是普通话讲解，使用简体中文和标点。",
    )

    rows = []
    for s in segments:
        text = s.text.strip()
        if text:
            rows.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": text})

    with open(os.path.join(args.outdir, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump({"language": info.language, "duration": round(duration, 1), "segments": rows}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.outdir, "transcript.txt"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"[{hms(r['start'])}] {r['text']}\n")

    os.unlink(tmp.name)
    print(f"segments={len(rows)} duration={duration:.0f}s lang={info.language} -> {args.outdir}")


if __name__ == "__main__":
    ensure_venv()
    main()
