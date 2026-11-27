#!/usr/bin/env node
// 从 ego 浏览器导出 YouTube/Google cookie 给 yt-dlp 用。
// 为什么需要：YouTube 对无 cookie 的请求直接返回 "Sign in to confirm you're not a bot"，
// yt-dlp 连字幕列表都拿不到。cookie 从已登录的 ego 会话里取，不碰系统 Keychain。
//
// 用法：
//   ego-browser nodejs < scripts/yt_export_cookies.js            # 默认写 /tmp/yt_cookies.txt
//   OUT=/tmp/other.txt ego-browser nodejs < scripts/yt_export_cookies.js
//
// 注意：cookie 含登录态，文件按 600 权限写，用完可删。不要提交进仓库。

const fs = await import("node:fs/promises");
const OUT = process.env.OUT || "/tmp/yt_cookies.txt";
const SPACE = "YouTube 拆解";

async function getSpace() {
  let entries = [];
  try { entries = await listTaskSpaces(); } catch (e) {}
  const entry = entries.find((s) => s.name === SPACE);
  if (!entry) return await taskSpace(SPACE, { profileId: "Default" });
  if (entry.ownership === "user") return await claimTaskSpace(entry.id);
  if (entry.ownership === "agentDelegatedToUser") return await takeOverTaskSpace(entry.id);
  return await taskSpace(entry.id);
}

const task = await getSpace();
const page = (await task.pages())[0] || await task.adopt((await task.tabs())[0].page);

// 先确保在 youtube.com 域名下，cookie 才是新鲜的
if (!/youtube\.com/.test(page.url ? page.url() : "")) {
  await page.goto("https://www.youtube.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(1500);
}

const r = await page.cdp("Network.getAllCookies");
const ck = (r.cookies || []).filter((c) => /(^|\.)youtube\.com$|(^|\.)google\.com$/.test(c.domain));
if (!ck.length) {
  console.log("[fail] 没取到 cookie，确认 ego 里 YouTube 是登录状态");
  await task.finish({ keep: "all" });
  process.exit(1);
}

const lines = ["# Netscape HTTP Cookie File", "# 由 scripts/yt_export_cookies.js 生成，含登录态，用完删除"];
for (const c of ck) {
  lines.push([
    c.domain,
    c.domain.startsWith(".") ? "TRUE" : "FALSE",
    c.path || "/",
    c.secure ? "TRUE" : "FALSE",
    String(Math.round(c.expires > 0 ? c.expires : 0)),
    c.name,
    c.value,
  ].join("\t"));
}
await fs.writeFile(OUT, lines.join("\n") + "\n", { mode: 0o600 });
console.log(`[ok] ${ck.length} 条 cookie → ${OUT}`);
await task.finish({ keep: "all" });
