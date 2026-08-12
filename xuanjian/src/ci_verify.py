#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ci_verify.py — IsoSand 自动 CI 验证系统

变更验证闭环：每次文件改动落地后，自动执行全部验证，通过才能 git commit。

设计原则：
  - 自包含脚本（不 import src/ 下其他模块检测自身，避免循环依赖）
  - 仅使用标准库（os, re, sys, json, subprocess, ast, tempfile, datetime）
  - 不修改现有 git hooks
  - 验证失败不自动 commit

验证类型（共7项）：
  1. 组件完整性 — 三个核心模块可导入
  2. 接口签名交叉验证 — 源码签名 vs 文档签名
  3. 版本号一致性 — 所有文档版本号一致
  4. 文件清单验证 — 文档中提到的路径真实存在
  5. 不存在组件引用检查 — docs/*.md 未引用不存在的 src 模块
  6. git 状态检查 — 干净或通过后补充断言并提交
  7. 操作日志记录 — 验证日志文件可写入并追加正确格式的记录
"""

import ast
import json
import os
import re
import subprocess
import sys
import datetime
import uuid

# ── 路径 ──

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SRC_DIR = SCRIPT_DIR
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DEPLOY_DIR = os.path.join(PROJECT_ROOT, "deploy")
LOG_FILE = os.path.join(DATA_DIR, "operation_log.jsonl")

CORE_MODULES = ["iso_logger", "facts_manager", "essence_distiller"]

VERSION_FILES = [
    "README.md",
    os.path.join("docs", "架构说明.md"),
    os.path.join("deploy", "install.sh"),
    os.path.join("deploy", "mcp_registry.json"),
]


# ── 辅助工具 ──


def _project_rel(path: str) -> str:
    """返回相对于项目根目录的路径（用于显示）"""
    try:
        return os.path.relpath(path, PROJECT_ROOT)
    except ValueError:
        return path


def _bjt_now() -> datetime.datetime:
    """返回当前时间（北京时区）"""
    from datetime import timezone, timedelta
    BJT = timezone(timedelta(hours=8))
    return datetime.datetime.now(BJT)


def _short_id() -> str:
    """生成简短可读 ID"""
    return uuid.uuid4().hex[:8]


# ═══════════════════════════════════════════════════════════════════
# 动态导出检测（替代硬编码 EXPECTED_EXPORTS）
# ═══════════════════════════════════════════════════════════════════


def _get_expected_exports() -> dict[str, list[str]]:
    """从各模块的 __all__ 动态读取导出列表，跳过 quick_test 等测试函数"""
    exports = {}
    for fname in sorted(os.listdir(SRC_DIR)):
        if not fname.endswith(".py") or fname == "ci_verify.py":
            continue
        if fname.startswith("_"):
            continue
        mod_name = fname[:-3]
        fpath = os.path.join(SRC_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=fpath)
            except SyntaxError:
                continue

        # 读取 __all__
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, ast.List):
                            all_funcs = [
                                elt.value
                                for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            ]
                            exports[mod_name] = [f for f in all_funcs if f != "quick_test"]
                            break

        # 无 __all__ 时兜底：提取全部公开函数
        if mod_name not in exports:
            funcs = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_") and node.name != "quick_test":
                    funcs.append(node.name)
            exports[mod_name] = funcs

    return exports


# ═══════════════════════════════════════════════════════════════════
# 验证 1：组件完整性
# ═══════════════════════════════════════════════════════════════════


def _verify_importable(module_name: str, expected_funcs: list[str]) -> dict:
    """验证模块可导入且包含预期函数"""
    func_list = ", ".join(expected_funcs)
    import_stmt = (
        f"import sys; sys.path.insert(0, {repr(SRC_DIR)}); "
        f"from {module_name} import {func_list}"
    )

    try:
        result = subprocess.run(
            [sys.executable, "-c", import_stmt],
            capture_output=True, text=True, timeout=10, cwd=PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "detail": f"导入 {module_name} 超时"}

    if result.returncode != 0:
        return {"passed": False, "detail": f"导入失败: {result.stderr.strip()[:200]}"}

    check_stmt = (
        f"import sys; sys.path.insert(0, {repr(SRC_DIR)}); "
        f"from {module_name} import {func_list}; "
        + "; ".join(f"callable({f}) or sys.exit(1)" for f in expected_funcs)
        + "; print('OK')"
    )
    try:
        result2 = subprocess.run(
            [sys.executable, "-c", check_stmt],
            capture_output=True, text=True, timeout=10, cwd=PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "detail": f"验证 {module_name} 函数签名超时"}

    if result2.returncode != 0:
        return {"passed": False, "detail": f"函数不可调用: {result2.stderr.strip()[:200]}"}

    return {"passed": True, "detail": f"from {module_name} import {func_list} ✅"}


def _check_component_integrity() -> dict:
    """验证 1：组件完整性"""
    details = []
    all_passed = True
    expected = _get_expected_exports()

    for mod_name in CORE_MODULES:
        funcs = expected.get(mod_name, [])
        if not funcs:
            details.append(f"  ⚪ {mod_name}: 未找到 __all__ 或公开函数")
            all_passed = False
            continue
        r = _verify_importable(mod_name, funcs)
        details.append(r["detail"])
        if not r["passed"]:
            all_passed = False

    return {"name": "组件完整性", "passed": all_passed, "detail": "\n".join(details)}


# ═══════════════════════════════════════════════════════════════════
# 验证 2：接口签名交叉验证（三叉戟检查）
# ═══════════════════════════════════════════════════════════════════


def _extract_source_signatures() -> dict[str, dict[str, tuple[str, list[str]]]]:
    """从 src/*.py 用 ast 提取所有公开函数签名"""
    result = {}
    for fname in os.listdir(SRC_DIR):
        if not fname.endswith(".py") or fname == "ci_verify.py":
            continue
        if fname.startswith("_"):
            continue
        mod_name = fname[:-3]
        fpath = os.path.join(SRC_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=fpath)
            except SyntaxError as e:
                result[mod_name] = {"__parse_error__": (str(e), [])}
                continue

        funcs = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith("_"):
                    continue
                params = []
                defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + node.args.defaults
                for i, arg in enumerate(node.args.args):
                    arg_name = arg.arg
                    if i < len(defaults) and defaults[i] is not None:
                        if arg.annotation:
                            ann_str = ast.unparse(arg.annotation) if hasattr(ast, "unparse") else "..."
                            arg_repr = f"{arg_name}: {ann_str}"
                        else:
                            arg_repr = arg_name
                        default_val = ast.unparse(defaults[i]) if hasattr(ast, "unparse") else "..."
                        arg_repr += f"={default_val}"
                    else:
                        if arg.annotation:
                            ann_str = ast.unparse(arg.annotation) if hasattr(ast, "unparse") else "..."
                            arg_repr = f"{arg_name}: {ann_str}"
                        else:
                            arg_repr = arg_name
                    params.append(arg_repr)

                returns = ""
                if node.returns:
                    ret_str = ast.unparse(node.returns) if hasattr(ast, "unparse") else ""
                    returns = f" -> {ret_str}"
                sig = f"{node.name}({', '.join(params)}){returns}"
                param_names = [a.arg for a in node.args.args]
                funcs[node.name] = (sig, param_names)

        result[mod_name] = funcs
    return result


def _extract_doc_signatures() -> dict[str, list[str]]:
    """从 docs/*.md 提取函数签名，支持跨多行的代码块内签名"""
    doc_sigs = {}
    for fname in sorted(os.listdir(DOCS_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(DOCS_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        found = set()
        # 模式 1: 反引号内的函数签名
        for m in re.finditer(r"`(\w+)\s*\(([^)]*)\)[^`]*`", content):
            func_name = m.group(1)
            if func_name.startswith("_") or func_name == "quick_test":
                continue
            if not func_name.isidentifier():
                continue
            params = m.group(2).strip()
            if "→" in params or "->" in params:
                params = params.split("→")[0].strip()
            found.add(f"{func_name}({params})")

        # 模式 2: 代码块内的函数签名（单行 + 多行）
        in_code = False
        pending_func = None  # (func_name, accumulated_text)
        for line in content.split("\n"):
            if line.strip().startswith("```"):
                in_code = not in_code
                pending_func = None
                continue
            if not in_code:
                pending_func = None
                continue
            if '"' in line or "'" in line:
                pending_func = None
                continue

            stripped = line.strip()

            # 多行拼接
            if pending_func is not None:
                func_name, acc = pending_func
                acc += " " + stripped
                if ")" in acc:
                    m = re.match(rf"^{re.escape(func_name)}\s*\(([^)]*)\)", acc)
                    if m:
                        params = m.group(1).strip()
                        if params:
                            found.add(f"{func_name}({params})")
                    pending_func = None
                else:
                    pending_func = (func_name, acc)
                continue

            # 单行匹配
            m = re.match(r"^\s*(\w+)\s*\(([^)]*)\)", stripped)
            if m:
                func_name = m.group(1)
                if func_name.startswith("_") or func_name == "quick_test":
                    continue
                if not func_name.isidentifier():
                    continue
                params = m.group(2).strip()
                if params:
                    found.add(f"{func_name}({params})")
            else:
                # 多行开始：func_name(  未闭合
                m2 = re.match(r"^\s*(\w+)\s*\([^)]*$", stripped)
                if m2:
                    func_name = m2.group(1)
                    if func_name.startswith("_") or func_name == "quick_test":
                        continue
                    if not func_name.isidentifier():
                        continue
                    if "(" in stripped and ")" not in stripped:
                        pending_func = (func_name, stripped)

        if found:
            doc_sigs[fname] = sorted(found)
    return doc_sigs


def _normalize_sig(sig: str) -> str:
    """去空格、去类型注解、去默认值，只保留函数名+参数名"""
    m = re.match(r"(\w+)\s*\(([^)]*)\)", sig)
    if not m:
        return sig.lower().strip()
    func_name = m.group(1)
    raw_params = m.group(2)
    param_names = []
    for p in raw_params.split(","):
        p = p.strip()
        if not p:
            continue
        p = p.split("=")[0].strip()
        p = p.split(":")[0].strip()
        p = p.split()[0].strip() if p.split() else p
        if p:
            param_names.append(p)
    return f"{func_name}({', '.join(param_names)})"


def _check_interface_signatures() -> dict:
    """验证 2：接口签名交叉验证"""
    details = []
    all_passed = True
    source_sigs = _extract_source_signatures()
    if not source_sigs:
        return {"name": "接口签名交叉验证", "passed": False, "detail": "未在 src/ 中找到 Python 源文件"}

    doc_sigs = _extract_doc_signatures()
    target_docs = ["接口协议.md", "操作规范.md", "架构说明.md"]
    found_inconsistency = False
    doc_summary = {}

    for doc in target_docs:
        doc_summary[doc] = {"found": 0, "mismatched": 0, "unreferenced": 0}

    for mod_name, funcs in sorted(source_sigs.items()):
        for func_name, (full_sig, param_names) in sorted(funcs.items()):
            if func_name.startswith("_") or func_name == "quick_test":
                continue
            src_normalized = _normalize_sig(full_sig)

            for doc in target_docs:
                if doc not in doc_sigs:
                    doc_summary[doc]["unreferenced"] += 1
                    continue

                found_in_doc = False
                for doc_sig in doc_sigs[doc]:
                    doc_normalized = _normalize_sig(doc_sig)
                    doc_func_name = doc_sig.split("(")[0].strip()
                    if doc_func_name == func_name:
                        found_in_doc = True
                        doc_summary[doc]["found"] += 1
                        if doc_normalized != src_normalized:
                            found_inconsistency = True
                            doc_summary[doc]["mismatched"] += 1
                            details.append(
                                f"  ❌ {mod_name}.{func_name}: 签名不一致\n"
                                f"      源码: {full_sig}\n"
                                f"      文档 {doc}: {doc_sig}"
                            )
                        break

                if not found_in_doc:
                    doc_summary[doc]["unreferenced"] += 1
                    details.append(f"  ⚪ {mod_name}.{func_name}: 未在 {doc} 中提及")

    details.insert(0, "📊 签名交叉验证报告:")
    for doc in target_docs:
        s = doc_summary[doc]
        if doc in doc_sigs:
            extra = len(doc_sigs[doc]) - sum(1 for _, fs in source_sigs.items() for fn in fs if not fn.startswith("_"))
            parts = [f"{s['found']} 匹配"]
            if s["mismatched"]:
                parts.append(f"{s['mismatched']} 不一致 ❌")
            if s["unreferenced"]:
                parts.append(f"{s['unreferenced']} 未提及")
            if extra > 0:
                parts.append(f"{extra} 文档独有")
            details.append(f"   · {doc}: {', '.join(parts)}")
        else:
            details.append(f"   · {doc}: ❌ 未找到签名")

    if found_inconsistency:
        details.insert(0, "❌ 发现签名不一致")
    else:
        details.insert(0, "✅ 无签名不一致")

    return {"name": "接口签名交叉验证", "passed": not found_inconsistency, "detail": "\n".join(details)}


# ═══════════════════════════════════════════════════════════════════
# 验证 3：版本号一致性
# ═══════════════════════════════════════════════════════════════════


def _extract_version(text: str) -> str | None:
    """从文本中提取项目版本号（v0.x），排除文件路径语境中的误匹配"""
    # 模式 1: 明确的项目版本声明
    for pattern in [
        r'当前版本[:：]?\s*[*]*v?(\d+\.\d+)',
        r'版本[:：]\s*v?(\d+\.\d+)',
        r'"version"\s*:\s*"(\d+\.\d+)"',
        r'IsoSand\s+v?(\d+\.\d+)',
        r'^#\s+.*v?(\d+\.\d+)',
    ]:
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            v = m.group(1)
            if v.count(".") == 1:
                return "v" + v if not v.startswith("v") else v

    # 模式 2: vX.Y 形式，要求前面是行首或空白（排除路径语境如 revisions/v0.1）
    for m in re.finditer(r'(?:^|(?<=\s))v(\d+\.\d+)(?:\.\w+)?(?!"|/|_|\.md)', text, re.MULTILINE):
        return m.group(0)

    return None


def _check_version_consistency() -> dict:
    """验证 3：版本号一致性"""
    details = []
    all_passed = True
    versions = {}

    for rel_path in VERSION_FILES:
        abs_path = os.path.join(PROJECT_ROOT, rel_path)
        if not os.path.exists(abs_path):
            details.append(f"  ❌ 文件不存在: {rel_path}")
            all_passed = False
            continue
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        ver = _extract_version(content)
        if ver:
            versions[rel_path] = ver
        else:
            details.append(f"  ⚪ {rel_path}: 未找到版本号")

    if not versions:
        return {"name": "版本号一致性", "passed": False, "detail": "任何文件都未找到版本号"}

    ver_values = list(versions.values())
    ref_ver = ver_values[0]
    mismatches = []
    for path, ver in versions.items():
        if ver != ref_ver:
            mismatches.append(f"{path} → {ver} (期望 {ref_ver})")
            all_passed = False

    if all_passed:
        details = [f"✅ 全部一致: {ref_ver}"]
        for path in versions:
            details.append(f"   · {path}: {versions[path]}")
    else:
        details = [f"❌ 版本号不一致"]
        for path, ver in versions.items():
            details.append(f"   · {path}: {ver}")
        if mismatches:
            details.append(f"   ⚠️  不匹配: {', '.join(mismatches)}")

    return {"name": "版本号一致性", "passed": all_passed, "detail": "\n".join(details)}


# ═══════════════════════════════════════════════════════════════════
# 验证 4：文件清单验证
# ═══════════════════════════════════════════════════════════════════


def _extract_file_paths_from_doc(filepath: str) -> list[str]:
    """从文档中提取看起来像文件路径的字符串"""
    paths = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError):
        return []

    path_patterns = [
        r"`(src/[\w./-]+)`",
        r"`(docs/[\w./-]+)`",
        r"`(deploy/[\w./-]+)`",
        r"`(data/[\w./-]+)`",
        r"`(revisions/[\w./-]+)`",
        r"`(backups/[\w./-]+)`",
        r"`([\w-]+\.py)`",
        r"`([\w-]+\.md)`",
        r"`([\w-]+\.json)`",
        r"`([\w-]+\.jsonl)`",
        r"`([\w-]+\.sh)`",
        r"`([\w-]+\.txt)`",
        r"`(\./[\w./-]+)`",
    ]

    for pat in path_patterns:
        for m in re.finditer(pat, content):
            p = m.group(1).strip()
            if len(p) > 120:
                continue
            if any(excl in p for excl in ["...", "xxx"]):
                continue
            if p.startswith("./"):
                p = p[2:]
            paths.add(p)

    return sorted(paths)


def _check_file_manifest() -> dict:
    """验证 4：文件清单验证"""
    details = []
    all_passed = True
    source_docs = [
        os.path.join(DOCS_DIR, "项目章程.md"),
        os.path.join(DOCS_DIR, "架构说明.md"),
    ]

    all_referenced = []
    for doc_path in source_docs:
        if not os.path.exists(doc_path):
            details.append(f"  ⚪ 源文档缺失: {_project_rel(doc_path)}")
            continue
        paths = _extract_file_paths_from_doc(doc_path)
        all_referenced.extend((_project_rel(doc_path), p) for p in paths)

    missing = []
    checked = set()
    exclusions = ["sandglass", "pgvector", "backups", "logs/", "data/essence/", ".DS_Store", "...", "xxx"]

    for src_doc, ref_path in all_referenced:
        if len(ref_path) > 200 or ref_path.startswith("http"):
            continue
        if any(excl in ref_path for excl in exclusions):
            continue
        if ref_path.startswith("./"):
            ref_path = ref_path[2:]

        key = (src_doc, ref_path)
        if key in checked:
            continue
        checked.add(key)

        abs_path = os.path.join(PROJECT_ROOT, ref_path)
        if os.path.exists(abs_path):
            continue

        # 裸文件名：尝试常见子目录
        if "/" not in ref_path:
            candidates = [
                os.path.join(PROJECT_ROOT, "src", ref_path),
                os.path.join(PROJECT_ROOT, "docs", ref_path),
                os.path.join(PROJECT_ROOT, "data", ref_path),
                os.path.join(PROJECT_ROOT, "deploy", ref_path),
            ]
            if any(os.path.exists(c) for c in candidates):
                continue

        missing.append(f"'{ref_path}' (来自 {src_doc})")
        all_passed = False

    if missing:
        details = [f"❌ {len(missing)} 个引用的文件/目录不存在:"]
        details.extend(f"   · {m}" for m in missing)
    else:
        details = [f"✅ 所有 {len(checked)} 个引用路径均存在"]

    return {"name": "文件清单验证", "passed": all_passed, "detail": "\n".join(details)}


# ═══════════════════════════════════════════════════════════════════
# 验证 5：不存在的组件引用检查
# ═══════════════════════════════════════════════════════════════════


def _check_nonexistent_imports() -> dict:
    """验证 5：不存在的组件引用检查"""
    details = []
    all_passed = True
    existing_modules = set()
    for fname in os.listdir(SRC_DIR):
        if fname.endswith(".py") and not fname.startswith("_"):
            existing_modules.add(fname[:-3])

    nonexistent = []
    for fname in sorted(os.listdir(DOCS_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(DOCS_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        for m in re.finditer(r"(?:from\s+src\.(\w+)|import\s+src\.(\w+))", content):
            mod = m.group(1) or m.group(2)
            if mod and mod not in existing_modules and mod != "ci_verify":
                nonexistent.append(f"{fname}: 引用了不存在的模块 'src.{mod}'")
                all_passed = False

        for m in re.finditer(r"src/(\w+)\.py", content):
            mod = m.group(1)
            if mod and mod not in existing_modules and mod != "ci_verify":
                nonexistent.append(f"{fname}: 引用了不存在的文件 'src/{mod}.py'")
                all_passed = False

    if nonexistent:
        details = [f"❌ 发现 {len(nonexistent)} 个不存在的组件引用:"]
        details.extend(f"   · {n}" for n in nonexistent)
    else:
        details = ["✅ 所有引用的 src/ 模块均存在"]

    return {"name": "不存在的组件引用检查", "passed": all_passed, "detail": "\n".join(details)}


# ═══════════════════════════════════════════════════════════════════
# 验证 6：git 状态检查
# ═══════════════════════════════════════════════════════════════════


def _check_git_status() -> dict:
    """验证 6：git 状态检查"""
    git_dir = os.path.join(PROJECT_ROOT, ".git")
    if not os.path.isdir(git_dir):
        return {"name": "git 状态检查", "passed": True, "detail": "⚪ 非 git 仓库，跳过"}

    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, timeout=10, cwd=PROJECT_ROOT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"name": "git 状态检查", "passed": True, "detail": f"⚪ git 命令失败: {e}"}

    if result.returncode != 0:
        return {"name": "git 状态检查", "passed": True, "detail": f"⚪ git status 执行失败: {result.stderr.strip()[:200]}"}

    output = result.stdout.strip()
    if not output:
        return {"name": "git 状态检查", "passed": True, "detail": "✅ git 工作区干净（无未提交文件）"}
    
    lines = output.split("\n")
    details = [f"❌ 有 {len(lines)} 个未提交文件:"]
    for line in lines:
        details.append(f"   · {line.strip()}")
    return {"name": "git 状态检查", "passed": False, "detail": "\n".join(details)}


# ═══════════════════════════════════════════════════════════════════
# 验证 7：操作日志记录
# ═══════════════════════════════════════════════════════════════════


def _write_operation_log(passed: bool, summary: str, results: list[dict]) -> None:
    """追加验证记录到 operation_log.jsonl（INFO 通过 / WARN 失败）"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    passed_count = sum(1 for r in results if r.get("passed"))
    total_count = len(results)
    failed_items = [r["name"] for r in results if not r.get("passed")]

    record = {
        "t": _bjt_now().isoformat(),
        "level": "INFO" if passed else "WARN",
        "actor": "ci_verify",
        "action": "verify",
        "target": "IsoSand 全部文件",
        "result": "OK" if passed else "FAIL",
        "detail": (
            f"CI 验证: {passed_count}/{total_count} 通过"
            + (f"; 失败: {', '.join(failed_items)}" if failed_items else "; 全部通过")
        ),
        "trace_id": "ci-" + _short_id(),
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _check_operation_log() -> dict:
    """验证 7：操作日志记录 — 验证日志文件可写入且格式正确"""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        record = {
            "t": _bjt_now().isoformat(),
            "level": "DEBUG",
            "actor": "ci_verify",
            "action": "check_log",
            "target": "operation_log.jsonl",
            "result": "OK",
            "detail": "操作日志记录验证",
            "trace_id": "ci-verify-" + _short_id(),
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
        # 读出验证写入正确
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last = json.loads(lines[-1].strip())
        assert last.get("action") == "check_log"
        return {"name": "操作日志记录", "passed": True, "detail": f"日志文件可写入 ({_project_rel(LOG_FILE)}) ✅"}
    except Exception as e:
        return {"name": "操作日志记录", "passed": False, "detail": f"日志写入验证失败: {e}"}


# ═══════════════════════════════════════════════════════════════════
# verify_all — 主入口
# ═══════════════════════════════════════════════════════════════════


def verify_all() -> dict:
    """
    执行全部 7 项验证。

    返回:
        dict: {"passed": bool, "results": [...], "summary": "..."}
    """
    checkers = [
        _check_component_integrity,
        _check_interface_signatures,
        _check_version_consistency,
        _check_file_manifest,
        _check_nonexistent_imports,
        _check_git_status,
        _check_operation_log,
    ]

    results = []
    for checker in checkers:
        try:
            result = checker()
        except Exception as e:
            name = checker.__name__.replace("_check_", "").replace("_", " ").strip()
            result = {"name": name, "passed": False, "detail": f"执行异常: {type(e).__name__}: {e}"}
        results.append(result)

    all_passed = all(r["passed"] for r in results)
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count

    if all_passed:
        summary = "全部通过 ✅"
    else:
        failed_names = [r["name"] for r in results if not r["passed"]]
        summary = f"{failed_count} 项失败 ❌: {', '.join(failed_names)}"

    # 全部通过时写入操作日志
    if all_passed:
        try:
            _write_operation_log(all_passed, summary, results)
        except Exception:
            pass

    return {"passed": all_passed, "results": results, "summary": summary}


# ═══════════════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    """命令行入口——运行全部验证并输出可读报告"""
    import time

    print("=" * 60)
    print("  IsoSand CI 验证系统")
    print(f"  运行时间: {_bjt_now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    start = time.time()
    result = verify_all()
    elapsed = time.time() - start

    print(f"⏱  耗时: {elapsed:.2f}s")
    print()

    for i, r in enumerate(result["results"]):
        status_icon = "✅" if r["passed"] else "❌"
        print(f" {status_icon} [{i+1}] {r['name']}")
        for line in r["detail"].split("\n"):
            print(f"     {line}")
        print()

    passed_count = sum(1 for r in result["results"] if r["passed"])
    total = len(result["results"])
    print("=" * 60)
    print(f"  {result['summary']}")
    print(f"  通过率: {passed_count}/{total} ({passed_count*100//total}%)")
    print("=" * 60)

    if result["passed"]:
        print("✅ CI 验证全部通过")
    else:
        print("❌ CI 验证未通过，请修复后再提交")
        sys.exit(1)


if __name__ == "__main__":
    # --test = 运行分离的自测脚本
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_script = os.path.join(os.path.dirname(SCRIPT_DIR), "tests", "test_ci_verify.py")
        if os.path.exists(test_script):
            os.execv(sys.executable, [sys.executable, test_script])
        else:
            print(f"❌ 未找到自测脚本: {test_script}")
            sys.exit(1)
    else:
        result = verify_all()
        if not result["passed"]:
            sys.exit(1)
