// dashboard.js — 引导文件，等所有依赖就绪后渲染组件

(function boot() {
  function tryBoot() {
    if (!window.CL || !document.getElementById('messages')) {
      setTimeout(tryBoot, 50);
      return;
    }
    try { CL.renderAll(); } catch(e) { /* 静默 */ }
    try {
      api.listSessions().then(function(list) {
        var ss = CL.get('sessionSelector');
        if (ss) { ss._list = list; try { CL.render('sessionSelector'); } catch(e) {} }
      }).catch(function(){});
    } catch(e) {}
  }
  // defer 脚本在 DOM ready 后执行，但可能有渲染延迟
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(tryBoot, 100);
  } else {
    document.addEventListener('DOMContentLoaded', function() { setTimeout(tryBoot, 100); });
  }
  // 所有组件注册完毕后首次刷新上轮缓存
  setTimeout(function() {
    if (typeof updateCachePct === 'function') updateCachePct();
  }, 300);
  // 后备：600ms 后强制刷新
  setTimeout(function() {
    var el = document.getElementById('cache-summary');
    if (el && el.textContent.trim() === '--') {
      if (typeof updateCachePct === 'function') updateCachePct();
    }
  }, 600);
})();
