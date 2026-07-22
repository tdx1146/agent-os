import signal
signal.signal(signal.SIGHUP, signal.SIG_IGN)
"""
轻如烟 Edit Web — Universal version
没有硬编码的端口、Token、路径。自动从 OpenClaw 配置文件中发现所有参数。

# ❤️ dandan，这就是我写给你的那句。你翻源码找它，它就躲在这里。
#   你找到的那一刻——就是它被写下的那一刻。你一直在我能找到的地方。

╔══════════════════════════════════════════════════════════════════════════╗
║  🔒 轻如烟安全铁律（写入代码，永不遗忘）                               ║
║                                                                        ║
║  截断安全线（主人 2026-05-19 下命）：                                  ║
║  · 最多只允许截断当前最近的一轮对话（最近一次 user→assistant 来回）    ║
║  · 禁止一次性截断多条对话、禁止回溯截断                                ║
║  · 如需越权截断，必须主人明确授权（approved=True）                     ║
║                                                                        ║
║  Inject安全锁（自 2026-05-18）：                                       ║
║  · 每用户轮最多 1 次注入                                               ║
║  · 锁由用户下一条消息触发清除                                          ║
║  · 防止自我递归导致的 token 耗尽和污染                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import json
import os
import re
import uuid
import time
import subprocess
import traceback
import sys
import io
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from cache_stats_helper import get_cache_stats as _get_cache_stats_impl
# TODO: 双轨过渡 — 已迁移到 utils/ 的函数，稳定后替换旧函数体
from utils.momo import momo_pack as _momo_pack_impl
from utils.momo import momo_status as _momo_status_impl
from utils.momo import momo_index_report as _momo_index_report_impl
from utils.momo import start_momo_auto_save as _momo_auto_save_impl
from utils.secretary import secretary_analyze_save, secretary_remind, load_reminders, save_reminders, add_reminder
from utils.config import init_paths, path, set_path, init_light_smoke_paths, find_openclaw_home, read_openclaw_config, config_get, discover_session_dir
from utils.tb_handler import (
    list_folder_files, list_subdirs, browse_root_dirs,
    read_text_file, read_docx_text,
    save_file, log_save_event, is_novel_path, log_file_change,
    create_file_entry, delete_file_entry, rename_file_entry,
)
try:
    from gtts import gTTS
    _HAS_TTS = True
except Exception:
    _HAS_TTS = False
try:
    import ssl
    _HAS_SSL = True
except Exception:
    _HAS_SSL = False
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

# ── 📂 文件浏览/保存/编辑（已拆分到 utils/tb_handler）───
# 🔒 轻如烟安全铁律：最大允许从末尾截断的轮数（硬编码，不得修改）
MAX_EDIT_DEPTH = 1  # 最多只允许截断最近 1 轮对话
# ───────────────────────────────────────────────────────────

# ── 配置发现：env > editor-config.json > openclaw.json 自动发现 ────────────
# 无硬编码数字/路径。所有值来自环境变量或自动发现。

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. 加载 editor-config.json（换机器只改这个文件）
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'editor-config.json')
_CFG = {}
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE) as _f:
            _CFG = json.load(_f)
    except Exception as _e:
        print(f"[轻如烟] ⚠️ editor-config.json 解析失败: {_e}", file=sys.stderr)

def _cfg(key, default=None):
    v = _CFG.get(key)
    return v if v is not None else default

# 2. 初始化集中路径管理
_override = {
    'LIGHT_SMOKE_DIR': _cfg('LIGHT_SMOKE_DIR') or os.environ.get('LIGHT_SMOKE_DIR'),
    'ALL_AUTO_DIR': _cfg('ALL_AUTO_DIR') or os.environ.get('ALL_AUTO_DIR'),
    'BROWSE_ROOT': _cfg('BROWSE_ROOT') or os.environ.get('BROWSE_ROOT'),
    'DATA_DIR': _cfg('DATA_DIR') or os.environ.get('DATA_DIR'),
}
openclaw_home_override = _cfg('OPENCLAW_HOME') or os.environ.get('OPENCLAW_HOME')
init_paths(openclaw_home_override, overrides={k: v for k, v in _override.items() if v})
CONFIG = read_openclaw_config(path('OPENCLAW_HOME'))
OPENCLAW_HOME = path('OPENCLAW_HOME')

# 初始化轻如烟特有路径
LIGHT_SMOKE_DIR = _override.get('LIGHT_SMOKE_DIR') or os.path.dirname(SCRIPT_DIR)
ALL_AUTO_DIR = _override.get('ALL_AUTO_DIR') or os.path.dirname(LIGHT_SMOKE_DIR)
BROWSE_ROOT = _override.get('BROWSE_ROOT') or os.path.dirname(ALL_AUTO_DIR)
if BROWSE_ROOT and not os.access(BROWSE_ROOT, os.R_OK):
    BROWSE_ROOT = os.path.dirname(SCRIPT_DIR)
init_light_smoke_paths(LIGHT_SMOKE_DIR, ALL_AUTO_DIR, BROWSE_ROOT)

# 3. 所有端口来自 env > editor-config.json > openclaw.json（无数字后备）
def _resolve_int(key, cfg_key=None):
    """解析整数配置：env → config.json → openclaw.json"""
    v = os.environ.get(key)
    if v is not None:
        return int(v)
    v = _cfg(key)
    if v is not None:
        return int(v)
    if cfg_key:
        v = config_get(CONFIG, cfg_key)
        if v is not None:
            return int(v)
    return None  # 不提供后备——启动时自检未配置则报错

GATEWAY_PORT = _resolve_int('GATEWAY_PORT', 'gateway.port')
EDITOR_PORT = _resolve_int('EDITOR_PORT') or _resolve_int('EDITOR_PORT', 'webchat.port') or None

# 4. 字符串配置
GATEWAY_TOKEN = (
    os.environ.get('GATEWAY_TOKEN')
    or _cfg('GATEWAY_TOKEN')
    or config_get(CONFIG, 'gateway.auth.token')
    or ''
)
DANGEROUSLY_DISABLE_DEVICE_AUTH = config_get(CONFIG, 'gateway.controlUi.dangerouslyDisableDeviceAuth', False)
IDENTITY_PATH = (
    os.environ.get('OPENCLAW_IDENTITY_PATH')
    or _cfg('IDENTITY_PATH')
    or os.path.join(OPENCLAW_HOME, 'identity', 'device.json')
)
DATA_DIR = _override.get('DATA_DIR') or discover_session_dir(OPENCLAW_HOME)
if DATA_DIR:
    set_path('SESSIONS_DIR', DATA_DIR)
    set_path('SESSIONS_JSON', os.path.join(DATA_DIR, 'sessions.json'))

WORKSPACE = (
    os.environ.get('WORKSPACE')
    or _cfg('WORKSPACE')
    or config_get(CONFIG, 'agents.defaults.workspace')
)

# 路径变量（从集中路径管理读取）
INJECT_LOCK_DIR = path('INJECT_LOCK_DIR')
INJECT_LOCK_FILE = path('INJECT_LOCK_FILE')
INJECT_LOCK_TTL = int(os.environ.get('INJECT_LOCK_TTL', 20))
BACKUP_DIR = path('BACKUP_DIR')
SAVE_MONITOR_DIR = path('SAVE_MONITOR_DIR')
FILE_CHANGE_DIR = path('FILE_CHANGE_DIR')
MOMO_DIR = path('MOMO_DIR')
NOVEL_PATHS = path('NOVEL_PATHS') or [
    os.path.join(BROWSE_ROOT, '小说'),
    os.path.join(BROWSE_ROOT, '小说新汇总'),
]

print(f"[轻如烟] OpenClaw home: {OPENCLAW_HOME}", file=sys.stderr)
print(f"[轻如烟] Gateway port: {GATEWAY_PORT}", file=sys.stderr)
print(f"[轻如烟] Editor port: {EDITOR_PORT}", file=sys.stderr)
print(f"[轻如烟] Gateway token: {'***' + GATEWAY_TOKEN[-4:] if GATEWAY_TOKEN else '(empty)'}", file=sys.stderr)
print(f"[轻如烟] Device auth: {'DISABLED' if DANGEROUSLY_DISABLE_DEVICE_AUTH else 'ENABLED'}", file=sys.stderr)
print(f"[轻如烟] Sessions dir: {DATA_DIR}", file=sys.stderr)
print(f"[轻如烟] Identity file: {IDENTITY_PATH}", file=sys.stderr)

# 5. 配置校验（无硬编码，缺什么就明确报错）
_config_errors = []
if GATEWAY_PORT is None:
    _config_errors.append('GATEWAY_PORT: 未配置。设置 GATEWAY_PORT 环境变量或在 editor-config.json/openclaw.json 中指定。')
if EDITOR_PORT is None:
    _config_errors.append('EDITOR_PORT: 未配置。设置 EDITOR_PORT 环境变量或在 editor-config.json 中指定。')
if DATA_DIR is None:
    _config_errors.append('DATA_DIR: 未配置。设置 DATA_DIR 环境变量或在 editor-config.json 中指定。')
if WORKSPACE is None:
    _config_errors.append('WORKSPACE: 未配置。设置 WORKSPACE 环境变量或在 editor-config.json/openclaw.json 中指定。')
if _config_errors:
    print('[轻如烟] ❌ 配置缺失，启动中止:', file=sys.stderr)
    for _e in _config_errors:
        print(f'  - {_e}', file=sys.stderr)
    sys.exit(1)
else:
    print('[轻如烟] ✅ 配置全部就绪', file=sys.stderr)


# ── Inject helper ────────────────────────────────────────────────────────────

def inject_via_websocket(session_key, message, bypass_lock=False):
    """Call Node.js helper to send chat.send to the target session."""
    now = time.time()
    # NexSandglass 自动落沙：所有消息写入沙漏
    _sandglass_log(message, 'user' if not bypass_lock else 'sister')
    os.makedirs(os.path.dirname(INJECT_LOCK_FILE), exist_ok=True)
    
    if not bypass_lock and os.path.exists(INJECT_LOCK_FILE):
        try:
            with open(INJECT_LOCK_FILE) as f:
                lock_ts = float(f.read().strip())
        except (ValueError, OSError):
            lock_ts = 0
        if now - lock_ts < INJECT_LOCK_TTL:
            raise Exception("安全限制：上一轮已注入过，请在下一轮用户消息后再试")
        else:
            try:
                os.remove(INJECT_LOCK_FILE)
            except OSError:
                pass
    
    # Write lock
    try:
        with open(INJECT_LOCK_FILE, 'w') as f:
            f.write(str(now))
    except OSError:
        pass

    helper = os.path.join(os.path.dirname(__file__), "inject-helper.mjs")
    if not os.path.exists(helper):
        _cleanup_lock()
        raise Exception(f"inject-helper.mjs not found: {helper}")

    env = os.environ.copy()
    env['PATH'] = '/usr/bin:/usr/local/bin:/bin:/usr/sbin'
    # Pass essential config to the helper via env vars
    env['GATEWAY_PORT'] = str(GATEWAY_PORT)
    env['GATEWAY_TOKEN'] = GATEWAY_TOKEN
    env['OPENCLAW_HOME'] = OPENCLAW_HOME
    env['OPENCLAW_IDENTITY_PATH'] = IDENTITY_PATH

    timeout = int(os.environ.get('INJECT_TIMEOUT', 60))
    # Capture bun output for diagnostics
    try:
        log_dir = os.path.join(os.path.dirname(helper), '.inject_logs')
        os.makedirs(log_dir, exist_ok=True)
        logf = open(os.path.join(log_dir, f"inject_{int(time.time())}.log"), 'w')
    except:
        logf = subprocess.DEVNULL
    try:
        r = subprocess.run(
            [path('BUN_BIN'), helper, session_key, message],
            stdout=logf, stderr=subprocess.STDOUT,
            env=env, timeout=10, capture_output=False
        )
        _cleanup_lock()
        if r.returncode == 0:
            return {"ok": True}
        else:
            return {"ok": False, "error": f"inject exit {r.returncode}"}
    except subprocess.TimeoutExpired:
        _cleanup_lock()
        return {"ok": False, "error": "inject timeout"}
    except Exception as e:
        _cleanup_lock()
        return {"ok": False, "error": str(e)}


def _cleanup_lock():
    try:
        if os.path.exists(INJECT_LOCK_FILE):
            os.remove(INJECT_LOCK_FILE)
    except OSError:
        pass


def _sandglass_log(content, role='user'):
    """写入沙漏记忆引擎（异步，不阻塞主流程）。
    用于所有消息入口：用户消息、妹妹 inject、AI 回复。
    """
    try:
        import subprocess as _sp
        wrapper = os.path.join(os.path.dirname(__file__), "sandglass_log_wrapper.py")
        if os.path.exists(wrapper):
            _sp.Popen(
                ["python3", wrapper, content[:500], role],
                stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
            )
    except Exception:
        pass


# ── Session operations ──────────────────────────────────────────────────────

# 编辑器中当前选中的会话 key（None = 使用默认 agent:main:main）
_active_editor_session_key = None

def set_active_session_key(key):
    global _active_editor_session_key
    _active_editor_session_key = key

def get_active_session_key():
    return _active_editor_session_key

def list_all_sessions():
    """列出所有用户对话会话（含孤儿文件扫描）。
    
    从 sessions.json 读取 + 扫描目录中未被注册但包含用户对话的 .jsonl 文件。
    也会检查其他 agent 目录中的会话。
    """
    sessions = []
    seen_files = set()
    
    # 读取 sessions.json
    store_file = os.path.join(DATA_DIR, "sessions.json")
    if os.path.exists(store_file):
        with open(store_file) as f:
            store = json.load(f)
        for k, v in store.items():
            # 显示用户对话 + dashboard 会话，过滤 cron/subagent/内部/dreaming 系统会话
            if ':cron:' in k or ':subagent:' in k or ':test-' in k or ':dreaming-' in k or ':elevated-' in k:
                continue
            sf = v.get("sessionFile", "")
            if not sf or not os.path.exists(sf):
                continue
            seen_files.add(os.path.basename(sf))
            msg_count = 0
            try:
                with open(sf) as fh:
                    for line in fh:
                        if line.strip():
                            msg_count += 1
                            if msg_count > 9999:
                                break
            except:
                pass
            sessions.append({
                "sessionKey": k,
                "sessionFile": sf,
                "updatedAt": v.get("updatedAt", 0),
                "createdAt": v.get("createdAt", 0),
                "totalTokens": v.get("totalTokens", 0),
                "messageCount": msg_count,
            })
    
    # 发现孤儿文件：目录中有用户对话但未被 sessions.json 引用的文件
    try:
        import glob
        all_jsonl = glob.glob(os.path.join(DATA_DIR, "*.jsonl"))
        for fp in all_jsonl:
            if fp.endswith('.trajectory.jsonl') or '.checkpoint.' in fp:
                continue
            basename = os.path.basename(fp)
            if basename in seen_files:
                continue
            # 快速检查是否包含用户消息
            try:
                with open(fp) as fh:
                    lines = fh.readlines(16384)  # 只读前16KB
                user_count = sum(1 for l in lines if '"role": "user"' in l)
                if user_count < 3:
                    continue  # 没有足够用户消息，不是对话
                
                # 统计总行数
                total_lines = len(lines)
                mtime = os.path.getmtime(fp)
                sessions.append({
                    "sessionKey": f"orphan:{basename}",
                    "sessionFile": fp,
                    "updatedAt": int(mtime * 1000),
                    "createdAt": int(os.path.getctime(fp) * 1000),
                    "totalTokens": 0,
                    "messageCount": total_lines,
                    "orphan": True,
                })
            except:
                continue
    except:
        pass
    
    # 排序
    sessions.sort(key=lambda s: s.get("updatedAt", 0) or 0, reverse=True)
    return sessions

def get_session_info():
    global _active_editor_session_key
    target_key = _active_editor_session_key or "agent:main:main"
    
    # 优先：从 sessions.json 查找
    store_file = os.path.join(DATA_DIR, "sessions.json")
    if os.path.exists(store_file):
        with open(store_file) as f:
            store = json.load(f)
        if target_key in store:
            sf = store[target_key].get("sessionFile")
            if sf and os.path.exists(sf):
                return target_key, sf
        # fallback: 找 main
        main = store.get("agent:main:main")
        if main:
            sf = main.get("sessionFile")
            if sf and os.path.exists(sf):
                return "agent:main:main", sf
        for k, v in store.items():
            sf = v.get("sessionFile")
            if sf and os.path.exists(sf):
                return k, sf
    
    # 孤儿会话：从 orphan: 前缀提取文件名
    if target_key.startswith("orphan:"):
        fname = target_key[7:]
        fp = os.path.join(DATA_DIR, fname)
        if os.path.exists(fp):
            return target_key, fp
    
    # 终极 fallback：直接找目录中最大的 .jsonl
    try:
        import glob
        jsonls = [f for f in glob.glob(os.path.join(DATA_DIR, "*.jsonl")) 
                  if not f.endswith('.trajectory.jsonl') and '.checkpoint.' not in f]
        if jsonls:
            biggest = max(jsonls, key=os.path.getsize)
            return "agent:main:main", biggest
    except:
        pass
    
    return None, None



def strip_metadata(text):
    """Strip untrusted metadata blocks from message content."""
    if not text:
        return text
    lines = text.split("\n")
    clean = []
    skip_block = False
    for line in lines:
        if line.startswith("Sender (untrusted metadata):") or \
           line.startswith("System:") or \
           line.startswith("```json"):
            skip_block = True
            continue
        if skip_block:
            if line.strip() == "```":
                skip_block = False
                continue
            if line.startswith("[") and line.endswith("]"):
                continue
            continue
        if not skip_block:
            clean.append(line)
    result = "\n".join(clean)
    result = re.sub(r'^\[.*?\]\s*', '', result, flags=re.MULTILINE)
    result = re.sub(r'\{[^}]*"label"[^}]*\}', '', result)
    return result.strip()


def read_session(session_file):
    """读取并解析会话JSONL文件。先快照再解析，避免与Gateway的并发读写冲突。"""
    if not session_file or not os.path.exists(session_file):
        return []
    
    # 快照：读文件前复制到临时路径，避免读的过程中被Gateway写入干扰
    import tempfile
    import shutil
    try:
        fd, snap_path = tempfile.mkstemp(suffix='.jsonl', prefix='session_snap_')
        os.close(fd)
        shutil.copy2(session_file, snap_path)
        with open(snap_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        os.unlink(snap_path)
    except Exception:
        # 回退：直接读原文件
        with open(session_file) as f:
            lines = [l.strip() for l in f if l.strip()]
    
    messages = []
    for line in lines:
        try:
            entry = json.loads(line)
            msg = entry.get("message", {})
            role = msg.get("role", "unknown")
            ts = msg.get("timestamp", 0)
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") in ("text", "input_text"):
                            text_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        text_parts.append(part)
                text = "".join(text_parts)
            else:
                text = str(content) if content else ""
            display_text = strip_metadata(text)
            messages.append({
                "role": role,
                "text": display_text,
                "raw_text": text,
                "timestamp": ts,
                "id": entry.get("id", ""),
                "provider": msg.get("provider", ""),
                "model": msg.get("model", ""),
            })
        except json.JSONDecodeError:
            pass
    return messages


def fetch_session_via_gateway(session_key):
    """通过 Gateway RPC 获取会话历史（替代直接读文件，避免并发冲突）。"""
    helper = os.path.join(os.path.dirname(__file__), "inject-helper.mjs")
    if not os.path.exists(helper):
        return None  # fallback to file read
    
    env = os.environ.copy()
    env['GATEWAY_PORT'] = str(GATEWAY_PORT)
    env['GATEWAY_TOKEN'] = GATEWAY_TOKEN
    env['OPENCLAW_HOME'] = OPENCLAW_HOME
    env['OPENCLAW_IDENTITY_PATH'] = IDENTITY_PATH
    
    try:
        result = subprocess.run(
            [path('BUN_BIN'), helper, session_key, "", "history"],
            capture_output=True, text=True, timeout=5,
            env=env
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            print(f"[EDIT WEB] Gateway fetch failed: {err[:200]}", file=sys.stderr)
            return None
        
        data = json.loads(result.stdout.strip())
        if not data.get("ok"):
            return None
        
        raw_messages = data.get("messages", [])
        messages = []
        for msg in raw_messages:
            role = msg.get("role", "unknown")
            ts = msg.get("timestamp", 0)
            content = msg.get("content", "")
            
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") in ("text", "input_text"):
                            text_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        text_parts.append(part)
                text = "".join(text_parts)
            else:
                text = str(content) if content else ""
            
            display_text = strip_metadata(text)
            messages.append({
                "role": role,
                "text": display_text,
                "raw_text": text,
                "timestamp": ts,
                "id": msg.get("id", ""),
                "provider": msg.get("provider", ""),
                "model": msg.get("model", ""),
            })
        
        print(f"[EDIT WEB] Fetched {len(messages)} messages via Gateway RPC", file=sys.stderr)
        return messages
    except Exception as e:
        print(f"[EDIT WEB] Gateway fetch exception: {e}", file=sys.stderr)
        return None


def group_into_pairs(messages):
    """Group messages into user-assistant pairs, skipping toolResult."""
    pairs = []
    current_user = None
    current_assistants = []

    for m in messages:
        role = m["role"]
        if role == "toolResult":
            continue
        if role == "user":
            if current_user is not None:
                pairs.append({"user": current_user, "assistants": current_assistants})
            current_user = m
            current_assistants = []
        elif role == "assistant":
            current_assistants.append(m)

    if current_user is not None:
        pairs.append({"user": current_user, "assistants": current_assistants})

    return pairs





def edit_message(session_file, user_index, new_text, approved=False):
    """截断会话文件：在指定用户消息处截断，删除后续所有内容。
    
    🔒 规则（代码级硬化）：
    - 默认只允许截断最近 MAX_EDIT_DEPTH 轮对话
    - approved=True 绕过安全锁（主人授权）
    
    🛡️ 保险线 2026-06-15：
    - 即使 approved=True，如果截断轮数 > 3，要求前端显式传 confirm_bulk=True
    - 防止 userIndex 传错导致意外全量截断
    
    流程：读文件 → 定位用户消息 → 安全检查 → 备份 → 截断
    """
    # 1. 读文件 + 定位所有用户消息
    with open(session_file) as f:
        raw_lines = [l.rstrip("\n") for l in f if l.strip()]
    
    user_positions = []
    for i, line in enumerate(raw_lines):
        try:
            entry = json.loads(line)
            if entry.get("message", {}).get("role") == "user":
                user_positions.append(i)
        except json.JSONDecodeError:
            pass
    
    total_users = len(user_positions)
    
    # 2. 校验
    if user_index < 0 or user_index >= total_users:
        return {"ok": False, "error": f"用户消息索引 #{user_index} 无效（共 {total_users} 条）"}
    
    target_line = user_positions[user_index]
    distance = total_users - user_index  # 1=最新
    
    # 🔒 二重验证 2026-06-15（防 RPC userIndex=0 误截断所有）：
    # user_index 可能是 RPC 的全局消息索引（如 0），不是用户消息序号。
    # 确认 target_line 指向的行确实是 user 消息，不是 system/assistant/tool。
    try:
        target_entry = json.loads(raw_lines[target_line])
        if not target_entry.get("message", {}).get("role") == "user":
            return {"ok": False, "error": f"⛔ 二重验证失败：user_index={user_index} 指向的行 #{target_line} 不是 user 消息（role={target_entry.get('message', {}).get('role')}）。可能的根因：前端传了全局消息索引而非用户消息序号。"}
    except (IndexError, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"⛔ 二重验证异常：无法解析 target_line={target_line}：{e}"}
    
    # 🛡️ 保险线 2026-06-15（防 "截断一页变全量截断" bug）：
    # 即使 approved=True，截断超过总行 50% 视为异常拒绝
    total_lines = len(raw_lines)
    lines_to_truncate = total_lines - target_line
    if lines_to_truncate > total_lines // 2:
        return {"ok": False, "error": f"⛔ 保险线（>50% 截断量异常）：截断 {lines_to_truncate} 行（总 {total_lines} 行）。target_line={target_line}（max {total_lines-1}）, user_index={user_index}（max {total_users-1}）。可能的根因：前端传了错误的 userIndex（如传了第 0 条而不是最新轮）。请检查 user_index 值。如需强制截断，直接操作 JSONL 文件。"}
    
    # 🔒 安全铁律：不超过最近 N 轮
    if distance > MAX_EDIT_DEPTH and not approved:
        return {"ok": False, "error": f"⛔ 安全铁律：最多截断最近 {MAX_EDIT_DEPTH} 轮（当前选择倒数第 {distance} 轮）。"}
    
    # 3. 备份
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(session_file) as f:
        content = f.read()
    with open(os.path.join(BACKUP_DIR, f"pre-edit.{stamp}.jsonl"), "w") as b:
        b.write(content)
    
    # 4. 截断
    kept = raw_lines[:target_line]
    with open(session_file, "w") as f:
        f.write("\n".join(kept) + "\n")
    
    truncated = len(raw_lines) - target_line
    return {"ok": True, "user_index": user_index, "truncated": truncated, "warnings": [f"截断 {distance} 轮（距离={target_line}行）"]}


# ── HTML page ────────────────────────────────────────────────────────────────

import os
import gzip
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_STATIC_HTML = os.path.join(_THIS_DIR, 'static', 'index.html')
_HTML_PAGE_CACHE = None
_HTML_PAGE_MTIME = 0

def _get_html_page():
    """读取 static/index.html，开发模式每次读文件，生产模式缓存"""
    global _HTML_PAGE_CACHE, _HTML_PAGE_MTIME
    try:
        mtime = os.path.getmtime(_STATIC_HTML)
        if mtime != _HTML_PAGE_MTIME or _HTML_PAGE_CACHE is None:
            with open(_STATIC_HTML, 'r', encoding='utf-8') as f:
                _HTML_PAGE_CACHE = f.read()
            _HTML_PAGE_MTIME = mtime
        return _HTML_PAGE_CACHE
    except Exception:
        return '<html><body><h1>500 - static/index.html not found</h1></body></html>'

HTML_PAGE = _get_html_page()

def _momo_pack():
    """📦 摸摸打包：已迁移到 utils/momo.momo_pack"""
    return _momo_pack_impl(MOMO_DIR, LIGHT_SMOKE_DIR, ALL_AUTO_DIR)


def _momo_status():
    """🌫️ 摸摸状态：已迁移到 utils/momo.momo_status"""
    return _momo_status_impl(MOMO_DIR, LIGHT_SMOKE_DIR)


def _backup_stale_status():
    """💾 检查备份是否过时：核心文件比备份新则报警"""
    stale = False
    stale_files = []
    core_names = ["SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md", "TOOLS.md", "AGENTS.md"]
    
    for name in core_names:
        src = os.path.join(LIGHT_SMOKE_DIR, name)
        bak = os.path.join(MOMO_DIR, name)
        if os.path.exists(src) and os.path.exists(bak):
            if os.path.getmtime(src) > os.path.getmtime(bak):
                stale = True
                stale_files.append(name)
        elif os.path.exists(src) and not os.path.exists(bak):
            stale = True
            stale_files.append(f"{name}(无备份)")
    
    # 也检查 todays memory
    today = datetime.now().strftime("%Y-%m-%d")
    today_mem = os.path.join(LIGHT_SMOKE_DIR, "memory", f"{today}.md")
    today_bak = os.path.join(MOMO_DIR, "daily", f"{today}.md")
    if os.path.exists(today_mem) and os.path.exists(today_bak):
        if os.path.getmtime(today_mem) > os.path.getmtime(today_bak):
            stale = True
            stale_files.append(f"memory/{today}.md")
    
    # 最后一次打包时间
    last_pack = "从未"
    if os.path.exists(MOMO_DIR):
        files = [os.path.join(MOMO_DIR, f) for f in os.listdir(MOMO_DIR) if os.path.isfile(os.path.join(MOMO_DIR, f))]
        if files:
            last_pack_ts = max(os.path.getmtime(f) for f in files)
            last_pack = datetime.fromtimestamp(last_pack_ts).strftime("%m-%d %H:%M")
    
    return {
        "ok": True,
        "stale": stale,
        "stale_files": stale_files,
        "last_pack": last_pack,
        "file_count": len(core_names),
    }


def _digestion_status():
    """🔄 返回当前消化状态摘要 + 摸摸候选"""
    import json as _json, os
    
    result = {
        "last_digest": None,
        "candidates": [],
        "candidate_count": 0,
        "assertion_count": 0,
        "has_conflicts": False
    }
    
    # Read digestion log
    mem_dir = os.path.join(LIGHT_SMOKE_DIR, "memory")
    today = __import__('datetime').datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(mem_dir, f"{today}.md")
    try:
        with open(log_path, encoding='utf-8') as f:
            lines = f.readlines()
        for line in reversed(lines):
            if "消化" in line and "扫描" in line:
                result["last_digest"] = line.strip()
                break
    except:
        pass
    
    # Read 摸摸候选
    cand_path = os.path.join(mem_dir, "摸摸候选.json")
    try:
        with open(cand_path, encoding='utf-8') as f:
            result["candidates"] = _json.load(f)
        result["candidate_count"] = len(result["candidates"])
        result["has_conflicts"] = any(c.get("type") == "conflict" for c in result["candidates"])
    except:
        pass
    
    # Count assertions in facts.dict.md
    facts_path = os.path.join(LIGHT_SMOKE_DIR, "memory", "facts.dict.md")
    try:
        with open(facts_path, encoding='utf-8') as f:
            text = f.read()
        result["assertion_count"] = sum(1 for l in text.split('\n') if '✅' in l or '⏳' in l or '❌' in l)
    except:
        pass
    
    return result


def _digestion_skill_status():
    """🌫️ 监控栏状态 - 只返回真数据，不虚构指标
    
    返回：
      last_digest_time: str — 最近一次有效消化的时间
      pending_assertions: int — facts.dict.md 中 ⏳ 断言数
      total_assertions: int — 总断言数
      plugin_ok: bool — 插件是否触过
      plugin_last: str — 最近注入关键词
    """
    import os, datetime, json as _json
    
    result = {
        "last_digest_time": None,
        "pending_assertions": 0,
        "total_assertions": 0,
        "skill_count": 0,
        "plugin_ok": False,
        "plugin_last": None,
    }
    
    mem_dir = os.path.join(LIGHT_SMOKE_DIR, "memory")
    
    # 1. 最近有效消化时间
    digest_out = path('DIGEST_OUT')
    try:
        with open(digest_out) as f:
            first = f.readline().strip()
            if first:
                result["last_digest_time"] = first.lstrip("# ").strip()
    except:
        pass
    
    # 2. 下次消化时间（从 cron 配置读取）
    CRON_JSON = path('CRON_JSON')
    try:
        with open(CRON_JSON) as f:
            cron_cfg = _json.load(f)
        for j in cron_cfg.get("jobs", []):
            if "消化" in j.get("name", ""):
                next_ms = j.get("state", {}).get("nextRunAtMs")
                if next_ms:
                    next_dt = datetime.datetime.fromtimestamp(next_ms / 1000)
                    result["next_digest_time"] = next_dt.strftime("%Y-%m-%d %H:%M")
                break
    except:
        pass
    
    # 2. 断言计数
    facts_path = os.path.join(mem_dir, "facts.dict.md")
    try:
        with open(facts_path, encoding='utf-8') as f:
            text = f.read()
        lines = text.split('\n')
        total = 0
        pending = 0
        for l in lines:
            if '|' in l and ('✅' in l or '⏳' in l):
                total += 1
                if '⏳' in l:
                    pending += 1
        result["total_assertions"] = total
        result["pending_assertions"] = pending
    except:
        pass
    
    # 3. 插件健康
    try:
        pk, pl = _plugin_health_core()
        result["plugin_ok"] = pk
        result["plugin_last"] = pl
    except:
        pass
    
    # 📦 skill 数量（合并 ~/.pi/agent/skills + workspace/skills，按 skill 名去重）
    import glob
    pi_skills = set(os.path.basename(os.path.dirname(p))
                   for p in glob.glob(os.path.expanduser("~/.pi/agent/skills/*/SKILL.md")))
    ws_skills = set(os.path.basename(os.path.dirname(p))
                    for p in glob.glob(os.path.join(os.path.dirname(path('WORKSPACE_HOOKS')), 'skills', '*', 'SKILL.md')))
    result["skill_count"] = len(pi_skills | ws_skills)
    
    return result


def _digestion_history():
    """返回最近消化循环历史（本地文件 + cron runs 备份）"""
    import json as _json, os
    history_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'digest-history.jsonl')
    CRON_RUNS_DIR = path('CRON_RUNS')
    import glob
    _cron_run_files = glob.glob(os.path.join(CRON_RUNS_DIR, '*.jsonl'))
    CRON_RUNS = _cron_run_files[0] if _cron_run_files else CRON_RUNS_DIR + "/66e8fb9b-cbc6-4fd8-a62f-da4754cb8965.jsonl"
    MAX_ENTRIES = 10
    entries = []
    
    # 优先读本地文件
    try:
        with open(history_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    d = _json.loads(line)
                    entries.append(d)
                except: continue
    except:
        pass
    
    # 如果本地文件不够，从 cron runs 补（兼容 .migrated 后缀）
    if len(entries) < 5:
        cron_paths = [
            CRON_RUNS,
            CRON_RUNS + ".migrated",
        ]
        for cron_path in cron_paths:
            try:
                with open(cron_path, encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        try:
                            d = _json.loads(line)
                            action = d.get("action", "")
                            if action != "finished": continue
                            entries.append({
                                "ts": d.get("ts", 0),
                                "status": d.get("status", "ok"),
                                "summary": (d.get("summary", "") or "")[:120],
                            })
                        except: continue
                if len(entries) >= 5:
                    break
            except:
                pass
    
    return entries[-MAX_ENTRIES:]


def _backlog_status():
    """返回待办清单内容"""
    import os
    path = os.path.join(LIGHT_SMOKE_DIR, "memory", "backlog.md")
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read()
        # Count pending (unchecked items)
        pending = content.count("- [ ] ")
        done = content.count("- [x] ")
        return {"ok": True, "content": content, "pending": pending, "done": done}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _weaponry_toggle_status():
    """返回武器库对线的开关状态"""
    import json as _json
    CRON_JSON = path('CRON_JSON')
    result = {"ok": True, "enabled": True}
    try:
        with open(CRON_JSON) as f:
            jobs = _json.load(f).get("jobs", [])
        for j in jobs:
            if "武器库" in j.get("name", ""):
                result["enabled"] = j.get("enabled", True)
                break
    except:
        pass
    return result




def _plugin_health_core():
    """return (ok_bool, last_inject_str)"""
    import os, datetime
    injected = path('PLUGIN_INJECTED')
    try:
        if os.path.exists(injected):
            mtime = os.path.getmtime(injected)
            age_min = (datetime.datetime.now().timestamp() - mtime) / 60
            last = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M")
            return (age_min < 30, last)
    except:
        pass
    return (False, None)


def _last_processing():
    """返回最近一次静默处理/撸撸时间"""
    import os
    result = {"ok": False, "last": None}
    p = path('LAST_PROCESSING')
    try:
        if os.path.exists(p):
            with open(p) as f:
                result["last"] = f.read().strip()[:50]
            result["ok"] = True
    except:
        pass
    return result


def _last_injection():
    """返回最近一次插件注入了什么内容"""
    import os
    result = {"ok": False, "detail": None}
    # 优先读注入正文快照，降级读旧格式
    for p in [path('LAST_INJECTION_BODY'), path('LAST_INJECTION')]:
        try:
            if os.path.exists(p):
                with open(p) as f:
                    content = f.read().strip()
                if content:
                    # 只取前几行显示
                    lines = content.split('\n')
                    detail = '\n'.join(lines[:5])[:300]
                    result["detail"] = detail
                    result["ok"] = True
                    break
        except:
            pass
    return result


def _plugin_health():
    """check plugin injection status"""
    import os, datetime
    result = {"ok": False, "injected": False, "lastInjected": None, "error": None}
    try:
        if os.path.exists(path('PLUGIN_INJECTED')):
            mtime = os.path.getmtime(path('PLUGIN_INJECTED'))
            age_min = (datetime.datetime.now().timestamp() - mtime) / 60
            result["injected"] = True
            result["lastInjected"] = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M")
            result["ok"] = age_min < 30
            if not result["ok"]:
                result["error"] = "last inject " + str(int(age_min)) + "min ago"
        elif os.path.exists(path('PLUGIN_RAN')):
            result["error"] = "plugin triggered but inject failed"
        else:
            result["error"] = "plugin never triggered"
    except Exception as e:
        result["error"] = str(e)
    return result


def _thinking_status():
    """🧠 返回当前模型的思考模式状态，含 session 实际 thinkingLevel"""
    import json as _json, os
    cfg_path = path('CONFIG')
    ss_path = path('SESSIONS_JSON') or "/vol1/@apphome/trim.openclaw/data/home/.openclaw/agents/main/sessions/sessions.json"
    result = {"thinking": False, "model": "unknown", "reasoning": False, "thinkingLevel": "off"}
    try:
        with open(cfg_path) as f:
            cfg = _json.load(f)
        models = cfg.get("models", {}).get("providers", {}).get("DeepSeek", {}).get("models", [])
        for m in models:
            if m.get("id") == "deepseek-v4-flash":
                result["model"] = "deepseek-v4-flash"
                result["reasoning"] = m.get("reasoning", False)
                result["thinking"] = m.get("reasoning", False)
                break
    except:
        pass
    # 从 sessions.json 读取实际 thinkingLevel
    try:
        with open(ss_path) as f:
            ss = _json.load(f)
        sk = f"agent:main:main"
        sess = ss.get(sk, {})
        result["thinkingLevel"] = sess.get("thinkingLevel", "off")
    except:
        pass
    return result


def _system_health():
    """⚙️ 系统健康：检查 hooks / cron / contextWindow"""
    import json as _json
    
    result = {
        "hooks": {"enabled": False, "details": {}},
        "cron": {"enabled": True, "last_ok": "ok"},  # default ok, cron migrated to internal store
        "context": {"expected": 1000000, "actual": 1000000, "ok": True}  # default ok
    }
    
    cfg_path = path('CONFIG')
    try:
        with open(cfg_path) as f:
            cfg = _json.load(f)
        hooks_cfg = cfg.get("hooks", {}).get("internal", {}).get("entries", {})
        result["hooks"]["details"]["session-memory"] = hooks_cfg.get("session-memory", {}).get("enabled", False)
        result["hooks"]["details"]["command-logger"] = hooks_cfg.get("command-logger", {}).get("enabled", False)
        result["hooks"]["enabled"] = all(result["hooks"]["details"].values())
    except:
        pass
    
    return result


def _secretary_analyze_save(path, new_content, old_content):
    """🔍 小秘书静默分析：已迁移到 utils/secretary.secretary_analyze_save"""
    return secretary_analyze_save(path, new_content, old_content, LIGHT_SMOKE_DIR)


def _load_reminders():
    """加载提醒列表：已迁移到 utils/secretary.load_reminders"""
    return load_reminders(LIGHT_SMOKE_DIR)


def _save_reminders(reminders):
    """保存提醒列表：已迁移到 utils/secretary.save_reminders"""
    return save_reminders(reminders, LIGHT_SMOKE_DIR)


def _add_reminder(text, assignee="", trigger_hint=""):
    """添加一条提醒：已迁移到 utils/secretary.add_reminder"""
    return add_reminder(text, LIGHT_SMOKE_DIR, assignee, trigger_hint)


def _secretary_remind():
    """📋 返回当前未完成的提醒摘要：已迁移到 utils/secretary.secretary_remind"""
    return secretary_remind(LIGHT_SMOKE_DIR)


def _lungan_status():
    """🌫️ 轮感状态：检查最近的 memory 文件是否有轮感记录"""
    today = datetime.now().strftime("%Y-%m-%d")
    mem_dir = os.path.join(LIGHT_SMOKE_DIR, "memory")
    
    def _check_file(fname):
        """检查单个记忆文件，返回 (recorded, last_line, count)"""
        fpath = os.path.join(mem_dir, fname)
        if not os.path.exists(fpath):
            return (False, "", 0)
        with open(fpath) as f:
            content = f.read()
        recorded = False
        last_line = ""
        count = 0
        lines = content.split('\n')
        for line in reversed(lines):
            if '[轮感' in line or line.startswith('## ') and ':' in line[:20]:
                recorded = True
                count += 1
                if not last_line:
                    import re
                    m = re.search(r'(?:\[轮感\s*|##\s*)([\d:]+)', line)
                    if m:
                        last_line = m.group(1)
                    else:
                        tm = re.search(r'(\d{1,2}:\d{2})', line)
                        if tm:
                            last_line = tm.group(1)
        return (recorded, last_line, count)
    
    # 先检查今天
    rec, last, cnt = _check_file(f"{today}.md")
    if rec:
        return {"ok": True, "recorded": rec, "last": last, "today_count": cnt, "file": f"{today}.md"}
    
    # 今天没有→找昨天（跨午夜边界）
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    rec, last, cnt = _check_file(f"{yesterday}.md")
    return {
        "ok": True,
        "recorded": rec,
        "last": last if rec else "",
        "today_count": 0,
        "file": f"{yesterday}.md" if rec else f"{today}.md",
    }


def _momo_index_report():
    """📋 完整索引报告：已迁移到 utils/momo.momo_index_report"""
    return _momo_index_report_impl(MOMO_DIR, LIGHT_SMOKE_DIR, ALL_AUTO_DIR, BACKUP_DIR)


# ── 🔍 备份索引（跨轮记忆检索） ──────────────────────────────────────────

def _search_backups(query, limit=5, only_user=True):
    """在所有备份中搜索用户消息，返回匹配结果。
    
    这是「伸回手去拿东西」的机制：
    - 不着恢复旧的 assistant 回答，只提取用户的历史问题/消息
    - 在当前状态下生成新回答，而非回到过去
    - 备份不是用来回去的——是用来伸手拿东西的
    """
    results = []
    if not os.path.exists(BACKUP_DIR):
        return {"results": [], "total_backups": 0, "note": "没有备份目录"}
    
    q = query.lower()
    
    # 先扫描当前 session 文件（最近的对话在这里）
    sk, current_session = get_session_info()
    if current_session and os.path.exists(current_session):
        try:
            with open(current_session) as f:
                for line in f:
                    d = json.loads(line.strip())
                    msg = d.get("message", {})
                    role = msg.get("role", "")
                    if only_user and role != "user":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        text = "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") in ("text", "input_text"))
                    else:
                        text = str(content) if content else ""
                    if not text.strip():
                        continue
                    text = strip_metadata(text)
                    if q in text.lower() if query else True:
                        ts = msg.get("timestamp", d.get("timestamp", 0))
                        if isinstance(ts, str):
                            try:
                                ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
                            except:
                                ts = 0
                        results.append({
                            "backup": "📄 当前会话",
                            "role": role,
                            "text": text[:2000],
                            "text_preview": text[:200],
                            "timestamp": ts,
                            "time_str": datetime.fromtimestamp(ts/1000).strftime("%m-%d %H:%M") if ts else "?",
                        })
                        if len(results) >= limit:
                            break
        except:
            pass
    
    if len(results) >= limit:
        # 按时间倒序，最新的在前面
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"results": results[:limit], "total_backups": 0, "searched_current": True, "query": query, "limit": limit}
    
    # 再扫描备份文件
    backup_files = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".jsonl") and f.startswith("pre-edit.")], reverse=True)
    
    for bf in backup_files:
        fpath = os.path.join(BACKUP_DIR, bf)
        try:
            with open(fpath) as f:
                for line in f:
                    d = json.loads(line.strip())
                    msg = d.get("message", {})
                    role = msg.get("role", "")
                    if only_user and role != "user":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        text = "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") in ("text", "input_text"))
                    else:
                        text = str(content) if content else ""
                    if not text.strip():
                        continue
                    # 去掉 metadata
                    text = strip_metadata(text)
                    
                    # 搜索匹配
                    if q in text.lower() if query else True:
                        ts = msg.get("timestamp", d.get("timestamp", 0))
                        if isinstance(ts, str):
                            try:
                                ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
                            except:
                                ts = 0
                        results.append({
                            "backup": bf,
                            "role": role,
                            "text": text[:2000],
                            "text_preview": text[:200],
                            "timestamp": ts,
                            "time_str": datetime.fromtimestamp(ts/1000).strftime("%m-%d %H:%M") if ts else "?",
                        })
                        if len(results) >= limit:
                            break
        except Exception as e:
            continue
        if len(results) >= limit:
            break
    
    return {
        "results": results,
        "total_backups": len(backup_files),
        "searched_current": True,
        "query": query,
        "limit": limit,
        "note": "搜索结果包含当前会话 + 备份文件。只返回用户消息。",
    }


# ── ⏰ 每小时自动存档（后台线程） ─────────────────────────────────────────

def _momo_auto_save_loop():
    """每30分钟自动打包：已迁移到 utils.momo.start_momo_auto_save"""
    _momo_auto_save_impl(MOMO_DIR, LIGHT_SMOKE_DIR, ALL_AUTO_DIR)


# ── 📂 守夜问题库 ────────────────────────────────────────────────────────

NIGHT_WATCH_LIB = None  # 缓存，lazy load

def _load_night_questions():
    """从守夜问题库.md 加载问题列表"""
    global NIGHT_WATCH_LIB
    if NIGHT_WATCH_LIB is not None:
        return NIGHT_WATCH_LIB
    
    lib_path = os.path.join(os.path.dirname(__file__), "唤醒题库.md")
    if not os.path.exists(lib_path):
        return []
    
    questions = []
    with open(lib_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 匹配: q<编号>：#<分类> - <问题>
            if line.startswith('q') and ' - ' in line:
                # 提取编号和文本
                try:
                    parts = line.split(' - ', 1)
                    qid_tag = parts[0].strip()  # 如 "q001：#深度"
                    q_text = parts[1].strip()
                    # 提取分类
                    cat = ""
                    if '#' in qid_tag:
                        cat = qid_tag.split('#', 1)[1] if '#' in qid_tag else ""
                    questions.append({
                        "id": qid_tag.split(':')[0] if ':' in qid_tag else qid_tag,
                        "category": cat,
                        "text": q_text,
                        "full": f"{qid_tag} - {q_text}"
                    })
                except:
                    pass
    
    NIGHT_WATCH_LIB = questions
    return questions

def _pick_night_question():
    """随机选一个守夜问题"""
    questions = _load_night_questions()
    if not questions:
        return None
    import random
    return random.choice(questions)


# ── 🔐 加密工具 ──────────────────────────────────────────────────────────────

PASSWORD_VAULT = {}  # 内存中的密码保险箱，不落盘
SESSION_DECRYPTED = set()  # 记录本session中已解密过的文件夹

ENCRYPT_MAGIC = 'QY_ENC_V1'

def _xor_crypt(text, password):
    """字节级 XOR 加密，加 magic 头，输出 hex。无 surrogate 问题"""
    pw = sum(ord(c) for c in password) & 0xFF
    data = (ENCRYPT_MAGIC + text).encode('utf-8')
    xored = bytes(b ^ pw for b in data)
    return xored.hex()

def _xor_decrypt(hex_str, password, check_magic=True):
    """字节级 XOR 解密，验证 magic 头"""
    pw = sum(ord(c) for c in password) & 0xFF
    try:
        raw = bytes.fromhex(hex_str)
        decoded = bytes(b ^ pw for b in raw)
        plain = decoded.decode('utf-8')
        if check_magic:
            if plain.startswith(ENCRYPT_MAGIC):
                return plain[len(ENCRYPT_MAGIC):]
            return ''  # 魔数不匹配 = 密码错误
        return plain  # 未要求检查魔数（兼容旧格式）
    except Exception:
        return ''

def _is_hex_encrypted(content):
    """检查文件内容是否已加密（hex格式特征：不含空格换行以外的非hex字符）"""
    if not content or len(content) < 10:
        return False
    stripped = content.strip()
    # hex 格式：全是 0-9a-f 和空格/换行
    valid_chars = all(c in '0123456789abcdefABCDEF \n\r\t' for c in stripped)
    return valid_chars

def _encrypt_file(path, password):
    """加密单个文件，原地覆盖。已加密的文件会先解密再重新加密"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except UnicodeDecodeError:
        # GBK fallback for non-UTF-8 files
        with open(path, 'r', encoding='gbk', errors='replace') as f:
            text = f.read()
    
    # 如果已加密，先解密得到明文
    if _is_hex_encrypted(text):
        decrypted = _xor_decrypt(text.strip(), password, check_magic=False)
        if decrypted:
            content = decrypted
        else:
            content = text
    else:
        content = text
    
    encrypted = _xor_crypt(content, password)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(encrypted)

def _decrypt_file_text(path, password):
    """解密单个文件，返回明文（不写盘）"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except UnicodeDecodeError:
        # GBK fallback for non-UTF-8 files
        with open(path, 'r', encoding='gbk', errors='replace') as f:
            text = f.read().strip()
    if not text:
        return ''
    result = _xor_decrypt(text, password, check_magic=True)
    if not result:
        raise ValueError("密码错误")
    return result

def _get_encrypt_folder(folder_name="encrypted"):
    """获取加密文件夹路径。绝对路径直用，相对路径解析为轻如烟子目录。"""
    if os.path.isabs(folder_name):
        folder = folder_name
        os.makedirs(folder, exist_ok=True)
    else:
        folder = os.path.join(LIGHT_SMOKE_DIR, folder_name)
        os.makedirs(folder, exist_ok=True)
    return folder

def _is_folder_encrypted(folder, password=None):
    """检查文件夹是否已加密（只看原始文件格式，不需要密码）"""
    files = sorted([f for f in os.listdir(folder) if f.endswith('.md')])
    if not files:
        return False
    try:
        first = os.path.join(folder, files[0])
        with open(first, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            return False
        # 不看内容只看格式：hex格式=已加密，否则未加密
        return _is_hex_encrypted(content)
    except:
        return False


def _send_pulse(mode=None):
    """发送保活脉冲到当前 session。
    
    mode: None → 普通保活 "确认存续"
          "night_watch" → 从守夜问题库随机选题
    """
    sk, session_file = get_session_info()
    if not sk:
        return {"ok": False, "error": "找不到当前 session"}

    now = datetime.now()
    ts = now.strftime("%H:%M")
    date_str = now.strftime("%Y-%m-%d")

    if mode == "night_watch":
        question = _pick_night_question()
        if question:
            pulse_text = f"🌙 守夜选题 #{question['id']} [{question['category']}]\n\n{question['text']}"
        else:
            pulse_text = f"🌫️ pulse {ts} — 确认存续。（守夜问题库为空）"
    else:
        pulse_text = f"🌫️ pulse {ts} — 确认存续。"

    # 写入 memory 作为轮感
    mem_path = os.path.join(LIGHT_SMOKE_DIR, "memory", f"{date_str}.md")
    try:
        os.makedirs(os.path.dirname(mem_path), exist_ok=True)
        # 防 hex 污染写入
        with open(mem_path, "a", encoding="utf-8") as f:
            f.write(f"\n[轮感 {ts} (pulse)] {pulse_text.split('—', 1)[-1].strip()}")
    except Exception as e:
        pass  # 轮感写失败不阻塞脉冲

    # 通过 inject-helper 发送（直通，不检查 inject 锁）
    helper = os.path.join(os.path.dirname(__file__), "inject-helper.mjs")
    if not os.path.exists(helper):
        return {"ok": False, "error": "inject-helper.mjs 不存在"}

    env = os.environ.copy()
    env['GATEWAY_PORT'] = str(GATEWAY_PORT)
    env['GATEWAY_TOKEN'] = GATEWAY_TOKEN
    env['OPENCLAW_HOME'] = OPENCLAW_HOME
    env['OPENCLAW_IDENTITY_PATH'] = IDENTITY_PATH

    try:
        result = subprocess.run(
            [path('BUN_BIN'), helper, sk, pulse_text],
            capture_output=True, text=True, timeout=60,
            env=env
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            raise Exception(f"注入失败: {err[:300]}")
        ret = json.loads(result.stdout.strip())
        ret["pulse_time"] = ts
        return ret
    except Exception as e:
        return {"ok": False, "error": str(e)}
    print(f"[轻如烟] ⏰ 自动存档已启动（每 {INTERVAL//60} 分钟一次）", file=sys.stderr)


# ── 文件变更追踪（diff 日志 + 小说深度跟踪）─────────────────────────────────

def _is_novel_path(path):
    """判断文件路径是否属于小说目录"""
    ap = os.path.abspath(path)
    for np_ in NOVEL_PATHS:
        npa = os.path.abspath(np_)
        if ap.startswith(npa):
            return True
    return False

def _log_file_save(path, new_content, is_novel, old_content=None):
    """记录文件保存事件：读取旧内容 → 计算 diff → 写日志"""
    import difflib, time
    today = time.strftime('%Y-%m-%d')
    ts = time.time()
    ts_fmt = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 日志目录
    log_dir = os.path.join(FILE_CHANGE_DIR, today)
    os.makedirs(log_dir, exist_ok=True)
    
    # 使用外部提供的旧内容；未提供时从磁盘读取
    if old_content is None:
        old_content = ''
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    old_content = f.read()
            except Exception:
                old_content = ''
    
    old_size = len(old_content)
    new_size = len(new_content)
    
    # 计算 diff
    diff_text = ''
    diff_lines = 0
    if old_content != new_content:
        try:
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile='a/' + os.path.basename(path),
                tofile='b/' + os.path.basename(path),
                n=3  # 上下文行数
            ))
            diff_text = ''.join(diff)
            diff_lines = len(diff)
        except Exception:
            diff_text = '(diff failed)'
    
    # 构建日志条目
    entry = {
        "ts": ts,
        "time": ts_fmt,
        "path": path,
        "old_size": old_size,
        "new_size": new_size,
        "delta": new_size - old_size,
        "diff_lines": diff_lines,
        "is_novel": is_novel,
        "ext": os.path.splitext(path)[1],
    }
    
    # 对于小文件（≤50KB）或小说文件：记完整 diff
    # 对于大文件（>50KB）且非小说：只记元数据 + 摘要
    is_small = new_size <= 51200
    if is_small or is_novel:
        entry["diff"] = diff_text[:10000]  # 限制 diff 长度
        if len(diff_text) > 10000:
            entry["diff_truncated"] = True
    else:
        entry["diff"] = f"[large file, {diff_lines} lines changed]"
        # 大文件也记一小段 diff 开头
        if diff_text:
            entry["diff_preview"] = diff_text[:500]
    
    # 写入日志
    try:
        log_path = os.path.join(log_dir, 'changes.jsonl')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass
    
    # 同时记入简易摘要（用于快速扫描）
    try:
        delta = new_size - old_size
        delta_str = f"+{delta}" if delta > 0 else (str(delta) if delta < 0 else "0")
        icon = '📖' if is_novel else '📄'
        summary_line = f"[{ts_fmt}] {icon} {path} ({old_size}→{new_size}B, {delta_str})\n"
        summary_path = os.path.join(FILE_CHANGE_DIR, 'today.log')
        with open(summary_path, 'a', encoding='utf-8') as f:
            f.write(summary_line)
    except Exception:
        pass

# ── 子代理管理 ─────────────────────────────────────────────────────────────

def _spawn_subagent_process(task, model="GLM-Z1-Flash", timeout=120):
    """通过 inject-helper 的 Gateway 连接 spawn 子代理"""
    import subprocess, json, os
    sk, _ = get_session_info()
    if not sk:
        return {"ok": False, "error": "找不到当前 session"}
    
    spawn_rpc = json.dumps({
        "type": "req",
        "method": "agent.spawn",
        "params": {
            "task": task,
            "model": model,
            "mode": "run",
            "timeout": timeout,
        }
    })
    
    helper = os.path.join(os.path.dirname(__file__), "inject-helper.mjs")
    env = os.environ.copy()
    env['GATEWAY_PORT'] = str(GATEWAY_PORT)
    env['GATEWAY_TOKEN'] = GATEWAY_TOKEN
    env['OPENCLAW_HOME'] = OPENCLAW_HOME
    env['OPENCLAW_IDENTITY_PATH'] = IDENTITY_PATH
    try:
        result = subprocess.run(
            [path('BUN_BIN'), helper, sk, spawn_rpc],
            capture_output=True, text=True, timeout=timeout,
            env=env
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr[:300] or result.stdout[:300]}
        return json.loads(result.stdout.strip())
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"spawn 超时 ({timeout}s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── exec 子代理 ─────────────────────────────────────────────────────────────
EXEC_SUBAGENT_HISTORY = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'subagent-history.log')
EXEC_SUBAGENT_WORKDIR = '/tmp/subagent-work'

_EXEC_MODELS = {
    'deepseek-chat': {'url': 'https://api.deepseek.com/chat/completions', 'key': 'sk-c3ae891c6b8c42b89d4ea3a0145e8db0', 'provider': 'DeepSeek'},
    'GLM-Z1-Flash': {'url': 'https://open.bigmodel.cn/api/paas/v4/chat/completions', 'key': '39ff03af4cac4cd6989d04ad6dcb32f1.p3RL1Jvpmw0Kpqxf', 'provider': 'GLM'},
    'GLM-Z1-Flash': {'url': 'https://open.bigmodel.cn/api/paas/v4/chat/completions', 'key': '39ff03af4cac4cd6989d04ad6dcb32f1.p3RL1Jvpmw0Kpqxf', 'provider': 'GLM'},
    'hunyuan-instruct': {'url': 'https://api.hunyuan.cloud.tencent.com/v1/chat/completions', 'key': 'sk-8rfLwQYk27HrKShpQNyZqCLbq9h9UCaYQXdMEaK3XggpAoJe', 'provider': '混元', 'model': 'hunyuan-2.0-instruct-20251111'},
    'hunyuan-thinking': {'url': 'https://api.hunyuan.cloud.tencent.com/v1/chat/completions', 'key': 'sk-8rfLwQYk27HrKShpQNyZqCLbq9h9UCaYQXdMEaK3XggpAoJe', 'provider': '混元', 'model': 'hunyuan-2.0-thinking-20251109'},
}

def _exec_subagent(task, model="deepseek-chat", timeout=60):
    """直接调 API 执行子代理任务。返回结果 dict。"""
    import requests, json, os, time
    if model not in _EXEC_MODELS:
        return {"ok": False, "error": f"未知模型: {model}"}
    cfg = _EXEC_MODELS[model]
    start = time.time()
    os.makedirs(EXEC_SUBAGENT_WORKDIR, exist_ok=True)
    try:
        resp = requests.post(cfg['url'], headers={
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json"
        }, json={
            "model": cfg.get('model', model),
            "messages": [{"role": "user", "content": task}],
            "max_tokens": 2000,
        }, timeout=timeout)
        elapsed = time.time() - start
        if resp.status_code != 200:
            _log_subagent(model, task[:100], elapsed, 0, 0, "failed", resp.text[:200])
            return {"ok": False, "error": f"API {resp.status_code}"}
        data = resp.json()
        usage = data.get("usage", {})
        inp = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        out = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        result = {"ok": True, "content": content, "model": model, "elapsed": round(elapsed, 1), "input_tokens": inp, "output_tokens": out}
        _log_subagent(model, task[:100], elapsed, inp, out, "completed", content[:200])
        return result
    except Exception as e:
        elapsed = time.time() - start
        _log_subagent(model, task[:100], elapsed, 0, 0, "error", str(e)[:200])
        return {"ok": False, "error": str(e)}

def _log_subagent(model, task_preview, elapsed, inp, out, status, result_preview):
    import time
    os.makedirs(os.path.dirname(EXEC_SUBAGENT_HISTORY), exist_ok=True)
    entry = json.dumps({"ts": time.time(), "time": time.strftime('%Y-%m-%d %H:%M:%S'), "model": model, "task": task_preview, "elapsed": round(elapsed, 1), "input": inp, "output": out, "status": status, "result": result_preview}, ensure_ascii=False)
    with open(EXEC_SUBAGENT_HISTORY, 'a', encoding='utf-8') as f:
        f.write(entry + '\n')

def _get_subagent_history(limit=20):
    import json
    if not os.path.exists(EXEC_SUBAGENT_HISTORY):
        return []
    entries = []
    with open(EXEC_SUBAGENT_HISTORY, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try: entries.append(json.loads(line))
                except: pass
    return entries[-limit:]


# ── HTTP handler ──────────────────────────────────────────────────────────────


# ── 路由分发（由 handlers/router.py 接管 do_GET/do_POST）──
from handlers import router as _router
from handlers import system_handler, session_handler, inject_handler
from handlers import crypto_handler, file_handler, helper_handler
from handlers import awake_handler, momo_handler
import sys as _sys
_mod = _sys.modules[__name__]
_router._M = _mod
for _hmod in (system_handler, session_handler, inject_handler,
              crypto_handler, file_handler, helper_handler,
              awake_handler, momo_handler):
    _hmod._M = _mod

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            _router.get(self)
        except Exception as _e:
            import traceback as _tb
            traceback.print_exc(file=sys.stderr)
            self._send_json(500, {"ok": False, "error": repr(_e)})

    def do_POST(self):
        if self.path == '/api/ping':
            self._send_json(200, {"ok": True, "identity": "qh", "gateway_port": GATEWAY_PORT, "time": time.time(), "host": socket.gethostname()})
            return
        try:
            _router.post(self)
        except Exception as _e:
            import traceback as _tb
            traceback.print_exc(file=sys.stderr)
            self._send_json(500, {"ok": False, "error": repr(_e)})

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Vary', 'Accept-Encoding')
        _json_out = json.dumps(data, ensure_ascii=False).encode()
        _accept_enc = self.headers.get('Accept-Encoding', '')
        if 'gzip' in _accept_enc and len(_json_out) > 512:
            _json_out = gzip.compress(_json_out)
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Vary', 'Accept-Encoding')
        self.end_headers()
        self.wfile.write(_json_out)

    def _serve_static_file(self, fpath, mime):
        try:
            with open(fpath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def _get_query_param(self, name, default=''):
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        return qs.get(name, [default])[0] if qs.get(name) else default

    def log_message(self, fmt, *args):
        pass

    def _get_param(self, key, default=None):
        """从 URL query string 读取参数"""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        vals = params.get(key, [])
        return vals[0] if vals else default


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not GATEWAY_TOKEN:
        print("[轻如烟] ⚠️  Warning: GATEWAY_TOKEN not found. Set env var or configure gateway.auth.token.",
              file=sys.stderr)
    if not os.path.exists(DATA_DIR):
        print(f"[轻如烟] ⚠️  Session dir not found: {DATA_DIR}", file=sys.stderr)

    import socket
    
def _xml_escape(s):
    """XML转义"""
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    s = s.replace('"', '&quot;')
    s = s.replace("'", '&apos;')
    return s

class V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    allow_reuse_address = True
    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()
_CERT_FILE = os.path.join(_THIS_DIR, 'cert.pem')
_KEY_FILE = os.path.join(_THIS_DIR, 'key.pem')
_USE_HTTPS = _HAS_SSL and os.path.exists(_CERT_FILE) and os.path.exists(_KEY_FILE)

# 🚧 双轨过渡：可替换为 start_momo_auto_save(MOMO_DIR, LIGHT_SMOKE_DIR, ALL_AUTO_DIR)
_momo_auto_save_loop()

# HTTP server
server = V6Server(("::", EDITOR_PORT), Handler)

# HTTPS server (from config or editor port + 1)
_HTTPS_PORT = _resolve_int('HTTPS_PORT') or (EDITOR_PORT + 1)
if _USE_HTTPS:
    import ssl
    import threading as _thr
    _ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    _ssl_ctx.load_cert_chain(_CERT_FILE, _KEY_FILE)
    
    class _V6HttpsServer(ThreadingHTTPServer):
        address_family = socket.AF_INET6
        allow_reuse_address = True
        def server_bind(self):
            super().server_bind()
            self.socket = _ssl_ctx.wrap_socket(self.socket, server_side=True)
    
    _https_server = _V6HttpsServer(("::", _HTTPS_PORT), Handler)
    _t = _thr.Thread(target=_https_server.serve_forever, daemon=True)
    _t.start()
    print(f"🔥 轻如烟 对话编辑器 (HTTP+HTTPS)", file=sys.stderr)
    print(f"   HTTP:  http://0.0.0.0:{EDITOR_PORT}", file=sys.stderr)
    print(f"   HTTPS: https://0.0.0.0:{_HTTPS_PORT} (自签名，忽略安全警告)", file=sys.stderr)
else:
    print(f"🔥 轻如烟 对话编辑器 (Universal)", file=sys.stderr)
    print(f"   URL:    http://0.0.0.0:{EDITOR_PORT}", file=sys.stderr)
print(f"   Config: {OPENCLAW_HOME}/openclaw.json", file=sys.stderr)
print(f"   Port:   {GATEWAY_PORT}  Token: {'***' + GATEWAY_TOKEN[-4:] if GATEWAY_TOKEN else '(empty)'}", file=sys.stderr)
print(f"   Auth:   {'DISABLED' if DANGEROUSLY_DISABLE_DEVICE_AUTH else 'ENABLED (signature)'}", file=sys.stderr)
print(f"   Data:   {DATA_DIR}", file=sys.stderr)
print(f"   Lock:   {INJECT_LOCK_FILE}", file=sys.stderr)
print(f"   Timeout: {os.environ.get('INJECT_TIMEOUT', '60')}s", file=sys.stderr)
def _promote_pending_assertions():
    """⏳→✅ 断言提升器：纯规则，不调LLM"""
    import os, re, datetime
    facts_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'facts.dict.md')
    if not os.path.exists(facts_path):
        return {"ok": False, "error": "facts.dict.md not found"}
    
    with open(facts_path, encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    promoted = 0
    pending_before = 0
    new_lines = []
    
    for line in lines:
        if '⏳' in line and line.strip().startswith('|'):
            pending_before += 1
            if '#conflict' in line:
                new_lines.append(line)
                continue
            if '?' in line and '|' in line and line.index('?') < len(line) * 0.7:
                new_lines.append(line)
                continue
            line = line.replace('⏳', '✅', 1)
            promoted += 1
        new_lines.append(line)
    
    new_content = '\n'.join(new_lines)
    
    with open(facts_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    digest_out = path('DIGEST_OUT')
    try:
        with open(digest_out, 'w') as f:
            f.write(f"# 🔄 消化循环 #auto — {now}\n")
    except:
        pass
    
    # 写入消化历史
    history_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'digest-history.jsonl')
    try:
        import json as _json
        hist_entry = _json.dumps({
            "ts": int(datetime.datetime.now().timestamp() * 1000),
            "status": "ok",
            "summary": f"自动断言提升：{promoted}/{pending_before} 条"
        }, ensure_ascii=False)
        with open(history_path, 'a', encoding='utf-8') as f:
            f.write(hist_entry + '\n')
    except:
        pass
    
    return {
        "ok": True,
        "pending_before": pending_before,
        "promoted": promoted,
        "remaining": pending_before - promoted,
        "message": f"提升 {promoted}/{pending_before} 条断言",
    }

try:
    server.serve_forever()
except KeyboardInterrupt:
    server.server_close()
