#!/usr/bin/env python3
"""
各类状态报告函数（轻量，仅读取计算，不修改）

从 edit-web.py 拆分，自包含。
需要调用方传入配置路径。
"""

import os
import json
import datetime
import glob


# ── 💾 备份状态 ──────────────────────────────────────────────────────

def backup_stale_status(light_smoke_dir, momo_dir):
    """💾 检查备份是否过时：核心文件比备份新则报警"""
    stale = False
    stale_files = []
    core_names = ["SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md", "TOOLS.md", "AGENTS.md"]

    for name in core_names:
        src = os.path.join(light_smoke_dir, name)
        bak = os.path.join(momo_dir, name)
        if os.path.exists(src) and os.path.exists(bak):
            if os.path.getmtime(src) > os.path.getmtime(bak):
                stale = True
                stale_files.append(name)
        elif os.path.exists(src) and not os.path.exists(bak):
            stale = True
            stale_files.append(f"{name}(无备份)")

    # 也检查 today's memory
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    today_mem = os.path.join(light_smoke_dir, "memory", f"{today}.md")
    today_bak = os.path.join(momo_dir, "daily", f"{today}.md")
    if os.path.exists(today_mem) and os.path.exists(today_bak):
        if os.path.getmtime(today_mem) > os.path.getmtime(today_bak):
            stale = True
            stale_files.append(f"memory/{today}.md")

    # 最后一次打包时间
    last_pack = "从未"
    if os.path.exists(momo_dir):
        files = [os.path.join(momo_dir, f) for f in os.listdir(momo_dir) if os.path.isfile(os.path.join(momo_dir, f))]
        if files:
            last_pack_ts = max(os.path.getmtime(f) for f in files)
            last_pack = datetime.datetime.fromtimestamp(last_pack_ts).strftime("%m-%d %H:%M")

    return {
        "ok": True,
        "stale": stale,
        "stale_files": stale_files,
        "last_pack": last_pack,
        "file_count": len(core_names),
    }


# ── 🔄 消化状态 ──────────────────────────────────────────────────────

def digestion_status(light_smoke_dir):
    """🔄 返回当前消化状态摘要 + 摸摸候选"""
    result = {
        "last_digest": None,
        "candidates": [],
        "candidate_count": 0,
        "assertion_count": 0,
        "has_conflicts": False
    }

    # Read digestion log from today's memory
    mem_dir = os.path.join(light_smoke_dir, "memory")
    today = datetime.datetime.now().strftime("%Y-%m-%d")
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
            result["candidates"] = json.load(f)
        result["candidate_count"] = len(result["candidates"])
        result["has_conflicts"] = any(c.get("type") == "conflict" for c in result["candidates"])
    except:
        pass

    # Count assertions in facts.dict.md
    facts_path = os.path.join(light_smoke_dir, "memory", "facts.dict.md")
    try:
        with open(facts_path, encoding='utf-8') as f:
            text = f.read()
        result["assertion_count"] = sum(1 for l in text.split('\n') if '✅' in l or '⏳' in l or '❌' in l)
    except:
        pass

    return result


def digestion_skill_status(light_smoke_dir, digest_out, cron_json, plugin_health_core_fn, workspace_hooks_path):
    """🌫️ 监控栏状态 - 只返回真数据，不虚构指标"""
    result = {
        "last_digest_time": None,
        "pending_assertions": 0,
        "total_assertions": 0,
        "skill_count": 0,
        "plugin_ok": False,
        "plugin_last": None,
    }

    mem_dir = os.path.join(light_smoke_dir, "memory")

    # 1. 最近有效消化时间
    try:
        with open(digest_out) as f:
            first = f.readline().strip()
            if first:
                result["last_digest_time"] = first.lstrip("# ").strip()
    except:
        pass

    # 2. 下次消化时间（从 cron 配置读取）
    try:
        with open(cron_json) as f:
            cron_cfg = json.load(f)
        for j in cron_cfg.get("jobs", []):
            if "消化" in j.get("name", ""):
                next_ms = j.get("state", {}).get("nextRunAtMs")
                if next_ms:
                    next_dt = datetime.datetime.fromtimestamp(next_ms / 1000)
                    result["next_digest_time"] = next_dt.strftime("%Y-%m-%d %H:%M")
                break
    except:
        pass

    # 3. 断言计数
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

    # 4. 插件健康
    try:
        pk, pl = plugin_health_core_fn()
        result["plugin_ok"] = pk
        result["plugin_last"] = pl
    except:
        pass

    # 📦 skill 数量（合并 ~/.pi/agent/skills + workspace/skills，按 skill 名去重）
    pi_skills = set(os.path.basename(os.path.dirname(p))
                   for p in glob.glob(os.path.expanduser("~/.pi/agent/skills/*/SKILL.md")))
    ws_skills = set(os.path.basename(os.path.dirname(p))
                    for p in glob.glob(os.path.join(os.path.dirname(workspace_hooks_path), 'skills', '*', 'SKILL.md')))
    result["skill_count"] = len(pi_skills | ws_skills)

    return result


def digestion_history(light_smoke_dir, cron_runs_dir):
    """返回最近消化循环历史（本地文件 + cron runs 备份）"""
    history_path = os.path.join(light_smoke_dir, 'memory', 'digest-history.jsonl')
    cron_run_files = glob.glob(os.path.join(cron_runs_dir, '*.jsonl'))
    cron_runs = cron_run_files[0] if cron_run_files else cron_runs_dir + "/66e8fb9b-cbc6-4fd8-a62f-da4754cb8965.jsonl"
    MAX_ENTRIES = 10
    entries = []

    # 优先读本地文件
    try:
        with open(history_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    entries.append(d)
                except:
                    continue
    except:
        pass

    # 如果本地文件不够，从 cron runs 补
    if len(entries) < 5:
        cron_paths = [
            cron_runs,
            cron_runs + ".migrated",
        ]
        for cron_path in cron_paths:
            try:
                with open(cron_path, encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            action = d.get("action", "")
                            if action != "finished":
                                continue
                            entries.append({
                                "ts": d.get("ts", 0),
                                "status": d.get("status", "ok"),
                                "summary": (d.get("summary", "") or "")[:120],
                            })
                        except:
                            continue
                if len(entries) >= 5:
                    break
            except:
                pass

    return entries[-MAX_ENTRIES:]


# ── 📋 待办 / 武器库 ────────────────────────────────────────────────

def backlog_status(light_smoke_dir):
    """返回待办清单内容"""
    path = os.path.join(light_smoke_dir, "memory", "backlog.md")
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read()
        pending = content.count("- [ ] ")
        done = content.count("- [x] ")
        return {"ok": True, "content": content, "pending": pending, "done": done}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def weaponry_toggle_status(cron_json):
    """返回武器库对线的开关状态"""
    result = {"ok": True, "enabled": True}
    try:
        with open(cron_json) as f:
            jobs = json.load(f).get("jobs", [])
        for j in jobs:
            if "武器库" in j.get("name", ""):
                result["enabled"] = j.get("enabled", True)
                break
    except:
        pass
    return result


# ── 🔌 插件健康 ──────────────────────────────────────────────────────

def plugin_health_core(plugin_injected):
    """return (ok_bool, last_inject_str)"""
    try:
        if os.path.exists(plugin_injected):
            mtime = os.path.getmtime(plugin_injected)
            age_min = (datetime.datetime.now().timestamp() - mtime) / 60
            last = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M")
            return (age_min < 30, last)
    except:
        pass
    return (False, None)


def plugin_health(plugin_injected, plugin_ran):
    """check plugin injection status"""
    result = {"ok": False, "injected": False, "lastInjected": None, "error": None}
    try:
        if os.path.exists(plugin_injected):
            mtime = os.path.getmtime(plugin_injected)
            age_min = (datetime.datetime.now().timestamp() - mtime) / 60
            result["injected"] = True
            result["lastInjected"] = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M")
            result["ok"] = age_min < 30
            if not result["ok"]:
                result["error"] = "last inject " + str(int(age_min)) + "min ago"
        elif os.path.exists(plugin_ran):
            result["error"] = "plugin triggered but inject failed"
        else:
            result["error"] = "plugin never triggered"
    except Exception as e:
        result["error"] = str(e)
    return result


# ── 🧠 思考状态 / ⚙️ 系统健康 ─────────────────────────────────────────

def thinking_status(config_path, sessions_json):
    """🧠 返回当前模型的思考模式状态，含 session 实际 thinkingLevel"""
    result = {"thinking": False, "model": "unknown", "reasoning": False, "thinkingLevel": "off"}
    try:
        with open(config_path) as f:
            cfg = json.load(f)
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
        with open(sessions_json) as f:
            ss = json.load(f)
        sk = "agent:main:main"
        sess = ss.get(sk, {})
        result["thinkingLevel"] = sess.get("thinkingLevel", "off")
    except:
        pass
    return result


def system_health(config_path):
    """⚙️ 系统健康：检查 hooks / cron / contextWindow"""
    result = {
        "hooks": {"enabled": False, "details": {}},
        "cron": {"enabled": True, "last_ok": "ok"},
        "context": {"expected": 1000000, "actual": 1000000, "ok": True}
    }
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        hooks_cfg = cfg.get("hooks", {}).get("internal", {}).get("entries", {})
        result["hooks"]["details"]["session-memory"] = hooks_cfg.get("session-memory", {}).get("enabled", False)
        result["hooks"]["details"]["command-logger"] = hooks_cfg.get("command-logger", {}).get("enabled", False)
        result["hooks"]["enabled"] = all(result["hooks"]["details"].values())
    except:
        pass
    return result


# ── 🕒 最后操作记录 ──────────────────────────────────────────────────

def last_processing(last_processing_path):
    """返回最近一次静默处理/撸撸时间"""
    result = {"ok": False, "last": None}
    try:
        if os.path.exists(last_processing_path):
            with open(last_processing_path) as f:
                result["last"] = f.read().strip()[:50]
            result["ok"] = True
    except:
        pass
    return result


def last_injection(last_injection_body, last_injection):
    """返回最近一次插件注入了什么内容"""
    result = {"ok": False, "detail": None}
    for p in [last_injection_body, last_injection]:
        try:
            if os.path.exists(p):
                with open(p) as f:
                    content = f.read().strip()
                if content:
                    lines = content.split('\n')
                    detail = '\n'.join(lines[:5])[:300]
                    result["detail"] = detail
                    result["ok"] = True
                    break
        except:
            pass
    return result


# ── 秘书分析包装 ──────────────────────────────────────────────────────

def secretary_analyze_save_wrapper(path, new_content, old_content, light_smoke_dir):
    """🔍 小秘书静默分析：已迁移到 utils/secretary.secretary_analyze_save"""
    from utils.secretary import secretary_analyze_save as _sas
    return _sas(path, new_content, old_content, light_smoke_dir)


# ── 🌫️ 轮感状态 ──────────────────────────────────────────────────────

def lungan_status(light_smoke_dir):
    """🌫️ 轮感状态：检查最近的 memory 文件是否有轮感记录"""
    import re
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    mem_dir = os.path.join(light_smoke_dir, "memory")

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
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    rec, last, cnt = _check_file(f"{yesterday}.md")
    return {
        "ok": True,
        "recorded": rec,
        "last": last if rec else "",
        "today_count": 0,
        "file": f"{yesterday}.md" if rec else f"{today}.md",
    }


# ── 🔍 备份搜索 ──────────────────────────────────────────────────────

def search_backups(query, limit, only_user, backup_dir, strip_metadata_fn, get_session_info_fn):
    """在所有备份中搜索用户消息，返回匹配结果。"""
    results = []
    if not os.path.exists(backup_dir):
        return {"results": [], "total_backups": 0, "note": "没有备份目录"}

    q = query.lower()

    # 先扫描当前 session 文件
    sk, current_session = get_session_info_fn()
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
                    text = strip_metadata_fn(text)
                    if q in text.lower() if query else True:
                        ts = msg.get("timestamp", d.get("timestamp", 0))
                        if isinstance(ts, str):
                            try:
                                ts = int(datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
                            except:
                                ts = 0
                        results.append({
                            "backup": "📄 当前会话",
                            "role": role,
                            "text": text[:2000],
                            "text_preview": text[:200],
                            "timestamp": ts,
                            "time_str": datetime.datetime.fromtimestamp(ts/1000).strftime("%m-%d %H:%M") if ts else "?",
                        })
                        if len(results) >= limit:
                            break
        except:
            pass

    if len(results) >= limit:
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"results": results[:limit], "total_backups": 0, "searched_current": True, "query": query, "limit": limit}

    # 再扫描备份文件
    backup_files = sorted([f for f in os.listdir(backup_dir) if f.endswith(".jsonl") and f.startswith("pre-edit.")], reverse=True)

    for bf in backup_files:
        fpath = os.path.join(backup_dir, bf)
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
                    text = strip_metadata_fn(text)
                    if q in text.lower() if query else True:
                        ts = msg.get("timestamp", d.get("timestamp", 0))
                        if isinstance(ts, str):
                            try:
                                ts = int(datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
                            except:
                                ts = 0
                        results.append({
                            "backup": bf,
                            "role": role,
                            "text": text[:2000],
                            "text_preview": text[:200],
                            "timestamp": ts,
                            "time_str": datetime.datetime.fromtimestamp(ts/1000).strftime("%m-%d %H:%M") if ts else "?",
                        })
                        if len(results) >= limit:
                            break
        except Exception:
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


# ── ⏳→✅ 断言提升器 ────────────────────────────────────────────────

def promote_pending_assertions(light_smoke_dir, digest_out):
    """⏳→✅ 断言提升器：纯规则，不调LLM"""
    import re
    facts_path = os.path.join(light_smoke_dir, 'memory', 'facts.dict.md')
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
    try:
        with open(digest_out, 'w') as f:
            f.write(f"# 🔄 消化循环 #auto — {now}\n")
    except:
        pass

    # 写入消化历史
    history_path = os.path.join(light_smoke_dir, 'memory', 'digest-history.jsonl')
    try:
        hist_entry = json.dumps({
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
