// 确保 pairs 引用 store.pairs（防止缓存导致变量未定义）
var pairs = store.pairs;

function openEdit(pairIdx) {
  const prev = document.getElementById('edit-panel');
  if (prev) prev.remove();

  const pair = store.pairs[pairIdx];
  if (!pair) return;

  const panel = document.createElement('div');
  panel.className = 'edit-panel active';
  panel.id = 'edit-panel';
  panel.innerHTML =
    '<label>编辑第 ' + (pairs.length - pairIdx) + ' 轮对话的用户消息（截断后续所有内容，发回给 AI 重新回复）：</label>' +
    '<textarea id="edit-text">' + escapeHtml(pair.user.text) + '</textarea>' +
    '<div style="margin:8px 0;padding:8px 10px;background:#0d1117;border:1px solid #30363d;border-radius:6px">' +
    '<label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;color:#8b949e">' +
    '<input type="checkbox" id="send-notice" checked onchange="toggleNotice()"> ' +
    '📢 发送截断通知</label>' +
    '<textarea id="notice-text" style="display:none;width:100%;margin-top:6px;min-height:36px;background:#0d1117;color:#8b949e;border:1px solid #30363d;border-radius:4px;padding:6px 8px;font-size:12px;font-family:inherit;resize:vertical">⚠️ 对话已被截断。本轮结束前请记录轮感。</textarea>' +
    '</div>' +
    '<div class="actions">' +
    '<button class="btn btn-primary" onclick="saveEdit(' + pairIdx + ')">💾 保存截断并发送给 AI</button>' +
    '<button class="btn" onclick="cancelEdit()">取消</button>' +
    '</div>' +
    '<div class="status" id="edit-status"></div>';

  const msgEl = document.getElementById('messages');
  // 在消息区内插入编辑框（当前卡片后面），不跳出消息区域
  if (msgEl) {
    const card = msgEl.querySelector('.pair-card');
    if (card && card.nextSibling) {
      msgEl.insertBefore(panel, card.nextSibling);
    } else {
      msgEl.appendChild(panel);
    }
  }
  setTimeout(function() {
    panel.scrollIntoView({ block: 'nearest' });
  }, 100);
}

function cancelEdit() {
  const panel = document.getElementById('edit-panel');
  if (panel) panel.remove();
}

function toggleNotice() {
  const cb = document.getElementById('send-notice');
  const ta = document.getElementById('notice-text');
  ta.style.display = cb.checked ? 'block' : 'none';
}

async function saveEdit(pairIdx) {
  const ta = document.getElementById('edit-text');
  const st = document.getElementById('edit-status');
  const txt = ta.value.trim();
  if (!txt) { st.className = 'status err'; st.textContent = '内容不能为空'; return; }

  const pair = store.pairs[pairIdx];
  const userIndex = pair.userIndex;
  st.className = 'status'; st.textContent = '⏳ 保存截断中...';

  try {
    // 📦 截断前先存档，确保不丢
    await api.momo('pack'); await api.clearLock();

    const res = await api.edit(userIndex, txt, false);
    if (!res.ok) {
      st.className = 'status err';
      // 🔒 安全铁律拦截：展示主人确认按钮
      if (res.error && /安全铁律/.test(res.error)) {
        st.innerHTML = '❌ ' + escapeHtml(res.error) + '<br><br>' +
          '<label style="display:inline-flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;color:#f0883e">' +
          '<input type="checkbox" id="approve-override" style="width:16px;height:16px"> ' +
          '我确认--这是主人的明确授权，允许截断此轮对话</label><br><br>' +
          '<button class="btn btn-primary" id="override-btn" onclick="saveEditWithApproval(' + pairIdx + ')" disabled>🔓 需勾选上方确认框</button>';
        // 勾选后方可点击
        document.getElementById('approve-override').addEventListener('change', function() {
          const btn = document.getElementById('override-btn');
          btn.disabled = !this.checked;
          btn.textContent = this.checked ? '🔓 以主人授权截断' : '🔓 需勾选上方确认框';
        });
      } else {
        st.textContent = '❌ ' + (res.error || '截断失败');
      }
      return;
    }

    st.textContent = '✅ 截断 ' + res.truncated + ' 条消息，正在发送给 AI...';

    // 📢 截断通知：如果勾选了，在消息前面加上通知文本
    let injectMsg = txt;
    const sendNotice = document.getElementById('send-notice');
    if (sendNotice && sendNotice.checked) {
      const noticeText = document.getElementById('notice-text');
      if (noticeText && noticeText.value.trim()) {
        injectMsg = noticeText.value.trim() + '\n\n' + injectMsg;
      }
    }

    const injRes = await api.inject(injectMsg);
    if (!injRes || injRes.error) {
      st.className = 'status err';
      st.textContent = '❌ 注入失败: ' + ((injRes && injRes.error) || '服务器错误');
      return;
    }

    cancelEdit();
    // 立即渲染用户消息
    store.currentPage = 0;
    renderPage();
    // 记录截断后的正确轮数
    var _targetLen = store.pairs.length;
    // 轮询等待截断结果写入
    var _tp = setInterval(async function() {
      try {
        var d = await api.sessionFresh();
        // 只需轮数 >= 目标轮数（旧数据轮数多，不会误触发）
        if (d && d.pairs && d.pairs.length >= _targetLen) {
          store.msgCache = d.messages || [];
          store.pairs = d.pairs || [];
          store.totalPages = store.pairs.length;
          if (d.pairs.length > _targetLen) store.currentPage = 0;
          renderPage();
          // 有 assistant 回复则停止
          if (d.pairs[0]?.assistants?.length > 0) clearInterval(_tp);
        }
      } catch(e) {}
    }, 1500);
    // 30秒超时停止轮询
    setTimeout(function() { clearInterval(_tp); }, 30000);

    const banner = document.createElement('div');
    if (injRes.ok) {
      banner.style.cssText = 'background:#1c2128;border:1px solid #3fb950;border-radius:8px;padding:14px 18px;margin:16px 0;font-size:14px;color:#3fb950;text-align:center;';
      banner.innerHTML = '✅ 已截断并发送，等待 AI 回复...<br><span style="color:#8b949e;font-size:12px">消息出现后会自动跳转到最新页</span>';
      toast('已截断并发送，等待 AI 回复');
    } else {
      banner.style.cssText = 'background:#1c2128;border:1px solid #f0883e;border-radius:8px;padding:14px 18px;margin:16px 0;font-size:14px;color:#f0883e;text-align:center;';
      banner.innerHTML = '✂️ 已截断 ' + res.truncated + ' 条消息，但发送给 AI 失败：' + escapeHtml(injRes.error || '未知错误');
      toast('截断成功，但注入失败: ' + (injRes.error || ''), true);
    }
    document.getElementById('msgCount').parentNode.insertBefore(banner, document.getElementById('msgCount').nextSibling);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    setTimeout(() => { if (banner.parentNode) banner.remove(); }, 5000);

  } catch(e) {
    st.className = 'status err';
    st.textContent = '❌ 网络错误: ' + (e.message || e);
  }
}

// 🔒 主人授权截断（绕过安全铁律）
async function saveEditWithApproval(pairIdx) {
  const ta = document.getElementById('edit-text');
  const st = document.getElementById('edit-status');
  const txt = ta.value.trim();
  if (!txt) { st.className = 'status err'; st.textContent = '内容不能为空'; return; }

  const pair = store.pairs[pairIdx];
  const userIndex = pair.userIndex;
  st.className = 'status'; st.textContent = '⏳ 以主人授权执行截断...';

  try {
    // 📦 截断前先存档，确保不丢
    await api.momo('pack'); await api.clearLock();

    const res = await api.edit(userIndex, txt, true);
    if (!res.ok) {
      st.className = 'status err';
      st.textContent = '❌ ' + (res.error || '截断失败');
      return;
    }

    st.textContent = '✅ 截断 ' + res.truncated + ' 条消息，正在发送给 AI...';

    const injRes = await api.inject(txt);
    // 立即在本地显示
    const now = Date.now();
    const optimisticPair = {
      user: { text: txt, model: '', timestamp: now, userIndex: -1 },
      assistants: []
    };
    store.pairs.unshift(optimisticPair);
    store.currentPage = 0;
    renderPage();
    
    if (!injRes || injRes.error) {
      st.className = 'status err';
      st.textContent = '❌ 注入失败: ' + ((injRes && injRes.error) || '服务器错误');
      return;
    }
    cancelEdit();
    await refresh();
    store.currentPage = 0;
    renderPage();
    var _targetLen2 = store.pairs.length;
    var _tp2 = setInterval(async function() {
      try {
        var d = await api.sessionFresh();
        if (d && d.pairs && d.pairs.length >= _targetLen2) {
          store.pairs = d.pairs || [];
          store.totalPages = store.pairs.length;
          if (d.pairs.length > _targetLen2) store.currentPage = 0;
          renderPage();
          if (d.pairs[0]?.assistants?.length > 0) clearInterval(_tp2);
        }
      } catch(e) {}
    }, 1500);
    setTimeout(function() { clearInterval(_tp2); }, 30000);

    const banner = document.createElement('div');
    if (injRes.ok) {
      banner.style.cssText = 'background:#1c2128;border:1px solid #3fb950;border-radius:8px;padding:14px 18px;margin:16px 0;font-size:14px;color:#3fb950;text-align:center;';
      banner.innerHTML = '✅ 已截断 ' + res.truncated + ' 条消息并发送给 AI 思考中<br><span style="color:#8b949e;font-size:12px">（主人授权模式下执行）</span>';
      toast('已截断并发送给 AI');
    } else {
      banner.style.cssText = 'background:#1c2128;border:1px solid #f0883e;border-radius:8px;padding:14px 18px;margin:16px 0;font-size:14px;color:#f0883e;text-align:center;';
      banner.innerHTML = '✂️ 已截断但注入失败：' + escapeHtml(injRes.error || '未知错误');
      toast('截断成功但注入失败', true);
    }
    document.getElementById('msgCount').parentNode.insertBefore(banner, document.getElementById('msgCount').nextSibling);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    setTimeout(() => { if (banner.parentNode) banner.remove(); }, 5000);
  } catch(e) {
    st.className = 'status err';
    st.textContent = '❌ 网络错误: ' + (e.message || e);
  }
}

// 🌫️ 摸摸协议
