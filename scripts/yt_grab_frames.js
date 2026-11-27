#!/usr/bin/env node
// 从 YouTube 播放器里抽帧（不下载视频）。
// 为什么这么干：2026-11 起 YouTube 对无 PO token 的客户端只返回 storyboard（320x180），
// 视频流格式全部不可用（yt-dlp 报 Requested format is not available）。浏览器里播放正常，
// 所以用播放器当前帧 canvas 导出，直接拿 1920x1080。
//
// 用法：
//   1) 写任务文件 /tmp/yt-frames-job.json：
//      { "url": "...", "outDir": "/tmp/xxx/frames", "times": [120, 300] }
//   2) ego-browser nodejs < scripts/yt_grab_frames.js
// 输出：outDir/t<秒>.png，并打印每帧实际落点、尺寸与字节数。
//
// 注意：seek 必须配合短播放，纯 paused 状态 seek 经常不落帧（会静默停在 0 秒）。

const fs = await import("node:fs/promises");

const JOB_PATH = "/tmp/yt-frames-job.json";
let job;
try {
  job = JSON.parse(await fs.readFile(JOB_PATH, "utf8"));
} catch (e) {
  job = {
    url: "https://www.youtube.com/watch?v=rEH7BZK-Rt4",
    outDir: "/tmp/yt-shamian/frames",
    times: [138, 421, 470, 1378]
  };
}
const URL_ = job.url;
const OUT_DIR = job.outDir;
const TIMES = job.times;
const SPACE = "YouTube 拆解";

await fs.mkdir(OUT_DIR, { recursive: true });

async function getSpace() {
  let entries = [];
  try { entries = await listTaskSpaces(); } catch (e) {}
  const found = entries.find((s) => s.name === SPACE);
  if (!found) return await taskSpace(SPACE, { profileId: "Default" });
  if (found.ownership === "user") return await claimTaskSpace(found.id);
  if (found.ownership === "agentDelegatedToUser") return await takeOverTaskSpace(found.id);
  return await taskSpace(found.id);
}

const task = await getSpace();
const page = (await task.pages())[0] || (await task.adopt((await task.tabs())[0].page));

const vid = (URL_.match(/[?&]v=([\w-]{6,})/) || [])[1] || "";
const cur = (await page.url()) || "";
if (!vid || cur.indexOf("v=" + vid) < 0) {
  await page.goto(URL_, { waitUntil: "domcontentloaded", timeout: 90000 });
}
await page.waitForSelector("video", { state: "visible", timeout: 60000 });
await page.waitForTimeout(2000);
await page.evaluate(() => {
  const v = document.querySelector("video");
  if (v) { v.pause(); v.muted = true; }
  return true;
});

const out = [];
for (const t of TIMES) {
  const info = await page.evaluate(async (sec) => {
    const v = document.querySelector("video");
    if (!v) return { ok: false, err: "no video" };
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    v.muted = true;
    v.pause();
    v.currentTime = sec;
    await wait(320);
    await v.play().catch(() => {});
    const t0 = Date.now();
    while (Date.now() - t0 < 6000) {
      if (v.currentTime >= sec - 0.6 && v.readyState >= 2 && !v.seeking) break;
      await wait(100);
    }
    v.pause();
    await wait(260);
    try {
      const c = document.createElement("canvas");
      c.width = v.videoWidth; c.height = v.videoHeight;
      c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
      return { ok: true, w: c.width, h: c.height, data: c.toDataURL("image/png").split(",")[1], got: +v.currentTime.toFixed(2) };
    } catch (e) {
      return { ok: false, err: String(e) };
    }
  }, t);

  if (!info.ok) { out.push({ want: t, ok: false, err: info.err }); continue; }
  const buf = Buffer.from(info.data, "base64");
  const path = `${OUT_DIR}/t${String(t).padStart(4, "0")}.png`;
  await fs.writeFile(path, buf);
  out.push({ want: t, got: info.got, w: info.w, h: info.h, kb: Math.round(buf.length / 1024), path });
}

console.log(JSON.stringify(out, null, 1));
await task.finish({ keep: "all" });
