======================================================================
  代码审视报告 — 轻如烟对话编辑器
  (基于 Understand Anything 知识图谱生成)
======================================================================

## 一、概述

- 分析时间: 2026-07-01 15:30 CST
- 分析方式: Understand Anything 官方工具（extract-structure.mjs + merge-batch-graphs.py）
- 总文件数: 98
- 总节点数: 801（文件级 98 + 函数 689 + 类 14）
- 总边数: 790（contains 703 + imports 87）
- 代码行规模: moderate（60 代码文件 + 6 脚本 + 27 文档 + 3 标记文件 + 2 配置）

## 二、模块依赖关系

### 2.1 被依赖最多的模块（被引用最多的文件）
| 文件 | 被引用次数 |
|------|-----------|
| `utils/config.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'handlers/awake_handler.py', 'handlers/inject_handler.py', 'handlers/momo_handler.py', 'handlers/system_handler.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/system_handler.py'] |
| `cache_stats_helper.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'revisions/20260612_v1_editor-backup.py', 'revisions/20260613_v2_zuixin.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py'] |
| `handlers/__init__.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'revisions/20260612_v1_editor-backup.py', 'revisions/20260613_v2_zuixin.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py'] |
| `handlers/awake_handler.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'handlers/router.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/router.py'] |
| `handlers/crypto_handler.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'handlers/router.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/router.py'] |
| `handlers/file_handler.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'handlers/router.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/router.py'] |
| `handlers/helper_handler.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'handlers/router.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/router.py'] |
| `handlers/inject_handler.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'handlers/router.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/router.py'] |
| `handlers/momo_handler.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'handlers/router.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/router.py'] |
| `handlers/session_handler.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'handlers/router.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/router.py'] |
| `handlers/system_handler.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'handlers/router.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/router.py'] |
| `utils/momo.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'revisions/20260612_v1_editor-backup.py', 'revisions/20260613_v2_zuixin.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py'] |
| `utils/secretary.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'revisions/20260612_v1_editor-backup.py', 'revisions/20260613_v2_zuixin.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py'] |
| `utils/tb_handler.py` | ['edit-web.py', 'experimental/edit-web_v4.1_subprocess-run.py', 'revisions/20260612_v1_editor-backup.py', 'revisions/20260613_v2_zuixin.py', 'revisions/v4.1_20260626_inject-fix/edit-web.py', 'revisions/v4.2_20260628_version-fix/edit-web.py'] |

### 2.2 依赖最多的模块（导入最多的文件）
| 文件 | 导入数 |
|------|--------|
| `edit-web.py` | 14 |
| `experimental/edit-web_v4.1_subprocess-run.py` | 14 |
| `revisions/v4.1_20260626_inject-fix/edit-web.py` | 14 |
| `revisions/v4.2_20260628_version-fix/edit-web.py` | 14 |
| `handlers/router.py` | 8 |
| `revisions/v4.2_20260628_version-fix/router.py` | 8 |
| `revisions/20260612_v1_editor-backup.py` | 5 |
| `revisions/20260613_v2_zuixin.py` | 5 |
| `handlers/awake_handler.py` | 1 |
| `handlers/inject_handler.py` | 1 |
| `handlers/momo_handler.py` | 1 |
| `handlers/system_handler.py` | 1 |
| `revisions/v4.2_20260628_version-fix/system_handler.py` | 1 |

## 三、高频/高压模块

### 3.1 最大文件（按行数）
| 文件 | 行数 | 语言 |
|------|------|------|
| `revisions/20260613_v2_zuixin.py` | 3877 | py |
| `revisions/20260612_v1_editor-backup.py` | 3772 | py |
| `edit-web.py` | 1935 | py |
| `experimental/edit-web_v4.1_subprocess-run.py` | 1935 | py |
| `revisions/v4.1_20260626_inject-fix/edit-web.py` | 1935 | py |
| `revisions/v4.2_20260628_version-fix/edit-web.py` | 1935 | py |
| `reflection_unified.py` | 844 | py |
| `think_patterns.py` | 664 | py |
| `static/js/render.js` | 656 | js |
| `static/js/file-browser.js` | 473 | js |

### 3.2 函数最多的文件
| 文件 | 函数数 |
|------|--------|
| `revisions/20260613_v2_zuixin.py` | 59 |
| `revisions/20260612_v1_editor-backup.py` | 58 |
| `edit-web.py` | 56 |
| `experimental/edit-web_v4.1_subprocess-run.py` | 56 |
| `revisions/v4.1_20260626_inject-fix/edit-web.py` | 56 |
| `revisions/v4.2_20260628_version-fix/edit-web.py` | 56 |
| `static/js/render.js` | 28 |
| `reflection_unified.py` | 17 |
| `revisions/v4.1_20260626_inject-fix/awake.js` | 17 |
| `static/js/awake.js` | 17 |

## 四、循环依赖分析

未发现循环依赖。

## 五、架构分层概览

知识图谱识别出 9 个架构层：

### Main Backend Server
- **描述**: Core Python backend — edit-web.py is the HTTP/HTTPS server entry point on port 18888/18889
- **节点数**: 13

### Request Handlers (REST API)
- **描述**: HTTP request routing and handler modules for all API endpoints (session, inject, momo, crypto, file, system, awake, helper)
- **节点数**: 10

### Utility Library
- **描述**: Backend utility modules: crypto, inject, momo-pack, secretary, session file IO, file browser, config, version
- **节点数**: 9

### Frontend (Static Assets)
- **描述**: Browser-side JavaScript UI: core state layer, component framework, renderer, editor panel, file browser, dashboard, subagent UI, awakening panel, cache monitor, momo protocol frontend
- **节点数**: 13

### WebSocket Injection Infrastructure
- **描述**: Node.js-based WebSocket injection helper and embed server — connects to Gateway for message injection
- **节点数**: 7

### Configuration
- **描述**: Project configuration files (editor-config.json and intermediate scan data)
- **节点数**: 4

### Documentation & Audit Reports
- **描述**: Project documentation, architecture docs, audit reports, and deploy notes
- **节点数**: 27

### Version History & Revisions
- **描述**: Historical code revisions, version comparisons, and rollback guides
- **节点数**: 16

### Experimental Code
- **描述**: Experimental features and alternative implementations
- **节点数**: 2

## 六、代码建议

### 6.1 大型文件拆分建议

- **`revisions/20260613_v2_zuixin.py`**（3877 行，59 个函数）
  - 建议拆分：此文件承担了过多职责，应考虑按功能拆分。
  - 参考：handler 层已有路由分发模式（router.py），可借此分散该文件的业务逻辑。

- **`revisions/20260612_v1_editor-backup.py`**（3772 行，58 个函数）
  - 建议拆分：此文件承担了过多职责，应考虑按功能拆分。
  - 参考：handler 层已有路由分发模式（router.py），可借此分散该文件的业务逻辑。

- **`edit-web.py`**（1935 行，56 个函数）
  - 建议拆分：此文件承担了过多职责，应考虑按功能拆分。
  - 参考：handler 层已有路由分发模式（router.py），可借此分散该文件的业务逻辑。

- **`experimental/edit-web_v4.1_subprocess-run.py`**（1935 行，56 个函数）
  - 建议拆分：此文件承担了过多职责，应考虑按功能拆分。
  - 参考：handler 层已有路由分发模式（router.py），可借此分散该文件的业务逻辑。

- **`revisions/v4.1_20260626_inject-fix/edit-web.py`**（1935 行，56 个函数）
  - 建议拆分：此文件承担了过多职责，应考虑按功能拆分。
  - 参考：handler 层已有路由分发模式（router.py），可借此分散该文件的业务逻辑。

### 6.2 导入分析

- 共发现 98 个文件中有 13 个存在依赖关系
- 产生的 import 边数: 87
- 建议为 utils/ 中的高引用模块（session.py, config.py）编写接口文档

### 6.3 项目建议

1. **版本管理**: 当前不是 Git 仓库，建议初始化 Git 以便追踪变更历史
2. **测试覆盖**: 未发现测试文件（_test.py / *.spec.*），建议增加单元测试
3. **统一入口**: edit-web.py（1935 行）承载过多职责，建议将核心逻辑拆入 handlers/ 目录
4. **配置文件**: editor-config.json 为基础配置，建议增加更细粒度的环境配置（如 dev/prod）
5. **静态资产优化**: static/js/ 下 11 个 JS 文件，建议路由层统一管理以减少全局命名空间污染

======================================================================
  报告生成完毕
  总览: 801 节点 / 790 边 / 9 层 / 0 循环依赖
  数据来源: Understand Anything v1.0.0 知识图谱
======================================================================