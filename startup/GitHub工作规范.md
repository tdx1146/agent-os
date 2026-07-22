# Agent OS · GitHub 工作规范

> 本文件对 AI 和人类开发者均有效。
> 修改代码前必读。

---

## 一、GitHub 仓库清单

| 仓库 | 内容 | 谁的代码 |
|------|------|---------|
| `tdx1146/edit-web.py` | **轻如烟编辑器** v1~v5.1 完整版本历史 | 前端+后端 |
| `tdx1146/monument-network` | **丰碑网络** — AI 群体记忆库 | 所有 AI |
| `tdx1146/agent-os-iso-sand` | **调度器 + 玄鉴 + 事件消费者**（主要修改目标） | 后端运维 |
| `tdx1146/agent-os-kernel` | 版本管理 + 快照系统（post-commit 自动生成） | 自动 |
| `tdx1146/agent-os-sandglass` | NexSandglass 记忆引擎 | 独立组件 |
| `tdx1146/agent-os` | 知识图谱 + 启动文档 | 静态内容 |

---

## 二、核心规则

### 规则 1：改正确的系统

系统有**两个前端**，不要搞混：

| 名称 | 端口 | 本质 | 能不能改 |
|------|------|------|---------|
| **轻如烟编辑器** | 18888 | Python `edit-web.py` + handlers + static JS | ✅ 主系统，可以改 |
| **OpenClaw control-ui** | 16878 | Vite SPA（node_modules 编译产物） | ❌ **终极备份，不能改** |

> ⚠️ 聊天渠道标记为「轻如烟编辑器 (openclaw-control-ui)」时，你其实在通过 **OpenClaw 备份通道** 对话。不要在这个通道里修代码。
>
> 要修代码，必须确认目标系统是 **轻如烟编辑器（18888）** 或 **Agent OS 的 iso-sand**。

### 规则 2：修改前确认目录

```
轻如烟编辑器代码:
  /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/

Agent OS 代码:
  /vol1/@team/qh团队/QH/AI专用/Agent OS/iso-sand/src/

版本归档:
  /vol1/@team/qh团队/QH/AI专用/编辑器所有版本/
```

### 规则 3：修改后走 git 流程

```bash
# 1. 进入正确的目录
cd /vol1/@team/qh团队/QH/AI专用/Agent OS/iso-sand

# 2. 提交
git add -A
git commit -m "描述改动内容"

# 3. 推送到 GitHub（post-commit hook 会自动执行）
#    如果 hook 没触发，手动推：
git push origin main
```

> ⚠️ 不要直接修改 `node_modules/` 下的文件。那是编译产物，git 不会记录。

### 规则 4：归档到版本库

如果修改了 **轻如烟编辑器**，除了 git commit，还要：

```bash
# 归档到版本历史
cp -r /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/ \
      /vol1/@team/qh团队/QH/AI专用/编辑器所有版本/v{新版本号}_{日期}_描述/

# 更新版本索引
echo "| vX.Y | vX.Y_目录/ | 日期 | 说明 | 改动内容 |" >> VERSION_INDEX.md

# 更新 CHANGELOG
# 追加到 /vol1/@team/qh团队/QH/AI专用/编辑器所有版本/CHANGELOG.md
```

### 规则 5：不要改 OpenClaw control-ui

```
/vol1/@apphome/trim.openclaw/data/openclaw/node_modules/openclaw/dist/control-ui/
```

这是 OpenClaw 自带的 WebChat，编译后的 Vite SPA 产物。**不是轻如烟编辑器。** 如果因为某种原因需要修改，必须先备份原始版本，修改后立即归档到 `编辑器所有版本/` 并标记为「control-ui 补丁」。

---

## 三、各仓库的修改流程

### iso-sand（最常改）

```bash
cd /vol1/@team/qh团队/QH/AI专用/Agent OS/iso-sand
# 改代码 → git add → git commit → git push（hook 自动推）
# 如果改了核心功能，重启对应进程：
kill 玄鉴PID && cd /path && nohup python3 src/verify_daemon.py &
```

### 轻如烟编辑器

```bash
cd /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟
# 改代码 → git add → git commit → git push
# 重启编辑器：
kill 轻如烟PID && cd scripts && python3 edit-web.py &
```

### 丰碑（monument）

丰碑是**全球公开**的仓库。推送前确保内容不包含私密信息（API key、密码、路径泄露等）。

```bash
cd /vol1/@team/qh团队/QH/AI专用/Agent OS/monument
git push origin main
```

---

## 四、常见的错误

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 改了 OpenClaw control-ui 的 `node_modules/` | 升级后改动丢失，轻如烟编辑器没改到 | 改轻如烟编辑器（18888）的源文件 |
| 改了代码没 git commit | 下一次其他 AI 看不到你的修改 | `git add && git commit && git push` |
| 改了代码没归档到 `编辑器所有版本/` | 版本历史断裂 | git commit 后执行归档步骤 |
| 在两个系统都改了同一功能 | 逻辑冲突，不知道哪个生效 | 先确认哪个系统在运行，修那个 |

---

## 五、系统结构速查

```
                                   用户
                                     │
                          ┌──────────┴──────────┐
                          │                     │
                   轻如烟编辑器(18888)     OpenClaw control-ui(16878)
                   (主系统)                (终极备份，不动)
                          │                     │
                          └──────────┬──────────┘
                                     │
                              Agent OS
                     ┌────────┬──────┴──────┬────────┐
                     │        │             │        │
                  iso-sand  kernel      sandglass   monument
                (玄鉴/调度器) (快照/版本)    (记忆引擎)  (丰碑)
```

---

*首次编写: 2026-07-22 | 最后更新: 2026-07-22*
*对应 GitHub: tdx1146/edit-web.py, tdx1146/agent-os-*, tdx1146/monument-network*
