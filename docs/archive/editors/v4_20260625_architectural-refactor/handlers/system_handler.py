# handlers/system_handler.py — 系统状态/切换
# 每个函数接收 handler (HTTP handler实例) 作为第一个参数

import sys
import json
import os
import time
from utils.config import path

_M = None
def g(name): return getattr(_M, name, None) if _M else None

def handle_usage_status(handler):
    """读取 Gateway sessions.json 中的上下文用量，context tokens 从模型配置取"""
    DATA_DIR = g('DATA_DIR')
    LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
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
    cfg_path = path('CONFIG')
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
        get_session_info = g('get_session_info')
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

def handle_cache_stats(handler):
    """通过 cache_monitor 返回缓存命中统计 v2"""
    DATA_DIR = g('DATA_DIR')
    try:
        from cache_monitor import get_cache_stats as _gcs
        result = _gcs(DATA_DIR)
        return result
    except Exception as e:
        print(f"[cache-monitor] import/run failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return {"ok": False, "error": str(e)}

def handle_quickcheck(handler):
    """快速健康检查"""
    import time as _time
    now = _time.time()
    OPENCLAW_HOME = g('OPENCLAW_HOME')
    INJECT_LOCK_DIR = g('INJECT_LOCK_DIR')
    SCRIPT_DIR = g('SCRIPT_DIR')
    cron_file = os.path.join(OPENCLAW_HOME, 'cron', 'jobs.json')
    if os.path.exists(cron_file):
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
    today = _time.strftime('%Y-%m-%d')
    mem_dir = os.path.join(SCRIPT_DIR, '..', 'memory')
    md = os.path.join(mem_dir, f'{today}.md')
    mem_st = f'{today}.md OK({os.path.getsize(md)//100}K)' if os.path.exists(md) else f'{today}.md missing'
    dg = path('DIGEST_OUT')
    dig_st = f'{int((now-os.path.getmtime(dg))/60)}min ago' if os.path.exists(dg) else 'never'
    return {'ok': True, 'timestamp': _time.strftime('%H:%M:%S'),
            'editor': 'alive', 'cron': cron_st, 'inject': inj_st,
            'memory': mem_st, 'lastDigest': dig_st}

def handle_list_subagents(handler):
    """从 sessions.json 读取所有活跃子代理，动态追踪"""
    DATA_DIR = g('DATA_DIR')
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

def handle_thinking_toggle(handler):
    """切换思考模式：off→medium→high→off 循环"""
    try:
        body_len = int(handler.headers.get('Content-Length', 0))
        body = json.loads(handler.rfile.read(body_len))
        
        # 读取当前 thinkingLevel，决定下一个状态
        ss_path = path('SESSIONS_JSON') or "/vol1/@apphome/trim.openclaw/data/home/.openclaw/agents/main/sessions/sessions.json"
        current = "off"
        try:
            with open(ss_path) as f:
                ss = json.load(f)
            sess = ss.get("agent:main:main", {})
            current = sess.get("thinkingLevel", "off")
        except:
            pass
        
        # 循环：off → medium → high → off
        cycle = {"off": "medium", "medium": "high", "high": "off"}
        mode = cycle.get(current, "high")
        
        get_session_info = g('get_session_info')
        inject_via_websocket = g('inject_via_websocket')
        sk, _ = get_session_info()
        if sk:
            result = inject_via_websocket(sk, f"/think {mode}")
            handler._send_json(200, {"ok": True, "mode": mode, "previous": current})
        else:
            handler._send_json(200, {"ok": False, "error": "无法获取当前会话"})
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})

def handle_weaponry_toggle(handler):
    """切换武器库对线开关"""
    try:
        body_len = int(handler.headers.get('Content-Length', 0))
        body = json.loads(handler.rfile.read(body_len))
        enable = body.get('enable', True)
        
        CRON_JSON = path('CRON_JSON')
        with open(CRON_JSON) as f:
            data = json.load(f)
        for j in data.get("jobs", []):
            if "武器库" in j.get("name", ""):
                j["enabled"] = enable
                break
        with open(CRON_JSON, 'w') as f:
            json.dump(data, f, indent=2)
        
        handler._send_json(200, {"ok": True, "enabled": enable})
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})
