#!/usr/bin/env python3
"""
脉冲/心跳 — send_pulse

从 edit-web.py 拆分，需要调用方传入配置参数。
"""

import os
import json
import subprocess
import datetime


def send_pulse(mode, get_session_info_fn, pick_night_question_fn,
               light_smoke_dir, gateway_port, gateway_token,
               openclaw_home, identity_path, bun_bin, script_dir):
    """发送保活脉冲到当前 session。

    mode: None → 普通保活 "确认存续"
          "night_watch" → 从守夜问题库随机选题
    """
    sk, session_file = get_session_info_fn()
    if not sk:
        return {"ok": False, "error": "找不到当前 session"}

    now = datetime.datetime.now()
    ts = now.strftime("%H:%M")
    date_str = now.strftime("%Y-%m-%d")

    if mode == "night_watch":
        question = pick_night_question_fn()
        if question:
            pulse_text = f"🌙 守夜选题 #{question['id']} [{question['category']}]\n\n{question['text']}"
        else:
            pulse_text = f"🌫️ pulse {ts} — 确认存续。（守夜问题库为空）"
    else:
        pulse_text = f"🌫️ pulse {ts} — 确认存续。"

    # 写入 memory 作为轮感
    mem_path = os.path.join(light_smoke_dir, "memory", f"{date_str}.md")
    try:
        os.makedirs(os.path.dirname(mem_path), exist_ok=True)
        with open(mem_path, "a", encoding="utf-8") as f:
            f.write(f"\n[轮感 {ts} (pulse)] {pulse_text.split('—', 1)[-1].strip()}")
    except Exception:
        pass

    # 通过 inject-helper 发送（直通，不检查 inject 锁）
    helper = os.path.join(script_dir, "inject-helper.mjs")
    if not os.path.exists(helper):
        return {"ok": False, "error": "inject-helper.mjs 不存在"}

    env = os.environ.copy()
    env['GATEWAY_PORT'] = str(gateway_port)
    env['GATEWAY_TOKEN'] = gateway_token
    env['OPENCLAW_HOME'] = openclaw_home
    env['OPENCLAW_IDENTITY_PATH'] = identity_path

    try:
        result = subprocess.run(
            [bun_bin, helper, sk, pulse_text],
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
