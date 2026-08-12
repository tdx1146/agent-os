#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_ci_verify.py — ci_verify 快速自测套件

对真实项目目录运行验证，不修改项目文件。
"""

import os
import re
import sys

# 将 src 目录加入路径以便 import ci_verify
SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC_DIR))

import ci_verify


def quick_test() -> None:
    """自测：创建一个测试环境，验证 ci_verify 工作正常"""
    print("=" * 60)
    print("\U0001f9ea ci_verify.py 快速自测")
    print("=" * 60)
    print(f"  项目根目录: {ci_verify.PROJECT_ROOT}")
    print(f"  src 目录:   {ci_verify.SRC_DIR}")
    print(f"  docs 目录:  {ci_verify.DOCS_DIR}")
    print()

    # ── 测试 1：verify_all 可调用 ──────────────────────────────────
    print("--- 测试 1: verify_all 可调用 ---")
    result = ci_verify.verify_all()
    assert isinstance(result, dict), "verify_all 应返回 dict"
    assert "passed" in result, "结果应包含 passed"
    assert "results" in result, "结果应包含 results"
    assert "summary" in result, "结果应包含 summary"
    assert isinstance(result["results"], list), "results 应为 list"
    assert len(result["results"]) >= 7, (
        f"应有至少 7 项验证结果（实际 {len(result['results'])}）"
    )
    print(f"  \u2705 verify_all 调用成功，共 {len(result['results'])} 项验证")
    print(f"  结果摘要: {result['summary']}")
    print()

    # ── 测试 2：验证每项结果格式 ──────────────────────────────────
    print("--- 测试 2: 验证结果格式 ---")
    for i, r in enumerate(result["results"]):
        assert "name" in r, f"结果 {i} 缺少 name"
        assert "passed" in r, f"结果 {i} 缺少 passed"
        assert "detail" in r, f"结果 {i} 缺少 detail"
        icon = "\u2705" if r["passed"] else "\u274c"
        print(f"  [{i+1}] {r['name']}: {icon} \u2014 {r['detail'][:80]}")
    print()

    # ── 测试 3：验证项命名正确 ────────────────────────────────────
    print("--- 测试 3: 验证项命名 - 共 7 项 ---")
    expected_names = [
        "组件完整性",
        "接口签名交叉验证",
        "版本号一致性",
        "文件清单验证",
        "不存在的组件引用检查",
        "git 状态检查",
        "操作日志记录",
    ]
    for i, (actual, expected) in enumerate(zip(result["results"], expected_names)):
        assert actual["name"] == expected, (
            f"结果 {i}: 期望 '{expected}', 实际 '{actual['name']}'"
        )
    print("  \u2705 全部 7 项命名正确")
    print()

    # ── 测试 4：自包含性检查 ──────────────────────────────────────
    print("--- 测试 4: 自包含性检查 ---")
    with open(os.path.join(SRC_DIR, "ci_verify.py"), "r", encoding="utf-8") as f:
        content_text = f.read()
    lines = content_text.split("\n")
    violations = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if re.search(r'\(\s*"', stripped) or re.search(r"\(\s*'", stripped):
            continue
        m = re.match(r"^import\s+src\.(\w+)", stripped)
        if m and m.group(1) != "ci_verify":
            violations.append(f"  第 {i+1} 行: {stripped}")
        m = re.match(r"^from\s+src\.(\w+)\s+import", stripped)
        if m and m.group(1) != "ci_verify":
            violations.append(f"  第 {i+1} 行: {stripped}")
    if not violations:
        print("  \u2705 ci_verify.py 未依赖 src/ 其他模块")
    else:
        print("\n".join(violations))
    print()

    # ── 测试 5：动态导出检测 ──────────────────────────────────────
    print("--- 测试 5: 动态导出检测 ---")
    expected = ci_verify._get_expected_exports()
    for mod_name, funcs in sorted(expected.items()):
        print(f"  \u00b7 {mod_name}: {', '.join(funcs)}")
    assert "iso_logger" in expected
    assert "facts_manager" in expected
    assert "essence_distiller" in expected
    for funcs in expected.values():
        for f in funcs:
            assert f != "quick_test", "动态导出不应包含 quick_test"
    print("  \u2705 动态导出检测正常（不含 quick_test）")
    print()

    # ── 测试 6：操作日志记录作为第 7 项存在 ──────────────────────
    print("--- 测试 6: 验证7 操作日志记录 ---")
    seventh = result["results"][6]
    assert seventh["name"] == "操作日志记录"
    icon = "\u2705" if seventh["passed"] else "\u274c"
    print(f"  {icon} 操作日志记录: {seventh['detail'][:80]}")
    print()

    # ── 测试 7：测试结果总览 ──────────────────────────────────────
    print("--- 测试 7: 测试结果总览 ---")
    passed_count = sum(1 for r in result["results"] if r["passed"])
    failed_count = len(result["results"]) - passed_count
    print(f"  总验证项: {len(result['results'])}")
    print(f"  通过: {passed_count}  \u2705")
    fail_icon = "\u274c" if failed_count else "\u2705"
    print(f"  失败: {failed_count}  {fail_icon}")
    print(f"  摘要: {result['summary']}")
    print()

    print("=" * 60)
    print("\u2705 ci_verify.py 快速自测完成")
    print("=" * 60)

    if not result["passed"]:
        print("\n\u26a0\ufe0f  注意: 以下验证项未通过，可能需要修复项目文件:")
        for r in result["results"]:
            if not r["passed"]:
                print(f"  \u274c {r['name']}")
                for line in r["detail"].split("\n")[:5]:
                    print(f"     {line}")


if __name__ == "__main__":
    quick_test()
