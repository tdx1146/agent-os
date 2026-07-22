// components.js — 轻如烟 UI 组件（每位组件只写自己的 DOM 容器）
// 通过 CL.register() 注册，不污染全局作用域

// ── 1. 上轮缓存（由 core.js 的 updateCachePct 接管）──
CL.register('cacheSummary', {
  container: 'cache-summary',
  parent: 'context-bar',
  init: function(ctx) { /* core.js 的 updateCachePct 全权负责 */ },
  render: function(ctx, el) {
    if (typeof updateCachePct === 'function') updateCachePct();
  }
});

// ── 2. 会话选择器 ────────────────────────────────────────────────────────
CL.register('sessionSelector', {
  container: 'serverInfo',
  parent: 'app',
  init: function(ctx) {
    ctx._list = [];
    ctx._open = false;
    ctx._current = 'agent:main:main';
    // 启动时立即加载会话列表
    var self = ctx;
    api.listSessions().then(function(list) { 
      self._list = list || []; 
      CL.render('sessionSelector'); 
    }).catch(function(){});
    ctx.render(ctx, ctx.el);
    setInterval(function() {
      // 每20秒刷新会话列表
      api.listSessions().then(function(list) {
        if (list) self._list = list;
        CL.render('sessionSelector');
      }).catch(function(){});
    }, 20000);
  },
  render: function(ctx, el) {
    var curr = ctx._current || 'agent:main:main';
    var html = '<div class="cl-flex-wrap"><span style="color:#8b949e">🔌</span>';
    html += '<span id="sess-drop-btn" class="cl-sess-selector">';
    html += shortKey(curr) + ' <span style="font-size:9px;color:#8b949e">▼</span>';
    html += '</span></div>';
    if (ctx._open) {
      html += '<div class="cl-sess-dropdown">';
      for (var i = 0; i < ctx._list.length; i++) {
        var s = ctx._list[i];
        var sk = s.sessionKey || '';
        var isCurr = (sk === curr);
        html += '<div data-sk="' + sk.replace(/"/g, '&quot;') + '" class="cl-sess-item' + (isCurr ? ' current' : '') + '">';
        html += '<span class="cl-sess-name" style="color:' + (isCurr ? '#58a6ff' : '#c9d1d9') + '">' + shortKey(sk) + '</span>';
        html += '<span class="cl-sess-time">' + fmtTimeShort(s.updatedAt) + '</span>';
        html += '<span class="cl-sess-count">' + (s.messageCount || '?') + '条</span>';
        html += '<span data-del="' + sk.replace(/"/g, '&quot;') + '" class="cl-sess-delete">✕</span>';
        html += '</div>';
      }
      html += '</div>';
    }
    el.innerHTML = html;
    el.onclick = function(e) {
      var t = e.target;
      if (t.id === 'sess-drop-btn' || t.parentElement.id === 'sess-drop-btn') {
        ctx._open = !ctx._open;
        CL.render('sessionSelector');
      } else if (t.classList.contains('cl-sess-delete')) {
        var k = t.getAttribute('data-del');
        e.stopPropagation();
        if (!confirm('\u5220\u9664\u4f1a\u8bdd\uff1a' + k)) return;
        api.deleteSession(k).then(function(d) {
          if (d.ok) api.listSessions().then(function(list) { ctx._list = list; CL.render('sessionSelector'); }).catch(function(){});
        }).catch(function(){});
      } else if (t.closest('.cl-sess-item')) {
        var item = t.closest('.cl-sess-item');
        var k = item.getAttribute('data-sk');
        if (k) {
          ctx._current = k;
          ctx._open = false;
          api.switchSession(k).then(function(d) {
            if (d && d.pairs) {
              store.pairs = d.pairs;
              store.totalPages = d.pairs.length;
              store.currentPage = 0;
              CL.render('sessionSelector');
              renderPage();
            }
          }).catch(function(){});
        }
      }
    };
  }
});

function shortKey(key) {
  if (!key) return '';
  if (key === 'agent:main:main') return '\u5f53\u524d\u4f1a\u8bdd';
  if (key.indexOf('cron:') > 0) return 'cron:' + key.slice(-8);
  if (key.indexOf('subagent:') > 0) return 'sub:' + key.slice(-8);
  if (key.indexOf(':dashboard:') > 0) return '\u4eea\u8868\u76d8:' + key.slice(-12);
  if (key.indexOf('orphan:') === 0) return 'old:' + key.slice(7, 19);
  return key.slice(-12);
}
function fmtTimeShort(ts) {
  if (!ts) return '';
  var d = new Date(ts);
  return pad2(d.getMonth()+1) + '-' + pad2(d.getDate()) + ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
}
function pad2(n) { return n < 10 ? '0' + n : '' + n; }

// ── 3. 消化栏 ──────────────────────────────────────────────────────────────
CL.register('digestBar', {
  container: 'ds-digest-time',
  parent: 'digest-skill-bar',
  init: function(ctx) { setInterval(ctx.render, 20000); },
  render: function(ctx, el) {
    api.digestSkill().then(function(d) {
      var lt = (d.last_digest_time || '').replace('\u6d88\u5316\u5faa\u73af', '').replace(/\d{4}-\d{2}-\d{2} /, '').trim();
      if (lt.indexOf('|') > 0) lt = lt.split('|')[0].trim();
      el.innerHTML = '\uD83C\uDF2B <span class="' + (d.last_digest_time ? 'cl-success' : 'cl-muted') + '">' + lt + '</span>';
      document.getElementById('ds-pending').innerHTML = '\u23F3 <span class="' + ((d.pending_assertions||0) > 0 ? 'cl-warn' : 'cl-muted') + '">' + (d.pending_assertions||0) + '</span>';
      document.getElementById('ds-assertions').innerHTML = '\uD83D\uDCA1 <span class="cl-success">' + (d.total_assertions||0) + '</span>';
      var se = document.getElementById('ds-skill-count');
      if (se) se.innerHTML = '\uD83D\uDCE6 <span class="cl-success">' + (d.skill_count||0) + '</span>';
      var pv = document.getElementById('ds-plugin-val');
      if (pv) { pv.textContent = d.plugin_ok ? '\u2705' : '\u26A0\uFE0F'; pv.className = d.plugin_ok ? 'cl-success' : 'cl-warn'; }
    }).catch(function(){});
  }
});

// ── 4. 消化历史 ──────────────────────────────────────────────────────────
CL.register('digestHistory', {
  container: 'ds-digest-history',
  parent: 'digest-skill-bar',
  render: function(ctx, el) { /* toggleDigestHistory 按需加载 */ }
});

function toggleDigestHistory() {
  var s = CL.get('digestHistory');
  if (!s) return;
  var panel = s.el;
  var btn = document.getElementById('ds-digest-btn');
  var vis = panel.style.display !== 'none';
  panel.style.display = vis ? 'none' : 'block';
  if (btn) btn.querySelector('span:last-child').textContent = vis ? '\u25BC' : '\u25B2';
  if (!vis) {
    panel.innerHTML = '<div class="cl-loading">\u52A0\u8F7D\u4E2D...</div>';
    api.get('/api/digestion-history').then(function(data) {
      if (!data || !data.length) {
        panel.innerHTML = '<div class="cl-loading">\u6682\u65E0\u5386\u53F2\u8BB0\u5F55</div>';
        return;
      }
      var html = '';
      for (var i = data.length - 1; i >= 0; i--) {
        var e = data[i];
        var t = new Date(e.ts);
        var ts = pad2(t.getMonth()+1) + '-' + pad2(t.getDate()) + ' ' + pad2(t.getHours()) + ':' + pad2(t.getMinutes());
        var icon = e.status === 'ok' ? '\uD83D\uDFE2' : '\uD83D\uDD34';
        html += '<div class="cl-flex-gap cl-border-bot" style="padding:4px 0;font-size:11px">';
        html += '<span>' + icon + ' ' + ts + '</span>';
        html += '<span class="cl-accent cl-text-nowrap">' + escapeHtml((e.summary||'').slice(0, 80)) + '</span>';
        html += '</div>';
      }
      panel.innerHTML = html;
    }).catch(function() {
      panel.innerHTML = '<div class="cl-error">\u52A0\u8F7D\u5931\u8D25</div>';
    });
  }
}

// ── 5. 系统健康 ──────────────────────────────────────────────────────────
CL.register('systemHealth', {
  container: 'sys-health',
  parent: 'app',
  init: function(ctx) { setInterval(ctx.render, 20000); },
  render: function(ctx, el) {
    var val = el;
    var target = el.querySelector && el.querySelector('span');
    if (target) val = target;
    api.systemHealth().then(function(d) {
      var ok = d.hooks && d.hooks.enabled && d.cron && d.cron.enabled && d.context && d.context.ok;
      val.textContent = ok ? '\u2705' : '\u26A0\uFE0F';
      val.className = ok ? 'cl-success' : 'cl-danger';
    }).catch(function(){ val.textContent = '?'; val.className = 'cl-danger'; });
  }
});

// ── 6. 备份状态 ──────────────────────────────────────────────────────────
CL.register('backup', {
  container: 'backup-stale',
  parent: 'app',
  init: function(ctx) { setInterval(ctx.render, 20000); },
  render: function(ctx, el) {
    api.backupStale().then(function(d) {
      if (!d.ok || d.stale === undefined) { el.textContent = '\uD83D\uDCBE ?'; return; }
      if (d.stale) { el.textContent = '\uD83D\uDCBE \u26A0\uFE0F'; el.style.color = '#da3633'; }
      else { el.textContent = '\uD83D\uDCBE \u2705 ' + (d.last_pack || ''); el.style.color = '#3fb950'; }
    }).catch(function(){ el.textContent = '\uD83D\uDCBE ?'; });
  }
});

// ── 7. 秘书 ──────────────────────────────────────────────────────────────
CL.register('secretary', {
  container: 'secretary-count',
  parent: 'secretary-indicator',
  init: function(ctx) { setInterval(ctx.render, 20000); },
  render: function(ctx, el) {
    api.secretaryLog().then(function(d) {
      if (!d.ok) return;
      el.textContent = d.total;
      el.className = d.total > 0 ? 'cl-accent' : 'cl-muted';
    }).catch(function(){});
  }
});

// ── 8. 武器库 ────────────────────────────────────────────────────────────
CL.register('weaponry', {
  container: 'weaponry-toggle-label',
  parent: 'app',
  init: function(ctx) { setInterval(ctx.render, 20000); },
  render: function(ctx, el) {
    api.weaponryToggle().then(function(d) {
      el.textContent = d.enabled ? '\u5BF9\u7EBF\u4E2D' : '\u5DF2\u6682\u505C';
      el.className = d.enabled ? 'cl-success' : 'cl-danger';
    }).catch(function(){});
  }
});

// ── 9. 思考模式 ──────────────────────────────────────────────────────────
CL.register('thinking', {
  container: 'think-status',
  parent: 'think-toggle',
  init: function(ctx) { setInterval(ctx.render, 20000); },
  render: function(ctx, el) {
    api.thinkingStatus().then(function(d) {
      var parent = document.getElementById('think-toggle');
      var dot = document.getElementById('think-dot');
      var dsEl = document.getElementById('ds-thinking-val');
      if (d.thinking) {
        el.textContent = '\u5F00';
        if (parent) { var onStyle = parent.dataset.onStyle; if (onStyle) parent.style.cssText = onStyle; }
        if (dot) { dot.style.background = '#da3633'; dot.style.borderColor = '#da3633'; }
        if (dsEl) { dsEl.textContent = '\u5F00'; dsEl.className = 'cl-warn'; }
      } else {
        el.textContent = '\u5173';
        if (parent) { var offStyle = parent.dataset.offStyle; if (offStyle) parent.style.cssText = offStyle; }
        if (dot) { dot.style.background = '#30363d'; dot.style.borderColor = '#30363d'; }
        if (dsEl) { dsEl.textContent = '\u5173'; dsEl.className = 'cl-muted'; }
      }
    }).catch(function(){ el.textContent = '?'; });
  }
});

// ── 10. 待办 ───────────────────────────────────────────────────────────────
function toggleBacklog() {
  var panel = document.getElementById('ds-backlog');
  var vis = panel.style.display !== 'none';
  panel.style.display = vis ? 'none' : 'block';
  if (!vis) {
    panel.innerHTML = '<div class="cl-loading">\u52A0\u8F7D\u4E2D...</div>';
    api.get('/api/backlog').then(function(d) {
      if (!d.ok) { panel.innerHTML = '<div class="cl-error">\u274C ' + (d.error||'') + '</div>'; return; }
      var html = '';
      for (var _i = 0; _i < d.content.split('\n').length; _i++) {
        var line = d.content.split('\n')[_i];
        if (line.startsWith('# ')) html += '<div class="cl-backlog-h1">' + escapeHtml(line.slice(2)) + '</div>';
        else if (line.startsWith('## ')) html += '<div class="cl-backlog-h2">' + escapeHtml(line.slice(3)) + '</div>';
        else if (line.includes('- [ ]')) html += '<div class="cl-backlog-pending">\u2B1C ' + escapeHtml(line.replace('- [ ]','').trim()) + '</div>';
        else if (line.includes('- [x]')) html += '<div class="cl-backlog-done">\u2705 ' + escapeHtml(line.replace('- [x]','').trim()) + '</div>';
        else if (line.trim()) html += '<div class="cl-backlog-meta">' + escapeHtml(line) + '</div>';
      }
      panel.innerHTML = html;
      var cnt = document.getElementById('ds-backlog-count');
      if (cnt) cnt.textContent = d.pending || 0;
    }).catch(function() { panel.innerHTML = '<div class="cl-error">\u52A0\u8F7D\u5931\u8D25</div>'; });
  }
}
