#!/usr/bin/env python3
"""
session_safety.py — Session 存活守护 & 恢复工具

问题：sessions_yield 后子代理返回时，Gateway 可能创建新 session 而非回到原 session。
旧 session JSONL 完好但不被新 session 感知。

职责：
  1. pre_yield_save()  — 在 sessions_yield 前保存当前 session 摘要到文件
  2. check_continuity() — 启动时检查是否在新 session 中，读取旧 session 恢复上下文
  3. recover_context()  — 从指定 session JSONL 中提取最后 N 轮用户消息

用法：
  from session_safety import pre_yield_save, check_continuity, recover_context
"""

import os
import json
import glob
from datetime import datetime, timezone

SESSION_DIR = '/vol1/@apphome/trim.openclaw/data/home/.openclaw/agents/main/sessions'
WORKSPACE = '/vol1/@apphome/trim.openclaw/data/workspace'
SAFEGUARD_FILE = os.path.join(WORKSPACE, 'memory', 'session-safeguard.json')


# ---------------------------------------------------------------------------
# 1. 保存 session 快照（yield 前调用）
# ---------------------------------------------------------------------------

def pre_yield_save(session_key: str = 'current',
                   user_message_count: int = 0,
                   last_topics: list = None):
    """
    在 sessions_yield 前调用。保存当前 session 的关键信息。

    写入 memory/session-safeguard.json，格式：
    {
        "saved_at": "ISO-8601",
        "session_key": "agent:main:xxx",
        "user_message_count": 61,
        "last_topics": ["子代理整合", "类型检查模块"],
        "last_user_messages": [最后 3 条用户消息摘要]
    }
    """
    safeguard = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "session_key": session_key,
        "user_message_count": user_message_count,
        "last_topics": last_topics or [],
    }

    # 尝试从当前 session 提取最后几条消息
    try:
        # 找最新 session
        sessions = sorted(glob.glob(os.path.join(SESSION_DIR, '*.jsonl')),
                          key=os.path.getmtime, reverse=True)
        if sessions:
            latest = sessions[0]
            safeguard["session_file"] = os.path.basename(latest)
            safeguard["session_path"] = latest
            # 提取最后 3 条用户消息
            last_msgs = []
            with open(latest, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        j = json.loads(line.strip())
                        if j.get('type') == 'message':
                            msg = j.get('message', {})
                            if isinstance(msg, dict):
                                role = msg.get('role', '')
                                content = msg.get('content', '')
                                if isinstance(content, list):
                                    parts = [p.get('text', '') for p in content if isinstance(p, dict)]
                                    content = ' '.join(parts)
                                if isinstance(content, str) and role == 'user' and content.strip():
                                    last_msgs.append(content.strip()[:200])
                    except:
                        pass
            safeguard["last_user_messages"] = last_msgs[-3:] if last_msgs else []
    except Exception as e:
        safeguard["read_error"] = str(e)

    # 写入
    os.makedirs(os.path.dirname(SAFEGUARD_FILE), exist_ok=True)
    with open(SAFEGUARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(safeguard, f, ensure_ascii=False, indent=2)

    return safeguard


# ---------------------------------------------------------------------------
# 2. 检查 session 连续性
# ---------------------------------------------------------------------------

def check_continuity(current_session_key: str = None) -> dict:
    """
    启动时调用。对比安全文件和当前 session，判断是否发生了断连。

    Returns:
        {
            "disconnected": bool,        # 是否发生了 session 断连
            "lost_messages": int,        # 丢失的用户消息数
            "previous_session": str,      # 前一个 session 文件名
            "current_session": str,       # 当前 session 文件名
            "recovered": bool,            # 是否已恢复
            "recovered_messages": list,   # 恢复的用户消息
        }
    """
    result = {
        "disconnected": False,
        "lost_messages": 0,
        "previous_session": "",
        "current_session": current_session_key or "unknown",
        "recovered": False,
        "recovered_messages": []
    }

    if not os.path.exists(SAFEGUARD_FILE):
        return result

    with open(SAFEGUARD_FILE, 'r', encoding='utf-8') as f:
        safeguard = json.load(f)

    prev_file = safeguard.get("session_file", "")
    if not prev_file:
        return result

    prev_path = os.path.join(SESSION_DIR, prev_file)
    if not os.path.exists(prev_path):
        result["disconnected"] = True
        result["previous_session"] = prev_file
        result["reason"] = "前一次 session 文件已不存在"
        return result

    # 找当前最新的 session
    sessions = sorted(glob.glob(os.path.join(SESSION_DIR, '*.jsonl')),
                      key=os.path.getmtime, reverse=True)
    current_file = os.path.basename(sessions[0]) if sessions else ""

    if current_file != prev_file:
        # 断连了！当前 session 和上次保存的不一样
        result["disconnected"] = True
        result["previous_session"] = prev_file
        result["current_session"] = current_file

        # 计算丢失的消息数
        prev_count = safeguard.get("user_message_count", 0)
        prev_msgs = safeguard.get("last_user_messages", [])

        # 恢复：从旧 session 提取消息
        recovered = []
        with open(prev_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    j = json.loads(line.strip())
                    if j.get('type') == 'message':
                        msg = j.get('message', {})
                        if isinstance(msg, dict):
                            role = msg.get('role', '')
                            content = msg.get('content', '')
                            if isinstance(content, list):
                                parts = [p.get('text', '') for p in content if isinstance(p, dict)]
                                content = ' '.join(parts)
                            if isinstance(content, str) and role == 'user' and content.strip():
                                recovered.append(content.strip()[:500])
                except:
                    pass

        # 取最后 N 条用户消息（来自旧 session）
        result["recovered"] = True
        result["recovered_messages"] = recovered[-(prev_count or 20):]
        result["lost_messages"] = len(recovered)  # 近似值

    return result


# ---------------------------------------------------------------------------
# 3. 从指定 session 恢复上下文
# ---------------------------------------------------------------------------

def recover_context(session_id: str = None,
                    last_n_user: int = 10,
                    last_n_assistant: int = 5) -> dict:
    """
    从 session JSONL 文件中提取最近的 N 条消息。

    Args:
        session_id: session UUID（不包含路径）。None = 最新 session
        last_n_user: 返回最近多少条用户消息
        last_n_assistant: 返回最近多少条助手消息

    Returns:
        {
            "session_id": str,
            "user_messages": [...],
            "assistant_messages": [...],
            "total_messages": int,
            "session_size_kb": float
        }
    """
    if session_id:
        path = os.path.join(SESSION_DIR, f'{session_id}.jsonl')
    else:
        sessions = sorted(glob.glob(os.path.join(SESSION_DIR, '*.jsonl')),
                          key=os.path.getmtime, reverse=True)
        if not sessions:
            return {"error": "没有 session 文件"}
        path = sessions[0]
        session_id = os.path.basename(path).replace('.jsonl', '')

    if not os.path.exists(path):
        return {"error": f"session 文件不存在: {path}"}

    user_msgs = []
    asst_msgs = []

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                j = json.loads(line.strip())
                if j.get('type') == 'message':
                    msg = j.get('message', {})
                    if isinstance(msg, dict):
                        role = msg.get('role', '')
                        content = msg.get('content', '')
                        if isinstance(content, list):
                            parts = [p.get('text', '') for p in content if isinstance(p, dict)]
                            content = ' '.join(parts)
                        if isinstance(content, str) and content.strip():
                            if role == 'user':
                                user_msgs.append(content.strip()[:500])
                            elif role == 'assistant':
                                asst_msgs.append(content.strip()[:500])
            except:
                pass

    return {
        "session_id": session_id,
        "user_messages": user_msgs[-last_n_user:],
        "assistant_messages": asst_msgs[-last_n_assistant:],
        "total_user_messages": len(user_msgs),
        "total_assistant_messages": len(asst_msgs),
        "session_size_kb": round(os.path.getsize(path) / 1024, 1)
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'check':
        result = check_continuity()
        if result.get("disconnected"):
            print(f"⚠️ Session 断连检测到！")
            print(f"  前一个 session: {result.get('previous_session','?')}")
            print(f"  当前 session:   {result.get('current_session','?')}")
            print(f"  丢失消息: {result.get('lost_messages',0)} 条")
            if result.get("recovered_messages"):
                print(f"\n📋 恢复的上下文:")
                for i, m in enumerate(result["recovered_messages"][-5:]):  # 最多5条
                    print(f"  [{i+1}] {m[:120]}")
        else:
            print(f"✅ Session 连续（{result.get('current_session','?')}）")

    elif len(sys.argv) > 1 and sys.argv[1] == 'save':
        pre_yield_save(session_key=sys.argv[2] if len(sys.argv) > 2 else 'current')
        print(f"✅ Session 快照已保存到 {SAFEGUARD_FILE}")

    elif len(sys.argv) > 1 and sys.argv[1] == 'recover':
        sid = sys.argv[2] if len(sys.argv) > 2 else None
        result = recover_context(sid)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print(f"用法:")
        print(f"  python3 {sys.argv[0]} check       检查 session 连续性")
        print(f"  python3 {sys.argv[0]} save [key]  保存 session 快照")
        print(f"  python3 {sys.argv[0]} recover [id] 从 session 恢复上下文")
