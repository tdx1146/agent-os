// ── ES Module imports ──

/**
 * cache-monitor.js — 缓存命中率监控面板（完全重写 v2）
 * ======================================================
 * 独立模块，完全替换 render.js 中的 loadCacheStats。
 * 
 * 后端：cache_monitor.py（不限制轮数、20轮实时窗口）
 * 
 * 暴露函数：loadCacheStats()
 * 这个函数名和 render.js 旧版的 loadCacheStats 相同，
 * 加载顺序靠后的会覆盖靠前的，所以本文件必须在 render.js 之后加载。
 * 
 * 更新：updateCachePct() 保留在 core.js 中不变。
 */

/**
 * 加载缓存详情面板
 * 由 core.js 中的 toggleCachePanel() 在展开时调用
 */
async function loadCacheStats() {
  const el = document.getElementById('cache-detail');
  if (!el) return;
  
  try {
    el.innerHTML = _loadingHTML();
    
    const d = await api.cacheStats();
    if (!d || !d.ok) {
      el.innerHTML = _errorHTML('获取失败');
      return;
    }
    
    const stats = d.stats || {};
    const rounds = d.rounds || [];
    
    // 只取最近 60 轮展示
    const displayRounds = rounds.slice(0, 60);
    const perCost = (stats.cost || {}).perRound || [];
    
    var html = '';
    
    // ── 概览行 ──
    html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:4px 10px;margin-bottom:8px;padding:6px 8px;background:#0d1117;border:1px solid #30363d;border-radius:4px">';
    html += _statBox('总轮次', stats.roundCount, '#8b949e');
    
    var overallHit = (stats.overall || {}).hitPct;
    var realtimeHit = (stats.realtime || {}).hitPct;
    var totalCost = (stats.cost || {}).total || 0;
    
    html += _statBox('总命中率', (overallHit !== undefined ? overallHit + '%' : '--'), 
            overallHit > 80 ? '#3fb950' : overallHit > 50 ? '#d29922' : '#f85149');
    html += _statBox('实时' + ((stats.realtime || {}).windowSize || 20) + '轮', 
            (realtimeHit !== undefined ? realtimeHit + '%' : '--'),
            realtimeHit > 80 ? '#3fb950' : realtimeHit > 50 ? '#d29922' : '#58a6ff');
    html += _statBox('总费用', '¥' + totalCost.toFixed(4), '#c9d1d9');
    html += '</div>';
    
    // 缓存节约
    var savings = (stats.cost || {}).savings || 0;
    if (savings > 0) {
      html += '<div style="color:#3fb950;font-size:11px;margin-bottom:6px">💰 缓存节约 ¥' + savings.toFixed(4) + '</div>';
    }
    
    // 吞吐
    var o = stats.overall || {};
    html += '<div style="display:flex;gap:12px;margin-bottom:6px;font-size:10px;color:#8b949e">';
    html += '<span>输入: ' + _fmtToken(o.totalInput) + '</span>';
    html += '<span>缓存: ' + _fmtToken(o.totalCache) + '</span>';
    html += '<span>输出: ' + _fmtToken(o.totalOutput) + '</span>';
    html += '</div>';
    
    // ── 历史轮次表（最近60轮）──
    html += '<div style="max-height:180px;overflow-y:auto;border:1px solid #30363d;border-radius:4px;background:#0d1117;font-size:10px">';
    html += '<table style="width:100%;border-collapse:collapse">';
    html += '<thead><tr style="background:#161b22;position:sticky;top:0">' +
            '<th style="padding:2px 4px;text-align:left;color:#8b949e;font-weight:400">#</th>' +
            '<th style="padding:2px 4px;text-align:right;color:#8b949e;font-weight:400">输入</th>' +
            '<th style="padding:2px 4px;text-align:right;color:#8b949e;font-weight:400">缓存</th>' +
            '<th style="padding:2px 4px;text-align:right;color:#8b949e;font-weight:400">输出</th>' +
            '<th style="padding:2px 4px;text-align:right;color:#8b949e;font-weight:400">命中率</th>' +
            '<th style="padding:2px 4px;text-align:right;color:#8b949e;font-weight:400">¥</th>' +
            '</tr></thead><tbody>';
    
    for (var i = 0; i < displayRounds.length; i++) {
      var r = displayRounds[i];
      var pct = r.cachePct;
      var pctColor = pct < 50 ? '#f85149' : pct < 80 ? '#d29922' : '#3fb950';
      var cost = (perCost[i] !== undefined ? perCost[i] : 0);
      html += '<tr>' +
        '<td style="padding:1px 4px;color:#8b949e;white-space:nowrap">#' + (i + 1) + '</td>' +
        '<td style="padding:1px 4px;text-align:right;color:#c9d1d9;font-variant-numeric:tabular-nums">' + _fmtNum(r.input) + '</td>' +
        '<td style="padding:1px 4px;text-align:right;color:' + (r.cacheRead > 0 ? '#3fb950' : '#8b949e') + ';font-variant-numeric:tabular-nums">' + _fmtNum(r.cacheRead) + '</td>' +
        '<td style="padding:1px 4px;text-align:right;color:#c9d1d9;font-variant-numeric:tabular-nums">' + _fmtNum(r.output) + '</td>' +
        '<td style="padding:1px 4px;text-align:right;color:' + pctColor + ';font-weight:600">' + pct + '%</td>' +
        '<td style="padding:1px 4px;text-align:right;color:#c9d1d9">' + (cost < 0.01 ? '<' + cost.toFixed(4) : cost.toFixed(4)) + '</td>' +
        '</tr>';
    }
    html += '</tbody></table></div>';
    
    // ── 最高/最低命中 ──
    var maxR = stats.maxCacheRound;
    var minR = stats.minCacheRound;
    if (maxR && minR) {
      html += '<div style="display:flex;gap:16px;margin-top:6px;font-size:10px;color:#8b949e;justify-content:center">';
      html += '<span>📈 最高: <span style="color:#3fb950">' + maxR.pct + '%</span></span>';
      html += '<span>📉 最低: <span style="color:#f85149">' + minR.pct + '%</span></span>';
      html += '</div>';
    }
    
    el.innerHTML = '<div style="padding:2px 0">' + html + '</div>';
  } catch(e) {
    el.innerHTML = _errorHTML('异常: ' + e.message);
  }
}

// ── 辅助函数 ──

function _loadingHTML() {
  return '<div style="color:#8b949e;text-align:center;padding:4px">加载中...</div>';
}

function _errorHTML(msg) {
  return '<div style="color:#f85149;text-align:center;padding:4px">❌ ' + msg + '</div>';
}

function _statBox(label, value, color) {
  return '<div><div style="color:#8b949e;font-size:9px">' + label + '</div>' +
    '<div style="color:' + color + ';font-weight:600;font-size:13px">' + value + '</div></div>';
}

function _fmtNum(n) {
  if (n === undefined || n === null) return '0';
  if (n < 1000) return String(n);
  if (n < 1000000) return (n / 1000).toFixed(1) + 'K';
  return (n / 1000000).toFixed(1) + 'M';
}

function _fmtToken(n) {
  return _fmtNum(n);
}

// ── ES Module exports ──

// ── Window bridge ──
window.loadCacheStats = loadCacheStats;
