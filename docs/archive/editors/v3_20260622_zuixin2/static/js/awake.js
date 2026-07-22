document.addEventListener('DOMContentLoaded', function() {
  _renderSentCache();
  // 🌫️ 自驱思维链：定时提醒自己深入思考
  setInterval(function() {
    try {
      const d = JSON.parse(localStorage.getItem('self_chain') || '{}');
      if (d.status === 'thinking' && (d.depth || 0) < 3) {
        toast('🌫️ 自驱链 (' + d.depth + '/3) — 继续深化?', false);
      }
    } catch(e) { /* ignore */ }
  }, 120000); // 2分钟
});
// 💬 对话框
function toggleDialog() {
  const panel = document.getElementById('awake-panel');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  if (panel.style.display !== 'none') awakeRefreshList();
}

async function abortThinking() {
  const btn = document.getElementById('stop-think-btn');
  const status = document.getElementById('awake-status');
  if (btn) { btn.disabled = true; btn.textContent = '⏳...'; }
  status.textContent = '⏳ 停止思考中...';
  try {
    const d = await api.abort();
    status.textContent = d.ok ? '✅ 已停止思考' : '❌ 取消失败: ' + (d.error || '');
    refresh();
  } catch(e) {
    status.textContent = '❌ ' + e.message;
  }
  if (btn) { btn.disabled = false; btn.textContent = '⏹ 停止'; }
}

async function awakePick() {
  const panel = document.getElementById('awake-panel');
  panel.style.display = 'block';
  await awakeRefreshList();
}

async function awakeRefreshList() {
  const list = document.getElementById('awake-list');
  const status = document.getElementById('awake-status');
  list.innerHTML = '<div style="padding:6px;color:#8b949e">⏳ 加载中...</div>';
  try {
    const data = await api.awakeList();
    if (!data.ok) { list.innerHTML = '<div style="padding:6px;color:#f85149">加载失败</div>'; return; }
    // Store raw file content for save
    window._awakeFileContent = data.file_content || '';
    awakeRenderList(data.questions);
  } catch(e) {
    list.innerHTML = '<div style="padding:6px;color:#f85149">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function awakeRenderList(questions) {
  const list = document.getElementById('awake-list');
  const q = (document.getElementById('awake-search').value || '').toLowerCase();
  const filtered = q ? questions.filter(x => x.toLowerCase().includes(q)) : questions;
  list.innerHTML = '';
  if (filtered.length === 0) {
    list.innerHTML = '<div style="padding:6px;color:#8b949e">' + (q ? '没有匹配的题目' : '题库为空') + '</div>';
    return;
  }
  for (const item of filtered) {
    const div = document.createElement('div');
    const display = item.length > 60 ? item.slice(0, 60) + '...' : item;
    div.textContent = display;
    div.style.cssText = 'padding:4px 8px;cursor:pointer;border-bottom:1px solid #21262d;color:#c9d1d9';
    div.onmouseover = function() { this.style.background = '#161b22'; };
    div.onmouseout = function() { this.style.background = ''; };
    div.onclick = function() { awakeSelect(item); };
    list.appendChild(div);
  }
}

let _awakeBankOpen = false;

function awakeToggleBank() {
  _awakeBankOpen = !_awakeBankOpen;
  const list = document.getElementById('awake-list');
  const btn = document.getElementById('awake-toggle-btn');
  const editDiv = document.getElementById('awake-bank-edit');
  if (_awakeBankOpen) {
    list.style.display = 'block';
    btn.textContent = '▼';
    awakeRefreshList();
  } else {
    list.style.display = 'none';
    btn.textContent = '▶';
    if (editDiv) editDiv.style.display = 'none';
  }
}

function awakeFilter() {
  if (_awakeBankOpen) awakeRefreshList();
}

function awakeSelect(text) {
  document.getElementById('awake-editor').value = text;
  document.getElementById('awake-status').textContent = '✔ 已选择';
}

function awakeEditBank() {
  const editDiv = document.getElementById('awake-bank-edit');
  if (editDiv.style.display === 'block') {
    editDiv.style.display = 'none';
    return;
  }
  editDiv.style.display = 'block';
  document.getElementById('awake-bank-status').textContent = '⏳ 加载中...';
  api.awakeList().then(function(d){
    if (d.ok && d.file_content) {
      document.getElementById('awake-bank-editor').value = d.file_content;
      document.getElementById('awake-bank-status').textContent = '✏️ 编辑中 (' + d.total + '条)';
    } else {
      document.getElementById('awake-bank-status').textContent = '❌ 加载失败';
    }
  }).catch(function(){
    document.getElementById('awake-bank-status').textContent = '❌ 网络错误';
  });
}

async function awakeSaveBank() {
  const editor = document.getElementById('awake-bank-editor');
  const status = document.getElementById('awake-bank-status');
  if (!editor) return;
  status.textContent = '⏳ 保存中...';
  try {
    const d = await api.awakeSave(editor.value);
    if (d.ok) { status.textContent = '✅ 已保存';
      document.getElementById('awake-bank-edit').style.display = 'none';
      awakeRefreshList();
    } else {
      status.textContent = '❌ ' + (d.error || '');
    }
  } catch(e) {
    status.textContent = '❌ ' + e.message;
  }
}

async function awakeSendNoTrunc() {
  await _awakeDoSend(false);
}

async function awakeSendTrunc() {
  await _awakeDoSend(true);
}

async function _awakeDoSend(truncate) {
  const editor = document.getElementById('awake-editor');
  const status = document.getElementById('awake-status');
  const text = editor.value.trim();
  if (!text) { status.textContent = '❌ 内容为空'; return; }

  if (truncate) {
    status.textContent = '⏳ 暂停思考 & 截断中...';
    try {
      // 先停止 AI 思考，确保文件安全
      await api.abort();

      // 截断当前在页面中选择的轮次（currentPage）
      if (store.pairs && store.pairs.length > 0 && store.currentPage >= 0 && store.currentPage < store.pairs.length) {
        const targetPair = store.pairs[store.currentPage];
        const ed = await api.edit(targetPair.userIndex, '…', true);
        if (!ed.ok) {
          status.textContent = '❌ 截断失败: ' + (ed.error || '');
          return;
        }
        // 截断后刷新页面
        refresh();
      } else {
        status.textContent = '❌ 没有可截断的轮次';
        return;
      }
    } catch(e) {
      status.textContent = '❌ 截断失败: ' + e.message;
      return;
    }
  }

  // 保存到本地缓存（防丢失）
  const sentCache = JSON.parse(localStorage.getItem('sentCache') || '[]');
  sentCache.push({text, ts: Date.now(), sent: false});
  localStorage.setItem('sentCache', JSON.stringify(sentCache));
  _renderSentCache();

  // 使用唤醒题库专用发送接口（绕过 inject 锁）
  // 先清空输入框防双击（即使发送失败也不留消息）
  editor.value = '';
  status.textContent = '⏳ 发送中...';
  try {
    const injR = await api.momo('inject_feeling', {feeling: text});
    // 发送成功 → 标记已发
    if (injR.ok) {
      const caches = JSON.parse(localStorage.getItem('sentCache') || '[]');
      const found = caches.find(c => c.text === text && !c.sent);
      if (found) { found.sent = true; found.ts2 = Date.now(); }
      localStorage.setItem('sentCache', JSON.stringify(caches));
      _renderSentCache();
    }
    if (injR.ok) {
      // ── 乐观更新：立即显示用户消息 ──
      const optimisticPair = {
        user: { text: text, model: '', timestamp: Date.now(), userIndex: -1 },
        assistants: []
      };
            store.pairs = [optimisticPair, ...store.pairs];
      store.totalPages = store.pairs.length;
      store.currentPage = 0;
      // 保存乐观消息文本，供 refresh 恢复
      window._optimisticText = text;
      renderPage();
      status.textContent = '✅ 已提交';
      // 标记已发（防重发）
      const caches = JSON.parse(localStorage.getItem('sentCache') || '[]');
      const found = caches.find(c => c.text === text && !c.sent);
      if (found) { found.sent = true; }
      localStorage.setItem('sentCache', JSON.stringify(caches));
      _renderSentCache();

      // ── 轮询 ──
      let stableCount = 0, lastText = '';
      let pollCount = 0;
      const pollTimer = setInterval(async () => {
        pollCount++;
        try {
          const d = await api.sessionFresh();
          if (!d || !d.pairs) return;
          // 后台没追上 → 还在等待送达
          if (d.pairs.length < store.pairs.length) {
            if (pollCount > 10) {
              // inject_feeling 不写回 session pairs，等不到变化
              // 消息已通过 inject API 送达，只是 Gateway 还没写 JSONL
              status.textContent = '✅ 已提交至 OpenClaw';
              clearInterval(pollTimer);
              return;
            }
            status.textContent = '⏳ 等待送达 OpenClaw...';
            return;
          }
          // 送达了！用完整后台数据替换（后台按时间顺序，最新在末尾）
          status.textContent = '✅ 已送达 (等待AI...)';
          const _oldPage = store.currentPage;
          store.msgCache = d.messages || [];
          store.pairs = d.pairs || [];
          store.totalPages = store.pairs.length;
          _lastRenderHash = '';  // 强制下次 renderPage 重建 DOM
          // 保持当前位置，除非当前页已超出范围
          if (store.currentPage >= store.totalPages) store.currentPage = store.totalPages - 1;
          renderPage();
          // 后备：5 秒后强制刷新一次（AI 可能回复中）
          setTimeout(function() { _lastRenderHash = ''; renderPage(); }, 5000);
          // 检测 AI 是否回复（最新消息在末尾）
          const lastPair = d.pairs[d.pairs.length - 1];
          const txt = (lastPair && lastPair.assistants ? lastPair.assistants[0]?.text : '') || '';
          if (txt) {
            status.textContent = '💬 回复中...';
            if (txt === lastText) {
              stableCount++;
              if (stableCount >= 3) {
                status.textContent = '✅ 已回复';
                clearInterval(pollTimer);
              }
            } else {
              stableCount = 0;
              lastText = txt;
            }
          } else {
            status.textContent = '✅ 已发送 (等待AI...)';
          }
        } catch(e) { /* ignore */ }
      }, 1500);
      setTimeout(function() { clearInterval(pollTimer); }, 15000);
    } else {
      status.textContent = '❌ 注入失败: ' + (injR.error || '');
    }
  } catch (e) {
    status.textContent = '❌ ' + e.message;
  }
}

async function awakeSave() {
  const status = document.getElementById('awake-status');
  const text = document.getElementById('awake-editor').value;
  if (!text.trim()) { status.textContent = '❌ 内容为空'; return; }

  // Load current file content and add/replace the question
  status.textContent = '⏳ 保存中...';
  try {
    const data = await api.awakeList();
    let content = data.file_content || '';

    // Check if this question text already exists (by prefix), replace it
    const lines = content.split('\n');
    let found = false;
    const prefix = text.split(' - ')[0] + ' - ';
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].startsWith(prefix)) {
        lines[i] = text;
        found = true;
        break;
      }
    }
    if (!found) {
      // Add as new question - find last q-number
      let maxNum = 0;
      for (const line of lines) {
        const m = line.match(/^q(\d+)/);
        if (m) maxNum = Math.max(maxNum, parseInt(m[1]));
      }
      lines.push('q' + String(maxNum + 1).padStart(3, '0') + ' - ' + text.split(' - ').slice(1).join(' - '));
      // If input doesn't have a q prefix, just append
    }

    const saveD = await api.awakeSave(lines.join('\n'));
    if (saveD.ok) {
      status.textContent = '✅ 已保存到题库';
      await awakeRefreshList();
    } else {
      status.textContent = '❌ ' + (saveD.error || '保存失败');
    }
  } catch(e) {
    status.textContent = '❌ ' + e.message;
  }
}

function hideAwake() {
}
