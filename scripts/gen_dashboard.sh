#!/bin/bash
# =============================================================
# gen_dashboard.sh — Agent OS 故障可视化看板生成器（只读）
# -------------------------------------------------------------
# 目标：dandan 打开一个 HTML 页面，10 秒内知道系统全貌。
# 数据来源（全部只读复用，不新造轮子）：
#   - run/system_health.state   （20 项巡检结果，cron 30min 更新）
#   - run/contract_check.state  （41 项契约结果，cron 30min 更新）
#   - 实时探针：LMS :8190 / glue :19000 / 沙漏 :17333 / 编辑器 :18888
#   - 状态文件：pulse-status.json / metrics.jsonl / salience_state.json /
#               sleep_pressure.json / dream_state.json / doubt.db /
#               event_bus.jsonl / daemon_audit.log / lms_backup.log
#
# 用法：
#   bash gen_dashboard.sh                    # 生成 dashboard.html（默认 Agent OS/dashboard.html）
#   bash gen_dashboard.sh --install-cron     # 幂等接入 crontab：每 5 分钟重新生成
#   DASHBOARD_OUT=/path/x.html bash gen_dashboard.sh   # 自定义输出路径
#
# 设计纪律：
#   - 零硬编码：所有路径来自 Agent OS/env.local，缺失时相对推导
#     （与 system_health_check.sh 完全同源）
#   - 只读：不写任何系统数据文件、不调用任何写接口
#   - 自包含：dashboard.html 无外部依赖（无 CDN/无字体），浏览器直接打开
#   - 同时输出 run/dashboard_state.json（机器可读快照，供未来工具复用）
# =============================================================
set -u

AGENT_OS_HOME="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi

# ---------- 路径/端口推导（与 system_health_check.sh 同源） ----------
SANDGLASS_API_PORT="${SANDGLASS_API_PORT:-17333}"
LMS_API_PORT="${LMS_API_PORT:-8190}"
LMS_CONTROL_PORT="${LMS_CONTROL_PORT:-8191}"
GLUE_PORT="${GLUE_PORT:-19000}"
EDITOR_PORT="${EDITOR_PORT:-18888}"
ISO_SAND_HOME="${ISO_SAND_HOME:-$AGENT_OS_HOME/iso-sand}"
RUN_DIR="${RUN_DIR:-$AGENT_OS_HOME/run}"
LOG_DIR="${LOG_DIR:-$AGENT_OS_HOME/logs}"
VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/../AgentOS-IsoSand/同构沙盘}"
NEXSANDBASE_HOME="${NEXSANDBASE_HOME:-$AGENT_OS_HOME/../所有自动化/轻如烟/sandglass}"
LIGHT_HOME="${LIGHT_HOME:-$AGENT_OS_HOME/../所有自动化/轻如烟}"
LMS_HOME="${LMS_HOME:-$AGENT_OS_HOME/../living-memory-system-cloud}"
GLUE_HOME="${GLUE_HOME:-$AGENT_OS_HOME/../memory-integration-layer}"
if [ -n "${FACTS_DICT_PATH:-}" ]; then
    WORKSPACE="$(dirname "$(dirname "$FACTS_DICT_PATH")")"
else
    WORKSPACE="/vol1/@apphome/trim.openclaw/data/workspace"
fi
BACKUP_ROOT="$(dirname "$LMS_HOME")/backups/lms"
DASHBOARD_OUT="${DASHBOARD_OUT:-$AGENT_OS_HOME/dashboard.html}"
STATE_OUT="$RUN_DIR/dashboard_state.json"
PULSE_STATUS="${PULSE_STATUS:-/tmp/pulse-status.json}"
GLUE_HOOK_LOG="${GLUE_HOOK_LOG:-/tmp/glue-hook-debug.log}"

if [ "${1:-}" = "--install-cron" ]; then
    MARK="# === 故障可视化看板 (gen_dashboard) 2026-08-11 ==="
    if crontab -l 2>/dev/null | grep -qF "$MARK"; then
        echo "cron 已存在，跳过（幂等）"
    else
        ( crontab -l 2>/dev/null; echo "$MARK"; \
          echo "*/5 * * * * bash \"$AGENT_OS_HOME/scripts/gen_dashboard.sh\" >> \"$LOG_DIR/gen_dashboard.log\" 2>&1" ) | crontab -
        echo "已接入 crontab：每 5 分钟重新生成看板"
    fi
    exit 0
fi

# ---------- 导出给 python3 渲染段 ----------
export AGENT_OS_HOME ISO_SAND_HOME RUN_DIR LOG_DIR VERIFY_HOME NEXSANDBASE_HOME \
       LIGHT_HOME LMS_HOME GLUE_HOME WORKSPACE BACKUP_ROOT DASHBOARD_OUT STATE_OUT \
       PULSE_STATUS GLUE_HOOK_LOG SANDGLASS_API_PORT LMS_API_PORT LMS_CONTROL_PORT \
       GLUE_PORT EDITOR_PORT

python3 - <<'PY'
# -*- coding: utf-8 -*-
"""看板渲染：读状态文件 + 实时探针 → dashboard.html（自包含）"""
import json, os, re, sys, time, urllib.request, sqlite3, html as H
from datetime import datetime

def env(k, d=""): return os.environ.get(k, d)
AO  = env("AGENT_OS_HOME"); ISO = env("ISO_SAND_HOME"); RUN = env("RUN_DIR"); LOG = env("LOG_DIR")
VH  = env("VERIFY_HOME");  NSB = env("NEXSANDBASE_HOME"); LIGHT = env("LIGHT_HOME")
LMS = env("LMS_HOME");     GLUE = env("GLUE_HOME"); WS = env("WORKSPACE"); BK = env("BACKUP_ROOT")
P8190, P8191, P17333, P19000, P18888 = env("LMS_API_PORT"), env("LMS_CONTROL_PORT"), env("SANDGLASS_API_PORT"), env("GLUE_PORT"), env("EDITOR_PORT")
PULSE = env("PULSE_STATUS"); HOOK = env("GLUE_HOOK_LOG")
OUT = env("DASHBOARD_OUT");  STATE_OUT = env("STATE_OUT")
NOW = time.time(); NOW_STR = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""

def jget(url, timeout=5):
    t = get(url, timeout)
    try: return json.loads(t)
    except Exception: return None

def fage(p):
    try: return int(NOW - os.path.getmtime(p))
    except Exception: return 999999

def alabel(s):
    if s >= 86400: return f"{s//86400}天前"
    if s >= 3600:  return f"{s//3600}小时前"
    if s >= 60:    return f"{s//60}分钟前"
    return f"{s}秒前"

def tail_lines(p, n=3, maxlen=300):
    try:
        with open(p, "rb") as f:
            f.seek(0, 2); sz = f.tell()
            f.seek(max(0, sz - 65536)); data = f.read().decode("utf-8", "replace")
        ls = [l for l in data.splitlines() if l.strip()][-n:]
        return [l[:maxlen] for l in ls]
    except Exception:
        return []

def first_json(p):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return None

# ============ 1. 巡检结果（system_health.state） ============
health = []
try:
    for line in open(os.path.join(RUN, "system_health.state"), encoding="utf-8"):
        line = line.strip()
        if not line or "|" not in line: continue
        parts = line.split("|", 2)
        if len(parts) == 3: health.append({"name": parts[0], "st": parts[1], "ev": parts[2]})
except Exception:
    pass
h_ok = sum(1 for x in health if x["st"] == "OK"); h_warn = sum(1 for x in health if x["st"] == "WARN")
h_fault = sum(1 for x in health if x["st"] == "FAULT")

# ============ 2. 契约结果（contract_check.state + 最近一次明细） ============
contracts = {}
try:
    for line in open(os.path.join(RUN, "contract_check.state"), encoding="utf-8"):
        parts = line.strip().split("|")
        if len(parts) == 2: contracts[parts[0]] = parts[1]
except Exception:
    pass
c_ok = sum(1 for v in contracts.values() if v == "OK"); c_warn = sum(1 for v in contracts.values() if v == "WARN")
c_fault = sum(1 for v in contracts.values() if v == "FAULT")
failing = [k for k, v in contracts.items() if v == "FAULT"]
c_detail = {}
clog = os.path.join(LOG, "contract_check.log")
try:
    lines = open(clog, encoding="utf-8").read().splitlines()
    sep = [i for i, l in enumerate(lines) if l.startswith("##########")]
    start = sep[-1] if sep else 0
    for l in lines[start:]:
        m = re.match(r"^(?:✅|⚠️|❌) \[([A-Z0-9-]+)\]", l)
        if m: c_detail[m.group(1)] = l
except Exception:
    pass

# ============ 3. 实时探针 ============
lms_health = jget(f"http://127.0.0.1:{P8190}/health")
lms_st = jget(f"http://127.0.0.1:{P8190}/status/main")
lms_st = (lms_st or {}).get("status") or lms_st or {}
glue = jget(f"http://127.0.0.1:{P19000}/health")
sg = jget(f"http://127.0.0.1:{P17333}/api/health")
ed = jget(f"http://127.0.0.1:{P18888}/api/quickcheck")

def num(d, k, fmt="%.3f"):
    v = d.get(k) if isinstance(d, dict) else None
    return (fmt % v) if isinstance(v, (int, float)) else "—"

# ============ 4. 状态文件 ============
pulse = first_json(PULSE)
metrics_tail = tail_lines(os.path.join(NSB, "metrics.jsonl"), 1)
m_last = None
if metrics_tail:
    try: m_last = json.loads(metrics_tail[0])
    except Exception: pass
sal = first_json(os.path.join(NSB, "salience_state.json"))
slp = first_json(os.path.join(NSB, "sleep_pressure.json"))
dream = first_json(os.path.join(NSB, "dream_state.json"))
doubt_count = "—"
try:
    c = sqlite3.connect(os.path.join(NSB, "doubt.db")); doubt_count = c.execute("SELECT COUNT(*) FROM doubt_episode").fetchone()[0]; c.close()
except Exception:
    pass
sg_txt_age = fage(os.path.join(NSB, "sandglass.txt"))
bus_age = fage(os.path.join(ISO, "data", "event_bus.jsonl"))
bus_last = "—"
try:
    with open(os.path.join(ISO, "data", "event_bus.jsonl"), "rb") as f:
        f.seek(0, 2); sz = f.tell(); f.seek(max(0, sz - 4096))
        for l in reversed(f.read().decode("utf-8", "replace").splitlines()):
            if l.strip():
                try: bus_last = json.loads(l).get("event_type", "—"); break
                except Exception: continue
except Exception:
    pass
dead = "—"
try: dead = sum(1 for _ in open(os.path.join(ISO, "data", ".dead_letter_queue.jsonl"), encoding="utf-8"))
except Exception: dead = 0 if os.path.exists(os.path.join(ISO, "data", ".dead_letter_queue.jsonl")) else "—"
audit_path = os.path.join(VH, "data", "daemon_audit.log")
audit = {"OK": 0, "WARN": 0, "FAIL": 0, "DEGRADED": 0}; audit_ts = "—"
try:
    with open(audit_path, encoding="utf-8") as f:
        al = f.readlines()[-200:]
    for l in al:
        for k in audit:
            if f'"result": "{k}"' in l: audit[k] += 1
    for l in reversed(al):
        m = re.search(r'"t": "([^"]+)"', l)
        if m: audit_ts = m.group(1)[:19]; break
except Exception:
    pass
bk_err = "—"; bk_tail = tail_lines(os.path.join(LMS, "logs", "lms_backup.log"), 2)
try:
    with open(os.path.join(LMS, "logs", "lms_backup.log"), encoding="utf-8") as f:
        bk_err = sum(1 for l in f.readlines()[-40:] if "ERROR" in l or "失败" in l)
except Exception:
    pass
hook_age = fage(HOOK)
hook_line = tail_lines(HOOK, 1)
hook_line = hook_line[0] if hook_line else "—"

# ============ 5. 巡检历史（最近 5 次汇总） ============
hist = []
try:
    for l in open(os.path.join(LOG, "system_health.log"), encoding="utf-8"):
        m = re.match(r"^########## (\S+ \S+) 系统健康巡检", l)
        if m: hist.append([m.group(1)])
        m2 = re.match(r"^结果: 绿=(\d+) 黄=(\d+) 红=(\d+)", l)
        if m2 and hist: hist[-1].append((int(m2.group(1)), int(m2.group(2)), int(m2.group(3))))
except Exception:
    pass
hist = [x for x in hist if len(x) == 2][-5:]

# ============ 6. 组件 → 恢复提示映射 ============
REC = [
    ("沙漏API", "仅 @reboot 拉起（start_all.sh）", f"bash {AO}/start_all.sh        # 幂等重启（含沙漏 17333）"),
    ("沙漏落沙", "仅 @reboot 拉起", f"先看沙漏API是否活着 → bash {AO}/start_all.sh"),
    ("沙漏索引", "仅 @reboot 拉起", f"bash {AO}/start_all.sh"),
    ("沙漏自治", "pulse-cron.sh 每 10min（cron 在则自动）", f"crontab -l | grep pulse-cron；缺失则补：*/10 * * * * {LIGHT}/scripts/pulse-cron.sh"),
    ("显著性/体力", "pulse-cron.sh 每 10min（同上）", f"同沙漏自治：跑一次 {LIGHT}/scripts/pulse-cron.sh 观察 salience/sleep_pressure 是否恢复更新"),
    ("怀疑账本", "无独立 watchdog（随沙漏管线）", f"看 {AO}/doubt-system/ 日志与 night_patrol；doubt.db 由怀疑闭环写入"),
    ("LMS-API", "仅 @reboot（lms_ctl.sh start, sleep 30）", f"cd {LMS} && bash scripts/lms_ctl.sh restart      # 先确保 .env 已 source"),
    ("LMS-深度指标", "cron */5 lms_ops_monitor.py（在则自动）", f"补 cron：*/5 * * * * cd {LMS} && python3 scripts/lms_ops_monitor.py >> logs/lms_ops_monitor.log 2>&1"),
    ("LMS-告警账本", "无（事件式记录）", "看 lms_alerts.jsonl 最近告警类型：孤儿进程→cleanup_orphan_mcp.sh；备份失败→见「备份」行"),
    ("LMS-控制口", "@reboot（run_control.py, sleep 45）", f"cd {LMS} && setsid .venv/bin/python scripts/run_control.py --host 127.0.0.1 --port {P8191} >> logs/lms_control.log 2>&1 < /dev/null &"),
    ("胶水层", "仅 @reboot（start_all.sh）", f"先救三后端（LMS/沙漏/向量），再 bash {AO}/start_all.sh"),
    ("总线", "仅 @reboot（start_all.sh）", f"bash {AO}/iso-sand/start_scheduler.sh && bash {AO}/iso-sand/start_consumer.sh"),
    ("玄鉴-进程", "仅 @reboot（start_all.sh）", f"cd {VH} && nohup python3 src/verify_daemon.py >> {LOG}/verify_daemon.log 2>&1 &"),
    ("玄鉴-审计发现", "push_verify 会重试（网络恢复后自愈）", "FAIL 多为 git 推送未落地：进对应仓库 `git status` 看 ahead，`git push` 补推"),
    ("夜巡", "cron 23:30（在则自动）", f"bash {AO}/doubt-system/night_patrol_run.sh      # 看 /tmp/night-patrol-cron.log"),
    ("self_pulse", "pulse-cron.sh 每 10min（cron 在则自动）", f"bash {LIGHT}/scripts/pulse-cron.sh && cat {PULSE}"),
    ("回魂插件", "仅 @reboot（openclaw-proxy）", f"重启 openclaw-proxy（/vol2/1000/AI专用/lobe-chat/openclaw-proxy.mjs），看 {HOOK} 是否恢复 INJECTED"),
    ("备份", "cron */15 --quick（在则自动）", f"bash {LMS}/scripts/lms_backup.sh --quick      # 看 {LMS}/logs/lms_backup.log 尾部 ERROR"),
    ("cron完整性", "无（人工）", "对照 SYSTEM_HEALTH.md §5 补 crontab 关键条目（三把锁/备份/深度健康/巡检）"),
    ("磁盘", "无（人工）", f"df -h {os.path.dirname(LMS)}    # 清旧备份：backups/lms 下 hourly 保留 9 份、daily 按策略"),
]
def rec_for(name):
    for k, auto, cmd in REC:
        if k in name or name in k: return (auto, cmd)
    return ("—", "见 SYSTEM_HEALTH.md §3 故障对照表")

# ============ 7. 恢复场景（10+1 个，dandan 不懂代码也能照做） ============
SCEN = [
    ("1️⃣ 明天 session 被重置（openclaw 会话没了）",
     "现象：对话历史/上下文没了，编辑器会话列表被清空",
     "影响：⚠️ 会话上下文丢失，但**记忆不丢**。沙漏（明线 sandglass.txt / 沙漏 db）和 LMS（暗线，:8190 记忆系统）都是**外部存储**，在 /vol2 和 /vol1 磁盘上，与 openclaw session 无关。session-reset-watchdog（2min cron）还会把重置前的会话归档成 *.restored.jsonl 供编辑器浏览。",
     "自动恢复：session-reset-watchdog 自动归档；记忆本身不受影响",
     "验证：打开本看板——沙漏条数 / LMS 轮次（turn_count）应继续增长；`tail -3 轻如烟/sandglass/sandglass.txt` 有今天的落沙即记忆完好。"),
    ("2️⃣ 服务器重启",
     "现象：全部服务消失，进程表空",
     "影响：@reboot 按依赖顺序自动拉起：LMS(lms_ctl.sh, sleep 30) → 控制口 8191(sleep 45) → 编辑器(立即) → openclaw-proxy(sleep 10) → start_all.sh(sleep 20：沙漏→LMS→glue→scheduler/consumer→verify_daemon)。LMS 启动最慢（嵌入模型初始化，最长 40s 探活）。",
     "自动恢复：全部 @reboot 条目（5 条启动 + 1 注释行，重启机器自动全拉起）",
     "验证：重启后等 2~3 分钟，`bash 状态脚本：Agent OS/status_all.sh` 或打开本看板（全绿=恢复）；若某服务没起来 → 手动 `bash Agent OS/start_all.sh`（幂等，已起的跳过）。"),
    ("3️⃣ LMS :8190 挂了",
     "现象：看板 LMS-API 红灯；巡检报「端口 8190 不可达」；AI 每轮记忆注入（回魂）失效",
     "影响：暗线记忆读写断，glue /recall 会降级。⚠️ 注意：LMS **没有进程级 watchdog**（health-check.sh 只自愈编辑器），进程死后不会自动复活，要靠巡检发现 + 手动拉。",
     "自动恢复：仅 @reboot（重启机器才触发）",
     "恢复：`cd /vol2/1000/AI专用/living-memory-system-cloud && bash scripts/lms_ctl.sh restart`（脚本自动 source .env；日志 logs/lms_api.log）"),
    ("4️⃣ glue :19000 挂了",
     "现象：看板胶水层红灯；/recall /store /soul 全断",
     "影响：读侧（recall）断 = AI 每轮失忆；写侧（store）断 = 新记忆写不进沙漏/LMS",
     "自动恢复：仅 @reboot",
     "恢复：先确认三后端（沙漏 17333 / LMS 8190 / 向量）活着，再 `bash /vol2/1000/AI专用/Agent OS/start_all.sh`（幂等）"),
    ("5️⃣ 沙漏 17333 挂了 / sandglass.txt 不更新",
     "现象：看板沙漏API 红灯；「沙漏落沙」显示 6 小时无新增 = 明线断（失忆根源）",
     "影响：明线记忆管线断；self_pulse 写 metrics 的是 pulse-cron（10min），它不拉 API，所以 metrics 可能还在涨、但对话落沙停了",
     "自动恢复：仅 @reboot",
     "恢复：`bash /vol2/1000/AI专用/Agent OS/start_all.sh`；若 API 活着但 txt 停更 → 查对话链路（glue/编辑器侧写沙漏的调用是否在跑）"),
    ("6️⃣ 手机 Ollama :11435（embed）不可达",
     "现象：LMS 感官层「瞎」——嵌入请求失败；store/recall 报错或空结果；LMS 轮次可能不涨",
     "影响：LMS_CLOUD_EMBED_URL 指向手机 Ollama bge-m3。不可达时新记忆**写不进/检索不到**（LMS 本体不挂，/health 仍 200——看板会显示 LMS 绿但轮次停涨，这是「感官层瞎」的信号）",
     "自动恢复：无（手机侧服务）",
     "恢复：确认手机 Ollama 在线：`curl -s http://192.168.0.103:11435/v1/embeddings -d '{\"model\":\"bge-m3\",\"input\":\"ping\"}'`；恢复后 LMS 自动续写（无需重启）"),
    ("7️⃣ 总线 event_bus.jsonl 停写",
     "现象：看板「总线最近事件」>30 分钟无新事件；巡检总线项黄/红",
     "影响：调度器/消费者死 → 事件骨架断（task_complete、heartbeat、落沙事件都不再流转）",
     "自动恢复：仅 @reboot",
     "恢复：`bash /vol2/1000/AI专用/Agent OS/iso-sand/start_scheduler.sh && bash /vol2/1000/AI专用/Agent OS/iso-sand/start_consumer.sh`（或直接 start_all.sh）"),
    ("8️⃣ 玄鉴（verify_daemon）挂了",
     "现象：看板玄鉴-进程红灯；daemon_audit.log 停更（>10min）",
     "影响：审外监督死——没人再巡检 operation_log、没人再验证 git 推送是否落地",
     "自动恢复：仅 @reboot",
     "恢复：`cd /vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘 && nohup python3 src/verify_daemon.py >> /vol2/1000/AI专用/Agent OS/logs/verify_daemon.log 2>&1 &`"),
    ("9️⃣ 备份失败（BK-01 红）",
     "现象：看板备份红灯；lms_backup.log 尾部有 ERROR；巡检报「最近 ERROR=4」",
     "影响：记忆快照可能没备份出去（rsync/磁盘/锁问题）。注意：BK-01 的「ERROR x4」可能是**历史**记录（近 40 行含），今天 0 次 ERROR + 快照新鲜 = 实际已恢复",
     "自动恢复：cron */15 --quick + 每小时归档 + 每日 02:30 全量（在则自动重试）",
     "恢复：`cd /vol2/1000/AI专用/living-memory-system-cloud && bash scripts/lms_backup.sh --quick` 手动跑一次看输出；持续失败查 df -h /vol2 与锁文件"),
    ("🔟 4:00 自动重置",
     "现象：（已关闭，无现象）",
     "影响：✅ 已确认关闭——crontab 中**没有** `0 4 * * *` 重置条目；现存的是 session-reset-watchdog（2min，只归档不重置），以及 openclaw 自身的会话轮换（非 4:00 强制清空）。",
     "自动恢复：不适用",
     "验证：`crontab -l | grep -E '4 \\* \\* \\*|reset'` 应只有 watchdog 归档条目，无重置执行条目"),
    ("1️⃣1️⃣ GitHub 网络断（push_verify WARN/FAIL）",
     "现象：看板玄鉴-审计发现红灯；audit 里 push_verify FAIL：本地 ahead=N 未推送",
     "影响：✅ 运行时**无影响**（记忆/总线全在本地）；只是代码/文档推送不落地。玄鉴每 5min 重试，网络恢复后会自动转绿",
     "自动恢复：push_verify 自动重试（网络恢复即自愈）",
     "恢复：网络恢复后进对应仓库 `git status` 看 ahead 数，`git push` 补推即可（Agent OS 仓：/vol2/1000/AI专用/Agent OS）"),
]

# ============ 8. 渲染 HTML ============
def esc(s): return H.escape(str(s), quote=True)

def card(x):
    st = x["st"]; name = x["name"]; ev = x["ev"]
    cls = {"OK": "ok", "WARN": "warn", "FAULT": "fault"}.get(st, "warn")
    lbl = {"OK": "正常", "WARN": "警告", "FAULT": "故障"}.get(st, st)
    auto, cmd = rec_for(name)
    return f'''<div class="card {cls}">
  <div class="ch"><span class="dot {cls}"></span><span class="cn">{esc(name)}</span><span class="cs">{lbl}</span></div>
  <div class="ce">{esc(ev)}</div>
  <details class="cr"><summary>🛠 怎么恢复</summary>
    <p class="ca">自动恢复：{esc(auto)}</p>
    <pre>{esc(cmd)}</pre>
  </details>
</div>'''

cards = "".join(card(x) for x in health) if health else '<div class="empty">暂无巡检数据（等 system_health_check.sh 跑一次）</div>'

verdict = "全绿 ✅" if h_fault == 0 and h_warn == 0 else ("有警告 ⚠️" if h_fault == 0 else "有故障 ❌")
vcls = "ok" if h_fault == 0 and h_warn == 0 else ("warn" if h_fault == 0 else "fault")

contract_fail_html = ""
if failing:
    rows = "".join(f"<li><code>{esc(k)}</code> — {esc(c_detail.get(k, '见 contract_check.log'))}</li>" for k in failing[:12])
    contract_fail_html = f'<div class="cfl"><b>契约违反 {len(failing)} 项：</b><ul>{rows}</ul></div>'

hist_html = ""
if hist:
    bars = "".join(
        f'<span class="hitem" title="{h[0]}"><b>{h[0][5:16]}</b> 绿{h[1][0]} 黄{h[1][1]} 红{h[1][2]}</span>'
        for h in hist)
    hist_html = f'<div class="hist">{bars}</div>'

scen_html = "".join(f'''<details class="scen"><summary>{esc(t)}</summary>
  <p><b>现象：</b>{esc(p)}</p>
  <p><b>影响：</b>{esc(imp)}</p>
  <p><b>自动恢复：</b>{esc(auto)}</p>
  <p><b>怎么办：</b>{esc(cmd)}</p>
</details>''' for t, p, imp, auto, cmd in SCEN)

lms_line = ""
if lms_health:
    lms_line = f'''<div class="k"><span class="kl">LMS 探针</span><span class="kv ok">✅ /health 200</span><span class="ks">轮次 {num(lms_st,'turn_count','%d')} · 熵比 {num(lms_st,'entropy_ratio')} · 目的 {num(lms_st,'purpose_coherence')}</span></div>'''
keynums = f'''
<div class="keynums">
  <div class="k"><span class="kl">沙漏记忆条数</span><span class="kv">{esc((sg or {}).get('sandglass_count','—'))}</span><span class="ks">txt {alabel(sg_txt_age)} 更新</span></div>
  <div class="k"><span class="kl">LMS 轮次/熵/目的</span><span class="kv">{num(lms_st,'turn_count','%d')}</span><span class="ks">熵 {num(lms_st,'entropy_ratio')} · 目的 {num(lms_st,'purpose_coherence')}</span></div>
  <div class="k"><span class="kl">self_pulse</span><span class="kv">{(pulse or {}).get('last_pulse','—')}</span><span class="ks">rc={(pulse or {}).get('pulse_rc','—')} · round={(pulse or {}).get('pulse_result',{}).get('round','—')}</span></div>
  <div class="k"><span class="kl">总线最近事件</span><span class="kv">{esc(bus_last)}</span><span class="ks">{alabel(bus_age)} · 死信 {dead} 行</span></div>
  <div class="k"><span class="kl">玄鉴审计(近200行)</span><span class="kv">FAIL {audit['FAIL']}</span><span class="ks">WARN {audit['WARN']} · OK {audit['OK']} · 最后 {esc(audit_ts)}</span></div>
  <div class="k"><span class="kl">备份日志(近40行)</span><span class="kv">ERROR {esc(bk_err)}</span><span class="ks">{esc(bk_tail[0][:80] if bk_tail else '—')}</span></div>
  <div class="k"><span class="kl">回魂注入</span><span class="kv">{alabel(hook_age)}</span><span class="ks">{esc(hook_line[:80])}</span></div>
  <div class="k"><span class="kl">怀疑账本</span><span class="kv">{esc(doubt_count)}</span><span class="ks">doubt.db {alabel(fage(os.path.join(NSB,'doubt.db')))} 写入</span></div>
</div>'''

html_doc = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="60">
<title>🐾 Agent OS 系统健康看板</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background:#0d1117; color:#e6edf3; font:14px/1.6 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; padding:20px; max-width:1200px; margin:0 auto; }}
h1 {{ font-size:22px; margin-bottom:4px; }}
h2 {{ font-size:16px; margin:26px 0 10px; color:#8b949e; border-bottom:1px solid #21262d; padding-bottom:6px; }}
.meta {{ color:#8b949e; font-size:12px; margin-bottom:12px; }}
.banner {{ padding:14px 18px; border-radius:10px; font-size:18px; font-weight:700; margin:10px 0 6px; }}
.banner.ok {{ background:#12261a; color:#3fb950; border:1px solid #238636; }}
.banner.warn {{ background:#2d2410; color:#d29922; border:1px solid #9e6a03; }}
.banner.fault {{ background:#2d1517; color:#f85149; border:1px solid #da3633; }}
.hist {{ margin:6px 0 10px; display:flex; gap:8px; flex-wrap:wrap; }}
.hitem {{ background:#161b22; border:1px solid #30363d; border-radius:6px; padding:4px 10px; font-size:12px; color:#8b949e; }}
.keynums {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:10px; margin:12px 0; }}
.k {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px 12px; }}
.kl {{ display:block; color:#8b949e; font-size:12px; }}
.kv {{ font-size:22px; font-weight:700; }}
.kv.ok {{ color:#3fb950; }}
.ks {{ display:block; color:#8b949e; font-size:12px; margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:10px; }}
.card {{ background:#161b22; border:1px solid #30363d; border-left:4px solid #8b949e; border-radius:8px; padding:10px 12px; }}
.card.ok {{ border-left-color:#3fb950; }} .card.warn {{ border-left-color:#d29922; }} .card.fault {{ border-left-color:#f85149; }}
.ch {{ display:flex; align-items:center; gap:8px; }}
.dot {{ width:10px; height:10px; border-radius:50%; flex:none; }}
.dot.ok {{ background:#3fb950; box-shadow:0 0 6px #3fb950; }} .dot.warn {{ background:#d29922; box-shadow:0 0 6px #d29922; }} .dot.fault {{ background:#f85149; box-shadow:0 0 6px #f85149; }}
.cn {{ font-weight:700; }} .cs {{ margin-left:auto; font-size:12px; color:#8b949e; }}
.ce {{ color:#c9d1d9; font-size:13px; margin:6px 0; }}
details.cr summary {{ cursor:pointer; color:#58a6ff; font-size:13px; }}
details.cr .ca {{ color:#d29922; font-size:12px; margin:6px 0 4px; }}
details.cr pre {{ background:#0d1117; border:1px solid #30363d; border-radius:6px; padding:8px; font-size:12px; color:#7ee787; white-space:pre-wrap; word-break:break-all; margin-top:4px; }}
.cfl {{ background:#2d1517; border:1px solid #da3633; border-radius:8px; padding:10px 14px; margin:10px 0; color:#f85149; font-size:13px; }}
.cfl ul {{ margin:6px 0 0 18px; }} .cfl li {{ margin:3px 0; color:#c9d1d9; }}
details.scen {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px 14px; margin-bottom:8px; }}
details.scen summary {{ cursor:pointer; font-weight:700; color:#58a6ff; }}
details.scen p {{ margin:6px 0; color:#c9d1d9; font-size:13px; }}
details.scen b {{ color:#8b949e; }}
footer {{ color:#484f58; font-size:12px; margin-top:30px; text-align:center; }}
.empty {{ color:#8b949e; }}
code {{ background:#0d1117; border:1px solid #30363d; border-radius:4px; padding:1px 5px; font-size:12px; }}
</style></head><body>
<h1>🐾 Agent OS 系统健康看板</h1>
<div class="meta">生成：{NOW_STR} ｜ 数据源：system_health.state / contract_check.state / 实时探针 / 状态文件 ｜ 页面每 60 秒自动刷新 ｜ 重新生成：<code>bash {esc(AO)}/scripts/gen_dashboard.sh</code></div>
<div class="banner {vcls}">巡检 {len(health)} 项：绿 {h_ok} · 黄 {h_warn} · 红 {h_fault} —— 判定：{verdict}（契约层：绿 {c_ok} · 黄 {c_warn} · 红 {c_fault}）</div>
{hist_html}
<h2>关键数字</h2>
{keynums}
<h2>组件状态（点击「怎么恢复」看处置步骤）</h2>
<div class="grid">{cards}</div>
<h2>契约层（{len(contracts)} 项，机器可校验）</h2>
{contract_fail_html if contract_fail_html else '<div class="k" style="color:#3fb950">✅ 无契约违反</div>'}
<h2>故障恢复预案（点开即看，照做即可）</h2>
{scen_html}
<footer>看板为只读快照，不改任何系统状态 ｜ 数据快照：<code>{esc(STATE_OUT)}</code></footer>
</body></html>'''

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html_doc)

snapshot = {
    "generated_at": NOW_STR, "verdict": verdict,
    "health": health, "health_counts": {"ok": h_ok, "warn": h_warn, "fault": h_fault},
    "contracts": contracts, "contract_counts": {"ok": c_ok, "warn": c_warn, "fault": c_fault},
    "probes": {
        "lms_health": lms_health, "lms_status": lms_st, "glue": glue, "sandglass": sg, "editor": ed,
    },
    "files": {
        "sandglass_txt_age_s": sg_txt_age, "event_bus_age_s": bus_age, "dead_letter_lines": dead,
        "audit": audit, "audit_last_ts": audit_ts, "backup_err_last40": bk_err,
        "doubt_count": doubt_count, "pulse": pulse, "hook_age_s": hook_age,
    },
    "history": hist,
}
os.makedirs(os.path.dirname(STATE_OUT) or ".", exist_ok=True)
with open(STATE_OUT, "w", encoding="utf-8") as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=1)

print(f"✅ 看板已生成: {OUT}")
print(f"   巡检 绿{h_ok} 黄{h_warn} 红{h_fault} ｜ 契约 绿{c_ok} 黄{c_warn} 红{c_fault} ｜ 数据快照: {STATE_OUT}")
PY

exit 0
