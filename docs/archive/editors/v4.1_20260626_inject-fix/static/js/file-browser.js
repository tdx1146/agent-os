function tbToggleBrowser() {
  var browser = document.getElementById('tb-browser');
  var btn = document.getElementById('tb-browse-btn');
  if (!browser || !btn) return;
  if (browser.style.display === 'block') {
    browser.style.display = 'none';
    return;
  }
  // 固定位置：从不跑转
  var left = Math.max(10, window.innerWidth - 420);
  var top = 48;
  // relative container already handles positioning

    var saved = localStorage.getItem('tb_browse_path');
  // 如果 localStorage 缓存的路径以 /vol1 开头（符号链接旧路径），自动清除
  if (saved && (saved.indexOf('/vol1') === 0 || saved === 'undefined')) {
    localStorage.removeItem('tb_browse_path');
    saved = null;
  }
  if (saved) {
    tbCurrentBrowsePath = saved;
  }
  browser.innerHTML = '<div style="padding:12px;color:#8b949e;text-align:center;font-size:12px">加载中...</div>';
  browser.style.display = 'block';
  tbLoadTree(tbCurrentBrowsePath || null);
}

async function tbLoadTree(dirPath) {
  var browser = document.getElementById('tb-browser');
  if (!browser) return;
  var savedScroll = browser.scrollTop || 0;
  browser.innerHTML = '<div style="padding:12px;color:#8b949e;text-align:center;font-size:12px">加载中...</div>';
  browser.style.display = 'none';
  
  try {
    var d = dirPath ? await api.listFiles(dirPath) : await api.browseDirs();
    if (!d.ok) {
      // fallback: 如果 localStorage 的路径失效，退回到 browseDirs()
      if (dirPath && localStorage.getItem('tb_browse_path')) {
        localStorage.removeItem('tb_browse_path');
        tbCurrentBrowsePath = '';
        tbLoadTree(null);
        return;
      }
      browser.innerHTML = '<div style="padding:12px;color:#f85149;text-align:center;font-size:12px">' + (d.error || '加载失败') + '</div>';
      browser.style.display = 'block';
      return;
    }

    // 根目录 = browse-dirs 返回的 root，跟 config 一致
    if (d.ok && d.root) {
      tbRootPath = d.root;
    }
    var files = d.files || [];
    var root = d.root || tbRootPath;
    if (root) tbRootPath = root;

    browser.innerHTML = '';
    var curDir = dirPath || tbRootPath;
    tbCurrentBrowsePath = curDir;
    localStorage.setItem('tb_browse_path', curDir);

    // 当前目录头 + 回到根按钮
    var headerRow = document.createElement('div');
    headerRow.style.cssText = 'display:flex;align-items:center;gap:4px;padding:8px 12px;border-bottom:1px solid #30363d';
    var header = document.createElement('span');
    header.style.cssText = 'color:#8b949e;font-size:10px;word-break:break-all;cursor:pointer;flex:1';
    header.textContent = '📁 ' + curDir;
    header.dataset.type = 'current-folder';
    header.dataset.path = curDir;
    headerRow.appendChild(header);
    if (curDir !== tbRootPath) {
      var homeBtn = document.createElement('span');
      homeBtn.style.cssText = 'cursor:pointer;color:#58a6ff;font-size:11px;padding:2px 6px;white-space:nowrap';
      homeBtn.textContent = '↩️ 根';
      homeBtn.dataset.type = 'root';
      homeBtn.dataset.path = tbRootPath;
      headerRow.appendChild(homeBtn);
    }
    browser.appendChild(headerRow);

    // 移动目标指示
    if (tbMovePath) {
      var moveBar = document.createElement('div');
      moveBar.style.cssText = 'padding:6px 12px;background:#2d1b69;color:#d2a8ff;font-size:11px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #30363d';
      moveBar.innerHTML = '📌 移动至: 当前目录';
      var pasteBtn = document.createElement('span');
      pasteBtn.style.cssText = 'cursor:pointer;color:#58a6ff;font-size:11px;padding:2px 6px;border:1px solid #58a6ff;border-radius:4px';
      pasteBtn.textContent = '✓ 确认移动';
      pasteBtn.dataset.type = 'paste-move';
      pasteBtn.dataset.path = curDir;
      moveBar.appendChild(pasteBtn);
      var cancelMove = document.createElement('span');
      cancelMove.style.cssText = 'cursor:pointer;color:#8b949e;font-size:11px;padding:2px 6px;margin-left:4px';
      cancelMove.textContent = '✕ 取消';
      cancelMove.dataset.type = 'cancel-move';
      moveBar.appendChild(cancelMove);
      browser.appendChild(moveBar);
    }

    // 返回上级（不超过根目录）
    if (dirPath) {
      var p = dirPath;
      // 去掉尾部的 /
      if (p.endsWith('/')) p = p.slice(0, -1);
      var r = tbRootPath;
      if (r && r.endsWith('/')) r = r.slice(0, -1);
      if (p !== r) {
        var parentPath = p.substring(0, p.lastIndexOf('/'));
        // 不超过根目录
        if (parentPath.length < (r || '').length) { parentPath = r || p; }
        addTreeEl('back', '..', {path: parentPath, name: '..'});
      }
    }

    // 全部目录（子文件夹）
    var folderItems = d.items || [];
    for (var i = 0; i < folderItems.length; i++) {
      var item = folderItems[i];
      var childPath = dirPath ? dirPath + '/' + item.name : tbRootPath + '/' + item.name;
      addTreeEl('folder', '📁 ' + item.name + ' (' + item.md_count + ')', {path: childPath, name: item.name});
    }

    // 文件
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      var fpath = dirPath ? dirPath + '/' + f.name : tbRootPath + '/' + f.name;
      addTreeEl('file', '📄 ' + f.name + ' (' + f.size_kb + 'KB)', {path: fpath, name: f.name});
    }

    // 分隔线 + 新建
    var sep = document.createElement('div');
    sep.style.cssText = 'border-top:1px solid #30363d;margin:4px 0';
    browser.appendChild(sep);

    addTreeEl('new-folder', '📁 新建目录', {path: curDir});
    addTreeEl('new-file', '📄 新建文件', {path: curDir});

    // 如果空目录且非root
    if (browser.children.length <= 1) {
      addTreeEl('empty', '(空)', {});
    }

    // 恢复滚动位置，防止跳动
    if (savedScroll > 0) { requestAnimationFrame(function(){ browser.scrollTop = savedScroll; }); }
    browser.style.display = 'block';
  } catch(e) {
    browser.innerHTML = '<div style="padding:12px;color:#f85149;text-align:center;font-size:12px">❌ ' + (e.message || '加载失败') + '</div>';
    browser.style.display = 'block';
  }
  browser.onclick = tbHandleTreeClick;
}

function addTreeEl(type, label, data) {
  var browser = document.getElementById('tb-browser');
  if (!browser) return;
  var el = document.createElement('div');
  if (type === 'back') {
    el.className = 'tb-back';
    el.style.cssText = 'padding:8px 12px;cursor:pointer;color:#f0c040;font-size:13px;border-bottom:1px solid #21262d;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
  } else if (type === 'folder') {
    el.className = 'tb-folder';
    el.style.cssText = 'padding:8px 12px;cursor:pointer;color:#c9d1d9;font-size:13px;border-bottom:1px solid #21262d;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
  } else if (type === 'file') {
    el.className = 'tb-file';
    el.style.cssText = 'padding:8px 12px;cursor:pointer;color:#8b949e;font-size:13px;border-bottom:1px solid #21262d;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
  } else if (type === 'new-folder') {
    el.className = 'tb-new-folder';
    el.style.cssText = 'padding:8px 12px;cursor:pointer;color:#58a6ff;font-size:13px';
  } else if (type === 'new-file') {
    el.className = 'tb-new-file';
    el.style.cssText = 'padding:8px 12px;cursor:pointer;color:#58a6ff;font-size:13px;border-bottom:none';
  } else if (type === 'empty') {
    el.className = 'tb-empty';
    el.style.cssText = 'padding:12px;color:#8b949e;text-align:center;font-size:12px';
  }
  el.textContent = label;
  if (type !== 'empty') {
    el.dataset.type = type;
    if (data && data.path) el.dataset.path = data.path;
    if (data && data.name) el.dataset.name = data.name;
  }
  browser.appendChild(el);
}

// ===== 树内点击委托 =====
function tbHandleTreeClick(e) {
  e.stopPropagation();
  var target = e.target.closest('[data-type]');
  if (!target) return;
  var type = target.dataset.type;
  var path = target.dataset.path;
  var name = target.dataset.name;

  if (type === 'back') {
    tbCurrentPath = path;
    tbCurrentName = '..';
    tbLoadTree(path);
    tbUpdatePathDisplay();
  } else if (type === 'root') {
    tbCurrentPath = path;
    tbCurrentName = '';
    tbLoadTree(path);
    tbUpdatePathDisplay();
  } else if (type === 'folder') {
    tbCurrentPath = path;
    tbCurrentName = name || '';
    tbLoadTree(path);
    tbUpdatePathDisplay();
  } else if (type === 'file') {
    tbCurrentPath = path;
    tbCurrentName = name || '';
    tbUpdatePathDisplay();
    tbSelectFile(path, name);
  } else if (type === 'current-folder') {
    tbCurrentPath = path;
    tbCurrentName = '';
    tbTreeClose();
    tbUpdatePathDisplay();
  } else if (type === 'new-folder') {
    tbNewFolder(path);
  } else if (type === 'new-file') {
    tbNewFile(path);
  } else if (type === 'move-start') {
    tbMovePath = path;
    tbMoveName = name || '';
    document.getElementById('tb-path-status').textContent = '📌 已标记移动: ' + (name || path);
    tbTreeClose();
  } else if (type === 'paste-move') {
    tbConfirmMove(tbMovePath, path);
  } else if (type === 'cancel-move') {
    tbMovePath = '';
    tbMoveName = '';
    tbLoadTree(tbCurrentBrowsePath);
    document.getElementById('tb-path-status').textContent = '已取消移动';
  }
}

function tbUpdatePathDisplay() {
  var lbl = document.getElementById('tb-path-label');
  if (lbl) lbl.textContent = tbCurrentName || '选择文件...';
  var cur = document.getElementById('tb-cur-path');
  if (cur) cur.textContent = tbCurrentPath ? tbCurrentPath : '';
  var renameBtn = document.getElementById('tb-rename-btn');
  var deleteBtn = document.getElementById('tb-delete-btn');
  var moveBtn = document.getElementById('tb-move-btn');
  if (tbCurrentPath) {
    if (renameBtn) renameBtn.style.display = '';
    if (deleteBtn) deleteBtn.style.display = '';
    if (moveBtn) moveBtn.style.display = '';
  } else {
    if (renameBtn) renameBtn.style.display = 'none';
    if (deleteBtn) deleteBtn.style.display = 'none';
    if (moveBtn) moveBtn.style.display = 'none';
  }
}

function tbTreeClose() {
  var b = document.getElementById('tb-browser');
  if (b) b.style.display = 'none';
}

// 点击树外关闭+清选择
// 🔧 修复：保存按钮和编辑区域在 tb-content-area（不在 tb-toolbar-row 内），
//    点击保存时不触发路径清除
document.addEventListener('click', function(e) {
  var b = document.getElementById('tb-browser');
  var tb = document.getElementById('tb-toolbar-row');
  var editArea = document.getElementById('tb-content-area');
  // 如果点击在编辑区域（包含保存按钮），不清除路径
  if (editArea && editArea.style.display !== 'none' && editArea.contains(e.target)) return;
  if (tb && !tb.contains(e.target) && !b.contains(e.target)) {
    // 点击工具栏外清除选择
    if (tbCurrentPath) {
      tbCurrentPath = '';
      tbCurrentName = '';
      tbUpdatePathDisplay();
    }
  }
  if (b && b.style.display === 'block' && !e.target.closest('#tb-browse-btn') && !b.contains(e.target)) {
    b.style.display = 'none';
  }
});

// ===== 文件操作 =====
async function tbSelectFile(fullPath, fileName) {
  if (!fullPath || !fileName) return;
  tbCurrentPath = fullPath;
  tbCurrentName = fileName;
  document.getElementById('tb-content-area').dataset.currentPath = fullPath;
  tbUpdatePathDisplay();
  tbTreeClose();
  document.getElementById('tb-content-area').style.display = 'block';
  document.getElementById('tb-content').value = '加载中...';
  var pwEl = document.getElementById('crypt-password');
  var pw = pwEl ? pwEl.value : '';
  var dd = await api.tbRead(fullPath, pw);
  if (dd.ok) {
    document.getElementById('tb-content').value = dd.content || '';
    document.getElementById('tb-save-btn').style.display = '';
  } else {
    document.getElementById('tb-content').value = '无法读取: ' + (dd.error || '未知错误');
  }
}

async function tbSaveFile() {
  var editArea = document.getElementById('tb-content-area');
  var path = editArea && editArea.dataset.currentPath ? editArea.dataset.currentPath : tbCurrentPath;
  var content = document.getElementById('tb-content');
  if (!path) { document.getElementById('tb-path-status').textContent = '❌ 未选择文件'; return; }
  if (!content) { document.getElementById('tb-path-status').textContent = '❌ 编辑器未找到'; return; }
  var txt = content.value;
  var st = document.getElementById('tb-path-status');
  st.textContent = '⏳ 保存中...';
  try {
    var d = await api.tbSave(path, txt || '');
    st.textContent = d.ok ? '✅ 保存成功' : '❌ ' + (d.error || '保存失败');
  } catch(e) {
    st.textContent = '❌ 网络错误: ' + (e.message || e);
  }
}

function tbCopyPath() {
  var editArea = document.getElementById('tb-content-area');
  var fallbackPath = editArea && editArea.dataset.currentPath ? editArea.dataset.currentPath : '';
  if (!tbCurrentPath && !fallbackPath) {
    document.getElementById('tb-path-status').textContent = '请先选择文件或目录';
    return;
  }
  var copyPath = tbCurrentPath || fallbackPath;
  try {
    var ta = document.createElement('textarea');
    ta.value = copyPath;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    document.getElementById('tb-path-status').textContent = '✅ 已复制: ' + copyPath;
  } catch(e) {
    document.getElementById('tb-path-status').textContent = '✅ 路径: ' + copyPath;
  }
}

// 通用：弹出内联输入框（替换浏览器 prompt()）
function tbShowPrompt(title, defaultValue) {
  return new Promise(function(resolve) {
    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
    var box = document.createElement('div');
    box.style.cssText = 'background:#21262d;border:1px solid #30363d;border-radius:8px;padding:20px;min-width:320px';
    box.innerHTML = '<div style="color:#c9d1d9;margin-bottom:12px;font-size:13px">' + title + '</div>' +
      '<input class="tb-prompt-input" type="text" value="' + (defaultValue || '').replace(/"/g,'&quot;') + '" style="width:100%;padding:8px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;font-size:13px;box-sizing:border-box">' +
      '<div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">' +
      '<button class="tb-prompt-cancel" class="btn" type="button" style="padding:6px 16px">取消</button>' +
      '<button class="tb-prompt-confirm" class="btn btn-primary" type="button" style="padding:6px 16px">确定</button></div>';
    wrapper.appendChild(box);
    document.body.appendChild(wrapper);
    var input = wrapper.querySelector('.tb-prompt-input');
    input.focus();
    input.select();
    function cleanup() { if (wrapper.parentNode) wrapper.parentNode.removeChild(wrapper); }
    wrapper.querySelector('.tb-prompt-confirm').onclick = function(e) { e.preventDefault(); e.stopPropagation(); var v = input.value.trim(); cleanup(); resolve(v); };
    wrapper.querySelector('.tb-prompt-cancel').onclick = function(e) { e.preventDefault(); e.stopPropagation(); cleanup(); resolve(null); };
    input.onkeydown = function(e) { if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); var v = input.value.trim(); cleanup(); resolve(v); } if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cleanup(); resolve(null); } };
  });
}

async function tbNewFolder(dirPath) {
  var name = await tbShowPrompt('新目录名：');
  if (!name) return;
  var d = await api.tbCreate(dirPath, name, true);
  document.getElementById('tb-path-status').textContent = d.ok ? '✅ 目录已创建: ' + name : '❌ ' + (d.error || '创建失败');
  if (d.ok) tbLoadTree(dirPath);
}

async function tbNewFile(dirPath) {
  var name = await tbShowPrompt('新文件名（例如 notes.md）：');
  if (!name) return;
  if (!name.endsWith('.md')) name += '.md';
  var d = await api.tbCreate(dirPath, name, false);
  document.getElementById('tb-path-status').textContent = d.ok ? '✅ 文件已创建: ' + name : '❌ ' + (d.error || '创建失败');
  if (d.ok) tbLoadTree(dirPath);
}



async function tbDelete() {
  if (!tbCurrentPath) return;
  var label = tbCurrentName || tbCurrentPath.split('/').pop();
  if (!confirm('删除 "' + label + '" - 确定吗？')) return;
  if (!confirm('再次确认："' + label + '"删除后不可恢复。')) return;
  document.getElementById('tb-path-status').textContent = '正在删除 ' + label + '...';
  var d = await api.tbDelete(tbCurrentPath);
  if (d.ok) {
    document.getElementById('tb-path-status').textContent = '✅ 已删除: ' + label;
    var curPath = tbCurrentPath;
    tbCurrentPath = '';
    tbCurrentName = '';
    tbUpdatePathDisplay();
    document.getElementById('tb-content-area').style.display = 'none';
    var parent = curPath.substring(0, curPath.lastIndexOf('/'));
    if (parent) tbLoadTree(parent);
  } else {
    document.getElementById('tb-path-status').textContent = '❌ ' + (d.error || '删除失败');
  }
}

async function tbRename() {
  var capturedPath = tbCurrentPath;
  if (!capturedPath) return;
  var oldName = tbCurrentName || capturedPath.split('/').pop();
  var newName = await tbShowPrompt('重命名 "' + oldName + '" 为：', oldName);
  if (!newName || newName === oldName) return;
  document.getElementById('tb-path-status').textContent = '正在重命名... (' + capturedPath + ' → ' + newName + ')';
  var d = await api.tbRename(capturedPath, newName, '');
  if (d.ok) {
    document.getElementById('tb-path-status').textContent = '✅ 已重命名为: ' + newName;
    tbCurrentPath = d.new_path || (capturedPath.substring(0, capturedPath.lastIndexOf('/')) + '/' + newName);
    tbCurrentName = newName;
    tbUpdatePathDisplay();
    tbLoadTree(tbCurrentPath.substring(0, tbCurrentPath.lastIndexOf('/')));
  } else {
    document.getElementById('tb-path-status').textContent = '❌ ' + (d.error || '重命名失败');
  }
}

// ===== 移动文件 =====
function tbStartMove() {
  if (!tbCurrentPath) return;
  tbMovePath = tbCurrentPath;
  tbMoveName = tbCurrentName || tbCurrentPath.split('/').pop();
  document.getElementById('tb-path-status').textContent = '📌 已标记: ' + tbMoveName + '，打开树选择目标目录';
  // 自动打开树
  tbToggleBrowser();
}

async function tbConfirmMove(source, targetDir) {
  if (!source || !targetDir) return;
  var name = source.split('/').pop();
  if (!name) return;
  document.getElementById('tb-path-status').textContent = '正在移动...';
  var st = document.getElementById('tb-path-status');
  var d = await api.tbRename(source, name, targetDir);
  tbMovePath = '';
  tbMoveName = '';
  if (d.ok) {
    st.textContent = '✅ 已移动至: ' + targetDir;
    tbCurrentPath = '';
    tbCurrentName = '';
    tbUpdatePathDisplay();
    tbLoadTree(targetDir);
  } else {
    // Fallback: try with full new path
    var newFullPath = targetDir + '/' + name;
    var d2 = await api.tbRename(source, name, targetDir);
    if (d2.ok) {
      st.textContent = '✅ 已移动至: ' + targetDir;
      tbCurrentPath = '';
      tbCurrentName = '';
      tbUpdatePathDisplay();
      tbLoadTree(targetDir);
    } else {
      st.textContent = '❌ ' + (d2.error || '移动失败');
      tbLoadTree(targetDir);
    }
  }
}




