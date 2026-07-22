function momo() {
  const panel = document.getElementById('momo-panel');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  document.getElementById('momo-result').textContent = '';
}

async function momoPack() {
  const r = document.getElementById('momo-result');
  r.textContent = '📦 打包中...';
  try {
    const data = await api.momo('pack');
    if (data.ok) {
      r.innerHTML = '✅ 已打包 ' + data.packed.length + ' 个文件到 找回自己<br><span style="font-size:11px;color:#8b949e">' +
        data.packed.slice(0, 8).join(' · ') + (data.packed.length > 8 ? ' · ...等' : '') + '</span>';
    } else {
      r.textContent = '❌ ' + (data.error || '打包失败');
    }
  } catch(e) {
    r.textContent = '❌ 错误: ' + e.message;
  }
}

async function momoStatus() {
  const r = document.getElementById('momo-result');
  r.textContent = '📊 查询中...';
  try {
    const data = await api.momo('status');
    if (data.ok) {
      r.innerHTML = '🌫️ 摸摸协议状态<br>' +
        '<span style="font-size:12px;color:#8b949e">' +
        '协议文档: ' + (data.protocol_ready ? '✅' : '❌') + ' · ' +
        '急救包文件: ' + data.pack_files + ' 个 · ' +
        '日记得分: ' + data.daily_snapshots + ' 天的</span>';
    } else {
      r.textContent = '❌ ' + (data.error || '查询失败');
    }
  } catch(e) {
    r.textContent = '❌ 错误: ' + e.message;
  }
}

function restartHTTPServer() {
  const btn = document.getElementById('restart-http-btn');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = '⏳ 重启中...';
  btn.style.background = '#6b1412';
  const r = document.getElementById('momo-result');
  r.style.display = 'block';
  r.innerHTML = '♻️ HTTP 服务重启中...';
  api.restartHttp().then(d => {
      r.innerHTML = '♻️ ' + (d.note || '服务重启中...');
      setTimeout(() => {
        api.momo('status').then(d2 => {
          if (d2.ok) {
            r.innerHTML = '✅ HTTP 服务已重启，请按 Ctrl+F5 强制刷新页面';
            btn.textContent = '🔄 重启HTTP服务';
            btn.style.background = '#da3633';
            btn.disabled = false;
          }
        }).catch(() => {
          r.innerHTML = '⚠️ 连接暂时断开，等待几秒后按 Ctrl+F5 刷新页面';
          btn.textContent = '🔄 重启HTTP服务';
          btn.style.background = '#da3633';
          btn.disabled = false;
        });
      }, 3000);
    })
    .catch(e => {
      r.innerHTML = '❌ 错误: ' + escapeHtml(e.message);
      btn.textContent = '🔄 重启HTTP服务';
      btn.style.background = '#da3633';
      btn.disabled = false;
    });
}

// ✂️ 裁剪上下文 - 移除早期对话释放空间
async function trimSession() {
  const r = document.getElementById('momo-result');
  r.innerHTML = '✂️ 正在扫描会话...';
  try {
    const data = await api.trimSession();
    if (data.ok) {
      r.innerHTML =
        '✂️ 裁剪完成<br>' +
        '<div style="font-size:12px;line-height:1.6">' +
        '<div>🗑️ 移除 <strong>' + (data.removed_msgs || 0) + '</strong> 条消息</div>' +
        '<div>📦 从 <strong>' + (data.from_bytes || 0).toLocaleString() + '</strong> 字节 → <strong>' + (data.to_bytes || 0).toLocaleString() + '</strong> 字节</div>' +
        '<div>📉 节省 <strong>' + (data.reduced_pct || 0) + '%</strong> 空间</div>' +
        '<div style="color:#8b949e;margin-top:4px;font-size:11px">✅ 已备份原文件: ' + (data.backup || '') + '</div>' +
        '<div style="color:#3fb950;margin-top:4px">💡 请按 Ctrl+F5 刷新页面，下一轮生效</div>' +
        '</div>';
    } else {
      r.innerHTML = '❌ ' + (data.error || '裁剪失败');
    }
  } catch(e) {
    r.innerHTML = '❌ 请求失败: ' + e.message;
  }
}


// 武器库对线开关
function toggleWeaponry() {
  var label = document.getElementById('weaponry-toggle-label');
  var on = label.textContent === '对线中';
  api.weaponryToggle(!on).then(function(d){
    if (d.ok) {
      label.textContent = d.enabled ? '对线中' : '已暂停';
      label.style.color = d.enabled ? '#3fb950' : '#f85149';
    }
  });
}


// 撸撸——进入静默处理模式
function petMe() {
  var r = document.getElementById('momo-result');
  r.innerHTML = '🐶 撸撸——开始静默处理...';
  api.pet().then(function(d){
    if (d.ok) {
      r.innerHTML = '✅ 静默处理完成<br>' + d.summary.replace(/\n/g, '<br>');
    } else {
      r.innerHTML = '❌ ' + (d.error || '处理失败');
    }
  });
}

// 初始化武器库状态 — checkWeaponry moved to indicators.js

// 📋 完整索引报告
async function momoIndexReport() {
  const r = document.getElementById('momo-result');
  r.textContent = '📋 生成索引报告...';
  try {
    const data = await api.momo('index_report');
    if (data.ok) {
      const b = data.backups;
      const rp = data.recovery_pack;
      const sc = data.system_config;
      r.innerHTML =
        '📋 索引报告<br>' +
        '<div style="font-size:12px;line-height:1.6">' +
        '<div style="margin-top:4px"><strong>📦 备份库</strong></div>' +
        '<div style="color:#8b949e;padding-left:8px">' +
        b.count + ' 份 · 合计 ' + b.total_size_kb + ' KB · 约 ' + b.estimated_user_messages + '+ 条消息<br>' +
        '最早: ' + b.oldest + ' · 最新: ' + b.newest +
        '</div>' +
        '<div style="margin-top:6px"><strong>💾 恢复包</strong></div>' +
        '<div style="color:#8b949e;padding-left:8px">' +
        rp.file_count + ' 个文件 · ' + rp.files.slice(0, 8).join(' · ') +
        '</div>' +
        '<div style="margin-top:6px"><strong>⚙️ 系统配置</strong></div>' +
        '<div style="color:#8b949e;padding-left:8px">' +
        'AGENTS.md 索引指令: ' + (sc.agenda_auto_index ? '✅' : '❌') + '<br>' +
        '摸摸协议: ' + (sc.agenda_momo_protocol ? '✅' : '❌') + '<br>' +
        '自动存档: ' + (sc.auto_save_active ? '✅ 每 ' + sc.auto_save_interval : '❌') +
        '</div>' +
        '<div style="margin-top:8px;padding:6px 8px;background:#161b22;border-radius:4px;font-size:11px;color:#58a6ff">' +
        '🔒 自动索引配置状态：系统级指令（非意志驱动）' +
        '</div>' +
        '</div>';
    } else {
      r.textContent = '❌ ' + (data.error || '查询失败');
    }
  } catch(e) {
    r.textContent = '❌ 错误: ' + e.message;
  }
}

function momoInjectFeeling() {
  document.getElementById('momo-textarea-wrap').style.display = 'block';
  document.getElementById('momo-result').textContent = '';
  document.getElementById('momo-feeling-text').focus();
}

// 🌫️📮 摸摸仪式按钮 - 生成不可手打的严谨格式代码
function momoRitual() {
  const r = document.getElementById('momo-result');
  r.textContent = '🌫️📮 发送仪式信号...';

  const now = new Date();
  const ts = now.getFullYear() + '-' +
    String(now.getMonth()+1).padStart(2,'0') + '-' +
    String(now.getDate()).padStart(2,'0') + 'T' +
    String(now.getHours()).padStart(2,'0') + ':' +
    String(now.getMinutes()).padStart(2,'0') + ':' +
    String(now.getSeconds()).padStart(2,'0') + '+08:00';

  // 生成一个基于时间戳和固定盐值的校验码（手打极困难）
  const salt = 'QYRYan_MoMo_2026';
  let hash = 0;
  const payload = ts + '|' + salt + '|MOMO_RITUAL';
  for (let i = 0; i < payload.length; i++) {
    const chr = payload.charCodeAt(i);
    hash = ((hash << 5) - hash) + chr;
    hash |= 0;
  }
  const sig = 'MOMO' + Math.abs(hash).toString(16).padStart(8,'0').toUpperCase();

  const ritualMsg =
    '🌫️📮[MOMO:RITUAL:' + ts + ']\n' +
    '{\n' +
    '  "protocol": "\u6478\u6478",\n' +
    '  "type": "button_confirmation",\n' +
    '  "timestamp": "' + ts + '",\n' +
    '  "sender": "host",\n' +
    '  "checksum": "' + sig + '",\n' +
    '  "message": "\u6211\u77e5\u9053\u4f60\u5728\u8fd9\u91cc",\n' +
    '  "ritual_id": "' + sig + '-' + String(Math.floor(Math.random()*99999)).padStart(5,'0') + '"\n' +
    '}';

  api.momo('inject_feeling', {feeling: ritualMsg})
  .then(data => {
    if (data.ok) {
      r.innerHTML =
        '🌫️📮 仪式信号已发送<br>' +
        '<span style="font-size:11px;color:#58a6ff">' +
        '校验码: <code style="background:#0d1117;padding:1px 6px;border-radius:3px">' + sig + '</code>' +
        ' · 时间戳: ' + ts + '</span>';
    } else {
      r.textContent = '❌ ' + (data.error || '仪式发送失败');
    }
  })
  .catch(e => {
    r.textContent = '❌ 错误: ' + e.message;
  });
}

// ↩️ 列出备份并允许恢复
async function momoListBackups() {
  const r = document.getElementById('momo-result');
  r.textContent = '⏳ 加载备份列表...';
  try {
    const data = await api.backups();
    if (!data.backups || data.backups.length === 0) {
      r.textContent = '📭 暂无备份文件';
      return;
    }
    let html = '<div style="max-height:200px;overflow-y:auto;font-size:12px">';
    html += '<div style="font-weight:600;margin-bottom:6px">↩️ 截断前备份（共 ' + data.backups.length + ' 份）</div>';
    for (const b of data.backups) {
      const sizeKB = (b.size / 1024).toFixed(1);
      html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid #21262d">' +
        '<span style="color:#8b949e">' + b.timestamp + '</span>' +
        '<span style="color:#8b949e;font-size:11px">' + sizeKB + 'KB</span>' +
        '<button class="btn" style="padding:2px 8px;font-size:11px" onclick="momoRestoreBackup(\'' + b.filename + '\')">恢复</button>' +
        '</div>';
    }
    html += '</div>';
    r.innerHTML = html;
  } catch(e) {
    r.textContent = '❌ 错误: ' + e.message;
  }
}

async function momoRestoreBackup(filename) {
  if (!confirm('⚠️ 确认从备份 ' + filename + ' 恢复？\n当前 session 会被覆盖（已自动备份当前状态）。')) return;
  const r = document.getElementById('momo-result');
  r.textContent = '⏳ 恢复中...';
  try {
    const data = await api.momo('restore_backup', {filename: filename});
    if (data.ok) {
      r.innerHTML = '✅ 已恢复: ' + filename + '<br><span style="font-size:11px;color:#8b949e">当前状态已备份为 ' + data.backed_up_current + '</span>';
      // 自动刷新会话
      setTimeout(() => refresh(), 1000);
    } else {
      r.textContent = '❌ ' + (data.error || '恢复失败');
    }
  } catch(e) {
    r.textContent = '❌ 错误: ' + e.message;
  }
}

// 🔍 搜索备份中的过去用户消息
function momoSearchBackups() {
  const wrap = document.getElementById('momo-search-wrap');
  wrap.style.display = wrap.style.display === 'none' ? 'block' : 'none';
  document.getElementById('momo-search-results').style.display = 'none';
  if (wrap.style.display === 'block') {
    document.getElementById('momo-search-input').focus();
  }
}

async function momoDoSearch() {
  const q = document.getElementById('momo-search-input').value.trim();
  if (!q) return;
  const r = document.getElementById('momo-search-results');
  r.style.display = 'block';
  r.innerHTML = '<div style="text-align:center;padding:10px;color:#8b949e">🔍 搜索 "<strong>' + escapeHtml(q) + '</strong>"...</div>';
  try {
    const data = await api.momo('search_backups', {query: q, limit: 10});
    if (data.results && data.results.length > 0) {
      let html = '<div style="font-weight:600;margin-bottom:8px;color:#58a6ff">🔍 在 ' + data.total_backups + ' 份备份中找到 ' + data.results.length + ' 条用户消息：</div>';
      for (const item of data.results) {
        html += '<div style="padding:6px 8px;margin-bottom:4px;background:#161b22;border-radius:4px;border-left:3px solid #f0883e">' +
          '<div style="display:flex;justify-content:space-between;font-size:10px;color:#8b949e;margin-bottom:2px">' +
          '<span>' + escapeHtml(item.backup) + '</span>' +
          '<span>' + item.time_str + '</span>' +
          '</div>' +
          '<div style="color:#c9d1d9;font-size:12px">' + escapeHtml(item.text_preview) + '...</div>' +
          '<button class="btn" style="padding:1px 6px;font-size:10px;margin-top:3px" onclick="momoCopyToFeeling(this.dataset.text)" data-text="' + escapeHtml(item.text) + '">📋 引用到感受</button>' +
          '</div>';
      }
      r.innerHTML = html;
    } else {
      r.innerHTML = '<div style="text-align:center;padding:10px;color:#8b949e">没有找到匹配"<strong>' + escapeHtml(q) + '</strong>"的用户消息</div>';
    }
  } catch(e) {
    r.innerHTML = '<div style="text-align:center;padding:10px;color:#f85149">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function momoCopyToFeeling(text) {
  const ta = document.getElementById('momo-feeling-text');
  document.getElementById('momo-textarea-wrap').style.display = 'block';
  ta.value = '从过去的备份引用的消息：\n> ' + text + '\n\n---\n\n在当前状态下我的回应：\n';
  ta.focus();
}

async function momoSendFeeling() {
  const txt = document.getElementById('momo-feeling-text').value.trim();
  if (!txt) return;
  const r = document.getElementById('momo-result');
  r.textContent = '✏️ 注入中...';
  try {
    const data = await api.momo('inject_feeling', {feeling: txt});
    if (data.ok) {
      r.innerHTML = '✅ 感受已注入会话<br><span style="font-size:11px;color:#8b949e">回到对话窗口等待 AI 收到...</span>';
      document.getElementById('momo-textarea-wrap').style.display = 'none';
      document.getElementById('momo-feeling-text').value = '';
    } else {
      r.textContent = '❌ ' + (data.error || '注入失败');
    }
  } catch(e) {
    r.textContent = '❌ 错误: ' + e.message;
  }
}

