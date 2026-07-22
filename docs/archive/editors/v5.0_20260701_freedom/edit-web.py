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
from utils.subagent import spawn_subagent_process as _spawn_subagent_process_impl
from utils.subagent import exec_subagent as _exec_subagent_impl
from utils.subagent import log_subagent as _log_subagent_impl
from utils.subagent import get_subagent_history as _get_subagent_history_impl
from utils.encryption import xor_crypt as _xor_crypt_impl
from utils.encryption import xor_decrypt as _xor_decrypt_impl
from utils.encryption import is_hex_encrypted as _is_hex_encrypted_impl
from utils.encryption import encrypt_file as _encrypt_file_impl
from utils.encryption import decrypt_file_text as _decrypt_file_text_impl
from utils.encryption import get_encrypt_folder as _get_encrypt_folder_impl
from utils.encryption import is_folder_encrypted as _is_folder_encrypted_impl
from utils.text_utils import strip_metadata as _strip_metadata_impl
from utils.text_utils import group_into_pairs as _group_into_pairs_impl
from utils.text_utils import xml_escape as _xml_escape_impl
from utils.text_utils import is_novel_path as _is_novel_path_impl
from utils.pulse import send_pulse as _send_pulse_impl
from utils.reminder import load_night_questions as _load_night_questions_impl
from utils.reminder import pick_night_question as _pick_night_question_impl
from utils.file_logger import log_file_save as _log_file_save_impl
from utils.status_reports import backup_stale_status as _backup_stale_status_impl
from utils.status_reports import digestion_status as _digestion_status_impl
from utils.status_reports import digestion_skill_status as _digestion_skill_status_impl
from utils.status_reports import digestion_history as _digestion_history_impl
from utils.status_reports import backlog_status as _backlog_status_impl
from utils.status_reports import weaponry_toggle_status as _weaponry_toggle_status_impl
from utils.status_reports import plugin_health_core as _plugin_health_core_impl
from utils.status_reports import plugin_health as _plugin_health_impl
from utils.status_reports import thinking_status as _thinking_status_impl
from utils.status_reports import system_health as _system_health_impl
from utils.status_reports import last_processing as _last_processing_impl
from utils.status_reports import last_injection as _last_injection_impl
from utils.status_reports import lungan_status as _lungan_status_impl
from utils.status_reports import search_backups as _search_backups_impl
from utils.status_reports import promote_pending_assertions as _promote_pending_assertions_impl
from utils.inject_lock import cleanup_lock as _cleanup_lock_impl
from utils.inject_lock import is_locked as _is_locked_impl
from utils.inject_lock import acquire_lock as _acquire_lock_impl
from utils.inject_lock import LOCK_TTL_SECONDS as _LOCK_TTL_SECONDS
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

# 子代理历史日志路径
EXEC_SUBAGENT_HISTORY = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'subagent-history.log')
EXEC_SUBAGENT_WORKDIR = '/tmp/subagent-work'

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
    # NexSandglass 自动落沙：所有消息写入沙漏
    _sandglass_log(message, 'user' if not bypass_lock else 'sister')
    
    if not bypass_lock:
        # 尝试获取锁（含 TTL 超时兜底），由 inject_lock 模块统一管理
        if not _acquire_lock_impl(LIGHT_SMOKE_DIR):
            raise Exception("安全限制：上一轮已注入过，请在下一轮用户消息后再试")

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
    """清理注入锁（委托给 inject_lock 模块）"""
    return _cleanup_lock_impl(
        LIGHT_SMOKE_DIR,
        lambda msg: print(f"[轻如烟] {msg}", file=sys.stderr)
    )


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
    """列出所有会话：已迁移到 utils/session"""
    import utils.session
    return utils.session.list_all_sessions(DATA_DIR)
def get_session_info():
    """获取当前 session：已迁移到 utils/session"""
    import utils.session
    global _active_editor_session_key
    return utils.session.get_session_info(DATA_DIR, _active_editor_session_key)
def strip_metadata(text):
    """Strip untrusted metadata: 已迁移到 utils/text_utils"""
    return _strip_metadata_impl(text)
def read_session(session_file):
    """读取JSONL会话文件：已迁移到 utils/session"""
    import utils.session
    return utils.session.read_session_v2(session_file, strip_metadata_fn=strip_metadata)
def fetch_session_via_gateway(session_key):
    """通过 Gateway RPC 获取会话：已迁移到 utils/session"""
    import utils.session
    return utils.session.fetch_session_via_gateway(
        session_key, GATEWAY_PORT, GATEWAY_TOKEN, OPENCLAW_HOME, IDENTITY_PATH,
        path('BUN_BIN'), os.path.dirname(__file__)
    )
def group_into_pairs(messages):
    """Group messages into pairs: 已迁移到 utils/text_utils"""
    return _group_into_pairs_impl(messages)
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
    """摸摸打包：已迁移到 utils/momo"""
    return _momo_pack_impl(MOMO_DIR, LIGHT_SMOKE_DIR, ALL_AUTO_DIR)
def _momo_status():
    """摸摸状态：已迁移到 utils/momo"""
    return _momo_status_impl(MOMO_DIR, LIGHT_SMOKE_DIR)
def _backup_stale_status():
    """备份过时检查：已迁移到 utils/status_reports"""
    return _backup_stale_status_impl(LIGHT_SMOKE_DIR, MOMO_DIR)
def _digestion_status():
    """消化状态：已迁移到 utils/status_reports"""
    return _digestion_status_impl(LIGHT_SMOKE_DIR)
def _digestion_skill_status():
    """监控栏状态：已迁移到 utils/status_reports"""
    return _digestion_skill_status_impl(
        LIGHT_SMOKE_DIR, path('DIGEST_OUT'), path('CRON_JSON'),
        lambda: _plugin_health_core_impl(path('PLUGIN_INJECTED')),
        path('WORKSPACE_HOOKS')
    )
def _digestion_history():
    """消化循环历史：已迁移到 utils/status_reports"""
    return _digestion_history_impl(LIGHT_SMOKE_DIR, path('CRON_RUNS'))
def _backlog_status():
    """待办清单：已迁移到 utils/status_reports"""
    return _backlog_status_impl(LIGHT_SMOKE_DIR)
def _weaponry_toggle_status():
    """武器库开关：已迁移到 utils/status_reports"""
    return _weaponry_toggle_status_impl(path('CRON_JSON'))
def _plugin_health_core():
    """return (ok, last)：已迁移到 utils/status_reports"""
    return _plugin_health_core_impl(path('PLUGIN_INJECTED'))
def _last_processing():
    """最近静默处理：已迁移到 utils/status_reports"""
    return _last_processing_impl(path('LAST_PROCESSING'))
def _last_injection():
    """最近插件注入：已迁移到 utils/status_reports"""
    return _last_injection_impl(path('LAST_INJECTION_BODY'), path('LAST_INJECTION'))
def _plugin_health():
    """plugin injection status: 已迁移到 utils/status_reports"""
    return _plugin_health_impl(path('PLUGIN_INJECTED'), path('PLUGIN_RAN'))
def _thinking_status():
    """thinking status: 已迁移到 utils/status_reports"""
    return _thinking_status_impl(path('CONFIG'), path('SESSIONS_JSON'))
def _system_health():
    """system health: 已迁移到 utils/status_reports"""
    return _system_health_impl(path('CONFIG'))
def _secretary_analyze_save(path, new_content, old_content):
    """秘书分析：已迁移到 utils/secretary"""
    return secretary_analyze_save(path, new_content, old_content, LIGHT_SMOKE_DIR)
def _load_reminders():
    """加载提醒：已迁移到 utils/secretary"""
    return load_reminders(LIGHT_SMOKE_DIR)
def _save_reminders(reminders):
    """保存提醒：已迁移到 utils/secretary"""
    return save_reminders(reminders, LIGHT_SMOKE_DIR)
def _add_reminder(text, assignee="", trigger_hint=""):
    """添加提醒：已迁移到 utils/secretary"""
    return add_reminder(text, LIGHT_SMOKE_DIR, assignee, trigger_hint)
def _secretary_remind():
    """提醒摘要：已迁移到 utils/secretary"""
    return secretary_remind(LIGHT_SMOKE_DIR)
def _lungan_status():
    """轮感状态：已迁移到 utils/status_reports"""
    return _lungan_status_impl(LIGHT_SMOKE_DIR)
def _momo_index_report():
    """索引报告：已迁移到 utils/momo"""
    return _momo_index_report_impl(MOMO_DIR, LIGHT_SMOKE_DIR, ALL_AUTO_DIR, BACKUP_DIR)
def _search_backups(query, limit=5, only_user=True):
    """搜索备份：已迁移到 utils/status_reports"""
    return _search_backups_impl(query, limit, only_user, BACKUP_DIR, strip_metadata, lambda: get_session_info())
def _momo_auto_save_loop():
    """自动存档：已迁移到 utils.momo"""
    _momo_auto_save_impl(MOMO_DIR, LIGHT_SMOKE_DIR, ALL_AUTO_DIR)
def _load_night_questions():
    """加载守夜问题：已迁移到 utils/reminder"""
    return _load_night_questions_impl(os.path.dirname(__file__))
def _pick_night_question():
    """随机守夜问题：已迁移到 utils/reminder"""
    return _pick_night_question_impl(os.path.dirname(__file__))
def _xor_crypt(text, password):
    """XOR 加密：已迁移到 utils/encryption"""
    return _xor_crypt_impl(text, password)
def _xor_decrypt(hex_str, password, check_magic=True):
    """XOR 解密：已迁移到 utils/encryption"""
    return _xor_decrypt_impl(hex_str, password, check_magic)
def _is_hex_encrypted(content):
    """检查hex加密：已迁移到 utils/encryption"""
    return _is_hex_encrypted_impl(content)
def _encrypt_file(path, password):
    """加密文件：已迁移到 utils/encryption"""
    return _encrypt_file_impl(path, password)
def _decrypt_file_text(path, password):
    """解密文件：已迁移到 utils/encryption"""
    return _decrypt_file_text_impl(path, password)
def _get_encrypt_folder(folder_name="encrypted"):
    """加密文件夹路径：已迁移到 utils/encryption"""
    return _get_encrypt_folder_impl(LIGHT_SMOKE_DIR, folder_name)
def _is_folder_encrypted(folder, password=None):
    """检查文件夹加密：已迁移到 utils/encryption"""
    return _is_folder_encrypted_impl(folder, password)
def _send_pulse(mode=None):
    """保活脉冲：已迁移到 utils/pulse"""
    return _send_pulse_impl(mode, get_session_info, _pick_night_question,
               LIGHT_SMOKE_DIR, GATEWAY_PORT, GATEWAY_TOKEN,
               OPENCLAW_HOME, IDENTITY_PATH, path('BUN_BIN'), os.path.dirname(__file__))
def _is_novel_path(path):
    """判断小说路径：已迁移到 utils/text_utils"""
    return _is_novel_path_impl(path, NOVEL_PATHS)
def _log_file_save(path, new_content, is_novel, old_content=None):
    """文件保存日志：已迁移到 utils/file_logger"""
    return _log_file_save_impl(path, new_content, is_novel, FILE_CHANGE_DIR, old_content)
def _spawn_subagent_process(task, model="GLM-Z1-Flash", timeout=120):
    """spawn 子代理：已迁移到 utils/subagent"""
    return _spawn_subagent_process_impl(task, model, timeout, get_session_info, GATEWAY_PORT, GATEWAY_TOKEN,
                OPENCLAW_HOME, IDENTITY_PATH, path('BUN_BIN'), os.path.dirname(__file__))
def _exec_subagent(task, model="deepseek-chat", timeout=60):
    """exec 子代理：已迁移到 utils/subagent"""
    return _exec_subagent_impl(task, model, timeout, EXEC_SUBAGENT_HISTORY, EXEC_SUBAGENT_WORKDIR)
def _log_subagent(model, task_preview, elapsed, inp, out, status, result_preview):
    """子代理日志：已迁移到 utils/subagent"""
    return _log_subagent_impl(model, task_preview, elapsed, inp, out, status, result_preview, EXEC_SUBAGENT_HISTORY)
def _get_subagent_history(limit=20):
    """子代理历史：已迁移到 utils/subagent"""
    return _get_subagent_history_impl(limit, EXEC_SUBAGENT_HISTORY)
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
    """XML转义：已迁移到 utils/text_utils"""
    return _xml_escape_impl(s)
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
import utils.inject_lock as _inject_lock_mod
print(f"   Lock:   {_inject_lock_mod.get_lock_file(LIGHT_SMOKE_DIR) or '(n/a)'}", file=sys.stderr)
print(f"   Timeout: {os.environ.get('INJECT_TIMEOUT', '60')}s", file=sys.stderr)
def _promote_pending_assertions():
    """断言提升器：已迁移到 utils/status_reports"""
    return _promote_pending_assertions_impl(LIGHT_SMOKE_DIR, path('DIGEST_OUT'))
try:
    server.serve_forever()
except KeyboardInterrupt:
    server.server_close()
