# 前端 JS 模块化方案

> 渐进式 ES Module 迁移，保持全局桥接兼容

## 依赖方向

```
core.js (无外部依赖) → 状态管理 + API 封装 + 工具函数
  ↓
render.js → DOM 渲染层（消息、分页、TTS、提醒、记忆管道）
components.js → CL 组件注册（会话选择器、消化栏、系统健康等）
  ↓
app.js → 组件注册框架 (CL)
dashboard.js → 启动引导
  ↓
editor.js → 对话编辑器（截断、编辑）
awake.js → 唤醒/题库/发送
momo.js → 摸摸协议
file-browser.js → 文件浏览器
subagent.js → 子代理管理
cache-monitor.js → 缓存监控
```

## 文件清单 (12 个 JS 文件)

| 文件 | 行数 | 核心功能 | 内部依赖 |
|------|------|----------|----------|
| core.js | ~310 | store, api, 轮询, 工具函数 | 无 |
| app.js | ~40 | CL 组件框架 | 无 |
| render.js | ~640 | 消息渲染, TTS, 分页, 记忆管道 | store, api, toast, fmtNum, escapeHtml, renderMarkdown |
| components.js | ~310 | CL 组件: 会话选择, 健康, 消化 | CL, api, escapeHtml, updateCachePct |
| dashboard.js | ~40 | 启动引导 | CL, api, updateCachePct |
| editor.js | ~250 | 对话截断/编辑 | store, api, escapeHtml, renderPage, toast, refresh |
| awake.js | ~370 | 唤醒题库/发送 | store, api, escapeHtml, toast, renderPage, refresh, _renderSentCache |
| momo.js | ~350 | 摸摸协议 | api, escapeHtml, refresh |
| file-browser.js | ~460 | 文件浏览器 | api, tbRootPath, tbCurrentPath |
| subagent.js | ~140 | 子代理管理 | api, escapeHtml, toast |
| cache-monitor.js | ~160 | 缓存监控 | api |

## 跨文件共享变量

| 变量 | 定义文件 | 使用文件 | 处理方式 |
|------|----------|----------|----------|
| `_lastRenderHash` | core.js | core.js, render.js | 保留在 window 上 |
| `cachePanelOpen` | core.js | core.js  | 保留在 window 上 |
| `tbRoot/Current/Name/BrowsePath/MovePath` | render.js | render.js, file-browser.js | 保留在 window 上 |
| `_memFileList` | render.js | render.js | 保留在 window 上 |
| `subagentPanelOpen` | render.js | subagent.js | 保留在 window 上 |
| `_awakeBankOpen` | awake.js | awake.js | 保留在 window 上 |
| `_ttsAudio`, `ttsRate` | render.js | render.js | 保留在 window 上 |

## 模块化策略

### 原则
1. **只加不删** — 现有 window 全局照旧，增加 export
2. **桥接层** — 每个文件末尾添加 `window.X = X` 和 `export { X }`
3. **app.js 作为入口** — import 所有模块触发加载
4. **index.html 单入口** — 只保留 `<script type="module" src="/static/js/app.js">`

### index.html 处理
- 移除 11 个 `<script src="..." defer>` 标签
- 替换为单个 `<script type="module" src="/static/js/app.js">`
- 内联 `<script>` 中的 toast 保留（作为降级兜底）

### 回归条件
如果 `type="module"` 加载导致 CORS 或白屏：
- 恢复 index.html 备份
- 将所有 `<script type="module">` 改回 `<script defer>`
- 保留每个文件中的 export 语句（非模块 script 会忽略 export）

## 实际变更总结

### CL 框架从 app.js 移到 core.js
由于 ES Module 加载顺序：app.js import components.js → components.js 在 app.js 主体执行前运行。
而 components.js 需要 CL 变量 → 将 CL 定义从 app.js 移到 core.js（第一个被 import 的基础模块）。

### 共享可变状态处理
在 ES Module 中，`import { x }` 创建只读绑定，不能用 `x = newValue` 修改。
解决方法：共享可变状态（tbRootPath, tbCurrentPath 等）通过 `window.` 访问。
- 定义方：`var tbX = window.tbX = initialValue;`
- 使用方：`window.tbX = newValue;`

### 文件修改清单

| 文件 | 改动 |
|------|------|
| core.js | 添加 CL 框架、4 个缺失的 api 方法、window bridge、ESM export |
| app.js | 简化为纯 ESM 入口（11 个 import）、移除 CL 定义 |
| render.js | 添加 import、window bridge（30个函数）、共享变量 window-export、ESM export |
| components.js | 添加 import（from core.js + render.js）、window bridge、ESM export |
| dashboard.js | 添加 import（from core.js） |
| editor.js | 添加 import（from core.js + render.js）、window bridge、ESM export |
| awake.js | 添加 import（from core.js + render.js）、window bridge（15个函数）、ESM export |
| momo.js | 添加 import、window bridge（16个函数）、ESM export |
| file-browser.js | 添加 import、tb* 变量改为 window. 前缀、window bridge（16个函数）、ESM export |
| subagent.js | 添加 import（from core.js + render.js）、window bridge（5个函数）、ESM export、修复 subagentPollTimer 声明 |
| cache-monitor.js | 添加 import、window bridge、ESM export |
| index.html | 11个 script defer 标签 → 1个 `<script type="module">` |
| 新建 MODULE_MAP.md | 本文件
