"""
cache_monitor.py — 缓存命中率监控模块（v2 完全重写）
==================================================
功能：从 OpenClaw session JSONL 文件提取每轮缓存命中数据
原则：
- 不设最大轮数限制，返回全量数据（前端自己决定展示数量）
- 不跳过任何轮次，最新在前的 realtime 命中率用最近 N 轮计算
- 费率实时可配，不硬编码
- 输出格式清晰，不为前端的简便性牺牲数据准确性
"""

import os
import json
import glob


DEFAULT_RATES = {
    "input_miss": 0.000001,      # DeepSeek: ¥/token miss
    "input_hit": 0.00000002,     # DeepSeek: ¥/token hit
    "output": 0.000002,          # DeepSeek: ¥/token output
}


def load_file(data_dir):
    """找最新的 session JSONL 文件"""
    files = [f for f in glob.glob(os.path.join(data_dir, '*.jsonl'))
             if '.trajectory' not in f and '.lock' not in f]
    if not files:
        return None
    return max(files, key=os.path.getctime)


def parse_rounds(filepath, max_rounds=0):
    """
    从 JSONL 文件读取 assistant 消息的使用数据。
    返回最新在前的列表。每个元素：
      {"input": int, "cacheRead": int, "cacheMiss": int, "output": int,
       "totalContext": int, "cachePct": float, "time": str}
    
    max_rounds=0 表示不限制数量，返回全部。
    """
    rounds = []
    with open(filepath, 'rb') as f:
        f.seek(0, 2)
        pos = f.tell()
        buf = b''
        chunk = 4096

        while pos > 0:
            if max_rounds > 0 and len(rounds) >= max_rounds:
                break

            read_size = min(chunk, pos)
            pos -= read_size
            f.seek(pos)
            buf = f.read(read_size) + buf
            lines = buf.split(b'\n')

            if pos > 0:
                buf = lines[0]
                lines = lines[1:]
            else:
                buf = b''

            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line.decode('utf-8'))
                except Exception:
                    continue

                msg = entry.get("message", {})
                if msg.get("role") != "assistant":
                    continue
                usage = msg.get("usage", {})
                if not usage or not usage.get("input", 0):
                    continue

                inp = usage.get("input", 0)
                cache_hit = usage.get("cacheRead", 0) or usage.get("input_cache_hit_tokens", 0)
                cache_miss = inp
                total_ctx = inp + cache_hit
                rate = round(cache_hit / max(total_ctx, 1) * 100, 1)

                rounds.append({
                    "input": inp,
                    "cacheRead": cache_hit,
                    "cacheMiss": cache_miss - cache_hit,
                    "output": usage.get("output", 0) or usage.get("output_tokens", 0),
                    "totalContext": total_ctx,
                    "cachePct": rate,
                    "time": entry.get("ts", entry.get("time", "")),
                })

    return rounds


def compute_stats(rounds, rates=None, realtime_window=20):
    """
    从 rounds 列表计算统计数据。
    
    返回：
    {
        "roundCount": int,          # 总轮数
        "overall": { "hitPct": % }, # 全部历史命中率
        "realtime": { "hitPct": % },# 最近 N 轮的实时命中率
        "cost": { "total": ¥, "savings": ¥, ... },
        "latest_round": {...},      # 最新一轮（给顶部栏）
    }
    """
    if not rounds:
        return {
            "roundCount": 0,
            "overall": {"hitPct": 0, "totalInput": 0, "totalCache": 0},
            "realtime": {"hitPct": 0},
            "cost": {"total": 0, "savings": 0, "perRound": []},
            "latest_round": None,
        }

    rates = rates or DEFAULT_RATES

    total_input = sum(r["input"] for r in rounds)
    total_cache = sum(r["cacheRead"] for r in rounds)

    # 全部历史
    overall_hit = round(total_cache / max(total_input + total_cache, 1) * 100, 1)

    # 实时：最近 N 轮
    recent = rounds[:realtime_window]
    recent_input = sum(r["input"] for r in recent)
    recent_cache = sum(r["cacheRead"] for r in recent)
    realtime_hit = round(recent_cache / max(recent_input + recent_cache, 1) * 100, 1)

    # 费用
    total_output = sum(r["output"] for r in rounds)
    
    # 实际花费 = input miss (大部分input是miss) * miss费率 + hit * hit费率 + output
    # 注意: DeepSeek API 的 cache 是先按全部 input 收费
    # 然后在 cache hit 时只收折 rate。
    # 所以实际花费应该是:
    # total_cost = (total_input * rates["input_miss"]) + (total_cache * rates["input_hit"]) + (total_output * rates["output"])
    total_cost_cny = (
        total_input * rates["input_miss"]
        + total_cache * rates["input_hit"]
        + total_output * rates["output"]
    )

    # 如果没有缓存，总花费应该是
    no_cache_cost = (total_input + total_cache) * rates["input_miss"] + total_output * rates["output"]
    savings = max(0, no_cache_cost - total_cost_cny)

    per_round_costs = []
    for r in rounds:
        c = (
            r["input"] * rates["input_miss"]
            + r["cacheRead"] * rates["input_hit"]
            + r["output"] * rates["output"]
        )
        per_round_costs.append(c)

    # 最高/最低缓存轮
    max_cache_round = max(rounds, key=lambda r: r["cachePct"]) if rounds else None
    min_cache_round = min(rounds, key=lambda r: r["cachePct"]) if rounds else None

    return {
        "roundCount": len(rounds),
        "overall": {
            "hitPct": overall_hit,
            "totalInput": total_input,
            "totalCache": total_cache,
            "totalOutput": total_output,
        },
        "realtime": {
            "hitPct": realtime_hit,
            "windowSize": realtime_window,
            "roundsInWindow": len(recent),
            "inputInWindow": recent_input,
            "cacheInWindow": recent_cache,
        },
        "cost": {
            "total": round(total_cost_cny, 4),
            "savings": round(savings, 4),
            "perRound": per_round_costs,
        },
        "maxCacheRound": {
            "pct": max_cache_round["cachePct"],
            "round": max_cache_round,
        } if max_cache_round else None,
        "minCacheRound": {
            "pct": min_cache_round["cachePct"],
            "round": min_cache_round,
        } if min_cache_round else None,
        "latest_round": rounds[0] if rounds else None,
    }


def get_cache_stats(data_dir=None, realtime_window=20):
    """
    对外唯一接口。
    返回完整缓存统计（无限轮数 + 实时窗口 + 健康指标）。
    """
    fp = load_file(data_dir) if data_dir else None
    if not fp:
        return {"ok": True, "rounds": [], "stats": compute_stats([])}

    all_rounds = parse_rounds(fp, max_rounds=0)
    stats = compute_stats(all_rounds, realtime_window=realtime_window)

    return {
        "ok": True,
        "sessionFile": fp,
        "rounds": all_rounds,
        "stats": stats,
    }
