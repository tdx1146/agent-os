
// ── 状态层 ──────────────────────────────────────────────────────────────────
const store = {
  msgCache: [], pairs: [], currentPage: 0, totalPages: 0,
};
// 全局别名
['msgCache','pairs','currentPage','totalPages']
  .forEach(k => Object.defineProperty(window, k, { get: () => store[k], set: v => store[k] = v }));

// Helper: 安全和并批量更新 store
function storeSet(updates) { Object.assign(store, updates); }

// 自动轮询追踪器
let _lastAsstLen = 0;
let _lastRefreshCount = 0;

// ── API 层 ──────────────────────────────────────────────────────────────────
const api = {
  _t: () => '?t=' + Date.now(),
  async get(path) {
    const r = await fetch(path + (path.includes('?') ? '&' : '?') + 't=' + Date.now());
    if (!r.ok) throw new Error('API ' + r.status + ': ' + path);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: body !== undefined ? JSON.stringify(body) : '{}'
    });
    if (!r.ok) throw new Error('API ' + r.status + ': ' + path);
    return r.json();
  },
  // ── 各端点 ──
  session:       () => api.get('/api/session'),
  sessionFresh:  () => api.get('/api/session?fresh=1'),
  sessionRpc:    () => api.get('/api/session-rpc'),
  status:        () => api.get('/api/status'),
  cacheStats:    () => api.get('/api/cache-stats'),
  backups:       () => api.get('/api/backups'),
  backupStale:   () => api.get('/api/backup-stale'),
  digestSkill:   () => api.get('/api/digestion-skill'),
  thinkingStatus:() => api.get('/api/thinking-status'),
  weaponryToggle:() => api.get('/api/weaponry-toggle'),
  memoryFiles:   () => api.get('/api/memory-files'),
  memoryFile:    (name, content) => content ? api.post('/api/memory-file', {name, content}) : api.get('/api/memory-file?name=' + encodeURIComponent(name)),
  reminders:     () => api.get('/api/reminders'),
  remindersAdd:  (t, a) => api.post('/api/reminders', {text: t, assignee: a}),
  remindersDone: (i) => api.post('/api/reminders', {done: i}),
  remindersClearDone: () => api.post('/api/reminders', {clear_done: true}),
  momo:          (s, extra) => api.post('/api/momo', Object.assign({sub_action: s}, extra)),
  systemHealth:  () => api.get('/api/system-health'),
  secretaryLog:  () => api.get('/api/secretary-log'),
  tbRead:        (p, pw) => api.get('/api/tb-read-file?path=' + encodeURIComponent(p) + '&pw=' + encodeURIComponent(pw||'')),
  tbSave:        (p, c) => api.post('/api/tb-save-file', {path: p, content: c}),
  listFiles:     (p) => api.get('/api/list-files?path=' + encodeURIComponent(p||'')),
  browseDirs:    () => api.get('/api/browse-dirs'),
  listSessions:  () => api.get('/api/list-sessions'),
  switchSession: (k) => api.get('/api/switch-session?key=' + encodeURIComponent(k)),
  deleteSession: (k) => api.get('/api/delete-session?key=' + encodeURIComponent(k)),
  abort:         () => api.post('/api/abort'),
  inject:        (m) => api.post('/api/inject', {message: m}),
  injectFeeling: (t) => api.post('/api/momo', {sub_action: 'inject_feeling', feeling: t}),
  clearLock:     () => api.post('/api/clear-inject-lock'),
  edit:          (i, t, a) => api.post('/api/edit', {index: i, text: t, approved: !!a}),
  tbCreate:      (f, n, d) => api.post('/api/tb-create-file', {folder: f, name: n, is_dir: !!d}),
  tbDelete:      (p) => api.post('/api/tb-delete-file', {path: p}),
  tbRename:      (o, n, f) => api.post('/api/tb-rename-file', {old_path: o, new_name: n, new_folder: f || ''}),
  subagentHist:  () => api.get('/api/subagent-history'),
  subagentsList:  () => api.get('/api/subagents'),
  trimSession:   () => api.post('/api/trim-session'),
  pet:           () => api.post('/api/pet-me'),
  restartHttp:   () => api.post('/api/restart-http'),
  awakeList:     () => api.get('/api/awake-questions/list'),
  awakeSave:     (c) => api.post('/api/awake-questions/save', {content: c}),
  spawnSubagent: (t, m) => api.post('/api/spawn-subagent', {task: t, model: m}),
};

// ── Markdown 渲染 ──────────────────────────────────────────────────────────
function renderMarkdown(html) {
  // html 已 escape，安全处理 markdown 语法
  // 1. 代码块（必须最先处理，避免内部被误转）
  html = html.replace(/~~~([\s\S]*?)~~~/g, '<pre><code>$1</code></pre>');
  html = html.replace(/\`\`\`([\s\S]*?)\`\`\`/g, '<pre><code>$1</code></pre>');
  // 2. 表格
  html = html.replace(/(^|\n)(\|[^\n]+\|(?:\n\|[^\n]+\|)+)/gm, function(m, before, tableBlock) {
    var rows = tableBlock.trim().split('\n');
    var isHeader = true;
    var thead = '', tbody = '';
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var cols = row.split('|').filter(function(c){ return c.trim() !== ''; });
      if (cols.length > 0 && /^[\s:-]+$/.test(cols.join(''))) continue;
      if (isHeader) {
        thead += '<tr>' + cols.map(function(c){ return '<th>' + c.trim() + '</th>'; }).join('') + '</tr>';
        isHeader = false;
      } else {
        tbody += '<tr>' + cols.map(function(c){ return '<td>' + c.trim() + '</td>'; }).join('') + '</tr>';
      }
    }
    var tbl = '<table>';
    if (thead) tbl += '<thead>' + thead + '</thead>';
    if (tbody) tbl += '<tbody>' + tbody + '</tbody>';
    tbl += '</table>';
    return before + tbl;
  });
  // 3. 行内代码
  html = html.replace(/\`([^`]+)\`/g, '<code>$1</code>');
  // 4. 粗体 + 斜体
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // 5. 行内链接
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:#58a6ff">$1</a>');
  return html;
}

let cachePanelOpen = false;
function toggleCachePanel() {
  cachePanelOpen = !cachePanelOpen;
  var el = document.getElementById('cache-detail');
  var toggler = document.getElementById('cache-toggle');
  if (!el || !toggler) return;
  el.style.display = cachePanelOpen ? 'block' : 'none';
  toggler.textContent = cachePanelOpen ? '▼' : '▶';
  if (cachePanelOpen && typeof loadCacheStats === 'function') loadCacheStats();
}

// ── 上下文监控 ──
function updateContextDisplay() {
  api.status().then(function(d) {
    if (!d.ok) return;
    var pct = d.percent || 0;
    var fill = document.getElementById('ctx-bar-fill');
    if (fill) {
      fill.style.width = Math.min(pct, 100) + '%';
      fill.style.background = pct > 90 ? '#f85149' : pct > 75 ? '#d29922' : '#58a6ff';
    }
    var el = document.getElementById('ctx-display');
    if (el) el.innerHTML = '📚 上下文: <b>' + fmtNum(d.totalTokens||0) + '</b>/' + fmtNum(d.contextTokens||0) + ' (' + pct + '%)' + ' · ' + fmtNum(d.inputTokens||0) + ' in / ' + fmtNum(d.outputTokens||0) + ' out';
    var cel = document.getElementById('cache-display');
    if (cel) cel.textContent = '🗄️ 缓存: ' + fmtNum(d.cacheRead||0);
    var cmpel = document.getElementById('comp-display');
    if (cmpel) cmpel.textContent = '🧹 压缩: ' + (d.compactionCount||0) + '次';
    var trimel = document.getElementById('trim-count');
    if (trimel) trimel.textContent = d.trimCount || 0;
  }).catch(function(){});
}
updateContextDisplay();
setInterval(updateContextDisplay, 20000);

// ── 上轮缓存直接更新（不走组件系统，稳）──
function updateCachePct() {
  api.cacheStats().then(function(d) {
    if (!d.ok) return;
    // 兼容新版(stats.latest_round)和旧版(previousRound)
    var prev = d.stats ? d.stats.latest_round : (d.previousRound || (d.rounds && d.rounds[d.rounds.length - 1]));
    if (!prev) return;
    var el = document.getElementById('cache-summary');
    if (!el) return;
    var pct = prev.cachePct;
    var cls = pct < 50 ? '#f85149' : pct < 90 ? '#d29922' : '#58a6ff';
    el.innerHTML = '<span style="color:' + cls + '">' + pct + '%</span>' +
      ' · input ' + fmtNum(prev.input) + ' · cache ' + fmtNum(prev.cacheRead) +
      ' · ¥' + prev.cost;
  }).catch(function(){});
}
setInterval(updateCachePct, 20000);
// 首次渲染由 dashboard.js boot 结束后触发


// ── 🌀 自动轮询：每3秒检查新消息 ──
var _lastPairCount = 0;
var _pollTimer = setInterval(async function() {
  // 🔧 修复：编辑面板打开时不刷新 pairs，防止正在编辑时 store.pairs 被覆盖
  if (document.getElementById('edit-panel')) return;
  try {
    var r = await fetch("/api/session?fresh=1&t=" + Date.now());
    var d = await r.json();
    if (d.pairs && d.pairs.length > 0) {
      var changed = d.pairs.length !== _lastPairCount;
      // 内容级检测：比较最新一条消息的 assistant 回复
      if (!changed && store.pairs && store.pairs.length > 0 && d.pairs.length > 0) {
        var a0 = store.pairs[0];
        var b0 = d.pairs[0];
        if (a0 && b0) {
          var aTxt = (a0.assistants || []).map(function(a){return (a.text||'').slice(0,50);}).join('');
          var bTxt = (b0.assistants || []).map(function(a){return (a.text||'').slice(0,50);}).join('');
          if (aTxt !== bTxt) changed = true;
        }
      }
      if (changed) {
        _lastPairCount = d.pairs.length;
        _lastRenderHash = '';
        // 用 refresh 完整拉取，不手动操作 store
        if (typeof refresh === 'function') {
          refresh();
        } else {
          var cur = (typeof store.currentPage !== 'undefined') ? store.currentPage : 0;
          storeSet({ msgCache: d.messages || [], pairs: d.pairs, totalPages: d.pairs.length, currentPage: cur });
          if (typeof renderPage === 'function') renderPage();
        }
      }
    }
  } catch(e) {}
}, 3000);

// ── 工具函数 ────────────────────────────────────────────────────────────────
function fmtNum(n) {
  if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n/1000).toFixed(1) + 'k';
  return String(n);
}

function escapeHtml(str) {
  if (typeof str !== 'string') return String(str || '');
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Toast ──────────────────────────────────────────────────────────────────
function toast(msg, isError) {
  var el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.style.background = isError ? '#3d1111' : '#1c2128';
  el.style.borderColor = isError ? '#f85149' : '#30363d';
  el.style.color = isError ? '#f85149' : '#c9d1d9';
  el.classList.add('show');
  clearTimeout(el._hide);
  el._hide = setTimeout(function() { el.classList.remove('show'); }, 3000);
}

// ── 初始加载 ───────────────────────────────────────────────────────────
async function refresh() {
  try {
    var d = await api.sessionFresh();
    if (d && d.pairs) {
      // 如果 store 有乐观消息（比后端多 1 轮），保留它
      if (store.pairs.length > d.pairs.length && window._optimisticText) {
        // 检查乐观消息是否已被后端收录
        var foundInBackend = d.pairs.some(function(p) {
          return p.user && p.user.text === window._optimisticText;
        });
        if (foundInBackend) {
          window._optimisticText = null;
          store.pairs = d.pairs;
          store.totalPages = d.pairs.length;
        }
        // _lastPairCount 不更新，保持比后端多 1，下次轮询会再检测到变化
      } else {
        store.pairs = d.pairs;
        store.totalPages = d.pairs.length;
        _lastPairCount = d.pairs.length;
      }
      if (store.pairs.length > 0 && typeof renderPage === 'function') renderPage();
    }
  } catch(e) {}
}

refresh();
updateContextDisplay();

// ── 待重发缓存 ───────────────────────────────────────────────────────────
function _renderSentCache() {
  var caches = JSON.parse(localStorage.getItem('sentCache') || '[]');
  var recent = caches.slice(-20);
  var el = document.getElementById('sent-cache-panel');
  if (!el) {
    el = document.createElement('div');
    el.id = 'sent-cache-panel';
    el.style.cssText = 'margin-top:6px;font-size:11px;max-height:120px;overflow-y:auto;background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:4px 6px;display:none';
    var after = document.getElementById('awake-status');
    if (after && after.parentNode) after.parentNode.appendChild(el);
  }
  var unsent = recent.filter(function(c) { return !c.sent; });
  if (unsent.length === 0) { el.style.display = 'none'; return; }
  el.style.display = 'block';
  el.innerHTML = '<div style="color:#f0883e;margin-bottom:2px">📋 待重发 (' + unsent.length + ')</div>' +
    unsent.slice(-5).reverse().map(function(c) {
      var txt = c.text.length > 40 ? c.text.slice(0,40) + '…' : c.text;
      return '<div style="display:flex;gap:4px;margin:2px 0;align-items:center">' +
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#c9d1d9">' + escapeHtml(txt) + '</span>' +
        '<button onclick="sentRetry(' + caches.indexOf(c) + ')" style="padding:1px 6px;font-size:10px;background:#238636;color:#fff;border:none;border-radius:3px;cursor:pointer">重发</button>' +
        '<button onclick="sentEdit(' + caches.indexOf(c) + ')" style="padding:1px 6px;font-size:10px;background:#1f6feb;color:#fff;border:none;border-radius:3px;cursor:pointer">编辑</button>' +
        '</div>';
    }).join('');
}
function sentRetry(idx) {
  var caches = JSON.parse(localStorage.getItem('sentCache') || '[]');
  var entry = caches[idx];
  if (!entry) return;
  document.getElementById('awake-editor').value = entry.text;
  entry.sent = true;
  localStorage.setItem('sentCache', JSON.stringify(caches));
  _renderSentCache();
}
function sentEdit(idx) {
  var caches = JSON.parse(localStorage.getItem('sentCache') || '[]');
  var entry = caches[idx];
  if (!entry) return;
  document.getElementById('awake-editor').value = entry.text;
  caches.splice(idx, 1);
  localStorage.setItem('sentCache', JSON.stringify(caches));
  _renderSentCache();
}
