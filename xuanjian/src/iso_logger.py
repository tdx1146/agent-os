"""
iso_logger.py — IsoSand 操作日志系统

操作日志是所有上层组件（essence_distiller、cron 任务、人机交互）的可见性基石。
提供追加写入和按条件筛选的读取接口。
"""

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

__all__ = ["log", "get_logs", "quick_test"]

# 日志文件路径（相对于此文件所在项目的根目录）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_FILE = os.path.join(_PROJECT_ROOT, "data", "operation_log.jsonl")

# 北京时区
_BJT = timezone(timedelta(hours=8))


def _short_id() -> str:
    """生成简短的可读 ID（类似 fix-config-xxx 格式）"""
    return uuid.uuid4().hex[:8]


def _now_iso() -> str:
    """返回当前时间的 ISO 8601 字符串，含北京时区"""
    return datetime.now(_BJT).isoformat()


def log(level: str, actor: str, action: str, target: str,
        result: str, detail: str, trace_id: Optional[str] = None) -> dict:
    """
    写入一条操作日志到 data/operation_log.jsonl

    参数:
        level:   日志级别 — INFO | WARN | ERROR | FATAL
        actor:   谁做的（system, essence-distiller, cron, subagent-xxx, human-dandan, fix-config 等）
        action:  做了什么（init, update, rollback, audit, verify 等）
        target:  操作对象路径或标识
        result:  结果状态 — OK | FAIL | PARTIAL
        detail:  详情描述（克制、准确、结构清晰）
        trace_id: 追踪链ID（可选，默认自动生成短 ID）

    返回:
        包含完整字段的 dict
    """
    record = {
        "t": _now_iso(),
        "level": level.upper(),
        "actor": actor,
        "action": action,
        "target": target,
        "result": result.upper(),
        "detail": detail,
        "trace_id": trace_id or _short_id(),
    }

    # 确保 data/ 目录存在
    os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)

    # 追加写入（不锁文件）
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def get_logs(limit: int = 50, offset: int = 0,
             level: Optional[str] = None, actor: Optional[str] = None,
             action: Optional[str] = None, since: Optional[str] = None) -> list:
    """
    读取操作日志，支持分页和筛选

    参数:
        limit:  返回条数（默认 50，最大 500）
        offset: 跳过前 N 条
        level:  按级别筛选（INFO / WARN / ERROR / FATAL）
        actor:  按执行者筛选（精确匹配）
        action: 按操作类型筛选
        since:  ISO 时间戳，只返回此时间之后的记录

    返回:
        日志记录列表（按时间正序）
    """
    if not os.path.exists(_LOG_FILE):
        return []

    records = []
    with open(_LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            # 字段筛选
            if level and rec.get("level", "").upper() != level.upper():
                continue
            if actor and rec.get("actor") != actor:
                continue
            if action and rec.get("action") != action:
                continue
            if since and rec.get("t", "") < since:
                continue

            records.append(rec)

    # 分页
    limit = min(limit, 500)
    return records[offset:offset + limit]


def quick_test() -> None:
    """
    快速自测：写入一条测试日志，然后读回来验证
    """
    print("=" * 50)
    print("🧪 iso_logger.py 快速自测")
    print("=" * 50)

    # 清理之前可能存在的测试数据
    test_data_file = _LOG_FILE

    # 写入测试日志
    rec = log(
        level="INFO",
        actor="system",
        action="test",
        target="iso_logger.py",
        result="OK",
        detail="iso_logger.py 快速自测 - 验证写入和读取功能",
        trace_id="self-test-001",
    )
    print(f"✅ 写入成功: {json.dumps(rec, ensure_ascii=False)}")

    # 读回来验证
    logs = get_logs(limit=10, actor="system", action="test")
    found = any(r["trace_id"] == "self-test-001" for r in logs)
    if found:
        print("✅ 读取验证成功 — 找到刚写入的测试日志")
    else:
        print("❌ 读取验证失败 — 未找到测试日志")
        return

    # 测试筛选
    level_logs = get_logs(level="INFO", limit=5)
    print(f"✅ 级别筛选: 最近 {len(level_logs)} 条 INFO 日志")

    # 测试分页
    recent = get_logs(limit=3)
    print(f"✅ 分页读取: 最近 {len(recent)} 条日志")

    print("=" * 50)
    print("✅ iso_logger.py 测试通过")
    print("=" * 50)


if __name__ == "__main__":
    quick_test()
