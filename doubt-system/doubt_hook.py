#!/usr/bin/env python3
"""
doubt_hook.py — 怀疑系统主动钩子（2026-08-10 部署钩子工程）
=============================================================
dandan 2026-08-10 拍板：怀疑系统要在"日常工作中首先怀疑部署是否正确"。
本脚本把怀疑从"被动记账"变成"主动触发"——任何部署/变更/异常点调用它，
即生成一条 doubt_episode（账本 + 总线 → LMS /feed 塑形）。

用法（零依赖，stdlib only，fail-open，任何异常静默）：
    python3 doubt_hook.py --deploy "start_all.sh 全服务启动"     # 部署/重启后
    python3 doubt_hook.py --deploy "lms_ctl.sh restart" --health http://127.0.0.1:8190/health
    python3 doubt_hook.py --fail "verify_daemon 连续3次FAIL"     # 异常即怀疑
    python3 doubt_hook.py --patrol                              # 夜巡每日注入（可选）

设计：
- 触发类型：--deploy → novelty（新状态需复核）；--fail → conflict（与预期冲突）
- 自定位：脚本所在目录 → ../../memory-integration-layer 找 doubt_adapter（不硬编码）
- DOUBT_BUS_FILE：优先读 memory-integration-layer/.env，其次环境变量
- 部署钩子附带基础自检（--health 时探活），结果写进 suspicion 叙事
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# ── 自定位（相对推导，绝不硬编码绝对路径）────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
# doubt-system/ 的上级是 Agent OS/；胶水层是兄弟目录 memory-integration-layer
_GLUE_DIR = _SCRIPT_DIR.parent.parent / "memory-integration-layer"
if not (_GLUE_DIR / "interfaces" / "adapters" / "doubt_adapter.py").exists():
    # 兜底：常见机器布局
    _GLUE_DIR = Path("/vol2/1000/AI专用/memory-integration-layer")


def _load_env_bus_file() -> str | None:
    """从胶水层 .env 读 DOUBT_BUS_FILE（cron/子代理环境不一定有该变量）。"""
    env_path = _GLUE_DIR / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("DOUBT_BUS_FILE="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
        except Exception:
            pass
    return os.environ.get("DOUBT_BUS_FILE")


def _health_check(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    """部署自检：探活一个健康端点。失败不阻断怀疑写入。"""
    if not url:
        return True, "未指定健康端点"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200, f"HTTP {r.status}"
    except Exception as e:
        return False, f"探活失败: {type(e).__name__}"


def _emit(trigger_type: str, suspicion: str, topic: str,
          health_url: str | None, queried: str = "部署/变更正确性") -> bool:
    """写怀疑账本 + 总线发布。全链路 fail-open。"""
    try:
        sys.path.insert(0, str(_GLUE_DIR))
        os.environ.setdefault("DOUBT_BUS_FILE", _load_env_bus_file() or "")
        from interfaces.adapters.doubt_adapter import store_doubt

        health_ok, health_note = _health_check(health_url) if health_url else (True, "")
        if health_url:
            suspicion = f"{suspicion} [自检: {health_note}]"

        ok = store_doubt({
            "trigger_type": trigger_type,
            "suspicion": suspicion[:200],
            "queried": queried,
            "answer_changed": False,
            "overturn_evidence": "",
            "user_reaction": "silent",  # 钩子触发，无用户反应（枚举: corrected/acknowledged/silent/rejected）
            "topic": topic[:100],
            "confidence_after": 0.5 if health_ok else 0.3,
        })
        return bool(ok)
    except Exception as e:
        # fail-open：钩子任何异常不影响主流程
        sys.stderr.write(f"[doubt_hook] 失败(静默): {type(e).__name__}: {e}\n")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="怀疑系统主动钩子")
    ap.add_argument("--deploy", help="部署/变更描述（trigger=novelty）")
    ap.add_argument("--fail", help="异常描述（trigger=conflict）")
    ap.add_argument("--health", help="部署自检健康端点 URL")
    ap.add_argument("--topic", default="deploy", help="主题词")
    ap.add_argument("--quiet", action="store_true", help="成功也不输出")
    args = ap.parse_args()

    if args.deploy:
        ok = _emit("novelty", f"部署完成: {args.deploy}", args.topic, args.health)
    elif args.fail:
        ok = _emit("conflict", f"异常: {args.fail}", args.topic, None)
    else:
        ap.error("需要 --deploy 或 --fail")
        return 2

    if not args.quiet:
        print(f"[doubt_hook] {'✅ 已记录' if ok else '⚠️ 写入失败(静默)'}: "
              f"{args.deploy or args.fail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
