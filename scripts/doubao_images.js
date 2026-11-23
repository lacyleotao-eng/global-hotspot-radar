#!/usr/bin/env node
// 用 ego 浏览器驱动豆包 Seedream 生成配图并下载到本地。
// 由定时任务通过 `ego-browser nodejs < scripts/doubao_images.js` 调用；需本机已登录豆包（Default profile）。
//
// 输入 data/image-jobs.json（两种写法都支持）：
//   单个：  {"jobs":[{"name":"slug","prompt":"...","out":"assets/images/xxx.jpeg"}]}
//   批量：  {"jobs":[{"name":"slug","prompt":"...","prefix":"assets/images/xxx","count":4}]}
//           → 一次生成的多张变体依次存成 xxx-1.jpeg / xxx-2.jpeg …
// 输出：覆盖 data/image-jobs.json 为 {"results":[...]}，逐张记录 out / url / bytes / ok / error。
//
// 2026-11-23 修复：豆包改版后生成图不在 img 的 src/href 上，而是挂在任意元素的属性里，
// 旧版只扫 src/href 会 120 秒空等。现在遍历全部属性 + 背景图，并按 hash 去重。
// 另外「图像生成」模式不再靠 Seedream 字样判断（首页已不显示），改为点按钮 + 抓到图为准。

const fs = await import("node:fs/promises");
const ROOT = "/Users/lee/WorkBuddy/hotspot-radar";
const JOBS = ROOT + "/data/image-jobs.json";
const SPACE = "豆包配图自动化";
const GEN_TIMEOUT = 180000; // 单轮生成最长等待
const MIN_BYTES = 30000;    // 小于这个数当失败，不写文件

async function getSpace() {
  let entries = [];
  try { entries = await listTaskSpaces(); } catch (e) {}
  const entry = entries.find((s) => s.name === SPACE);
  if (!entry) return await taskSpace(SPACE, { profileId: "Default" });
  if (entry.ownership === "user") return await claimTaskSpace(entry.id);
  if (entry.ownership === "agentDelegatedToUser") return await takeOverTaskSpace(entry.id);
  return await taskSpace(entry.id);
}

// 抓页面里所有 rc_gen_image 直链（含原图模板）。按 hash 去重，避免同一张图多个 CDN 前缀算多张。
async function grabGenUrls(page) {
  return await page.evaluate(() => {
    const map = new Map();
    const push = (v) => {
      if (!v || !v.includes("rc_gen_image")) return;
      // 只要原图，不要头像/图标类
      if (/\/rc\/icon\//.test(v)) return;
      const m = v.match(/rc_gen_image\/([0-9a-f]{16,})/);
      if (!m) return;
      const key = m[1];
      // 同一 hash 优先保留分辨率更高的模板（cgen 前缀）或首个
      if (!map.has(key) || /cgen/.test(v)) map.set(key, v);
    };
    document.querySelectorAll("*").forEach((e) => {
      for (const a of Array.from(e.attributes || [])) push(a.value);
      const bg = getComputedStyle(e).backgroundImage;
      if (bg && bg.includes("rc_gen_image")) {
        const m = bg.match(/url\(["']?([^"')]+)/);
        if (m) push(m[1]);
      }
    });
    return Array.from(map.values());
  });
}

const raw = JSON.parse(await fs.readFile(JOBS, "utf-8"));
const jobs = Array.isArray(raw) ? raw : (raw.jobs || []);
const results = [];

// 下载：byteimg 签名链接必须带 Referer
async function download(url, outPath) {
  const resp = await fetch(url, {
    headers: { Referer: "https://www.doubao.com/", "User-Agent": "Mozilla/5.0" },
  });
  const buf = Buffer.from(await resp.arrayBuffer());
  if (buf.length < MIN_BYTES) throw new Error("下载图片过小(" + buf.length + "B)");
  const abs = ROOT + "/" + String(outPath).replace(/^\/+/, "");
  await fs.mkdir(abs.substring(0, abs.lastIndexOf("/")), { recursive: true });
  await fs.writeFile(abs, buf);
  return buf.length;
}

try {
  const task = await getSpace();
  const page = (await task.pages())[0] || await task.adopt((await task.tabs())[0].page);
  await page.goto("https://www.doubao.com/chat/", { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(3500);

  const hasEditor = await page.evaluate(() => !!document.querySelector('[contenteditable="true"]'));
  if (!hasEditor) throw new Error("豆包页面无输入框，可能未登录或页面结构变化");

  // 激活「图像生成」模式：点输入框下方那排按钮里文本完全等于「图像生成」的那个
  const modeOn = await page.evaluate(() => {
    const hit = Array.from(document.querySelectorAll("div,span,button,a"))
      .find((e) => e.textContent.trim() === "图像生成" && e.offsetParent !== null);
    if (!hit) return false;
    hit.click();
    return true;
  });
  if (!modeOn) throw new Error("页面上找不到「图像生成」模式按钮");
  await page.waitForTimeout(2500);
  console.log("[mode] 图像生成已激活");

  for (const job of jobs) {
    const count = Math.max(1, Math.min(4, job.count || 1));
    const rec = { name: job.name, prompt: job.prompt, outs: [], urls: [], ok: false, error: null };
    try {
      const before = await grabGenUrls(page);
      await page.fill('[contenteditable="true"]', job.prompt);
      await page.press('[contenteditable="true"]', "Enter");

      const deadline = Date.now() + GEN_TIMEOUT;
      let fresh = [];
      while (Date.now() < deadline) {
        await page.waitForTimeout(3000);
        const now = await grabGenUrls(page);
        fresh = now.filter((u) => !before.includes(u));
        if (fresh.length >= count) break;
      }
      if (!fresh.length) throw new Error(Math.round(GEN_TIMEOUT / 1000) + " 秒内没抓到新生成图");

      const picked = fresh.slice(0, count);
      for (let i = 0; i < picked.length; i++) {
        const out = job.out && count === 1
          ? job.out
          : (job.prefix || "assets/images/gen") + "-" + (i + 1) + ".jpeg";
        const bytes = await download(picked[i], out);
        rec.outs.push(out);
        rec.urls.push(picked[i]);
        rec.bytes = rec.bytes || [];
        rec.bytes.push(bytes);
        console.log("[ok]", job.name, "#" + (i + 1), bytes + "B", "->", out);
      }
      rec.ok = true;
    } catch (e) {
      rec.error = String((e && e.message) || e);
      console.log("[fail]", job.name, rec.error);
    }
    results.push(rec);
    await page.waitForTimeout(2000);
  }

  await task.finish({ keep: "all" });
} catch (e) {
  const msg = String((e && e.message) || e);
  console.log("[fatal]", msg);
  jobs.forEach((j) => results.push({ name: j.name, prompt: j.prompt, outs: [], urls: [], ok: false, error: "fatal: " + msg }));
}

await fs.writeFile(JOBS, JSON.stringify({ results }, null, 2));
const okCount = results.filter((r) => r.ok).length;
const imgCount = results.reduce((n, r) => n + (r.outs || []).length, 0);
console.log("[done] 任务成功", okCount, "/", results.length, "，共下载", imgCount, "张");
