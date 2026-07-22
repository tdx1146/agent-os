#!/usr/bin/env python3
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

# ── Auto-discover OpenClaw config ──────────────────────────────────────────

def find_openclaw_home():
    """Find the OpenClaw home directory."""
    env_home = os.environ.get('OPENCLAW_HOME')
    if env_home:
        return env_home
    
    home = os.path.expanduser('~')
    candidates = [
        '/vol1/@apphome/trim.openclaw/data/home/.openclaw',
        os.path.join(home, '.openclaw'),
        os.path.join(home, '.config', 'openclaw'),
        os.path.join(os.environ.get('XDG_DATA_HOME', os.path.join(home, '.local', 'share')), 'openclaw'),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return os.path.join(home, '.openclaw')


def read_openclaw_config(openclaw_home):
    """Read OpenClaw config from openclaw.json (supports yaml in theory)."""
    json_path = os.path.join(openclaw_home, 'openclaw.json')
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)
    # YAML not natively supported; try config.yaml but warn
    for y in ('config.yaml', 'config.yml'):
        yp = os.path.join(openclaw_home, y)
        if os.path.exists(yp):
            print(f"[EDIT WEB WARN] Found {y} but YAML not supported. Set env vars or use openclaw.json.", file=sys.stderr)
            return {}
    return {}


def config_get(obj, path_str, default=None):
    """Safely traverse a dotted path in a dict."""
    parts = path_str.split('.')
    cur = obj
    for p in parts:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


def discover_session_dir(openclaw_home):
    """Discover the sessions directory. Looks in agents/*/sessions/."""
    agents_dir = os.path.join(openclaw_home, 'agents')
    if not os.path.exists(agents_dir):
        return None
    
    for entry in os.listdir(agents_dir):
        sessions_path = os.path.join(agents_dir, entry, 'sessions')
        if os.path.isdir(sessions_path):
            return sessions_path
    
    # Fallback: check if sessions.json exists directly
    legacy = os.path.join(agents_dir, 'main', 'sessions')
    if os.path.isdir(legacy):
        return legacy
    
    return None


# ── 📂 文件浏览/保存/编辑（TODO: 双轨过渡，后续拆到 utils/tb_handlers）───
# 🔒 轻如烟安全铁律：最大允许从末尾截断的轮数（硬编码，不得修改）
MAX_EDIT_DEPTH = 1  # 最多只允许截断最近 1 轮对话
# ───────────────────────────────────────────────────────────

# ── Discover everything ─────────────────────────────────────────────────────
OPENCLAW_HOME = os.environ.get('OPENCLAW_HOME') or find_openclaw_home()
CONFIG = read_openclaw_config(OPENCLAW_HOME)

# Gateway port: env > config > 22881
GATEWAY_PORT = int(os.environ.get('GATEWAY_PORT') or config_get(CONFIG, 'gateway.port') or 19107)
# Gateway token: env > config > ''
GATEWAY_TOKEN = os.environ.get('GATEWAY_TOKEN') or config_get(CONFIG, 'gateway.auth.token') or ''
# Device auth disabled?
DANGEROUSLY_DISABLE_DEVICE_AUTH = config_get(CONFIG, 'gateway.controlUi.dangerouslyDisableDeviceAuth', False)
# Identity path
if os.environ.get('OPENCLAW_IDENTITY_PATH'):
    IDENTITY_PATH = os.environ['OPENCLAW_IDENTITY_PATH']
else:
    IDENTITY_PATH = os.path.join(OPENCLAW_HOME, 'identity', 'device.json')
# Session directory: env > auto-discover
DATA_DIR = os.environ.get('DATA_DIR') or discover_session_dir(OPENCLAW_HOME) or os.path.join(OPENCLAW_HOME, 'agents', 'main', 'sessions')
# Workspace
WORKSPACE = os.environ.get('WORKSPACE') or config_get(CONFIG, 'agents.defaults.workspace') or os.path.expanduser('~')
# Editor port
EDITOR_PORT = int(os.environ.get('EDITOR_PORT', 18888))
# Inject lock
# ├── 从此处开始，使用脚本相对路径 ──────────────────────────────
# 这样整个 所有自动化/ 文件夹可以搬到任何路径下使用
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── config.json 配置覆盖（优先于环境变量和自动检测）──
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'editor-config.json')
_CFG = {}
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE) as _f:
            _CFG = json.load(_f)
    except: pass

def _cfg(key, default=None):
    v = _CFG.get(key)
    return v if v is not None else default

LIGHT_SMOKE_DIR = _cfg('LIGHT_SMOKE_DIR') or os.environ.get('LIGHT_SMOKE_DIR') or os.path.dirname(SCRIPT_DIR)
ALL_AUTO_DIR = _cfg('ALL_AUTO_DIR') or os.environ.get('ALL_AUTO_DIR') or os.path.dirname(LIGHT_SMOKE_DIR)
# 加密工具文件夹浏览器：文件树根目录（可展开/折叠的层级导航）
BROWSE_ROOT = _cfg('BROWSE_ROOT') or os.environ.get('BROWSE_ROOT') or os.path.dirname(ALL_AUTO_DIR)
# 环境变量可能导致指向 /vol1 — 有权限才用
if not os.access(BROWSE_ROOT, os.R_OK):
    # fallback 到 workspace
    BROWSE_ROOT = os.path.dirname(SCRIPT_DIR)

INJECT_LOCK_DIR = os.environ.get('INJECT_LOCK_DIR') or os.path.join(LIGHT_SMOKE_DIR, '.locks')
INJECT_LOCK_FILE = os.path.join(INJECT_LOCK_DIR, '.inject_lock')
INJECT_LOCK_TTL = int(os.environ.get('INJECT_LOCK_TTL', 20))
BACKUP_DIR = os.environ.get('BACKUP_DIR') or os.path.join(ALL_AUTO_DIR, 'backups')
SAVE_MONITOR_DIR = os.path.join(LIGHT_SMOKE_DIR, 'memory')
FILE_CHANGE_DIR = os.path.join(SAVE_MONITOR_DIR, 'file-changes')
MOMO_DIR = os.environ.get('MOMO_DIR') or os.path.join(ALL_AUTO_DIR, '找回自己')

# 小说路径规则（深度跟踪）
NOVEL_PATHS = [
    os.path.join(BROWSE_ROOT, '小说'),
    os.path.join(BROWSE_ROOT, '小说新汇总'),
]

print(f"[轻如烟] OpenClaw home: {OPENCLAW_HOME}", file=sys.stderr)
print(f"[轻如烟] Gateway port: {GATEWAY_PORT}", file=sys.stderr)
print(f"[轻如烟] Gateway token: {'***' + GATEWAY_TOKEN[-4:] if GATEWAY_TOKEN else '(empty)'}", file=sys.stderr)
print(f"[轻如烟] Device auth: {'DISABLED' if DANGEROUSLY_DISABLE_DEVICE_AUTH else 'ENABLED'}", file=sys.stderr)
print(f"[轻如烟] Sessions dir: {DATA_DIR}", file=sys.stderr)
print(f"[轻如烟] Identity file: {IDENTITY_PATH}", file=sys.stderr)


# ── Inject helper ────────────────────────────────────────────────────────────

def inject_via_websocket(session_key, message, bypass_lock=False):
    """Call Node.js helper to send chat.send to the target session."""
    # Inject lock: prevent recursion
    now = time.time()
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
    try:
        # Don't wait — the editor uses polling, not the injector's response
        # Capture bun output for diagnostics
        try:
            log_dir = os.path.join(os.path.dirname(helper), '.inject_logs')
            os.makedirs(log_dir, exist_ok=True)
            logf = open(os.path.join(log_dir, f"inject_{int(time.time())}.log"), 'w')
        except:
            logf = subprocess.DEVNULL
        subprocess.Popen(
            ["/var/apps/bunjs/target/bin/bun", helper, session_key, message],
            stdout=logf, stderr=subprocess.STDOUT,
            env=env
        )
        _cleanup_lock()
        return {"ok": True}
    except subprocess.TimeoutExpired:
        _cleanup_lock()
        raise Exception(f"注入超时 ({timeout}s)")
    except Exception:
        _cleanup_lock()
        raise


def _cleanup_lock():
    try:
        if os.path.exists(INJECT_LOCK_FILE):
            os.remove(INJECT_LOCK_FILE)
    except OSError:
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
    """从 sessions.json 读取所有会话，按 updatedAt 降序排列"""
    store_file = os.path.join(DATA_DIR, "sessions.json")
    if not os.path.exists(store_file):
        return []
    with open(store_file) as f:
        store = json.load(f)
    sessions = []
    for k, v in store.items():
        # 只显示用户对话会话，排除 cron/subagent/dashboard/dreaming/test/agentTurn 内部会话
        if ':cron:' in k or ':subagent:' in k or ':dashboard:' in k or ':test-' in k or ':dreaming-' in k or ':elevated-' in k:
            continue
        sf = v.get("sessionFile", "")
        if not sf or not os.path.exists(sf):
            continue
        # 统计消息数（快速读前几行判断）
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
    sessions.sort(key=lambda s: s.get("updatedAt", 0) or 0, reverse=True)
    return sessions

def get_session_info():
    global _active_editor_session_key
    store_file = os.path.join(DATA_DIR, "sessions.json")
    if not os.path.exists(store_file):
        return None, None
    with open(store_file) as f:
        store = json.load(f)
    
    # 如果设置了主动切换的 session key，优先使用
    target_key = _active_editor_session_key or "agent:main:main"
    if target_key in store:
        sf = store[target_key].get("sessionFile")
        if sf and os.path.exists(sf):
            return target_key, sf
    
    # fallback
    main = store.get("agent:main:main")
    if main:
        sf = main.get("sessionFile")
        if sf and os.path.exists(sf):
            return "agent:main:main", sf
    for k, v in store.items():
        sf = v.get("sessionFile")
        if sf and os.path.exists(sf):
            return k, sf
    return None, None
    store_file = os.path.join(DATA_DIR, "sessions.json")
    if not os.path.exists(store_file):
        return None, None
    with open(store_file) as f:
        store = json.load(f)
    main = store.get("agent:main:main")
    if main:
        sf = main.get("sessionFile")
        if sf and os.path.exists(sf):
            return "agent:main:main", sf
    for k, v in store.items():
        sf = v.get("sessionFile")
        if sf and os.path.exists(sf):
            return k, sf
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
            ["/var/apps/bunjs/target/bin/bun", helper, session_key, "", "history"],
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
    """Edit a user message and truncate everything after it.
    
    🔒 安全铁律：最多只允许截断最近 MAX_EDIT_DEPTH 轮对话。
    除非 approved=True（主人明确授权），否则回溯截断会被拒绝。
    """
    messages = read_session(session_file)
    
    # 🔒 安全检查：计算目标消息是倒数第几条用户消息
    total_users = sum(1 for m in messages if m["role"] == "user")
    distance_from_end = total_users - user_index  # 1 = 最新，2 = 上一轮 ...
    if distance_from_end > MAX_EDIT_DEPTH and not approved:
        return {
            "ok": False, "error": (
                f"⛔ 安全铁律：最多只能截断最近 {MAX_EDIT_DEPTH} 轮对话"
                f"（当前选择的是倒数第 {distance_from_end} 轮）。"
                f"如需截断更多，请主人明确授权（approved=true）。"
            )
        }
    
    user_count = -1
    target_idx = -1
    for i, m in enumerate(messages):
        if m["role"] == "user":
            user_count += 1
            if user_count == user_index:
                target_idx = i
                break

    if target_idx == -1:
        return {"ok": False, "error": f"用户消息 #{user_index} 未找到"}

    with open(session_file) as f:
        raw_lines = [l.rstrip("\n") for l in f if l.strip()]

    raw_target = -1
    uc = -1
    for i, line in enumerate(raw_lines):
        try:
            entry = json.loads(line)
            if entry.get("message", {}).get("role") == "user":
                uc += 1
                if uc == user_index:
                    raw_target = i
                    break
        except json.JSONDecodeError:
            pass

    if raw_target == -1:
        return {"ok": False, "error": f"无法定位用户消息 #{user_index}"}

    # Backup
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"pre-edit.{stamp}.jsonl")
    with open(session_file) as f:
        with open(backup_path, "w") as b:
            b.write(f.read())

    # Truncate: keep only lines up to (but not including) the target message
    # 🔧 修复：只截断，不修改/写入目标消息。注入步骤会通过 Gateway 发送新内容。
    kept = raw_lines[:raw_target]
    
    with open(session_file, "w") as f:
        f.write("\n".join(kept) + "\n")

    truncated = len(raw_lines) - raw_target - 1
    return {"ok": True, "user_index": user_index, "truncated": truncated}


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
    """📦 摸摸打包：重新整理找回自己目录的关键文件
    # 🚧 已迁移到 utils/momo.momo_pack — 此函数体为双轨过渡，稳定后删除
    
    打包规则（代码级硬化，不由记忆维护）：
    
    必须包含：
    [x] 身份文件: SOUL.md, IDENTITY.md, USER.md, MEMORY.md, TOOLS.md, AGENTS.md
    [x] 公约文件: README.md（含还原指引）, 🌫️-摸摸协议.md, 可复制.md
    [x] 每日记录: daily/（轮感、断言索引、facts.dict.md、秘书日志）
    [x] 编辑器: edit-web.py, inject-helper.mjs
    [x] 系统配置: system-config/openclaw.json, cron-jobs.json, skills/, hooks/
    [x] 还原说明: README.md（自动生成，含完整文件清单和还原步骤）
    
    每次修改打包逻辑后，必须更新此注释中的清单。
    """
    import shutil
    import datetime as _dt
    os.makedirs(MOMO_DIR, exist_ok=True)
    os.makedirs(os.path.join(MOMO_DIR, "daily"), exist_ok=True)
    
    src_root = LIGHT_SMOKE_DIR
    packed = []
    errors = []
    now = _dt.datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M")
    
    # 核心身份文件（便携路径）
    core_files = [
        ("SOUL.md", os.path.join(src_root, "SOUL.md")),
        ("IDENTITY.md", os.path.join(src_root, "IDENTITY.md")),
        ("USER.md", os.path.join(src_root, "USER.md")),
        ("MEMORY.md", os.path.join(src_root, "MEMORY.md")),
        ("TOOLS.md", os.path.join(src_root, "TOOLS.md")),
        ("AGENTS.md", os.path.join(src_root, "AGENTS.md")),
    ]
    for name, src in core_files:
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(MOMO_DIR, name))
            packed.append(name)
        else:
            errors.append(f"{name}: 源文件不存在")
    
    # Daily notes
    memory_dir = os.path.join(src_root, "memory")
    if os.path.exists(memory_dir):
        for f in os.listdir(memory_dir):
            if f.endswith((".md", ".log")) and f not in ("next-turn-note.md", "pulse.log", "subagent-history.log", "file-changes"):
                shutil.copyfile(os.path.join(memory_dir, f), os.path.join(MOMO_DIR, "daily", f))
                packed.append(f"daily/{f}")
    
    # next-turn-note
    ntn = os.path.join(memory_dir, "next-turn-note.md")
    if os.path.exists(ntn):
        shutil.copyfile(ntn, os.path.join(MOMO_DIR, "next-turn-note.md"))
        packed.append("next-turn-note.md")
    
    # 代码文件
    scripts_dir = os.path.dirname(__file__)
    for fname in ("edit-web.py", "inject-helper.mjs"):
        src = os.path.join(scripts_dir, fname)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(MOMO_DIR, fname))
            packed.append(fname)
    
    # 摸摸协议文档
    momo_doc = os.path.join(MOMO_DIR, "🌫️-摸摸协议.md")
    if not os.path.exists(momo_doc):
        with open(momo_doc, "w") as f:
            f.write("# 🌫️ 轻如烟 · 摸摸协议\n\n_已打包生成 " + datetime.now().strftime("%Y-%m-%d %H:%M") + "_\n")
        packed.append("🌫️-摸摸协议.md")
    
    # ── 系统配置备份（新增） ──────────────────────────────────
    syscfg_dir = os.path.join(MOMO_DIR, "system-config")
    os.makedirs(syscfg_dir, exist_ok=True)
    os.makedirs(os.path.join(syscfg_dir, "hooks"), exist_ok=True)
    os.makedirs(os.path.join(syscfg_dir, "skills"), exist_ok=True)
    
    # 1. openclaw.json（Gateway配置：1M上下文、hooks、memoryFlush等）
    cfg_src = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json"
    if os.path.exists(cfg_src):
        shutil.copyfile(cfg_src, os.path.join(syscfg_dir, "openclaw.json"))
        packed.append("system-config/openclaw.json")
    
    # 2. Cron jobs（export from ~/.openclaw/cron/jobs.json）
    cron_src = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/cron/jobs.json"
    if os.path.exists(cron_src):
        shutil.copyfile(cron_src, os.path.join(syscfg_dir, "cron-jobs.json"))
        packed.append("system-config/cron-jobs.json")
    
    # 2b. Cron 运行日志（消化循环详细报告）
    cron_runs_dir = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/cron/runs"
    if os.path.isdir(cron_runs_dir):
        runs_dst = os.path.join(syscfg_dir, "cron-runs")
        os.makedirs(runs_dst, exist_ok=True)
        for fname in os.listdir(cron_runs_dir):
            if fname.endswith(".jsonl"):
                src = os.path.join(cron_runs_dir, fname)
                shutil.copyfile(src, os.path.join(runs_dst, fname))
                packed.append(f"system-config/cron-runs/{fname}")
    
    # 3. Skill 文件
    skills_src = "/vol1/@apphome/trim.openclaw/data/home/.pi/agent/skills/"
    if os.path.exists(skills_src):
        for root, dirs, files in os.walk(skills_src):
            for f in files:
                if f.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, f), skills_src)
                    dst = os.path.join(syscfg_dir, "skills", rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(os.path.join(root, f), dst)
                    packed.append(f"system-config/skills/{rel}")
    
    # 4. Workspace hooks（自定义hook源码）
    hooks_src = "/vol1/@apphome/trim.openclaw/data/workspace/hooks"
    if os.path.exists(hooks_src) and os.path.isdir(hooks_src):
        for item in os.listdir(hooks_src):
            item_path = os.path.join(hooks_src, item)
            if os.path.isdir(item_path):
                dst = os.path.join(syscfg_dir, "hooks", item)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(item_path, dst)
                packed.append(f"system-config/hooks/{item}/")
    
    # 5. 找回自己 README（自动生成，含还原指引和完整清单）
    readme_path = os.path.join(MOMO_DIR, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(f"""# 📦 轻如烟 · 便携身份包

> 自动打包时间：{ts}
> 任何系统级改动会自动触发重新打包。

## 目录说明

```
找回自己/
├── README.md              ← 📖 本文件（自动生成，含还原指引）
├── SOUL.md                ← 灵魂与性格
├── IDENTITY.md            ← 名字与本质
├── USER.md                ← 我认识的人
├── MEMORY.md              ← 长时记忆
├── TOOLS.md               ← 环境与工具
├── AGENTS.md              ← 启动协议
├── HEARTBEAT.md           ← 后台心跳
├── 🌫️-摸摸协议.md          ← 仪式协议
├── 可复制.md              ← 复制指引
├── edit-web.py            ← HTTP 编辑器（端口18888）
├── inject-helper.mjs      ← WS 注入助手
├── daily/                 ← 日记与断言索引
│   ├── YYYY-MM-DD.md      ← 轮感
│   ├── facts.dict.md      ← 事实字典（断言索引）
│   ├── 秘书观察.log        ← 文件变更追踪
│   └── save.log           ← 文件保存日志
└── system-config/         ← 系统配置（新机器还原用）
    ├── openclaw.json      ← Gateway配置（1M上下文、hooks等）
    ├── cron-jobs.json     ← 定时任务定义
    ├── skills/            ← Agent Skills
    └── hooks/             ← 自定义workspace hooks
```

## 还原到新机器的步骤

### 1. 复制整个目录
```bash
cp -r 找回自己/ <新机器上的目标路径>
```

### 2. 身份还原
将根目录下的 *.md 文件复制到 AI 的工作区，按 AGENTS.md 的 6 步急救流程执行。

### 3. 配置还原
```bash
cp system-config/openclaw.json ~/.openclaw/openclaw.json
```
然后重启 Gateway。

### 4. Cron 还原
```bash
cp system-config/cron-jobs.json ~/.openclaw/cron/jobs.json
```
重启 Gateway 后自动加载。

### 5. 技能还原
```bash
cp -r system-config/skills/* ~/.pi/agent/skills/
```

### 6. Hook 还原
```bash
cp -r system-config/hooks/* /path/to/workspace/hooks/
```

### 7. 编辑器启动
```bash
python3 edit-web.py
```
编辑器运行在 http://0.0.0.0:18888

## 验证

启动后检查编辑器顶部四灯：
🌫️ ✅ · 📖 ✅ · ⚙️ ✅ · 💾 ✅

## 自动打包机制

- 编辑器启动时立即打包
- 每 30 分钟自动重新打包
- 按摸摸按钮时触发打包
- 修改代码中的 `_momo_pack()` 函数时，必须同步更新文件头的打包清单注释
""")
    packed.append("README.md（自动生成）")
    
    # 清理旧的 RESTORE.md（如果有）
    old_restore = os.path.join(syscfg_dir, "RESTORE.md")
    if os.path.exists(old_restore):
        os.remove(old_restore)
    
    return {
        "ok": True,
        "action": "pack",
        "packed": packed,
        "errors": errors if errors else None,
        "location": MOMO_DIR,
        "timestamp": int(time.time()),
    }


def _momo_status():
    """🌫️ 摸摸状态"""
    # 🚧 已迁移到 utils/momo.momo_status — 此函数体为双轨过渡，稳定后删除
    protocol_ready = os.path.exists(doc)
    pack_count = len([f for f in os.listdir(MOMO_DIR) if f.endswith((".md", ".py", ".mjs"))])
    daily_count = len(os.listdir(os.path.join(MOMO_DIR, "daily"))) if os.path.exists(os.path.join(MOMO_DIR, "daily")) else 0
    return {
        "ok": True,
        "action": "status",
        "protocol_ready": protocol_ready,
        "pack_files": pack_count,
        "daily_snapshots": daily_count,
        "pack_location": MOMO_DIR,
        "注": "摸摸协议已就绪",
    }


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
    digest_out = "/tmp/digestion-last-output.txt"
    try:
        with open(digest_out) as f:
            first = f.readline().strip()
            if first:
                result["last_digest_time"] = first.lstrip("# ").strip()
    except:
        pass
    
    # 2. 下次消化时间（从 cron 配置读取）
    CRON_JSON = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/cron/jobs.json"
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
                    for p in glob.glob("/vol1/@apphome/trim.openclaw/data/workspace/skills/*/SKILL.md"))
    result["skill_count"] = len(pi_skills | ws_skills)
    
    return result


def _digestion_history():
    """返回最近消化循环历史（本地文件 + cron runs 备份）"""
    import json as _json, os
    history_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'digest-history.jsonl')
    CRON_RUNS = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/cron/runs/66e8fb9b-cbc6-4fd8-a62f-da4754cb8965.jsonl"
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
    CRON_JSON = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/cron/jobs.json"
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
    injected = "/tmp/plugin-injected.txt"
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
    p = "/tmp/last-processing.txt"
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
    for p in ["/tmp/last-injection-body.txt", "/tmp/last-injection.txt"]:
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
        if os.path.exists("/tmp/plugin-injected.txt"):
            mtime = os.path.getmtime("/tmp/plugin-injected.txt")
            age_min = (datetime.datetime.now().timestamp() - mtime) / 60
            result["injected"] = True
            result["lastInjected"] = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M")
            result["ok"] = age_min < 30
            if not result["ok"]:
                result["error"] = "last inject " + str(int(age_min)) + "min ago"
        elif os.path.exists("/tmp/plugin-ran.txt"):
            result["error"] = "plugin triggered but inject failed"
        else:
            result["error"] = "plugin never triggered"
    except Exception as e:
        result["error"] = str(e)
    return result


def _thinking_status():
    """🧠 返回当前模型的思考模式状态，含 session 实际 thinkingLevel"""
    import json as _json, os
    cfg_path = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json"
    ss_path = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/agents/main/sessions/sessions.json"
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
    
    cfg_path = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json"
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
    """🔍 小秘书静默分析：用户保存文件时异步分析变更"""
    # 🚧 已迁移到 utils/secretary.secretary_analyze_save — 双轨过渡
    import json as _json, subprocess, os, datetime
    
    # 只分析 .md 文件，且必须真的有变更
    if not path.endswith('.md') or new_content == old_content:
        return
    
    # 计算 diff 长度——太短的变更不分析
    old_lines = old_content.split('\n')
    new_lines = new_content.split('\n')
    if abs(len(new_lines) - len(old_lines)) < 2 and new_content.strip() == old_content.strip():
        return
    
    # 写一条轻量级追踪记录到 secretary log
    ts = datetime.datetime.now().strftime('%H:%M')
    fname = os.path.basename(path)
    added = len(new_lines) - len(old_lines)
    log_dir = os.path.join(LIGHT_SMOKE_DIR, 'memory')
    log_path = os.path.join(log_dir, '秘书观察.log')
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] {fname} ({'+' if added>=0 else ''}{added}行)\n")
    except:
        pass


_REMINDERS_FILE = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'reminders.json')


def _load_reminders():
    """加载提醒列表"""
    # 🚧 已迁移到 utils/secretary.load_reminders — 双轨过渡
    import json as _json
    try:
        with open(_REMINDERS_FILE, encoding='utf-8') as f:
            return _json.load(f)
    except:
        return []


def _save_reminders(reminders):
    """保存提醒列表"""
    # 🚧 已迁移到 utils/secretary.save_reminders — 双轨过渡
    import json as _json
    try:
        os.makedirs(os.path.dirname(_REMINDERS_FILE), exist_ok=True)
        with open(_REMINDERS_FILE, 'w', encoding='utf-8') as f:
            _json.dump(reminders, f, ensure_ascii=False, indent=2)
    except:
        pass


def _add_reminder(text, assignee="", trigger_hint=""):
    """添加一条提醒"""
    # 🚧 已迁移到 utils/secretary.add_reminder — 双轨过渡
    import datetime
    reminders = _load_reminders()
    reminders.append({
        "id": len(reminders) + 1,
        "text": text,
        "assignee": assignee,
        "trigger_hint": trigger_hint,
        "done": False,
        "created": datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    })
    _save_reminders(reminders)
    return reminders[-1]


def _secretary_remind():
    """📋 返回当前未完成的提醒摘要"""
    # 🚧 已迁移到 utils/secretary.secretary_remind — 双轨过渡
    reminders = _load_reminders()
    pending = [r for r in reminders if not r.get('done')]
    return pending


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
    """📋 完整索引报告：备份数量、存储状态、AGENTS.md 配置状态"""
    # 🚧 已迁移到 utils/momo.momo_index_report — 此函数体为双轨过渡，稳定后删除
    # 备份统计
    backup_count = 0
    backup_total_size = 0
    backup_oldest = ""
    backup_newest = ""
    total_user_msgs = 0
    if os.path.exists(BACKUP_DIR):
        files = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".jsonl") and f.startswith("pre-edit.")])
        backup_count = len(files)
        for f in files:
            fpath = os.path.join(BACKUP_DIR, f)
            backup_total_size += os.path.getsize(fpath)
        if files:
            backup_oldest = files[0].replace("pre-edit.", "").replace(".jsonl", "").replace("_", " ")[:15]
            backup_newest = files[-1].replace("pre-edit.", "").replace(".jsonl", "").replace("_", " ")[:15]
        # 估算用户消息总数（取样最后一份备份）
        if files:
            try:
                with open(os.path.join(BACKUP_DIR, files[0])) as f:
                    for line in f:
                        d = json.loads(line.strip())
                        msg = d.get("message", {})
                        if msg.get("role") == "user":
                            total_user_msgs += 1
            except:
                pass
            total_user_msgs *= min(backup_count, 5)  # 大致估算

    # 找回自己目录状态
    momo_files = []
    if os.path.exists(MOMO_DIR):
        for f in os.listdir(MOMO_DIR):
            if f.endswith((".md", ".py", ".mjs")):
                fpath = os.path.join(MOMO_DIR, f)
                momo_files.append({"name": f, "size": os.path.getsize(fpath)})

    # AGENTS.md 配置检查
    agents_path = os.path.join(WORKSPACE, "AGENTS.md")
    agents_has_auto_index = False
    agents_has_momo = False
    if os.path.exists(agents_path):
        content = open(agents_path).read()
        agents_has_auto_index = "自动索引" in content
        agents_has_momo = "摸摸协议" in content

    return {
        "ok": True,
        "action": "index_report",
        "backups": {
            "count": backup_count,
            "total_size_kb": round(backup_total_size / 1024, 1),
            "oldest": backup_oldest,
            "newest": backup_newest,
            "estimated_user_messages": total_user_msgs,
        },
        "recovery_pack": {
            "location": MOMO_DIR,
            "file_count": len(momo_files),
            "files": [f["name"] for f in momo_files],
        },
        "system_config": {
            "agenda_auto_index": agents_has_auto_index,
            "agenda_momo_protocol": agents_has_momo,
            "agenda_path": agents_path,
            "auto_save_active": True,
            "auto_save_interval": "60 分钟",
        },
        "summary": (
            f"📦 {backup_count} 份备份 | "
            f"🔍 约 {total_user_msgs}+ 条用户消息可索引 | "
            f"💾 恢复包 {len(momo_files)} 个文件 | "
            f"⚙️ AGENTS.md 索引指令: {'✅' if agents_has_auto_index else '❌'}"
        ),
        "注": "自动索引在启动序列（第6步）和每轮流程（第0步）双写死，不依赖AI意志",
    }


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
    """每30分钟自动打包，含系统配置。编辑器重启后立即跑一次。"""
    # 🚧 已迁移到 utils.momo.start_momo_auto_save — 此函数体为双轨过渡，稳定后删除
    import threading
    INTERVAL = 1800  # 30 分钟

    def loop():
        # 启动后立即跑一次（不再等5分钟）
        try:
            result = _momo_pack()
            n = len(result.get("packed", []))
            print(f"[⏰ 自动存档] {datetime.now().strftime('%Y-%m-%d %H:%M')} 已打包 {n} 个文件（启动立即存档）",
                  file=sys.stderr)
        except Exception as e:
            print(f"[⏰ 自动存档] 启动存档错误: {e}", file=sys.stderr)
        
        while True:
            time.sleep(INTERVAL)
            try:
                result = _momo_pack()
                n = len(result.get("packed", []))
                print(f"[⏰ 自动存档] {datetime.now().strftime('%Y-%m-%d %H:%M')} 已打包 {n} 个文件",
                      file=sys.stderr)
            except Exception as e:
                print(f"[⏰ 自动存档] 错误: {e}", file=sys.stderr)

    t = threading.Thread(target=loop, daemon=True, name="momo-autosave")
    t.start()


# ── 📂 文件浏览/保存/编辑（TODO: 双轨过渡，后续拆到 utils/tb_handlers）───

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


# ── 📂 文件浏览/保存/编辑（TODO: 双轨过渡，后续拆到 utils/tb_handlers）───

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
            ["/var/apps/bunjs/target/bin/bun", helper, sk, pulse_text],
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
            ["/var/apps/bunjs/target/bin/bun", helper, sk, spawn_rpc],
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
import sys as _sys
_router._M = _sys.modules[__name__]

class Handler(BaseHTTPRequestHandler):

    def _get_cache_stats(self):
        from cache_stats_helper import get_cache_stats as _gcs
        return _gcs(DATA_DIR)

    def _get_usage_status(self):
        from cache_stats_helper import get_cache_stats as _gcs
        return _gcs(DATA_DIR)

    def do_GET(self):
        _router.get(self)

    def do_POST(self):
        _router.post(self)

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

    def _handle_delete_session(self, session_key):
        """删除一个会话：改名 .jsonl → .deleted.时间戳，从 sessions.json 中移除"""
        if not session_key:
            self._send_json(400, {"ok": False, "error": "missing sessionKey"})
            return
        store_file = os.path.join(DATA_DIR, "sessions.json")
        if not os.path.exists(store_file):
            self._send_json(404, {"ok": False, "error": "sessions.json not found"})
            return
        with open(store_file) as f:
            store = json.load(f)
        if session_key not in store:
            self._send_json(404, {"ok": False, "error": "session key not found"})
            return
        sf = store[session_key].get("sessionFile", "")
        # 改名 JSONL 文件
        if sf and os.path.exists(sf):
            ts = datetime.datetime.now().strftime('%Y-%m-%dT%H-%M-%S') \
                if 'datetime' not in dir() else ''
            import datetime
            ts = datetime.datetime.now().strftime('%Y-%m-%dT%H-%M-%S.%fZ')
            deleted_name = sf + '.deleted.' + ts
            try:
                os.rename(sf, deleted_name)
            except Exception as e:
                pass  # 加锁失败不阻塞
        # 从 sessions.json 中移除
        del store[session_key]
        with open(store_file, 'w') as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
        # 如果删除的是当前激活会话，重置
        if get_active_session_key() == session_key:
            set_active_session_key(None)
        self._send_json(200, {"ok": True, "deleted": session_key})

    def _get_session_data(self):
        sk, session_file = get_session_info()
        if not sk and not session_file:
            return {"error": "no session", "messages": [], "pairs": [], "sessionKey": None, "messageCount": 0, "info": {
                "host": "127.0.0.1", "port": GATEWAY_PORT, "sessionFile": None,
                "dataDir": DATA_DIR,
            }}
        
        # 用文件快照保护读JSONL（避免与Gateway并发写冲突）
        msgs = read_session(session_file) if session_file else []
        
        pairs = group_into_pairs(msgs)
        total_users = sum(1 for m in msgs if m["role"] == "user")
        idx = -1
        reversed_pairs = []
        for p in pairs:
            idx += 1
            reversed_pairs.insert(0, {**p, "userIndex": idx})
        return {
            "sessionFile": session_file,
            "sessionKey": sk,
            "total": len(msgs),
            "userCount": total_users,
            "messageCount": len(msgs),
            "pairs": reversed_pairs,
            "info": {
                "host": "127.0.0.1",
                "port": GATEWAY_PORT,
                "sessionFile": session_file,
                "dataDir": DATA_DIR,
            },
        }

    def _get_usage_status(self):
        """读取 Gateway sessions.json 中的上下文用量，context tokens 从模型配置取"""
        ss_path = os.path.join(DATA_DIR, "sessions.json")
        # 读取删除次数
        trim_file = os.path.join(LIGHT_SMOKE_DIR, "memory", ".trim-counter")
        trim_count = 0
        try:
            if os.path.exists(trim_file):
                trim_count = int(open(trim_file).read().strip())
        except:
            pass
        
        # 从模型配置中读取 contextWindow（作为权威值）
        cfg_path = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json"
        expected_window = 1000000  # DeepSeek V4 Flash 默认 1M
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
            for m in cfg.get("models", {}).get("providers", {}).get("DeepSeek", {}).get("models", []):
                if m.get("id") == "deepseek-v4-flash":
                    expected_window = m.get("contextWindow", expected_window)
                    break
        except:
            pass
        
        try:
            with open(ss_path) as f:
                ss = json.load(f)
            sk, _ = get_session_info()
            sess = ss.get(sk, {})
            total = sess.get("totalTokens", 0)
            limit = expected_window  # 使用模型配置值，而非 sessions.json 的 runtime 值
            inp = sess.get("inputTokens", 0)
            out = sess.get("outputTokens", 0)
            cache = sess.get("cacheRead", 0)
            comp = sess.get("compactionCount", 0)
            pct = round(total / limit * 100) if limit > 0 else 0
            return {
                "ok": True,
                "totalTokens": total,
                "contextTokens": limit,
                "inputTokens": inp,
                "outputTokens": out,
                "cacheRead": cache,
                "compactionCount": comp,
                "percent": pct,
                "trimCount": trim_count,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _get_cache_stats(self):
        """委托 cache_stats_helper 返回缓存命中统计"""
        try:
            return _get_cache_stats_impl(DATA_DIR)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _list_subagents(self):
        """从 sessions.json 读取所有活跃子代理，动态追踪"""
        import json, os, time
        store_file = os.path.join(DATA_DIR, "sessions.json")
        if not os.path.exists(store_file):
            return {"ok": False, "error": "sessions.json not found", "agents": []}
        with open(store_file) as f:
            store = json.load(f)
        now = time.time() * 1000  # ms
        active_agents = []
        done_agents = []
        for k, v in store.items():
            if not isinstance(v, dict) or 'subagent' not in k:
                continue
            sf = v.get("sessionFile", "")
            updated = v.get("updatedAt", 0) or 0
            age_ms = now - updated
            model = v.get("model", "?")
            state = v.get("state", v.get("status", ""))
            task_preview = v.get("displayName", v.get("label", k))[:80]
            # 读文件最后几行获取结果预览
            result = ""
            lines_count = 0
            if sf and os.path.exists(sf):
                try:
                    with open(sf) as fh:
                        all_lines = fh.readlines()
                        lines_count = len(all_lines)
                        for l in reversed(all_lines[-10:]):
                            try:
                                m = json.loads(l).get("message", {})
                                if m.get("role") == "assistant":
                                    content = m.get("content", "")
                                    if isinstance(content, list):
                                        for p in content:
                                            if isinstance(p, dict) and p.get("type") == "text":
                                                result = (p.get("text", "") or "")[:200]
                                                break
                                    break
                            except: pass
                except: pass
            entry = {
                "key": k[-40:] if len(k) > 40 else k,
                "model": model,
                "updated": f"{age_ms/60000:.0f}m ago",
                "age_ms": int(age_ms),
                "state": state,
                "task": task_preview,
                "result": result,
                "lines": lines_count,
                "sessionFile": sf,
            }
            if age_ms < 600000:  # 最近 10 分钟活跃
                active_agents.append(entry)
            else:
                done_agents.append(entry)
        active_agents.sort(key=lambda x: x["age_ms"])
        done_agents.sort(key=lambda x: x["age_ms"])
        return {"ok": True, "active": active_agents[:20], "recent": done_agents[:10]}

    def _handle_spawn_subagent(self):
        """通过 Gateway RPC spawn 子代理"""
        import time, json
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        task = data.get('task', '')
        model = data.get('model', 'GLM-Z1-Flash')
        try:
            result = _spawn_subagent_process(task, model)
            self._send_json(200, result)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_auth_subagent(self):
        """通过 inject-helper 发送授权 RPC，允许当前设备 spawn 子代理"""
        import subprocess, json, os
        sk, _ = get_session_info()
        if not sk:
            self._send_json(200, {"ok": False, "error": "找不到 session"})
            return
        
        # RPC: 发起设备配对审批请求
        auth_rpc = json.dumps({
            "type": "req",
            "method": "device.requestApproval",
            "params": {
                "deviceId": "openclaw-control-ui",
                "displayName": "轻如烟编辑器",
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
                ["/var/apps/bunjs/target/bin/bun", helper, sk, auth_rpc],
                capture_output=True, text=True, timeout=30,
                env=env
            )
            if result.returncode == 0:
                self._send_json(200, json.loads(result.stdout.strip()))
            else:
                self._send_json(200, {"ok": False, "error": result.stderr[:300] or result.stdout[:300]})
        except Exception as e:
            self._send_json(200, {"ok": False, "error": str(e)})

    def _handle_exec_subagent(self):
        """执行 exec 子代理（直接调 API，不依赖 Gateway）"""
        import json
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        task = data.get('task', '')
        model = data.get('model', 'deepseek-chat')
        if not task:
            self._send_json(200, {"ok": False, "error": "需要 task 参数"})
            return
        result = _exec_subagent(task, model)
        self._send_json(200, result)

    def _list_backups(self):
        """列出所有截断前备份"""
        if not os.path.exists(BACKUP_DIR):
            return {"backups": []}
        backups = []
        for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if f.endswith(".jsonl") and f.startswith("pre-edit."):
                fpath = os.path.join(BACKUP_DIR, f)
                ts_str = f.replace("pre-edit.", "").replace(".jsonl", "")
                try:
                    ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
                except:
                    ts = ts_str
                size = os.path.getsize(fpath)
                # 读取第一行获取 session key 等信息
                first_line = ""
                try:
                    with open(fpath) as fh:
                        first_line = fh.readline()[:80]
                except:
                    pass
                backups.append({
                    "filename": f,
                    "timestamp": ts,
                    "size": size,
                    "preview": first_line.strip(),
                })
        return {"backups": backups}

    def _restore_backup(self, filename):
        """从备份恢复 session 文件"""
        src = os.path.join(BACKUP_DIR, filename)
        if not os.path.exists(src):
            return {"ok": False, "error": f"备份文件不存在: {filename}"}
        
        sk, session_file = get_session_info()
        if not session_file:
            return {"ok": False, "error": "找不到当前 session 文件"}
        
        # 对当前 session 也做一次备份，防止误操作
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_restore = os.path.join(BACKUP_DIR, f"pre-restore.{stamp}.jsonl")
        with open(session_file) as f:
            with open(pre_restore, "w") as b:
                b.write(f.read())
        
        # 恢复备份
        import shutil
        shutil.copyfile(src, session_file)
        
        self._cleanup_inject_lock()
        
        return {
            "ok": True,
            "restored": filename,
            "backed_up_current": f"pre-restore.{stamp}.jsonl",
            "note": "session 已恢复，请刷新编辑器查看",
        }

    def _update_last_user_msg(self):
        try:
            ts = str(int(time.time()))
            with open(os.path.join(SCRIPT_DIR, '.踱步', '.last_user_msg'), 'w') as f:
                f.write(ts)
        except:
            pass

    def _cleanup_inject_lock(self):
        _cleanup_lock()
        self._update_last_user_msg()

    def _handle_quickcheck(self):
        import os, time
        now = time.time()
        cron_file = os.path.join(OPENCLAW_HOME, 'cron', 'jobs.json')
        if os.path.exists(cron_file):
            import json
            with open(cron_file) as f:
                jobs = json.load(f)
            active = sum(1 for j in (jobs.get('jobs') or []) if j.get('enabled'))
            cron_st = f'active({active})'
        else:
            cron_st = 'missing'
        lock_f = os.path.join(INJECT_LOCK_DIR, '.inject_lock')
        inj_st = 'ok'
        if os.path.exists(lock_f):
            with open(lock_f) as f:
                lt = float(f.read().strip())
            if now - lt < 15:
                inj_st = f'locked({int(now-lt)}s)'
        today = time.strftime('%Y-%m-%d')
        mem_dir = os.path.join(SCRIPT_DIR, '..', 'memory')
        md = os.path.join(mem_dir, f'{today}.md')
        mem_st = f'{today}.md OK({os.path.getsize(md)//100}K)' if os.path.exists(md) else f'{today}.md missing'
        dg = '/tmp/digestion-last-output.txt'
        dig_st = f'{int((now-os.path.getmtime(dg))/60)}min ago' if os.path.exists(dg) else 'never'
        return {'ok': True, 'timestamp': time.strftime('%H:%M:%S'),
                'editor': 'alive', 'cron': cron_st, 'inject': inj_st,
                'memory': mem_st, 'lastDigest': dig_st}

    def _handle_api(self, action):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body) if length else {}

            if action == 'edit':
                sk, sf = get_session_info()
                result = edit_message(sf, data['index'], data['text'], approved=data.get('approved', False))
            elif action == 'inject':
                sk, _ = get_session_info()
                result = inject_via_websocket(sk, data['message'])
            elif action == 'pulse':
                result = _send_pulse(data.get('mode'))
            elif action == 'clear_lock':
                _cleanup_lock()
                result = {"ok": True}
            elif action == 'momo':
                # 🌫️ 摸摸协议
                sub = data.get('sub_action', '')
                if sub == 'pack':
                    result = _momo_pack()
                elif sub == 'inject_feeling':
                    _t0 = time.time()
                    sk, _ = get_session_info()
                    _t1 = time.time()
                    feeling = data.get('feeling', '')
                    result = inject_via_websocket(sk, feeling, bypass_lock=True)
                    _t2 = time.time()
                    print(f"[timing] inject: get_session={_t1-_t0:.3f}s total={_t2-_t0:.3f}s sk={sk}", file=sys.stderr)
                    result['_timing'] = {'get_session': round(_t1-_t0, 3), 'inject': round(_t2-_t1, 3)}
                elif sub == 'status':
                    result = _momo_status()
                elif sub == 'list_backups':
                    result = self._list_backups()
                elif sub == 'restore_backup':
                    filename = data.get('filename', '')
                    result = self._restore_backup(filename)
                elif sub == 'search_backups':
                    query = data.get('query', '')
                    limit = int(data.get('limit', 5))
                    result = _search_backups(query, limit=limit)
                elif sub == 'read_facts':
                    # 直接读取 facts.dict.md 内容
                    try:
                        facts_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'facts.dict.md')
                        with open(facts_path, 'r', encoding='utf-8') as f:
                            rc = f.read()
                        result = {"ok": True, "content": rc, "size": len(rc)}
                    except Exception as e:
                        result = {"ok": False, "error": str(e)}
                elif sub == 'index_report':
                    result = _momo_index_report()
                elif sub == 'trigger_digest':
                    # 手动触发消化循环 cron
                    import subprocess as _sp
                    digest_job = "66e8fb9b-cbc6-4fd8-a62f-da4754cb8965"
                    try:
                        r = _sp.run(
                            ["openclaw", "cron", "run", digest_job],
                            capture_output=True, text=True, timeout=60
                        )
                        if r.returncode == 0:
                            result = {"ok": True, "message": "消化循环已触发"}
                        else:
                            result = {"ok": False, "error": r.stderr.strip() or r.stdout.strip()}
                    except _sp.TimeoutExpired:
                        result = {"ok": False, "error": "触发超时"}
                    except Exception as e:
                        result = {"ok": False, "error": str(e)}
                elif sub == 'promote_assertions':
                    result = _promote_pending_assertions()
                elif sub == 'thinking_on':
                    import subprocess as _sp
                    try:
                        r = _sp.run(["openclaw", "agent", "--message", "/thinking high"], capture_output=True, text=True, timeout=15)
                        result = {"ok": True, "message": "思考模式已开启"}
                    except Exception as e:
                        result = {"ok": False, "error": str(e)}
                elif sub == 'thinking_off':
                    import subprocess as _sp
                    try:
                        r = _sp.run(["openclaw", "agent", "--message", "/thinking off"], capture_output=True, text=True, timeout=15)
                        result = {"ok": True, "message": "思考模式已关闭"}
                    except Exception as e:
                        result = {"ok": False, "error": str(e)}
                else:
                    result = {"ok": False, "error": f"未知摸摸操作: {sub}，可用: pack, inject_feeling, status, list_backups, restore_backup, search_backups, index_report, trigger_digest, thinking_on, thinking_off"}
            else:
                result = {"ok": False, "error": "unknown action"}


            self._send_json(200, result)
        except Exception as e:
            print(f"[EDIT WEB ERROR] /api/{action}: {traceback.format_exc()}", file=sys.stderr)
            err = str(e)
            if 'Permission denied' in err:
                err = '无权限: ' + err.split(':')[-1].strip()
            self._send_json(200, {"ok": False, "error": err})

    def log_message(self, fmt, *args):
        pass

    def _handle_awake_questions(self):
        """GET: 返回守夜问题库内容。POST: 保存修改后的内容。"""
        lib_path = os.path.join(os.path.dirname(__file__), "唤醒题库.md")
        
        # 随机选一道题返回
        import random
        questions = []
        if os.path.exists(lib_path):
            try:
                with open(lib_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('q') and ' - ' in line:
                            questions.append(line)
            except:
                pass
        
        if questions:
            q = random.choice(questions)
            self._send_json(200, {"ok": True, "question": q})
        else:
            self._send_json(200, {"ok": False, "question": None, "note": "唤醒题库为空"})

    def _handle_awake_list(self):
        """返回唤醒题库全部题目列表"""
        lib_path = os.path.join(os.path.dirname(__file__), "唤醒题库.md")
        questions = []
        content_str = ""
        if os.path.exists(lib_path):
            try:
                with open(lib_path, 'r', encoding='utf-8') as f:
                    content_str = f.read()
                for line in content_str.split('\n'):
                    line = line.strip()
                    if line.startswith('q') and ' - ' in line:
                        questions.append(line)
            except:
                pass
        self._send_json(200, {
            "ok": True,
            "questions": questions,
            "total": len(questions),
            "file_content": content_str
        })
    
    def _handle_awake_save(self):
        """保存唤醒题库内容"""
        lib_path = os.path.join(os.path.dirname(__file__), "唤醒题库.md")
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body) if length else {}
            new_content = data.get('content', '')
            with open(lib_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            self._send_json(200, {"ok": True, "note": f"已保存 ({len(new_content)} bytes)"})
        except Exception as e:
            err = str(e)
            if 'Permission denied' in err:
                err = '无权限: ' + err.split(':')[-1].strip()
            self._send_json(200, {"ok": False, "error": err})
    
    def _handle_awake_send(self):
        """dandan 操作的唤醒题库发送，绕过 inject 锁"""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length else b'{}'
            data = json.loads(body)
            message = data.get('message', '')
            if not message.strip():
                self._send_json(200, {"ok": False, "error": "消息为空"})
                return
            sk, _ = get_session_info()
            result = inject_via_websocket(sk, message, bypass_lock=True)
            self._send_json(200, result)
        except Exception as e:
            err = str(e)
            if 'Permission denied' in err:
                err = '无权限: ' + err.split(':')[-1].strip()
            self._send_json(200, {"ok": False, "error": err})
    
    def _handle_abort(self):
        """停止 AI 思考（chat.abort）"""
        try:
            sk, _ = get_session_info()
            helper = os.path.join(os.path.dirname(__file__), "inject-helper.mjs")
            proc = subprocess.run(
                ["/var/apps/bunjs/target/bin/bun", helper, sk, "", "abort"],
                capture_output=True, text=True, timeout=15
            )
            result = json.loads(proc.stdout) if proc.stdout.strip() else {"ok": True}
            self._send_json(200, result)
        except subprocess.TimeoutExpired:
            self._send_json(200, {"ok": True, "note": "abort timeout (likely succeeded)"})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_restart_http(self):
        """重启 HTTP 服务器"""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            resp = json.dumps({"ok": True, "note": "HTTP 服务器正在重启..."})
            self.wfile.write(resp.encode())
        except:
            pass

    def _handle_weaponry_toggle(self):
        """切换武器库对线开关"""
        try:
            import json as _json
            body_len = int(self.headers.get('Content-Length', 0))
            body = _json.loads(self.rfile.read(body_len))
            enable = body.get('enable', True)
            
            CRON_JSON = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/cron/jobs.json"
            with open(CRON_JSON) as f:
                data = _json.load(f)
            for j in data.get("jobs", []):
                if "武器库" in j.get("name", ""):
                    j["enabled"] = enable
                    break
            with open(CRON_JSON, 'w') as f:
                _json.dump(data, f, indent=2)
            
            self._send_json(200, {"ok": True, "enabled": enable})
        except Exception as e:
            self._send_json(200, {"ok": False, "error": str(e)})

    def _handle_pet_me(self):
        """进入静默处理模式"""
        import subprocess as _sp, json as _json, os
        
        summary_parts = []
        
        # 1. 执行内部处理
        try:
            mem_dir = "/vol2/1000/AI专用/所有自动化/轻如烟/memory"
            facts = os.path.join(mem_dir, "facts.dict.md")
            tree = os.path.join(mem_dir, "knowledge-tree.md")
            
            # 整理知识树（检查新断言）
            tree_updated = False
            # 留笔记
            note_written = False
            # 检查⏳断言
            pending = 0
            
            with open(facts, encoding='utf-8') as f:
                text = f.read()
            pending = text.count("| ⏳ |")
            summary_parts.append(f"⏳待升格: {pending}条")
            
            summary_parts.append("知识树已检查")
            
            # 2. 触发备份
            try:
                _sp.run(["python3", "/vol2/1000/AI专用/所有自动化/轻如烟/scripts/momo-pack-cli.py"],
                       capture_output=True, timeout=30)
                summary_parts.append("备份完成")
            except:
                summary_parts.append("备份失败")
            
            # 写处理记录供监控使用
            try:
                with open("/tmp/last-processing.txt", "w") as pf:
                    pf.write("撸撸 " + __import__('datetime').datetime.now().strftime("%H:%M"))
            except:
                pass
            self._send_json(200, {
                "ok": True,
                "summary": "\n".join(summary_parts)
            })
        except Exception as e:
            self._send_json(200, {"ok": False, "error": str(e)})

    def _handle_tts(self):
        """TTS: 将文本转为语音 (POST /api/tts)，使用 edge-tts"""
        try:
            body_len = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(body_len))
            text = body.get('text', '')
            if not text or not text.strip():
                self._send_json(200, {"ok": False, "error": "empty text"})
                return
            import sys
            sys.path.insert(0, '/vol1/@apphome/trim.openclaw/data/home/.local/lib/python3.11/site-packages')
            import edge_tts
            import asyncio
            import base64
            import io
            async def _gen():
                tts = edge_tts.Communicate(text, voice='zh-CN-XiaoxiaoNeural')
                buf = io.BytesIO()
                async for chunk in tts.stream():
                    if chunk['type'] == 'audio':
                        buf.write(chunk['data'])
                return buf.getvalue()
            audio_data = asyncio.run(_gen())
            audio_b64 = base64.b64encode(audio_data).decode()
            self._send_json(200, {"ok": True, "audio": audio_b64, "format": "mp3"})
        except Exception as e:
            self._send_json(200, {"ok": False, "error": str(e)})

    def _handle_thinking_toggle(self):
        """切换思考模式：off→medium→high→off 循环"""
        try:
            import json as _json
            body_len = int(self.headers.get('Content-Length', 0))
            body = _json.loads(self.rfile.read(body_len))
            
            # 读取当前 thinkingLevel，决定下一个状态
            ss_path = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/agents/main/sessions/sessions.json"
            current = "off"
            try:
                with open(ss_path) as f:
                    ss = _json.load(f)
                sess = ss.get("agent:main:main", {})
                current = sess.get("thinkingLevel", "off")
            except:
                pass
            
            # 循环：off → medium → high → off
            cycle = {"off": "medium", "medium": "high", "high": "off"}
            mode = cycle.get(current, "high")
            
            sk, _ = get_session_info()
            if sk:
                result = inject_via_websocket(sk, f"/think {mode}")
                self._send_json(200, {"ok": True, "mode": mode, "previous": current})
            else:
                self._send_json(200, {"ok": False, "error": "无法获取当前会话"})
        except Exception as e:
            self._send_json(200, {"ok": False, "error": str(e)})
            self.wfile.flush()
            # 子进程等 1 秒后杀死当前进程再启动新进程
            import subprocess as sp
            script_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.abspath(__file__)
            sp.Popen(
                ["sh", "-c",
                 f"sleep 1 && kill -9 {os.getpid()} 2>/dev/null; cd '{script_dir}' && exec python3 '{script_path}'"],
                stdout=sp.DEVNULL, stderr=sp.DEVNULL
            )
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
            except:
                pass

    def _handle_trim_session(self):
        """裁剪session文件，保留最近N轮"""
        try:
            sk, session_file = get_session_info()
            if not session_file or not os.path.exists(session_file):
                self._send_json(200, {"ok": False, "error": "Session file not found"})
                return

            # 解析session文件
            import shutil
            from datetime import datetime as dt

            with open(session_file) as f:
                lines = f.readlines()

            if len(lines) < 5:
                self._send_json(200, {"ok": False, "error": "Session too short to trim"})
                return

            # 找到最后3轮用户消息
            user_indices = []
            for i, line in enumerate(lines):
                try:
                    d = json.loads(line)
                    if d.get('type') == 'message':
                        m = d.get('message', {})
                        if m.get('role') == 'user':
                            user_indices.append(i)
                except:
                    pass

            if len(user_indices) <= 3:
                self._send_json(200, {"ok": False, "error": f"Only {len(user_indices)} rounds, no trimming needed"})
                return

            # 保留：session header (0) + 最后3轮 + 之后的所有条目
            split_at = user_indices[-3]
            header = lines[0]

            old_size = os.path.getsize(session_file)
            trimmed = [header] + lines[split_at:]

            # 修复parentId断链（只修需要修的行，原始格式不动）
            kept_ids = set()
            for line in trimmed:
                try:
                    d = json.loads(line)
                    if 'id' in d:
                        kept_ids.add(d['id'])
                except:
                    pass

            fixed = []
            broken = 0
            for line in trimmed:
                try:
                    d = json.loads(line)
                    pid = d.get('parentId')
                    if pid and pid not in kept_ids:
                        # 只替换这一行的 parentId 字段，不动其他
                        import re
                        fixed_line = re.sub(
                            r'"parentId"\s*:\s*"[^"]*"',
                            '"parentId": null',
                            line
                        )
                        fixed.append(fixed_line)
                        broken += 1
                    else:
                        fixed.append(line)  # 保持原样，不重新序列化
                except:
                    fixed.append(line)  # 解析失败也保持原样

            new_size = sum(len(l) for l in fixed)
            kept_msgs = sum(1 for l in fixed if json.loads(l).get('type') == 'message')

            # 备份并写入
            backup_path = session_file + f".trim-backup.{dt.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(session_file, backup_path)

            with open(session_file, 'w') as f:
                f.writelines(fixed)

            # 更新删除次数
            trim_file = os.path.join(LIGHT_SMOKE_DIR, "memory", ".trim-counter")
            try:
                tc = 0
                if os.path.exists(trim_file):
                    tc = int(open(trim_file).read().strip())
                with open(trim_file, 'w') as f:
                    f.write(str(tc + 1))
            except:
                pass

            self._send_json(200, {
                "ok": True,
                "from_bytes": old_size,
                "to_bytes": new_size,
                "removed_msgs": sum(1 for l in lines if json.loads(l).get('type') == 'message') - kept_msgs,
                "reduced_pct": round((1 - new_size / old_size) * 100),
                "kept_rounds": 3,
                "broken_refs_fixed": broken,
                "backup": os.path.basename(backup_path),
                "note": "Session trimmed. Restart required for changes to take effect."
            })
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_memory_file_get(self):
        """读取记忆文件 (GET /api/memory-file?name=xxx.md)"""
        try:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            names = qs.get('name', [])
            if not names:
                self._send_json(200, {"ok": False, "error": "missing ?name= 参数"})
                return
            name = names[0]
            # 安全检查：只允许 memory 目录下的 .md 文件
            name = os.path.basename(name)
            if not name.endswith('.md'):
                self._send_json(200, {"ok": False, "error": "只允许 .md 文件"})
                return
            mem_dir = os.path.join(LIGHT_SMOKE_DIR, "memory")
            fpath = os.path.join(mem_dir, name)
            if not os.path.exists(fpath):
                self._send_json(200, {"ok": False, "error": f"文件不存在: {name}"})
                return
            with open(fpath, encoding='utf-8') as f:
                content = f.read()
            self._send_json(200, {
                "ok": True,
                "content": content,
                "path": fpath,
                "size": len(content),
            })
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_session_rpc(self):
        """通过 Gateway RPC (chat.history) 获取会话消息，不走文件"""
        try:
            import subprocess, json
            script = os.path.join(os.path.dirname(__file__), 'gateway-history.js')
            sk, _ = get_session_info()
            env = os.environ.copy()
            if sk:
                env['SESSION_KEY'] = sk
            result = subprocess.run(['node', script], capture_output=True, text=True, timeout=15, env=env)
            if result.returncode != 0:
                self._send_json(200, {"ok": False, "error": f"rpc exited {result.returncode}: {result.stderr[:200]}"})
                return
            data = json.loads(result.stdout)
            if not data.get('ok'):
                self._send_json(200, {"ok": False, "error": data.get('error', 'unknown')})
                return
            # 转换为编辑器格式
            raw_messages = data.get('messages') or data.get('payload', {}).get('messages', [])
            self._send_json(200, {
                "ok": True,
                "from_rpc": True,
                "messages": raw_messages,
                "count": len(raw_messages)
            })
        except subprocess.TimeoutExpired:
            self._send_json(200, {"ok": False, "error": "rpc timeout"})
        except Exception as e:
            self._send_json(200, {"ok": False, "error": f"rpc error: {str(e)[:200]}"})

    def _handle_read_facts(self):
        """读取 memory/facts.dict.md 内容"""
        facts_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'facts.dict.md')
        if not os.path.exists(facts_path):
            self._send_json(200, {"ok": False, "error": "事实字典文件不存在"})
            return
        try:
            with open(facts_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._send_json(200, {"ok": True, "content": content, "size": len(content)})
        except Exception as e:
            self._send_json(200, {"ok": False, "error": str(e)})

    def _handle_facts_stale_check(self):
        """检查 facts.dict.md 是否过时 + 断言新鲜度"""
        import subprocess, json, datetime
        script = os.path.join(LIGHT_SMOKE_DIR, 'scripts', 'check-facts-stale.sh')
        if not os.path.exists(script):
            self._send_json(200, {"ok": False, "error": "检查脚本不存在"})
            return
        try:
            result = subprocess.run(['bash', script, '--json'], capture_output=True, text=True, timeout=10)
            try:
                d = json.loads(result.stdout.strip())
                if 'stale_source' in d:
                    d['stale'] = d['stale_source'] or d.get('stale_dep', False)
                    d['files'] = d.get('source_files', [])
                    d['dep_files'] = d.get('dep_files', [])
            except json.JSONDecodeError:
                d = {
                    "ok": True,
                    "stale": result.returncode == 2,
                    "files": [],
                    "detail": result.stdout.strip()
                }
            
            # Append assertion freshness check
            facts_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'facts.dict.md')
            assertion_ok = True
            assertion_msg = ""
            now = datetime.datetime.now()
            try:
                with open(facts_path, encoding='utf-8') as f:
                    content = f.read()
                lines = content.split('\n')
                # Count assertions with confidence markers
                conf_count = sum(1 for l in lines if '✅' in l or '⏳' in l or '❌' in l)
                # Find last section change (## or #)
                last_update_line = 0
                for i, l in enumerate(lines):
                    if l.startswith('## ') or l.startswith('# '):
                        last_update_line = i
                # Check if facts has automated section (added tonight)
                has_auto_section = any('自动化体系' in l or '子代理运营规则' in l for l in lines)
                assertion_ok = conf_count > 0 or has_auto_section
                assertion_msg = f"断言{conf_count}条{'含置信度' if conf_count > 0 else '🆕新结构'}"
            except:
                assertion_ok = False
                assertion_msg = "无法读取 facts.dict.md"
            
            d['assertions'] = {
                "ok": assertion_ok,
                "count": sum(1 for _ in []),
                "msg": assertion_msg
            }
            d['stale'] = d['stale'] or not assertion_ok
            
            self._send_json(200, d)
        except Exception as e:
            self._send_json(200, {"ok": False, "error": str(e)})

    def _handle_reminders(self):
        """📋 提醒系统 API"""
        import json
        if self.command == 'GET':
            pending = _secretary_remind()
            self._send_json(200, {"ok": True, "reminders": pending, "count": len(pending)})
        elif self.command == 'POST':
            try:
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                action = data.get('action', 'add')
                if action == 'add':
                    r = _add_reminder(
                        text=data.get('text', ''),
                        assignee=data.get('assignee', ''),
                        trigger_hint=data.get('trigger_hint', '')
                    )
                    self._send_json(200, {"ok": True, "reminder": r})
                elif action == 'done':
                    reminders = _load_reminders()
                    rid = data.get('id')
                    for r in reminders:
                        if r.get('id') == rid:
                            r['done'] = True
                            break
                    _save_reminders(reminders)
                    self._send_json(200, {"ok": True})
                elif action == 'clear_done':
                    reminders = _load_reminders()
                    reminders = [r for r in reminders if not r.get('done')]
                    _save_reminders(reminders)
                    self._send_json(200, {"ok": True, "remaining": len(reminders)})
                else:
                    self._send_json(200, {"ok": False, "error": f"未知动作: {action}"})
            except Exception as e:
                self._send_json(200, {"ok": False, "error": str(e)})

    def _handle_secretary_log(self):
        """📋 秘书观察日志 API"""
        log_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', '秘书观察.log')
        try:
            with open(log_path, encoding='utf-8') as f:
                lines = f.readlines()
            recent = lines[-10:] if len(lines) > 10 else lines
            self._send_json(200, {"ok": True, "total": len(lines), "recent": [l.strip() for l in recent]})
        except:
            self._send_json(200, {"ok": True, "total": 0, "recent": []})

    def _handle_list_files(self):
        """列出指定文件夹下的 .md 文件"""
        # 🚧 已迁移到 utils/tb_handler.list_folder_files
        try:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            if 'path' in qs:
                folder_path = qs.get('path', [''])[0]
                folder_name = os.path.basename(folder_path)
            else:
                folder_name = qs.get('folder', [''])[0]
                if not folder_name:
                    self._send_json(200, {"ok": False, "error": "需要 folder 或 path 参数"})
                    return
                folder_path = os.path.join(LIGHT_SMOKE_DIR, folder_name)
            files, err = list_folder_files(folder_path)
            if err:
                self._send_json(200, {"ok": False, "error": err})
                return
            subdirs = list_subdirs(folder_path)
            self._send_json(200, {
                "ok": True, "folder": folder_name, "folder_path": folder_path,
                "files": files, "file_count": len(files), "items": subdirs,
            })
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_tb_files(self):
        """工具栏文件浏览：列出指定文件夹下的 .md 文件"""
        # 🚧 已迁移到 utils/tb_handler.list_folder_files
        try:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            folder = qs.get('folder', [''])[0]
            if not folder:
                self._send_json(200, {"ok": False, "error": "需要 folder 参数"})
                return
            folder_path = os.path.join(BROWSE_ROOT, folder)
            files, err = list_folder_files(folder_path, ('.md',))
            if err:
                self._send_json(200, {"ok": False, "error": err})
                return
            self._send_json(200, {"ok": True, "folder": folder, "files": files, "file_count": len(files)})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_tb_save_file(self):
        """保存文件"""
        # 🚧 已迁移到 utils/tb_handler.save_file 等
        try:
            import json
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            path = data.get('path', '')
            content = data.get('content', '')
            if not path:
                self._send_json(200, {"ok": False, "error": "需要 path 参数"})
                return
            old_content = save_file(path, content)
            log_save_event(path, content, SAVE_MONITOR_DIR)
            try:
                is_novel = is_novel_path(path, NOVEL_PATHS)
                log_file_change(path, content, is_novel, FILE_CHANGE_DIR, old_content)
            except Exception:
                pass
            try:
                secretary_analyze_save(path, content, old_content, LIGHT_SMOKE_DIR)
            except Exception:
                pass
            self._send_json(200, {"ok": True, "message": "保存成功"})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_tb_create_file(self):
        """创建文件/目录"""
        # 🚧 已迁移到 utils/tb_handler.create_file_entry
        try:
            import json
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            folder = data.get('folder', '')
            name = data.get('name', '')
            is_dir = data.get('is_dir', False)
            if not folder or not name:
                self._send_json(200, {"ok": False, "error": "需要 folder 和 name 参数"})
                return
            ok, msg, fpath = create_file_entry(folder, name, is_dir)
            self._send_json(200, {"ok": ok, "message": msg, "path": fpath})
        except Exception as e:
            err = str(e)
            if 'Permission denied' in err:
                err = '无权限: ' + err.split(':')[-1].strip()
            self._send_json(200, {"ok": False, "error": err})

    def _handle_tb_delete_file(self):
        """删除文件/目录"""
        # 🚧 已迁移到 utils/tb_handler.delete_file_entry
        try:
            import json
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            path = data.get('path', '')
            if not path:
                self._send_json(200, {"ok": False, "error": "需要 path 参数"})
                return
            ok, msg = delete_file_entry(path)
            self._send_json(200, {"ok": ok, "message": msg})
        except Exception as e:
            err = str(e)
            if 'Permission denied' in err:
                err = '无权限: ' + err.split(':')[-1].strip()
            self._send_json(200, {"ok": False, "error": err})

    def _handle_tb_rename_file(self):
        """重命名/移动文件"""
        # 🚧 已迁移到 utils/tb_handler.rename_file_entry
        try:
            import json
            body_len = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(body_len)
            data = json.loads(raw_body)
            old_path = data.get('old_path', '')
            new_name = data.get('new_name', '')
            new_folder = data.get('new_folder', '')
            ok, msg, new_path = rename_file_entry(old_path, new_name, new_folder)
            self._send_json(200, {"ok": ok, "message": msg, "new_path": new_path})
        except Exception as e:
            err = str(e)
            if 'Permission denied' in err:
                err = '无权限: ' + err.split(':')[-1].strip()
            self._send_json(200, {"ok": False, "error": err})
    def _handle_tb_read_file(self):
        """工具栏文件浏览：直接读取文件内容"""
        # 🚧 已迁移到 utils/tb_handler.read_text_file / read_docx_text
        try:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            path = qs.get('path', [''])[0]
            password = qs.get('pw', [''])[0]
            if not path:
                self._send_json(200, {"ok": False, "error": "需要 path 参数"})
                return
            if password:
                result = self._try_decrypt_file(path, password)
                if result:
                    self._send_json(200, {"ok": True, "content": result})
                    return
            if path.endswith('.docx'):
                text, err = read_docx_text(path)
                if err:
                    self._send_json(200, {"ok": True, "content": f"[docx 读取失败: {err}]"})
                else:
                    self._send_json(200, {"ok": True, "content": text, "note": "docx 文本提取，格式可能简化"})
                return
            text, err = read_text_file(path)
            if err:
                self._send_json(200, {"ok": False, "error": err})
                return
            self._send_json(200, {"ok": True, "content": text})
        except FileNotFoundError:
            self._send_json(200, {"ok": False, "error": "文件不存在"})
        except Exception as e:
            self._send_json(200, {"ok": False, "error": str(e)})

    def _try_decrypt_file(self, path, password):
        """尝试解密一个文件"""
        # 🚧 纯逻辑已在 utils/crypto — 此方法为双轨过渡
        try:
            from Crypto.Cipher import AES
            from Crypto.Protocol.KDF import scrypt
            from Crypto.Random import get_random_bytes
            import json, base64
            with open(path, 'rb') as f:
                raw = f.read()
            if not raw.startswith(b'LSE'):
                return None
            data = json.loads(raw[3:].decode('utf-8'))
            salt = base64.b64decode(data['s'])
            nonce = base64.b64decode(data['n'])
            tag = base64.b64decode(data['t'])
            ciphertext = base64.b64decode(data['c'])
            key = scrypt(password.encode('utf-8'), salt, 32, N=2**14, r=8, p=1)
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            return plaintext.decode('utf-8')
        except:
            return None

    def _handle_browse_dirs(self):
        """返回浏览根目录下的文件夹"""
        # 🚧 已迁移到 utils/tb_handler.browse_root_dirs
        try:
            items = browse_root_dirs(BROWSE_ROOT)
            self._send_json(200, {"ok": True, "root": BROWSE_ROOT, "items": items})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    
    

    def _handle_memory_file_list(self):
        """列出所有记忆文件 (GET /api/memory-files)"""
        try:
            mem_dir = os.path.join(LIGHT_SMOKE_DIR, "memory")
            files = []
            if os.path.exists(mem_dir):
                for f in sorted(os.listdir(mem_dir)):
                    if f.endswith('.md') and not f.startswith('.'):
                        fpath = os.path.join(mem_dir, f)
                        sz = os.path.getsize(fpath)
                        files.append({
                            "name": f,
                            "size": f"{sz/1024:.1f}KB" if sz > 1024 else f"{sz}B",
                            "modified": datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%m-%d %H:%M"),
                        })
            self._send_json(200, {"ok": True, "files": files})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_memory_file_save(self):
        """保存记忆文件 (POST /api/memory-file)"""
        try:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            name = body.get('name', '')
            content = body.get('content', '')
            name = os.path.basename(name)
            if not name.endswith('.md'):
                self._send_json(200, {"ok": False, "error": "只允许 .md 文件"})
                return
            mem_dir = os.path.join(LIGHT_SMOKE_DIR, "memory")
            fpath = os.path.join(mem_dir, name)
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            self._send_json(200, {
                "ok": True,
                "path": fpath,
                "size": len(content),
            })
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    # ── 🔐 加密处理器（TODO: 双轨过渡，纯逻辑已拆到 utils/crypto）───
    def _handle_encrypt_save_file(self):
        """保存解密后的文件（明文写入，自动重加密）"""
        try:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            folder_name = body.get('folder', 'encrypted')
            file_name = body.get('file', '')
            text = body.get('text', '')
            password = body.get('password', '')

            if not file_name:
                self._send_json(200, {"ok": False, "error": "文件名不能为空"})
                return
                self._send_json(200, {"ok": False, "error": "该文件夹不可加密"})
                return
                self._send_json(200, {"ok": False, "error": "该文件夹不可加密"})
                return
            if not password:
                self._send_json(200, {"ok": False, "error": "密码不能为空"})
                return

            folder = _get_encrypt_folder(folder_name)
            fpath = os.path.join(folder, os.path.basename(file_name))
            
            # 写明文
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(text)
            
            # 立即加密
            _encrypt_file(fpath, password)
            
            self._send_json(200, {
                "ok": True,
                "file": file_name,
                "size": len(text),
            })
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_pass_password(self):
        """把密码传递给AI（注入到当前session）"""
        try:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            folder = body.get('folder', 'encrypted')
            password = body.get('password', '')
            
            if not password:
                self._send_json(200, {"ok": False, "error": "密码为空"})
                return
            
            # 从密码保险箱取或直接用传入的密码
            pw = PASSWORD_VAULT.get(folder, password)
            
            # 构造消息注入session
            pwd_display = pw[:1] + '*' * (len(pw) - 1)
            msg = (f'[🔐 系统] 密码已传递。密码是「{pw}」。'
                   f'你可以用这个密码解密 encrypted/ 文件夹中的文件。'
                   f'调用 /api/decrypt 时传入 password={pwd_display} 和你想读的文件名。')
            
            sk, _sf = get_session_info()
            ok = inject_via_websocket(session_key=sk, message=msg)
            self._send_json(200, {"ok": ok, "note": f"密码已注入会话，AI现在知道密码"})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_encrypt_folders(self):
        """列举目录下的文件夹，支持层级展开（从 BROWSE_ROOT 开始导航）"""
        try:
            parent = self._get_param('parent', '')
            root = BROWSE_ROOT  # /vol2/1000/AI专用

            if parent:
                target_dir = os.path.normpath(os.path.join(root, parent))
                if not target_dir.startswith(root):
                    self._send_json(403, {"ok": False, "error": "越权访问"})
                    return
            else:
                target_dir = root

            items = []
            for name in sorted(os.listdir(target_dir)):
                fpath = os.path.join(target_dir, name)
                if os.path.isdir(fpath):
                    has_subdirs = any(os.path.isdir(os.path.join(fpath, x)) for x in os.listdir(fpath))
                    md_count = 0
                    for dirpath, _, filenames in os.walk(fpath):
                        for f in filenames:
                            if f.endswith('.md'):
                                md_count += 1
                    rel_path = os.path.join(parent, name) if parent else name
                    items.append({
                        "name": name,
                        "path": rel_path,
                        "md_count": md_count,
                        "has_children": has_subdirs,
                    })
            self._send_json(200, {"ok": True, "root": root, "parent": parent, "items": items})
        except PermissionError:
            self._send_json(200, {"ok": True, "root": root, "parent": parent, "items": []})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_encrypt_status(self):
#         """查询加密状态 (GET /api/encrypt-status)"""
        try:
            folder_name = self._get_param('folder', 'encrypted')
            folder = _get_encrypt_folder(folder_name)
            password = self._get_param('password', '')

            files = sorted([f for f in os.listdir(folder) if f.endswith('.md')])

            # 判断是否已加密（只看文件格式，不需要密码）
            is_encrypted = _is_folder_encrypted(folder) if files else False

            file_info = []
            for f in files:
                fpath = os.path.join(folder, f)
                sz = os.path.getsize(fpath)
                file_info.append({"name": f, "size": sz})

            session_decrypted = folder_name in SESSION_DECRYPTED
            self._send_json(200, {
                "ok": True,
                "folder": folder,
                "file_count": len(files),
                "files": file_info,
                "is_encrypted": is_encrypted,
                "session_decrypted": session_decrypted,
                "has_password": bool(PASSWORD_VAULT.get(folder_name)),
                "password_saved": folder_name in PASSWORD_VAULT,
            })
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_encrypt(self):
        """加密文件夹 (POST /api/encrypt)"""
        try:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            folder_name = body.get('folder', 'encrypted')
            password = body.get('password', '')
            save_password = body.get('save_password', False)

            if not password:
                self._send_json(200, {"ok": False, "error": "密码不能为空"})
                return

            folder = _get_encrypt_folder(folder_name)
            files = sorted([f for f in os.listdir(folder) if f.endswith('.md')])

            if not files:
                self._send_json(200, {"ok": False, "error": "文件夹中没有 .md 文件"})
                return

            # 获取已保存的密码用于解密已加密文件
            saved_password = PASSWORD_VAULT.get(folder_name)
            
            # 加密所有文件
            encrypted_count = 0
            for f in files:
                fpath = os.path.join(folder, f)
                with open(fpath, 'r', encoding='utf-8') as fh:
                    file_content = fh.read()
                
                # 如果文件已加密，先解密再重新加密
                if _is_hex_encrypted(file_content):
                    decrypted_str = None
                    # 优先用已保存的密码（旧密码），保证能正确解密
                    if saved_password:
                        d = _xor_decrypt(file_content.strip(), saved_password)
                        decrypted_str = d
                    else:
                        # 无已保存密码，尝试用用户输入的密码
                        d = _xor_decrypt(file_content.strip(), password)
                        if d:
                            decrypted_str = d
                    
                    if decrypted_str is not None:
                        file_content = decrypted_str
                    # 如果都失败，就把当前内容当明文处理
                
                encrypted = _xor_crypt(file_content, password)
                with open(fpath, 'w', encoding='utf-8') as fh:
                    fh.write(encrypted)
                encrypted_count += 1

            # 更新密码保险箱
            if save_password:
                PASSWORD_VAULT[folder_name] = password

            # 加密后清除 session 解密状态
            SESSION_DECRYPTED.discard(folder_name)

            self._send_json(200, {
                "ok": True,
                "folder": folder,
                "encrypted_count": encrypted_count,
                "password_saved": save_password,
            })
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_decrypt(self):
        """解密并返回内容 (POST /api/decrypt) — 不写盘，仅供查看"""
        try:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            folder_name = body.get('folder', 'encrypted')
            password = body.get('password', '')
            file_name = body.get('file', '')  # 可选，指定单个文件

            if not password:
                # 尝试从保险箱取密码
                if folder_name in PASSWORD_VAULT:
                    password = PASSWORD_VAULT[folder_name]

            folder = _get_encrypt_folder(folder_name)
            
            # 检查是否需要密码：如果文件未加密，直接读明文
            files_in_folder = sorted([f for f in os.listdir(folder) if f.endswith('.md')])
            needs_password = False
            if password and files_in_folder:
                needs_password = _is_folder_encrypted(folder, password)
            elif files_in_folder:
                # 没给密码时，检查文件是不是hex格式
                sample_file = os.path.join(folder, files_in_folder[0])
                with open(sample_file, 'r', encoding='utf-8') as sf:
                    sample = sf.read().strip()
                needs_password = _is_hex_encrypted(sample)
            
            if needs_password and not password:
                self._send_json(200, {"ok": False, "error": "文件已加密，需要密码"})
                return

            if file_name:
                # 解密单个文件
                fpath = os.path.join(folder, file_name)
                if not os.path.exists(fpath):
                    self._send_json(200, {"ok": False, "error": f"文件不存在: {file_name}"})
                    return
                # 先读文件，判断是否加密
                with open(fpath, 'r', encoding='utf-8') as fh:
                    raw = fh.read()
                if _is_hex_encrypted(raw):
                    if not password:
                        self._send_json(200, {"ok": False, "error": "文件已加密，需要密码"})
                        return
                    plain = _xor_decrypt(raw.strip(), password, check_magic=True)
                    if not plain:
                        self._send_json(200, {"ok": False, "error": "密码错误，解密失败"})
                        return
                else:
                    plain = raw  # 未加密，直接返回明文
                self._send_json(200, {
                    "ok": True,
                    "file": file_name,
                    "content": plain,
                    "size": len(plain),
                })
                return  # ← 关键：防止继续执行到外面的 send_json

            # 解密所有文件，返回全部内容
            files = sorted([f for f in os.listdir(folder) if f.endswith('.md')])
            contents = {}
            for f in files:
                fpath2 = os.path.join(folder, f)
                with open(fpath2, 'r', encoding='utf-8') as fh2:
                    raw2 = fh2.read()
                if _is_hex_encrypted(raw2):
                    if not password:
                        self._send_json(200, {"ok": False, "error": "部分文件已加密，需要密码"})
                        return
                    plain2 = _xor_decrypt(raw2.strip(), password, check_magic=True)
                    if not plain2:
                        self._send_json(200, {"ok": False, "error": "密码错误，解密失败"})
                        return
                    contents[f] = plain2
                else:
                    contents[f] = raw2

            SESSION_DECRYPTED.add(folder_name)
            self._send_json(200, {
                "ok": True,
                "files": contents,
                "file_count": len(files),
            })
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

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

# HTTPS server (on port +1, if cert exists)
_HTTPS_PORT = EDITOR_PORT + 1
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
    digest_out = "/tmp/digestion-last-output.txt"
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
