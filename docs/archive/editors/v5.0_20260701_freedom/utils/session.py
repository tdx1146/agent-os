#!/usr/bin/env python3
"""
会话文件读写
"""
import json, os, time, shutil

def discover_session_dir(openclaw_home):
    agents_dir = os.path.join(openclaw_home, "agents")
    if not os.path.exists(agents_dir):
        return None
    for entry in os.listdir(agents_dir):
        sessions_path = os.path.join(agents_dir, entry, "sessions")
        if os.path.isdir(sessions_path):
            return sessions_path
    return None

def get_session_info(data_dir):
    """从 sessions.json 获取主 session，返回 sessionKey 和 sessionFile 路径"""
    sessions_file = os.path.join(data_dir, "sessions.json")
    if not os.path.exists(sessions_file):
        return {"ok": False, "error": "no sessions.json"}
    with open(sessions_file) as f:
        store = json.load(f)
    main = store.get("agent:main:main")
    if main:
        sid = main.get("sessionId") if isinstance(main, dict) else main
        if isinstance(sid, str):
            fpath = os.path.join(data_dir, sid + ".jsonl")
        else:
            fpath = None
        if fpath and os.path.exists(fpath):
            return {"ok": True, "sessionKey": "agent:main:main", "sessionFile": fpath}
        return {"ok": True, "sessionKey": "agent:main:main", "sessionFile": fpath or str(main)}
    for k, v in store.items():
        if v:
            sid = v.get("sessionId") if isinstance(v, dict) else v
            fpath = os.path.join(data_dir, sid + ".jsonl") if isinstance(sid, str) else None
            return {"ok": True, "sessionKey": k, "sessionFile": fpath or str(v)}
    return {"ok": False, "error": "no active session"}

def read_session(session_file, max_messages=200):
    messages = []
    if not os.path.exists(session_file):
        return messages
    # Single binary read: count lines AND tail-read in one pass
    with open(session_file, "rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        # If file is small enough, just read it all
        if file_size < 1024 * 1024:  # 1MB threshold
            f.seek(0)
            raw = f.read().decode("utf-8", errors="replace")
            lines = [l for l in raw.split("\n") if l.strip()]
        else:
            # Estimate line count from file size (assume ~1.6KB/line avg)
            est_lines = file_size / 1600
            need_tail = est_lines > max_messages * 2
            tail_n = int(max_messages * 3) if need_tail else 0
            if need_tail:
                lines = []
                chunk = 8192
                pos = file_size
                buf = b""
                while pos > 0 and len(lines) < tail_n:
                    read_size = min(chunk, pos)
                    pos -= read_size
                    f.seek(pos)
                    chunk_data = f.read(read_size)
                    buf = chunk_data + buf
                    parts = buf.decode("utf-8", errors="replace").split("\n")
                    if pos > 0:
                        buf = chunk_data[:1]  # keep one byte for boundary
                        lines = parts[1:] + lines
                    else:
                        lines = parts + lines
                    # Trim buffer to avoid unbounded memory
                    if len(lines) > tail_n * 2:
                        lines = lines[-tail_n:]
                lines = [l for l in lines if l][-tail_n:]
            else:
                f.seek(0)
                raw = f.read().decode("utf-8", errors="replace")
                lines = [l for l in raw.split("\n") if l.strip()]
    for line in lines:
        try:
            entry = json.loads(line)
        except:
            continue
        msg = entry.get("message", {})
        if msg.get("role") and msg.get("content"):
            msg["_raw_entry"] = entry
            messages.append(msg)
    return messages

def group_into_pairs(messages):
    pairs = []
    current_user = None
    current_assistants = []
    for msg in messages:
        role = msg.get("role")
        if role == "user":
            if current_user:
                pairs.append({"user": current_user, "assistants": current_assistants})
                current_assistants = []
            current_user = msg
        elif role == "assistant":
            current_assistants.append(msg)
    if current_user:
        pairs.append({"user": current_user, "assistants": current_assistants})
    return pairs

def edit_message(session_file, user_index, new_text, backup_dir):
    backup_path = None
    try:
        os.makedirs(backup_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"pre-edit.{stamp}.jsonl")
        shutil.copy2(session_file, backup_path)
    except:
        pass
    with open(session_file, "r") as f:
        lines = f.readlines()
    target_idx = -1
    for i, line in enumerate(lines):
        try:
            entry = json.loads(line)
        except:
            continue
        msg = entry.get("message", {})
        if msg.get("role") == "user":
            target_idx += 1
            if target_idx == user_index:
                entry["message"]["content"] = new_text
                lines[i] = json.dumps(entry, ensure_ascii=False) + "\n"
                with open(session_file, "w") as f:
                    f.writelines(lines)
                return {"ok": True, "message": "已修改", "backup": backup_path}
    return {"ok": False, "error": "未找到目标消息", "backup": backup_path}


# ── 编辑器中当前选中的会话 key ─────────────────────────────────

_active_editor_session_key = None

def set_active_session_key(key):
    global _active_editor_session_key
    _active_editor_session_key = key

def get_active_session_key():
    return _active_editor_session_key


def list_all_sessions(data_dir):
    """列出所有用户对话会话（含孤儿文件扫描）。
    从 sessions.json 读取 + 扫描目录中未被注册但包含用户对话的 .jsonl 文件。
    """
    import glob
    sessions = []
    seen_files = set()
    
    store_file = os.path.join(data_dir, "sessions.json")
    if os.path.exists(store_file):
        with open(store_file) as f:
            store = json.load(f)
        for k, v in store.items():
            if ':cron:' in k or ':subagent:' in k or ':test-' in k or ':dreaming-' in k or ':elevated-' in k:
                continue
            sf = v.get("sessionFile", "")
            if not sf or not os.path.exists(sf):
                continue
            seen_files.add(os.path.basename(sf))
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
    
    try:
        all_jsonl = glob.glob(os.path.join(data_dir, "*.jsonl"))
        for fp in all_jsonl:
            if fp.endswith('.trajectory.jsonl') or '.checkpoint.' in fp:
                continue
            basename = os.path.basename(fp)
            if basename in seen_files:
                continue
            try:
                with open(fp) as fh:
                    lines = fh.readlines(16384)
                user_count = sum(1 for l in lines if '"role": "user"' in l)
                if user_count < 3:
                    continue
                total_lines = len(lines)
                mtime = os.path.getmtime(fp)
                sessions.append({
                    "sessionKey": f"orphan:{basename}",
                    "sessionFile": fp,
                    "updatedAt": int(mtime * 1000),
                    "createdAt": int(os.path.getctime(fp) * 1000),
                    "totalTokens": 0,
                    "messageCount": total_lines,
                    "orphan": True,
                })
            except:
                continue
    except:
        pass
    
    sessions.sort(key=lambda s: s.get("updatedAt", 0) or 0, reverse=True)
    return sessions


def get_session_info(data_dir, active_key=None):
    """获取当前 session 的 key 和文件路径。
    active_key: 若提供，优先使用；否则 fallback 到 agent:main:main。
    """
    import glob
    target_key = active_key or "agent:main:main"
    
    store_file = os.path.join(data_dir, "sessions.json")
    if os.path.exists(store_file):
        with open(store_file) as f:
            store = json.load(f)
        if target_key in store:
            sf = store[target_key].get("sessionFile")
            if sf and os.path.exists(sf):
                return target_key, sf
        main = store.get("agent:main:main")
        if main:
            sf = main.get("sessionFile")
            if sf and os.path.exists(sf):
                return "agent:main:main", sf
        for k, v in store.items():
            sf = v.get("sessionFile")
            if sf and os.path.exists(sf):
                return k, sf
    
    if target_key.startswith("orphan:"):
        fname = target_key[7:]
        fp = os.path.join(data_dir, fname)
        if os.path.exists(fp):
            return target_key, fp
    
    try:
        jsonls = [f for f in glob.glob(os.path.join(data_dir, "*.jsonl")) 
                  if not f.endswith('.trajectory.jsonl') and '.checkpoint.' not in f]
        if jsonls:
            biggest = max(jsonls, key=os.path.getsize)
            return "agent:main:main", biggest
    except:
        pass
    
    return None, None


def read_session_v2(session_file, strip_metadata_fn=None):
    """读取并解析会话JSONL文件。先快照再解析，避免与Gateway的并发读写冲突。
    v2 版本：接受可选的 strip_metadata_fn 参数。
    """
    import tempfile, shutil
    if not session_file or not os.path.exists(session_file):
        return []
    
    try:
        fd, snap_path = tempfile.mkstemp(suffix='.jsonl', prefix='session_snap_')
        os.close(fd)
        shutil.copy2(session_file, snap_path)
        with open(snap_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        os.unlink(snap_path)
    except Exception:
        with open(session_file) as f:
            lines = [l.strip() for l in f if l.strip()]
    
    if strip_metadata_fn is None:
        strip_metadata_fn = lambda t: t
    
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
            display_text = strip_metadata_fn(text)
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


def fetch_session_via_gateway(session_key, gateway_port, gateway_token, openclaw_home, identity_path, bun_bin, script_dir):
    """通过 Gateway RPC 获取会话历史。"""
    import subprocess, json, os
    helper = os.path.join(script_dir, "inject-helper.mjs")
    if not os.path.exists(helper):
        return None
    
    env = os.environ.copy()
    env['GATEWAY_PORT'] = str(gateway_port)
    env['GATEWAY_TOKEN'] = gateway_token
    env['OPENCLAW_HOME'] = openclaw_home
    env['OPENCLAW_IDENTITY_PATH'] = identity_path
    
    try:
        result = subprocess.run(
            [bun_bin, helper, session_key, "", "history"],
            capture_output=True, text=True, timeout=5,
            env=env
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            print(f"[EDIT WEB] Gateway fetch failed: {err[:200]}", file=__import__('sys').stderr)
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
            messages.append({
                "role": role,
                "text": text,
                "raw_text": text,
                "timestamp": ts,
                "id": msg.get("id", ""),
                "provider": msg.get("provider", ""),
                "model": msg.get("model", ""),
            })
        print(f"[EDIT WEB] Fetched {len(messages)} messages via Gateway RPC", file=__import__('sys').stderr)
        return messages
    except Exception as e:
        print(f"[EDIT WEB] Gateway fetch exception: {e}", file=__import__('sys').stderr)
        return None
