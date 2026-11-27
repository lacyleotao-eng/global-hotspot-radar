// 抓 1688 商品详情页的「规格 + 每个规格的定价 + 阶梯价 + 运费」
// 用法：ego-browser nodejs < scripts/t1688_specs.js
//      带 --refresh 全量重抓；否则只补 links 里还没抓过的 offer
// 输出：data/t1688-offers.json
import fs from 'node:fs';
import path from 'node:path';
const ROOT = '/Users/lee/WorkBuddy/hotspot-radar';
const LINKS = path.join(ROOT, 'data/t1688-links.json');
const OUT = path.join(ROOT, 'data/t1688-offers.json');

const links = JSON.parse(fs.readFileSync(LINKS, 'utf8'));
const ids = [];
for (const rows of Object.values(links.items || {})) {
  for (const g of rows || []) for (const p of g.picks || []) if (p.id && !ids.includes(p.id)) ids.push(p.id);
}

// 参数走文件：ego-browser 不继承 shell 环境变量
let params = {};
try { params = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/t1688-params.json'), 'utf8')); } catch (e) { }
const REFRESH = !!params.refresh;
const onlyArg = (params.only || []).join(',');
const pool = onlyArg ? onlyArg.split(',').map(x => x.trim()).filter(Boolean) : ids;
console.log('params', JSON.stringify({ refresh: REFRESH, pool: pool.length }));
const linkTitles = {};
for (const rows of Object.values(links.items || {})) for (const g of rows || []) for (const p of g.picks || []) linkTitles[p.id] = p.title || '';

let store = { fetchedAt: '', offers: {} };
if (fs.existsSync(OUT)) {
  try { store = JSON.parse(fs.readFileSync(OUT, 'utf8')); } catch (e) { }
}
store.offers = store.offers || {};
if (REFRESH) store.offers = {};

const task = await taskSpace("1688 规格抓取");
let page = task.page("p1");
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const EXTRACT = () => {
  const T = (el) => (el ? (el.innerText || '').replace(/\s+/g, ' ').trim() : '');
  const body = document.body.innerText.replace(/\u00a0/g, ' ');
  const flat = body.replace(/\s+/g, ' ');

  // ---- 阶梯价 ----
  const ladder = [];
  const stepBox = document.querySelector('.od-price-container-step');
  if (stepBox) {
    const s = T(stepBox);
    const re = /¥\s*(\d+)\s*\.\s*(\d{1,2})(?:\s*(?:(\d+)\s*-\s*(\d+)|≥\s*(\d+)|(\d+)))?\s*([^\d¥]{0,8})/g;
    let m;
    while ((m = re.exec(s))) {
      const price = parseFloat(m[1] + '.' + m[2]);
      if (!isFinite(price)) continue;
      let min = null, max = null;
      if (m[3]) { min = +m[3]; max = +m[4]; }
      else if (m[5]) { min = +m[5]; max = null; }
      else if (m[6]) { min = +m[6]; max = null; }
      ladder.push({ min, max, price, unit: (m[7] || '').replace(/起批|套|件|个|包|张|条|对|盒|只|支/g, '').trim() });
    }
  }

  // ---- 发货 / 运费 ----
  let shipFrom = '', freight = '', shipNote = '';
  const shipBox = document.querySelector('.module-od-shipping-services');
  if (shipBox) {
    shipNote = T(shipBox);
    const fm = shipNote.match(/运费\s*¥?\s*([\d.]+)\s*起/);
    if (fm) freight = parseFloat(fm[1]);
    const parts = shipNote.split(' ').filter(x => x && !/送至|选择收货地址|运费|承诺|发货|以内|小时/.test(x));
    shipFrom = parts[0] || '';
  }

  // ---- 已售 ----
  let sold = '';
  const sm = flat.match(/已售\s*([\d.]+[万亿+]*\s*[^\s]{0,3})/);
  if (sm) sold = sm[1].trim();

  // ---- 店铺 ----
  let shop = '';
  const shopSel = ['.od-company-name', '[class*="company-name"]', '[class*="companyName"]', '[class*="shop-name"]', '.company-name'];
  for (const sel of shopSel) { const e = document.querySelector(sel); if (e && T(e)) { shop = T(e); break; } }
  if (!shop) {
    const m = flat.match(/([\u4e00-\u9fa5]{2,}(?:市|县|区)[\u4e00-\u9fa5]{2,}(?:有限公司|工艺品厂|贸易有限公司|制品厂|商行|经营部|电子商务有限公司))/);
    if (m) shop = m[1];
  }

  // ---- 规格维度 ----
  const dims = [...document.querySelectorAll('.feature-item')].map((fi) => {
    const name = T(fi.querySelector('.feature-item-label'));
    const values = [...fi.querySelectorAll('.expand-view-item')].map((it) => {
      const labelEl = it.querySelector('.item-label');
      const nm = (labelEl?.getAttribute('title') || T(labelEl) || '').trim();
      const ps = [...it.querySelectorAll('.item-price-stock')].map((e) => T(e));
      let price = null, stock = null;
      for (const s of ps) {
        const pm = s.match(/¥\s*([\d.]+)/); if (pm && price == null) price = parseFloat(pm[1]);
        const km = s.match(/库存\s*([\d]+)/); if (km && stock == null) stock = +km[1];
      }
      return { name: nm, price, stock, raw: ps.join(' ') };
    }).filter(v => v.name && !/默认|另加|备注|说明|请联系/.test(v.name));
    return { name, values };
  }).filter(d => d.values.length);

  // ---- 组合规格：单维度直接用；多维度按维度拼接，价格留空待组合表 ----
  let specs = [];
  const multi = dims.length > 1;
  if (dims.length === 1) {
    specs = dims[0].values.map(v => ({ name: v.name, price: v.price, stock: v.stock, dims: { [dims[0].name]: v.name } }));
  } else if (dims.length > 1) {
    // 多维度：优先找带价格的组合行（部分类目有 SKU 表）
    const rows = [...document.querySelectorAll('[class*="sku-table"] tbody tr, .od-sku-table tbody tr')];
    for (const tr of rows) {
      const tds = [...tr.querySelectorAll('td')].map(td => T(td));
      if (tds.length >= 2) {
        const pm = tds.join(' ').match(/¥\s*([\d.]+)/);
        specs.push({ name: tds.slice(0, dims.length).join(' / '), price: pm ? parseFloat(pm[1]) : null, stock: null, dims: {} });
      }
    }
    if (!specs.length) {
      // 退化：每个维度的值单列，价格为空
      for (const d of dims) for (const v of d.values) {
        specs.push({ name: v.name, price: v.price, stock: v.stock, dims: { [d.name]: v.name }, partial: true });
      }
    }
  }

  const title = (document.querySelector('h1')?.innerText || document.title.replace(/\s*-\s*阿里巴巴\s*$/, '')).trim();
  return { title, shop, ladder, shipFrom, freight, shipNote, sold, dims, specs, multiDim: multi, specCount: specs.length };
};


async function passSlider(page) {
  const has = await page.evaluate(() => !!document.querySelector('.nc_scale'));
  if (!has) return false;
  await page.cdp("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 1 });
  const b = await page.evaluate(() => {
    const s = document.querySelector('.nc_scale').getBoundingClientRect();
    const h = document.querySelector('.btn_slide') ? document.querySelector('.btn_slide').getBoundingClientRect() : s;
    return { sx: s.x, sw: s.width, hx: h.x, hy: h.y, hw: h.width, hh: h.height };
  });
  const y = Math.round(b.hy + b.hh / 2);
  const x0 = Math.round(b.hx + b.hw / 2);
  const x1 = Math.round(b.sx + b.sw - 6);
  await page.cdp("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: x0, y, id: 1 }] });
  await sleep(320);
  for (let i = 1; i <= 40; i++) {
    const t = i / 40;
    const p = t < 0.12 ? t * 0.6 : t > 0.88 ? 1 - (1 - t) * 0.5 : 0.072 + (t - 0.12) * 1.13;
    const x = x0 + Math.round((x1 - x0) * Math.min(1, p));
    await page.cdp("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: y + (i % 7 === 0 ? 1 : 0), id: 1 }] });
    await sleep(20 + Math.random() * 26);
  }
  await page.cdp("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await sleep(4200);
  return true;
}

let ok = 0, fail = 0;
for (const id of pool) {
  if (!REFRESH && store.offers[id] && (store.offers[id].specs || []).length) { continue; }
  try { await page.url(); } catch (e) {
    const pages = await task.pages();
    page = pages.length ? pages[0] : await task.newPage();
  }
  const url = `https://detail.1688.com/offer/${id}.html`;
  let got = null, err = '';
  for (let attempt = 1; attempt <= 3 && !got; attempt++) {
    try {
      await page.goto(url, { timeout: 45000 });
      await sleep(2600 + Math.random() * 700);
      await passSlider(page);
      await sleep(900);
      const r = await page.evaluate(EXTRACT);
      const here = await page.evaluate(() => ({ href: location.href, title: document.title }));
      const hrefOk = here.href.indexOf(id) >= 0;
      const want = (linkTitles[id] || '');
      const bigrams = (t) => { const a = new Set(); const c = t.replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g, ''); for (let i = 0; i < c.length - 1; i++) a.add(c.slice(i, i + 2)); return a; };
      const A = bigrams(want), B = bigrams(here.title);
      let hit = 0; for (const g of A) if (B.has(g)) hit++;
      const titleOk = !want || hit >= 3;
      if (r && r.title && hrefOk && titleOk && (r.specs.length || r.ladder.length)) {
        got = { ...r, pageTitle: here.title, matchHits: hit };
      } else {
        err = !hrefOk ? ('href mismatch: ' + here.href.slice(-40)) : (!titleOk ? ('title mismatch hit=' + hit) : 'empty');
      }
    } catch (e) { err = String(e).slice(0, 120); }
    if (!got) { await sleep(1500); try { await page.reload({ timeout: 25000 }); } catch (e) { } await sleep(1200); }
  }
  if (got) {
    store.offers[id] = { id, url, ...got, fetchedAt: new Date().toISOString().slice(0, 10) };
    ok++;
    const lo = got.ladder.length ? Math.min(...got.ladder.map(l => l.price)) : null;
    console.log(`[ok] ${id} specs=${got.specCount} ladder=${got.ladder.length} lo=${lo} ${got.shop.slice(0, 14)} | ${got.title.slice(0, 26)}`);
  } else {
    store.offers[id] = { id, url, error: err || 'unknown', fetchedAt: new Date().toISOString().slice(0, 10) };
    fail++;
    console.log(`[fail] ${id} ${err}`);
  }
  await sleep(2600 + Math.random() * 1800);
}

store.fetchedAt = new Date().toISOString().slice(0, 10);
fs.writeFileSync(OUT, JSON.stringify(store, null, 1), 'utf8');
console.log(`\n[done] ok=${ok} fail=${fail} total=${Object.keys(store.offers).length} -> ${OUT}`);
await task.finish({ keep: [] });
