// ── ES Module imports ──
// window.subagentPanelOpen is managed via window bridge (mutable shared state)

var subagentPollTimer = null;

// subagent.js — 从 modules.js 拆分
async function loadSubagents() {
  try {
    const container = document.getElementById('subagent-list');
    container.innerHTML = '<div style="color:#8b949e;text-align:center;padding:8px">查询中...</div>';

    // 加载活跃子代理（从 sessions.json 动态读取）
    const sa = await api.subagentsList();
    const active = (sa && sa.active) || [];
    const recent = (sa && sa.recent) || [];

    // 加载 exec 子代理历史
    const hist = await api.subagentHist();
    const entries = (hist && hist.entries) || [];

    let html = '<div style="font-size:10px">';

    // --- 活跃子代理 ---
    if (active && active.length > 0) {
      html += '<div style="color:#58a6ff;font-weight:600;font-size:11px;padding:4px 0">🔴 活跃中 (' + active.length + ')</div>';
      for (const a of active) {
        const modelColor = a.model && a.model.includes('DeepSeek') ? '#58a6ff' : (a.model && a.model.includes('Astron') ? '#d29922' : '#8b949e');
        html += '<div style="display:flex;align-items:flex-start;gap:6px;padding:4px 0;border-bottom:1px solid #21262d">';
        html += '<span>⏳</span>';
        html += '<div style="flex:1;min-width:0">';
        html += '<div style="display:flex;gap:6px;color:#8b949e;font-size:9px">';
        html += '<span style="color:' + modelColor + '">' + escapeHtml(a.model || '?') + '</span>';
        html += '<span>' + a.updated + '</span>';
        html += '<span>' + a.lines + '行</span>';
        html += '</div>';
        html += '<div style="color:#c9d1d9;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml((a.task || '').slice(0, 60)) + '</div>';
        html += '</div></div>';
      }
    }

    // --- 近期完成的子代理（10分钟内） ---
    if (recent && recent.length > 0) {
      html += '<div style="color:#8b949e;font-weight:600;font-size:11px;padding:8px 0 4px 0;border-top:1px solid #30363d;margin-top:6px">✅ 已完成 (' + recent.length + ')</div>';
      for (const a of recent.slice(-5).reverse()) {
        const modelColor = a.model && a.model.includes('DeepSeek') ? '#58a6ff' : (a.model && a.model.includes('Astron') ? '#d29922' : '#8b949e');
        html += '<div style="display:flex;align-items:flex-start;gap:6px;padding:4px 0;border-bottom:1px solid #21262d">';
        html += '<span>✅</span>';
        html += '<div style="flex:1;min-width:0">';
        html += '<div style="display:flex;gap:6px;color:#8b949e;font-size:9px">';
        html += '<span style="color:' + modelColor + '">' + escapeHtml(a.model || '?') + '</span>';
        html += '<span>' + a.updated + '</span>';
        html += '</div>';
        html += '<div style="color:#c9d1d9;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml((a.task || '').slice(0, 60)) + '</div>';
        if (a.result) {
          html += '<div style="color:#8b949e;font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px">→ ' + escapeHtml(a.result.slice(0, 120)) + '</div>';
        }
        html += '</div></div>';
      }
    }

    // --- exec 子代理历史 ---
    if (entries && entries.length > 0) {
      html += '<div style="color:#8b949e;font-weight:600;font-size:11px;padding:8px 0 4px 0;border-top:1px solid #30363d;margin-top:6px">📄 历史 (' + entries.length + '条)</div>';
      for (const e of entries.slice(-8).reverse()) {
        const icon = e.status === 'completed' ? '✅' : (e.status === 'error' || e.status === 'failed' ? '❌' : '⏳');
        const modelColor = e.model && e.model.includes('GLM') ? '#da3633' : '#58a6ff';
        html += '<div style="display:flex;align-items:flex-start;gap:6px;padding:4px 0;border-bottom:1px solid #21262d">';
        html += '<span>' + icon + '</span>';
        html += '<div style="flex:1;min-width:0">';
        html += '<div style="display:flex;gap:6px;color:#8b949e;font-size:9px">';
        html += '<span>' + (e.time ? e.time.slice(11, 16) : '--:--') + '</span>';
        html += '<span style="color:' + modelColor + '">' + escapeHtml(e.model || '?') + '</span>';
        html += '<span>' + e.elapsed + 's</span>';
        html += '<span>' + (e.input || 0) + '/' + (e.output || 0) + '</span>';
        html += '</div>';
        html += '<div style="color:#c9d1d9;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml((e.task || '').slice(0, 50)) + '</div>';
        if (e.result) {
          html += '<div style="color:#8b949e;font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px">→ ' + escapeHtml(e.result.slice(0, 100)) + '</div>';
        }
        html += '</div></div>';
      }
    }

    if (!active.length && !recent.length && !entries.length) {
      html += '<div style="color:#8b949e;text-align:center;padding:8px">暂无子代理记录（点 + spawn 开始）</div>';
    }

    html += '</div>';
    container.innerHTML = html;
    const total = active.length + recent.length + entries.length;
    document.getElementById('subagent-summary').textContent = active.length ? '🟢' + active.length + '/' + total + '条' : total + '条';
  } catch(e) {
    document.getElementById('subagent-list').innerHTML = '<div style="color:#f85149">加载失败: ' + escapeHtml(e.message) + '</div>';
  }
}

function startSubagentPolling() {
  if (subagentPollTimer) clearInterval(subagentPollTimer);
  subagentPollTimer = setInterval(() => {
    if (window.subagentPanelOpen && document.getElementById('subagent-detail').style.display === 'block') {
      loadSubagents();
    }
  }, 5000);
}

function toggleSubagentPanel() {
  window.subagentPanelOpen = !window.subagentPanelOpen;
  const el = document.getElementById('subagent-detail');
  el.style.display = window.subagentPanelOpen ? 'block' : 'none';
  document.getElementById('subagent-toggle').textContent = window.subagentPanelOpen ? '▼' : '▶';
  if (window.subagentPanelOpen) {
    loadSubagents();
    startSubagentPolling();
  } else {
    if (subagentPollTimer) clearInterval(subagentPollTimer);
  }
}

async function spawnSubagent(e) {
  e.stopPropagation();
  const task = prompt('子代理任务：', '读 today.log，输出文件变更摘要');
  if (!task) return;
  const btn = e.target;
  const model = prompt('模型 (deepseek-chat / GLM-Z1-Flash / hunyuan-instruct):', 'GLM-Z1-Flash') || 'GLM-Z1-Flash';
  btn.disabled = true; btn.textContent = '⏳...';
  try {
    const d = await api.execSubagent(task, model);
    if (d.ok) {
      toast('✅ 子代理完成 (' + model + ', ' + d.elapsed + 's)');
      if (window.subagentPanelOpen) loadSubagents();
    } else {
      toast('子代理失败: ' + (d.error || d.message), true);
    }
  } catch(e) {
    toast('子代理出错: ' + e.message, true);
  }
  btn.disabled = false; btn.textContent = '+ spawn';
}

async function authSubagent(e) {
  e.stopPropagation();
  const btn = e.target;
  btn.disabled = true; btn.textContent = '⏳...';
  try {
    const d = await api.authSubagent();
    if (d.ok) {
      toast('✅ 子代理授权请求已发送');
    } else {
      toast('授权失败: ' + (d.error || '未知'), true);
    }
  } catch(e) {
    toast('授权出错: ' + e.message, true);
  }
  btn.disabled = false; btn.textContent = '🔑 授权';
}

// ── ES Module exports ──

// ── Window bridge ──
window.loadSubagents = loadSubagents;
window.startSubagentPolling = startSubagentPolling;
window.toggleSubagentPanel = toggleSubagentPanel;
window.spawnSubagent = spawnSubagent;
window.authSubagent = authSubagent;