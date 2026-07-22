#!/usr/bin/env python3
"""
子代理管理 — spawn / exec / log / history

从 edit-web.py 拆分，需要调用方传入配置参数。
"""

import json
import os
import subprocess
import time
import requests


def spawn_subagent_process(task, model, timeout, get_session_info, gateway_port, gateway_token, openclaw_home, identity_path, bun_bin, script_dir):
    """通过 inject-helper 的 Gateway 连接 spawn 子代理"""
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

    helper = os.path.join(script_dir, "inject-helper.mjs")
    env = os.environ.copy()
    env['GATEWAY_PORT'] = str(gateway_port)
    env['GATEWAY_TOKEN'] = gateway_token
    env['OPENCLAW_HOME'] = openclaw_home
    env['OPENCLAW_IDENTITY_PATH'] = identity_path
    try:
        result = subprocess.run(
            [bun_bin, helper, sk, spawn_rpc],
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

EXEC_MODELS = {
    'deepseek-chat': {'url': 'https://api.deepseek.com/chat/completions', 'key': 'sk-c3ae891c6b8c42b89d4ea3a0145e8db0', 'provider': 'DeepSeek'},
    'GLM-Z1-Flash': {'url': 'https://open.bigmodel.cn/api/paas/v4/chat/completions', 'key': '39ff03af4cac4cd6989d04ad6dcb32f1.p3RL1Jvpmw0Kpqxf', 'provider': 'GLM'},
    'hunyuan-instruct': {'url': 'https://api.hunyuan.cloud.tencent.com/v1/chat/completions', 'key': 'sk-8rfLwQYk27HrKShpQNyZqCLbq9h9UCaYQXdMEaK3XggpAoJe', 'provider': '混元', 'model': 'hunyuan-2.0-instruct-20251111'},
    'hunyuan-thinking': {'url': 'https://api.hunyuan.cloud.tencent.com/v1/chat/completions', 'key': 'sk-8rfLwQYk27HrKShpQNyZqCLbq9h9UCaYQXdMEaK3XggpAoJe', 'provider': '混元', 'model': 'hunyuan-2.0-thinking-20251109'},
}


def exec_subagent(task, model, timeout, history_path, workdir):
    """直接调 API 执行子代理任务。返回结果 dict。"""
    if model not in EXEC_MODELS:
        return {"ok": False, "error": f"未知模型: {model}"}
    cfg = EXEC_MODELS[model]
    start = time.time()
    os.makedirs(workdir, exist_ok=True)
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
            log_subagent(model, task[:100], elapsed, 0, 0, "failed", resp.text[:200], history_path)
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
        log_subagent(model, task[:100], elapsed, inp, out, "completed", content[:200], history_path)
        return result
    except Exception as e:
        elapsed = time.time() - start
        log_subagent(model, task[:100], elapsed, 0, 0, "error", str(e)[:200], history_path)
        return {"ok": False, "error": str(e)}


def log_subagent(model, task_preview, elapsed, inp, out, status, result_preview, history_path):
    """记录子代理执行日志"""
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    entry = json.dumps({
        "ts": time.time(),
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "model": model,
        "task": task_preview,
        "elapsed": round(elapsed, 1),
        "input": inp,
        "output": out,
        "status": status,
        "result": result_preview
    }, ensure_ascii=False)
    with open(history_path, 'a', encoding='utf-8') as f:
        f.write(entry + '\n')


def get_subagent_history(limit, history_path):
    """获取子代理执行历史"""
    if not os.path.exists(history_path):
        return []
    entries = []
    with open(history_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except:
                    pass
    return entries[-limit:]
