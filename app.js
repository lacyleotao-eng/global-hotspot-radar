(function () {
  'use strict';

  var TYPE = {
    hotspot: '热点话题', news: '新闻资讯', discussion: '热门帖子', resource: '资源工具',
    demand: '需求求助', idea: '想法观点', other: '其他'
  };
  var STATUS = ['已核实', '部分核实', '待核实', '未核实'];
  var REGION = ['国内', '海外'];

  var state = { items: [], meta: {}, picks: null, ready: { docs: [] }, viral: { items: [], meta: {}, benchmark: [] }, audit: null, q: '', type: '', region: '', verify: '', sort: 'collected', page: 1, per: 24, view: 'issue', target: '', priority: '', draftOpen: null, viralForm: '', viralSort: 'score', viralTier: '', viralOpen: null, auditForm: '', auditToday: true, issue: null };

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

  // 每天一班：清晨把当天素材备齐，09:30 起发布人随时可取（排期改动同步这里）。
  var BATCH = [[8, 45, '当天素材备齐']];

  function pad2(n) { return n < 10 ? '0' + n : '' + n; }

  function nextBatches() {
    var now = new Date(), out = [];
    BATCH.forEach(function (b) {
      var d = new Date(now.getFullYear(), now.getMonth(), now.getDate(), b[0], b[1], 0);
      var same = d > now;
      if (!same) d.setDate(d.getDate() + 1);
      out.push({ at: d, label: (same ? '今天 ' : '明天 ') + pad2(b[0]) + ':' + pad2(b[1]), what: b[2] });
    });
    out.sort(function (a, b) { return a.at - b.at; });
    return out;
  }

  // 这一批稿什么时候发：生成当晚 21:00–22:00（公众号晚高峰尾段），或次日 07:00–08:30（早高峰）。
  function renderWindows() {
    var el = document.getElementById('heroWindow');
    if (el) {
      var nb = nextBatches(), a = nb[0];
      var it = state.issue || {};
      var today = new Date();
      var ymd = today.getFullYear() + '-' + pad2(today.getMonth() + 1) + '-' + pad2(today.getDate());
      if (it.date === ymd && it.status === 'ready') {
        var g = ((it.pools || {})['公众号'] || {}).available || 0;
        var t = ((it.pools || {})['今日头条'] || {}).available || 0;
        el.innerHTML = '<span class="hw-tag">今日已备齐</span><b>公众号 ' + g + ' 篇 · 头条 ' + t + ' 篇</b>' +
          '　→　09:30 起随时取用，复制即可发';
      } else if (a) {
        el.innerHTML = '<span class="hw-tag">下一批</span><b>' + a.label + '</b> ' + a.what +
          '　→　<b>09:30 起</b>公众号 1 篇、头条 3 篇，素材随时取用';
      }
    }
    var pw = document.getElementById('picksWindow');
    if (pw) {
      var p = state.picks || {};
      var gen = p.generatedAt ? fmt(p.generatedAt) : (p.date ? p.date + ' 晚间批次' : '未知');
      var latest = ((state.ready || {}).docs || []).reduce(function (acc, d) {
        return (d.date && d.date > acc) ? d.date : acc;
      }, '');
      var today = fmt(new Date()).slice(0, 10);
      var stale = (p.date || latest) && (p.date || latest) < today;
      var nb2 = nextBatches()[0];
      pw.innerHTML = '本批生成 ' + esc(gen) +
        ' ｜ 已备好 <b>公众号 6 篇</b>、<b>头条 8 篇</b>，<b>几点发、发哪篇由发布人定</b>；去「今日发布」直接复制全文与图片' +
        (stale ? ' ｜ <span class="pw-stale">今天素材将在 ' + esc(nb2.label) + ' 前备齐</span>' : '');
    }
  }

  function boot(data) {
    state.items = (data && data.items) || [];
    state.meta = (window.__META__ && window.__META__) || {};
    state.picks = window.__PICKS__ || null;
    state.ready = window.__READY__ || { docs: [] };
    state.viral = window.__VIRAL__ || { items: [], meta: {}, benchmark: [] };
    state.audit = window.__AUDIT__ || null;
    state.issue = window.__ISSUE__ || null;
    initControls();
    // 深链：#view=picks|audit|benchmark|feed|leads 直接打开某个视图
    var vm = /^#view=(issue|picks|audit|benchmark|feed|leads)$/.exec(location.hash || '');
    if (vm) state.view = vm[1];
    applyView();
    renderPipe();
    render();
    renderIssue();
    // 深链：#draft=<sourceItemId>:<pieceId> 直接打开某篇成品稿
    var m = /^#draft=([^:]+):(.+)$/.exec(location.hash || '');
    if (m) openDraft(decodeURIComponent(m[1]), decodeURIComponent(m[2]));
    renderWindows();
    setInterval(renderWindows, 60000);
    refreshEmbeddedData();
  }

  // *-embed.js 会被浏览器/CDN 缓存（GitHub Pages 10 分钟），而站点数据每天更新。
  // 线上环境额外用 no-store 拉一次 JSON，比对 updatedAt 后静默替换，避免看到昨天的分。
  function refreshEmbeddedData() {
    if (!/^https?:/.test(location.protocol) || typeof fetch !== 'function') return;
    function pull(url, pick, apply) {
      fetch(url + '?t=' + Date.now(), { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && pick(d)) apply(d); })
        .catch(function () {});
    }
    pull('data/audit.json', function (d) { return d && d.updatedAt && (!state.audit || d.updatedAt !== state.audit.updatedAt); }, function (d) {
      state.audit = d;
      if (state.view === 'audit') renderAudit();
    });
    pull('data/picks.json', function (d) { return d && d.generatedAt && (!state.picks || d.generatedAt !== state.picks.generatedAt); }, function (d) {
      state.picks = d;
      renderPipe();
      if (state.view === 'picks') renderPicks();
    });
    pull('data/ready/index.json', function (d) { return d && d.docs; }, function (d) {
      state.ready = d;
      if (state.view === 'picks') renderPicks();
    });
    pull('data/issue.json', function (d) { return d && d.pools && d.generatedAt !== (state.issue || {}).generatedAt; }, function (d) {
      state.issue = d;
      renderPipe();
      if (state.view === 'issue') renderIssue();
    });
  }

  function applyView() {
    var isPicks = state.view === 'picks';
    var isLeads = state.view === 'leads';
    var isBench = state.view === 'benchmark';
    var isAudit = state.view === 'audit';
    var isIssue = state.view === 'issue';
    document.getElementById('issuePanel').hidden = !isIssue;
    document.getElementById('benchPanel').hidden = !isBench;
    document.getElementById('auditPanel').hidden = !isAudit;
    document.getElementById('picksPanel').hidden = !isPicks;
    document.getElementById('mainToolbar').hidden = isPicks || isBench || isAudit || isIssue;
    document.getElementById('typeChips').hidden = isPicks || isLeads || isBench || isAudit || isIssue;
    document.getElementById('leadBar').hidden = !isLeads;
    document.querySelector('.resultbar').hidden = isPicks || isBench || isAudit || isIssue;
    document.getElementById('grid').hidden = isPicks || isBench || isAudit || isIssue;
    document.getElementById('empty').hidden = true;
    document.querySelector('.more-wrap').hidden = isPicks || isBench || isAudit || isIssue;
  }

  // 六个视图其实是两条路：
  //   生产线 feed → leads → picks → audit → issue（前者喂后者，audit 是闸门）
  //   参照系 benchmark（只当标尺，不参与生产）
  var VIEW_HINT = {
    feed: '第 1 步｜每条情报都带原文链接、采集时间与核实状态，点开可看溯源',
    leads: '第 2 步｜情报里能写的角度：标题 + 切入角度 + 提纲 + 事实依据，按去向和优先级筛',
    picks: '第 3 步｜今天定下要做的选题：公众号 6 个 + 头条 8 个，每个选题下面挂着已出的稿和自检分',
    audit: '第 4 步｜闸门：按爆款基准打分，≥85 进发布池，＜85 直接淘汰',
    issue: '第 5 步｜通过自检的成品，复制全文 + 下载图片就能发',
    benchmark: '参照系｜每天采 10 篇真爆款（公众号 5 · 头条 5），拆成标尺；它不参与生产，只决定自检的及格线'
  };

  function setText(id, txt) {
    var el = document.getElementById(id);
    if (el) el.textContent = txt;
  }

  // 流水线数字全部来自真实数据，不写死；缺数据时显示「—」
  function renderPipe() {
    var it = state.issue || {};
    var f = it.funnel || {};
    var pools = it.pools || {};
    var gzh = pools['公众号'] || {};
    var tt = pools['今日头条'] || {};
    var gzhAvail = gzh.available || 0;
    var ttAvail = tt.available || 0;
    var gzhTarget = (it.targets || {})['公众号'] || 6;
    var ttTarget = (it.targets || {})['今日头条'] || 8;

    var picks = state.picks || {};
    var groups = picks.groups || {};
    var gzhPicks = (groups['公众号'] || []).length;
    var ttPicks = (groups['今日头条'] || []).length;
    var leadCount = state.items.reduce(function (n, x) { return n + ((x.leads || []).length); }, 0);

    setText('pnIntel', state.items.length ? state.items.length + ' 条' : '—');
    setText('pnLeads', leadCount ? leadCount + ' 个角度' : '—');
    setText('pnPicks', (gzhPicks + ttPicks) ? (gzhPicks + ttPicks) + ' 个' : '—');
    setText('pnAudit', f.passed != null ? f.passed + ' 过 / ' + (f.rejected || 0) + ' 汰' : '—');
    setText('pnIssue', (gzhAvail + ttAvail) ? (gzhAvail + ttAvail) + ' 篇' : '—');
    setText('pnViral', ((state.viral || {}).meta || {}).total ? ((state.viral || {}).meta || {}).total + ' 篇' : '—');

    // 小字改成动态配额，让「6 / 8」一眼可见
    var pnPicks = document.querySelector('.pnode[data-view="picks"] small');
    if (pnPicks) pnPicks.textContent = '公众号 ' + gzhPicks + ' · 头条 ' + ttPicks;
    var pnAudit = document.querySelector('.pnode[data-view="audit"] small');
    if (pnAudit) pnAudit.textContent = '及格线 ' + (it.passScore || 85) + ' 分，不过就淘汰';
    var pnIssue = document.querySelector('.pnode[data-view="issue"] small');
    if (pnIssue) pnIssue.textContent = '公 ' + gzhAvail + '/' + gzhTarget + ' · 头 ' + ttAvail + '/' + ttTarget;
    var pnIntel = document.querySelector('.pnode[data-view="feed"] small');
    if (pnIntel) pnIntel.textContent = '全网采集的原始情报';
    var pnViralNote = document.querySelector('.pnode[data-view="benchmark"] small');
    if (pnViralNote) {
      var vt = ((state.viral || {}).meta || {}).total || 0;
      pnViralNote.textContent = '样本库 ' + vt + ' 篇 · 每天新增约 10 篇（公 5 · 头 5）';
    }

    Array.prototype.forEach.call(document.querySelectorAll('.pnode'), function (b) {
      b.classList.toggle('on', b.getAttribute('data-view') === state.view);
    });
    var hint = document.getElementById('viewHint');
    if (hint) hint.textContent = VIEW_HINT[state.view] || '';
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
    Array.prototype.forEach.call(tabs.querySelectorAll('.pnode'), function (btn) {
      btn.onclick = function () {
        state.view = btn.getAttribute('data-view');
        state.page = 1;
        Array.prototype.forEach.call(tabs.querySelectorAll('.pnode'), function (b) { b.classList.toggle('on', b === btn); });
        applyView();
        renderPipe();
        if (state.view === 'issue') renderIssue();
        document.querySelector('.legend').hidden = state.view === 'leads' || state.view === 'picks' || state.view === 'benchmark' || state.view === 'audit' || state.view === 'issue';
        document.getElementById('search').placeholder = state.view === 'leads' ? '搜索选题标题、切入点、提纲…' : '搜索标题、摘要、平台、标签…';
        render();
      };
    });
    document.getElementById('targetFilter').addEventListener('change', function (e) { state.target = e.target.value; state.page = 1; render(); });
    document.getElementById('priorityFilter').addEventListener('change', function (e) { state.priority = e.target.value; state.page = 1; render(); });
    document.getElementById('viralSort').addEventListener('change', function (e) { state.viralSort = e.target.value; renderBenchmark(); });
    document.getElementById('viralTierFilter').addEventListener('change', function (e) { state.viralTier = e.target.value; renderBenchmark(); });

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
    document.getElementById('draftClose').onclick = closeDraft;
    document.getElementById('draftMask').onclick = function (e) { if (e.target.id === 'draftMask') closeDraft(); };
    document.getElementById('viralClose').onclick = closeViral;
    document.getElementById('viralMask').onclick = function (e) { if (e.target.id === 'viralMask') closeViral(); };
    document.getElementById('viralCopy').onclick = function () {
      if (state.viralOpen) copyText(viralFullText(state.viralOpen), document.getElementById('viralCopy'));
    };
    document.getElementById('draftCopy').onclick = function (b) {
      var o = state.draftOpen;
      if (!o) return;
      var piece = o.pieces.find(function (p) { return p.id === o.pieceId; });
      if (piece) copyText(pieceFullText(piece, o.doc), document.getElementById('draftCopy'));
    };
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      if (!document.getElementById('viralMask').hidden) closeViral();
      else if (!document.getElementById('draftMask').hidden) closeDraft();
      else closeModal();
    });

    var total = state.items.length;
    var cn = state.items.filter(function (i) { return i.region === '国内'; }).length;
    var leads = state.items.reduce(function (n, i) { return n + ((i.leads || []).length); }, 0);
    document.getElementById('topStats').innerHTML =
      '<span><b>' + total + '</b>条目</span><span><b>' + leads + '</b>选题线索</span><span><b>' + ((state.viral.meta || {}).total || 0) + '</b>爆款样本</span><span><b>' + cn + '</b>国内</span>';
    document.getElementById('updateLabel').textContent = state.meta.updatedAt ? '条目更新 ' + fmt(state.meta.updatedAt) : '等待数据';
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
    var rows = (pick.breakdown || []).filter(function (b) { return b && Number(b.points) !== 0; });
    return rows.map(function (b) {
      var cls = b.points > 0 ? 'sp-pos' : (b.points < 0 ? 'sp-neg' : 'sp-zero');
      return '<span class="score-part ' + cls + '">' + esc(b.label) + ' <b>' + (b.points > 0 ? '+' : '') + b.points + '</b></span>';
    }).join('');
  }

  // 选题 → 今天已经出的稿（带自检分）。发布人看选题时就能知道「这条到底出了没有、过没过」。
  function draftsOfPick(pick) {
    var scoreMap = {};
    ((state.audit || {}).pieces || []).forEach(function (p) { scoreMap[(p.file || '') + '::' + p.form] = p; });
    var passScore = (state.issue || {}).passScore || 85;
    var out = [];
    ((state.ready || {}).docs || []).forEach(function (d) {
      if (d.sourceItemId !== pick.itemId) return;
      var file = d.file || (d.date + '-' + d.slug + '.json');
      (d.pieces || []).forEach(function (pc) {
        var rec = scoreMap[file + '::' + pc.id] || null;
        out.push({
          pieceId: pc.id,
          title: pc.title,
          formShort: pc.id === 'gzh-poster' ? '贴图' : (pc.id === 'tt-micro' ? '微头条' : '文章'),
          score: rec ? rec.score : null,
          passed: !!(rec && rec.score >= passScore)
        });
      });
    });
    return out;
  }

  function pickCardHtml(pick) {
    var lead = pick.lead || {};
    var url = safeUrl(pick.url);
    var outline = (lead.outline || []).map(function (o, i) {
      return '<li>' + esc(o) + '</li>';
    }).join('');
    var verifyCls = statusClass(pick.verification);
    var risk = lead.risk || '无';
    var drafts = draftsOfPick(pick);
    var draftsHtml = '<div class="pick-drafts"><span class="pd-label">今天的稿</span>' +
      (drafts.length
        ? drafts.map(function (x) {
            var cls = x.score == null ? 'wait' : (x.passed ? 'pass' : 'fail');
            var stateTxt = x.score == null ? '待检' : (x.passed ? '过' : '淘汰');
            return '<button class="dstate ' + cls + '" data-item="' + esc(pick.itemId) + '" data-piece="' + esc(x.pieceId) + '" title="' + esc(x.title) + '">' +
              esc(x.formShort) + ' <b>' + (x.score == null ? '—' : x.score) + '</b> ' + stateTxt + '</button>';
          }).join('')
        : '<span class="pick-empty-draft">还没出稿</span>') +
      '</div>';
    return '<article class="pick-card">' +
      '<div class="pick-top">' +
        '<span class="pick-rank">TOP ' + pick.rank + '</span>' +
        '<span class="pick-score"><b>' + pick.score + '</b> 分</span>' +
        '<span class="vpill v-' + esc(verifyCls) + '">' + esc(pick.verification || '未核实') + '</span>' +
      '</div>' +
      '<h3 class="pick-title">' + esc(lead.headline || pick.sourceTitle) + '</h3>' +
      '<p class="pick-angle">' + esc(lead.angle || '') + '</p>' +
      (outline ? '<ol class="pick-outline">' + outline + '</ol>' : '') +
      (scoreRows(pick) ? '<div class="pick-scores">' + scoreRows(pick) + '</div>' : '') +
      '<div class="pick-meta">' +
        '<span>读者：' + esc(lead.audience || '泛读者') + '</span>' +
        '<span class="risk-warn">风险：' + esc(risk) + '</span>' +
      '</div>' +
      '<div class="pick-src">线索源：' + esc(pick.platform || '') + ' · ' + esc(pick.region || '') + ' · ' + esc(pick.heatStage || '') + '</div>' +
      draftsHtml +
      '<div class="pick-actions">' +
        (findDocForPick(pick)
          ? '<button class="view-draft" data-item="' + esc(pick.itemId) + '">查看草稿详情</button>'
          : '<span class="draft-pending" title="这条选题还没有对应成品稿，出稿任务会在下一轮补上">草稿待补</span>') +
        '<button class="copy-brief" data-key="' + esc(pick.itemId + '|' + pick.target) + '">复制成稿 brief</button>' +
        (url ? '<a class="pick-orig" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">原文</a>' : '') +
      '</div>' +
    '</article>';
  }

  function findDocForPick(pick) {
    return (state.ready.docs || []).find(function (d) { return d.sourceItemId === pick.itemId; }) || null;
  }

  function picksCoverage() {
    var p = state.picks || {};
    var have = {};
    ((state.ready || {}).docs || []).forEach(function (d) { if (d.sourceItemId) have[d.sourceItemId] = 1; });
    var total = 0, covered = 0, missing = [];
    Object.keys(p.groups || {}).forEach(function (k) {
      var seen = {};
      (p.groups[k] || []).forEach(function (pick) {
        var id = pick.itemId;
        if (!id || seen[id]) return;
        seen[id] = 1;
        total += 1;
        if (have[id]) covered += 1;
        else missing.push((pick.lead || {}).headline || pick.sourceTitle || id);
      });
    });
    return { total: total, covered: covered, ok: total > 0 && covered === total, missing: missing };
  }

  function docPiecesForItem(itemId) {
    var doc = (state.ready.docs || []).find(function (d) { return d.sourceItemId === itemId; });
    return doc ? { doc: doc, pieces: doc.pieces || [] } : null;
  }

  function blockOne(b) {
    if (b.type === 'h2') return '<h3 class="rp-h2">' + esc(b.text) + '</h3>';
    if (b.type === 'para') return '<p class="rp-para">' + esc(b.text) + '</p>';
    if (b.type === 'note') return '<p class="rp-note">' + esc(b.text) + '</p>';
    if (b.type === 'list') return '<ul class="rp-list">' + (b.items || []).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
    return '';
  }

  function figHtml(im) {
    return '<figure class="rp-figure"><img src="' + esc(im.src) + '" alt="' + esc(im.caption || '') + '" loading="lazy"><figcaption>' + esc(im.caption || '') + '</figcaption></figure>';
  }

  function blocksToHtml(piece) {
    return (piece.blocks || []).map(blockOne).join('');
  }

  // 把全部配图均匀穿插进正文：文章首图作封面，其余按段落均分；贴图从第一张起均分
  function bodyWithImages(piece) {
    var imgs = piece.images || [];
    var rows = (piece.blocks || []).map(blockOne).filter(Boolean);
    var isPoster = piece.form === '贴图';
    var cover = (!isPoster && imgs.length) ? figHtml(imgs[0]) : '';
    var rest = isPoster ? imgs.slice() : imgs.slice(1);
    if (!rest.length || !rows.length) {
      return { cover: cover, body: rows.join('') + rest.map(figHtml).join('') };
    }
    var step = rows.length / rest.length;
    var marks = rest.map(function (im, i) {
      return { at: Math.min(rows.length, Math.max(1, Math.round((i + 1) * step))), im: im };
    });
    var out = [];
    var k = 0;
    for (var i = 0; i <= rows.length; i++) {
      while (k < marks.length && marks[k].at === i) { out.push(figHtml(marks[k].im)); k++; }
      if (i < rows.length) out.push(rows[i]);
    }
    while (k < marks.length) { out.push(figHtml(marks[k].im)); k++; }
    return { cover: cover, body: out.join('') };
  }

  function pieceHtml(piece, doc) {
    var imgs = piece.images || [];
    var built = bodyWithImages(piece);
    var lead = built.cover;
    var all = built.body;
    return '<div class="rp-meta"><span class="badge l-' + esc(piece.target) + '">' + esc(piece.target) + '</span>' +
      '<span class="rp-form">' + esc(piece.form) + '</span>' +
      '<span class="vpill v-' + esc(statusClass(doc.verification)) + '">' + esc(doc.verification || '') + '</span>' +
      '<span class="rp-badge">' + esc(piece.badge || '') + '</span>' +
      '<span class="rp-imgcount">' + imgs.length + ' 张配图</span></div>' +
      '<h2 class="rp-title" id="draftTitle">' + esc(piece.title) + '</h2>' +
      (piece.digest ? '<p class="rp-digest">' + esc(piece.digest) + '</p>' : '') +
      lead + '<div class="rp-content">' + all + '</div>' +
      '<div class="rp-disclaimer"><b>核实与配图说明</b><p>' + esc(doc.verificationNote || '') + '</p><p>' + esc(doc.imageNote || '') + '</p>' +
      '<p>原文：<a href="' + esc(safeUrl(doc.sourceUrl) || '#') + '" target="_blank" rel="noopener noreferrer">' + esc(doc.sourceTitle || '查看来源') + ' ↗</a></p></div>';
  }

  function openDraft(itemId, pieceId) {
    var found = docPiecesForItem(itemId);
    if (!found) return;
    var doc = found.doc, pieces = found.pieces;
    var current = pieceId || (pieces[0] && pieces[0].id);
    state.draftOpen = { itemId: itemId, pieceId: current, doc: doc, pieces: pieces };
    var tabs = document.getElementById('draftTabs');
    tabs.innerHTML = pieces.map(function (p) {
      return '<button class="draft-tab' + (p.id === current ? ' on' : '') + '" data-piece="' + esc(p.id) + '">' +
        esc(p.target) + ' · ' + esc(p.form) + '</button>';
    }).join('');
    Array.prototype.forEach.call(tabs.querySelectorAll('.draft-tab'), function (b) {
      b.onclick = function () { openDraft(itemId, b.getAttribute('data-piece')); };
    });
    var piece = pieces.find(function (p) { return p.id === current; }) || pieces[0];
    document.getElementById('draftBody').innerHTML = pieceHtml(piece, doc);
    document.getElementById('draftBody').scrollTop = 0;
    document.getElementById('draftMask').hidden = false;
  }

  function closeDraft() { document.getElementById('draftMask').hidden = true; state.draftOpen = null; }

  function pieceFullText(piece, doc) {
    var lines = ['【' + piece.target + ' · ' + piece.form + '】' + piece.title];
    if (piece.digest) lines.push('', piece.digest);
    (piece.blocks || []).forEach(function (b) {
      if (b.type === 'h2') lines.push('', b.text);
      else if (b.type === 'para' || b.type === 'note') lines.push('', b.text);
      else if (b.type === 'list') (b.items || []).forEach(function (x, i) { lines.push((i + 1) + '. ' + x); });
    });
    lines.push('', '---', '核实：' + (doc.verification || ''), doc.verificationNote || '', '原文：' + (doc.sourceUrl || ''));
    return lines.join('\n');
  }

  var VFORM = {
    'gzh-article': '公众号文章', 'gzh-poster': '公众号贴图',
    'tt-article': '头条文章', 'tt-micro': '微头条'
  };
  // 前端二次隔离：形态与平台必须对应，防止历史脏数据混显
  var FORM_PLATFORM = {
    'gzh-article': '微信公众号', 'gzh-poster': '微信公众号',
    'tt-article': '今日头条', 'tt-micro': '今日头条'
  };
  var VTIER = {
    S: { label: 'S 现象级', cls: 's' }, A: { label: 'A 爆款', cls: 'a' },
    B: { label: 'B 热门', cls: 'b' }, C: { label: 'C 上升', cls: 'c' }
  };

  function benchTableHtml() {
    var rows = state.viral.benchmark || [];
    return rows.map(function (r) {
      var v = r.viral || {}, m = r.mine || {};
      var verdictCls = r.verdict.indexOf('达标') >= 0 ? 'ok' : (r.verdict.indexOf('不足') >= 0 || r.verdict.indexOf('偏少') >= 0 ? 'warn' : 'muted');
      return '<tr>' +
        '<td><b>' + esc(r.formLabel) + '</b><small>爆款 ' + r.viralSample + ' 条 / 自家 ' + r.selfSample + ' 条</small></td>' +
        '<td>' + (v.wordCount != null ? v.wordCount + ' 字' : '—') + '</td>' +
        '<td><b>' + (m.wordCount != null ? m.wordCount + ' 字' : '—') + '</b></td>' +
        '<td>' + (v.images != null ? v.images + ' 张' : '—') + '</td>' +
        '<td><b>' + (m.images != null ? m.images + ' 张' : '—') + '</b></td>' +
        '<td><span class="bench-verdict ' + verdictCls + '">' + esc(r.verdict) + '</span></td>' +
      '</tr>';
    }).join('');
  }

  function viralFiltered() {
    var rows = (state.viral.items || []).filter(function (i) {
      return FORM_PLATFORM[i.form] && i.platform === FORM_PLATFORM[i.form];
    });
    if (state.viralForm) rows = rows.filter(function (i) { return i.form === state.viralForm; });
    if (state.viralTier) rows = rows.filter(function (i) { return (i.viralScore || {}).tier === state.viralTier; });
    var order = { S: 4, A: 3, B: 2, C: 1 };
    rows.sort(function (a, b) {
      if (state.viralSort === 'words') return ((b.anatomy || {}).wordCount || 0) - ((a.anatomy || {}).wordCount || 0);
      if (state.viralSort === 'collected') return String(b.collectedAt || '').localeCompare(String(a.collectedAt || ''));
      if (state.viralSort === 'tier') return (order[(b.viralScore || {}).tier] || 0) - (order[(a.viralScore || {}).tier] || 0) || (b.viralScore.total - a.viralScore.total);
      return (b.viralScore || {}).total - (a.viralScore || {}).total;
    });
    return rows;
  }

  function viralCardHtml(it) {
    var url = safeUrl(it.url);
    var vs = it.viralScore || {}, an = it.anatomy || {}, sig = it.signals || {};
    var tier = VTIER[vs.tier] || VTIER.C;
    var title = url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(it.title) + '</a>' : esc(it.title);
    var lessons = (an.lessons || []).slice(0, 2);
    return '<article class="viral-card">' +
      '<div class="viral-card-head">' +
        '<span class="vform">' + esc(VFORM[it.form] || it.form) + '</span>' +
        '<span class="vplat">' + esc(it.platform || FORM_PLATFORM[it.form] || '') + '</span>' +
        '<span class="vtier t-' + tier.cls + '">' + esc(tier.label) + '</span>' +
        '<span class="vscore"><b>' + (vs.total || 0) + '</b> 分</span>' +
      '</div>' +
      '<h3>' + title + '</h3>' +
      '<p class="viral-account">' + esc(it.account || '') + ' · ' + esc(it.category || '') + ' · ' + (it.sourceHost ? '原文域名 ' + esc(it.sourceHost) : '无公开直链（客户端补录）') + '</p>' +
      '<div class="viral-stats">' +
        '<span>字数 <b>' + (an.wordCount != null ? an.wordCount : '—') + '</b></span>' +
        '<span>配图 <b>' + (an.images != null ? an.images : '—') + '</b></span>' +
        '<span>小标题 <b>' + (an.subheads != null ? an.subheads : '—') + '</b></span>' +
        '<span class="vsrc">信号：' + esc(sig.source || '不可见') + '</span>' +
      '</div>' +
      '<p class="viral-pattern"><b>标题套路：</b>' + esc(an.titlePattern || '—') + '</p>' +
      (lessons.length ? '<ul class="viral-lessons">' + lessons.map(function (l) { return '<li>' + esc(l) + '</li>'; }).join('') + '</ul>' : '') +
      '<div class="viral-card-actions">' +
        '<button class="viral-detail" data-id="' + esc(it.id) + '">查看拆解 →</button>' +
        (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">原文 ↗</a>' : '') +
      '</div>' +
    '</article>';
  }

  var AGRADE = { '达标': 'g-ok', '接近': 'g-near', '不达标': 'g-bad' };

  function auditCardHtml(p) {
    var m = p.metrics || {};
    var bench = p.bench || {};
    var checks = p.checks || {};
    var passScore = (state.issue || {}).passScore || 85;
    var passed = p.score >= passScore;
    var gate = '<span class="dstate ' + (passed ? 'pass' : 'fail') + '">' +
      (passed ? '通过 · 进发布池' : '淘汰 · 不发布') + '</span>';
    var keys = ['wordCount', 'images', 'structure', 'title', 'hook'];
    var bars = keys.map(function (k) {
      var c = checks[k];
      if (!c) return '';
      var pct = Math.round((c.score / c.weight) * 100);
      var cls = pct >= 85 ? 'b-ok' : (pct >= 65 ? 'b-near' : 'b-bad');
      var note = (c.notes || []).filter(function (n) { return n; }).join('；');
      return '<div class="audit-check">' +
        '<div class="ac-head"><span class="ac-label">' + esc(c.label) + '</span>' +
        '<span class="ac-score">' + c.score + '/' + c.weight + '</span></div>' +
        '<div class="ac-bar ' + cls + '"><i style="width:' + Math.max(2, Math.min(100, pct)) + '%"></i></div>' +
        '<p class="ac-note">' + esc(note) + '</p>' +
        '</div>';
    }).join('');

    var gaps = (p.gaps || []).map(function (g) {
      return '<li><b>' + esc(g.dim) + '</b><span>' + esc(g.gap) + '</span>' +
        '<em>' + esc(g.fix) + '</em></li>';
    }).join('');
    var gapBlock = gaps
      ? '<div class="audit-gaps"><div class="ag-title">还差什么、怎么补</div><ul>' + gaps + '</ul></div>'
      : '<div class="audit-gaps ok"><div class="ag-title">五项全部达标，可以直接进排期</div></div>';

    var numMeta = function (label, val, target) {
      if (val == null) return '';
      var t = (target == null || target === 0) ? '' : ' <span class="mm-t">/ ' + target + '</span>';
      return '<div class="audit-metric"><span>' + esc(label) + '</span><b>' + esc(val) + t + '</b></div>';
    };

    return '<article class="audit-card ' + (AGRADE[p.grade] || '') + '">' +
      '<div class="audit-card-head">' +
        '<div class="audit-title-wrap">' +
          '<div class="audit-tags"><span class="audit-form">' + esc(p.formLabel) + '</span>' +
            '<span class="audit-grade ' + (AGRADE[p.grade] || '') + '">' + esc(p.grade) + '</span>' +
            gate +
            (p.benchmarkReliable === false ? '<span class="audit-warn">基准样本 ' + (p.viralSample || 0) + ' 条，仅供参考</span>' : '') +
          '</div>' +
          '<h3>' + esc(p.title) + '</h3>' +
          '<p class="audit-sub">' + esc(p.file || '') + ' · 爆款基准 ' + esc(p.formLabel) + '</p>' +
        '</div>' +
        '<div class="audit-score"><b>' + p.score + '</b><span>分</span></div>' +
      '</div>' +
      '<div class="audit-metrics">' +
        numMeta('字数', m.wordCount, bench.wordCount ? Math.round(bench.wordCount) : null) +
        numMeta('配图', m.images, bench.images != null ? bench.images : null) +
        numMeta('小标题', m.subheads, null) +
        numMeta('首段', m.firstParaLen + ' 字', null) +
        numMeta('段落', m.paragraphs, null) +
      '</div>' +
      '<div class="audit-checks">' + bars + '</div>' +
      gapBlock +
    '</article>';
  }

  function renderAudit() {
    var a = state.audit;
    var list = document.getElementById('auditList');
    var empty = document.getElementById('auditEmpty');
    if (!a || !a.pieces || !a.pieces.length) {
      list.innerHTML = '';
      empty.hidden = false;
      document.getElementById('auditSummary').innerHTML = '';
      document.getElementById('auditFormBar').innerHTML = '';
      document.getElementById('auditUpdated').textContent = '等待自检数据';
      return;
    }
    empty.hidden = true;
    document.getElementById('auditUpdated').textContent = '自检于 ' + fmt(a.updatedAt) + ' · ' + a.total + ' 篇 · 爆款库 ' + (a.viralTotal || 0) + ' 条';

    var cov = a.coverage || picksCoverage();
    var covTitle = cov.ok ? '选题池里每个选题都有对应成品稿' : '缺稿：' + (cov.missing || []).join('；');
    var g = a.grades || {};
    var passScore = (state.issue || {}).passScore || 85;
    var now0 = new Date();
    var todayStr = now0.getFullYear() + '-' + pad2(now0.getMonth() + 1) + '-' + pad2(now0.getDate());
    var todayPieces = (a.pieces || []).filter(function (p) { return p.date === todayStr; });
    var todayPass = todayPieces.filter(function (p) { return p.score >= passScore; }).length;
    var todayFail = todayPieces.length - todayPass;
    document.getElementById('auditSummary').innerHTML =
      '<div class="audit-sum-box ' + (todayFail ? 'g-near' : 'g-ok') + '" title="今天的稿里，≥' + passScore + ' 分的进发布池，其余淘汰">' +
        '<span>今日过闸&nbsp;</span><b>' + todayPass + ' 过 / ' + todayFail + ' 汰</b></div>' +
      '<div class="audit-sum-box ' + (cov.ok ? 'g-ok' : 'g-near') + '" title="' + esc(covTitle) + '"><span>出稿覆盖&nbsp;</span><b>' + cov.covered + '/' + cov.total + '</b></div>' +
      '<div class="audit-sum-box"><span>全部均分</span><b>' + a.avgScore + '</b></div>' +
      '<div class="audit-sum-box g-ok"><span>达标 ≥' + passScore + '</span><b>' + (g['达标'] || 0) + '</b></div>' +
      '<div class="audit-sum-box g-near"><span>接近 70-84</span><b>' + (g['接近'] || 0) + '</b></div>' +
      '<div class="audit-sum-box g-bad"><span>不达标 &lt;70</span><b>' + (g['不达标'] || 0) + '</b></div>' +
      (a.byForm || []).map(function (f) {
        return '<div class="audit-sum-box mini"><span>' + esc(f.formLabel) + '</span><b>' + f.avgScore + '</b></div>';
      }).join('');

    // 筛选条每次重建，避免 state 切换后残留旧按钮
    var bar = document.getElementById('auditFormBar');
    bar.innerHTML = '';
    var scope = document.createElement('button');
    scope.className = 'vform-chip scope' + (state.auditToday ? ' on' : '');
    scope.textContent = state.auditToday ? '只看今天（' + todayPieces.length + '）' : '看全部历史（' + (a.total || 0) + '）';
    scope.onclick = function () { state.auditToday = !state.auditToday; renderAudit(); };
    bar.appendChild(scope);

    var opts = [['', '全部形态']].concat((a.byForm || []).map(function (f) { return [f.form, f.formLabel + ' ' + f.count]; }));
    opts.forEach(function (kv) {
      var b = document.createElement('button');
      b.className = 'vform-chip' + (kv[0] === state.auditForm ? ' on' : '');
      b.textContent = kv[1];
      b.setAttribute('data-form', kv[0]);
      b.onclick = function () {
        state.auditForm = kv[0];
        renderAudit();
      };
      bar.appendChild(b);
    });

    var rows = (a.pieces || []).filter(function (p) {
      if (state.auditToday && p.date !== todayStr) return false;
      if (state.auditForm && p.form !== state.auditForm) return false;
      return true;
    });
    rows.sort(function (x, y) { return x.score - y.score; });
    list.innerHTML = rows.map(auditCardHtml).join('') || '<div class="empty">该条件下暂无成品稿。</div>';
  }

  function renderBenchmark() {    document.getElementById('benchBody').innerHTML = benchTableHtml() || '<tr><td colspan="6">暂无对标数据</td></tr>';
    var m = state.viral.meta || {};
    document.getElementById('benchUpdated').textContent = m.updatedAt ? '更新于 ' + fmt(m.updatedAt) + ' · ' + (m.total || 0) + ' 条爆款' : '等待爆款数据';
    var chips = document.getElementById('viralFormChips');
    if (!chips.childElementCount) {
      var keys = [['', '全部'], ['gzh-article', '公众号文章'], ['gzh-poster', '公众号贴图'], ['tt-article', '头条文章'], ['tt-micro', '微头条']];
      keys.forEach(function (kv) {
        var b = document.createElement('button');
        b.className = 'vform-chip' + (kv[0] === '' ? ' on' : '');
        b.textContent = kv[1]; b.setAttribute('data-form', kv[0]);
        b.onclick = function () {
          state.viralForm = kv[0];
          Array.prototype.forEach.call(chips.children, function (c) { c.classList.toggle('on', c === b); });
          renderBenchmark();
        };
        chips.appendChild(b);
      });
    }
    var rows = viralFiltered();
    document.getElementById('viralCount').textContent = '显示 ' + rows.length + ' 条爆款（已按平台隔离：公众号仅微信原文、头条仅头条原文；基准为公开可见信息估算，非精确实测）';
    document.getElementById('viralEmpty').hidden = rows.length > 0;
    document.getElementById('viralGrid').innerHTML = rows.map(viralCardHtml).join('');
    Array.prototype.forEach.call(document.querySelectorAll('.viral-detail'), function (b) {
      b.onclick = function () { openViral(b.getAttribute('data-id')); };
    });
  }

  function viralFullText(it) {
    var an = it.anatomy || {}, vs = it.viralScore || {};
    var lines = ['【爆款拆解 · ' + (VFORM[it.form] || '') + '】' + it.title,
      '账号：' + (it.account || '') + ' · 平台：' + (it.platform || '') + ' · 原文域名：' + (it.sourceHost || '未标注'),
      '爆款指数：' + vs.total + ' 分（' + (VTIER[vs.tier] || {}).label + '）',
      '', '【形态拆解】',
      '字数：' + (an.wordCount != null ? an.wordCount : '—') + '　配图：' + (an.images != null ? an.images : '—') + '　小标题：' + (an.subheads != null ? an.subheads : '—'),
      '标题套路：' + (an.titlePattern || ''),
      '开头钩子：' + (an.hook || ''),
      '', '结构：', (an.structure || []).map(function (x, i) { return (i + 1) + '. ' + x; }).join('\n'),
      '', '重点手法：', (an.highlightSkills || []).map(function (x, i) { return (i + 1) + '. ' + x; }).join('\n'),
      '', '可借鉴：', (an.lessons || []).map(function (x, i) { return (i + 1) + '. ' + x; }).join('\n'),
      '', '评分明细：', (vs.breakdown || []).map(function (b) { return b.label + ' +' + b.points + '（' + b.note + '）'; }).join('\n'),
      '', '信号来源：' + ((it.signals || {}).source || '不可见'),
      '核实：' + ((it.verification || {}).status || '') + ' · ' + ((it.verification || {}).notes || ''),
      '原文：' + (it.url || '')];
    return lines.join('\n');
  }

  function openViral(id) {
    var it = (state.viral.items || []).find(function (x) { return x.id === id; });
    if (!it) return;
    state.viralOpen = it;
    var an = it.anatomy || {}, vs = it.viralScore || {}, sig = it.signals || {}, v = it.verification || {};
    var url = safeUrl(it.url);
    var tier = VTIER[vs.tier] || VTIER.C;
    document.getElementById('viralBody').innerHTML =
      '<div class="vdetail-head">' +
        '<span class="vform">' + esc(VFORM[it.form] || it.form) + '</span>' +
        '<span class="vplat">' + esc(it.platform || FORM_PLATFORM[it.form] || '') + '</span>' +
        '<span class="vtier t-' + tier.cls + '">' + esc(tier.label) + '</span>' +
        '<span class="vscore"><b>' + (vs.total || 0) + '</b> 分</span>' +
      '</div>' +
      '<h2 id="viralDetailTitle">' + esc(it.title) + '</h2>' +
      '<p class="vdetail-sub">' + esc(it.account || '') + ' · ' + esc(it.platform || '') + ' · ' + (it.sourceHost ? '原文域名 ' + esc(it.sourceHost) : '无公开直链（客户端补录）') + ' · ' + esc(it.category || '') + ' · ' + esc(fmt(it.publishedAt || it.collectedAt)) + '</p>' +
      '<p class="vdetail-summary">' + esc(it.summary || '') + '</p>' +
      '<div class="vdetail-metrics">' +
        '<div><span>正文字数</span><b>' + (an.wordCount != null ? an.wordCount : '—') + '</b></div>' +
        '<div><span>配图</span><b>' + (an.images != null ? an.images : '—') + '</b></div>' +
        '<div><span>小标题</span><b>' + (an.subheads != null ? an.subheads : '—') + '</b></div>' +
        '<div><span>信号来源</span><b class="small">' + esc(sig.source || '不可见') + '</b></div>' +
      '</div>' +
      '<div class="vdetail-signals"><b>可见信号</b>　阅读：' + esc(sig.views || '不可见') + '　点赞：' + esc(sig.likes || '不可见') + '　评论：' + esc(sig.comments || '不可见') + '　转发：' + esc(sig.shares || '不可见') + (it.ranking ? '<br><b>榜单：</b>' + esc(it.ranking.name || '') + ' · ' + esc(it.ranking.position || '') : '') + '</div>' +
      '<section class="vdetail-sec"><h3>标题套路 & 开头钩子</h3><p><b>套路：</b>' + esc(an.titlePattern || '—') + '</p><p><b>钩子：</b>' + esc(an.hook || '—') + '</p></section>' +
      '<section class="vdetail-sec"><h3>结构拆解</h3><ol>' + (an.structure || []).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ol></section>' +
      '<section class="vdetail-sec"><h3>重点突出手法</h3><ul>' + (an.highlightSkills || []).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></section>' +
      '<section class="vdetail-sec lessons"><h3>可借鉴点（写给下次的我们）</h3><ol>' + (an.lessons || []).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ol></section>' +
      '<section class="vdetail-sec"><h3>爆款指数明细</h3>' + (vs.breakdown || []).map(function (b) {
        return '<p class="vbreak"><span>' + esc(b.label) + '</span><b>+' + b.points + '</b><small>' + esc(b.note) + '</small></p>';
      }).join('') + '<p class="vmethod">' + esc(vs.method || '') + '</p></section>' +
      '<section class="vdetail-sec"><h3>资料核实</h3><p>状态：' + esc(v.status || '未核实') + '</p><p>方法：' + esc(v.method || '') + '</p><p class="vnotes">存疑：' + esc(v.notes || '无') + '</p></section>' +
      '<div class="vdetail-actions">' + (url ? '<a class="btn" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">打开原文 ↗</a>' : '') + '</div>';
    document.getElementById('viralMask').hidden = false;
  }

  function closeViral() { document.getElementById('viralMask').hidden = true; state.viralOpen = null; }

  // ===== 今日素材（issue）：公众号池 + 头条池，发布人自己挑时段 =====
  function issueAsset(a) {
    var thumbs = (a.images || []).map(function (im, i) {
      var name = (a.slug || 'img') + '-' + (i + 1) + '.jpeg';
      return '<a class="ic-thumb" href="' + esc(im.src) + '" download="' + esc(name) + '" target="_blank" rel="noopener" title="' + esc(im.caption || ('图 ' + (i + 1))) + '">' +
        '<img src="' + esc(im.src) + '" alt="" loading="lazy"><i>图' + (i + 1) + ' ↓</i></a>';
    }).join('');
    var first = (a.images || [])[0];
    var cover = first
      ? '<div class="ia-cover"><img src="' + esc(first.src) + '" alt="' + esc(first.caption || '') + '" loading="lazy">' +
        '<span class="ia-cover-tag">封面 · 共 ' + a.imageCount + ' 图</span></div>'
      : '';
    var ORIGIN = { source: '原文图', doubao: 'AI 生成', chatgpt: 'AI 生成', card: '自制卡' };
    var origins = (a.imageOrigins || []).map(function (o) { return ORIGIN[o] || ''; }).filter(function (v, i, arr) { return v && arr.indexOf(v) === i; });
    var originChip = origins.length
      ? '<span class="ia-origin' + (origins.indexOf('原文图') === 0 ? ' is-src' : '') + '" title="' + esc(a.imageNote || '') + '">' + esc(origins.join('+')) + '</span>'
      : '';
    return '<article class="ia-card" data-item="' + esc(a.itemId) + '" data-piece="' + esc(a.pieceId) + '">' +
      cover +
      '<div class="ia-top">' +
        '<span class="ia-form f-' + esc(a.pieceId) + '">' + esc(a.formShort) + '</span>' +
        originChip +
        '<span class="ia-num"><b>' + a.words + '</b> 字</span>' +
        '<span class="ia-num"><b>' + a.imageCount + '</b> 图</span>' +
        '<span class="dstate pass" title="自检分数，≥' + esc((state.issue || {}).passScore || 85) + ' 分才进发布池">自检 <b>' + (a.score != null ? a.score : '—') + '</b></span>' +
        '<span class="vpill v-' + esc(statusClass(a.verification)) + '">' + esc(a.verification || '未核实') + '</span>' +
      '</div>' +
      '<h3 class="ia-title">' + esc(a.title) + '</h3>' +
      (a.digest ? '<p class="ia-digest">' + esc(a.digest) + '</p>' : '') +
      '<div class="ia-foot">' +
        '<div class="ia-actions">' +
          '<button class="ic-btn primary" data-act="copy">复制全文</button>' +
          '<button class="ic-btn" data-act="title">复制标题</button>' +
          (a.imageCount ? '<button class="ic-btn" data-act="imgs">图片（' + a.imageCount + '）</button>' : '') +
          '<button class="ic-btn ghost" data-act="open">看排版</button>' +
        '</div>' +
        '<span class="ia-src" title="' + esc(a.sourceTitle) + '">' + esc(a.sourceTitle || '') + '</span>' +
      '</div>' +
      '<div class="ic-imgs" hidden>' + thumbs + '</div>' +
      '</article>';
  }

  function renderIssue() {
    var it = state.issue;
    var list = document.getElementById('issueList');
    var empty = document.getElementById('issueEmpty');
    if (!it || !it.pools) {
      list.innerHTML = '';
      empty.hidden = false;
      document.getElementById('issueDate').textContent = '—';
      document.getElementById('issueState').textContent = '—';
      return;
    }
    empty.hidden = true;
    document.getElementById('issueDate').textContent = it.date;

    var gzh = it.pools['公众号'] || { items: [], target: 6 };
    var tt = it.pools['今日头条'] || { items: [], target: 8 };
    var ok = it.status === 'ready';
    var gzhTarget = gzh.target || 6;
    var ttTarget = tt.target || 8;
    var st = document.getElementById('issueState');
    st.className = 'issue-state ' + (ok ? 'ok' : 'warn');
    var dupN = (it.duplicates || []).length;
    st.innerHTML = '<b>公众号 ' + gzh.items.length + '/' + gzhTarget + ' · 头条 ' + tt.items.length + '/' + ttTarget + '</b>' +
      (dupN ? '<span class="dup-chip">合并重复 ' + dupN + ' 篇</span>' : '') +
      '<span>' + (it.stale
        ? '最近一版 · ' + esc((gzh.items[0] || tt.items[0] || {}).date || '')
        : (it.generatedAt ? String(it.generatedAt).slice(11, 16) + ' 备齐' : '')) + '</span>';

    var callout = document.getElementById('issueCallout');
    if (it.stale) {
      callout.hidden = false;
      callout.className = 'issue-callout warn';
      callout.innerHTML = '<b>今天（' + esc(it.date) + '）的素材还没生成。</b>' +
        '下面是最近一版（' + esc((gzh.items[0] || tt.items[0] || {}).date || '') + '），只能应急；标题和开头里的时间点必须自己改成今天。';
    } else if (!ok) {
      callout.hidden = false;
      callout.className = 'issue-callout warn';
      callout.innerHTML = '<b>' + esc(it.note || '素材没备齐') + '</b>　够发的先发，缺的部分下一轮会补。';
    } else {
      callout.hidden = true;
    }

    // 被淘汰的稿不进发布池，但在这一步留痕：谁被淘汰、多少分、差在哪
    var rjBox = document.getElementById('issueRejected');
    var rejected = it.rejected || [];
    var pending = it.pending || [];
    if (rejected.length || pending.length) {
      rjBox.hidden = false;
      var rjList = rejected.map(function (r) {
        return '<li>' + esc(r.formLabel) + '　<span class="rj-score">' + (r.score == null ? '—' : r.score) + ' 分</span>　' + esc(r.title) +
          ((r.gaps || []).length ? '　<small>差在：' + esc((r.gaps || []).map(function (g) { return g.dim || g; }).join('、')) + '</small>' : '') + '</li>';
      }).join('');
      var pdList = pending.map(function (p) {
        return '<li>' + esc(p.formLabel) + '　' + esc(p.title) + '　<small>还没跑自检</small></li>';
      }).join('');
      rjBox.innerHTML = '<b>自检没过的 ' + (rejected.length + pending.length) + ' 篇已挡在发布池外</b>' +
        '<ul>' + rjList + pdList + '</ul>' +
        '<span class="rj-note">淘汰是常态：宁可不发，也不发没把握的。要救回就改稿后重跑自检。</span>';
    } else {
      rjBox.hidden = true;
    }

    var groups = [
      { key: '公众号', pool: gzh, desc: (it.usage || {})['公众号'] || '每天 1 篇，从池子里挑' },
      { key: '今日头条', pool: tt, desc: (it.usage || {})['今日头条'] || '每天 3 篇，从池子里挑' }
    ];
    list.innerHTML = groups.map(function (g) {
      var items = g.pool.items || [];
      return '<section class="ia-group">' +
        '<div class="ia-ghead"><h3>' + esc(g.key) + '</h3>' +
          '<span class="ia-gcount">已备 <b>' + items.length + '</b> 篇' +
            (items.length < (g.pool.target || 0) ? '（目标 ' + g.pool.target + '）' : '') + '</span>' +
          '<span class="ia-gdesc">' + esc(g.desc) + '</span></div>' +
        (items.length
          ? '<div class="ia-grid' + (g.key === '公众号' ? ' two' : '') + '">' + items.map(issueAsset).join('') + '</div>'
          : '<p class="ia-none">这个池还没有素材。</p>') +
        '</section>';
    }).join('');

    Array.prototype.forEach.call(list.querySelectorAll('.ia-card'), function (card) {
      Array.prototype.forEach.call(card.querySelectorAll('.ic-btn'), function (b) {
        b.onclick = function () {
          var itemId = card.getAttribute('data-item');
          var pieceId = card.getAttribute('data-piece');
          var a = null;
          ['公众号', '今日头条'].some(function (k) {
            var hit = ((it.pools[k] || {}).items || []).filter(function (x) {
              return x.itemId === itemId && x.pieceId === pieceId;
            })[0];
            if (hit) a = hit;
            return !!hit;
          });
          if (!a) return;
          var act = b.getAttribute('data-act');
          if (act === 'copy') copyText(a.text || '', b);
          else if (act === 'title') copyText(a.title || '', b);
          else if (act === 'imgs') {
            var box = card.querySelector('.ic-imgs');
            box.hidden = !box.hidden;
            b.textContent = box.hidden ? ('图片（' + a.imageCount + '）') : '收起图片';
          } else if (act === 'open') openDraft(itemId, pieceId);
        };
      });
    });
  }

  function renderPicks() {
    var p = state.picks;
    var groupsEl = document.getElementById('picksGroups');
    if (!p || !p.groups) {
      document.getElementById('picksDate').textContent = '暂无选题数据';
      renderWindows();
      document.getElementById('picksStat').textContent = '';
      groupsEl.innerHTML = '<div class="picks-empty">今日选题尚未生成，等待定时任务运行或手动执行评分脚本。</div>';
      return;
    }
    document.getElementById('picksDate').textContent = p.date + ' · 今日选题';
    renderWindows();
    var total = 0;
    Object.keys(p.groups).forEach(function (k) { total += (p.groups[k] || []).length; });
    var gzhN = (p.groups['公众号'] || []).length;
    var ttN = (p.groups['今日头条'] || []).length;
    // 选题条数 ≠ 事件数：同一事件会出公众号版和头条版，这里两个数都摆出来，避免误读
    var events = {}, have = {};
    Object.keys(p.groups).forEach(function (k) {
      (p.groups[k] || []).forEach(function (r) { if (r.itemId) events[r.itemId] = 1; });
    });
    ((state.ready || {}).docs || []).forEach(function (d) { if (d.sourceItemId) have[d.sourceItemId] = 1; });
    var evIds = Object.keys(events);
    var evCovered = evIds.filter(function (id) { return have[id]; }).length;
    var covOk = evIds.length > 0 && evCovered === evIds.length;
    document.getElementById('picksStat').innerHTML = '<b>' + total + '</b> 个选题' +
      '<span>公众号 ' + gzhN + ' · 头条 ' + ttN + '</span>' +
      '<span>来自 ' + evIds.length + ' 个事件</span>' +
      '<span class="picks-cov ' + (covOk ? 'ok' : 'warn') + '">出稿覆盖 ' + evCovered + '/' + evIds.length + '</span>';

    var html = '';
    ['公众号', '今日头条'].forEach(function (target) {
      var rows = p.groups[target] || [];
      if (!rows.length) return;
      html += '<div class="picks-group"><div class="picks-group-head"><span class="target-badge l-' + esc(target) + '">' + esc(target) + '</span><span>TOP ' + rows.length + '</span></div>';
      html += '<div class="picks-cards">' + rows.map(pickCardHtml).join('') + '</div></div>';
    });
    groupsEl.innerHTML = html;

    Array.prototype.forEach.call(groupsEl.querySelectorAll('.view-draft'), function (b) {
      b.onclick = function () { openDraft(b.getAttribute('data-item')); };
    });
    // 选题卡上的形态徽章直接打开对应成品稿，省一次点击
    Array.prototype.forEach.call(groupsEl.querySelectorAll('.pick-drafts .dstate'), function (b) {
      b.onclick = function () { openDraft(b.getAttribute('data-item'), b.getAttribute('data-piece')); };
    });
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
    if (state.view === 'benchmark') { renderBenchmark(); return; }
    if (state.view === 'audit') { renderAudit(); return; }
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
