// B 站 AI 字幕抓取（带归属校验）
// 背景：api.bilibili.com/x/player/v2 返回的 ai-zh subtitle_url 不稳定，
//   实测同一请求连续 6 次：约 40% 是本视频、40% 是别的视频、20% 为空。
//   subtitle_url 路径形如 /bfs/ai_subtitle/prod/<aid><cid><hash>，可用 aid+cid 前缀校验归属。
// 用法：ego-browser nodejs < scripts/bili_subtitle.js
//   读取 /tmp/bili-sub-job.json：{"bvs":["BV...","BV..."],"out":"绝对路径.json"}
//   不提供 job 文件时使用下方 DEFAULT_BVS。
// 产出：每条视频 {bvid, title, duration, aid, cid, attempts, matchedUrl, lines[], verdict}
//   verdict: ok / no_subtitle / attribution_failed / empty
// 铁律：即使 verdict=ok，事实仍以本地 ASR 为准；字幕只作参考与校对。

const DEFAULT_BVS = ["BV15gZzYXE4N"];
const OUT_DEFAULT = "/Users/lee/WorkBuddy/hotspot-radar/data/bili-probe/subtitles.json";
const MAX_TRIES = 8;

let job = { bvs: DEFAULT_BVS, out: OUT_DEFAULT };
try {
  const fs = await import("node:fs/promises");
  job = JSON.parse(await fs.readFile("/tmp/bili-sub-job.json", "utf8"));
  if (!job.bvs || !job.bvs.length) job.bvs = DEFAULT_BVS;
  if (!job.out) job.out = OUT_DEFAULT;
} catch (e) {}

const task = await taskSpace("B站 字幕抓取");
const page = task.page("p1");
await page.goto(`https://www.bilibili.com/video/${job.bvs[0]}`, { waitUntil: "domcontentloaded", timeout: 90000 });
await page.waitForTimeout(3500);

const results = [];
for (const bv of job.bvs) {
  const rec = { bvid: bv, attempts: 0, verdict: "unknown" };
  try {
    if (!(await page.url()).includes(bv)) {
      await page.goto(`https://www.bilibili.com/video/${bv}`, { waitUntil: "domcontentloaded", timeout: 90000 });
      await page.waitForTimeout(3000);
    }
    const meta = await page.evaluate(async ({ bv }) => {
      const r = await (await fetch(`https://api.bilibili.com/x/web-interface/view?bvid=${bv}`, { credentials: "include" })).json();
      const d = r.data || {};
      return { code: r.code, aid: d.aid, cid: d.cid, title: d.title, duration: d.duration, owner: (d.owner || {}).name };
    }, { bv });
    Object.assign(rec, meta);
    if (!meta.aid || !meta.cid) { rec.verdict = "meta_failed"; results.push(rec); continue; }
    const own = String(meta.aid) + String(meta.cid);

    let url = "";
    const seen = { empty: 0, other: 0, noAuthPath: 0 };
    for (let i = 0; i < MAX_TRIES && !url; i++) {
      rec.attempts = i + 1;
      const u = await page.evaluate(async ({ aid, cid }) => {
        const j = await (await fetch(`https://api.bilibili.com/x/player/v2?aid=${aid}&cid=${cid}`, { credentials: "include" })).json();
        const subs = (((j.data || {}).subtitle || {}).subtitles) || [];
        const zh = subs.find(s => s.lan === "ai-zh") || subs.find(s => (s.lan || "").startsWith("zh")) || subs[0] || {};
        const raw = zh.subtitle_url || "";
        return raw ? (raw.startsWith("//") ? "https:" + raw : raw) : "";
      }, { aid: meta.aid, cid: meta.cid });
      if (!u) { seen.empty++; await page.waitForTimeout(1200); continue; }
      const m = u.match(/ai_subtitle\/prod\/(\d+)/) || u.match(/subtitle\/(\w+)\.json/);
      // 人工上传字幕（/bfs/subtitle/xxx.json）路径不含 aid，无从校验，直接视为不可信
      if (!/ai_subtitle\/prod\//.test(u)) { seen.noAuthPath++; await page.waitForTimeout(1200); continue; }
      if (!m || !m[1].startsWith(own)) { seen.other++; await page.waitForTimeout(1200); continue; }
      url = u;
    }
    rec.attemptStats = seen;

    if (!url) { rec.verdict = "attribution_failed"; results.push(rec); continue; }
    rec.matchedUrl = url.replace(/\?auth_key=.*$/, "") + "?auth_key=<redacted>";

    let text = "";
    try { text = await page.fetch(url); } catch (e) { rec.verdict = "fetch_failed"; rec.err = String(e).slice(0, 120); results.push(rec); continue; }
    // page.fetch 可能返回字符串，也可能返回 {ok,status,url,body} 包装对象
    let payload = text;
    if (payload && typeof payload === "object") payload = payload.body ?? payload.text ?? payload.data;
    let body = [];
    try {
      const parsed = typeof payload === "string" ? JSON.parse(payload) : payload;
      body = (parsed && parsed.body) || [];
    } catch (e) { rec.verdict = "parse_failed"; rec.head = String(payload).slice(0, 120); results.push(rec); continue; }
    rec.lines = body.length;
    rec.sample = body.slice(0, 3).map(x => ({ t: x.from, s: x.content }));
    rec.tail = body.slice(-1).map(x => ({ t: x.from, s: x.content }));
    rec.verdict = body.length ? "ok" : "empty";
  } catch (e) {
    rec.verdict = "error";
    rec.err = String(e).slice(0, 160);
  }
  results.push(rec);
  console.log(`[${rec.verdict}] ${bv} attempts=${rec.attempts} lines=${rec.lines || 0} | ${(rec.title || "").slice(0, 34)}`);
}

console.log("SUMMARY:", JSON.stringify(results.map(r => ({ bv: r.bvid, verdict: r.verdict, attempts: r.attempts, lines: r.lines || 0, first: (r.sample || [{}])[0].s })), null, 1));

try {
  const fs = await import("node:fs/promises");
  await fs.mkdir(job.out.replace(/\/[^/]+$/, ""), { recursive: true });
  await fs.writeFile(job.out, JSON.stringify({ generatedAt: new Date().toISOString(), note: "subtitle_url 已被 redact，仅留归属前缀供复核", results }, null, 2));
  console.log("WROTE:", job.out);
} catch (e) { console.log("WRITE_ERR:", String(e).slice(0, 120)); }
