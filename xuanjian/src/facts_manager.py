#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
facts_manager.py — IsoSand 断言图管理器

"关系先于实体"：断言图是 IsoSand 的关系存储层核心组件。
不预设本体，从关系密度中涌现实体。

断言图文件：data/facts.dict.md
格式：
    # IsoSand Facts Dictionary
    > 断言图 — "关系先于实体"
    ...
    ## ├ <namespace>:<topic>
    - [YYYY-MM-DD] <断言内容>

"""

from __future__ import annotations

import os
import re
import datetime
from typing import Optional

__all__ = [
    "append_fact",
    "get_facts",
    "get_categories",
    "count",
    "quick_test",
]

# ── 路径 ──────────────────────────────────────────────────────────

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DEFAULT_FACTS_PATH = os.path.join(_PROJECT_ROOT, "data", "facts.dict.md")

_HEADER = """# IsoSand Facts Dictionary
> 断言图 — "关系先于实体"
> 每行一个原子断言，git 可追溯

"""

_FACT_RE = re.compile(r"^-\s*\[(\d{4}-\d{2}-\d{2})\]\s+(.+)$")
_HEADING_RE = re.compile(r"^##\s+├\s+(.+)$")


# ── 内部工具 ──────────────────────────────────────────────────────

def _ensure_file(path: str) -> None:
    """如果断言图文件不存在，创建带头部的新文件。"""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(_HEADER)


def _read_lines(path: str) -> list[str]:
    """读取文件全部行，确保文件存在。"""
    _ensure_file(path)
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()


def _write_lines(path: str, lines: list[str]) -> None:
    """原子写入——写临时文件 + rename，避免半成品被提交。"""
    import uuid
    tmp = path + ".tmp." + uuid.uuid4().hex[:8]
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(lines)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


# ── 核心 API ──────────────────────────────────────────────────────


def append_fact(category: str, statement: str, date: str = None,
                facts_path: str = None) -> bool:
    """
    追加一条断言到指定的 category 下。

    参数
    ----
    category : str
        类别标识，例如 "project:iso_sand" 或 "component:iso_logger"。
        支持自动补全：若传入的 category 不包含冒号，将匹配已有类别后缀。
    statement : str
        断言内容。
    date : str, optional
        日期字符串 "YYYY-MM-DD"。默认当天。
    facts_path : str, optional
        断言图文件路径。默认 data/facts.dict.md。

    返回
    ----
    bool
        追加成功返回 True。

    示例
    ----
    >>> append_fact("project:iso_sand", "IsoSand 项目初始化完成", "2026-07-06")
    """
    path = facts_path or _DEFAULT_FACTS_PATH
    date = date or datetime.date.today().isoformat()

    # ── 自动补全 category ──
    if ":" not in category:
        cat_map = {c.split(":", 1)[-1]: c for c in get_categories(path)}
        if category in cat_map:
            category = cat_map[category]
        # 如果也没匹配到，就原样使用（当作新类别）

    lines = _read_lines(path)

    target_heading = f"## ├ {category}"
    fact_line = f"- [{date}] {statement}\n"

    # 查找目标 section 的位置
    heading_idx = None
    next_heading_idx = None
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped == target_heading:
            heading_idx = i
        elif heading_idx is not None and _HEADING_RE.match(stripped):
            next_heading_idx = i
            break

    if heading_idx is None:
        # section 不存在 → 在末尾追加
        # 确保末尾有空行分隔
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append(f"{target_heading}\n")
        lines.append(fact_line)
    else:
        # section 存在 → 追加到 section 末尾（下一个 heading 之前）
        insert_at = next_heading_idx if next_heading_idx is not None else len(lines)
        # 从 heading_idx+1 往后找，跳过可能的空行和注释，找到最后一个 "fact" 行位置
        last_fact = heading_idx
        for j in range(heading_idx + 1, insert_at):
            if _FACT_RE.match(lines[j].strip()):
                last_fact = j
        insert_pos = last_fact + 1
        lines.insert(insert_pos, fact_line)

    _write_lines(path, lines)
    # 自动 git commit — 每次写入断言后自动版本记录
    _git_auto_commit(path)
    return True


def _git_auto_commit(facts_path: str) -> None:
    """
    如果 facts.dict.md 在 git 仓库中，自动 add + commit 变更。
    取最新断言行内容做 commit message。静默失败。
    """
    try:
        import subprocess, os
        facts_path = os.path.abspath(facts_path)
        repo_root = os.path.dirname(os.path.dirname(facts_path))
        git_dir = os.path.join(repo_root, ".git")
        if not os.path.isdir(git_dir):
            return
        rel = os.path.relpath(facts_path, repo_root)
        subprocess.run(["git", "-C", repo_root, "add", rel],
                       capture_output=True, timeout=5)
        msg = ""
        with open(facts_path, encoding="utf-8") as f:
            for line in f:
                m = _FACT_RE.match(line.strip())
                if m:
                    msg = m.group(1)
        short = msg[:40] if msg else "auto commit"
        subprocess.run(["git", "-C", repo_root, "commit",
                        "-m", f"facts: {short}"],
                       capture_output=True, timeout=5)
    except Exception:
        pass  # git 失败不阻塞写入


def get_facts(category: str = None, keyword: str = None,
              since: str = None, limit: int = 100,
              facts_path: str = None) -> list[dict]:
    """
    读取断言，支持按类别/关键词/日期筛选。

    参数
    ----
    category : str, optional
        筛选类别（精确匹配 "namespace:topic"）。
    keyword : str, optional
        关键词（在断言内容中模糊匹配）。
    since : str, optional
        起始日期 "YYYY-MM-DD"（含该日）。
    limit : int
        最大返回条数，默认 100。
    facts_path : str, optional
        断言图文件路径。

    返回
    ----
    list[dict]
        每项含 {date, statement, category}。
    """
    path = facts_path or _DEFAULT_FACTS_PATH
    lines = _read_lines(path)
    results: list[dict] = []
    current_category: Optional[str] = None

    for line in lines:
        stripped = line.strip()
        # 检测 category heading
        m = _HEADING_RE.match(stripped)
        if m:
            current_category = m.group(1).strip()
            continue

        # 检测事实行
        m = _FACT_RE.match(stripped)
        if not m:
            continue
        fact_date = m.group(1)
        fact_statement = m.group(2).strip()

        # 筛选
        if category and current_category != category:
            continue
        if keyword and keyword.lower() not in fact_statement.lower():
            continue
        if since and fact_date < since:
            continue

        results.append({
            "date": fact_date,
            "statement": fact_statement,
            "category": current_category or "",
        })

        if len(results) >= limit:
            break

    return results


def get_categories(facts_path: str = None) -> list[str]:
    """
    返回所有已有类别列表。

    参数
    ----
    facts_path : str, optional
        断言图文件路径。

    返回
    ----
    list[str]
        类别名称列表，例如 ["project:iso_sand", "component:iso_logger"]。
    """
    path = facts_path or _DEFAULT_FACTS_PATH
    lines = _read_lines(path)
    categories: list[str] = []
    for line in lines:
        m = _HEADING_RE.match(line.strip())
        if m:
            categories.append(m.group(1).strip())
    return categories


def count(facts_path: str = None) -> dict[str, int]:
    """
    返回每个类别的断言数统计。

    参数
    ----
    facts_path : str, optional
        断言图文件路径。

    返回
    ----
    dict
        {category: count}。
    """
    path = facts_path or _DEFAULT_FACTS_PATH
    lines = _read_lines(path)
    counts: dict[str, int] = {}
    current_category: Optional[str] = None

    for line in lines:
        stripped = line.strip()
        m = _HEADING_RE.match(stripped)
        if m:
            current_category = m.group(1).strip()
            if current_category not in counts:
                counts[current_category] = 0
            continue
        if _FACT_RE.match(stripped) and current_category:
            counts[current_category] = counts.get(current_category, 0) + 1

    return counts


# ── 快速测试 ──────────────────────────────────────────────────────

def quick_test(facts_path: str = None) -> None:
    """
    快速自测：创建一条测试断言 → 读取验证 → 清理。

    用于验证断言图文件可读写、格式正确。
    """
    path = facts_path or _DEFAULT_FACTS_PATH
    print(f"📂 断言图路径: {path}")

    # 1. 追加测试断言
    test_cat = "test:quick_check"
    test_stmt = f"quick_test 自检通过 ({datetime.datetime.now():%Y-%m-%d %H:%M})"
    test_date = datetime.date.today().isoformat()
    print(f"➕ 追加测试断言: [{test_cat}] {test_stmt}")
    append_fact(test_cat, test_stmt, test_date, path)

    # 2. 读取验证
    facts = get_facts(category=test_cat, facts_path=path)
    print(f"🔍 读取到 {len(facts)} 条断言")
    for f in facts:
        print(f"   - [{f['date']}] {f['statement']}")
    assert len(facts) >= 1, "quick_test: 未读取到刚写入的断言"
    assert facts[-1]["statement"] == test_stmt, "quick_test: 断言内容不匹配"

    # 3. 清理：删除测试行
    lines = _read_lines(path)
    # 找出测试 section 的所有事实行
    in_test = False
    last_fact_idx = -1
    test_fact_indices: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _HEADING_RE.match(stripped) and f"├ {test_cat}" in stripped:
            in_test = True
            continue
        if in_test and _HEADING_RE.match(stripped):
            break
        if in_test and _FACT_RE.match(stripped):
            test_fact_indices.append(i)

    # 从后往前删除
    for idx in reversed(test_fact_indices):
        del lines[idx]

    # 如果 test section 没有事实行了，也删除 heading 和空行
    # 重新检查 heading 后面是否有事实
    heading_pos = None
    for i, line in enumerate(lines):
        if _HEADING_RE.match(line.strip()) and f"├ {test_cat}" in line:
            heading_pos = i
            break
    if heading_pos is not None:
        # 检查 heading 后面有没有非空行（除了空白行/注释）
        has_content = False
        for j in range(heading_pos + 1, len(lines)):
            s = lines[j].strip()
            if not s or s.startswith("#") or s.startswith(">"):
                continue
            if _FACT_RE.match(s):
                has_content = True
                break
            break  # 遇到其他行停止
        if not has_content:
            # 删除 heading 和后续空行直到下一个 heading 或文件尾
            del_pos = heading_pos
            # 删除 heading
            del lines[del_pos]
            # 删除后面连续的空行（但保留一个分隔）
            while del_pos < len(lines) and not lines[del_pos].strip():
                del lines[del_pos]
            # 再删除 heading 前多余的空行
            while del_pos > 1 and not lines[del_pos - 1].strip():
                del lines[del_pos - 1]
                del_pos -= 1

    _write_lines(path, lines)
    print(f"🧹 测试断言已清理")

    # 4. 最终验证
    remaining = get_facts(category=test_cat, facts_path=path)
    assert len(remaining) == 0, f"quick_test: 清理后仍有 {len(remaining)} 条断言"
    print("✅ quick_test 全部通过")
    print(f"📊 当前统计: {count(path)}")
    print()


# ── 自测入口 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from iso_logger import log
    import tempfile

    print("=" * 50)
    print("🧪 facts_manager.py 自测")
    print("=" * 50)

    # 使用临时文件测试，避免影响真实数据
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = os.path.join(tmpdir, "facts.dict.md")
        print(f"📁 临时测试文件: {tmp_path}")

        # ── 测试 1：新建文件 + 追加 ──
        print("\n--- 测试 1: 新建文件 + 追加断言 ---")
        assert append_fact("project:iso_sand", "项目初始化完成", "2026-07-06", tmp_path)
        cats = get_categories(tmp_path)
        assert cats == ["project:iso_sand"], f"类别不匹配: {cats}"
        facts = get_facts(category="project:iso_sand", facts_path=tmp_path)
        assert len(facts) == 1
        assert facts[0]["date"] == "2026-07-06"
        assert facts[0]["statement"] == "项目初始化完成"
        print("  ✅ 新建+追加通过")

        # ── 测试 2：追加到已有 category ──
        print("\n--- 测试 2: 追加到已有 category ---")
        append_fact("project:iso_sand", "上下文窗口升级", "2026-07-06", tmp_path)
        facts = get_facts(category="project:iso_sand", facts_path=tmp_path)
        assert len(facts) == 2
        print(f"  ✅ 追加通过，共 {len(facts)} 条")

        # ── 测试 3：自动补全 category ──
        print("\n--- 测试 3: 自动补全 category ---")
        append_fact("iso_sand", "自动补全测试", "2026-07-06", tmp_path)
        facts = get_facts(category="project:iso_sand", facts_path=tmp_path)
        assert len(facts) == 3
        print(f"  ✅ 自动补全通过")

        # ── 测试 4：新 category ──
        print("\n--- 测试 4: 新 category ---")
        append_fact("component:iso_logger", "日志模块实现完成", "2026-07-06", tmp_path)
        cats = get_categories(tmp_path)
        assert "component:iso_logger" in cats
        print(f"  ✅ 新 category 通过，类别: {cats}")

        # ── 测试 5：筛选 ──
        print("\n--- 测试 5: 筛选功能 ---")
        r = get_facts(keyword="日志", facts_path=tmp_path)
        assert len(r) == 1
        assert r[0]["category"] == "component:iso_logger"
        r = get_facts(since="2026-07-07", facts_path=tmp_path)
        assert len(r) == 0
        print("  ✅ 筛选通过")

        # ── 测试 6：count ──
        print("\n--- 测试 6: count ---")
        c = count(tmp_path)
        assert c.get("project:iso_sand") == 3
        assert c.get("component:iso_logger") == 1
        print(f"  ✅ count 通过: {c}")

        # ── 测试 7：quick_test ──
        print("\n--- 测试 7: quick_test ---")
        quick_test(tmp_path)

    # ── 主报告 ──
    print("=" * 50)

    # 记录测试到操作日志
    log("INFO", "quick_test", "test_facts_manager", "self_test", "OK", "断言图管理组件自测通过")
    print("✅ facts_manager.py 测试通过")
    print("=" * 50)
