#!/usr/bin/env node
// 用 ego 浏览器驱动豆包 Seedream 5.5 生成配图并下载到本地。
// 由定时任务通过 `ego-browser nodejs <本文件>` 调用；需要本机已登录豆包（Default profile）。
//
// 输入：data/image-jobs.json  —— [{"name":"slug","prompt":"...","out":"assets/images/xxx.jpeg"}]
// 输出：覆盖 data/image-jobs.json 为 {"results":[{name,out,url,ok,error}...]}
// 任何一步失败都写 ok:false 并继续下一个，不影响其他任务；绝不伪造成功。

const fs = await import("node:fs/promises");
const ROOT = "/Users/lee/WorkBuddy/hotspot-radar";
const JOBS = ROOT + "/data/image-jobs.json";
const SPACE = "豆包配图自动化";

// 取或建空间：优先复用同名 agent 空间；若是用户持有的空间则 claim；否则新建并绑定 Default profile。
async function getSpace() {
  let entries = [];
  try { entries = await listTaskSpaces(); } catch (e) {}
  const entry = entries.find((s) => s.name === SPACE);
  if (!entry) return await taskSpace(SPACE, { profileId: "Default" });
  if (entry.ownership === "user") return await claimTaskSpace(entry.id);
  if (entry.ownership === "agentDelegatedToUser") return await takeOverTaskSpace(entry.id);
  return await taskSpace(entry.id);
}

// 收集页面里所有「生成图」直链（rc_gen_image），排除头像与图标。
async function grabGenUrls(page) {
  return await page.evaluate(() => {
    const set = new Set();
    document.querySelectorAll("*").forEach((e) => {
      ["src", "href"].forEach((a) => {
        const v = e.getAttribute(a);
        if (v && v.includes("rc_gen_image")) set.add(v);
      });
      const bg = getComputedStyle(e).backgroundImage;
      if (bg && bg.includes("rc_gen_image")) {
        const m = bg.match(/url\(["']?([^"')]+)/);
        if (m) set.add(m[1]);
      }
    });
    return Array.from(set);
  });
}

const jobsRaw = JSON.parse(await fs.readFile(JOBS, "utf-8"));
const jobs = Array.isArray(jobsRaw) ? jobsRaw : (jobsRaw.jobs || []);
const results = [];

try {
  const task = await getSpace();
  const page = (await task.pages())[0] || await task.adopt((await task.tabs())[0].page);
  await page.goto("https://www.doubao.com/chat/", { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(2500);

  // 确认登录：能读到输入框即可；读不到就判失败，不假装成功。
  const hasEditor = await page.evaluate(() => !!document.querySelector('[contenteditable="true"]'));
  if (!hasEditor) throw new Error("豆包页面无输入框，可能未登录或页面结构变化");

  // 激活「图像生成」模式（若尚未激活，页面不会出现 Seedream 字样）
  const active = await page.evaluate(() => document.body.innerText.includes("Seedream"));
  if (!active) {
    await page.click("text=图像生成");
    await page.waitForTimeout(1000);
  }
  const modelOn = await page.evaluate(() => document.body.innerText.includes("Seedream"));
  if (!modelOn) throw new Error("未能激活图像生成模式（未见 Seedream 模型标识）");

  for (const job of jobs) {
    const rec = { name: job.name, out: job.out, url: null, ok: false, error: null };
    try {
      const before = await grabGenUrls(page);
      await page.fill('[contenteditable="true"]', job.prompt);
      await page.press('[contenteditable="true"]', "Enter");
      // 等待出现新的生成图链接：轮询而非固定延时，最多 120 秒
      const deadline = Date.now() + 120000;
      let after = [];
      while (Date.now() < deadline) {
        await page.waitForTimeout(2500);
        after = await grabGenUrls(page);
        if (after.some((u) => !before.includes(u))) break;
      }
      const fresh = after.filter((u) => !before.includes(u));
      if (!fresh.length) throw new Error("120 秒内未获得新生成图链接");
      rec.url = fresh[0];
      // 下载到本地：byteimg 签名链接需要 Referer；图片有效性用字节数兜底
      const resp = await fetch(fresh[0], {
        headers: { Referer: "https://www.doubao.com/", "User-Agent": "Mozilla/5.0" },
      });
      const buf = Buffer.from(await resp.arrayBuffer());
      if (buf.length < 20000) throw new Error("下载图片过小(" + buf.length + "B)，疑似失败");
      const outPath = ROOT + "/" + String(job.out).replace(/^\/+/, "");
      await fs.mkdir(outPath.substring(0, outPath.lastIndexOf("/")), { recursive: true });
      await fs.writeFile(outPath, buf);
      rec.ok = true;
      rec.bytes = buf.length;
      console.log("[ok]", job.name, rec.bytes + "B", "->", job.out);
    } catch (e) {
      rec.error = String(e && e.message || e);
      console.log("[fail]", job.name, rec.error);
    }
    results.push(rec);
    await page.waitForTimeout(1500);
  }

  await task.finish({ keep: "all" });
} catch (e) {
  const msg = String(e && e.message || e);
  console.log("[fatal]", msg);
  jobs.forEach((j) => results.push({ name: j.name, out: j.out, url: null, ok: false, error: "fatal: " + msg }));
}

await fs.writeFile(JOBS, JSON.stringify({ results }, null, 2));
console.log("[done] 成功", results.filter((r) => r.ok).length, "/", results.length);
