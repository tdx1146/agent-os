#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sleep_pressure.py — 体力系统（仿 Borbély Process S 睡眠压力，2026-08-06）
==========================================================================
防自激循环核心：模仿人类"体力极限"（腺苷/睡眠压力）的自组织负反馈。

模型（对应调研报告 C 节）：
  - 唤醒压力 W(t)：每次自主唤醒 W += ΔW_act（默认 0.15）；
    清醒期按 τ_wake（默认 45min）指数衰减：W *= exp(-dt/τ_wake)
  - 休眠：W > θ_sleep（0.7）→ 强制休眠期，拒绝一切自主唤醒；
    休眠时长 ∝ 超出量：base * (W-θ_sleep)/ΔW_act，夹在 [30, 240] 分钟；
    休眠中 W 按 τ_sleep（20min）指数衰减
  - 恢复：休眠到时 / W < θ_awake（0.2）→ 解除休眠
  - 紧急 override：事件等级=anomaly（硬告警）可强唤醒（人类被地震吵醒），
    但记入成本：W += ΔW_act + OVERRIDE_COST（0.4，≈3 次普通唤醒）
  - 冷却期：每次唤醒后 ≥10min 不重复唤醒（注入锁思路）
  - 去重游标：同事件指纹（hash）只唤醒一次（TTL 7 天，防久远旧事复活刷屏）

状态文件（持久，跟 metrics 同层）：
  /vol2/1000/AI专用/所有自动化/轻如烟/sandglass/sleep_pressure.json
  （环境变量 SP_STATE_FILE 可覆盖；NEXSANDBASE_HOME 优先）

用法：
    from sleep_pressure import check, load_state, status
    allowed, reason, st = check('anomaly', fingerprint='ab12cd34',
                                dry_run=True)   # dry_run 不落盘
    print(status(st))                            # 人类可读状态

CLI：
    python3 sleep_pressure.py --status
    python3 sleep_pressure.py --check anomaly --fingerprint xyz --commit
"""

import json
import math
import os
import sys
import time
from datetime import datetime

# 沙漏数据目录（跟 self_pulse 同推导）：NEXSANDBASE_HOME 优先
_SANDBASE = os.environ.get('NEXSANDBASE_HOME') or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'sandglass',
)
_STATE_FILE = os.environ.get('SP_STATE_FILE',
                             os.path.join(_SANDBASE, 'sleep_pressure.json'))

# 参数（全部可用环境变量覆盖；保守起步）
DELTA_W_ACT = float(os.environ.get('SP_DELTA_W', '0.15'))       # 每次唤醒 W += ΔW
TAU_WAKE_MIN = float(os.environ.get('SP_TAU_WAKE', '45'))       # 清醒期衰减常数
TAU_SLEEP_MIN = float(os.environ.get('SP_TAU_SLEEP', '20'))     # 休眠期衰减常数
THETA_SLEEP = float(os.environ.get('SP_THETA_SLEEP', '0.7'))    # 进入休眠阈值
THETA_AWAKE = float(os.environ.get('SP_THETA_AWAKE', '0.2'))    # 解除休眠阈值
COOLDOWN_MIN = float(os.environ.get('SP_COOLDOWN_MIN', '10'))   # 唤醒冷却期
OVERRIDE_COST = float(os.environ.get('SP_OVERRIDE_COST', '0.4'))  # anomaly 强唤醒额外成本
SLEEP_BASE_MIN = float(os.environ.get('SP_SLEEP_BASE_MIN', '30'))  # 休眠基础时长
SLEEP_MAX_MIN = float(os.environ.get('SP_SLEEP_MAX_MIN', '240'))
DEDUP_TTL_DAYS = float(os.environ.get('SP_DEDUP_TTL_DAYS', '7'))   # 去重游标 TTL
DEDUP_MAX = 200
HISTORY_MAX = 20

# ── 白天禁醒窗口 & 每日预算（2026-08-07 dandan 拍板：省 token）──
# 2026-08-12 唤醒策略修正（dandan 澄清，权威；沙漏 2026-08-12 10:52 记录）：
#   - 白天禁醒窗口（DAY_NO_WAKE_START~DAY_NO_WAKE_END，默认 00:00~18:00）：
#     18:00 前禁 routine 级自主唤醒（token 贵；"18:00 前禁止自主唤醒" 8/6 拍板，保留）
#   - 夜间（18:00 后）：dandan 无交互（detect_interactive=False 持续 SP_IDLE_MIN
#     分钟）→ 允许醒；在沟通中 → 顺延（交互相位门，见下）
#   - 没有"23:00-08:00 安静期"这种全静默——那是子 AI 臆测/幻觉，dandan 2026-08-12
#     纠正；原 QUIET 语义（安静期）与 08:30-18:00 窗口作废
#   - 每日预算 SP_DAILY_CAP（默认 10，8/7 拍板"一晚上最多10次"）：routine 唤醒只可能
#     发生在 18:00 后（白天禁醒窗口先挡），日预算即夜间预算；2026-08-10 夜间分桶
#     （NIGHT_CAP/DAY_CAP，窗口 00:30-08:30）随安静窗口语义一起作废——其窗口在白天
#     禁醒窗口内 routine 永远用不到，保留分桶反而会把 18:00 后的晚间唤醒误限到 2 次
#   - anomaly 硬告警穿透（"禁 routine 级"：紧急事件类保留）
DAY_NO_WAKE_START = os.environ.get('SP_DAY_NO_WAKE_START', '00:00')  # 白天禁醒窗口起
DAY_NO_WAKE_END = os.environ.get('SP_DAY_NO_WAKE_END', '18:00')      # 白天禁醒窗口止（不含）
# 兼容旧变量（SP_QUIET_*，2026-08-12 语义修正前）；新变量显式设置时优先
if 'SP_QUIET_START' in os.environ and 'SP_DAY_NO_WAKE_START' not in os.environ:
    DAY_NO_WAKE_START = os.environ['SP_QUIET_START']
if 'SP_QUIET_END' in os.environ and 'SP_DAY_NO_WAKE_END' not in os.environ:
    DAY_NO_WAKE_END = os.environ['SP_QUIET_END']
DAILY_CAP = int(os.environ.get('SP_DAILY_CAP', '10'))


def _in_window(hhmm: str, start: str, end: str) -> bool:
    """判断 HH:MM 是否在 [start, end) 窗口内（支持跨午夜）。"""
    return (start <= hhmm < end) if start <= end else (hhmm >= start or hhmm < end)

# ── 交互相位门（Phase gate，2026-08-06 dandan 设计）──
# 人类不打扰正在上班的人：用户最近有输入时，自主唤醒应闭嘴（排队到空闲）。
# 2026-08-12 澄清：夜间"dandan 不在（无交互）→ 可醒；在沟通中 → 顺延"——
# 即 detect_interactive=False 持续 SP_IDLE_MIN 分钟才允许 routine 唤醒。
IDLE_MINUTES = float(os.environ.get('SP_IDLE_MIN', '30'))          # 最近交互判定窗口
# 主会话目录（OpenClaw sessions）：机器相关，正式部署经 env.local 的
# RESET_WATCHDOG_SESSIONS_DIR 或 SP_SESSION_DIR 配置；兜底 ~/.openclaw（可移植）。
SESSION_DIR = os.environ.get('SP_SESSION_DIR',
    os.path.join(os.path.expanduser('~'), '.openclaw', 'agents', 'main', 'sessions'))


def detect_interactive(now: float = None, session_dir: str = '') -> bool:
    """检测主会话最近是否有交互（读会话文件 mtime）。fail-open：读不到视为非交互。"""
    now = time.time() if now is None else now
    d = session_dir or SESSION_DIR
    try:
        newest = 0.0
        for name in os.listdir(d):
            if not name.endswith('.jsonl') or 'trajectory' in name:
                continue
            # 只统计主会话（agent:main:main）；子代理/心跳等其他会话文件
            # 不算用户交互，避免误判抑制（2026-08-07 修复）
            try:
                with open(os.path.join(d, name), encoding='utf-8',
                          errors='replace') as f:
                    first = f.readline()
                if 'agent:main:main' not in first:
                    continue
            except Exception:
                continue
            p = os.path.join(d, name)
            try:
                m = os.path.getmtime(p)
            except OSError:
                continue
            if m > newest:
                newest = m
        return (now - newest) < IDLE_MINUTES * 60
    except Exception:
        return False


def _now_iso(ts: float = None) -> str:
    ts = time.time() if ts is None else ts
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%S+08:00')


def _parse_iso(iso: str) -> float:
    """解析本地时区 ISO 字符串 → epoch。失败返回 None（fail-open）。"""
    if not iso:
        return None
    try:
        return datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S').timestamp()
    except Exception:
        return None


def default_state() -> dict:
    return {
        'W': 0.0,
        'mode': 'awake',          # awake | sleeping
        'last_update': _now_iso(),
        'sleep_started': None,    # iso
        'wakeup_at': None,        # iso（休眠到期时刻）
        'sleep_duration_min': None,
        'last_wake_at': None,     # iso
        'dedup': {},              # {指纹: iso} 同事件只唤醒一次
        'history': [],            # 近 HISTORY_MAX 条唤醒记录
        'total_wakes': 0,
        'total_suppressed': 0,
        'total_overrides': 0,
        'daily': {'date': '', 'count': 0, 'night_count': 0, 'day_count': 0},
        # 2026-08-12 起只计 count（night/day 分桶随夜间窗口作废，字段保留兼容旧状态）
        'updated_at': _now_iso(),
    }


def load_state(path: str = '') -> dict:
    """读状态文件；缺失/损坏 → 全新状态（fail-open，保守从 0 开始）。"""
    path = path or _STATE_FILE
    st = default_state()
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in st:
                if k in data:
                    st[k] = data[k]
            st.setdefault('dedup', {})
            st.setdefault('history', [])
            # 旧状态兼容：daily 补 night/day 分桶（2026-08-10 夜间权重版）
            daily = st.get('daily') or {}
            if 'night_count' not in daily or 'day_count' not in daily:
                daily.setdefault('night_count', 0)
                daily.setdefault('day_count', 0)
                st['daily'] = daily
    except Exception:
        pass
    return st


def save_state(st: dict, dry_run: bool = False, path: str = '') -> bool:
    """原子写（tmp + rename）。dry_run 不落盘。失败返回 False（fail-open）。"""
    if dry_run:
        return False
    st['updated_at'] = _now_iso()
    path = path or _STATE_FILE
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _decay(w: float, dt_min: float, tau_min: float) -> float:
    """指数衰减：W *= exp(-dt/τ)。"""
    if dt_min <= 0 or tau_min <= 0:
        return w
    return w * math.exp(-dt_min / tau_min)


def _trim_dedup(st: dict, now: float) -> None:
    """裁剪去重游标：TTL 过期 + 数量上限（drop 最旧）。"""
    dedup = st.get('dedup') or {}
    ttl = DEDUP_TTL_DAYS * 86400
    fresh = {fp: ts for fp, ts in dedup.items()
             if _parse_iso(ts) is not None and now - _parse_iso(ts) < ttl}
    if len(fresh) > DEDUP_MAX:
        ordered = sorted(fresh.items(), key=lambda kv: _parse_iso(kv[1]) or 0)
        fresh = dict(ordered[-(DEDUP_MAX - 1):])
    st['dedup'] = fresh


def update(st: dict, now: float = None) -> dict:
    """按经过时间衰减 W；休眠到期 / W<θ_awake → 解除休眠。"""
    now = time.time() if now is None else now
    last = _parse_iso(st.get('last_update'))
    st['last_update'] = _now_iso(now)
    if last is None:
        return st
    dt_min = max(0.0, (now - last) / 60.0)
    tau = TAU_SLEEP_MIN if st.get('mode') == 'sleeping' else TAU_WAKE_MIN
    st['W'] = _decay(st.get('W', 0.0), dt_min, tau)

    if st.get('mode') == 'sleeping':
        wakeup = _parse_iso(st.get('wakeup_at'))
        if (wakeup is not None and now >= wakeup) or st.get('W', 0.0) <= THETA_AWAKE:
            st['mode'] = 'awake'
            st['sleep_started'] = None
            st['wakeup_at'] = None
            st['sleep_duration_min'] = None
    return st


def _enter_sleep(st: dict, now: float) -> dict:
    """进入休眠：时长 ∝ 超出量 (W-θ_sleep)，夹在 [base, max]。"""
    overshoot = max(0.0, st.get('W', 0.0) - THETA_SLEEP)
    duration = SLEEP_BASE_MIN * (overshoot / DELTA_W_ACT) if DELTA_W_ACT else SLEEP_BASE_MIN
    duration = max(SLEEP_BASE_MIN, min(SLEEP_MAX_MIN, duration))
    st['mode'] = 'sleeping'
    st['sleep_started'] = _now_iso(now)
    st['wakeup_at'] = _now_iso(now + duration * 60)
    st['sleep_duration_min'] = round(duration, 1)
    return st


def check(event_type: str = 'routine', fingerprint: str = '',
          now: float = None, dry_run: bool = False,
          state: dict = None, interactive: bool = None) -> tuple:
    """唤醒判定：放行 or 抑制。

    参数：
      event_type  事件等级：'anomaly'（硬告警）可强唤醒；其余常规
      fingerprint 事件指纹（hash 字符串）：同指纹 TTL 内只唤醒一次；
                  传 '' 跳过去重
      now         测试用固定时间戳（epoch 秒）
      dry_run     不落盘（演练）
      state       注入状态（测试用）；None 时自读状态文件
      interactive 交互相位：True=用户最近有输入（抑制常规唤醒）；
                  None=自动检测会话文件 mtime

    返回 (allowed: bool, reason: str, state: dict)：
      reason: 'ok' / 'anomaly_override'（放行）
              'daytime_no_wake' / 'interactive' / 'dedup' / 'cooldown' /
              'sleeping' / 'daily_cap'（抑制）
    """
    st = state if state is not None else load_state()
    now = time.time() if now is None else now
    st = update(st, now)

    # 0) 白天禁醒窗口闸门：18:00 前禁 routine 级自主唤醒（省 token，8/6 拍板；
    #    2026-08-12 修正：没有"23:00-08:00 安静期"全静默，白天窗口 = 00:00~18:00）；
    #    anomaly 硬告警穿透（"禁 routine 级"，紧急事件类保留）
    override = (event_type == 'anomaly')
    if not override:
        try:
            hhmm_now = datetime.fromtimestamp(now).strftime('%H:%M')
            if _in_window(hhmm_now, DAY_NO_WAKE_START, DAY_NO_WAKE_END):
                st['total_suppressed'] = st.get('total_suppressed', 0) + 1
                save_state(st, dry_run=dry_run)
                return False, 'daytime_no_wake', st
        except Exception:
            pass

    # 0b) 交互相位门：dandan 最近有交互（SP_IDLE_MIN 分钟内）→ 顺延不醒
    #     （8/12 拍板：夜间"在沟通中"→ 顺延；"不在（无交互）"→ 可醒）；anomaly 穿透
    if interactive is None:
        interactive = detect_interactive(now)
    if interactive and not override:
        st['total_suppressed'] = st.get('total_suppressed', 0) + 1
        save_state(st, dry_run=dry_run)
        return False, 'interactive', st

    # 1) 去重游标：同事件只唤醒一次
    if fingerprint:
        seen = _parse_iso((st.get('dedup') or {}).get(fingerprint))
        if seen is not None and now - seen < DEDUP_TTL_DAYS * 86400:
            st['total_suppressed'] = st.get('total_suppressed', 0) + 1
            save_state(st, dry_run=dry_run)
            return False, 'dedup', st

    # 2) 休眠期：拒绝一切自主唤醒；anomaly 可强唤醒（记入成本）
    #    置于冷却之前：休眠是最强抑制状态，优先判定
    if st.get('mode') == 'sleeping' and not override:
        st['total_suppressed'] = st.get('total_suppressed', 0) + 1
        save_state(st, dry_run=dry_run)
        return False, 'sleeping', st

    # 3) 冷却期：每次唤醒后 ≥COOLDOWN_MIN 不重复唤醒；anomaly 穿透
    last_wake = _parse_iso(st.get('last_wake_at'))
    if (last_wake is not None and (now - last_wake) / 60.0 < COOLDOWN_MIN
            and not override):
        st['total_suppressed'] = st.get('total_suppressed', 0) + 1
        save_state(st, dry_run=dry_run)
        return False, 'cooldown', st

    # 3.5) 每日预算（8/7 拍板：一晚上最多 10 次）：routine 唤醒只可能发生在
    #      18:00 后（白天禁醒窗口先挡），日预算即夜间预算；anomaly 穿透。
    #      2026-08-12：移除 NIGHT_CAP/DAY_CAP 分桶（其窗口 00:30-08:30 已在
    #      白天禁醒窗口内，routine 永远用不到；保留分桶会让 18:00 后的晚间
    #      唤醒被误限到 DAY_CAP=2，违背"一晚上最多 10 次"）。
    if not override:
        today = datetime.fromtimestamp(now).strftime('%Y-%m-%d')
        daily = st.get('daily') or {}
        if daily.get('date') != today:
            daily = {'date': today, 'count': 0, 'night_count': 0, 'day_count': 0}
        if daily.get('count', 0) >= DAILY_CAP:
            st['total_suppressed'] = st.get('total_suppressed', 0) + 1
            save_state(st, dry_run=dry_run)
            return False, 'daily_cap', st
        st['daily'] = daily

    # 4) 放行：记入唤醒成本
    cost = DELTA_W_ACT + (OVERRIDE_COST if override else 0.0)
    st['W'] = st.get('W', 0.0) + cost
    st['last_wake_at'] = _now_iso(now)
    if fingerprint:
        st.setdefault('dedup', {})[fingerprint] = _now_iso(now)
        _trim_dedup(st, now)
    st['total_wakes'] = st.get('total_wakes', 0) + 1
    if override:
        st['total_overrides'] = st.get('total_overrides', 0) + 1
    else:
        # 每日预算计数（放行成功才计入；2026-08-12 起只计总量，
        # night_count/day_count 字段保留兼容旧状态文件）
        today = datetime.fromtimestamp(now).strftime('%Y-%m-%d')
        daily = st.get('daily') or {}
        if daily.get('date') != today:
            daily = {'date': today, 'count': 0, 'night_count': 0, 'day_count': 0}
        daily['count'] = daily.get('count', 0) + 1
        st['daily'] = daily
    history = st.get('history') or []
    history.append({'ts': _now_iso(now), 'event_type': event_type,
                    'cost': round(cost, 3), 'override': override,
                    'W_after': round(st['W'], 3)})
    st['history'] = history[-HISTORY_MAX:]

    # 5) 体力见底 → 强制休眠
    if st['W'] > THETA_SLEEP:
        _enter_sleep(st, now)

    save_state(st, dry_run=dry_run)
    return True, ('anomaly_override' if override else 'ok'), st


def status(st: dict = None) -> dict:
    """人类可读状态摘要（用于 metrics/日志，不含敏感信息）。"""
    st = st if st is not None else load_state()
    return {
        'W': round(st.get('W', 0.0), 3),
        'mode': st.get('mode'),
        'sleep_duration_min': st.get('sleep_duration_min'),
        'wakeup_at': st.get('wakeup_at'),
        'total_wakes': st.get('total_wakes', 0),
        'total_suppressed': st.get('total_suppressed', 0),
        'total_overrides': st.get('total_overrides', 0),
        'dedup_count': len(st.get('dedup') or {}),
        'daily': st.get('daily'),
        'daytime_no_wake_window': f"{DAY_NO_WAKE_START}~{DAY_NO_WAKE_END}",
        'daily_cap': DAILY_CAP,
    }


def main(argv=None) -> dict:
    import argparse
    p = argparse.ArgumentParser(description='sleep_pressure 体力系统 CLI')
    p.add_argument('--status', action='store_true', help='打印状态摘要')
    p.add_argument('--check', metavar='EVENT_TYPE', help='执行一次唤醒判定')
    p.add_argument('--fingerprint', default='', help='事件指纹（去重）')
    p.add_argument('--commit', action='store_true', help='落盘（默认 dry-run 不写）')
    p.add_argument('--state-file', default='', help='覆盖状态文件路径')
    args = p.parse_args(argv)
    if args.state_file:
        globals()['_STATE_FILE'] = args.state_file
    if args.status or not args.check:
        st = load_state()
        return {'state': status(st), 'raw': st}
    allowed, reason, st = check(args.check, fingerprint=args.fingerprint,
                                dry_run=not args.commit)
    return {'allowed': allowed, 'reason': reason, 'state': status(st)}


if __name__ == '__main__':
    try:
        print(json.dumps(main(), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'error': str(e)[:200]}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
