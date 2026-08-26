#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wake_client.py — 唤醒主 AI 的 HTTP 客户端（A 通道，2026-08-06）
==============================================================
POST {HOOKS_URL}/wake —— OpenClaw 官方外部唤醒接口（hooks.path=/hooks）：
  - Authorization: Bearer <token>（token 来自 openclaw.json 的 hooks.token，
    任何情况不打印、不写日志、不入 metrics）
  - body: {"text": str, "mode": "now" | "next-heartbeat"}
  - timeout 5s；fail-open：任何失败只返回结果 dict（供调用方记 metrics），
    绝不抛异常。

用法：
    from wake_client import wake
    r = wake("醒来第一眼摘要", mode="next-heartbeat")
    r = wake("...", dry_run=True)   # 演练：构造请求但不发送

环境变量：
    HOOKS_URL     默认 http://127.0.0.1:10554（gateway.port=10554，调研确认）
    OPENCLAW_JSON 默认 /vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

def _default_openclaw_json() -> str:
    """默认 openclaw.json 定位：OPENCLAW_HOME > HOME > ~（可移植；生产由 pulse-cron.sh 导出 OPENCLAW_HOME）。"""
    for base in (os.environ.get('OPENCLAW_HOME'), os.environ.get('HOME')):
        if base:
            p = os.path.join(base, 'openclaw.json')
            if os.path.exists(p):
                return p
    return os.path.expanduser('~/.openclaw/openclaw.json')

_DEFAULT_OPENCLAW_JSON = _default_openclaw_json()
_TIMEOUT = 5  # 秒


def _now_iso() -> str:
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')


def load_token(path: str = '') -> str:
    """读 openclaw.json hooks.token。任何失败返回 ''（fail-open）。
    返回值仅内部使用，严禁打印/落盘。"""
    path = path or os.environ.get('OPENCLAW_JSON') or _DEFAULT_OPENCLAW_JSON
    try:
        with open(path, encoding='utf-8') as f:
            cfg = json.load(f)
        tok = (cfg.get('hooks') or {}).get('token')
        return str(tok) if tok else ''
    except Exception:
        return ''


def hooks_url() -> str:
    """完整 wake 端点 URL（不含 token，可安全打印/记录）。
    ★ 2026-08-06 修复：gateway hooks 挂在 {base}{hooks.path} 下，
    实际端点是 /hooks/wake 而非 /wake（原实现 404，活体测试暴露）。"""
    base = (os.environ.get('HOOKS_URL') or _DEFAULT_HOOKS_URL).rstrip('/')
    if base.endswith('/hooks'):
        return base + '/wake'
    path = os.environ.get('HOOKS_PATH', '')
    if not path:
        try:
            with open(os.environ.get('OPENCLAW_JSON') or _DEFAULT_OPENCLAW_JSON, encoding='utf-8') as f:
                path = (json.load(f).get('hooks') or {}).get('path', '/hooks')
        except Exception:
            path = '/hooks'
    return base + '/' + str(path).strip('/') + '/wake'


def wake(text: str = '', mode: str = 'next-heartbeat',
         dry_run: bool = False, hooks_url_override: str = '',
         token: str = '', timeout: int = _TIMEOUT) -> dict:
    """POST /hooks/wake 唤醒主 AI（A 通道）。全 fail-open，返回结果 dict。

    ★ 2026-08-07 实证更新：heartbeat target:last 修复后 A 通道端到端已通
    （19:34:29 POST /hooks/wake → 19:36:10 心跳 poll 消费，main session
    65ce6954 记录在案）。A 通道已恢复为主通道（self_pulse_cli 同日改回）。
    此前 06:00-10:50 "20+ 次 200 零注入" 根因是 heartbeat 默认 target:none
    不投递，非 A 通道本身问题。wake_editor()（B 通道 chat.send）保留作
    fallback，修好 GATEWAY_TOKEN 环境后可启用。

    dry_run=True：只构造并返回将发送的请求信息，不真实发送。
    返回 dict 字段：ok / attempted / dry_run / mode / text_len / url /
    status / error / ts。绝不含 token。
    """
    result = {
        'ok': False,
        'attempted': not dry_run,
        'dry_run': bool(dry_run),
        'mode': mode,
        'text_len': len(text or ''),
        'url': hooks_url_override or hooks_url(),
        'status': None,
        'error': None,
        'ts': _now_iso(),
    }
    if dry_run:
        result['ok'] = True
        return result

    tok = token if token else load_token()
    if not tok:
        result['error'] = 'no_token: openclaw.json hooks.token 缺失'
        return result
    if mode not in ('now', 'next-heartbeat'):
        result['error'] = f'bad_mode: {mode}'
        return result

    try:
        body = json.dumps({'text': text or '', 'mode': mode}).encode('utf-8')
        req = urllib.request.Request(
            result['url'], data=body, method='POST',
            headers={
                'Authorization': 'Bearer ' + tok,
                'Content-Type': 'application/json',
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result['status'] = resp.status
            result['ok'] = resp.status < 400
            if not result['ok']:
                result['error'] = f'http_{resp.status}'
            else:
                try:
                    result['resp'] = resp.read(512).decode('utf-8', 'replace')[:200]
                except Exception:
                    pass
    except Exception as e:
        result['error'] = f'{type(e).__name__}: {e}'
    return result


def wake_editor(text: str = '', session_key: str = 'agent:main:main',
                dry_run: bool = False, timeout: int = 30) -> dict:
    """B 通道：编辑器 chat.send 注入（生产已验证，守夜/自问脚本同款）。

    2026-08-07 空转修复：A 通道（/hooks/wake）的 text 只入队系统事件，
    主会话空闲时事件积压无人消费 → woke=True 但零感知。B 通道直接调
    inject-helper.mjs 发 chat.send → 消息作为真实 user 消息进主会话，
    必然触发一次 run → 主 AI 真正看到唤醒内容。

    返回 dict：ok / attempted / dry_run / text_len / method / error / ts。
    """
    result = {
        'ok': False,
        'attempted': not dry_run,
        'dry_run': bool(dry_run),
        'method': 'chat.send',
        'text_len': len(text or ''),
        'error': None,
        'ts': _now_iso(),
    }
    if dry_run:
        result['ok'] = True
        return result
    if not (text or '').strip():
        result['error'] = 'empty_text'
        return result
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'inject-helper.mjs')
    if not os.path.exists(helper):
        result['error'] = f'inject-helper.mjs not found: {helper}'
        return result
    try:
        import shutil
        import subprocess
        # 2026-08-07 修复：crontab 环境 PATH 无 node（实测 FileNotFoundError:
        # 'node'），唤醒链 13:00-13:30 三次 wake_failed。显式解析 node 绝对路径
        # （NAS 上 node 在 /vol1/@appcenter/nodejs_v24/bin/node）。
        node_bin = shutil.which('node') or '/vol1/@appcenter/nodejs_v24/bin/node'
        if not os.path.exists(node_bin):
            node_bin = shutil.which('nodejs') or ''
        if not node_bin or not os.path.exists(node_bin):
            result['error'] = 'node_bin_not_found'
            return result
        p = subprocess.run(
            [node_bin, helper, session_key, text, 'send'],
            capture_output=True, text=True, timeout=timeout,
        )
        if p.returncode != 0:
            result['error'] = f'inject_exit_{p.returncode}: {(p.stderr or "")[:120]}'
            return result
        out = (p.stdout or '').strip()
        try:
            parsed = json.loads(out)
            result['ok'] = bool(parsed.get('ok'))
            if not result['ok']:
                result['error'] = str(parsed.get('error') or 'inject_ng')[:120]
        except Exception:
            result['ok'] = 'ok' in out.lower()
            result['error'] = None if result['ok'] else (out[:120] or 'inject_unknown')
    except Exception as e:
        result['error'] = f'{type(e).__name__}: {e}'
    return result


def main(argv=None) -> dict:
    import argparse
    p = argparse.ArgumentParser(description='wake_client 冒烟测试（默认 dry-run）')
    p.add_argument('--text', default='wake_client 冒烟测试（可忽略）')
    p.add_argument('--mode', choices=['now', 'next-heartbeat'], default='next-heartbeat')
    p.add_argument('--real', action='store_true', help='真实发送（默认演练）')
    args = p.parse_args(argv)
    r = wake(args.text, mode=args.mode, dry_run=not args.real)
    # 只打印可安全公开的字段（url 无 token；error 理论含 token 的可能为零，
    # 但保险起见 error 也截断 120 字符且不含 Authorization）
    public = {k: r.get(k) for k in
              ('ok', 'attempted', 'dry_run', 'mode', 'text_len', 'url',
               'status', 'ts')}
    public['error'] = (r.get('error') or '')[:120]
    return public


if __name__ == '__main__':
    try:
        print(json.dumps(main(), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'error': str(e)[:200]}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
