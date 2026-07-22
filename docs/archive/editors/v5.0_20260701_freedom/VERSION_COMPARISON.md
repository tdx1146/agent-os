# 轻如烟版本对比分析报告

> 生成时间：2026-06-25 16:51
> 扫描范围：3个历史分离版本 vs 当前运行的单体版本

---

## 1. 版本对比表

| 维度 | 当前运行（单体） | 版本A (editor-backup) | 版本B (最新版) | 版本C (最新版2) |
|------|:---------:|:-------------:|:--------:|:---------:|
| **edit-web.py 行数** | 3925 | **3772** (-153) | **3877** (-48) | 3925 (完全一致) |
| **与当前版本行差异** | — | 477行差异 | 62行差异 | **0行（完全相同）** |
| **utils/ 模块** | ✅ 6个模块 | ✅ 6个模块 | ✅ 6个模块 | ✅ 6个模块 |
| **utils/ 导入使用** | ✅ 已导入并使用 | ✅ 已导入并使用 | ✅ 已导入并使用 | ✅ 同当前版本 |
| **handlers/router.py 导入** | ✅ 已导入并使用 | ✅ 已导入并使用 | ✅ 已导入并使用 | ✅ 同当前版本 |
| **handler 骨架文件** | 7个空壳(未导入) | 7个空壳(未导入) | ❌ 不存在 | 7个空壳(未导入) |
| **inject-helper.mjs** | ✅ 359行 | ❌ 不存在 | ✅ 与当前一致 | ✅ 与当前一致 |
| **static/js/ 目录** | ✅ scripts/static/js/ | ✅ static/js/ | ❌ 不存在 | ✅ static/js/ (与当前相同) |
| **sandglass_log 功能** | ✅ 有 | ❌ 无 | ❌ 无 | ✅ 有 |
| **配置校验** | ✅ 完整(6项检查) | ❌ 基本 | ❌ 基本 | ✅ 完整 |
| **截断安全校验** | ✅ 双重验证 | ❌ 无 | ❌ 无 | ✅ 双重验证 |

### 关键发现

**❗ 版本C的edit-web.py与当前运行版本完全相同** — diff 输出 `IDENTICAL`。这意味着版本C根本没有做真正的"分离"，只是把当前文件复制了一份，同时在旁边创建了 handlers/ 和 utils/ 目录。

**❗ 版本B的edit-web.py只差62行，且同样使用了 router.py** — 版本B实际上已经是部分分离的架构了。

**❗ 版本A的edit-web.py差异最大（-153行）** — 但主要是因为配置部分被简化，而不是真正把逻辑抽走了。

---

## 2. 当前版本的"伪单体"架构真相

### 当前版本的实际架构

当前运行的 `edit-web.py` 其实**已经是一个部分分离的版本**：

```
edit-web.py (3925行)
├── 顶层配置 (第134-275行) — 配置发现 + 校验
├── 工具函数 (第37-42行) — 从 utils/ 导入
│   ├── from utils.momo import ...       ✅ 已分离
│   ├── from utils.secretary import ...   ✅ 已分离
│   └── from utils.tb_handler import ...  ✅ 已分离
├── Handler 类方法 — 主要业务逻辑 (仍在 edit-web.py 内)
└── 路由分发 (第2197行)
    └── from handlers import router     ✅ 已分离
```

### 已分离的部分

| 模块 | 位置 | 状态 |
|------|------|------|
| **路由分发 (do_GET/do_POST)** | `handlers/router.py` | ✅ 52+ 路由全部通过 router 处理 |
| **摸摸打包/状态** | `utils/momo.py` (222行) | ✅ import 使用 |
| **秘书模块** | `utils/secretary.py` (87行) | ✅ import 使用 |
| **TB文件浏览器** | `utils/tb_handler.py` (216行) | ✅ import 使用 |
| **加密工具** | `utils/crypto.py` (55行) | ✅ 存在但未确认是否通过 utils 路径使用 |
| **WS注入** | `utils/inject.py` (36行) | ✅ 存在 |
| **会话管理** | `utils/session.py` (138行) | ✅ 存在 |

### 未分离的部分

| 模块 | 位置 | 状态 |
|------|------|------|
| **Handler 类 (80+方法)** | `edit-web.py` 内 | ❌ 仍为内联方法 |
| **crypto_handler.py** | `handlers/` | ❌ 空壳 (4行, 只有注释) |
| **file_handler.py** | `handlers/` | ❌ 空壳 (4行, 只有注释) |
| **helper_handler.py** | `handlers/` | ❌ 空壳 (4行, 只有注释) |
| **inject_handler.py** | `handlers/` | ❌ 空壳 (4行, 只有注释) |
| **system_handler.py** | `handlers/` | ❌ 空壳 (4行, 只有注释) |
| **momo_handler.py** | `handlers/` | ❌ **有函数体但依赖不存在模块** |
| **session_handler.py** | `handlers/` | ❌ **有函数体但依赖不存在模块** |

---

## 3. 分离缺陷分析 — 为什么分离版本没跑起来

### 致命缺陷 #1：`edit_web_merged` 不存在

`momo_handler.py` 和 `session_handler.py` 在第5行写着：

```python
from edit_web_merged import *
```

但 **`edit_web_merged.py` 在所有版本中都不存在**。这导致一旦 Python 尝试加载这些 handler 文件，就会抛出 `ModuleNotFoundError`。由于这些 handler 未被 edit-web.py import，因此问题被"隐藏"了——但也意味着无法使用。

### 致命缺陷 #2：Handler 骨架全是空的

7个 handler 文件中有5个是空的：

| 文件 | 大小 | 内容 |
|------|------|------|
| `crypto_handler.py` | 149B | 只有注释和 docstring |
| `file_handler.py` | 145B | 只有注释和 docstring |
| `helper_handler.py` | 149B | 只有注释和 docstring |
| `inject_handler.py` | 149B | 只有注释和 docstring |
| `system_handler.py` | 149B | 只有注释和 docstring |

这些文件没有定义任何函数。它们是为了"路由处理函数"预留的骨架，但从未填充实际代码。

### 致命缺陷 #3：router.py 依赖魔术引用

```python
_M = None
def g(name): return getattr(_M, name, None) if _M else None
```

router.py 通过 `_M = _sys.modules[__name__]` 绑定到主模块，使用 `g()` 函数通过字符串名查找主模块中的函数。这种模式：
- 在代码层面可以工作（当前版本就是这样跑的）
- 但**完全不利用分离架构的优势** — handler 们没有自己的模块
- 依然强耦合：router.py 依赖于主模块中存在所有 `_handle_xxx` 方法

### 缺陷 #4：Handler 类的 80+ 方法未拆分

当前版本的 Handler 类是一个**巨型类**，包含80多个方法。这些方法从未被迁移到 handler 文件中。例如：
- `_handle_encrypt()` → 应该去 `crypto_handler.py`，但那里是空的
- `_handle_inject()` → 应该去 `inject_handler.py`，但那里是空的
- `_handle_api()` → 应该去 `helper_handler.py`，但那里是空的

### 缺陷 #5：配置模块线差异（版本A vs 当前）

版本A的配置更简单粗暴，没有 `_resolve_int()` 辅助函数，没有配置校验：

| 特性 | 版本A | 当前版本 |
|------|-------|---------|
| 配置优先级链 | env → config.json | env → config.json → openclaw.json |
| 端口解析辅助函数 | ❌ 无 | ✅ `_resolve_int()` |
| 6项配置校验 | ❌ 无 | ✅ 全面 |
| LIGHT_SMOKE_DIR 自动发现 | ✅ 有 | ✅ 有 |
| GATEWAY_PORT 后备值 | 19107 (硬编码) | None (要求配置) |

### 版本B vs 当前版本差异

版本B与当前版本的62行差异主要是：

1. **无 sandglass_log**（版本B缺失 `_sandglass_log()` 函数和 `sandglass_log_wrapper.py` 调用）
2. **无截断安全校验**（双重验证 + 50%截断保护）
3. **cache_stats 引用不同**（版本B用 `cache_stats_helper`，当前版本额外有 `cache_monitor` 的 fallback）
4. **inject timing 计算不同**（版本B用 `_t2-_t1`，当前用 `_t2-_t0`）

---

## 4. 如果让版本C跑起来，需要修复什么

版本C的 `edit-web.py` 和当前版本完全相同，**它已经能"跑"了**。但如果目标是**真正前后端分离**，需要：

### 步骤1：填充 handler 文件（最关键）

将 Handler 类中的方法迁移到对应的 handler 文件中：

```python
# handlers/crypto_handler.py
def handle_encrypt(handler):
    """处理 /api/encrypt"""
    return handler._handle_encrypt()
```

需要迁移的方法：
- `crypto_handler.py` ← `_handle_encrypt()`
- `file_handler.py` ← `_handle_list_files()`, `_handle_browse_dirs()`
- `inject_handler.py` ← `_handle_inject()`, `_handle_edit()`, `_handle_api()`
- `helper_handler.py` ← `handle_abort()`, `handle_thinking_toggle()`, 等
- `system_handler.py` ← `_system_health()`, `_get_usage_status()`
- `session_handler.py` ← 已部分实现但需要修复 import
- `momo_handler.py` ← 已部分实现但需要修复 import

### 步骤2：修复 `edit_web_merged` 引用

将 `momo_handler.py` 和 `session_handler.py` 中的：

```python
from edit_web_merged import *
```

改为 import 具体模块：

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import edit_web  # 需要把 edit-web.py 重命名
```

或者把引用的函数内联进去。

### 步骤3：让 router.py 分发到 handler 文件

改变 router.py 的分发模式，从：

```python
if cp == '/api/encrypt': return handler._handle_encrypt()
```

改为调用 handler 模块：

```python
if cp == '/api/encrypt':
    from handlers.crypto_handler import handle_encrypt
    return handle_encrypt(handler)
```

### 步骤4：统一配置文件路径

版本A和当前版本的配置模块差异较大，需要统一。建议用当前版本的配置模块（更完善），抽到 `utils/config.py` 中。

### 步骤5：去除重复的 static/js/

当前版本有 `scripts/static/js/`，版本C有 `static/js/`。需要统一路径，消除 JS 文件的冗余副本。

---

## 5. 备份机制评估 — 为什么"保存工作"失败了

### 5.1 文件路径混乱

```
所有自动化/
├── 轻如烟/                        ← 实际运行目录
│   └── scripts/
│       ├── edit-web.py            ← 3925行，当前运行的版本
│       ├── static/js/             ← JS文件独立副本
│       ├── utils/                 ← 部分分离的模块
│       └── handlers/              ← 路由已分离，handler是空壳
│
├── 找回自己/                       ← 备份/存档目录（不是可运行的）
    ├── editor-backup/             ← "版本A" — 最早的分离尝试（3772行）
    ├── 最新版/                     ← "版本B" — 第二次（3877行）
    └── 最新版2/                   ← "版本C" — 第三次（与当前完全相同）
```

**问题：**
- 目录名 `找回自己` 表述不清（是备份还是可运行版本？）
- `最新版` 和 `最新版2` 缺乏时间标记，不知道哪个更新
- `editor-backup` 的 `editor` 指向哪个项目不明
- 版本C只是副本，被误认为"分离版本"

### 5.2 没有版本标记

```bash
# 任何版本中都没有：
$ find 找回自己/ -name "VERSION*" -o -name ".git*"
# → 空
```

- 没有 Git 仓库
- 没有 VERSION 文件
- 文件注释中没有明确的版本号和变更日志
- 无法判断"哪个版是哪个版"

### 5.3 缺少切换/回滚机制

- 没有启动脚本能方便切换版本
- 没有 `version.txt` 或软链指向当前活动版本
- 想回滚需要手动复制文件，容易出错

### 5.4 版本C的静态JS与当前版本完全相同

```
diff -r 轻如烟/scripts/static/js/ 找回自己/最新版2/static/js/
# → 无输出（完全一致）
```

版本C的 JS 文件与当前版本完全一致，说明**JS 端也没有进步**。

### 5.5 推荐的备份机制

```
所有自动化/
├── 轻如烟/
│   ├── scripts/
│   │   ├── edit-web.py          ← 当前运行
│   │   ├── VERSION              ← 版本标记
│   │   └── revisions/           ← 归档目录
│   │       ├── 20260612_v1/     ← 版本A（带日期+序号）
│   │       ├── 20260613_v2/     ← 版本B
│   │       └── revert-guide.md  ← 回滚指南
```

---

## 6. 总结

### 核心结论

1. **分离从未真正完成** — 所有"分离"尝试都是半途而废的。每次都在创建 handlers/ 目录和 utils/ 目录后，只分离了路由分发和少数工具函数，但 handler 端的业务逻辑从未迁移。

2. **版本C是最大的误解** — `最新版2/edit-web.py` 与当前运行版本 **完全相同**。它并不是"第三个分离版本"，只是一个副本 + 死代码的 handlers/ 目录。

3. **当前版本其实已经部分分离了但没人知道** — 当前运行的 edit-web.py 已经通过 `from handlers import router` 和 `from utils.momo import ...` 等方式使用分离模块。这可能是在演进过程中自然形成的，不是有计划的架构。

4. **空壳 handler 是最大的讽刺** — 5个 handler 文件只有注释和 docstring，2个有函数体的 handler 依赖不存在的模块。这些文件在创建后从未被使用。

5. **所有版本之间没有清晰的演进路径** — 版本A（6/12）、版本B（6/13）、版本C（6/22）之间的变更记录不清晰。版本A比版本B少了153行（配置简化），版本B比当前少了48行（sandglass等新功能），版本C又回到了当前版本的3925行。

### 推荐行动

| 优先级 | 行动 | 说明 |
|--------|------|------|
| 🔴 P0 | 整理文件结构 | 删掉重复文件，统一定位 |
| 🔴 P0 | 添加 VERSION 文件 | `git describe` 或版本号 |
| 🟡 P1 | 修复 handler import | 把空壳填上或有计划删除 |
| 🟡 P1 | 统一 static/js | 目录和引用路径 |
| 🟢 P2 | 添加启动脚本 | 方便切换版本 |
| 🟢 P2 | 建立 Git 仓库 | 真正的版本管理 |
