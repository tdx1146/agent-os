# 版本一致性审计报告

**审计日期**: 2026-06-28 17:59  
**审计对象**: 轻如烟编辑器 (edit-web.py + inject-helper.mjs)  
**执行者**: subagent 自动审计  

---

## 1. 当前代码 vs 归档版本对比结果

| 文件 | 当前 vs v4.1 (2026-06-26) | 当前 vs v4 (2026-06-25) | 备注 |
|-----|:------------------------:|:----------------------:|------|
| `edit-web.py` | ✅ 完全一致 (diff exit 0) | 不适用 | 当前运行的就是 v4.1 |
| `inject-helper.mjs` | ✅ 完全一致 (diff exit 0) | 不适用 | 也在 v4.1 归档中 |

**结论**: 当前运行的文件与 `/vol1/@team/qh团队/QH/AI专用/编辑器所有版本/v4.1_20260626_inject-fix/` 完全一致。黄金副本同步无误。

---

## 2. 版本管理规则现状

### 已有的规则

**A. senior-assistant-orchestrator SKILL.md 中（架构原则）**

```
### 1. 版本管理
- 修改任何文件前必须先备份（`cp file.py file.py.bak.$(date +%Y%m%d_%H%M)`）
- 子代理任务完成后，创建一份带日期戳的归档：`scripts/revisions/<模块名>-v<版本>-<日期>.md`
- 保留回滚指南，每次版本迭代更新
- 改动清单写入 deploy-notes，方便回滚
```

**B. MIGRATION_PLAN.md 附录 B（备份脚本）**

有备份命令模板 (`cp edit-web.py edit-web.py.bak.$(date +%Y%m%d_%H%M%S)`)，但没有纳入完整的版本管理生命周期。

**C. 现存版本产物**

- `scripts/revisions/fix-delivery-bug-20260626.md` — 修复记录 ✅
- `scripts/revisions/fix-watchdog-20260626.md` — 修复记录 ✅
- `scripts/revisions/revert-guide.md` — 回滚指南 ✅
- `VERSION` — 版本声明文件 ✅ (内容为 v4.1, 2026-06-27）
- `deploy-notes/` — 部署笔记目录 ✅

### 缺失的规则

1. **❌ 没有前端版本号自动更新规则**
   - `index.html` 中的 `<title>` 不会随代码版本更新
   - 没有任何规则规定「每次新版本部署时必须修改 frontend title」

2. **❌ 没有版本切换时 title 同步的检查清单**
   - 升级 v4 → v4.1 时，代码都备份了，但 title 还是旧的

3. **❌ revert-guide.md 内容未更新到 v4.1**
   - 版本索引中 v4 列在"当前"，实际上当前已是 v4.1
   - v4.1 没有加入回滚索引表
   - 多了一个 `❌ handlers/ 为空壳` 的旧状态条目

4. **❌ 没有版本号的单一数据源**
   - `VERSION` 文件记录 v4.1 — 但是前端 title 不读它
   - 没有 `/api/version` 端点
   - `edit-web.py` 本身没有版本字符串常量

---

## 3. 标题版本号问题

### 当前标题显示什么

前端 title (index.html 第 6 行):
```html
<title>轻如烟姐姐 对话编辑器 v2026-06-25</title>
```

标题显示的是 **2026-06-25** 的版本。

### 为什么

- 标题是**硬编码**在 `index.html` 的 `<title>` 标签中的
- 6月25号发布了 v4 架构重建，当时设置了 `v2026-06-25`
- 6月26号发布了 v4.1 inject-fix，**没有人更新这个 `<title>`**
- 没有自动机制或流程检查来防止这种遗漏

### 怎么修

**立即修复**：将 `index.html` 第 6 行的 `v2026-06-25` 改为 `v2026-06-26` 或 `v4.1-2026-06-26`。

**长期方案（推荐 2 选 1）**：

**方案 A — 前端从 API 获取版本号（最佳）**
- 新增 `/api/version` 端点，返回 `{"version": "v4.1", "date": "2026-06-26"}`
- 前端 `<title>` 通过 JS 动态设置，读取该 API 返回值
- 每次部署只需更新一个数据源（`VERSION` 文件 或 edit-web.py 中的常量）

**方案 B — 写入 deploy-notes 检查清单**
- 在 deploy-notes 模板中增加一项：「✅ 更新 index.html 标题版本号」
- 不改变架构，但通过流程防止遗漏

---

## 4. 建议

### 需要补充的规则（按优先级）

| 优先级 | 规则 | 说明 |
|:-----:|------|------|
| 🔴 P0 | **版本号单一数据源** | 创建 `VERSION` 文件的读取机制，前端从后端 API 获取版本号，或 edit-web.py 文件中定义一个 `__version__ = "v4.1"` 常量，让前端标题动态读取 |
| 🔴 P0 | **更新 revert-guide.md** | 将 v4.1 加入版本索引表，标记 v4 为旧版，删除 `❌ handlers/ 为空壳` 过时条目 |
| 🟡 P1 | **版本切换检查清单** | 在 `deploy-notes/` 模板中明确包含：「✅ 更新 index.html 标题版本号」「✅ 更新 VERSION 文件」「✅ 更新 revert-guide.md 版本索引」|
| 🟡 P1 | **版本标签/打标机制** | 在文件头注释中添加版本日期和变更摘要，例如当前 `edit-web.py` 第 4 行只有 `轻如烟 Edit Web — Universal version`，建议加上日期 |
| 🟢 P2 | **API 版本端点** | 新增 `/api/version` 返回版本号和发布日期，方便后续工具化和自动化 |

### 标题版本号自动化方案（推荐方案 A 详细设计）

**实现步骤**：

1. 在 `edit-web.py` 中新增常量：
   ```python
   __version__ = "v4.1"
   __release_date__ = "2026-06-26"
   ```

2. 在 `system_handler.py` 或 `router.py` 中新增路由 `/api/version`：
   ```python
   @router.get("/api/version")
   def version():
       return {"version": __version__, "date": __release_date__}
   ```

3. 在 `index.html` 中修改：
   ```html
   <title>轻如烟姐姐 对话编辑器</title>
   ```
   + 添加 JS 启动时调用 `/api/version` 动态设置：
   ```javascript
   fetch('/api/version').then(r=>r.json()).then(v => {
       document.title = `轻如烟姐姐 对话编辑器 v${v.version}-${v.date}`;
   });
   ```

4. 将这一步写入 `senior-assistant-orchestrator` SKILL.md 的版本管理规则中。

### 立即修复清单

- [ ] `index.html` 第 6 行: `v2026-06-25` → `v4.1-2026-06-26`（或按方案 A 动态获取）
- [ ] `revert-guide.md`: 补充 v4.1 到版本索引表
- [ ] `VERSION`: 确认内容已为最新（当前是对的：v4.1, 2026-06-27）
- [ ] 在 SKILL.md 的版本管理规则中补充前端标题同步要求

---

## 5. 完整备份记录 (v4.2)

**备份时间**: 2026-06-28 18:14  
**备份方式**: `cp -r` 完整目录副本  
**目标路径**: `/vol1/@team/qh团队/QH/AI专用/编辑器所有版本/v4.2_20260628_current-running/`

### 备份内容

| 类别 | 文件/目录 | 大小 | 说明 |
|:----:|---------|:---:|------|
| 核心文件 | `edit-web.py` | 75,999 B | 主后端 |
| | `inject-helper.mjs` | 14,288 B | WS 注入通道 |
| | `start-clean.sh` | 1,052 B | 启动脚本 |
| 辅助文件 | `embed-server.mjs` | 3,762 B | 嵌入嵌入服务 |
| | `editor-config.json` | 796 B | 编辑器配置 |
| | `README.md` | 7,771 B | 系统说明书 |
| | `VERSION_COMPARISON.md` | 13,053 B | 版本对比 |
| 核心目录 | `handlers/` | 9 文件 + __pycache__ | 路由+8 handler |
| | `utils/` | 9 文件 + __pycache__ | 工具模块 |
| | `static/` | index.html + css/ + js/ | 前端资源 |

### 完整性校验

- ✅ 所有核心文件与运行中实例 100% 一致 (diff exit 0)
- ✅ 所有目录递归比较一致 (diff -rq exit 0)
- ✅ v4.2 新增文件: `embed-server.mjs`, `editor-config.json`, `README.md`, `VERSION_COMPARISON.md`, `utils/version.py`

### v4.1 与 v4.2 差异

v4.2 相对于 v4.1 的增量：

1. **`utils/version.py`** — 新增版本号常量文件，作为唯一数据源
2. **`handlers/router.py`** — 导入并注册 `/api/version` 路由
3. **`handlers/system_handler.py`** — 新增 `handle_version_info()` 方法，使用 `_send_json` 格式
4. **`static/index.html`** — 从静态 title 改为 `<title>轻如烟姐姐 对话编辑器</title>` + JS 动态从 `/api/version` 获取
5. **`static/js/core.js`** — 新增 fetch('/api/version') 动态设置 title
6. **额外文件** — `embed-server.mjs`, `editor-config.json`, `README.md`, `VERSION_COMPARISON.md`
