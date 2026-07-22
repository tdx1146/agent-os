
// ── ES Module imports ──

// ── merged from cache.js ──
// cache.js — 展开的缓存面板（精简版，不碰 cache-summary，只写 cache-overview）
async function loadCacheStats() {
  try {
    const d = await api.cacheStats();
    if (!d.ok) { return; }
    const rounds = d.rounds || [];
    const summary = d.summary || {};

    document.getElementById('cache-overview').innerHTML =
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 20px;padding:4px 0">' +
        '<div style="color:#8b949e">总轮次</div>' +
        '<div style="text-align:right;color:#c9d1d9;font-weight:600">' + rounds.length + '</div>' +
        '<div style="color:#8b949e">总命中率</div>' +
        '<div style="text-align:right;color:#58a6ff;font-weight:600;font-size:15px">' + summary.avgCachePct + '%</div>' +
        '<div style="color:#8b949e">总费用</div>' +
        '<div style="text-align:right;color:#c9d1d9">¥' + summary.totalCost + '</div>' +
        '<div style="color:#8b949e">缓存节约</div>' +
        '<div style="text-align:right;color:#3fb950">¥' + summary.cacheSavings + '</div>' +
      '</div>';
  } catch(e) { /* ignore */ }
}

// 只在展开时加载，不由定时器触发

// ── merged from facts.js ──
// facts.js — 从 modules.js 拆分
function loadFactsLightbox() {
  document.getElementById('facts-overlay').style.display = 'block';
  const body = document.getElementById('facts-body');
  document.getElementById('facts-meta').textContent = '加载中...';
  body.textContent = '加载中...';
  api.momo('read_facts').then(d => {
    if (d.ok && d.content) {
      body.innerHTML = renderMarkdown(d.content);
      document.getElementById('facts-meta').textContent = d.content.split('\\n').length + '行 | ' + d.size + 'B';
    } else {
      body.innerHTML = '❌ 读取失败: ' + (d.error || '未知错误');
    }
  }).catch(e => {
    body.innerHTML = '❌ 网络错误: ' + e.message;
  });
}


function closeFactsOverlay(event) {
  if (!event || event.target === document.getElementById('facts-overlay') || !event.target) {
    document.getElementById('facts-overlay').style.display = 'none';
  }
}
// ── merged from tts.js ──
var ttsRate = 1;
// TTS 状态机: idle → loading → playing → idle
// TTS: 最简版 - 先出声再说
var _ttsAudio = null;

function ttsReadBtn(btn) {
  if (!btn) return;
  var msg = btn.closest('.msg');
  var textEl = msg ? msg.querySelector('.text') : null;
  var text = textEl ? textEl.textContent : '';
  if (!text || !text.trim()) { toast('没有文本', true); return; }
  
  // 如果正在播放或加载中，停止并返回（不重新播放）
  if (_ttsAudio) {
    try { _ttsAudio.pause(); _ttsAudio.src = ''; _ttsAudio.load(); } catch(e) {}
    _ttsAudio = null;
    btn.textContent = '🔊';
    return;
  }

  
  toast('⏳ 生成中...', false);
  btn.textContent = '⏳';
  
  api.post('/api/tts', {text: text}).then(function(d) {
    if (!d.ok || !d.audio) { 
      toast('生成失败: ' + (d.error || '未知'), true); 
      btn.textContent = '🔊';
      return; 
    }
    try {
      var raw = atob(d.audio);
      var buf = new ArrayBuffer(raw.length);
      var view = new Uint8Array(buf);
      for (var i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
      var blob = new Blob([buf], {type: 'audio/mpeg'});
      var url = URL.createObjectURL(blob);
      var a = new Audio(url);
      _ttsAudio = a;
      a.playbackRate = parseFloat(document.getElementById('ttsSpeed').value || '1');
      btn.textContent = '⏹';
      toast('🔊 播放中...', false);
      a.play().then(function(){}).catch(function(e){ 
        toast('播放失败: ' + e.message, true); 
        btn.textContent = '🔊';
      });
      a.onended = function(){ 
        URL.revokeObjectURL(url); 
        btn.textContent = '🔊'; 
        _ttsAudio = null; 
      };
    } catch(e) {
      toast('处理失败', true);
      btn.textContent = '🔊';
    }
  }).catch(function(e) {
    toast('请求失败: ' + e.message, true);
    btn.textContent = '🔊';
  });
}

// TTS: 速度选择器绑定（DOM 就绪后执行）
document.addEventListener('DOMContentLoaded', function(){
  var sel = document.getElementById('ttsSpeed');
  if (sel) sel.addEventListener('change', function(){ ttsRate = parseFloat(this.value); });
});

// 渲染入口（操作 DOM）

// ── merged from reminders.js ──
function openReminderDialog() {
  // 加载现有提醒
  api.reminders().then(d => {
      let html = '<div id="reminder-overlay" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:9999;display:flex;align-items:center;justify-content:center;font-size:13px">';
      html += '<div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:20px;max-width:500px;width:90%;max-height:80vh;overflow-y:auto">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">';
      html += '<strong style="color:#f0c040;font-size:15px">📋 提醒</strong>';
      html += '<span onclick="closeReminderDialog()" style="cursor:pointer;color:#8b949e;font-size:18px">✕</span>';
      html += '</div>';
      html += '<div style="margin-bottom:12px;display:flex;gap:6px">';
      html += '<input id="reminder-text" style="flex:1;background:#161b22;border:1px solid #30363d;border-radius:4px;padding:6px 8px;color:#c9d1d9;font-size:12px" placeholder="记下要做的事...">';
      html += '<select id="reminder-assignee" style="background:#161b22;border:1px solid #30363d;border-radius:4px;padding:6px;color:#c9d1d9;font-size:12px">';
      html += '<option value="">自己</option><option value="DeepSeek">DeepSeek</option><option value="混元">混元</option>';
      html += '</select>';
      html += '<button onclick="addReminder()" style="background:#238636;border:1px solid #2ea043;border-radius:4px;padding:6px 10px;color:white;cursor:pointer;font-size:12px">添加</button>';
      html += '</div>';
      html += '<div id="reminder-list">';
      if (d.ok && d.reminders && d.reminders.length > 0) {
        d.reminders.forEach(r => {
          const a = r.assignee ? ' [' + r.assignee + ']' : '';
          const done = r.done;
          html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #21262d">';
          html += '<button onclick="doneReminder(' + r.id + ')" style="background:transparent;border:1px solid #30363d;border-radius:3px;padding:2px 6px;color:' + (done ? '#58a6ff' : '#8b949e') + ';cursor:pointer;font-size:10px">' + (done ? '✅' : '✓') + '</button>';
          html += '<span style="flex:1;color:' + (done ? '#484f58' : '#c9d1d9') + ';text-decoration:' + (done ? 'line-through' : 'none') + '">' + r.text + '</span>';
          html += '<span style="color:#8b949e;font-size:10px">' + a + '</span>';
          html += '<span style="color:#484f58;font-size:10px">' + (r.created || '') + '</span>';
          html += '</div>';
        });
      } else {
        html += '<div style="color:#484f58;text-align:center;padding:20px">暂无待办提醒</div>';
      }
      html += '</div>';
      if (d.ok && d.count > 0) {
        html += '<div style="margin-top:10px;text-align:right"><button onclick="clearDoneReminders()" style="background:transparent;border:1px solid #30363d;border-radius:4px;padding:4px 8px;color:#8b949e;cursor:pointer;font-size:10px">清理已完成</button></div>';
      }
      html += '</div></div>';
      const existing = document.getElementById('reminder-overlay');
      if (existing) existing.remove();
      document.body.insertAdjacentHTML('beforeend', html);
    });
}

function closeReminderDialog() {
  const el = document.getElementById('reminder-overlay');
  if (el) el.remove();
  checkReminders();
}

function addReminder() {
  const text = document.getElementById('reminder-text').value.trim();
  if (!text) return;
  const assignee = document.getElementById('reminder-assignee').value;
  api.remindersAdd(text, assignee).then(d => {
    if (d.ok) {
      // Show brief toast
      const toast = document.createElement('div');
      toast.textContent = '✅ 已添加';
      toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#238636;color:white;padding:8px 16px;border-radius:6px;font-size:13px;z-index:10000;transition:opacity 0.5s';
      document.body.appendChild(toast);
      setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 500); }, 1500);
    }
    document.getElementById('reminder-text').value = '';
    openReminderDialog();
  });
}

function doneReminder(id) {
  api.remindersDone(id).then(() => openReminderDialog());
}

function clearDoneReminders() {
  api.remindersClearDone().then(() => openReminderDialog());
}


// ── merged from textarea.js ──
function enableMobileResize(ta) {
  if (!ta || ta.dataset.mobileResize) return;
  ta.dataset.mobileResize = '1';
  var startY, startH;
  ta.addEventListener('touchstart', function(e) {
    // 只有触摸底部时才触发
    var rect = ta.getBoundingClientRect();
    var touchY = e.touches[0].clientY;
    if (touchY < rect.bottom - 30) return;
    startY = touchY;
    startH = ta.offsetHeight;
  }, {passive: true});
  ta.addEventListener('touchmove', function(e) {
    if (!startY) return;
    var dy = e.touches[0].clientY - startY;
    var newH = Math.max(60, startH + dy);
    ta.style.height = newH + 'px';
  }, {passive: true});
  ta.addEventListener('touchend', function() { startY = null; }, {passive: true});
}

// 自动给所有textarea启用触摸缩放
document.addEventListener('DOMContentLoaded', function() {
  // 使 textarea 可从右上+右下拖拽变长
  function setupResize(el) {
    el.style.resize = "vertical";

    // 在手柄所属的 textarea 外面包一层紧身容器
    const wrap = document.createElement("div");
    wrap.style.cssText = "position:relative;width:100%";
    // 把 textarea 的 margin 转移到容器上
    const m = el.style.marginBottom;
    if (m) { wrap.style.marginBottom = m; el.style.marginBottom = "0"; }
    el.parentNode.insertBefore(wrap, el);
    wrap.appendChild(el);

    // 右上角手柄——贴在 textarea 本体右上角
    const grip = document.createElement("div");
    grip.style.cssText = "position:absolute;top:0;right:0;width:24px;height:16px;cursor:nw-resize;z-index:10;background:linear-gradient(225deg,transparent 40%,#666 60%,#888 100%);border-radius:0 6px 0 0;opacity:0.4";
    grip.title = "上拖变大，下拖变小";
    grip.onmouseenter = function() { this.style.opacity = "0.8"; };
    grip.onmouseleave = function() { this.style.opacity = "0.4"; };
    grip.onmousedown = function(e) {
      e.preventDefault(); e.stopPropagation();
      const startY = e.clientY, startH = el.offsetHeight;
      function mm(ev) {
        const delta = startY - ev.clientY;
        el.style.height = Math.max(50, startH + delta) + "px";
      }
      function mu() { document.removeEventListener("mousemove", mm); document.removeEventListener("mouseup", mu); }
      document.addEventListener("mousemove", mm);
      document.addEventListener("mouseup", mu);
    };
    // 移动端 touch 支持
    grip.ontouchstart = function(e) {
      var touch = e.touches[0];
      var startY = touch.clientY, startH = el.offsetHeight;
      function tm(ev) {
        ev.preventDefault();
        var t = ev.touches[0];
        var delta = startY - t.clientY;
        el.style.height = Math.max(50, startH + delta) + "px";
      }
      function tu() { document.removeEventListener("touchmove", tm); document.removeEventListener("touchend", tu); }
      document.addEventListener("touchmove", tm, {passive: false});
      document.addEventListener("touchend", tu);
    };
    wrap.appendChild(grip);
  }
    document.querySelectorAll("textarea").forEach(setupResize);
  });
// 动态创建的textarea也启用
var origCreateTextarea = document.createElement;
document.createElement = function(tag) {
  var el = origCreateTextarea.call(document, tag);
  if (tag === 'textarea' || tag === 'TEXTAREA') {
    setTimeout(function() { enableMobileResize(el); }, 100);
  }
  return el;
};

// 思考模式检测

// ── merged from pagination.js ──
function setupPagination() {
  // 只执行一次：创建分页栏HTML结构
  const initHtml = totalPages > 0
    ? '<button class="btn" data-page="0">«</button>' +
      '<button class="btn" data-page="prev">‹</button>' +
      ' 第 <input id="pageInput" type="number" min="1" max="' + totalPages + '" value="1" style="width:48px"> 页 / <span id="pageTotal">' + totalPages + '</span>' +
      '<button class="btn" data-page="next">›</button>' +
      '<button class="btn" data-page="last">»</button>' +
      '<button class="btn" id="jumpBtn">跳转</button>' +
      '<button class="btn" onclick="refresh()" title="刷新会话内容" style="margin-left:8px;font-size:11px">🔄</button>'
    : '';
  document.getElementById('paginationBottom').innerHTML = initHtml;

  // 事件代理：统一处理两个分页栏的点击
  document.addEventListener('click', function(e) {
    const btn = e.target.closest('.pagination .btn[data-page]');
    if (!btn) return;
    const page = btn.dataset.page;
    if (page === 'prev') goToPage(store.currentPage - 1);
    else if (page === 'next') goToPage(store.currentPage + 1);
    else if (page === 'last') goToPage(store.totalPages - 1);
    else goToPage(parseInt(page));
  });
  document.getElementById('jumpBtn')?.addEventListener('click', jumpPage);
  // 更新初始状态
  updatePaginationState();
}

function renderPagination() {
  // 向后兼容：初次调用时setup，后续只更新状态
  if (!document.getElementById('pageTotal')) {
    setupPagination();
  } else {
    updatePaginationState();
  }
}

function goToPage(p) {
  if (p < 0 || p >= store.totalPages) return;
  // 记录翻页栏当前位置，render后补偿，防止跳动
  const pb = document.getElementById('paginationBottom');
  const beforeRect = pb ? pb.getBoundingClientRect() : null;
  store.currentPage = p;
  renderPage();
  // 补偿：翻页栏应该停留在视口中原来相同的位置
  if (beforeRect) {
    requestAnimationFrame(function() {
      const pb2 = document.getElementById('paginationBottom');
      if (!pb2) return;
      const afterRect = pb2.getBoundingClientRect();
      const dy = afterRect.top - beforeRect.top;
      if (Math.abs(dy) > 2) window.scrollBy(0, dy);
    });
  }
}

function jumpPage() {
  const inp = document.getElementById('pageInput');
  const p = parseInt(inp.value, 10);
  if (p >= 1 && p <= store.totalPages) goToPage(p - 1);
}

// 增强分页状态
function updatePaginationState() {
  var paginationBtns = document.querySelectorAll('#paginationBottom .btn[data-page]');
  var pageInput = document.getElementById('pageInput');
  var jumpBtn = document.getElementById('jumpBtn');
  
  var pageNum = store.currentPage + 1;
  paginationBtns.forEach(function(btn) {
    var page = btn.dataset.page;
    var disabled = false;
    if (page === '0' || page === 'prev') disabled = store.currentPage <= 0;
    else if (page === 'next' || page === 'last') disabled = store.currentPage >= store.totalPages - 1;
    btn.disabled = disabled;
  });
  if (pageInput) { pageInput.value = pageNum; pageInput.max = store.totalPages; }
  var pageTotal = document.getElementById('pageTotal');
  if (pageTotal) pageTotal.textContent = store.totalPages;
}


var tbRootPath = window.tbRootPath = '';
var tbCurrentPath = window.tbCurrentPath = '';
var tbCurrentName = window.tbCurrentName = '';
var tbCurrentBrowsePath = window.tbCurrentBrowsePath = ''; // 当前浏览的目录（记忆用）
var tbMovePath = window.tbMovePath = ''; // 待移动的路径

// ===== 树弹出 =====

// ── merged from memory-file.js ──
// 📂 记忆文件系统 - 跳出对话窗口的另一种对话
let _memFileList = window._memFileList = [];

async function toggleMemoryFile() {
  const panel = document.getElementById('memory-file-panel');
  const backdrop = document.getElementById('memfile-backdrop');
  if (panel.style.display !== 'none' && panel.style.display !== '') {
    panel.style.display = 'none';
    backdrop.style.display = 'none';
    return;
  }
  backdrop.style.display = 'block';
  panel.style.display = 'block';
  panel.style.position = 'fixed';
  panel.style.top = '10%';
  panel.style.left = '50%';
  panel.style.transform = 'translateX(-50%)';
  panel.style.width = '90%';
  panel.style.maxWidth = '800px';
  panel.style.margin = '0';
  panel.style.zIndex = '1001';
  panel.style.maxHeight = '75vh';
  panel.style.overflowY = 'auto';
  panel.style.boxShadow = '0 8px 32px rgba(0,0,0,0.6)';
  panel.style.border = '1px solid #58a6ff';
  await loadMemFileList();
}

async function closeMemFile() {
  document.getElementById('memory-file-panel').style.display = 'none';
  document.getElementById('memfile-backdrop').style.display = 'none';
}

async function loadMemFileList() {
  const status = document.getElementById('memfile-status');
  status.textContent = '📂 加载文件列表...';
  try {
    const d = await api.memoryFiles();
    if (d.ok) {
      _memFileList = d.files;
      renderMemFileList(d.files);
      status.textContent = '📂 点击文件加载内容，编辑后保存';
    } else {
      status.textContent = '❌ ' + (d.error || '加载失败');
    }
  } catch(e) {
    status.textContent = '❌ ' + e.message;
  }
}

function renderMemFileList(files) {
  const list = document.getElementById('memfile-list');
  list.innerHTML = files.map(f =>
    `<div class="memfile-item" style="cursor:pointer;padding:4px 8px;border-radius:4px;font-size:12px;font-family:monospace;color:#8b949e;border-bottom:1px solid #21262d"
          onmouseover="this.style.background='#161b22'"
          onmouseout="this.style.background='transparent'"
          onclick="loadMemFile('${f.name}')">
      <span style="color:#58a6ff">📄</span> ${f.name}
      <span style="float:right;color:#484f58">${f.size}</span>
    </div>`
  ).join('');
}

async function loadMemFile(name) {
  const status = document.getElementById('memfile-status');
  const textarea = document.getElementById('memfile-text');
  status.textContent = '📂 加载 ' + name + '...';
  try {
    const d = await api.memoryFile(name);
    if (d.ok) {
      textarea.value = d.content;
      document.getElementById('memfile-path').textContent = name;
      document.getElementById('memfile-current-name').value = name;
      status.textContent = '✅ 已加载，编辑后保存';
    } else {
      status.textContent = '❌ ' + (d.error || '加载失败');
    }
  } catch(e) {
    status.textContent = '❌ ' + e.message;
  }
}

async function saveMemoryFile() {
  const status = document.getElementById('memfile-status');
  const textarea = document.getElementById('memfile-text');
  const name = document.getElementById('memfile-current-name').value;
  status.textContent = '💾 保存中...';
  try {
    const d = await api.memoryFile(name, textarea.value);
    if (d.ok) {
      status.textContent = '✅ 保存成功！你的话已经留在了我的记忆里';
      await loadMemFileList(); // Refresh file list to update sizes
    } else {
      status.textContent = '❌ ' + (d.error || '保存失败');
    }
  } catch(e) {
    status.textContent = '❌ ' + e.message;
  }
}





// ── render.js core ──
function rpcMessagesToPairs(messages) {
  // Convert OpenAI-format messages [{role, content: [{type, text}]}]
  // to editor pairs [{user:{text,model,timestamp}, assistants:[{text,model,timestamp}]}]
  var pairs = [];
  var currentUser = null;
  var userIdx = 0;  // 🌫️ 用户消息序号（非全局行号），防止截断时传错索引
  for (var i = 0; i < messages.length; i++) {
    var m = messages[i];
    var text = '';
    var thinking = '';
    if (Array.isArray(m.content)) {
      for (var j = 0; j < m.content.length; j++) {
        var c = m.content[j];
        if (c.type === 'text') text = c.text || '';
        else if (c.type === 'thinking') thinking = c.thinking || '';
      }
    } else if (typeof m.content === 'string') {
      text = m.content;
    }
    var role = m.role || 'user';
    var ts = m.created || m.timestamp || (m.createdAt ? new Date(m.createdAt).getTime() : Date.now());

    if (role === 'user') {
      currentUser = {text: text, model: m.model || '', timestamp: ts, userIndex: userIdx++};
      pairs.push({user: currentUser, assistants: []});
    } else if (role === 'assistant' && pairs.length > 0) {
      pairs[pairs.length - 1].assistants.push({
        text: text, thinking: thinking,
        model: m.model || 'AI', timestamp: ts
      });
    } else if (role === 'toolResult' && pairs.length > 0) {
      // skip tool results
    }
  }
  return pairs;
}

function fmtTime(ts) {
  if (!ts || ts === 0) return '';
  const d = new Date(ts);
  const pad = (n) => String(n).padStart(2, '0');
  return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
}

function fmtTimeFull(ts) {
  if (!ts || ts === 0) return '';
  const d = new Date(ts);
  const pad = (n) => String(n).padStart(2, '0');
  return pad(d.getMonth()+1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

// ── 渲染层 ──────────────────────────────────────────────────────────────────
// 纯函数：生成消息列表 HTML（不操作 DOM）
function renderMessagesHtml(st) {
  if (st.totalPages === 0) return '<div style="text-align:center;color:#8b949e;padding:40px;font-size:14px">暂无对话记录</div>';
  
  // 过滤空助理消息（只显示有实际文本或思考内容的助理消息）
  function filterAsst(aa) {
    return (aa || []).filter(function(a) {
      return (a.text && a.text.trim()) || (a.thinking && a.thinking.trim());
    });
  }
  
  // 收集要渲染的对（单页模式，每次只显示当前页的一轮对话）
  var pairsToRender = [];
  var p0 = st.pairs[st.currentPage];
  if (p0) pairsToRender.push({pair: p0, idx: st.currentPage, roundNum: st.currentPage + 1, totalU: st.totalPages});
  
  var allHtml = '';
  for (var prIdx = 0; prIdx < pairsToRender.length; prIdx++) {
    var pr = pairsToRender[prIdx];
    var pair = pr.pair;
    var u = pair.user || {};
    var aa = filterAsst(pair.assistants);
    var editBtn = '<span onclick="openEdit(' + pr.idx + ')" style="cursor:pointer;color:#f0883e;font-size:13px">✏️ 编辑</span>';
    
    allHtml += '<div class="pair-card">';
    allHtml += '<div class="pair-header">';
    allHtml += '<span>轮 #' + pr.roundNum + ' · ' + (u.model || '') + '</span>';
    allHtml += '<span style="color:#8b949e;font-size:11px">' + fmtTimeFull(u.timestamp) + '</span>';
    allHtml += editBtn;
    allHtml += '</div>';
    
    for (ai = 0; ai < aa.length; ai++) {
      var a = aa[ai];
      allHtml += '<div class="msg assistant">';
      allHtml += '<div class="role-badge assistant">AI' + (a.model ? ' · ' + a.model : '') + '</div>';
      if (a.thinking) {
        allHtml += '<div class="thinking-section" style="margin:6px 0 6px 0">';
        allHtml += '<div class="thinking-toggle" style="color:#da3633;font-size:12px;cursor:pointer;user-select:none" onclick="this.nextElementSibling.classList.toggle(\'collapsed\');this.querySelector(\'.thinking-count\').textContent=this.querySelector(\'.thinking-count\').textContent==\'收起\'?\'展开\':\'收起\'">🧠 思考 <span class="thinking-count">展开</span></div>';
        allHtml += '<div class="thinking-body collapsed" style="color:#8b949e;font-size:13px;margin:4px 0 4px 0;padding:8px;background:#1c1c1c;border-left:2px solid #da3633;max-height:200px;overflow-y:auto;line-height:1.5;white-space:pre-wrap;">';
        allHtml += escapeHtml(a.thinking);
        allHtml += '</div></div>';
      }
      allHtml += '<div class="text">' + (a.text ? renderMarkdown(escapeHtml(a.text)) : '') + '</div>';
      allHtml += '<div class="msg-time">' + fmtTime(a.timestamp) + '</div>';
      allHtml += '<span class="tts-btn" onclick="event.stopPropagation();ttsReadBtn(this)">🔊</span>';
      allHtml += '</div>';
    }
    
    allHtml += '<div class="msg user">';
    allHtml += '<div class="role-badge user">' + (u.text ? '你' : '📨 系统') + ' <span class="index-badge">#' + pr.roundNum + '/' + pr.totalU + '</span></div>';
    allHtml += '<div class="text">' + (u.text ? renderMarkdown(escapeHtml(u.text)) : '') + '</div>';
    allHtml += '<div class="msg-time">' + fmtTime(u.timestamp) + '</div>';
    allHtml += '<span class="tts-btn" onclick="event.stopPropagation();ttsReadBtn(this)">🔊</span>';
    allHtml += '<span class="edit-icon" onclick="openEdit(' + pr.idx + ')">✏️</span>';
    allHtml += '</div></div>';
  }
  
  return allHtml;
}
// 纯函数：生成消息计数文字
function renderCountText(st) {
  if (st.totalPages === 0) return '暂无对话';
  var mode = '第 ' + (st.currentPage + 1) + ' / ' + st.totalPages + ' 轮';
  return mode + ' · 共 ' + st.pairs.length + ' 组';
}

// ── TTS ────────────────────────────────────────────
// ── 增量渲染 ────────────────────────────────────────────────────────────
var _lastRenderHash = window._lastRenderHash = '';

function pairHash(st) {
  if (!st || !st.pairs || st.pairs.length === 0) return 'empty';
var p = st.pairs[st.currentPage];
  if (!p) return 'no-page';
  var u = p.user || {};
  var aa = p.assistants || [];
  var h = st.currentPage + '|' + st.totalPages + '|' + (u.text||'').slice(0,20) + '|' + (u.timestamp||'');
  for (var i = 0; i < aa.length; i++) {
    h += '|' + (aa[i].text||'').slice(0,30) + '|' + (aa[i].thinking||'').slice(0,10);
  }
  return h;
}

function renderPage() {
  var el = document.getElementById('messages');
  if (!el) return;
  
  var hash = pairHash(store);
  if (hash === _lastRenderHash) {
    // 内容没变，只更新计数和分页（可能翻页键状态变了）
    document.getElementById('msgCount').textContent = renderCountText(store);
    renderPagination();
    return;
  }
  _lastRenderHash = hash;
  
  var pc = document.getElementById('msgCount');
  
  // 保存选中
  var savedSel = null;
  var sel = window.getSelection();
  if (sel && sel.rangeCount > 0 && el.contains(sel.anchorNode)) {
    savedSel = {
      anchorNode: sel.anchorNode,
      anchorOffset: sel.anchorOffset,
      focusNode: sel.focusNode,
      focusOffset: sel.focusOffset
    };
  }
  
  pc.textContent = renderCountText(store);
  el.innerHTML = renderMessagesHtml(store);
  renderPagination();
  
  if (savedSel && document.body.contains(savedSel.anchorNode)) {
    try {
      var range = document.createRange();
      range.setStart(savedSel.anchorNode, savedSel.anchorOffset);
      range.setEnd(savedSel.focusNode, savedSel.focusOffset);
      sel.removeAllRanges();
      sel.addRange(range);
    } catch(e) {}
  }
}

// ── 子代理面板 ────────────────────────────────────────────────────────────
let subagentPanelOpen = window.subagentPanelOpen = false;

// ── ES Module exports ──

// ── Window bridge (for onclick handlers in HTML and cross-file globals) ──
window.loadFactsLightbox = loadFactsLightbox;
window.closeFactsOverlay = closeFactsOverlay;
window.ttsReadBtn = ttsReadBtn;
window.openReminderDialog = openReminderDialog;
window.closeReminderDialog = closeReminderDialog;
window.addReminder = addReminder;
window.doneReminder = doneReminder;
window.clearDoneReminders = clearDoneReminders;
window.setupPagination = setupPagination;
window.renderPagination = renderPagination;
window.goToPage = goToPage;
window.jumpPage = jumpPage;
window.updatePaginationState = updatePaginationState;
window.toggleMemoryFile = toggleMemoryFile;
window.closeMemFile = closeMemFile;
window.loadMemFileList = loadMemFileList;
window.renderMemFileList = renderMemFileList;
window.loadMemFile = loadMemFile;
window.saveMemoryFile = saveMemoryFile;
window.rpcMessagesToPairs = rpcMessagesToPairs;
window.fmtTime = fmtTime;
window.fmtTimeFull = fmtTimeFull;
window.renderMessagesHtml = renderMessagesHtml;
window.renderCountText = renderCountText;
window.renderPage = renderPage;
window.pairHash = pairHash;
window.ttsRate = ttsRate;
window._ttsAudio = _ttsAudio;
window._lastRenderHash = _lastRenderHash;
window.enableMobileResize = enableMobileResize;
