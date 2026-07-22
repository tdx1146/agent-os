# 需求分解

## dandan 的原话

三条核心指令：

> 1. 标题版本号修好（不能硬编码）
> 2. 版本更新规则完整建立（不能再出现漏文件、忘改号）
> 3. 创建完整的新版本——以 **当前正在运行的所有文件** 为基准，保存到 `/vol1/@team/qh团队/QH/AI专用/编辑器所有版本/`

## 我理解的他要我干什么

- **标题修好**：`static/index.html` 第 6 行 `<title>轻如烟姐姐 对话编辑器 v2026-06-25</title>` 是硬编码的，6月25号定稿后就再也没变过，即使后面升级了 v4.1 也没人记得改。需要把它变成动态读取，不再依赖人工手动改 HTML。
- **版本更新规则**：目前有零散的规则碎片（SKILL.md 架构原则里有备份要求，deploy-notes 目录里有一些审计记录），但没有一份完整的、可执行的版本更新操作说明书。应该要补齐，让以后的人（或者 AI agent）按步骤走就不会漏文件、忘改号。
- **创建完整的新版本**：当前运行的是 v4.1，但归档目录 `v4.1_20260626_inject-fix/` 只存了 `edit-web.py` + `inject-helper.mjs` + `utils/` + `handlers/` + `static/`，缺少一些边角文件（`start-clean.sh` 以外还有 `VERSION`、`editor-config.json`、`watchdog.sh`、`health-check.sh` 等可能有用的辅助文件）。新版本必须以 **当前运行的全部文件** 为基准做一份快照，确保能完整回滚。

## 拆分为子任务

### 子任务A：审计需求本身 ✓（本文件即产出）

- 理解 dandan 三条指令的完整意图
- 确认当前状态和差距
- 拆分为可执行的子任务
- 确定验收标准

### 子任务B：修复标题 + 建立版本更新规则

#### B1. 修复标题硬编码问题

**现状**:
- `static/index.html` 第 6 行: `<title>轻如烟姐姐 对话编辑器 v2026-06-25</title>`（硬编码的旧版本号）
- 没有 `/api/version` 端点
- 没有任何文件或常量系统提供当前版本的权威数据源

**要做的事**:
1. 在 `edit-web.py` 或某处添加版本常量（例如 `VERSION = "v4.2"`），作为单一数据源
2. 新增 `/api/version` 端点（在 `router.py` 注册、在 `system_handler.py` 添加 `handle_version`），返回 `{"version": "v4.2", "date": "2026-06-28"}`
3. 修改 `static/index.html`，让 `<title>` 通过 JS 从 `/api/version` 获取版本号后动态设置（方案 A），或至少写一个 `/js/version.js` 变量引用（避免硬编码）
4. 如果选方案 A，还需要在页面加载时 JS 调用 API 更新 title，并同步更新 header 或 nav 中的版本显示文字

**注意事项**:
- `edit-web.py` 本身不含版本常量，需要决定放哪里：直接写在 `edit-web.py` 顶部？还是创建一个 `version.py` 模块？
- 推荐做法：在 `utils/config.py` 中或新建 `utils/version.py` 定义版本常量，`edit-web.py` 引用，`system_handler.py` 中新增 `handle_version` 读取它并返回
- `router.py` 需要加一行路由注册，老版本路由在 `def get(handler)` 中按 `if cp == '/api/...'` 模式添加

#### B2. 建立完整的版本管理规则文档

**现状**:
- SKILL.md 架构原则第 1 条：备份 + 日期戳归档 + 回滚指南 + 改动清单 — 没错，但太概括
- `revisions/revert-guide.md` — 有回滚指南，但内容没更新到 v4.1
- `VERSION` — 运行目录中不存在
- 没有完整的「从开发到部署到归档到发布」操作流程

**要做的事**:
1. 创建一份 `VERSION_MANAGEMENT.md`（放在 `scripts/` 或 `scripts/deploy-notes/` 下），包含：
   - 版本号规则（semver-like：主版本.次版本_日期_功能标记）
   - 版本常量定义在哪里（谁负责更新）
   - 从开发到发布的完整检查清单（pre-release checklist）：
     - ✅ 更新 `VERSION` 常量（单一数据源）
     - ✅ 确保 title 自动读取最新版本号（不再需要手动改 HTML）
     - ✅ 哪些文件必须同步到归档目录
     - ✅ 写 CHANGELOG 条目
     - ✅ 更新回滚索引
     - ✅ 验证所有文件已提交/备份
   - 回滚操作流程
   - 紧急修复时的版本号策略

#### B3. 修复现有回滚文档

- 更新 `revisions/revert-guide.md`，补上 v4.1（和即将创建的 v4.2）的条目
- 清理错误的描述（如 `❌ handlers/ 为空壳` 等过时内容）

### 子任务C：完整备份当前运行版本

#### C1. 确认当前运行的所有文件

**现状**:
- PID 514381，cwd = `/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/`
- 已确认 `edit-web.py` 和 `inject-helper.mjs` 与 v4.1 归档完全一致（diff exit 0）
- v4.1 归档不含：
  - `start-clean.sh` ✅ 在归档中
  - `VERSION` ❌ 不存在
  - `editor-config.json` ❌ 不在归档中
  - `watchdog.sh` ❌ 不在归档中
  - `health-check.sh` / `health-loop.sh` ❌ 不在归档中
  - `cache_monitor.py` ❌ 不在归档中
  - 其他 `.py` 辅助脚本 ❌ 不在归档中
  - `__pycache__/` ❌ 不需要（编译缓存）

**要做的事**:
1. 确认当前 PID 的唯一性：`ps -p 514381 -o pid,cmd`
2. 确定备份范围：以 `edit-web.py` 为入口，凡是被 import 的模块都包含，加上配置文件和辅助脚本
3. 建议的备份清单（文件级别）：

**必须包含（核心可运行文件）**:
| 文件 | 原因 |
|------|------|
| `edit-web.py` | 主后端入口 |
| `inject-helper.mjs` | WS 注入子进程 |
| `utils/config.py` | 配置模块 |
| `utils/crypto.py` | 加密模块 |
| `utils/inject.py` | 注入 WS 封装 |
| `utils/momo.py` | 摸摸协议 |
| `utils/secretary.py` | 文件变更追踪 |
| `utils/session.py` | 会话读写 |
| `utils/tb_handler.py` | 文件浏览器后端 |
| `utils/__init__.py` | 包声明 |
| `handlers/router.py` | 路由分发 |
| `handlers/system_handler.py` | 系统状态 |
| `handlers/session_handler.py` | 会话 API |
| `handlers/file_handler.py` | 文件浏览 |
| `handlers/inject_handler.py` | 注入 API |
| `handlers/helper_handler.py` | 助手 API |
| `handlers/awake_handler.py` | 唤醒 API |
| `handlers/crypto_handler.py` | 加密 API |
| `handlers/momo_handler.py` | 摸摸 API |
| `handlers/__init__.py` | 包声明 |
| `static/index.html` | 前端 HTML |
| `static/css/styles.css` | 样式 |
| `static/js/app.js` | 前端逻辑 |
| `static/js/core.js` | 核心组件 |
| `static/js/editor.js` | 编辑器组件 |
| `static/js/components.js` | UI 组件 |
| `static/js/dashboard.js` | 仪表盘 |
| `static/js/render.js` | 渲染 |
| `static/js/awake.js` | 唤醒 UI |
| `static/js/cache-monitor.js` | 缓存监控 |
| `static/js/file-browser.js` | 文件浏览器 |
| `static/js/momo.js` | 摸摸 UI |
| `static/js/subagent.js` | 子代理 UI |
| `static/favicon.ico` | 图标 |

**也应包含（辅助/可追溯）**:
| 文件 | 原因 |
|------|------|
| `start-clean.sh` | 启动脚本 |
| `watchdog.sh` | 看门狗 |
| `health-check.sh` | 健康检查 |
| `health-loop.sh` | 健康循环 |
| `editor-config.json` | 编辑器配置 |
| `TODO / VERSION_MANAGEMENT.md` | 版本操作文档 |

**不应包含**:
- `__pycache__/` — 自动生成，无保留价值
- `.bak.*` 文件 — 历史备份，无需复制
- `deploy-notes/` — 独立目录，版本快照中引用即可
- `revisions/` — 独立目录，版本快照中引用即可
- `experimental/` — 实验性文件
- `backup_*` / `backup_old_baks` — 已有独立备份

#### C2. 执行备份

1. 创建目标目录：`v4.2_20260628_current-running/`
2. 复制所有必须文件，保持目录结构
3. 创建 VERSION 声明文件（写入 `v4.2, 2026-06-28`）
4. 对比验证：diff -r 当前运行目录 ↔ 备份目录（排除 __pycache__ 和 .bak 文件）
5. 更新 `VERSION_INDEX.md`（在 `编辑器所有版本/` 下）

## 验收标准

### 标题版本号修好
- [ ] 前端页面加载后，`<title>` 显示的不是 `v2026-06-25`，而是最新的版本号
- [ ] 修改 VERSION 常量后，刷新浏览器 title 自动更新，不需要手动改 HTML
- [ ] `/api/version` 返回 `{"version": "v4.2", "date": "2026-06-28"}` 或类似格式

### 版本更新规则建立
- [ ] `VERSION_MANAGEMENT.md` 存在于 `scripts/deploy-notes/` 目录下
- [ ] 文档包含：版本号规则、单一数据源位置、发布检查清单、回滚流程
- [ ] `revisions/revert-guide.md` 已更新，包含 v4.1 和 v4.2
- [ ] 按照检查清单执行一次完整发布流程，没有遗漏步骤

### 完整备份
- [ ] `/vol1/@team/qh团队/QH/AI专用/编辑器所有版本/v4.2_20260628_current-running/` 已创建
- [ ] 包含所有必要文件（核心文件 + 辅助文件）
- [ ] 文件结构与运行目录一致（diff -r 无差异，排除 __pycache__ 和 .bak）
- [ ] `VERSION_INDEX.md` 已更新，反映 v4.2 为当前版本
- [ ] `CHANGELOG.md` 已更新

## 备注

- v4.2 版本号建议：当前运行代码与 v4.1 完全相同（diff exit 0），所以 v4.2 本质上只是「v4.1 的完整归档 + 标题修复」。版本号跳 v4.2 是合理的——因为做了架构改进（版本动态化）和备份完整性提升。
- 版本日期用 2026-06-28（今天是周日，6月28号）。dandan 是在这天提的需求，以这天归档是合理的。
- 备份完成后，务必重启 edit-web.py 让标题修复生效（或者用 `inject-restart` API 热重启）。
