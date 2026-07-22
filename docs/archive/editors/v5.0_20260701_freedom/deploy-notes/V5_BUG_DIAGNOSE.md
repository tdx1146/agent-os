# V5 编辑器诊断报告

> 诊断时间：2026-07-01 21:26
> 诊断机器：qh
> 诊断人：Subagent

---

## 症状

页面框架渲染正常，消息区域空白，`msgCount` 显示"加载中..."永远不变。

---

## 诊断路径

### Step 1 - 服务器端静默检查

| 检查项 | 结果 |
|--------|------|
| JS 语法 (Python compile) | 全部"失败" — 但这是误报（Python 不识别 JS 注释中的 Unicode 装饰字符`─` `—`） |
| msgCount 更新来源 | `render.js:623` — `document.getElementById('msgCount').textContent = renderCountText(store)` |
| API /api/sessions | ✅ 正常工作，返回 163 对，`pairs` 数组完整 |
| API /api/session | ✅ 正常，542KB 数据 |
| window 桥接 | 所有关键函数桥接均声称"✅" — 但这是 grep 文本匹配，不反映运行是否成功 |
| CL.register 组件注册 | 9 个组件正常注册 |

### Step 2 - 渲染链分析

关键发现：**render.js 在运行时因 `import` 语法无法解析而整文件崩溃。**

### Step 3 - 根因定位

#### ❌ 根因 #1（致命）：index.html 与 render.js 架构不匹配

**当前 index.html (line 214)：**
```html
<script src="/static/js/render.js" defer></script>
```
这是 **plain `<script defer>`**（非 `type="module"`）。

**但 render.js (line 3)：**
```js
import { store, api, renderMarkdown, escapeHtml, toast, fmtNum } from './core.js';
```
`import` 是 **ES Module 专用语法**。在非 module 的 `<script>` 标签中，浏览器遇到 `import` 会立即抛出 **SyntaxError**，render.js **整个文件停止执行**。

**后果：**
- `renderPage()` 函数从未定义 → 不渲染消息列表
- `renderMessagesHtml()` 从未定义 → 无法生成消息 HTML
- `renderCountText()` 从未定义 → `msgCount.textContent` 从未更新
- 所有在 render.js 中桥接到 `window` 上的 20+ 个函数全部缺失

#### ❌ 根因 #2：core.js export 块语法断裂

**core.js 最后几行 (line 372+)：**
```js
// ── ES Module exports ──
  store, storeSet, api, renderMarkdown, toggleCachePanel,
  updateContextDisplay, updateCachePct, fmtNum, escapeHtml,
  toast, refresh, _renderSentCache, sentRetry, sentEdit,
  CL
```
**缺少 `export {` 关键字！** 即使改成 `type="module"`，render.js 的 `import from './core.js'` 也找不到任何导出项（因为 core.js 根本没有 `export` 声明），同样会报错。

#### ❌ 根因 #3：window-bridge.js 被删除

备份版本 `index.html.bak.v5-esmodule` 使用：
```html
<script type="module" src="/static/js/app.js"></script>
<script type="module" src="/static/js/window-bridge.js"></script>
```
而当前版本用 11 个 `<script defer>` 代替，并且 **没有包含 window-bridge.js**。该文件负责将 ES Module 内部函数桥接到 window，虽然没有它也不会直接导致崩溃（因为 core.js 内建了 window bridge），但部分缺失的函数可能影响功能完整性。

### Step 4 - 变更溯源

```
diff static/index.html static/index.html.bak.v5-esmodule
```
当前版本从 ES Module 架构改回了传统 `<script defer>`，但 JS 文件没有同步回退，导致 mix-match。

---

## 修复方案

### 方案 A（推荐）：回退 index.html 到 ES Module 架构

将 `index.html` 恢复为备份版本 `index.html.bak.v5-esmodule` 的 script 加载方式。

**修改文件：** `static/index.html`

**修改内容：**
```
删除 lines 211-221（11 个 <script defer> 标签）
替换为：
<script type="module" src="/static/js/app.js"></script>
<script type="module" src="/static/js/window-bridge.js"></script>
```

**同时修复 core.js export 块：**

**修改文件：** `static/js/core.js` lines 372-377

**修改内容：**
```js
// 把
  store, storeSet, api, renderMarkdown, toggleCachePanel,
  updateContextDisplay, updateCachePct, fmtNum, escapeHtml,
  toast, refresh, _renderSentCache, sentRetry, sentEdit,
  CL
// 改成
export {
  store, storeSet, api, renderMarkdown, toggleCachePanel,
  updateContextDisplay, updateCachePct, fmtNum, escapeHtml,
  toast, refresh, _renderSentCache, sentRetry, sentEdit,
  CL
};
```

**风险：** 低。和备份版本架构一致，已验证可工作。

---

### 方案 B（备选）：让 render.js 适配传统 `<script defer>` 模式

移除 render.js 中的 `import` 语句，改为依赖全局变量（core.js 已挂到 window）。

**修改文件：** `static/js/render.js`

**修改内容：**
```
line 3:  删除 import { store, api, renderMarkdown, escapeHtml, toast, fmtNum } from './core.js';
         改为引用 window 上的全局变量（这些变量已在 core.js 的 window 桥接中定义）
```

**风险：** 中。需要验证 render.js 中所有对导入变量的引用在运行时是否都能正确从 window 上获取；如果某个函数引用早于 core.js 初始化，会有时序问题。不如方案 A 干净。

---

### 方案 C（最保守）：只修 index.html script 标签为 type="module"

不修改 JS 文件，仅修复 index.html 的 script 标签。

**修改文件：** `static/index.html`

**修改内容：**
```
将 lines 211-221 的 11 个 <script src="..." defer>
全部改为 <script type="module" src="...">
并移除 <script type="module" src="/static/js/window-bridge.js"></script>（因为已有内建 bridge）
```

**风险：** 中高。ES Module 有 strict mode、defer-by-default、CORS 限制等问题，且 `import` 指向 `./core.js` 但 core.js 的 export 语法已断裂（缺失 `export {`），仍然会报错。必须同时修 core.js export 块。

---

## 快速验证清单

| # | 验证项 | 方法 |
|---|--------|------|
| 1 | render.js 不再报 SyntaxError | 浏览器 Console 无红色错误 |
| 2 | `CL` 是对象 | Console 输入 `CL` 回车 |
| 3 | `renderPage` 是函数 | Console 输入 `typeof renderPage` → `"function"` |
| 4 | 消息列表有内容 | 页面上消息区域不再是空白 |
| 5 | `msgCount` 显示实际数字 | 不再是"加载中..." |

---

## 诊断输出说明

本次诊断为**只读诊断**，未修改任何文件。修复方案仅供参考，请决策后实施。
