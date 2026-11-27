// B 站取流 + 元信息 + 弹幕（一次跑完）
//
// 用法：
//   1) 写 /tmp/bili-fetch-job.json：
//      {"bvid":"BV15gZzYXE4N","video":"/tmp/bili_full.mp4","meta":"/tmp/bili-meta.json","danmaku":"/tmp/bili-danmaku.json"}
//   2) ego-browser nodejs < scripts/bili_fetch.js
//
// 为什么在浏览器里取流：playurl 的 durl 地址带签名、720p 需要登录态，必须在已登录页面内请求；
// 拿到地址后由 node 端下载（CDN 只校验 Referer，不校验 cookie）。
//
// 注意：page.evaluate 的第二个参数在本机 ego 版本里传不进去（实测拿到 undefined），
// 所以下面统一把变量内联进函数源码，再用字符串形式交给 evaluate。
const fs = await import("node:fs/promises");
const https = await import("node:https");

const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36";
const job = JSON.parse(await fs.readFile("/tmp/bili-fetch-job.json", "utf8"));
const bvid = job.bvid;
if (!bvid) throw new Error("job.bvid 为空");

const spaceName = job.space || "B站 取流";
// 空间已存在时不能再传 profileId，先按名字复用，没有再新建（新建才复用登录态）
const exist = (await listTaskSpaces()).find((s) => s.name === spaceName);
const task = exist ? await taskSpace(exist.id) : await taskSpace(spaceName, { profileId: "Default" });
const page = task.page("p1");
await page.goto(`https://www.bilibili.com/video/${bvid}`, { waitUntil: "domcontentloaded", timeout: 90000 });
await page.waitForTimeout(3500);
console.log("PAGE:", await page.url());

// 1) 元信息 + playurl 地址
const viewSrc = `(async () => {
  const BVID = ${JSON.stringify(bvid)};
  const j = async (u) => (await fetch(u, { credentials: "include" })).json();
  const v = await j("https://api.bilibili.com/x/web-interface/view?bvid=" + BVID);
  if (v.code !== 0) return { err: "view code=" + v.code + " " + (v.message || "") };
  const d = v.data;
  const pu = await j("https://api.bilibili.com/x/player/playurl?bvid=" + BVID + "&cid=" + d.cid + "&qn=80&fnval=1&fnver=0&fourk=1");
  const pd = pu.data || {};
  const durl = (pd.durl || [])[0] || null;
  return {
    meta: { bvid: d.bvid, aid: d.aid, cid: d.cid, title: d.title, desc: d.desc, pubdate: d.pubdate,
            duration: d.duration, owner: (d.owner || {}).name, mid: (d.owner || {}).mid,
            tname: d.tname, pic: d.pic, stat: d.stat,
            pages: (d.pages || []).map(function (p) { return { cid: p.cid, part: p.part }; }) },
    play: { code: pu.code, quality: pd.quality, accept: pd.accept_quality || [],
            url: durl ? durl.url : "", size: durl ? durl.size : 0, dash: !!pd.dash }
  };
})()`;
const info = await page.evaluate(viewSrc);
if (info.err) throw new Error(info.err);
console.log("TITLE:", info.meta.title);
console.log("PLAY: quality=" + info.play.quality + " size=" + (info.play.size / 1048576).toFixed(1) + "MB url=" + (info.play.url ? "ok" : "EMPTY"));
if (!info.play.url) {
  console.log("PLAY_RAW:", JSON.stringify(info.play));
  throw new Error("没拿到 durl（可能只有 DASH 或需要大会员）");
}

// 2) 下载（node 端，只带 Referer）
function download(url, dest, depth = 0) {
  return new Promise((resolve, reject) => {
    if (depth > 5) return reject(new Error("too many redirects"));
    const req = https.get(url, {
      headers: { "Referer": "https://www.bilibili.com/", "User-Agent": UA, "Range": "bytes=0-" },
    }, (res) => {
      const sc = res.statusCode;
      if (sc >= 300 && sc < 400 && res.headers.location) {
        res.resume();
        resolve(download(res.headers.location, dest, depth + 1));
        return;
      }
      if (sc !== 200 && sc !== 206) {
        res.resume();
        reject(new Error("HTTP " + sc));
        return;
      }
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", async () => {
        const buf = Buffer.concat(chunks);
        await fs.writeFile(dest, buf);
        resolve(buf.length);
      });
    });
    req.on("error", reject);
    req.setTimeout(240000, () => req.destroy(new Error("download timeout")));
  });
}
const bytes = await download(info.play.url, job.video);
console.log("VIDEO:", job.video, (bytes / 1048576).toFixed(1) + "MB");

// 3) 弹幕（zlib 压缩 XML，页面内解压）
let dan = { total: 0, top: [], sample: [] };
try {
  const danSrc = `(async () => {
    const CID = ${Number(info.meta.cid)};
    const r = await fetch("https://api.bilibili.com/x/v1/dm/list.so?oid=" + CID, { credentials: "include" });
    const buf = new Uint8Array(await r.arrayBuffer());
    let text = "";
    const fmts = ["deflate", "deflate-raw"];
    for (let i = 0; i < fmts.length; i++) {
      try {
        const ds = new DecompressionStream(fmts[i]);
        const stream = new Blob([buf]).stream().pipeThrough(ds);
        const t = await new Response(stream).text();
        if (t.indexOf("<d ") >= 0) { text = t; break; }
      } catch (e) {}
    }
    if (text.indexOf("<d ") < 0) {
      const dec = new TextDecoder().decode(buf);
      if (dec.indexOf("<d ") >= 0) text = dec;
    }
    const items = [];
    const re = /<d p="([^"]+)">([\\s\\S]*?)<\\/d>/g;
    let m;
    while ((m = re.exec(text))) items.push({ t: Number(m[1].split(",")[0]) || 0, text: m[2] });
    const freq = {};
    for (let i = 0; i < items.length; i++) {
      const k = (items[i].text || "").trim();
      if (k.length >= 2 && k.length <= 14) freq[k] = (freq[k] || 0) + 1;
    }
    const top = Object.entries(freq).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 40);
    return { total: items.length, top: top, sample: items.slice(0, 30) };
  })()`;
  dan = await page.evaluate(danSrc);
} catch (e) {
  console.log("DANMAKU_ERR:", String(e).slice(0, 160));
}
console.log("DANMAKU:", dan.total, "条");

await fs.writeFile(job.meta || "/tmp/bili-meta.json",
  JSON.stringify(Object.assign({}, info.meta, { play: info.play }), null, 1), "utf8");
await fs.writeFile(job.danmaku || "/tmp/bili-danmaku.json",
  JSON.stringify({ meta: info.meta, danmakuTotal: dan.total, top: dan.top, sample: dan.sample }, null, 1), "utf8");
console.log("WROTE:", job.meta || "/tmp/bili-meta.json", "|", job.danmaku || "/tmp/bili-danmaku.json");
