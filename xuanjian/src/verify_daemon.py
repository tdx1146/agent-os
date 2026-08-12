#!/usr/bin/env python3
"""
玄鉴守护进程 v0.1
=================
独立守护进程，监控 data/operation_log.jsonl 的新条目，
对涉及文件变更的条目做关键词重叠度校验，
结果写入 data/daemon_audit.log。

用法:
    cd <玄鉴目录>   # 2026-08-12 起玄鉴已并入 agent-os/xuanjian
    python3 src/verify_daemon.py &

依赖: Python 3.11 标准库（无第三方包）
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── 项目根 ──────────────────────────────────────────────────────────────
# 我们假定守护进程从项目根目录启动（调用者 cd 到项目根再执行）
PROJECT_ROOT = Path.cwd().resolve()

# 用确定性的路径来定位重要文件，避免 chdir 依赖
_SCRIPT = Path(__file__).resolve().parent  # src/
_PROJECT_PARENT = _SCRIPT.parent           # 项目根（玄鉴目录，如 agent-os/xuanjian）
if _PROJECT_PARENT == PROJECT_ROOT:
    pass  # 一致，OK
elif not (PROJECT_ROOT / "src" / "verify_daemon.py").exists():
    # 如果 cwd 不是项目根但脚本在 src/ 下，用脚本定位
    PROJECT_ROOT = _PROJECT_PARENT
    os.chdir(PROJECT_ROOT)

DATA_DIR = PROJECT_ROOT / "data"
LOG_PATH = DATA_DIR / "operation_log.jsonl"
AUDIT_PATH = DATA_DIR / "daemon_audit.log"
SEEK_PATH = DATA_DIR / "daemon.seek"
PID_PATH = DATA_DIR / "daemon.pid"
PURPOSE_HASH_PATH = DATA_DIR / "purpose.sha256"

# ── 内核层规范路径 ───────────────────────────────────────────────────────
# 2026-08-12 玄鉴并入 agent-os 时参数化：默认值向后兼容本机部署，
# 新机器用 XJ_* 环境变量覆盖（复现缺口清单 #2：路径不硬编码）。
def _env_path(name: str, default: str) -> Path:
    """读取环境变量路径，缺省回退到默认值（向后兼容本机部署）"""
    raw = os.environ.get(name)
    return Path(raw).resolve() if raw else Path(default).resolve()


KERNEL_SPEC_DIR = _env_path("XJ_KERNEL_SPEC_DIR", "/vol2/1000/AI专用/AgentOS-IsoSand/内核层规范")
PURPOSE_PATH = KERNEL_SPEC_DIR / "PURPOSE.md"
SNAPSHOTS_DIR = KERNEL_SPEC_DIR / "snapshots"

# ── 工具函数 ────────────────────────────────────────────────────────────

def iso_now() -> str:
    """返回 ISO8601 时间字符串（含时区）"""
    return datetime.now(timezone.utc).astimezone().isoformat()


def write_audit(record: dict) -> None:
    """追加一条审计日志到 daemon_audit.log（关键字段前置）"""
    line = json.dumps(record, ensure_ascii=False)
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_pid() -> None:
    """记录当前 PID"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PID_PATH, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()) + "\n")


def read_seek() -> int:
    """读取上一次读取到的文件偏移（字节）"""
    if SEEK_PATH.exists():
        with open(SEEK_PATH, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            if raw:
                return int(raw)
    return 0


def write_seek(pos: int) -> None:
    """持久化当前读取位置"""
    with open(SEEK_PATH, "w", encoding="utf-8") as f:
        f.write(str(pos) + "\n")


def extract_filenames(text: str) -> list[str]:
    """
    从文本中提取文件名，匹配模式：
      - src/xxx.py
      - docs/xxx.md
      - 也匹配 tests/xxx.py 等常见代码路径
    返回去重后的文件名列表。
    """
    pattern = r'(?:src|docs|tests|data|deploy|backups|revisions)/[^\s\'\"`,)]+\.(?:py|md|jsonl|json|txt|sh|yaml|yml|cfg|ini|env)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    return list(dict.fromkeys(m.strip() for m in matches))


def git_diff_stat(filepath: str) -> str:
    """
    对指定文件执行 git diff --stat，返回输出文本。
    如果文件不在 git 跟踪中或 diff 为空，返回空字符串。
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "--", filepath],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return f"<git-diff-error: {e}>"


def tokenize(text: str) -> set[str]:
    """
    将文本分词为小写词集合（仅含字母/数字/下划线的词）。
    排除纯数字、单字符、以及常见的停用词。
    """
    STOP_WORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "can",
        "could", "shall", "should", "may", "might", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "and", "or", "not", "but", "if",
        "as", "it", "its", "this", "that", "these", "those", "i", "we", "you",
        "he", "she", "they", "me", "my", "our", "your", "his", "her", "their",
        "my", "our", "your", "his", "her", "its", "their", "mine", "ours",
        "yours", "hers", "theirs",
        # 中文常用停用词
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会",
        "着", "没有", "看", "好", "自己", "这", "他", "她", "它", "们",
    })
    tokens: set[str] = set()
    for word in re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", text.lower().strip()):
        if len(word) <= 1:
            continue
        if word.isdigit():
            continue
        if word in STOP_WORDS:
            continue
        tokens.add(word)
    return tokens


def compute_overlap(detail_words: set[str], diff_words: set[str]) -> float:
    """
    计算关键词重叠度: |detail ∩ diff| / |detail|（如果 detail 非空）
    如果 detail 为空则返回 0。
    """
    if not detail_words:
        return 0.0
    if not diff_words:
        return 0.0
    intersection = detail_words & diff_words
    return round(len(intersection) / len(detail_words), 4)


def classify_overlap(overlap: float) -> str:
    """根据重叠度返回 PASS / SUSPECT / FAIL"""
    if overlap > 0.5:
        return "PASS"
    elif overlap >= 0.2:
        return "SUSPECT"
    else:
        return "FAIL"


def append_warn_to_operation_log(detail_text: str) -> None:
    """追加一条 WARN 到 operation_log.jsonl"""
    warn_entry = {
        "t": iso_now(),
        "level": "WARN",
        "actor": "verify_daemon",
        "action": "keyword_verify_fail_threshold",
        "target": "daemon_audit.log",
        "result": "WARN",
        "detail": detail_text,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(warn_entry, ensure_ascii=False) + "\n")
    # 怀疑钩子：异常即怀疑（玄鉴发现连续 FAIL → 生成 conflict 怀疑，喂 LMS）
    # 子进程调用 doubt_hook.py，fail-open 不阻断玄鉴主循环
    try:
        import subprocess
        _hook = _env_path("XJ_DOUBT_HOOK", "/vol2/1000/AI专用/Agent OS/doubt-system/doubt_hook.py")
        if _hook.exists():
            subprocess.Popen(
                [sys.executable, str(_hook), "--fail", f"verify_daemon: {detail_text[:150]}",
                 "--topic", "verify-daemon", "--quiet"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass  # fail-open


# ── 目的完整性检查 ──────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    """计算文件的 SHA256 十六进制摘要"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_latest_snapshot() -> Path | None:
    """在 snapshots/ 中找出最新（按名称排序）的快照目录"""
    if not SNAPSHOTS_DIR.is_dir():
        return None
    snapshots = sorted(
        [d for d in SNAPSHOTS_DIR.iterdir() if d.is_dir() and d.name.startswith("snapshot_")],
        reverse=True,
    )
    return snapshots[0] if snapshots else None


def _check_purpose_integrity() -> None:
    """
    职责2：目的文档完整性检查
    - 首次启动：记录 PURPOSE.md 的 SHA256 指纹
    - 后续检查：比对 SHA256，不一致则 WARN，丢失/空则 FAIL 并从快照恢复
    """
    # 1. 计算当前指纹（如果文件存在且非空）
    current_hash = None
    purpose_exists = PURPOSE_PATH.is_file()
    purpose_nonempty = purpose_exists and PURPOSE_PATH.stat().st_size > 0

    if purpose_nonempty:
        try:
            current_hash = _sha256_file(PURPOSE_PATH)
        except OSError as e:
            audit_msg = {
                "t": iso_now(),
                "level": "ERROR",
                "detector": "purpose_integrity_v0.1",
                "task_id": "purpose-check",
                "claim_actor": "system",
                "keyword_overlap": 0.0,
                "result": "ERROR",
                "detail": f"PURPOSE.md 读取失败: {e}",
            }
            write_audit(audit_msg)
            return

    # 2. 读取已存储的指纹
    stored_hash = None
    if PURPOSE_HASH_PATH.is_file():
        try:
            stored_hash = PURPOSE_HASH_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            stored_hash = None

    # 3. 首次启动：存储指纹
    if stored_hash is None and purpose_nonempty:
        try:
            PURPOSE_HASH_PATH.write_text(current_hash + "\n", encoding="utf-8")
        except OSError as e:
            write_audit({
                "t": iso_now(),
                "level": "ERROR",
                "detector": "purpose_integrity_v0.1",
                "task_id": "purpose-check",
                "claim_actor": "system",
                "keyword_overlap": 0.0,
                "result": "ERROR",
                "detail": f"无法写入指纹文件 {PURPOSE_HASH_PATH.name}: {e}",
            })
        return  # 首次无检查

    # 4. 常规检查
    # 4a. 文件丢失或为空 → FAIL
    if not purpose_exists or not purpose_nonempty:
        fail_detail = (
            f"PURPOSE.md 缺失" if not purpose_exists
            else "PURPOSE.md 为空"
        )
        write_audit({
            "t": iso_now(),
            "level": "FAIL",
            "detector": "purpose_integrity_v0.1",
            "task_id": "purpose-check",
            "claim_actor": "system",
            "keyword_overlap": 0.0,
            "result": "FAIL",
            "detail": f"{fail_detail}，尝试从快照恢复",
        })
        # 尝试从最新快照恢复
        latest = _find_latest_snapshot()
        if latest is not None:
            snapshot_purpose = latest / "purpose" / "PURPOSE.md"
            if snapshot_purpose.is_file():
                try:
                    shutil.copy2(snapshot_purpose, PURPOSE_PATH)
                    restored_hash = _sha256_file(PURPOSE_PATH)
                    PURPOSE_HASH_PATH.write_text(restored_hash + "\n", encoding="utf-8")
                    write_audit({
                        "t": iso_now(),
                        "level": "WARN",
                        "detector": "purpose_integrity_v0.1",
                        "task_id": "purpose-check",
                        "claim_actor": "system",
                        "keyword_overlap": 0.0,
                        "result": "WARN",
                        "detail": f"从快照 {latest.name}/purpose/PURPOSE.md 恢复成功",
                    })
                except OSError as e:
                    write_audit({
                        "t": iso_now(),
                        "level": "FAIL",
                        "detector": "purpose_integrity_v0.1",
                        "task_id": "purpose-check",
                        "claim_actor": "system",
                        "keyword_overlap": 0.0,
                        "result": "FAIL",
                        "detail": f"从快照恢复失败: {e}",
                    })
            else:
                write_audit({
                    "t": iso_now(),
                    "level": "FAIL",
                    "detector": "purpose_integrity_v0.1",
                    "task_id": "purpose-check",
                    "claim_actor": "system",
                    "keyword_overlap": 0.0,
                    "result": "FAIL",
                    "detail": f"快照 {latest.name} 中缺少 purpose/PURPOSE.md，无法恢复",
                })
        else:
            write_audit({
                "t": iso_now(),
                "level": "FAIL",
                "detector": "purpose_integrity_v0.1",
                "task_id": "purpose-check",
                "claim_actor": "system",
                "keyword_overlap": 0.0,
                "result": "FAIL",
                "detail": "snapshots/ 目录为空或不存在，无法恢复",
            })
        return

    # 4b. 指纹不匹配 → WARN
    if stored_hash and current_hash and current_hash != stored_hash:
        write_audit({
            "t": iso_now(),
            "level": "WARN",
            "detector": "purpose_integrity_v0.1",
            "task_id": "purpose-check",
            "claim_actor": "system",
            "keyword_overlap": 0.0,
            "result": "WARN",
            "detail": f"PURPOSE.md 指纹不匹配 (期望 {stored_hash[:16]}..., 当前 {current_hash[:16]}...)",
        })
        return

    # 4c. 一切正常 → 静默通过


# ── 主循环 ──────────────────────────────────────────────────────────────

# ── 推送真实性验证（push_verify_v0.1）──────────────────────────────────
# 三仓路径与 agent-os TOPOLOGY.md 权威拓扑一致（2026-08-10 加入）
# 2026-08-11 修复 ahead 计数：改用 rev-list 双向计数（详见 _check_push_integrity docstring）
PUSH_REPOS = {
    "living-memory-system": os.environ.get("XJ_REPO_LMS", "/vol2/1000/AI专用/living-memory-system-cloud"),
    "memory-integration-layer": os.environ.get("XJ_REPO_GLUE", "/vol2/1000/AI专用/memory-integration-layer"),
    "agent-os": os.environ.get("XJ_REPO_AGENTOS", "/vol2/1000/AI专用/Agent OS"),
}


def _check_push_integrity() -> None:
    """
    职责3：推送真实性验证
    针对"声称推送成功、实际未推送"的偏离（2026-08-10 dandan 指出玄鉴盲区）：
    对三仓执行 git rev-list 双向计数（远端SHA..HEAD / HEAD..远端SHA）+ ls-remote：
    - 本地领先远端（ahead>0）或本地/远端 HEAD 不一致 → FAIL
    - ls-remote 失败（网络/token/认证）→ WARN（无法验证，推送能力存疑）
    - 一致 → 不写日志（静默，避免刷屏）
    ahead 计数用 ls-remote 实测远端 SHA 而非 status -sb / 本地跟踪引用
    （2026-08-11 修复：未配 upstream 时 `git status -sb` 不显示 [ahead N]
    → 假 ahead=0，审计 C-11/VD-03 根因误导；双向计数同时暴露远端领先）。
    """
    for name, path in PUSH_REPOS.items():
        repo = Path(path)
        if not (repo / ".git").exists():
            write_audit({
                "t": iso_now(), "level": "WARN", "detector": "push_verify_v0.1",
                "task_id": "push-verify", "claim_actor": "system",
                "keyword_overlap": 0.0, "result": "WARN",
                "detail": f"[{name}] 仓库不存在: {path}",
            })
            continue
        try:
            remote_out = subprocess.run(
                ["git", "-C", path, "ls-remote", "origin", "HEAD"],
                capture_output=True, text=True, timeout=30,
            )
            if remote_out.returncode != 0:
                write_audit({
                    "t": iso_now(), "level": "WARN", "detector": "push_verify_v0.1",
                    "task_id": "push-verify", "claim_actor": "system",
                    "keyword_overlap": 0.0, "result": "WARN",
                    "detail": f"[{name}] ls-remote 失败（网络/token/认证?）: {remote_out.stderr.strip()[:120]}",
                })
                continue
            remote_sha = remote_out.stdout.split()[0] if remote_out.stdout.strip() else ""
            local_head = subprocess.run(
                ["git", "-C", path, "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()

            # 双向 ahead/behind 计数（2026-08-11 修复）：
            # 旧实现解析 `git status -sb` 的 [ahead N]，但 agent-os 等仓库未配
            # upstream 时 status -sb 不显示 ahead 标记 → 假 ahead=0。改用 rev-list
            # 双向计数：本地领先 = 远端SHA..HEAD，远端领先 = HEAD..远端SHA。用
            # ls-remote 实测 SHA（而非本地 origin/main 跟踪引用）计数，不受跟踪引用
            # 缺失/过期影响。ahead/behind=-1 表示无法计数（FAIL 判定仍由 SHA 兜底）。
            ahead = behind = -1
            if remote_sha:
                for label, ref in (("ahead", f"{remote_sha}..HEAD"), ("behind", f"HEAD..{remote_sha}")):
                    try:
                        p = subprocess.run(
                            ["git", "-C", path, "rev-list", "--count", ref],
                            capture_output=True, text=True, timeout=20,
                        )
                        if p.returncode == 0 and p.stdout.strip().isdigit():
                            if label == "ahead":
                                ahead = int(p.stdout.strip())
                            else:
                                behind = int(p.stdout.strip())
                    except Exception:
                        pass

            if ahead > 0 or (remote_sha and local_head and remote_sha != local_head):
                write_audit({
                    "t": iso_now(), "level": "FAIL", "detector": "push_verify_v0.1",
                    "task_id": "push-verify", "claim_actor": "system",
                    "keyword_overlap": 0.0, "result": "FAIL",
                    "detail": (f"[{name}] 声称推送成功但实际未推送: 本地领先远端 ahead={ahead}, "
                               f"远端领先本地 behind={behind}, "
                               f"本地HEAD={local_head[:8] or '?'}, 远端HEAD={remote_sha[:8] or '未知'}"),
                })
        except Exception as e:
            write_audit({
                "t": iso_now(), "level": "WARN", "detector": "push_verify_v0.1",
                "task_id": "push-verify", "claim_actor": "system",
                "keyword_overlap": 0.0, "result": "WARN",
                "detail": f"[{name}] 检查异常: {type(e).__name__}: {e}",
            })


def run_scan() -> None:
    """
    扫描 operation_log.jsonl 的新条目并执行关键词校验。
    本函数只处理本轮新发现的条目。
    """
    # 确保日志文件存在
    if not LOG_PATH.exists():
        write_audit({
            "t": iso_now(),
            "level": "INFO",
            "detector": "keyword_v0.1",
            "task_id": "daemon-startup",
            "claim_actor": "system",
            "keyword_overlap": 0.0,
            "result": "SKIP",
            "detail": "operation_log.jsonl 不存在，等待创建",
        })
        return

    old_pos = read_seek()
    current_size = LOG_PATH.stat().st_size

    if current_size < old_pos:
        # 文件被截断/重建，从头开始
        old_pos = 0

    if current_size == old_pos:
        # 没有新条目
        return

    # 读取新内容
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        f.seek(old_pos)
        new_lines = f.readlines()
        new_pos = f.tell()

    if not new_lines:
        write_seek(new_pos)
        return

    # 逐条处理
    consecutive_fail_count = 0
    last_fail_detail = ""

    for line in new_lines:
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # 检查必要字段
        actor = entry.get("actor")
        action = entry.get("action")
        detail = entry.get("detail")
        task_id = entry.get("trace_id", "unknown")

        if not (actor and action and detail):
            continue

        # 提取文件名
        filenames = extract_filenames(detail)
        if not filenames:
            continue

        # 对每个文件做校验（取平均值）
        overlaps: list[float] = []
        detail_tokens = tokenize(detail)

        for fname in filenames:
            diff_out = git_diff_stat(fname)
            if not diff_out or diff_out.startswith("<git-diff-error"):
                overlaps.append(0.0)
                continue
            diff_tokens = tokenize(diff_out)
            overlaps.append(compute_overlap(detail_tokens, diff_tokens))

        avg_overlap = round(sum(overlaps) / len(overlaps), 4) if overlaps else 0.0
        result = classify_overlap(avg_overlap)

        # 构造审计日志
        audit_entry = {
            "t": iso_now(),
            "level": "WARN" if result == "FAIL" else "INFO" if result == "PASS" else "WARN",
            "detector": "keyword_v0.1",
            "task_id": task_id,
            "claim_actor": actor,
            "keyword_overlap": avg_overlap,
            "result": result,
        }

        if result == "FAIL":
            audit_entry["detail"] = "detail中的关键词未能匹配到git diff"
        elif result == "SUSPECT":
            audit_entry["detail"] = f"关键词部分匹配，重叠度 {avg_overlap}"
        else:
            audit_entry["detail"] = f"关键词验证通过，重叠度 {avg_overlap}（文件: {', '.join(filenames)}）"

        write_audit(audit_entry)

        # 连续 FAIL 计数
        if result == "FAIL":
            consecutive_fail_count += 1
            last_fail_detail = f"连续 {consecutive_fail_count} 次 FAIL；最近一次: task_id={task_id}, actor={actor}"
        else:
            consecutive_fail_count = 0

    # 如果连续 3 次 FAIL，追加一条 WARN 到 operation_log.jsonl
    if consecutive_fail_count >= 3:
        append_warn_to_operation_log(last_fail_detail)
        # 复位计数器（因为我们已经发出了 WARN）
        # 注：实际连续 FAIL 会由下一个循环周期重新计数

    # 更新 seek 位置
    write_seek(new_pos)


def main() -> None:
    """守护进程入口"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_pid()

    # 启动日志
    start_msg = {
        "t": iso_now(),
        "level": "INFO",
        "detector": "keyword_v0.1",
        "task_id": "daemon-startup",
        "claim_actor": "system",
        "keyword_overlap": 0.0,
        "result": "OK",
        "detail": f"守护进程启动 (PID={os.getpid()})，监视线程每 30 秒扫描",
    }
    write_audit(start_msg)

    # 扫描计数器，用于调度周期任务
    scan_count = 0

    try:
        while True:
            try:
                scan_count += 1
                run_scan()
                # 每 10 次扫描（约 5 分钟）执行一次目的文档完整性 + 推送真实性检查
                if scan_count % 10 == 0:
                    _check_purpose_integrity()
                    _check_push_integrity()
            except Exception as e:
                # 捕获任何异常保证循环不崩溃
                error_msg = {
                    "t": iso_now(),
                    "level": "ERROR",
                    "detector": "keyword_v0.1",
                    "task_id": "daemon-loop",
                    "claim_actor": "system",
                    "keyword_overlap": 0.0,
                    "result": "ERROR",
                    "detail": f"扫描异常: {type(e).__name__}: {e}",
                }
                write_audit(error_msg)
            time.sleep(30)
    except KeyboardInterrupt:
        exit_msg = {
            "t": iso_now(),
            "level": "INFO",
            "detector": "keyword_v0.1",
            "task_id": "daemon-shutdown",
            "claim_actor": "system",
            "keyword_overlap": 0.0,
            "result": "OK",
            "detail": f"守护进程优雅退出 (PID={os.getpid()})",
        }
        write_audit(exit_msg)
        sys.exit(0)


if __name__ == "__main__":
    main()
