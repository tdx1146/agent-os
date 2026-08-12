#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自主唤醒模块测试（2026-08-06 初版 / 2026-08-12 唤醒策略修正版）。
覆盖：salience 判据（惊讶度突变触发 / 持续高熵不触发 / anomaly 不再硬直通）、
sleep_pressure（白天禁醒窗口 / 夜间交互相位顺延 / 冷却 / 去重 / 休眠 /
每日预算 / override）、first_sight（摘要生成）。
运行：python3 test_awaken.py
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import salience_gate as sg
import sleep_pressure as sp
import first_sight as fs

FAILS = []


def check(name, cond, detail=""):
    mark = "✅" if cond else "❌"
    print(f"{mark} {name} {detail}")
    if not cond:
        FAILS.append(name)


def ts(hhmm: str) -> float:
    """HH:MM → 今天对应时刻的 epoch（固定时间戳，测试与真实时刻无关）。"""
    now = datetime.datetime.now()
    h, m = map(int, hhmm.split(':'))
    return datetime.datetime(now.year, now.month, now.day, h, m, 0).timestamp()


# 平静基线窗口（有微小方差，σ>0 才能算 z-score）
CALM_WINDOW = [0.03, 0.04, 0.05, 0.06, 0.05, 0.04, 0.05, 0.06, 0.04, 0.05]


# ── 1. salience 判据（2026-08-12：突变信号，非持续高熵）─────────────────
def test_salience():
    # 1.1 无突变的 anomaly（漂移告警=持续态）→ 不 salient（anomaly 不再硬直通）
    v = sg.judge(event_type="anomaly",
                 metrics={"last_surprise": 0.04, "entropy_ratio": 0.95,
                          "purpose_coherence": 0.95},
                 dry_run=True)
    check("anomaly 无突变不唤醒", not v["salient"] and not v["hard_bypass"],
          f"score={v['score']}")

    # 1.2 持续高熵（3 连）不触发（兴奋睡不着，不是醒）
    prev = None
    results = []
    for _ in range(3):
        prev = sg.judge(event_type="routine",
                        metrics={"last_surprise": 0.05, "entropy_ratio": 0.95,
                                 "purpose_coherence": 0.95},
                        dry_run=True, state=prev)
        results.append(prev)
    check("持续高熵不唤醒", not results[-1]["salient"],
          f"streak={results[-1]['entropy_streak']} score={results[-1]['score']}")

    # 1.3 惊讶度 z-score 突变（平静基线 + 突刺）→ salient + rising_edge（梦中惊醒）
    st = sg.load_state()
    st['surprise_window'] = list(CALM_WINDOW)
    st['last_salient'] = False
    v = sg.judge(event_type="routine",
                 metrics={"last_surprise": 0.60, "entropy_ratio": 0.60,
                          "purpose_coherence": 0.95},
                 dry_run=True, state=st)
    check("惊讶度突变→唤醒", v["salient"] and v["rising_edge"],
          f"z={v['z']} score={v['score']}")

    # 1.4 正常态不唤醒（低熵低惊讶例行）
    v = sg.judge(event_type="routine",
                 metrics={"last_surprise": 0.03, "entropy_ratio": 0.6,
                          "purpose_coherence": 0.95},
                 dry_run=True)
    check("正常态不唤醒", not v["salient"], f"score={v['score']}")

    # 1.5 事件权重
    check("anomaly 权重>routine",
          sg.event_weight("anomaly") > sg.event_weight("routine"))

    # 1.6 anomaly + 突变 → salient（硬告警配合真突变才醒）
    st = sg.load_state()
    st['surprise_window'] = list(CALM_WINDOW)
    st['last_salient'] = False
    v = sg.judge(event_type="anomaly",
                 metrics={"last_surprise": 0.60, "entropy_ratio": 0.95,
                          "purpose_coherence": 0.90},
                 dry_run=True, state=st)
    check("anomaly+突变→唤醒", v["salient"] and v["z"] is not None,
          f"score={v['score']}")


# ── 2. sleep_pressure 体力系统 ────────────────────────────────
def test_sleep_pressure():
    DAY = ts('14:00')      # 白天（18:00 前，白天禁醒窗口内）
    NIGHT = ts('22:00')    # 夜间（18:00 后）

    # 2.1 白天禁醒窗口：routine 在 18:00 前被挡（token 贵，8/6 拍板）
    st = sp.default_state()
    allowed, reason, st = sp.check(event_type="routine", fingerprint="e1",
                                   state=st, dry_run=True, interactive=False,
                                   now=DAY)
    check("白天 routine 禁醒", not allowed and reason == "daytime_no_wake",
          f"reason={reason}")

    # 2.2 白天 anomaly 仍可穿透（"禁 routine 级"，紧急类保留）
    st = sp.default_state()
    allowed, reason, st = sp.check(event_type="anomaly", fingerprint="e1",
                                   state=st, dry_run=True, interactive=False,
                                   now=DAY)
    check("白天 anomaly 穿透", allowed and reason == "anomaly_override",
          f"reason={reason}")

    # 2.3 夜间无交互 → 允许醒（8/12：不在 → 可醒）
    st = sp.default_state()
    allowed, reason, st = sp.check(event_type="routine", fingerprint="e0",
                                   state=st, dry_run=True, interactive=False,
                                   now=NIGHT)
    check("夜间无交互可醒", allowed and reason == "ok", f"reason={reason}")

    # 2.4 夜间 dandan 在沟通中 → 顺延不醒（8/12）
    st = sp.default_state()
    allowed, reason, st = sp.check(event_type="routine", fingerprint="e0",
                                   state=st, dry_run=True, interactive=True,
                                   now=NIGHT)
    check("夜间交互顺延", not allowed and reason == "interactive",
          f"reason={reason}")

    # 2.5 冷却期抑制（routine 事件，非 anomaly）
    st = sp.default_state()
    allowed, _, st = sp.check(event_type="routine", fingerprint="e0",
                              state=st, dry_run=True, interactive=False,
                              now=NIGHT)
    allowed, reason, st = sp.check(event_type="routine", fingerprint="e1",
                                   state=st, dry_run=True, interactive=False,
                                   now=NIGHT)
    check("冷却期抑制", not allowed and reason == "cooldown", f"reason={reason}")

    # 2.6 去重（同指纹）
    st = sp.default_state()
    allowed, _, st = sp.check(event_type="anomaly", fingerprint="e1",
                              state=st, dry_run=True, interactive=False,
                              now=NIGHT)
    allowed, reason, st = sp.check(event_type="anomaly", fingerprint="e1",
                                   state=st, dry_run=True, interactive=False,
                                   now=NIGHT)
    check("去重抑制", not allowed and reason == "dedup", f"reason={reason}")

    # 2.7 休眠（W 超标放行后进入休眠，后续被抑制）
    st = sp.default_state()
    st["last_update"] = sp._now_iso(NIGHT)   # 对齐测试时钟，避免按真实时钟衰减
    st["W"] = 0.75          # 超过 θ_sleep(0.7)
    allowed, reason, st = sp.check(event_type="routine", fingerprint="",
                                   state=st, dry_run=True, interactive=False,
                                   now=NIGHT)
    check("W超标放行后进入休眠", allowed and st["mode"] == "sleeping",
          f"mode={st['mode']} reason={reason}")
    allowed, reason, st = sp.check(event_type="routine", fingerprint="",
                                   state=st, dry_run=True, interactive=False,
                                   now=NIGHT)
    check("休眠期抑制", not allowed and reason == "sleeping", f"reason={reason}")
    allowed, reason, st = sp.check(event_type="anomaly", fingerprint="",
                                   state=st, dry_run=True, interactive=False,
                                   now=NIGHT)
    check("休眠期 anomaly override", allowed and reason == "anomaly_override",
          f"reason={reason}")

    # 2.8 每日预算 10 次/日（8/7 拍板：一晚上最多 10 次）
    today = datetime.datetime.fromtimestamp(NIGHT).strftime('%Y-%m-%d')
    st = sp.default_state()
    st['daily'] = {'date': today, 'count': 10, 'night_count': 0, 'day_count': 0}
    allowed, reason, st = sp.check(event_type="routine", fingerprint="",
                                   state=st, dry_run=True, interactive=False,
                                   now=NIGHT)
    check("每日预算上限", not allowed and reason == "daily_cap", f"reason={reason}")

    # 2.9 日预算 anomaly 穿透
    st = sp.default_state()
    st['daily'] = {'date': today, 'count': 10, 'night_count': 0, 'day_count': 0}
    allowed, reason, st = sp.check(event_type="anomaly", fingerprint="",
                                   state=st, dry_run=True, interactive=False,
                                   now=NIGHT)
    check("预算 anomaly 穿透", allowed and reason == "anomaly_override",
          f"reason={reason}")


def test_phase_gate():
    """交互相位门（dandan 设计：不打扰正在上班的人；8/12：沟通中顺延）"""
    NIGHT = ts('22:00')
    st = sp.default_state()
    a, r, st = sp.check(event_type="routine", fingerprint="", state=st,
                        dry_run=True, interactive=True, now=NIGHT)
    check("交互期 routine 顺延", not a and r == "interactive", f"reason={r}")
    a, r, st = sp.check(event_type="anomaly", fingerprint="", state=st,
                        dry_run=True, interactive=True, now=NIGHT)
    check("交互期 anomaly 穿透", a and r == "anomaly_override", f"reason={r}")
    st = sp.default_state()
    a, r, st = sp.check(event_type="routine", fingerprint="", state=st,
                        dry_run=True, interactive=False, now=NIGHT)
    check("空闲期 routine 放行", a and r == "ok", f"reason={r}")


# ── 3. first_sight 摘要 ───────────────────────────────────────
def test_first_sight():
    s = fs.build(max_chars=500)
    check("first_sight 生成摘要", isinstance(s, str) and len(s) > 0,
          f"{len(s) if s else 0} 字")
    if s:
        check("摘要含回魂标记", "回魂" in s or "熵" in s)
        check("摘要≤500字", len(s) <= 520)


if __name__ == "__main__":
    test_salience()
    test_sleep_pressure()
    test_phase_gate()
    test_first_sight()
    print("-" * 40)
    if FAILS:
        print(f"❌ 失败 {len(FAILS)} 项: {FAILS}")
        sys.exit(1)
    print("✅ 全部通过")
