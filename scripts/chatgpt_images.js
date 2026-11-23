#!/usr/bin/env node
// 用 ego 浏览器驱动 ChatGPT 生成配图并下载到本地（豆包额度用完时的第二顺位）。
// 调用：ego-browser nodejs < scripts/chatgpt_images.js
//
// 输入 data/chatgpt-jobs.json（与豆包同格式）：
//   {"jobs":[{"name":"slug","prompt":"...","prefix":"assets/images/xxx","count":2}]}
// 输出：data/chatgpt-results.json {"results":[{name,ok,outs,bytes,error}]}
//   并写 data/chatgpt-map.json {"items":{slug:[{src,prompt}]}} 供 rebind_images.py 取用
//
// 注意：ChatGPT 一次只出一张，count>1 表示在同一会话里追加"换构图再来一张"，
// 因此 count 别开太大（每张 30-60 秒），一般 2-3 张够用。

const fs = await import("node:fs/promises");
const ROOT = "/Users/lee/WorkBuddy/hotspot-radar";
const JOBS = ROOT + "/data/chatgpt-jobs.json";
const MAP = ROOT + "/data/chatgpt-map.json";
const RESULT = ROOT + "/data/chatgpt-results.json"; // 结果单独落盘，别覆盖 jobs（覆盖会让下次跑空）
const SPACE = "ChatGPT 配图自动化";
const GEN_TIMEOUT = 200000;
const MIN_BYTES = 40000;

async function getSpace() {
  let entries = [];
  try { entries = await listTaskSpaces(); } catch (e) {}
  const entry = entries.find((s) => s.name === SPACE);
  if (!entry) return await taskSpace(SPACE, { profileId: "Default" });
  if (entry.ownership === "user") return await claimTaskSpace(entry.id);
  if (entry.ownership === "agentDelegatedToUser") return await takeOverTaskSpace(entry.id);
  return await taskSpace(entry.id);
}

// 页面里已渲染出的生成图。ChatGPT 用 <button data-testid="generated-image-preview"><img src="blob:...">
// 图片是 blob，外面拿不到，只能在页面里 fetch 回来。
async function grab(page) {
  return await page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll('[data-testid="generated-image-preview"] img, img[alt*="已生成"], img[alt*="Generated"]'));
    return nodes.map((img) => ({
      src: img.currentSrc || img.src || "",
      w: img.naturalWidth || 0,
      h: img.naturalHeight || 0,
      alt: img.alt || "",
      key: (img.getAttribute("alt") || "") + "|" + (img.naturalWidth || 0) + "|" + String(img.src).slice(-24),
    }));
  });
}

// blob → base64（页面内取字节），再在 node 侧落盘
async function saveBlob(page, src, outPath) {
  const b64 = await page.evaluate(async (url) => {
    const r = await fetch(url);
    const buf = await r.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let s = "";
    const CH = 0x8000;
    for (let i = 0; i < bytes.length; i += CH) s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    return btoa(s);
  }, src);
  if (!b64 || b64.length < 1000) throw new Error("取图失败");
  const buf = Buffer.from(b64, "base64");
  if (buf.length < MIN_BYTES) throw new Error("图太小 " + buf.length);
  const abs = ROOT + "/" + String(outPath).replace(/^\/+/, "");
  await fs.mkdir(abs.substring(0, abs.lastIndexOf("/")), { recursive: true });
  await fs.writeFile(abs, buf);
  return buf.length;
}

const COMPOSER = '#prompt-textarea, div[contenteditable="true"], textarea[placeholder], textarea';

async function waitComposer(page, timeout) {
  try {
    await page.waitForSelector(COMPOSER, { state: "visible", timeout });
    return true;
  } catch (e) {
    return false;
  }
}

async function send(page, text) {
  await page.fill(COMPOSER, text);
  await page.waitForTimeout(500);
  try {
    await page.click('[data-testid="send-button"]', { timeout: 4000 });
  } catch (e) {
    await page.press(COMPOSER, "Enter");
  }
}

// 等新图出现：比 before 数量多，且已加载完成
async function waitNew(page, beforeKeys, timeout) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    await page.waitForTimeout(4000);
    const now = await grab(page);
    const fresh = now.filter((n) => !beforeKeys.has(n.key) && n.w >= 480 && /^blob:|^https:/.test(n.src));
    if (fresh.length) return fresh;
  }
  return [];
}

const raw = JSON.parse(await fs.readFile(JOBS, "utf-8"));
const jobs = Array.isArray(raw) ? raw : (raw.jobs || []);
const results = [];
const mapItems = {};

try {
  const task = await getSpace();
  const page = (await task.pages())[0] || await task.adopt((await task.tabs())[0].page);
  await page.goto("https://chatgpt.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
  if (!(await waitComposer(page, 25000))) throw new Error("找不到输入框：可能未登录，或页面没加载完（profile Default）");

  for (const job of jobs) {
    const prefix = job.prefix || ("assets/images/" + job.name);
    const count = Math.max(1, Number(job.count || 1));
    const outs = [];
    const bytes = [];
    try {
      // 每轮开新会话，避免上一轮上下文干扰构图
      await page.goto("https://chatgpt.com/?model=auto", { waitUntil: "domcontentloaded", timeout: 60000 });
      await waitComposer(page, 20000);
      await page.waitForTimeout(1500);
      const beforeKeys = new Set((await grab(page)).map((x) => x.key));
      await send(page, job.prompt);
      let got = await waitNew(page, beforeKeys, GEN_TIMEOUT);
      let n = 0;
      while (got.length && n < count) {
        const pickImg = got[0];
        n += 1;
        const out = prefix + "-" + n + ".png";
        bytes.push(await saveBlob(page, pickImg.src, out));
        outs.push(out);
        if (n >= count) break;
        const seenNow = new Set((await grab(page)).map((x) => x.key));
        await send(page, "换一个完全不同的构图、机位和光线，再生成一张；同样不要出现任何可读文字、logo、水印。");
        got = await waitNew(page, seenNow, GEN_TIMEOUT);
      }
      results.push({ name: job.name, ok: outs.length > 0, outs, bytes, error: outs.length ? "" : "超时未出图" });
      if (outs.length) mapItems[job.name] = outs.map((src) => ({ src, prompt: job.prompt }));
      console.log(`[ok] ${job.name}: ${outs.length} 张 ${outs.join(", ")}`);
    } catch (e) {
      results.push({ name: job.name, ok: false, outs: [], bytes: [], error: String(e.message || e).slice(0, 200) });
      console.log(`[fail] ${job.name}: ${e.message}`);
    }
  }
  await task.finish({ keep: "all" });
} catch (e) {
  console.log("[fatal] " + e.message);
} finally {
  await fs.writeFile(RESULT, JSON.stringify({ updatedAt: new Date().toISOString(), results }, null, 2));
  // 与已有映射合并：分批跑不会互相覆盖
  let prev = {};
  try { prev = JSON.parse(await fs.readFile(MAP, "utf-8")).items || {}; } catch (e) {}
  const map = { updatedAt: new Date().toISOString(), items: { ...prev, ...mapItems } };
  await fs.writeFile(MAP, JSON.stringify(map, null, 2));
  const ok = results.filter((r) => r.ok).length;
  const total = results.reduce((s, r) => s + (r.outs || []).length, 0);
  console.log(`[done] 成功 ${ok}/${results.length}，共 ${total} 张 → data/chatgpt-map.json`);
}
