# RECOVERY.md — 故障恢复预案手册（dandan 用 · 不懂代码也能照做）

> 2026-08-11 建立。配套：`SYSTEM_HEALTH.md`（巡检信号含义）＋ `dashboard.html`（可视化看板，打开即看）。
> **一句话用法**：打开 `Agent OS/dashboard.html` → 看哪个灯红 → 在页面点「🛠 怎么恢复」或对号入座下表。
> 看板由 `scripts/gen_dashboard.sh` 每 5 分钟自动重新生成（cron 已接入），页面自身每 60 秒自动刷新。

---

## 0. 先回答 dandan 的三个核心担忧

### ① 明天 session 被重置了会怎样？记忆还在吗？
**记忆不丢。** 沙漏（明线：sandglass.txt + sandglass.db）和 LMS（暗线：:8190 活体记忆）都是**磁盘上的外部存储**（/vol2 与 /vol1），跟 openclaw 的会话文件完全无关。session 重置只清对话上下文，不清记忆。
- 丢的只是「当前对话的上下文窗口」（AI 会短暂失忆，靠每轮记忆注入找回来）
- 不丢的是：全部落沙记录、LMS 轮次/熵/目的演化、doubt 账本、备份快照
- 兜底：`session-reset-watchdog`（2 分钟 cron）会自动把被重置的会话归档成 `*.restored.jsonl` 供编辑器浏览
- **验证**：打开看板看「沙漏记忆条数」和「LMS 轮次」是否继续增长；或 `tail -3 "所有自动化/轻如烟/sandglass/sandglass.txt"` 有今天的落沙 = 记忆完好

### ② 服务器重启了会怎样？
crontab 里有 5 条 @reboot 启动条目（另有 1 条注释行），按依赖顺序自动拉起（重启后等 2~3 分钟）：

| 顺序 | 服务 | 启动方式 | 说明 |
|---|---|---|---|
| 1 | LMS :8190 | `lms_ctl.sh start`（sleep 30） | 启动最慢，嵌入模型初始化最长 40s |
| 2 | LMS 控制口 :8191 | `run_control.py`（sleep 45） | |
| 3 | 编辑器 :18888 | `backend/server.py`（立即） | |
| 4 | openclaw-proxy | `node openclaw-proxy.mjs`（sleep 10） | 记忆注入通道 |
| 5 | 沙漏 17333 → glue 19000 → 调度器/消费者 → 玄鉴 | `start_all.sh`（sleep 20） | 幂等，已起的跳过 |

**验证**：重启后打开看板，全绿 = 恢复。有红的 → 手动 `bash "/vol2/1000/AI专用/Agent OS/start_all.sh"` 补拉（幂等，安全）。

### ③ 我怎么知道系统正不正常？
**打开看板，10 秒扫一眼**：顶部横幅「绿 X 黄 Y 红 Z」+ 判定；红 = 有故障 → 点卡片里的「怎么恢复」或对号入座下表。
看板数据来自现有巡检（30 分钟一次）＋ 实时探针（每次生成时现场测）+ 状态文件，**不新增任何系统负担**。

---

## 1. 故障场景 → 现象 → 恢复（对号入座）

### 场景 1：session 被重置（见上 ①）
- **现象**：对话上下文没了；编辑器会话列表被清
- **自动恢复**：watchdog 归档；记忆本身不受影响
- **恢复**：无需处理；验证沙漏/LMS 数字继续涨即可

### 场景 2：服务器重启（见上 ②）
- **现象**：全部服务消失
- **自动恢复**：6 条 @reboot
- **恢复**：等 2~3 分钟后看板验证；缺谁补谁：`bash "/vol2/1000/AI专用/Agent OS/start_all.sh"`

### 场景 3：LMS :8190 挂了
- **现象**：看板 LMS-API 红灯；巡检「端口 8190 不可达」；回魂注入停
- **影响**：暗线记忆读写断，glue 降级。⚠️ **LMS 没有进程级 watchdog**（health-check.sh 只自愈编辑器），死了不会自动复活
- **自动恢复**：仅 @reboot
- **恢复**：
  ```bash
  cd "/vol2/1000/AI专用/living-memory-system-cloud" && bash scripts/lms_ctl.sh restart
  # 脚本自动 source .env；日志看 logs/lms_api.log；等 30~40s 探活
  ```

### 场景 4：glue :19000 挂了
- **现象**：看板胶水层红灯；/recall /store /soul 断 = AI 每轮失忆 + 新记忆写不进
- **自动恢复**：仅 @reboot
- **恢复**：先确认三后端（沙漏 17333 / LMS 8190 / 向量）活着，再：
  ```bash
  bash "/vol2/1000/AI专用/Agent OS/start_all.sh"
  ```

### 场景 5：沙漏 17333 挂了 / sandglass.txt 不更新
- **现象**：看板沙漏API 红灯；或「沙漏落沙」显示 6 小时无新增（明线断 = 失忆根源）
- **注意**：self_pulse 的 metrics 由 pulse-cron（10min）写，不经过 API——所以 metrics 可能还在涨、但对话落沙停了
- **自动恢复**：仅 @reboot
- **恢复**：`bash "/vol2/1000/AI专用/Agent OS/start_all.sh"`；若 API 活但 txt 停更 → 查对话写沙漏的链路（glue/编辑器侧）

### 场景 6：手机 Ollama :11435（embed）不可达 —— 感官层「瞎」
- **现象**：⚠️ 迷惑性信号——LMS /health 仍 200（看板 LMS 绿），但 **LMS 轮次不涨、新记忆写不进/检索不到**。巡检项里 LMS-API 可能全绿，要盯「LMS 轮次」这个数字
- **原因**：LMS_CLOUD_EMBED_URL 指向手机 Ollama bge-m3；不可达时嵌入失败 → store/recall 失效
- **自动恢复**：无（手机侧服务，LMS 本体不受影响，恢复后自动续写）
- **恢复**：
  ```bash
  # 确认手机 Ollama 在线：
  curl -s http://192.168.0.103:11435/v1/embeddings -d '{"model":"bge-m3","input":"ping"}'
  # 通 → LMS 无需重启自动恢复；不通 → 看手机端 Ollama 服务
  ```

### 场景 7：总线 event_bus.jsonl 停写
- **现象**：看板「总线最近事件」> 30 分钟没变；巡检总线项黄/红
- **影响**：事件骨架断（task_complete / heartbeat / 落沙事件不流转）
- **自动恢复**：仅 @reboot
- **恢复**：
  ```bash
  bash "/vol2/1000/AI专用/Agent OS/iso-sand/start_scheduler.sh"
  bash "/vol2/1000/AI专用/Agent OS/iso-sand/start_consumer.sh"
  # 或直接 bash "/vol2/1000/AI专用/Agent OS/start_all.sh"
  ```

### 场景 8：玄鉴（verify_daemon）挂了
- **现象**：看板玄鉴-进程红灯；daemon_audit.log 停更（>10 分钟）
- **影响**：审外监督死（不再巡检 operation_log、不再验证 git 推送）
- **自动恢复**：仅 @reboot
- **恢复**：
  ```bash
  cd "/vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘" && nohup python3 src/verify_daemon.py \
    >> "/vol2/1000/AI专用/Agent OS/logs/verify_daemon.log" 2>&1 &
  ```

### 场景 9：备份失败（BK-01 红）
- **现象**：看板备份红灯；lms_backup.log 尾部有 ERROR
- **⚠️ 先分清新旧**：BK-01 统计的是「近 40 行」——历史 ERROR 会残留到第二天。看板上「备份日志(近40行) ERROR x / 今日 ERROR」：**今日 0 次 + 快照新鲜 = 实际已恢复**，明天自动转绿
- **自动恢复**：cron */15 --quick + 每小时归档 + 每日 02:30 全量（自动重试）
- **恢复**：
  ```bash
  cd "/vol2/1000/AI专用/living-memory-system-cloud" && bash scripts/lms_backup.sh --quick
  # 持续失败 → df -h /vol2 看磁盘；查备份日志具体 ERROR 行
  ```

### 场景 10：4:00 自动重置
- **状态**：✅ **已确认关闭**——crontab 中没有 `0 4 * * *` 重置条目；现存只有 session-reset-watchdog（2min，只归档不重置）
- **验证**：`crontab -l | grep -E "4 \* \* \*|reset"` → 应只有 watchdog 归档条目

### 场景 11：GitHub 网络断（push_verify WARN/FAIL）
- **现象**：看板玄鉴-审计发现红灯；audit 里 `push_verify FAIL：本地领先远端 ahead=N`
- **影响**：✅ **运行时无影响**（记忆/总线全在本地），只是代码/文档推送不落地
- **自动恢复**：玄鉴每 5 分钟重试，网络恢复自动转绿
- **恢复**：网络恢复后进对应仓库补推：
  ```bash
  cd "/vol2/1000/AI专用/Agent OS" && git status   # 看 ahead 数
  git push
  ```

---

## 2. 看板使用说明

| 看板区域 | 看什么 | 红 = |
|---|---|---|
| 顶部横幅 | 绿/黄/红计数 + 判定 | 有故障，往下找红卡 |
| 巡检历史条 | 最近 5 次「绿黄红」趋势 | 持续变红 = 恶化 |
| 关键数字 | 沙漏条数 / LMS 轮次熵目的 / pulse / 总线 / 玄鉴 FAIL / 备份 ERROR / 回魂 / doubt | 见各卡片 |
| 组件卡片 | 20 项巡检，点击「怎么恢复」展开处置 | 红卡 = 对号入座 §1 |
| 契约层 | 41 项跨组件契约 | 违反清单 = 改 A 砸 B 的预警 |

**手工重新生成**（改完配置后）：
```bash
bash "/vol2/1000/AI专用/Agent OS/scripts/gen_dashboard.sh"
```
**机器可读快照**：`Agent OS/run/dashboard_state.json`（每次生成时写，供未来工具复用）。

---

## 3. 关键事实备忘（避免误判）

1. **进程死了不会自动复活（除编辑器）**：LMS/glue/沙漏/玄鉴/总线只有 @reboot 兜底；`health-check.sh`（5min）只自愈编辑器。发现红卡 → 手动拉（见 §1）。
2. **玄鉴审计日志有两个副本**：live 是 `AgentOS-IsoSand/同构沙盘/data/daemon_audit.log`；`Agent OS/docker/verify-data/xuanjian-data/` 那份已死（08-07 停更），别接错。
3. **LMS :8190 无 CORS 头**：浏览器直连会被拦（看板不走浏览器直连，是生成时服务端探测，无此问题）。
4. **BK-01 的 ERROR 是「近 40 行」口径**：历史 ERROR 会残留，看「今日」为准。
5. **LM-02 曾有瞬时 404**（20:00 巡检报，20:12 实测 200）：LMS 偶发未就绪即被探活，看板每次生成时**现场实测**，以实测为准。
6. **4:00 重置已关**（见场景 10）；**GitHub 断不影响运行**（见场景 11）。

---

*维护规则：新增组件/改端口 → 同步改本文件 + SYSTEM_HEALTH.md §2 表 + gen_dashboard.sh 的 REC/SCEN 映射。*
