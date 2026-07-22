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
