# handlers/session_handler.py — 会话管理
# 每个函数接收 handler (HTTP handler实例) 作为第一个参数

import sys
import json
import os
import time

_M = None
def g(name): return getattr(_M, name, None) if _M else None

def handle_get_session_data(handler):
    """获取当前会话数据"""
    get_session_info = g('get_session_info')
    read_session = g('read_session')
    group_into_pairs = g('group_into_pairs')
    DATA_DIR = g('DATA_DIR')
    GATEWAY_PORT = g('GATEWAY_PORT')
    
    sk, session_file = get_session_info()
    if not sk and not session_file:
        return {"error": "no session", "messages": [], "pairs": [], "sessionKey": None, "messageCount": 0, "info": {
            "host": "127.0.0.1", "port": GATEWAY_PORT, "sessionFile": None,
            "dataDir": DATA_DIR,
        }}
    
    # 用文件快照保护读JSONL（避免与Gateway并发写冲突）
    msgs = read_session(session_file) if session_file else []
    
    pairs = group_into_pairs(msgs)
    total_users = sum(1 for m in msgs if m["role"] == "user")
    idx = -1
    reversed_pairs = []
    for p in pairs:
        idx += 1
        reversed_pairs.insert(0, {**p, "userIndex": idx})
    return {
        "sessionFile": session_file,
        "sessionKey": sk,
        "total": len(msgs),
        "userCount": total_users,
        "messageCount": len(msgs),
        "pairs": reversed_pairs,
        "info": {
            "host": "127.0.0.1",
            "port": GATEWAY_PORT,
            "sessionFile": session_file,
            "dataDir": DATA_DIR,
        },
    }

def handle_delete_session(handler):
    """删除一个会话：改名 .jsonl → .deleted.时间戳，从 sessions.json 中移除"""
    session_key = handler._get_query_param('key') or handler._get_query_param('sessionKey') or ''
    if not session_key:
        handler._send_json(400, {"ok": False, "error": "missing sessionKey"})
        return
    DATA_DIR = g('DATA_DIR')
    get_active_session_key = g('get_active_session_key')
    set_active_session_key = g('set_active_session_key')
    
    store_file = os.path.join(DATA_DIR, "sessions.json")
    if not os.path.exists(store_file):
        handler._send_json(404, {"ok": False, "error": "sessions.json not found"})
        return
    with open(store_file) as f:
        store = json.load(f)
    if session_key not in store:
        handler._send_json(404, {"ok": False, "error": "session key not found"})
        return
    sf = store[session_key].get("sessionFile", "")
    # 改名 JSONL 文件
    if sf and os.path.exists(sf):
        import datetime
        ts = datetime.datetime.now().strftime('%Y-%m-%dT%H-%M-%S.%fZ')
        deleted_name = sf + '.deleted.' + ts
        try:
            os.rename(sf, deleted_name)
        except Exception as e:
            pass  # 加锁失败不阻塞
    # 从 sessions.json 中移除
    del store[session_key]
    with open(store_file, 'w') as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
    # 如果删除的是当前激活会话，重置
    if get_active_session_key() == session_key:
        set_active_session_key(None)
    handler._send_json(200, {"ok": True, "deleted": session_key})

def handle_trim_session(handler):
    """裁剪session文件，保留最近N轮"""
    try:
        get_session_info = g('get_session_info')
        LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
        sk, session_file = get_session_info()
        if not session_file or not os.path.exists(session_file):
            handler._send_json(200, {"ok": False, "error": "Session file not found"})
            return

        # 解析session文件
        import shutil
        from datetime import datetime as dt

        with open(session_file) as f:
            lines = f.readlines()

        if len(lines) < 5:
            handler._send_json(200, {"ok": False, "error": "Session too short to trim"})
            return

        # 找到最后3轮用户消息
        user_indices = []
        for i, line in enumerate(lines):
            try:
                d = json.loads(line)
                if d.get('type') == 'message':
                    m = d.get('message', {})
                    if m.get('role') == 'user':
                        user_indices.append(i)
            except:
                pass

        if len(user_indices) <= 3:
            handler._send_json(200, {"ok": False, "error": f"Only {len(user_indices)} rounds, no trimming needed"})
            return

        # 保留：session header (0) + 最后3轮 + 之后的所有条目
        split_at = user_indices[-3]
        header = lines[0]

        old_size = os.path.getsize(session_file)
        trimmed = [header] + lines[split_at:]

        # 修复parentId断链（只修需要修的行，原始格式不动）
        kept_ids = set()
        for line in trimmed:
            try:
                d = json.loads(line)
                if 'id' in d:
                    kept_ids.add(d['id'])
            except:
                pass

        fixed = []
        broken = 0
        for line in trimmed:
            try:
                d = json.loads(line)
                pid = d.get('parentId')
                if pid and pid not in kept_ids:
                    # 只替换这一行的 parentId 字段，不动其他
                    import re
                    fixed_line = re.sub(
                        r'"parentId"\s*:\s*"[^"]*"',
                        '"parentId": null',
                        line
                    )
                    fixed.append(fixed_line)
                    broken += 1
                else:
                    fixed.append(line)  # 保持原样，不重新序列化
            except:
                fixed.append(line)  # 解析失败也保持原样

        new_size = sum(len(l) for l in fixed)
        kept_msgs = sum(1 for l in fixed if json.loads(l).get('type') == 'message')

        # 备份并写入
        backup_path = session_file + f".trim-backup.{dt.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(session_file, backup_path)

        with open(session_file, 'w') as f:
            f.writelines(fixed)

        # 更新删除次数
        trim_file = os.path.join(LIGHT_SMOKE_DIR, "memory", ".trim-counter")
        try:
            tc = 0
            if os.path.exists(trim_file):
                tc = int(open(trim_file).read().strip())
            with open(trim_file, 'w') as f:
                f.write(str(tc + 1))
        except:
            pass

        handler._send_json(200, {
            "ok": True,
            "from_bytes": old_size,
            "to_bytes": new_size,
            "removed_msgs": sum(1 for l in lines if json.loads(l).get('type') == 'message') - kept_msgs,
            "reduced_pct": round((1 - new_size / old_size) * 100),
            "kept_rounds": 3,
            "broken_refs_fixed": broken,
            "backup": os.path.basename(backup_path),
            "note": "Session trimmed. Restart required for changes to take effect."
        })
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_session_rpc(handler):
    """通过 Gateway RPC (chat.history) 获取会话消息，不走文件"""
    try:
        import subprocess
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gateway-history.js')
        get_session_info = g('get_session_info')
        sk, _ = get_session_info()
        env = os.environ.copy()
        if sk:
            env['SESSION_KEY'] = sk
        result = subprocess.run(['node', script], capture_output=True, text=True, timeout=15, env=env)
        if result.returncode != 0:
            handler._send_json(200, {"ok": False, "error": f"rpc exited {result.returncode}: {result.stderr[:200]}"})
            return
        data = json.loads(result.stdout)
        if not data.get('ok'):
            handler._send_json(200, {"ok": False, "error": data.get('error', 'unknown')})
            return
        # 转换为编辑器格式
        raw_messages = data.get('messages') or data.get('payload', {}).get('messages', [])
        handler._send_json(200, {
            "ok": True,
            "from_rpc": True,
            "messages": raw_messages,
            "count": len(raw_messages)
        })
    except subprocess.TimeoutExpired:
        handler._send_json(200, {"ok": False, "error": "rpc timeout"})
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": f"rpc error: {str(e)[:200]}"})

def handle_list_backups(handler):
    """列出所有截断前备份"""
    BACKUP_DIR = g('BACKUP_DIR')
    if not os.path.exists(BACKUP_DIR):
        return {"backups": []}
    backups = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if f.endswith(".jsonl") and f.startswith("pre-edit."):
            fpath = os.path.join(BACKUP_DIR, f)
            ts_str = f.replace("pre-edit.", "").replace(".jsonl", "")
            try:
                ts = __import__('datetime').datetime.strptime(ts_str, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
            except:
                ts = ts_str
            size = os.path.getsize(fpath)
            # 读取第一行获取 session key 等信息
            first_line = ""
            try:
                with open(fpath) as fh:
                    first_line = fh.readline()[:80]
            except:
                pass
            backups.append({
                "filename": f,
                "timestamp": ts,
                "size": size,
                "preview": first_line.strip(),
            })
    return {"backups": backups}

def handle_restore_backup(handler):
    """从备份恢复 session 文件"""
    BACKUP_DIR = g('BACKUP_DIR')
    get_session_info = g('get_session_info')
    
    try:
        data = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        filename = data.get('filename', '')
    except:
        filename = handler._get_query_param('filename', '')
    
    src = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(src):
        return {"ok": False, "error": f"备份文件不存在: {filename}"}
    
    sk, session_file = get_session_info()
    if not session_file:
        return {"ok": False, "error": "找不到当前 session 文件"}
    
    # 对当前 session 也做一次备份，防止误操作
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore = os.path.join(BACKUP_DIR, f"pre-restore.{stamp}.jsonl")
    with open(session_file) as f:
        with open(pre_restore, "w") as b:
            b.write(f.read())
    
    # 恢复备份
    import shutil
    shutil.copyfile(src, session_file)
    
    _cleanup_lock = g('_cleanup_lock')
    _cleanup_lock()
    
    return {
        "ok": True,
        "restored": filename,
        "backed_up_current": f"pre-restore.{stamp}.jsonl",
        "note": "session 已恢复，请刷新编辑器查看",
    }

def handle_update_last_user_msg(handler):
    """更新最后用户消息时间"""
    try:
        SCRIPT_DIR = g('SCRIPT_DIR')
        ts = str(int(time.time()))
        os.makedirs(os.path.join(SCRIPT_DIR, '.踱步'), exist_ok=True)
        with open(os.path.join(SCRIPT_DIR, '.踱步', '.last_user_msg'), 'w') as f:
            f.write(ts)
    except:
        pass

def handle_cleanup_inject_lock(handler):
    """清理注入锁"""
    _cleanup_lock = g('_cleanup_lock')
    _cleanup_lock()
    handle_update_last_user_msg(handler)
