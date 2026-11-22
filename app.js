(function () {
  'use strict';

  var TYPE = {
    hotspot: '热点话题', news: '新闻资讯', discussion: '热门帖子', resource: '资源工具',
    demand: '需求求助', idea: '想法观点', other: '其他'
  };
  var STATUS = ['已核实', '部分核实', '待核实', '未核实'];
  var REGION = ['国内', '海外'];

  var state = { items: [], meta: {}, picks: null, q: '', type: '', region: '', verify: '', sort: 'collected', page: 1, per: 24, view: 'picks', target: '', priority: '' };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function safeUrl(u) {
    try { var x = new URL(u); return /^https?:$/.test(x.protocol) ? u : ''; } catch (e) { return ''; }
  }
  function copyText(text, btn) {
    function done() {
      if (!btn) return;
      var old = btn.textContent;
      btn.textContent = '已复制';
      setTimeout(function () { btn.textContent = old; }, 1600);
    }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { /* 忽略浏览器限制 */ }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(fallback);
    } else fallback();
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
    state.picks = window.__PICKS__ || null;
    initControls();
    applyView();
    render();
  }

  function applyView() {
    var isPicks = state.view === 'picks';
    var isLeads = state.view === 'leads';
    document.getElementById('picksPanel').hidden = !isPicks;
    document.getElementById('mainToolbar').hidden = isPicks;
    document.getElementById('typeChips').hidden = isPicks || isLeads;
    document.getElementById('leadBar').hidden = !isLeads;
    document.querySelector('.resultbar').hidden = isPicks;
    document.getElementById('grid').hidden = isPicks;
    document.getElementById('empty').hidden = true;
    document.querySelector('.more-wrap').hidden = isPicks;
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

    var tabs = document.getElementById('viewTabs');
    Array.prototype.forEach.call(tabs.querySelectorAll('.vtab'), function (btn) {
      btn.onclick = function () {
        state.view = btn.getAttribute('data-view');
        state.page = 1;
        Array.prototype.forEach.call(tabs.querySelectorAll('.vtab'), function (b) { b.classList.toggle('on', b === btn); });
        applyView();
        document.querySelector('.legend').hidden = state.view === 'leads' || state.view === 'picks';
        document.getElementById('search').placeholder = state.view === 'leads' ? '搜索选题标题、切入点、提纲…' : '搜索标题、摘要、平台、标签…';
        document.getElementById('viewHint').textContent = state.view === 'picks'
          ? '每日按时效、热度、核实度、优先级打分排序的成稿候选'
          : (state.view === 'leads'
            ? '按发布去向与优先级筛选，一键复制标题 + 提纲 + 原文链接'
            : '每条情报可展开详情，查看来源与核实过程');
        render();
      };
    });
    document.getElementById('targetFilter').addEventListener('change', function (e) { state.target = e.target.value; state.page = 1; render(); });
    document.getElementById('priorityFilter').addEventListener('change', function (e) { state.priority = e.target.value; state.page = 1; render(); });

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
    var leads = state.items.reduce(function (n, i) { return n + ((i.leads || []).length); }, 0);
    document.getElementById('leadTabCount').textContent = leads;
    document.getElementById('topStats').innerHTML =
      '<span><b>' + total + '</b>条目</span><span><b>' + leads + '</b>选题线索</span><span><b>' + cn + '</b>国内</span><span><b>' + (total - cn) + '</b>海外</span>';
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
        var leadText = (it.leads || []).map(function (l) {
          return [l.headline, l.angle, l.audience, (l.outline || []).join(' ')].join(' ');
        }).join(' ');
        var hay = [it.title, it.summary, it.platform, it.subtype, (it.tags || []).join(' '), (it.evaluation || {}).editor, leadText].join(' ').toLowerCase();
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

  function filteredLeads() {
    var rank = { '高': 0, '中': 1, '低': 2 };
    var out = [];
    filtered().forEach(function (it) {
      (it.leads || []).forEach(function (lead) {
        if (state.target && lead.target !== state.target) return;
        if (state.priority && lead.priority !== state.priority) return;
        out.push({ item: it, lead: lead });
      });
    });
    out.sort(function (a, b) {
      var d = (rank[a.lead.priority] == null ? 3 : rank[a.lead.priority]) - (rank[b.lead.priority] == null ? 3 : rank[b.lead.priority]);
      if (d) return d;
      return String(b.item.collectedAt || '').localeCompare(String(a.item.collectedAt || ''));
    });
    return out;
  }

  function scoreRows(pick) {
    return (pick.breakdown || []).map(function (b) {
      var cls = b.points > 0 ? 'sp-pos' : (b.points < 0 ? 'sp-neg' : 'sp-zero');
      return '<span class="score-part ' + cls + '">' + esc(b.label) + ' <b>' + (b.points > 0 ? '+' : '') + b.points + '</b></span>';
    }).join('');
  }

  function pickCardHtml(pick) {
    var lead = pick.lead || {};
    var url = safeUrl(pick.url);
    var outline = (lead.outline || []).map(function (o, i) {
      return '<li>' + esc(o) + '</li>';
    }).join('');
    var verifyCls = statusClass(pick.verification);
    var risk = lead.risk || '无';
    return '<article class="pick-card">' +
      '<div class="pick-top">' +
        '<span class="pick-rank">TOP ' + pick.rank + '</span>' +
        '<span class="pick-score"><b>' + pick.score + '</b> 分</span>' +
        '<span class="vpill v-' + esc(verifyCls) + '">' + esc(pick.verification || '未核实') + '</span>' +
      '</div>' +
      '<h3 class="pick-title">' + esc(lead.headline || pick.sourceTitle) + '</h3>' +
      '<p class="pick-angle">' + esc(lead.angle || '') + '</p>' +
      (outline ? '<ol class="pick-outline">' + outline + '</ol>' : '') +
      '<div class="pick-scores">' + scoreRows(pick) + '</div>' +
      '<div class="pick-meta">' +
        '<span>读者：' + esc(lead.audience || '泛读者') + '</span>' +
        '<span class="risk-warn">风险：' + esc(risk) + '</span>' +
      '</div>' +
      '<div class="pick-src">线索源：' + esc(pick.platform || '') + ' · ' + esc(pick.region || '') + ' · ' + esc(pick.heatStage || '') + '</div>' +
      '<div class="pick-actions">' +
        '<button class="copy-brief" data-key="' + esc(pick.itemId + '|' + pick.target) + '">复制成稿 brief</button>' +
        (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">原文 ↗</a>' : '') +
        '<span class="draft-tag">草稿已生成</span>' +
      '</div>' +
    '</article>';
  }

  function renderPicks() {
    var p = state.picks;
    var groupsEl = document.getElementById('picksGroups');
    if (!p || !p.groups) {
      document.getElementById('picksDate').textContent = '暂无选题数据';
      document.getElementById('picksStat').textContent = '';
      groupsEl.innerHTML = '<div class="picks-empty">今日选题尚未生成，等待定时任务运行或手动执行评分脚本。</div>';
      return;
    }
    document.getElementById('picksDate').textContent = p.date + ' 每日选题';
    var total = 0;
    Object.keys(p.groups).forEach(function (k) { total += (p.groups[k] || []).length; });
    document.getElementById('picksStat').innerHTML = '<b>' + total + '</b> 个成稿候选<span>评分 ' + p.totalScored + ' 条线索</span>';

    var html = '';
    ['公众号', '今日头条'].forEach(function (target) {
      var rows = p.groups[target] || [];
      if (!rows.length) return;
      html += '<div class="picks-group"><div class="picks-group-head"><span class="target-badge l-' + esc(target) + '">' + esc(target) + '</span><span>TOP ' + rows.length + '</span></div>';
      html += '<div class="picks-cards">' + rows.map(pickCardHtml).join('') + '</div></div>';
    });
    groupsEl.innerHTML = html;

    Array.prototype.forEach.call(groupsEl.querySelectorAll('.copy-brief'), function (b) {
      b.onclick = function () {
        var parts = b.getAttribute('data-key').split('|');
        var found = null;
        Object.keys(p.groups).forEach(function (k) {
          (p.groups[k] || []).forEach(function (row) {
            if (row.itemId === parts[0] && row.target === parts[1]) found = row;
          });
        });
        if (!found) return;
        var lead = found.lead || {};
        var text = '【' + found.target + '成稿 brief · ' + found.date + ' · ' + found.score + '分】\n\n' +
          '标题：' + (lead.headline || '') + '\n\n' +
          '切入角度：' + (lead.angle || '') + '\n\n' +
          '提纲：\n' + (lead.outline || []).map(function (o, i) { return (i + 1) + '. ' + o; }).join('\n') + '\n\n' +
          '目标读者：' + (lead.audience || '') + '\n' +
          '时效：' + (lead.timeliness || '') + ' · 优先级：' + (lead.priority || '') + '\n\n' +
          '事实依据：' + (lead.basis || '') + '\n' +
          '核实状态：' + (found.verification || '') + '\n' +
          '风险提示：' + (lead.risk || '无') + '\n' +
          '原文：' + (found.url || '') + '\n' +
          '评分明细：' + (found.breakdown || []).map(function (x) { return x.label + '(' + (x.points > 0 ? '+' : '') + x.points + ')'; }).join('、');
        copyText(text, b);
      };
    });
  }

  function render() {
    if (state.view === 'picks') { renderPicks(); return; }
    var rows = state.view === 'leads' ? filteredLeads() : filtered();
    document.getElementById('resultCount').textContent = '显示 ' + rows.length + (state.view === 'leads' ? ' 条选题线索' : ' 条');
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

  function leadCardHtml(pair) {
    var it = pair.item, ld = pair.lead;
    var url = safeUrl(it.url);
    var outline = (ld.outline || []).slice(0, 4).map(function (o, i) {
      return '<li>' + esc(o) + '</li>';
    }).join('');
    var risk = ld.risk || '无';
    var riskCls = risk === '无' ? 'safe' : 'warn';
    return '<article class="card lead-card">' +
      '<div class="card-head">' +
        '<span class="badge l-' + esc(ld.target) + '">' + esc(ld.target) + '</span>' +
        '<span class="lead-pri p-' + esc(ld.priority) + '">' + esc(ld.priority || '中') + '优先级</span>' +
        '<span class="lead-time">' + esc(ld.timeliness || '长期') + '</span>' +
      '</div>' +
      '<h3 class="card-title lead-title">' + esc(ld.headline) + '</h3>' +
      '<p class="lead-angle"><b>切入角度：</b>' + esc(ld.angle) + '</p>' +
      (outline ? '<ol class="lead-outline">' + outline + '</ol>' : '') +
      '<div class="lead-extra"><span>读者：' + esc(ld.audience || '泛读者') + '</span>' +
        '<span class="risk-' + riskCls + '">风险：' + esc(risk) + '</span></div>' +
      '<p class="lead-basis"><b>事实依据：</b>' + esc(ld.basis || it.summary.slice(0, 80)) + '</p>' +
      '<div class="card-meta"><span>线索源：' + esc(it.platform) + '</span><span class="sep">·</span><span>' + esc(it.title) + '</span></div>' +
      '<div class="card-actions">' +
        '<button class="copy-lead" data-id="' + esc(it.id) + '" data-target="' + esc(ld.target) + '">复制选题包</button>' +
        (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">原文 ↗</a>' : '') +
        '<button class="detail-btn" data-id="' + esc(it.id) + '">详情 / 溯源 →</button></div>' +
    '</article>';
  }

  function drawCards() {
    var rows = window.__ROWS__ || [];
    var grid = document.getElementById('grid');
    var start = (state.page - 1) * state.per;
    var slice = rows.slice(0, start + state.per);
    grid.innerHTML = state.view === 'leads' ? slice.map(leadCardHtml).join('') : slice.map(cardHtml).join('');
    Array.prototype.forEach.call(grid.querySelectorAll('.copy-lead'), function (b) {
      b.onclick = function () {
        var it = state.items.find(function (x) { return x.id === b.getAttribute('data-id'); });
        if (!it) return;
        var ld = (it.leads || []).find(function (l) { return l.target === b.getAttribute('data-target'); });
        if (!ld) return;
        var text = '【' + ld.target + '选题】' + ld.headline + '\n\n切入角度：' + ld.angle +
          '\n\n提纲：\n' + (ld.outline || []).map(function (o, i) { return (i + 1) + '. ' + o; }).join('\n') +
          '\n\n事实依据：' + ld.basis + '\n风险提示：' + (ld.risk || '无') +
          '\n原文：' + (it.url || '') + '\n采集时间：' + it.collectedAt;
        copyText(text, b);
      };
    });
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
      ((it.leads || []).length ? '<div class="m-box"><h4>选题线索</h4>' + it.leads.map(function (l) {
        return '<div class="m-lead"><span class="badge l-' + esc(l.target) + '">' + esc(l.target) + '</span> <b>' + esc(l.headline) + '</b>' +
          '<p>' + esc(l.angle) + '</p><small>优先级：' + esc(l.priority || '中') + ' · 时效：' + esc(l.timeliness || '长期') + ' · 风险：' + esc(l.risk || '无') + '</small></div>';
      }).join('') + '</div>' : '') +
      '<div class="m-box"><h4>引用溯源</h4>' + (cites || '<p>暂无独立引用，仅以上述来源为准。</p>') + '</div>' +
      '<div class="m-actions">' + (url ? '<a class="btn" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">打开原文 ↗</a>' : '') +
      '<button class="btn alt" id="copyLink">复制本条链接</button></div>';
    document.getElementById('modalMask').hidden = false;
    var cp = document.getElementById('copyLink');
    if (cp) cp.onclick = function () { copyText(url || it.title, cp); };
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
