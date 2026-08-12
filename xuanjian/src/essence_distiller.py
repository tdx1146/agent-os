# -*- coding: utf-8 -*-
"""
essence_distiller.py — IsoSand 轮感结晶组件

从 operation_log.jsonl 中周期性提炼「轮感」（essence），
基于规则的模式发现（错误频发、成功链、新 actor、统计趋势），
不做 AI 摘要。输出写入 data/essence/essence_YYYY-MM-DD.json。
"""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

__all__ = ["distill", "save_essence", "load_essence", "scan_logs", "quick_test"]

# 项目根目录（与 iso_logger.py 保持一致）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_FILE = os.path.join(_PROJECT_ROOT, "data", "operation_log.jsonl")
_ESSENCE_DIR = os.path.join(_PROJECT_ROOT, "data", "essence")
_FACTS_FILE = os.path.join(_PROJECT_ROOT, "data", "facts.dict.md")

# 北京时区
_BJT = timezone(timedelta(hours=8))

# ── 工具函数 ──────────────────────────────────────────────────────────


def _extract_date(t_iso: str) -> str:
    """从 ISO 时间戳中提取 YYYY-MM-DD 日期"""
    # 兼容带时区和不带时区两种格式
    match = re.match(r"(\d{4}-\d{2}-\d{2})", t_iso)
    return match.group(1) if match else datetime.now(_BJT).strftime("%Y-%m-%d")


def _now_str() -> str:
    """返回当前 ISO 时间字符串"""
    return datetime.now(_BJT).isoformat()


# ── 核心接口 ──────────────────────────────────────────────────────────


def scan_logs(log_path: str = None, start_trace: str = None) -> list[dict]:
    """
    扫描 operation_log.jsonl 读取所有条目。

    参数:
        log_path: 日志文件路径（默认 data/operation_log.jsonl）
        start_trace: 如果指定，只返回该 trace_id 匹配的条目

    返回:
        日志记录列表（按文件中的出现顺序）
    """
    path = log_path or _LOG_FILE
    if not os.path.exists(path):
        return []

    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.append(rec)

    # 如果指定了 start_trace，只返回该 trace_id 的完整链路
    if start_trace:
        records = [r for r in records if r.get("trace_id") == start_trace]

    return records


def load_essence(date_str: str = None) -> list[dict]:
    """
    加载指定日期的轮感。

    参数:
        date_str: YYYY-MM-DD 格式日期（默认加载最新的）

    返回:
        essence 列表（若无数据则返回空列表）
    """
    if not os.path.isdir(_ESSENCE_DIR):
        return []

    if date_str:
        target = date_str
    else:
        # 找最新的 essence 文件
        files = [f for f in os.listdir(_ESSENCE_DIR)
                 if f.startswith("essence_") and f.endswith(".json")]
        if not files:
            return []
        files.sort(reverse=True)
        target = files[0][len("essence_"):-len(".json")]

    path = os.path.join(_ESSENCE_DIR, f"essence_{target}.json")
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_essence(essences: list[dict], date_str: str = None) -> str:
    """
    将轮感保存到 data/essence/essence_YYYY-MM-DD.json。

    如果当日文件已存在，合并（去重后更新）。

    参数:
        essences: essence 列表
        date_str: YYYY-MM-DD 格式日期（默认用当天）

    返回:
        写入的文件路径
    """
    date_str = date_str or datetime.now(_BJT).strftime("%Y-%m-%d")
    path = os.path.join(_ESSENCE_DIR, f"essence_{date_str}.json")

    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 如果文件已存在，加载旧数据并去重合并
    existing = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except (json.JSONDecodeError, ValueError):
                existing = []

    # 用 (type, summary) 作为去重 key
    seen = set()
    merged = []
    for e in existing + essences:
        key = (e.get("type", ""), e.get("summary", ""))
        if key not in seen:
            seen.add(key)
            merged.append(e)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    return path


def distill(source_logs: list[dict], existing_facts: str = None) -> list[dict]:
    """
    从一组日志条目中提炼轮感。

    这个函数做的是**模式发现**而非 AI 摘要——它从日志的结构中发现
    规律（actor 高频、FAIL 频发、trace 链连续等）。

    规则:
        1. 错误频发检测：同一 actor 在短时间窗口内 ERROR ≥ 3 次 → anomaly
        2. 成功链检测：trace_id 相同的链全部 OK → milestone
        3. 新 actor 识别：过去日志中未出现的 actor → milestone
        4. 统计：每天总操作数、各 actor 分布 → trend

    参数:
        source_logs: operation_log.jsonl 里读出来的条目列表
        existing_facts: facts.dict.md 的内容（当前未使用，保留接口签名）

    返回:
        essence 列表
    """
    if not source_logs:
        return []

    today = _extract_date(source_logs[-1].get("t", "")) or datetime.now(_BJT).strftime("%Y-%m-%d")
    essences = []

    # ── 规则 1：错误频发检测 ──────────────────────────────────────
    # 按 actor 分组，统计 ERROR 条目
    actor_errors = defaultdict(list)
    for rec in source_logs:
        if rec.get("level", "").upper() == "ERROR":
            actor_errors[rec.get("actor", "unknown")].append(rec)

    for actor, error_recs in actor_errors.items():
        if len(error_recs) >= 3:
            # 检测这些错误是否在短时间窗口内（取首尾时间差 < 10 分钟）
            times = []
            for r in error_recs:
                t_str = r.get("t", "")
                try:
                    # 尝试解析含时区的时间戳
                    dt = datetime.fromisoformat(t_str)
                    times.append(dt)
                except (ValueError, TypeError):
                    pass

            if len(times) >= 3:
                window_span = (max(times) - min(times)).total_seconds()
                if window_span <= 600:  # 10 分钟
                    essences.append({
                        "date": today,
                        "type": "anomaly",
                        "summary": f"actor [{actor}] 在 {window_span:.0f}s 内发生 {len(times)} 次 ERROR",
                        "detail": f"短时间窗口内连续报错:\n" + "\n".join(
                            f"  • {r.get('action','?')} @ {r.get('target','?')}: {r.get('detail','')[:80]}"
                            for r in error_recs[:5]
                        ),
                        "tags": ["anomaly", "error_burst", actor],
                        "source_logs": [r.get("trace_id", "?") for r in error_recs],
                        "confidence": round(min(0.5 + len(error_recs) * 0.1, 0.95), 2),
                    })

    # ── 规则 2：成功链检测 ──────────────────────────────────────────
    # 按 trace_id 分组
    trace_groups = defaultdict(list)
    for rec in source_logs:
        trace_groups[rec.get("trace_id", "none")].append(rec)

    for trace_id, group in trace_groups.items():
        if trace_id == "none" or trace_id == "?":
            continue
        if len(group) < 2:
            continue
        # 检查链中所有条目是否全部 OK
        all_ok = all(r.get("result", "").upper() == "OK" for r in group)
        if all_ok:
            # 找出涉及的 actor
            actors = list(dict.fromkeys(r.get("actor", "?") for r in group))
            actions = list(dict.fromkeys(r.get("action", "?") for r in group))
            essences.append({
                "date": _extract_date(group[0].get("t", "")) or today,
                "type": "milestone",
                "summary": f"trace 链 [{trace_id}] 全部成功（{len(group)} 步）",
                "detail": f"完整链路由 {', '.join(actors)} 完成，动作序列: {' → '.join(actions)}",
                "tags": ["milestone", "success_chain", trace_id] + actors,
                "source_logs": [r.get("trace_id", "?") for r in group],
                "confidence": 0.9,
            })

    # ── 规则 3：新 actor 识别 ────────────────────────────────────────
    # 通过检查今日日志中 actors 出现的最早时间来判断
    actor_first_seen = {}
    for rec in source_logs:
        actor = rec.get("actor", "unknown")
        t_str = rec.get("t", "")
        if actor not in actor_first_seen or t_str < actor_first_seen[actor]:
            actor_first_seen[actor] = t_str

    today_actors = set()
    for rec in source_logs:
        rec_date = _extract_date(rec.get("t", ""))
        if rec_date == today:
            today_actors.add(rec.get("actor", "unknown"))

    # 模拟「历史 actor 集合」：从 source_logs 本身推断，
    # 如果一个 actor 在今天之前就出现过，不算新
    historical_actors = set()
    for rec in source_logs:
        rec_date = _extract_date(rec.get("t", ""))
        if rec_date < today:
            historical_actors.add(rec.get("actor", "unknown"))

    new_actors = today_actors - historical_actors
    for actor in sorted(new_actors):
        if actor == "unknown":
            continue
        first_t = actor_first_seen.get(actor, "")
        essences.append({
            "date": today,
            "type": "milestone",
            "summary": f"新 actor [{actor}] 首次出现在操作日志中",
            "detail": f"actor '{actor}' 于 {first_t} 首次出现，操作: "
                      f"{', '.join(r.get('action','?') for r in source_logs if r.get('actor')==actor)}",
            "tags": ["milestone", "new_actor", actor],
            "source_logs": [r.get("trace_id", "?") for r in source_logs if r.get("actor") == actor],
            "confidence": 0.85,
        })

    # ── 规则 4：统计趋势 ────────────────────────────────────────────
    # 按日期分组统计
    daily_records = defaultdict(list)
    for rec in source_logs:
        d = _extract_date(rec.get("t", ""))
        daily_records[d].append(rec)

    for d, recs in sorted(daily_records.items()):
        total = len(recs)
        actor_counts = Counter(r.get("actor", "unknown") for r in recs)
        result_counts = Counter(r.get("result", "UNKNOWN") for r in recs)
        level_counts = Counter(r.get("level", "INFO") for r in recs)

        top_actors = actor_counts.most_common(5)
        essences.append({
            "date": d,
            "type": "trend",
            "summary": f"日志统计 {d}: 共 {total} 条操作, {len(actor_counts)} 个 actor",
            "detail": (
                f"操作数: {total}\n"
                f"actor 分布: {', '.join(f'{a}={c}' for a, c in top_actors)}\n"
                f"结果分布: {', '.join(f'{r}={c}' for r, c in result_counts.most_common())}\n"
                f"级别分布: {', '.join(f'{l}={c}' for l, c in level_counts.most_common())}"
            ),
            "tags": ["trend", "daily_stats"],
            "source_logs": [r.get("trace_id", "?") for r in recs[:10]],
            "confidence": 0.95,
        })

    return essences


# ── 快速测试 ──────────────────────────────────────────────────────────


def quick_test() -> None:
    """
    快速自测：
    1. 写入几条不同场景的测试日志
    2. 跑 distill 验证规则发现
    3. 验证保存/加载
    4. 清理测试数据
    """
    print("=" * 60)
    print("🧪 essence_distiller.py 快速自测")
    print("=" * 60)

    # ── 准备测试日志（直接写入 jsonl 以避免依赖 iso_logger 的副作用） ──
    test_logs = [
        # 场景 A：成功链 (trace_id: chain-ok-001)
        {"t": "2026-07-06T10:00:00+08:00", "level": "INFO",  "actor": "system",       "action": "init",     "target": "project",  "result": "OK", "detail": "step 1/3", "trace_id": "chain-ok-001"},
        {"t": "2026-07-06T10:01:00+08:00", "level": "INFO",  "actor": "fix-config",   "action": "update",   "target": "config",   "result": "OK", "detail": "step 2/3", "trace_id": "chain-ok-001"},
        {"t": "2026-07-06T10:02:00+08:00", "level": "INFO",  "actor": "system",       "action": "verify",   "target": "config",   "result": "OK", "detail": "step 3/3", "trace_id": "chain-ok-001"},
        {"t": "2026-07-06T10:03:00+08:00", "level": "INFO",  "actor": "system",       "action": "complete", "target": "project",  "result": "OK", "detail": "all done",  "trace_id": "chain-ok-001"},

        # 场景 B：错误频发 (actor: crash-loop, ERROR × 4)
        {"t": "2026-07-06T10:05:00+08:00", "level": "ERROR", "actor": "crash-loop",   "action": "read",     "target": "db/state", "result": "FAIL", "detail": "timeout",          "trace_id": "err-001"},
        {"t": "2026-07-06T10:05:30+08:00", "level": "ERROR", "actor": "crash-loop",   "action": "read",     "target": "db/state", "result": "FAIL", "detail": "connection reset", "trace_id": "err-001"},
        {"t": "2026-07-06T10:06:00+08:00", "level": "ERROR", "actor": "crash-loop",   "action": "read",     "target": "db/state", "result": "FAIL", "detail": "timeout",          "trace_id": "err-002"},
        {"t": "2026-07-06T10:06:30+08:00", "level": "ERROR", "actor": "crash-loop",   "action": "read",     "target": "db/state", "result": "FAIL", "detail": "timeout",          "trace_id": "err-003"},

        # 场景 C：新 actor（过去的日志中未出现过）
        # （所有测试日志都是 7月6日的，所以 7月6之前没有记录 → 全部 actor 都是新的）
        {"t": "2026-07-06T10:10:00+08:00", "level": "INFO",  "actor": "brand-new-module", "action": "register", "target": "plugin", "result": "OK", "detail": "new plugin registered", "trace_id": "new-001"},
    ]

    test_file = os.path.join(os.path.dirname(_LOG_FILE), "_test_essence_logs.jsonl")
    os.makedirs(os.path.dirname(test_file), exist_ok=True)
    with open(test_file, "w", encoding="utf-8") as f:
        for rec in test_logs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"📝 已写入 {len(test_logs)} 条测试日志 → {test_file}")

    # ── 步骤 1：读取测试日志 ────────────────────────────────────────
    logs = scan_logs(log_path=test_file)
    print(f"📖 scan_logs 读取到 {len(logs)} 条记录")
    assert len(logs) == len(test_logs), "scan_logs 读取数量不匹配"

    # 测试按 trace 追踪
    traced = scan_logs(log_path=test_file, start_trace="chain-ok-001")
    print(f"🔍 trace 链追踪 (chain-ok-001): 找到 {len(traced)} 条")
    assert len(traced) == 4, f"trace 追踪应返回 4 条, 实际 {len(traced)}"

    # ── 步骤 2：蒸馏 ────────────────────────────────────────────────
    # 为了测试新 actor 识别更干净，我们先只给 today 的 actor，没有旧的
    # 但全部日志都是今天 → 我们再加几条「昨日」的模拟日志
    # 这里直接向 distill 传入额外数据会更复杂，不如直接在当前测试
    # 日志中加上一条昨天日期的记录，让 historical_actors 出现
    yesterday_logs = [
        {"t": "2026-07-05T10:00:00+08:00", "level": "INFO", "actor": "system",     "action": "init",   "target": "project", "result": "OK", "detail": "yesterday init", "trace_id": "old-001"},
        {"t": "2026-07-05T10:01:00+08:00", "level": "INFO", "actor": "fix-config", "action": "verify", "target": "config",  "result": "OK", "detail": "yesterday cfg",  "trace_id": "old-002"},
    ]
    mixed_logs = yesterday_logs + test_logs
    essences = distill(mixed_logs)
    print(f"🔄 distill 产出 {len(essences)} 条轮感")

    # ── 验证各个规则 ────────────────────────────────────────────────
    # 规则 1：错误频发 → anomaly
    anomalies = [e for e in essences if e["type"] == "anomaly"]
    print(f"  📊 anomaly 轮感: {len(anomalies)} 条")
    for a in anomalies:
        print(f"    ⚠️  {a['summary']}")
    assert len(anomalies) >= 1, "应检测到错误频发 anomaly"

    # 规则 2：成功链 → milestone
    milestones = [e for e in essences if e["type"] == "milestone"]
    print(f"  📊 milestone 轮感: {len(milestones)} 条")
    for m in milestones:
        print(f"    🎯 {m['summary']}")
    success_chain = [m for m in milestones if "success_chain" in m.get("tags", [])]
    assert len(success_chain) >= 1, "应检测到成功链 milestone"
    new_actor_m = [m for m in milestones if "new_actor" in m.get("tags", [])]
    assert len(new_actor_m) >= 1, "应检测到新 actor milestone"

    # 规则 4：统计 → trend
    trends = [e for e in essences if e["type"] == "trend"]
    print(f"  📊 trend 轮感: {len(trends)} 条")
    assert len(trends) >= 1, "应产出 trend 轮感"

    # 置信度验证
    for e in essences:
        assert 0 <= e.get("confidence", 0) <= 1, f"confidence 超出范围: {e}"

    # ── 步骤 3：保存 / 加载 ────────────────────────────────────────
    saved_path = save_essence(essences, date_str="2026-07-06")
    print(f"💾 已保存 → {saved_path}")
    assert os.path.exists(saved_path), "保存文件不存在"

    loaded = load_essence("2026-07-06")
    print(f"📂 load_essence 读取到 {len(loaded)} 条轮感")
    assert len(loaded) == len(essences), "保存/加载轮感数量不匹配"

    # 测试合并去重
    saved_path2 = save_essence(essences[:1], date_str="2026-07-06")
    loaded2 = load_essence("2026-07-06")
    assert len(loaded2) == len(essences), f"合并去重后数量应为 {len(essences)}, 实际 {len(loaded2)}"

    # 测试加载最新
    latest = load_essence()
    assert len(latest) == len(essences), "加载最新应返回相同数据"

    # ── 清理测试文件 ────────────────────────────────────────────────
    os.remove(test_file)
    os.remove(saved_path)
    print("🧹 已清理测试文件")

    print("=" * 60)

    # 记录测试到操作日志
    log("INFO", "quick_test", "test_essence_distiller", "self_test", "OK", "轮感结晶组件自测通过")
    print("✅ essence_distiller.py 测试通过")
    print("=" * 60)


if __name__ == "__main__":
    # 延迟导入避免循环依赖
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from iso_logger import log
    quick_test()
