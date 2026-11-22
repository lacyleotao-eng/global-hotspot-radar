#!/usr/bin/env python3
"""爆款参考库入库脚本。

输入: data/viral-inbox/*.json（JSON 数组，字段规范见 data/viral-schema.md）
输出:
  data/viral/items.json        去重后的爆款条目
  data/viral/meta.json         统计：形态分布/档位分布/信号来源分布
  data/viral/benchmark.json    对标报告：自家成品稿 vs 爆款中位数，逐形态给达标结论
  data/viral-embed.js          前端本地预览用的汇总（含上述三项）
"""
import json
import re
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "viral-inbox"
OUTDIR = ROOT / "data" / "viral"
READY = ROOT / "data" / "ready"
EMBED = ROOT / "data" / "viral-embed.js"

FORMS = {
    "gzh-article": ("微信公众号", "文章"),
    "gzh-poster": ("微信公众号", "贴图"),
    "tt-article": ("今日头条", "文章"),
    "tt-micro": ("今日头条", "微头条"),
}
TIERS = ["S", "A", "B", "C"]


def now_iso():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def norm_url(u):
    if not u:
        return ""
    u = str(u).strip().split("#")[0]
    u = re.sub(r"[?&](utm_\w+|share[_=]\w+|v=\w+|t=\d+)", "", u)
    return u.rstrip("/?")


def norm_title(t):
    return re.sub(r"[\s\W_]+", "", str(t or "")).lower()


def make_id(item):
    # 去重键带形态：同一 URL 的文章版与贴图版是两条不同的参考条目
    key = str(item.get("form", "")) + "|" + (norm_url(item.get("url")) or norm_title(item.get("title")))
    import hashlib
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def clamp_score(item):
    """校验/兜底 viralScore：缺 total 时按 breakdown 求和，缺 tier 时按 total 分档。"""
    vs = item.get("viralScore") or {}
    bd = vs.get("breakdown") or []
    if vs.get("total") is None and bd:
        vs["total"] = sum(int(b.get("points") or 0) for b in bd)
    total = int(vs.get("total") or 0)
    total = max(0, min(100, total))
    vs["total"] = total
    tier = vs.get("tier")
    if tier not in TIERS:
        tier = "S" if total >= 85 else ("A" if total >= 70 else ("B" if total >= 55 else "C"))
    vs["tier"] = tier
    vs.setdefault("method", "五维加权：阅读30+互动25+榜单20+传播15+时效10，逐项见 breakdown")
    item["viralScore"] = vs


def clean_item(raw):
    item = dict(raw)
    for k in ("title", "summary", "platform", "url", "category", "region"):
        item.setdefault(k, "")
    item.setdefault("form", "gzh-article")
    if item["form"] not in FORMS:
        item["form"] = "gzh-article"
    item.setdefault("account", "")
    item.setdefault("publishedAt", None)
    item.setdefault("collectedAt", now_iso())
    item.setdefault("tags", [])
    sig = item.get("signals") or {}
    sig = {k: sig.get(k, "不可见") for k in ("views", "likes", "comments", "shares", "favorites", "wow")}
    sig["source"] = (item.get("signals") or {}).get("source", "不可见")
    item["signals"] = sig
    item.setdefault("ranking", None)
    v = item.get("verification") or {}
    v.setdefault("status", "待核实")
    v.setdefault("method", "公开页面检索")
    v.setdefault("notes", "")
    item["verification"] = v
    ana = item.get("anatomy") or {}
    for k in ("wordCount", "paragraphs", "subheads", "images"):
        ana.setdefault(k, None)
    for k in ("titlePattern", "hook"):
        ana.setdefault(k, "")
    for k in ("structure", "highlightSkills", "lessons"):
        if not isinstance(ana.get(k), list):
            ana[k] = []
        ana[k] = [str(x) for x in ana[k]]
    item["anatomy"] = ana
    if not isinstance(item["tags"], list):
        item["tags"] = []
    clamp_score(item)
    item["id"] = make_id(item)
    # 派生：平台/形态中文名，前端直接用
    plat, form_cn = FORMS[item["form"]]
    item["platform"] = item["platform"] or plat
    item["formLabel"] = item["platform"] + " · " + form_cn
    return item


def build_benchmark(items):
    """对标报告：按形态取爆款字数/配图/小标题的中位数，与自家成品稿逐项比较。"""
    self_docs = []
    if READY.exists():
        for f in sorted(READY.glob("*.json")):
            if f.name == "index.json":
                continue
            try:
                self_docs.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass

    # 自家成品稿按形态归集（piece.target + piece.form -> 形态 key）
    def piece_form(piece):
        target = piece.get("target", "")
        form = piece.get("form", "")
        if target == "公众号" and "文章" in form:
            return "gzh-article"
        if target == "公众号" and ("贴图" in form or "图" in form):
            return "gzh-poster"
        if target == "今日头条" and "微头条" in form:
            return "tt-micro"
        if target == "今日头条":
            return "tt-article"
        return None

    def wc_of(piece):
        n = 0
        for b in piece.get("blocks", []):
            n += len(str(b.get("text") or ""))
            n += sum(len(str(x)) for x in (b.get("items") or []))
        return n

    self_by_form = {}
    for d in self_docs:
        for p in d.get("pieces", []):
            f = piece_form(p)
            if not f:
                continue
            self_by_form.setdefault(f, []).append({
                "title": p.get("title", ""),
                "wordCount": wc_of(p),
                "images": len(p.get("images") or []),
                "subheads": sum(1 for b in p.get("blocks", []) if b.get("type") == "h2"),
            })

    def median_of(rows, field, nested=None):
        def val(r):
            return (r.get(nested) or {}).get(field) if nested else r.get(field)
        vals = [val(r) for r in rows if isinstance(val(r), (int, float))]
        return round(statistics.median(vals), 1) if vals else None

    report = []
    for form in FORMS:
        viral_rows = [i for i in items if i["form"] == form]
        mine = self_by_form.get(form, [])
        vmw = median_of(viral_rows, "wordCount", nested="anatomy")
        vmi = median_of(viral_rows, "images", nested="anatomy")
        vms = median_of(viral_rows, "subheads", nested="anatomy")
        mmw = median_of(mine, "wordCount")
        mmi = median_of(mine, "images")
        mms = median_of(mine, "subheads")

        verdict = "待采样"
        if vmw and mmw:
            ratio = mmw / vmw
            if ratio >= 0.85:
                verdict = "字数达标"
            elif ratio >= 0.6:
                verdict = "字数偏少"
            else:
                verdict = "字数明显不足"
        elif not viral_rows:
            verdict = "爆款样本不足，暂无基准"
        elif not mine:
            verdict = "自家样例缺失"

        report.append({
            "form": form,
            "formLabel": FORMS[form][0] + " · " + FORMS[form][1],
            "viralSample": len(viral_rows),
            "selfSample": len(mine),
            "viral": {"wordCount": vmw, "images": vmi, "subheads": vms},
            "mine": {"wordCount": mmw, "images": mmi, "subheads": mms},
            "verdict": verdict,
            "advice": next((i["anatomy"]["lessons"][0] for i in viral_rows if i["anatomy"]["lessons"]), ""),
        })
    return report


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    files = sorted(INBOX.glob("*.json")) if INBOX.exists() else []
    seen = {}
    incoming = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[warn] 跳过 {f.name}: {exc}")
            continue
        rows = data if isinstance(data, list) else data.get("items", [])
        incoming += len(rows)
        for raw in rows:
            it = clean_item(raw)
            key = it["id"]
            if key in seen:
                # 重复条目：合并信号与来源标注，保留更完整的一条
                old = seen[key]
                if len(str(it.get("summary", ""))) > len(str(old.get("summary", ""))):
                    seen[key] = it
                continue
            seen[key] = it

    items = sorted(seen.values(), key=lambda x: (-x["viralScore"]["total"], x["collectedAt"]), reverse=False)
    # 重新按分数降序（上面的 sorted 已按 -total 升序，即总分降序；collectedAt 次级）
    items = sorted(seen.values(), key=lambda x: (-x["viralScore"]["total"], -_ts(x["collectedAt"])))

    by_form = {}
    by_tier = {t: 0 for t in TIERS}
    by_source = {}
    for i in items:
        by_form[i["form"]] = by_form.get(i["form"], 0) + 1
        by_tier[i["viralScore"]["tier"]] += 1
        src = i["signals"].get("source", "不可见")
        by_source[src] = by_source.get(src, 0) + 1

    meta = {
        "updatedAt": now_iso(),
        "total": len(items),
        "incoming": incoming,
        "byForm": by_form,
        "byTier": by_tier,
        "bySignalSource": by_source,
    }
    benchmark = build_benchmark(items)

    (OUTDIR / "items.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTDIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTDIR / "benchmark.json").write_text(json.dumps({"updatedAt": now_iso(), "rows": benchmark}, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {"items": items, "meta": meta, "benchmark": benchmark}
    EMBED.write_text("window.__VIRAL__=" + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")

    print(f"[done] 爆款 {len(items)} 条（读入 {incoming}），档位 {by_tier}")
    print(f"[done] 形态 {by_form}")
    for b in benchmark:
        print(f"  {b['formLabel']}: 爆款字中位 {b['viral']['wordCount']} / 自家 {b['mine']['wordCount']} → {b['verdict']}")


def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


if __name__ == "__main__":
    main()
