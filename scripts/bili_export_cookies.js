#!/usr/bin/env node
// 从 ego 浏览器导出 B 站 cookie（含 SESSDATA）给 API / yt-dlp 用。
// 为什么需要：B 站 CC/AI 字幕必须登录态才返回，未登录时 player/v2 的 subtitle.subtitles 恒为空。
//
// 用法：
//   ego-browser nodejs < scripts/bili_export_cookies.js                  # 只检查登录态
//   OUT=/tmp/bili_cookies.txt ego-browser nodejs < scripts/bili_export_cookies.js
//
// 注意：cookie 含登录态，文件按 600 权限写，不要提交进仓库。

const fs = await import("node:fs/promises");
const OUT = process.env.OUT || "";
const SPACE = process.env.SPACE || "B站 拆解-工作台";

// 坑一：taskSpace(name, {profileId}) 只在「新建」时可用，空间已存在会直接报错。
// 坑二：历史空间「B站 拆解」(id=218) 被 finish 过之后，claim 回来的 task 仍是 paused，
//        page.goto 报 "task space is no longer assigned"。所以固定用自己的工作台空间，
//        存在时按 id / claim 续用，不存在才新建。
let task;
{
  let entries = [];
  try { entries = await listTaskSpaces(); } catch (e) {}
  const hit = entries.find((x) => x.name === SPACE);
  if (!hit) {
    task = await taskSpace(SPACE, { profileId: "Default" });
  } else {
    try { task = await claimTaskSpace(hit.id); }
    catch (e) { task = await taskSpace(hit.id); }
  }
}

const pages = await task.pages();
const page = pages[0] || (await task.newPage());

if (!/bilibili\.com/.test(page.url ? page.url() : "")) {
  await page.goto("https://www.bilibili.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(2500);
}

const r = await page.cdp("Network.getAllCookies");
const ck = (r.cookies || []).filter((c) => /(^|\.)bilibili\.com$/.test(c.domain));
const hasSess = ck.some((c) => c.name === "SESSDATA" && c.value);

const st = await page.evaluate(() => {
  const av = document.querySelector(".header-avatar-wrap, .bili-avatar, #h-avatar, .header-entry-mini");
  const loginBtn = document.querySelector(".header-login-entry, .login-btn");
  const txt = document.body ? document.body.innerText.slice(0, 220) : "";
  return { hasAvatar: !!av, hasLoginBtn: !!loginBtn, snippet: txt.replace(/\s+/g, " ") };
});

console.log(JSON.stringify({
  cookieCount: ck.length,
  hasSESSDATA: hasSess,
  pageLoggedIn: st,
  url: page.url ? page.url() : "",
}));

if (OUT && ck.length) {
  const lines = [
    "# Netscape HTTP Cookie File",
    "# 由 scripts/bili_export_cookies.js 生成，含登录态，用完删除",
  ];
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
}

await task.finish({ keep: "all" });
