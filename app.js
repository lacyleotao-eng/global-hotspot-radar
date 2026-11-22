(function () {
  'use strict';

  var TYPE = {
    hotspot: '热点话题', news: '新闻资讯', discussion: '热门帖子', resource: '资源工具',
    demand: '需求求助', idea: '想法观点', other: '其他'
  };
  var STATUS = ['已核实', '部分核实', '待核实', '未核实'];
  var REGION = ['国内', '海外'];

  var state = { items: [], meta: {}, q: '', type: '', region: '', verify: '', sort: 'collected', page: 1, per: 24 };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function safeUrl(u) {
    try { var x = new URL(u); return /^https?:$/.test(x.protocol) ? u : ''; } catch (e) { return ''; }
  }
  function fmt(t) {
    if (!t) return '时间未知';
    var d = new Date(t);
    if (isNaN(d.getTime())) return String(t);
    var p = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
  function statusClass(s) { return STATUS.indexOf(s) >= 0 ? s : '未核实'; }

  function boot(data) {
    state.items = (data && data.items) || [];
    state.meta = (window.__META__ && window.__META__) || {};
    initControls();
    render();
  }

  function initControls() {
    var tf = document.getElementById('typeFilter');
    Object.keys(TYPE).forEach(function (k) {
      var o = document.createElement('option'); o.value = k; o.textContent = TYPE[k]; tf.appendChild(o);
    });
    var rf = document.getElementById('regionFilter');
    REGION.forEach(function (r) { var o = document.createElement('option'); o.value = r; o.textContent = r; rf.appendChild(o); });
    var vf = document.getElementById('verifyFilter');
    STATUS.forEach(function (s) { var o = document.createElement('option'); o.value = s; o.textContent = s; vf.appendChild(o); });

    var chips = document.getElementById('typeChips');
    var keys = ['', 'hotspot', 'news', 'discussion', 'resource', 'demand', 'idea'];
    keys.forEach(function (k) {
      var b = document.createElement('button');
      b.className = 'chip' + (k === '' ? ' on' : '');
      b.textContent = k === '' ? '全部 ' + state.items.length : TYPE[k] + ' ' + state.items.filter(function (i) { return i.type === k; }).length;
      b.onclick = function () {
        state.type = k; state.page = 1;
        Array.prototype.forEach.call(chips.children, function (c) { c.classList.remove('on'); });
        b.classList.add('on'); tf.value = k; render();
      };
      chips.appendChild(b);
    });

    document.getElementById('search').addEventListener('input', function (e) { state.q = e.target.value.trim().toLowerCase(); state.page = 1; render(); });
    tf.addEventListener('change', function (e) {
      state.type = e.target.value; state.page = 1;
      Array.prototype.forEach.call(chips.children, function (c, idx) { c.classList.toggle('on', keys[idx] === state.type); });
      render();
    });
    rf.addEventListener('change', function (e) { state.region = e.target.value; state.page = 1; render(); });
    vf.addEventListener('change', function (e) { state.verify = e.target.value; state.page = 1; render(); });
    document.getElementById('sortBy').addEventListener('change', function (e) { state.sort = e.target.value; state.page = 1; render(); });
    document.getElementById('moreBtn').onclick = function () { state.page++; drawCards(); };
    document.getElementById('closeBtn').onclick = closeModal;
    document.getElementById('modalMask').onclick = function (e) { if (e.target.id === 'modalMask') closeModal(); };
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });

    var total = state.items.length;
    var cn = state.items.filter(function (i) { return i.region === '国内'; }).length;
    document.getElementById('topStats').innerHTML =
      '<span><b>' + total + '</b>条目</span><span><b>' + cn + '</b>国内</span><span><b>' + (total - cn) + '</b>海外</span>';
    document.getElementById('updateLabel').textContent = state.meta.updatedAt ? '更新于 ' + fmt(state.meta.updatedAt) : '等待数据';
    document.getElementById('footerMeta').textContent = state.meta.updatedAt ? '数据更新时间：' + fmt(state.meta.updatedAt) + ' · 共 ' + total + ' 条' : '';
  }

  function filtered() {
    var q = state.q;
    var rows = state.items.filter(function (it) {
      if (state.type && it.type !== state.type) return false;
      if (state.region && it.region !== state.region) return false;
      if (state.verify && (it.verification || {}).status !== state.verify) return false;
      if (q) {
        var hay = [it.title, it.summary, it.platform, it.subtype, (it.tags || []).join(' '), (it.evaluation || {}).editor].join(' ').toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
    rows.sort(function (a, b) {
      if (state.sort === 'published') return String(b.publishedAt || '').localeCompare(String(a.publishedAt || ''));
      if (state.sort === 'type') return String(a.type).localeCompare(String(b.type)) || String(b.collectedAt).localeCompare(String(a.collectedAt));
      return String(b.collectedAt || '').localeCompare(String(a.collectedAt || ''));
    });
    return rows;
  }

  function render() {
    var rows = filtered();
    document.getElementById('resultCount').textContent = '显示 ' + rows.length + ' 条';
    document.getElementById('empty').hidden = rows.length > 0;
    window.__ROWS__ = rows;
    state.page = 1;
    var grid = document.getElementById('grid');
    grid.innerHTML = '';
    drawCards();
  }

  function cardHtml(it) {
    var url = safeUrl(it.url);
    var v = it.verification || {};
    var h = it.heat || {};
    var img = it.image && safeUrl(it.image.url);
    var title = url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(it.title) + '</a>' : esc(it.title);
    return '<article class="card">' +
      '<div class="card-head">' +
        '<span class="badge t-' + esc(it.type) + '">' + esc(TYPE[it.type] || '其他') + '</span>' +
        '<span class="region">' + esc(it.region) + '</span>' +
        '<span class="stage">' + esc(h.stage || '热度未知') + '</span>' +
      '</div>' +
      (img ? '<img class="thumb" src="' + esc(img) + '" alt="' + esc((it.image && it.image.caption) || it.title) + '" loading="lazy" onerror="this.style.display=\'none\'">' : '') +
      '<h3 class="card-title">' + title + '</h3>' +
      '<p class="card-summary">' + esc(it.summary) + '</p>' +
      '<div class="card-meta"><span>' + esc(it.platform) + '</span><span class="sep">·</span><span>' + esc(fmt(it.publishedAt || it.collectedAt)) + '</span><span class="sep">·</span><span class="vpill v-' + esc(statusClass(v.status)) + '">' + esc(v.status || '未核实') + '</span></div>' +
      ((it.tags || []).length ? '<div class="tags">' + it.tags.slice(0, 5).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') + '</div>' : '') +
      '<div class="card-actions">' + (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">查看原文 ↗</a>' : '<span>无直链</span>') +
        '<button class="detail-btn" data-id="' + esc(it.id) + '">详情 / 溯源 →</button></div>' +
    '</article>';
  }

  function drawCards() {
    var rows = window.__ROWS__ || [];
    var grid = document.getElementById('grid');
    var start = (state.page - 1) * state.per;
    var slice = rows.slice(0, start + state.per);
    grid.innerHTML = slice.map(cardHtml).join('');
    Array.prototype.forEach.call(grid.querySelectorAll('.detail-btn'), function (b) {
      b.onclick = function () { openModal(b.getAttribute('data-id')); };
    });
    document.getElementById('moreBtn').hidden = slice.length >= rows.length;
  }

  function signalsHtml(sig) {
    if (!sig || !Object.keys(sig).length) return '<p>页面可见互动数据：不可见</p>';
    var labels = { views: '阅读/播放', likes: '赞', comments: '评论', shares: '转发' };
    return '<p>' + Object.keys(labels).map(function (k) {
      return labels[k] + '：' + esc(sig[k] || '不可见');
    }).join('　') + '</p>';
  }

  function openModal(id) {
    var it = state.items.find(function (x) { return x.id === id; });
    if (!it) return;
    var url = safeUrl(it.url);
    var v = it.verification || {}, e = it.evaluation || {}, h = it.heat || {};
    var img = it.image && safeUrl(it.image.url);
    var cites = (it.citations || []).map(function (c) {
      var u = safeUrl(c.url);
      return '<div class="cite">' + (u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + esc(c.title || c.url) + ' ↗</a>' : esc(c.title || '未命名来源')) +
        '<small>' + esc(c.publisher || '') + (c.date ? ' · ' + esc(c.date) : '') + (c.relation ? ' · ' + esc(c.relation) : '') + '</small></div>';
    }).join('');
    document.getElementById('modalBody').innerHTML =
      '<div class="card-head"><span class="badge t-' + esc(it.type) + '">' + esc(TYPE[it.type] || '其他') + '</span>' +
      '<span class="region">' + esc(it.region) + '</span><span class="vpill v-' + esc(statusClass(v.status)) + '">' + esc(v.status || '未核实') + '</span></div>' +
      '<h3 id="modalTitle">' + esc(it.title) + '</h3>' +
      '<p class="m-summary">' + esc(it.summary) + '</p>' +
      (img ? '<img class="m-img" src="' + esc(img) + '" alt="' + esc((it.image && it.image.caption) || it.title) + '" onerror="this.style.display=\'none\'"><small style="color:var(--muted)">' + esc((it.image && it.image.caption) || '') + (it.image && it.image.rights ? ' · 版权：' + esc(it.image.rights) : '') + '</small>' : '') +
      '<div class="m-grid">' +
        '<div class="m-box"><h4>来源与时间</h4><p>平台：' + esc(it.platform) + '</p><p>原发布：' + esc(fmt(it.publishedAt)) + '</p><p>采集：' + esc(fmt(it.collectedAt)) + '</p><p>细分：' + esc(it.subtype || '未分类') + '</p></div>' +
        '<div class="m-box"><h4>热度信号</h4><p>阶段：' + esc(h.stage || '未知') + '</p>' + signalsHtml(h.signals) + '</div>' +
        '<div class="m-box"><h4>资料核实</h4><p>状态：' + esc(v.status || '未核实') + '</p><p>方法：' + esc(v.method || '未记录') + '</p><p>核实时间：' + esc(fmt(v.verifiedAt)) + '</p><p>存疑：' + esc(v.notes || '无') + '</p></div>' +
        '<div class="m-box"><h4>评价</h4><p>编辑点评：' + esc(e.editor || '无') + '</p><p>社区评价：' + esc(e.community || '不可见') + '</p><p>倾向：' + esc(e.sentiment || '未知') + (e.source ? '（' + esc(e.source) + '）' : '') + '</p>' +
          ((it.needs || []).length ? '<p>需求归纳：</p><ul>' + it.needs.map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('') + '</ul>' : '') + '</div>' +
      '</div>' +
      '<div class="m-box"><h4>引用溯源</h4>' + (cites || '<p>暂无独立引用，仅以上述来源为准。</p>') + '</div>' +
      '<div class="m-actions">' + (url ? '<a class="btn" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">打开原文 ↗</a>' : '') +
      '<button class="btn alt" id="copyLink">复制本条链接</button></div>';
    document.getElementById('modalMask').hidden = false;
    var cp = document.getElementById('copyLink');
    if (cp) cp.onclick = function () {
      var text = url || it.title;
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text);
      cp.textContent = '已复制';
    };
  }
  function closeModal() { document.getElementById('modalMask').hidden = true; }

  if (window.__ITEMS__) {
    boot(window.__ITEMS__);
  } else {
    fetch('data/items.json', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(boot)
      .catch(function () { boot({ items: [] }); });
  }
})();
