// 淘宝在售价采样：按词抓搜索结果（默认按销量排序），落 data/tb-market.json
//
// 用法：
//   ego-browser nodejs < scripts/tb_market.js
//   只跑部分词：写 data/tb-run.json = {"only":["mag-base","cut-paper"]}
//
// 为什么必须用浏览器：s.taobao.com 列表是登录态 + JS 渲染，curl 只拿到骨架页（实测 40KB 无商品），
// WebFetch 会跳验证。这里复用 Default profile 的登录态，在页面内读 DOM。
//
// 口径（写进页面，别含糊）：
//   - 价格取「列表卡展示价」，通常是该链接最低价规格，且可能带「首单价」首单优惠 —— 会单独标记；
//   - 销量取「N人付款」文本，加权算分位，避免被 0 销量长尾带偏；
//   - 只读公开列表，不登录卖家后台、不加购、不下单。
const fs = await import("node:fs/promises");
const ROOT = "/Users/lee/WorkBuddy/hotspot-radar";
const CFG = JSON.parse(await fs.readFile(ROOT + "/data/tb-queries.json", "utf8"));
const OUT = ROOT + "/data/tb-market.json";

let only = null;
try {
  const run = JSON.parse(await fs.readFile(ROOT + "/data/tb-run.json", "utf8"));
  if (run.only && run.only.length) only = new Set(run.only);
} catch (e) {}

const SPACE = "淘宝比价";
const exist = (await listTaskSpaces()).find((s) => s.name === SPACE);
const task = exist ? await taskSpace(exist.id) : await taskSpace(SPACE, { profileId: "Default" });
const page = task.page("p1");

// 注意：ego 的 page.evaluate 第二参数传不进去（实测 undefined），所以这里用零参函数，不靠闭包。
function extract() {
  const PROV =
    "(浙江|广东|江苏|河北|河南|福建|山东|安徽|江西|湖北|湖南|四川|云南|贵州|陕西|山西|辽宁|吉林|黑龙江|广西|海南|内蒙古|宁夏|青海|甘肃|新疆|西藏|重庆|天津|北京|上海)";
  const num = (s) => {
    if (!s) return 0;
    const m = String(s).match(/([\d.]+)\s*万/);
    if (m) return Math.round(parseFloat(m[1]) * 10000);
    const d = String(s).match(/([\d,]+)/);
    return d ? parseInt(d[1].replace(/,/g, ""), 10) : 0;
  };
  const cards = Array.from(
    document.querySelectorAll('a[href*="item.taobao.com"], a[href*="detail.tmall.com"]')
  );
  const seen = new Set();
  const out = [];
  for (const a of cards) {
    const pw = a.querySelector('[class*="priceWrapper"]');
    if (!pw) continue;
    const href = a.href.split("&")[0];
    const idm = href.match(/id=(\d+)/);
    const key = idm ? idm[1] : href;
    if (seen.has(key)) continue;
    seen.add(key);

    const lines = (pw.innerText || "")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const salesIdx = lines.findIndex((s) => /人付款|人收货|已售/.test(s));
    const salesText = salesIdx >= 0 ? lines[salesIdx] : "";
    const pricePart = lines.join("").split(/(?:人付款|人收货|已售)/)[0];
    const pm = pricePart.match(/¥?\s*(\d+(?:\.\d{1,2})?)/);
    const price = pm ? parseFloat(pm[1]) : null;

    const full = (a.innerText || "").replace(/\n+/g, "\n");
    const seg = full.replace(/\n+/g, " / ").split(" / ").map((s) => s.trim()).filter(Boolean);

    // 店铺：列表卡里店铺名紧挨在「AI分析」前面；拿不到再用后缀兜底
    let shop = "";
    const aiIdx = seg.indexOf("AI分析");
    if (aiIdx > 0) shop = seg[aiIdx - 1];
    if (!shop || /人付款|回头客|^\d/.test(shop)) {
      const cands = seg.filter((s) =>
        /(旗舰店|专营店|专卖店|企业店|工厂店|官方店|店$|厂$|商行|经营部|贸易|公司|铺$)/.test(s)
      );
      shop = cands.length ? cands[cands.length - 1] : shop;
    }

    const tm = seg.join(" / ").match(new RegExp(PROV + "\\s*\\/\\s*([^\\/]{1,8})"));
    const title = seg[0] || "";
    if (price === null || !title) continue;
    out.push({
      id: key,
      title: title.slice(0, 90),
      price: price,
      sales: num(salesText),
      salesText: salesText,
      firstPrice: seg.some((s) => s === "首单价"),
      tmall: /detail\.tmall/.test(href),
      prov: tm ? tm[1] : "",
      city: tm ? tm[2].trim() : "",
      shop: shop,
      href: href,
    });
  }
  return {
    n: out.length,
    items: out,
    url: location.href,
    title: document.title,
    blocked: /验证|滑块/.test(document.title || "") || !!document.querySelector("#nc_1_wrapper, .nc-container"),
  };
}

const results = [];
let blocked = false;

for (const q of CFG.queries) {
  if (only && !only.has(q.id)) continue;
  const url =
    "https://s.taobao.com/search?q=" + encodeURIComponent(q.kw) + "&sort=" + (CFG.sort || "sale-desc");
  let got = null;
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
      await page.waitForTimeout(4500 + attempt * 1500);
      got = await page.evaluate(extract);
    } catch (e) {
      console.log("ERR", q.id, String(e).slice(0, 140));
    }
    if (got && got.n >= 8) break;
    await page.waitForTimeout(3000);
  }
  if (!got) {
    console.log("FAIL", q.id);
    continue;
  }
  if (got.blocked) {
    blocked = true;
    console.log("BLOCKED at", q.id, got.title);
  }
  const ps = got.items.map((x) => x.price).sort((a, b) => a - b);
  console.log(
    String(q.id).padEnd(12),
    String(q.kw).padEnd(20),
    "n=" + got.n,
    ps.length ? "rawP50=" + ps[Math.floor(ps.length / 2)] : ""
  );
  results.push({
    ...q,
    url,
    title: got.title,
    n: got.n,
    items: got.items,
    fetchedAt: new Date().toISOString(),
  });
  if (blocked) break;
  await page.waitForTimeout(2500 + Math.round(Math.random() * 2500));
}

const prev = await fs
  .readFile(OUT, "utf8")
  .then(JSON.parse)
  .catch(() => ({ queries: [] }));
const keep = (prev.queries || []).filter((p) => !results.some((r) => r.id === p.id));
const merged = {
  fetchedAt: new Date().toISOString(),
  source: "s.taobao.com 搜索结果（按销量排序，取列表展示价）",
  sort: CFG.sort,
  blocked,
  queries: [...keep, ...results].sort((a, b) => String(a.product).localeCompare(String(b.product))),
};
await fs.writeFile(OUT, JSON.stringify(merged, null, 1), "utf8");
console.log("\nDONE queries=" + merged.queries.length + " blocked=" + blocked + " -> " + OUT);
