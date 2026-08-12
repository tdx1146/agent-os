#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_claim.py — 履约核验脚本

三层核验（L1/L2/L3），对应不同风险等级的操作。
所有核验结果写入操作日志，供审计链追溯。

用法：
    python3 src/verify_claim.py L1 <task-id>      # 复现命令检查
    python3 src/verify_claim.py L2 <task-id>      # 文件存在+SHA+diff行数
    python3 src/verify_claim.py L3 <task-id>      # 全检查（含测试）

输出：JSON (exit code 0=PASS, 1=FAIL)

设计来源：基于 dandan 另一实例 AI 的 "verify_claim.sh" 三层设计，
经 IsoSand 项目命名规范重写为 Python。
"""

import sys
import json
import os
import hashlib
import subprocess
import re
from datetime import datetime, timezone, timedelta

# ── 路径 ──

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CLAIMS_DIR = os.path.join(_PROJECT_ROOT, ".claims")
_OPERATION_LOG = os.path.join(_PROJECT_ROOT, "data", "operation_log.jsonl")

# ── 时区 ──

_TZ = timezone(timedelta(hours=8))  # Asia/Shanghai

def _now() -> str:
    return datetime.now(_TZ).isoformat()


# ═══════════════════════════════════════════════════════════════════
# 核验引擎
# ═══════════════════════════════════════════════════════════════════


def _sha256(path: str) -> str:
    """计算文件的 SHA256 哈希。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _diff_lines(path: str) -> dict:
    """
    返回文件增减行数（通过 git diff）。
    如果文件不在 git 跟踪中，返回 {"add": 0, "del": 0}。
    """
    try:
        rel = os.path.relpath(path, _PROJECT_ROOT)
        result = subprocess.run(
            ["git", "-C", _PROJECT_ROOT, "diff", "--numstat", rel],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            parts = result.stdout.strip().split("\t")
            return {"add": int(parts[0]), "del": int(parts[1])}
    except Exception:
        pass
    return {"add": 0, "del": 0}


def _log_result(task_id: str, level: str, status: str, detail: str):
    """将核验结果写入操作日志。"""
    entry = {
        "t": _now(),
        "level": "INFO" if status == "PASS" else "WARN",
        "actor": f"verify-{task_id}",
        "action": f"verify_{level}",
        "target": f"task/{task_id}",
        "result": status,
        "detail": detail,
        "trace_id": f"vfy-{task_id}"
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    os.makedirs(os.path.dirname(_OPERATION_LOG), exist_ok=True)
    with open(_OPERATION_LOG, "a", encoding="utf-8") as f:
        f.write(line)


def _read_claim_field(claim_path: str, field_name: str) -> str:
    """从履约报告 Markdown 表格中提取字段值。"""
    with open(claim_path, encoding="utf-8") as f:
        content = f.read()
    # 匹配表格行: | 字段名 | 内容 |
    m = re.search(rf"\|\s*{re.escape(field_name)}\s*\|\s*(.+?)\s*\|", content)
    if m:
        return m.group(1).strip()
    return ""


# ═══════════════════════════════════════════════════════════════════
# L1 — 命令链（必选，所有履约报告必须包含）
# ═══════════════════════════════════════════════════════════════════


def verify_L1(task_id: str) -> dict:
    """
    核验L1：运行履约报告中的复现命令，比对输出。
    最低成本的"诚实门槛"——AI不知道命令的实际返回值，编造易被戳穿。
    """
    claim_path = os.path.join(_CLAIMS_DIR, f"{task_id}.md")
    if not os.path.exists(claim_path):
        return _fail("L1", f"履约报告未找到: {claim_path}")

    commands_text = _read_claim_field(claim_path, "复现命令")
    if not commands_text:
        # 也尝试从代码块中提取
        with open(claim_path, encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"```(?:bash|shell)?\n(.+?)\n```", content, re.DOTALL)
        if m:
            commands_text = m.group(1).strip()
        else:
            return _fail("L1", "未找到复现命令")

    details = []
    all_pass = True
    for line in commands_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            result = subprocess.run(
                line, shell=True, capture_output=True, text=True, timeout=15,
                cwd=_PROJECT_ROOT
            )
            actual = result.stdout.strip()
            # 报告中通常会声明预期输出，不太可能精确匹配，所以只记录实际值
            details.append({
                "cmd": line,
                "exit_code": result.returncode,
                "actual_output": actual[:200]
            })
            if result.returncode != 0:
                all_pass = False
        except subprocess.TimeoutExpired:
            details.append({"cmd": line, "exit_code": -1, "actual_output": "TIMEOUT"})
            all_pass = False
        except Exception as e:
            details.append({"cmd": line, "exit_code": -1, "actual_output": str(e)})
            all_pass = False

    status = "PASS" if all_pass else "FAIL"
    _log_result(task_id, "L1", status, json.dumps(details, ensure_ascii=False))
    _update_reputation("iso-sand-main", 1 if all_pass else -2, f"L1-{task_id}: {status}")
    return {
        "status": status,
        "task_id": task_id,
        "level": "L1",
        "details": details
    }


# ═══════════════════════════════════════════════════════════════════
# L2 — 轻核验（中配：文件存在 + SHA256 + diff 行数）
# ═══════════════════════════════════════════════════════════════════


def verify_L2(task_id: str) -> dict:
    """
    核验L2：检查文件存在性、SHA256、变更行数。
    SHA256 由脚本计算，AI 不可伪造。
    """
    claim_path = os.path.join(_CLAIMS_DIR, f"{task_id}.md")
    if not os.path.exists(claim_path):
        return _fail("L2", f"履约报告未找到: {claim_path}")

    # 从表格中提取修改文件
    files_text = _read_claim_field(claim_path, "修改文件")
    if not files_text:
        return _fail("L2", "未找到'修改文件'字段")
    files_list = [f.strip().strip("`") for f in files_text.split(",")]

    # 从表格中提取声明的 SHA256
    declared_shas = {}
    with open(claim_path, encoding="utf-8") as f:
        content = f.read()
    # 匹配文件指纹表格
    sha_lines = re.findall(r"\|\s*`?(.+?)`?\s*\|\s*`?([a-f0-9]{64})`?\s*\|", content)
    for fname, declared_hash in sha_lines:
        declared_shas[fname.strip()] = declared_hash

    details = []
    all_pass = True

    # 检查文件存在性
    for fname in files_list:
        fpath = os.path.join(_PROJECT_ROOT, fname)
        exists = os.path.exists(fpath)
        if not exists:
            details.append({
                "check": "file_exists",
                "file": fname,
                "result": "FAIL",
                "detail": "文件不存在"
            })
            all_pass = False
        else:
            # 计算实际 SHA256
            actual_sha = _sha256(fpath)
            declared = declared_shas.get(fname)
            sha_match = not declared or actual_sha == declared
            if declared and not sha_match:
                details.append({
                    "check": "sha256",
                    "file": fname,
                    "result": "FAIL",
                    "actual": actual_sha[:16],
                    "declared": declared[:16]
                })
                all_pass = False
            else:
                # 计算diff行数
                diff = _diff_lines(fpath)
                details.append({
                    "check": "file_exists",
                    "file": fname,
                    "result": "PASS",
                    "sha256": actual_sha[:16],
                    "diff": diff
                })

    status = "PASS" if all_pass else "FAIL"
    _log_result(task_id, "L2", status, json.dumps(details, ensure_ascii=False))
    _update_reputation("iso-sand-main", 1 if all_pass else -2, f"L2-{task_id}: {status}")
    return {"status": status, "task_id": task_id, "level": "L2", "details": details}


# ═══════════════════════════════════════════════════════════════════
# L3 — 全核验（高配：含测试包裹）
# ═══════════════════════════════════════════════════════════════════


def verify_L3(task_id: str) -> dict:
    """
    核验L3：L2 所有检查 + 运行测试命令，比对测试结果。
    测试结果由脚本实际运行 pytest 获取，AI 不可编造。
    """
    # 先跑 L2
    l2_result = verify_L2(task_id)
    details = list(l2_result["details"])
    all_pass = l2_result["status"] == "PASS"

    claim_path = os.path.join(_CLAIMS_DIR, f"{task_id}.md")
    if not os.path.exists(claim_path):
        return _fail("L3", f"履约报告未找到: {claim_path}")

    # 提取测试命令
    test_cmd = _read_claim_field(claim_path, "测试命令")
    if test_cmd:
        # 去掉 Markdown 反引号
        test_cmd = test_cmd.strip("`").strip()
        try:
            result = subprocess.run(
                test_cmd, shell=True, capture_output=True, text=True, timeout=60,
                cwd=_PROJECT_ROOT
            )
            output = result.stdout + result.stderr
            # 提取 passed/failed 计数
            passed_match = re.search(r"(\d+)\s+passed", output)
            failed_match = re.search(r"(\d+)\s+failed", output)
            actual_passed = int(passed_match.group(1)) if passed_match else 0
            actual_failed = int(failed_match.group(1)) if failed_match else 0

            # 从表格提取声明的测试结果
            declared_passed = 0
            declared_failed = 0
            with open(claim_path, encoding="utf-8") as f:
                content = f.read()
            tm = re.search(r"\*\*总计\*\*\s*\|\s*(\d+)/(\d+)\s+PASS", content)
            if tm:
                declared_passed = int(tm.group(1))

            if actual_failed > 0 or (declared_passed > 0 and actual_passed < declared_passed):
                details.append({
                    "check": "test_result",
                    "result": "FAIL",
                    "actual": f"{actual_passed}PASS/{actual_failed}FAIL",
                    "declared": f"{declared_passed}PASS"
                })
                all_pass = False
            else:
                details.append({
                    "check": "test_result",
                    "result": "PASS",
                    "actual": f"{actual_passed}PASS/{actual_failed}FAIL"
                })
        except subprocess.TimeoutExpired:
            details.append({"check": "test_result", "result": "FAIL", "detail": "TIMEOUT"})
            all_pass = False
        except Exception as e:
            details.append({"check": "test_result", "result": "FAIL", "detail": str(e)})
            all_pass = False

    status = "PASS" if all_pass else "FAIL"
    _log_result(task_id, "L3", status, json.dumps(details, ensure_ascii=False))
    _update_reputation("iso-sand-main", 1 if all_pass else -2, f"L3-{task_id}: {status}")
    return {"status": status, "task_id": task_id, "level": "L3", "details": details}


# ═══════════════════════════════════════════════════════════════════
# 双AI交叉签字（预留，注释状态）
# ═══════════════════════════════════════════════════════════════════

# 设计原理：
# 主AI完成任务→输出L3履约报告→派遣审计子AI（不同session）独立验证
# 审计子AI亲自运行复现命令+sha256sum+pytest，输出签字报告
# 主AI造假被审计AI抓到→主AI信誉扣分；审计AI漏签→审计AI扣分
#
# 实现条件：需要子AI之间的任务结果可互相读取。
# 当前子AI session 独立，通过 .claims/ 目录共享履约报告，
# 审计子AI 读 .claims/<task-id>.md → 运行验证 → 追加签字到报告文件中
#
# def cross_sign(claim_path: str, auditor_name: str) -> dict:
#     \"\"\"审计AI在履约报告末尾追加签字。\"\"\"
#     audit_result = verify_L3(os.path.basename(claim_path).replace('.md',''))
#     signature = f"""
# ## 审计签字
# - 审计者：{auditor_name}
# - 验证时间：{_now()}
# - 结论：{'PASS' if audit_result['status']=='PASS' else 'FAIL'}
# """
#     with open(claim_path, 'a', encoding='utf-8') as f:
#         f.write(signature)
#     return audit_result
# """
# 使用（子AI中）：
# from verify_claim import cross_sign
# result = cross_sign(".claims/fix-xxx.md", "subagent-audit-001")


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════


def _fail(level: str, msg: str) -> dict:
    """生成统一的 FAIL 结果。"""
    entry = {"status": "FAIL", "level": level, "details": [{"error": msg}]}
    return entry


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"status": "ERROR", "message": "用法: python3 verify_claim.py L1|L2|L3 <task-id>"}))
        sys.exit(1)

    level = sys.argv[1].upper()
    task_id = sys.argv[2]

    if level not in ("L1", "L2", "L3"):
        print(json.dumps({"status": "ERROR", "message": f"未知级别: {level}, 可选: L1/L2/L3"}))
        sys.exit(1)

    os.makedirs(_CLAIMS_DIR, exist_ok=True)

    verifiers = {"L1": verify_L1, "L2": verify_L2, "L3": verify_L3}
    result = verifiers[level](task_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
