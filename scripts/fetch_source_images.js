#!/usr/bin/env node
// 抓原文配图：用 ego 浏览器渲染文章页（头条/微信/澎湃等都要 JS），取真实图片并下载原图。
// 调用：ego-browser nodejs < scripts/fetch_source_images.js
//
// 输入 data/source-image-requests.json：
//   {"jobs":[{"slug":"property-fee","urls":["https://原文1","https://原文2"]}]}
// 输出：
//   图片落盘 assets/source/<slug>/raw-<n>.<ext>
//   data/source-image-raw.json  {"items":{"<slug>":[{"file","url","w","h","alt","from"}]}}
//
// 之后跑 python3 scripts/finalize_source_images.py 做尺寸/去重/拼图质检。
// 只抓「原文自己刊发的图」，不改图、不去水印；有平台水印或像素不够的交给质检环节淘汰。

const fs = await import("node:fs/promises");
const ROOT = "/Users/lee/WorkBuddy/hotspot-radar";
const REQ = ROOT + "/data/source-image-requests.json";
const OUT = ROOT + "/data/source-image-raw.json";
const SPACE = "原文配图抓取";
const MAX_PER_SLUG = 8;
const MIN_BYTES = 25000;

// 明显不是正文图的：图标、头像、二维码、分享按钮、emoji、广告位
const BAD = /(logo|icon|avatar|emoji|qrcode|qr-code|share|sprite|placeholder|loading|blank|1x1|\/statics\/|favicon)/i;

async function getSpace() {
  let entries = [];
  try { entries = await listTaskSpaces(); } catch (e) {}
  const entry = entries.find((s) => s.name === SPACE);
  if (!entry) return await taskSpace(SPACE, { profileId: "Default" });
  if (entry.ownership === "user") return await claimTaskSpace(entry.id);
  if (entry.ownership === "agentDelegatedToUser") return await takeOverTaskSpace(entry.id);
  return await taskSpace(entry.id);
}

// 在页面里挑正文图。
// 做法：不猜"正文容器"（头条/澎湃首页化改造后 class 天天变），改为逐图排除——
// 任何祖先带 feed / recommend / hot-list / sidebar / comment / banner 等标记的一律跳过，
// 再加上"渲染宽度 ≥280px"和"原图 ≥700px"，剩下的基本就是正文图。
async function collect(page) {
  return await page.evaluate(() => {
    const BAD_ANC = /(feed|recommend|related|hot[-_]?list|hotspot|rank|sidebar|side-bar|comment|advert|advertise|banner|footer|header|nav\b|toolbar|share|qrcode|popup|modal|search|login|download)/i;
    const BAD_SRC = /(logo|icon|avatar|emoji|qrcode|qr-code|share|sprite|placeholder|loading|blank|1x1|favicon|\/statics\/|mixern\.|adunit|\/ads?\/|advert)/i;
    const badAncestor = (img) => {
      let el = img.parentElement, n = 0;
      while (el && n < 12) {
        const tag = String(el.className || "") && typeof el.className === "string" ? el.className : "";
        const mark = tag + " " + (el.id || "");
        if (BAD_ANC.test(mark)) return true;
        el = el.parentElement; n++;
      }
      return false;
    };
    const out = [];
    const seen = new Set();
    const push = (url, w, h, alt, from, inLink) => {
      if (!url || !/^https?:/.test(url) || seen.has(url)) return;
      seen.add(url);
      out.push({ url, w: w || 0, h: h || 0, alt: alt || "", from: from || "img", inLink: !!inLink });
    };
    const pickSrcset = (s) => {
      const parts = String(s || "").split(",").map((x) => x.trim()).filter(Boolean);
      let best = "", bestW = 0;
      for (const p of parts) {
        const m = p.match(/^(\S+)\s+(\d+)w$/);
        if (m && Number(m[2]) > bestW) { bestW = Number(m[2]); best = m[1]; }
      }
      return best;
    };
    document.querySelectorAll('meta[property="og:image"],meta[name="twitter:image"]').forEach((m) => {
      const c = m.getAttribute("content");
      if (c) push(c, 0, 0, "", "meta");
    });
    // 2) 定位"正文段落簇"：把长度≥25字的 p 取出来，算它们的横向带与纵向范围。
    //    图片必须落在这个带里，否则就是侧栏 / 相关推荐 / 广告位（腾讯、新浪尤其多）。
    const ps = Array.from(document.querySelectorAll("p")).filter((el) => {
      const t = (el.innerText || "").trim();
      return t.length >= 25 && !badAncestor(el);
    });
    let band = null;
    if (ps.length >= 2) {
      const rs = ps.map((el) => el.getBoundingClientRect()).filter((r) => r.width > 120);
      if (rs.length >= 2) {
        const xs = rs.map((r) => r.left).sort((a, b) => a - b);
        const xe = rs.map((r) => r.right).sort((a, b) => a - b);
        const ys = rs.map((r) => r.top + window.scrollY).sort((a, b) => a - b);
        band = {
          left: xs[Math.floor(xs.length / 2)] - 90,
          right: xe[Math.floor(xe.length / 2)] + 130,
          // 纵向给足余量：正文图常出现在首段之前或末段之后很远（图集型文章）；
          // 真正需要拦的是"横向不在正文列"的侧栏/右栏广告。
          top: ys[0] - 1600,
          bottom: ys[ys.length - 1] + 2600,
        };
      }
    }
    const inBand = (r) => {
      if (!band) return true;
      const cy = r.top + window.scrollY;
      const inX = r.left >= band.left - 60 && r.left <= band.right - 40;
      return inX && cy >= band.top && cy <= band.bottom;
    };

    let scanned = 0, skipped = 0, outBand = 0;
    document.querySelectorAll("img").forEach((img) => {
      scanned += 1;
      const rect = img.getBoundingClientRect();
      const w = img.naturalWidth || img.width || 0;
      const h = img.naturalHeight || img.height || 0;
      const alt = (img.getAttribute("alt") || img.getAttribute("title") || "").trim();
      const ss = pickSrcset(img.getAttribute("srcset") || img.getAttribute("data-srcset"));
      const order = [
        ss, img.getAttribute("data-src"), img.getAttribute("data-original"),
        img.getAttribute("data-lazy-src"), img.getAttribute("data-actualsrc"),
        img.currentSrc, img.src,
      ].filter((v) => v && /^https?:/.test(v));
      if (!order.length || badAncestor(img) || (rect.width && rect.width < 280)) { skipped += 1; return; }
      if (!inBand(rect)) { outBand += 1; return; }
      const cand = order[0];
      if (BAD_SRC.test(cand)) { skipped += 1; return; }
      push(cand, w, h, alt.slice(0, 120), "img", !!img.closest("a"));
    });
    // 3) 域名归并：取封面图（og:image）的域名族为准，站外 CDN 的图基本是广告/推广位
    const fam = (u) => {
      try {
        const h = new URL(u).hostname.split(".");
        return h.slice(-2).join(".");
      } catch (e) { return ""; }
    };
    const metaImg = out.find((x) => x.from === "meta");
    const mine = metaImg ? fam(metaImg.url) : "";
    let offDomain = 0;
    const kept = mine
      ? out.filter((x) => { if (fam(x.url) === mine || x.from === "meta") return true; offDomain += 1; return false; })
      : out;
    return {
      scope: `图 ${scanned} 张：排除 ${skipped} 张（推荐流/小图/图标），正文带外 ${outBand} 张，站外域名 ${offDomain} 张，留 ${kept.length} 张`,
      list: kept,
    };
  });
}

async function download(url, absPath, referer) {
  const resp = await fetch(url, {
    headers: {
      Referer: referer || "https://www.toutiao.com/",
      "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
      Accept: "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    },
  });
  if (!resp.ok) throw new Error("HTTP " + resp.status);
  const buf = Buffer.from(await resp.arrayBuffer());
  if (buf.length < MIN_BYTES) throw new Error("too small " + buf.length);
  const ct = String(resp.headers.get("content-type") || "");
  const ext = /png/.test(ct) ? "png" : (/webp/.test(ct) ? "webp" : (/gif/.test(ct) ? "gif" : "jpeg"));
  const file = absPath + "." + ext;
  await fs.mkdir(absPath.substring(0, absPath.lastIndexOf("/")), { recursive: true });
  await fs.writeFile(file, buf);
  return { file: file.slice(ROOT.length + 1), bytes: buf.length };
}

const raw = JSON.parse(await fs.readFile(REQ, "utf-8"));
const jobs = raw.jobs || [];
const items = {};
const report = [];

const task = await getSpace();
const page = (await task.pages())[0] || await task.adopt((await task.tabs())[0].page);

for (const job of jobs) {
  const slug = job.slug;
  items[slug] = [];
  let n = 0; // 同一选题跨多个原文链接连续编号，避免互相覆盖
  for (const url of job.urls || []) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
      await page.waitForTimeout(3500);
      // 一直滚到底：微信/澎湃/头条的正文图都是懒加载，滚不到位就取不到
      let lastH = 0;
      for (let i = 0; i < 14; i++) {
        await page.evaluate(() => window.scrollBy(0, Math.round(window.innerHeight * 0.85)));
        await page.waitForTimeout(900);
        const h = await page.evaluate(() => document.body.scrollHeight);
        if (h === lastH && i > 3) break;
        lastH = h;
      }
      const got = await collect(page);
      const cands = got.list;
      report.push(`  正文容器：${got.scope}`);
      // 过滤 + 按面积取前 8
      const keep = cands
        .filter((c) => !BAD.test(c.url))
        .filter((c) => (c.w ? c.w >= 700 && c.h >= 320 : true))
        .filter((c) => { const r = c.w && c.h ? c.w / c.h : 1.6; return r > 0.5 && r < 3.0; })
        .sort((a, b) => b.w * b.h - a.w * a.h)
        .slice(0, MAX_PER_SLUG);
      report.push(`${slug} | ${url} → 候选 ${cands.length}，保留 ${keep.length}`);
      for (const c of keep) {
        try {
          n += 1;
          const got = await download(c.url, `${ROOT}/assets/source/${slug}/raw-${n}`, url);
          items[slug].push({ file: got.file, bytes: got.bytes, url: c.url, w: c.w, h: c.h, alt: c.alt, from: c.from, page: url });
        } catch (e) {
          n -= 1;
          report.push(`  下载失败 ${c.url.slice(0, 80)} → ${e.message}`);
        }
      }
    } catch (e) {
      report.push(`${slug} | ${url} 打开失败：${e.message}`);
    }
  }
}

await fs.writeFile(OUT, JSON.stringify({ updatedAt: new Date().toISOString(), items }, null, 2));
console.log(report.join("\n"));
console.log("[done] 落盘", Object.entries(items).map(([k, v]) => `${k}:${v.length}`).join(" "));
await task.finish({ keep: "all" });
