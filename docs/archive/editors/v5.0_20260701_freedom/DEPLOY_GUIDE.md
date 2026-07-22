# 轻如烟 v5.0「自由王国」— 部署迁移指南

> 将编辑器和所有自动化工件从当前机器迁移到另一台机器（"妹妹"）

---

## 1. 文件清单

从 `/vol1/@team/qh团队/QH/AI专用/编辑器所有版本/v5.0_20260701_freedom/` 迁移以下内容：

```
v5.0_20260701_freedom/
├── edit-web.py                        # 编辑器主入口 (705行)
├── inject-helper.mjs                  # OpenClaw 注入通道
├── editor-config.json                 # 编辑器配置
├── start-clean.sh                     # 无守护进程启动脚本
├── static/
│   ├── index.html                     # 前端入口 (11个<script defer>)
│   ├── css/styles.css                 # 样式
│   ├── favicon.ico
│   └── js/                            # 11 个 JS 模块
│       ├── core.js                    # 核心：store/api/CL/render链路
│       ├── render.js                  # 渲染引擎：renderPage
│       ├── components.js              # CL 组件注册
│       ├── dashboard.js               # 启动引导：CL.renderAll()
│       ├── app.js                     # 模块入口
│       ├── awake.js                   # 对话面板
│       ├── editor.js                  # 编辑面板
│       ├── momo.js                    # 工具箱
│       ├── subagent.js                # 子代理管理
│       ├── file-browser.js            # 文件浏览
│       ├── cache-monitor.js           # 缓存监控
│       └── window-bridge.js           # [可选，已弃用]
├── handlers/
│   ├── router.py                      # API 路由 (~170行)
│   ├── system_handler.py              # 系统级 handler
│   ├── helper_handler.py              # 辅助功能 handler
│   ├── inject_handler.py              # 注入通道 handler
│   └── __init__.py
├── utils/
│   ├── __init__.py
│   ├── config.py                      # 路径/配置
│   ├── crypto.py
│   ├── encryption.py
│   ├── file_logger.py
│   ├── inject.py
│   ├── inject_lock.py                 # 锁管理 (20s TTL)
│   ├── momo.py
│   ├── pulse.py
│   ├── reminder.py                    # 提醒系统
│   ├── secretary.py
│   ├── session.py
│   ├── status_reports.py
│   ├── subagent.py
│   ├── tb_handler.py
│   ├── text_utils.py
│   └── version.py                     # 版本号唯一数据源
├── knowledge-graph/                   # 调用链 D3.js 图
│   └── call-graph.html
├── tests/
│   ├── conftest.py
│   ├── test_basic.py                  # 3 冒烟测试
│   ├── test_api.py                    # 7 API 集成测试
│   ├── test_modules.py                # 13 模块单元测试
│   └── frontend/test_api_contract.html
└── static/API_CONTRACT.md             # 41KB API 文档（60端点）
```

---

## 2. 目标机器前置条件

| 项目 | 要求 |
|:----|:----|
| **Python** | ≥ 3.10（推荐 3.11） |
| **端口可用** | 18888（编辑器主端口） |
| **内存** | ≥ 256MB（编辑器本身~30MB RSS） |
| **磁盘** | ≥ 100MB（代码 + 日志） |
| **网络** | 服务端 127.0.0.1 绑定，或按需暴露 |

---

## 3. 安装步骤

### 3.1 复制文件

```bash
# scp 或 rsync 整个目录到目标机器
rsync -avz --progress \
  /vol1/@team/qh团队/QH/AI专用/编辑器所有版本/v5.0_20260701_freedom/ \
  user@target:/path/to/light-smoke/
```

或仅复制核心文件：

```bash
scp -r \
  edit-web.py inject-helper.mjs editor-config.json start-clean.sh \
  static/ handlers/ utils/ tests/ knowledge-graph/ \
  user@target:/path/to/light-smoke/
```

### 3.2 创建运行目录

```bash
# 编辑器的记忆目录（必须）
mkdir -p /path/to/light-smoke/memory
mkdir -p /path/to/light-smoke/.locks
mkdir -p /path/to/light-smoke/scripts/backup
mkdir -p /tmp/subagent-work          # 子代理工作目录
```

### 3.3 配置要点

**3.3.1 配置文件 `editor-config.json`**

```json
{
  "PORT": 18888,
  "GATEWAY_PORT": 18822,
  "GATEWAY_TOKEN": "<your-token>",
  "INJECT_PORT": 18889,
  "BROWSE_ROOT": "/path/to/browse/root",
  "LIGHT_SMOKE_DIR": "/path/to/light-smoke",
  "CONTEXT_WINDOW": 1000000
}
```

> `GATEWAY_PORT` 和 `GATEWAY_TOKEN` 需与目标机器上运行的 OpenClaw Gateway 匹配。
> 若目标机器没有 OpenClaw，编辑器仍可运行但子代理功能和注入通道不可用。

**3.3.2 环境变量（可选，覆盖配置文件）**

```bash
export PORT=18888
export LIGHT_SMOKE_DIR=/path/to/light-smoke
export GATEWAY_PORT=18822
export GATEWAY_TOKEN=xxx
```

### 3.4 启动

**方式1：直接运行（推荐调试）**

```bash
cd /path/to/light-smoke/scripts
python3 edit-web.py
```

输出示例：
```
🔥 轻如烟 v5.0「自由王国 (Freedom First)」
   Port:   18888
   PID:    12345
   Lock:   /path/to/light-smoke/.locks/inject.lock
   Dir:    /path/to/light-smoke
```

**方式2：后台运行（生产推荐）**

```bash
cd /path/to/light-smoke/scripts
nohup python3 edit-web.py > /tmp/edit-web.log 2>&1 &
```

**方式3：start-clean.sh（无守护进程冲突）**

```bash
cd /path/to/light-smoke/scripts
chmod +x start-clean.sh
./start-clean.sh
```

### 3.5 验证部署

```bash
# 1. 版本 API
curl http://127.0.0.1:18888/api/version
# 应返回: {"ok":true,"version":"v5.0","full":"轻如烟 v5.0「自由王国…"}

# 2. 状态 API
curl http://127.0.0.1:18888/api/status

# 3. 页面
curl -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:18888/
# 应返回 200

# 4. 运行测试（需在 scripts/ 目录下）
cd /path/to/light-smoke/scripts
python3 -m pytest tests/ -v
# 应全部通过（21 passed）
```

---

## 4. 与 OpenClaw Gateway 对接（可选）

如果目标机器运行 OpenClaw，需要配置：

### 4.1 openclaw.json 添加

```json
{
  "plugins": {
    "entries": {
      "inject-web": {
        "text": "{\"url\":\"http://127.0.0.1:18889\",\"token\":\"<token>\"}",
        "token": "<same-token>"
      }
    }
  }
}
```

### 4.2 环境变量

```bash
openclaw config set OPENAI_API_KEY sk-xxx  # 用于子代理
```

---

## 5. 故障排查

### 5.1 页面空白 / 加载中

| 可能原因 | 检查方法 | 修复 |
|:--------|:--------|:----|
| JS 语法错误 | 浏览器 F12 → Console | 确认 JS 文件为 v5.0 备份版，无 import/export |
| script 顺序错误 | 检查 `<script defer>` 顺序 | dashboard.js 必须在 components.js + render.js 之后 |
| API 不可达 | `curl /api/version` | 确认 PORT 正确，无端口冲突 |

### 5.2 API 返回 500

| 错误信息 | 原因 | 修复 |
|:--------|:----|:----|
| `name 'EXEC_SUBAGENT_HISTORY' is not defined` | B1 拆分时常量丢失 | 在 edit-web.py 中加回 `EXEC_SUBAGENT_HISTORY = os.path.join(...)`（参考行145） |
| `name 'XXX' is not defined` | 类似常量/变量在拆分时丢失 | 从 v4.2 备份对应文件中查找定义 |

### 5.3 子代理功能不可用

- 确保 `GATEWAY_PORT` / `GATEWAY_TOKEN` 配置正确
- 确保 `inject-helper.mjs` 存在于同目录
- 检查 `/tmp/subagent-work` 目录存在

### 5.4 端口被占用

```bash
# 查看占用进程
lsof -i :18888
# 或修改 PORT：export PORT=18887 后再启动
```

---

## 6. 备份验证

部署后创建一次完整备份确认：

```bash
# 从目标机器运行
tar czf v5.0_deployed_$(date +%Y%m%d).tar.gz \
  edit-web.py inject-helper.mjs editor-config.json start-clean.sh \
  static/ handlers/ utils/ tests/ knowledge-graph/
ls -lh v5.0_deployed_*.tar.gz
```

---

## 7. 架构概要（给下一个开发者）

### 前后端分离
- `edit-web.py`：纯后端，705行，5个核心函数 + API 委托
- `static/index.html` + `static/js/*`：纯前端，通过 `/api/` 调后端
- 后端不生成 HTML，前端不直接访问文件系统

### 模块独立
- `utils/` 17个模块各管一摊：锁、注入、提醒、子代理、状态报告…
- API handler 在 `handlers/` 中按功能分文件
- 跨模块依赖很小（主要依赖 `utils/config.py` 的路径和 `core.js` 的 window 桥接）

### 前端加载模式
- 11 个 `<script defer>` 顺序加载（非 `type="module"`）
- 所有函数通过 `window.X = X` 挂在全局
- inline `onclick` 直接调用
- `dashboard.js` → `CL.renderAll()` 在全部组件注册后执行
