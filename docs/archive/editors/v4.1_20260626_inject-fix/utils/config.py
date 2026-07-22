#!/usr/bin/env python3
"""
utils/config.py — 集中式路径管理与配置发现

替换所有模块中散落的硬编码路径。
由 edit-web.py 启动时调用 init_paths() 初始化。
"""

import os
import json
import sys

# ── 全局路径字典 ──────────────────────────────────────────────────────
PATHS = {}

# ── OpenClaw 配置发现（从 edit-web.py 迁移） ─────────────────────────

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
    """Read OpenClaw config from openclaw.json."""
    json_path = os.path.join(openclaw_home, 'openclaw.json')
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)
    for y in ('config.yaml', 'config.yml'):
        yp = os.path.join(openclaw_home, y)
        if os.path.exists(yp):
            print(f"[CONFIG WARN] Found {y} but YAML not supported.", file=sys.stderr)
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

    legacy = os.path.join(agents_dir, 'main', 'sessions')
    if os.path.isdir(legacy):
        return legacy

    return None


# ── 集中式路径初始化 ─────────────────────────────────────────────────

def init_paths(openclaw_home=None, overrides=None):
    """初始化所有路径，由 edit-web.py 启动时调用。

    overrides: dict — 用于注入 editor-config.json / env 覆盖
    """
    global PATHS
    home = openclaw_home or find_openclaw_home()
    config = read_openclaw_config(home)
    ov = overrides or {}

    # OpenClaw 基础路径
    PATHS['OPENCLAW_HOME'] = home
    PATHS['CONFIG'] = os.path.join(home, 'openclaw.json')
    PATHS['CRON_JSON'] = os.path.join(home, 'cron', 'jobs.json')
    PATHS['CRON_RUNS'] = os.path.join(home, 'cron', 'runs')

    # Session
    sessions_dir = ov.get('DATA_DIR') or discover_session_dir(home)
    PATHS['SESSIONS_DIR'] = sessions_dir
    PATHS['SESSIONS_JSON'] = os.path.join(sessions_dir, 'sessions.json') if sessions_dir else None

    # 固定路径（跨主机可变的通过 overrides 注入）
    PATHS['BUN_BIN'] = '/var/apps/bunjs/target/bin/bun'
    PATHS['DIGEST_OUT'] = '/tmp/digestion-last-output.txt'
    PATHS['PLUGIN_INJECTED'] = '/tmp/plugin-injected.txt'
    PATHS['PLUGIN_RAN'] = '/tmp/plugin-ran.txt'
    PATHS['LAST_PROCESSING'] = '/tmp/last-processing.txt'
    PATHS['LAST_INJECTION_BODY'] = '/tmp/last-injection-body.txt'
    PATHS['LAST_INJECTION'] = '/tmp/last-injection.txt'

    # Python site-packages
    PATHS['SITE_PACKAGES'] = '/vol1/@apphome/trim.openclaw/data/home/.local/lib/python3.11/site-packages'

    # 项目相关（通过 overrides 或相对路径发现）
    script_dir = os.path.dirname(os.path.abspath(__file__))  # utils/
    light_smoke_dir = ov.get('LIGHT_SMOKE_DIR') or os.path.dirname(script_dir)  # scripts/ 父目录 = 轻如烟/
    PATHS['LIGHT_SMOKE_DIR'] = light_smoke_dir

    all_auto_dir = ov.get('ALL_AUTO_DIR') or os.path.dirname(light_smoke_dir)
    PATHS['ALL_AUTO_DIR'] = all_auto_dir

    browse_root = ov.get('BROWSE_ROOT') or os.path.dirname(all_auto_dir)
    PATHS['BROWSE_ROOT'] = browse_root

    workspace_hooks = ov.get('WORKSPACE_HOOKS') or os.path.join(home, '..', 'workspace', 'hooks')
    PATHS['WORKSPACE_HOOKS'] = workspace_hooks

    skills_dir = ov.get('SKILLS_DIR') or os.path.join(home, '..', '.pi', 'agent', 'skills')
    PATHS['SKILLS_DIR'] = skills_dir

    # 轻如烟内部路径
    PATHS['SCRIPT_DIR'] = script_dir  # 实际上是 utils/ 目录，注意修正
    # 修正：SCRIPT_DIR 应该是 scripts/ 目录
    scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or os.path.dirname(script_dir)
    PATHS['SCRIPT_DIR'] = scripts_dir

    return PATHS


def init_light_smoke_paths(light_smoke_dir, all_auto_dir, browse_root):
    """初始化轻如烟特有的路径（在 init_paths 之后调用）."""
    PATHS['LIGHT_SMOKE_DIR'] = light_smoke_dir
    PATHS['ALL_AUTO_DIR'] = all_auto_dir
    PATHS['BROWSE_ROOT'] = browse_root

    # Inject / Lock
    PATHS['INJECT_LOCK_DIR'] = os.path.join(light_smoke_dir, '.locks')
    PATHS['INJECT_LOCK_FILE'] = os.path.join(PATHS['INJECT_LOCK_DIR'], '.inject_lock')

    # 备份
    PATHS['BACKUP_DIR'] = os.path.join(all_auto_dir, 'backups')

    # Memory / File change tracking
    PATHS['SAVE_MONITOR_DIR'] = os.path.join(light_smoke_dir, 'memory')
    PATHS['FILE_CHANGE_DIR'] = os.path.join(PATHS['SAVE_MONITOR_DIR'], 'file-changes')

    # MOMO 打包目录
    PATHS['MOMO_DIR'] = os.path.join(all_auto_dir, '找回自己')

    # 小说路径
    PATHS['NOVEL_PATHS'] = [
        os.path.join(browse_root, '小说'),
        os.path.join(browse_root, '小说新汇总'),
    ]

    # 秘书提醒
    PATHS['REMINDERS_FILE'] = os.path.join(PATHS['SAVE_MONITOR_DIR'], 'reminders.json')

    # 踱步目录
    PATHS['PACE_DIR'] = os.path.join(PATHS['SCRIPT_DIR'], '.踱步')

    return PATHS


def path(key):
    """获取配置路径"""
    return PATHS.get(key)


def set_path(key, value):
    """运行时设置路径（用于编辑器配置发现）"""
    PATHS[key] = value
