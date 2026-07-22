"""
缓存命中率统计工具 — 从 edit-web.py 拆分出来的独立模块

用法：
    from cache_stats_helper import get_cache_stats
    result = get_cache_stats(data_dir)
    # result = {"ok": True, "rounds": [...], "summary": {...}, "previousRound": {...}|None}
"""

import os
import json
import glob


def get_cache_stats(data_dir):
    """
    解析会话文件，返回缓存命中统计。
    
    返回格式：
    {
        "ok": True,
        "rounds": [ ... ],         # 所有轮次（最多50条），最新在前
        "summary": { ... },        # 聚合摘要
        "previousRound": {...}|None,  # 上一轮缓存（给顶部状态栏用）
    }
    """
    try:
        files = [f for f in glob.glob(os.path.join(data_dir, '*.jsonl'))
                 if '.trajectory' not in f]
        if not files:
            return _empty_result()

        sf = max(files, key=os.path.getctime)
        all_rounds = _parse_rounds_from_file(sf, max_rounds=50)

        # 上一轮 = 寻找最近一个有缓存数据的轮次
        # rounds[0] 是当前正在生成的回复（cachePct=0），跳过它
        prev = None
        for r in all_rounds[1:]:
            if r.get('cacheRead', 0) > 0 and r.get('cachePct', 0) > 0:
                prev = r
                break
        if prev is None and len(all_rounds) > 1:
            # 仅当所有历史轮都0缓存时，回退到第二新
            prev = all_rounds[1]
        elif prev is None and len(all_rounds) == 1:
            # 只有一轮（新session或刚压缩），显示暂无
            prev = None

        # 计算聚合摘要
        total_input = sum(r['input'] for r in all_rounds)
        total_cache = sum(r['cacheRead'] for r in all_rounds)
        total_output = sum(r['output'] for r in all_rounds)
        total_ctx = total_input + total_cache
        total_cost = sum(r['cost'] for r in all_rounds)

        # 缓存节约 = 用缓存替代了多少 input token 的费用
        # cache 费率 = $0.025/M, input 费率 = $3.0/M
        cache_savings = sum(
            r['cacheRead'] * (3.0 - 0.025) / 1000000
            for r in all_rounds
            if r['cacheRead'] > 0
        )

        avg_pct = round(
            total_cache / max(total_ctx, 1) * 100, 1
        ) if all_rounds else 0

        return {
            "ok": True,
            "rounds": all_rounds,
            "summary": {
                "roundCount": len(all_rounds),
                "avgCachePct": avg_pct,
                "totalCost": round(total_cost, 4),
                "cacheSavings": round(cache_savings, 4),
                "overallHitPct": avg_pct,
                "totalInput": total_input,
                "totalCache": total_cache,
                "totalOutput": total_output,
                "totalContext": total_ctx,
            },
            "previousRound": prev,  # 上一轮（给顶部状态栏快速显示）
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _parse_rounds_from_file(filepath, max_rounds=50):
    """从 JSONL 文件末尾倒读 assistant 消息的使用数据"""
    rounds = []
    with open(filepath, 'rb') as f:
        f.seek(0, 2)
        pos = f.tell()
        buf = b''
        chunk = 4096

        while pos > 0 and len(rounds) < max_rounds:
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
                cache = usage.get("cacheRead", 0)
                out = usage.get("output", 0)
                total_ctx = inp + cache
                rate = round(cache / max(total_ctx, 1) * 100, 1)

                rounds.append({
                    "input": inp,
                    "cacheRead": cache,
                    "output": out,
                    "totalContext": total_ctx,
                    "cachePct": rate,
                    "cost": round(
                        (cache * 0.025 + inp * 3.0 + out * 8.0) / 1000000, 5
                    ),
                })

    return rounds


def _empty_result():
    return {
        "ok": True,
        "rounds": [],
        "summary": {
            "roundCount": 0,
            "avgCachePct": 0,
            "totalCost": 0,
            "cacheSavings": 0,
            "overallHitPct": 0,
            "totalInput": 0,
            "totalCache": 0,
            "totalOutput": 0,
            "totalContext": 0,
        },
        "previousRound": None,
    }
