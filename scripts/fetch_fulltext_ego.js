#!/usr/bin/env node
// 全文抓取的 ego 兜底：crawl4ai 拿不到的站（头条、The Verge、TechCrunch、__biz 微信、反爬门户）
// 用 ego 真浏览器 + 已登录 profile 再取一次正文，成功则写回 data/fulltext/<date>/。
//
// 用法：
//   DATE=2026-11-26 ego-browser nodejs < scripts/fetch_fulltext_ego.js
//   （不带 DATE 就取今天；只重试 _index.json 里 ok=false 的条目）
//
// 输出：与 fetch_fulltext.py 一致 —— <slug>.md、<slug>.json，并原地更新 _index.json。
// 为什么要它：crawl4ai 是 headless，账号墙/Cloudflare/头条的结构化反爬一律过不去；
// ego 有登录态和真实浏览器指纹，是同一件事的另一条腿。两条腿都过不去才算真的拿不到。

const fs = await import("node:fs/promises");
const ROOT = "/Users/lee/WorkBuddy/hotspot-radar";
const SH = (d) => new Date(d.getTime() + 8 * 3600e3).toISOString();
const DATE = process.env.DATE || SH(new Date()).slice(0, 10);
const DIR = `${ROOT}/data/fulltext/${DATE}`;
const IDX = `${DIR}/_index.json`;
const SPACE = "全文底稿抓取";

async function getSpace() {
  let entries = [];
  try { entries = await listTaskSpaces(); } catch (e) {}
  const entry = entries.find((s) => s.name === SPACE);
  if (!entry) return await taskSpace(SPACE, { profileId: "Default" });
  if (entry.ownership === "user") return await claimTaskSpace(entry.id);
  if (entry.ownership === "agentDelegatedToUser") return await takeOverTaskSpace(entry.id);
  return await taskSpace(entry.id);
}

// 正文抽取：不猜死某个 class（各站天天改），改成"候选容器里挑中文字最多的那个"
async function extract(page) {
  return await page.evaluate(() => {
    const CJK = /[\u4e00-\u9fff]/g;
    const cands = [
      "article", "#js_content", ".rich_media_content", ".article-content", ".article_content",
      ".post-content", ".entry-content", ".content", "main", "[role=main]", "div[id*=content]",
    ];
    let best = null, bestLen = 0;
    for (const sel of cands) {
      for (const el of document.querySelectorAll(sel)) {
        const t = (el.innerText || "").trim();
        const n = (t.match(CJK) || []).length;
        if (n > bestLen) { best = el; bestLen = n; }
      }
    }
    if (!best) { best = document.body; bestLen = ((best.innerText || "").match(CJK) || []).length; }
    const text = (best.innerText || "").replace(/\n{3,}/g, "\n\n").trim();
    const imgs = new Set();
    for (const im of best.querySelectorAll("img")) {
      const u = im.currentSrc || im.getAttribute("data-src") || im.getAttribute("src") || "";
      if (u && u.length > 20 && !u.startsWith("data:")) imgs.add(u.split("?")[0]);
    }
    const h1 = document.querySelector("h1");
    const words = (text.match(/[A-Za-z][A-Za-z'-]+/g) || []).length;
    return {
      title: (h1 && h1.innerText.trim()) || document.title || "",
      text, cjk: ((text.match(CJK) || []).length), words,
      images: imgs.size,
      url: location.href,
    };
  });
}

const idx = JSON.parse(await fs.readFile(IDX, "utf-8"));
const todo = (idx.rows || []).filter((r) => !r.ok && r.url);
if (!todo.length) {
  console.log("[skip] 没有需要兜底的条目");
  await fs.writeFile(IDX, JSON.stringify(idx, null, 1));
  process.exit(0);
}

const task = await getSpace();
const page = (await task.pages())[0] || await task.adopt((await task.tabs())[0].page);
const report = [];

for (const row of todo) {
  try {
    await page.goto(row.url, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForTimeout(2800);
    for (let i = 0; i < 6; i++) {
      await page.evaluate(() => window.scrollBy(0, Math.round(window.innerHeight * 0.9)));
      await page.waitForTimeout(600);
    }
    const got = await extract(page);
    if (got.cjk + got.words < 80) {
      row.note = `ego 也没取到正文（汉字 ${got.cjk} / 英文词 ${got.words}）`;
      report.push(`[fail] ${row.slug}: ${row.note}`);
      continue;
    }
    const paras = got.text.split(/\n+/).filter((l) => l.trim() && !/^[#\-*>|\d]/.test(l.trim())).length;
    const lines = got.text.split(/\n+/).map((s) => s.trim()).filter(Boolean);
    await fs.writeFile(`${DIR}/${row.slug}.md`, `# ${got.title}\n\n${got.text}\n`, "utf-8");
    const out = {
      slug: row.slug, url: got.url || row.url, ok: true, source: "ego",
      cjk: got.cjk, words: got.words, paras, subheads: 0, images: got.images, mdChars: got.text.length,
      title: got.title, note: "crawl4ai 失败，ego 兜底成功",
      fetchedAt: new Date().toISOString(),
    };
    await fs.writeFile(`${DIR}/${row.slug}.json`, JSON.stringify(out, null, 1), "utf-8");
    Object.assign(row, out);
    report.push(`[ok]   ${row.slug}: 汉字 ${got.cjk} / 英文词 ${got.words} / 图 ${got.images}`);
  } catch (e) {
    row.note = `ego 出错：${String(e.message).slice(0, 80)}`;
    report.push(`[err]  ${row.slug}: ${row.note}`);
  }
}

idx.generatedAt = new Date().toISOString();
idx.egoRetryAt = new Date().toISOString();
await fs.writeFile(IDX, JSON.stringify(idx, null, 1));
console.log(report.join("\n"));
const ok = (idx.rows || []).filter((r) => r.ok).length;
console.log(`[done] ${ok}/${(idx.rows || []).length} 条有全文`);
await task.finish({ keep: "all" });
