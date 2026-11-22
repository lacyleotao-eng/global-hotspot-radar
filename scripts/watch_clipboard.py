#!/usr/bin/env python3
"""微信「复制链接」剪贴板监听器 —— 用户复制，脚本自动解析入库。

【使用场景】
微信客户端里点开任意爆款文章/贴图 → 右键 →「复制链接」→ 本脚本自动捕获剪贴板里的
mp.weixin.qq.com 链接，立刻调用 fetch_wechat_url 解析，写入 data/viral-inbox 并合并到爆款库。
用户只需连续复制，不用把链接手动发给我，也不用我抢占鼠标键盘（那是不可靠的共享桌面操作）。

【为什么这样设计】
- 实测：微信右键「复制链接」会把真实 mp.weixin.qq.com/s/xxx 直链写入系统剪贴板，稳定可靠。
- 实测：computer-use 后台投递键盘/鼠标到微信不稳定，且用户会实时接管桌面，抢占不可行。
- 所以把「采集」这一步交给人（用户本来就要在微信里翻），把「解析+结构化+入库」交给脚本。

用法：
  python3 scripts/watch_clipboard.py                 # 持续监听，Ctrl+C 停止
  python3 scripts/watch_clipboard.py --once          # 只处理当前剪贴板里的链接（一次性）
  python3 scripts/watch_clipboard.py --interval 0.8  # 轮询间隔秒
每条捕获的链接会：解析 → 写入 wechat-clip-YYYYMMDD.json → 调用 ingest_viral.py 合并。
重复链接自动跳过（按 URL 去重）。
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "viral-inbox"
SEEN_FILE = ROOT / "data" / "clip-seen.json"
FETCH = ROOT / "scripts" / "fetch_wechat_url.py"
INGEST = ROOT / "scripts" / "ingest_viral.py"
PY = sys.executable


def now_cst():
    return datetime.now(timezone(timedelta(hours=8)))


def read_clipboard():
    try:
        return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")


def process(url, engagement=None, engagement_source=None):
    """解析单条链接，追加到当天 inbox，返回是否成功。"""
    cmd = [PY, str(FETCH), "--url", url,
           "--out", f"data/viral-inbox/wechat-clip-{now_cst().strftime('%Y%m%d')}.json"]
    if engagement:
        cmd += ["--engagement", json.dumps(engagement, ensure_ascii=False)]
    if engagement_source:
        cmd += ["--engagement-source", engagement_source]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=90)
    out = (r.stdout + r.stderr).strip()
    print(out, flush=True)
    return "[ok]" in out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="只处理当前剪贴板一次")
    ap.add_argument("--interval", type=float, default=0.8, help="轮询间隔秒")
    ap.add_argument("--no-ingest", action="store_true", help="只写 inbox，不合并到爆款库")
    ap.add_argument("--engagement", help="互动数 JSON（所有捕获链接共用，慎用）")
    ap.add_argument("--engagement-source", help="互动数来源说明")
    args = ap.parse_args()

    seen = load_seen()
    last = read_clipboard()
    if args.once:
        if "mp.weixin.qq.com/s/" in last and last not in seen:
            print(f"[capture] {last[:90]}")
            if process(last, json.loads(args.engagement) if args.engagement else None,
                       args.engagement_source):
                seen.add(last)
                save_seen(seen)
                if not args.no_ingest:
                    subprocess.run([PY, str(INGEST)], cwd=str(ROOT))
        else:
            print("[info] 剪贴板没有新的微信链接")
        return

    print(f"[watch] 监听剪贴板，间隔 {args.interval}s。在微信里右键「复制链接」即可自动入库。Ctrl+C 停止。", flush=True)
    try:
        while True:
            cur = read_clipboard()
            if cur != last:
                last = cur
                if "mp.weixin.qq.com/s/" in cur and cur not in seen:
                    print(f"\n[capture] {now_cst().strftime('%H:%M:%S')} {cur[:90]}", flush=True)
                    if process(cur, json.loads(args.engagement) if args.engagement else None,
                               args.engagement_source):
                        seen.add(cur)
                        save_seen(seen)
                        if not args.no_ingest:
                            r = subprocess.run([PY, str(INGEST)], capture_output=True, text=True,
                                               cwd=str(ROOT), timeout=90)
                            print((r.stdout or "").strip()[:400], flush=True)
                    else:
                        print("[warn] 解析失败，未入库", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[stop] 监听已停止", flush=True)


if __name__ == "__main__":
    main()
