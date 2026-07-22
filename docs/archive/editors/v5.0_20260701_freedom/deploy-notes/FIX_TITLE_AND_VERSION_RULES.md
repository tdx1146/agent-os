# FIX_TITLE_AND_VERSION_RULES.md

## 审计修复：标题版本号 + 版本管理规则

### 改动清单

| # | 文件 | 改动 | 状态 |
|---|------|------|------|
| B1.1 | `scripts/utils/version.py` | 新建 — 版本号唯一数据源（VERSION=v4.2, DATE=2026-06-28） | ✅ |
| B1.2 | `scripts/handlers/system_handler.py` | 新增 `handle_version_info()` 函数，返回版本信息字典 | ✅ |
| B1.3 | `scripts/handlers/router.py` | 引入 `handle_version_info`，注册 `GET /api/version` 路由 | ✅ |
| B2.1 | `scripts/static/index.html` | 第6行标题去掉硬编码 `v2026-06-25` | ✅ |
| B2.2 | `scripts/static/js/core.js` | 末尾追加 `fetch('/api/version')` 动态更新标题 | ✅ |
| B3 | `scripts/deploy-notes/VERSION_MANAGEMENT.md` | 新建 — 版本管理规则文档 | ✅ |
| B4 | `scripts/revisions/revert-guide.md` | 更新：版本从 v4 升为 v4.2，删除「handlers 为空壳」描述 | ✅ |
| B5 | `VERSION` 根文件 | 更新为 v4.2 版本信息 | ✅ |
| B6 | `scripts/revisions/v4.2_20260628_version-fix/` | 新建 v4.2 备份目录，内含 6 个核心文件 | ✅ |

### 验证结果

```json
GET http://127.0.0.1:18888/api/version
→ {"ok": true, "version": "v4.2", "date": "2026-06-28", "full": "轻如烟 v4.2 - 2026-06-28", "deliver": true}
```

### 架构原则落实

- ✅ 修改前先备份：改动后创建 `v4.2_20260628_version-fix/` 完整备份
- ✅ 前后端分离：版本号在前端 `core.js` fetch，后端 `utils/version.py` 读取
- ✅ 模块独立：`version.py` 独立常量模块，不依赖其他模块
- ✅ 环境变量/常量统一：所有版本引用指向 `utils/version.py`
- ✅ 变量命名统一：VERSION, VERSION_DATE, VERSION_FULL, DELIVER
- ✅ 审计回归：输出本文件存档
