#!/usr/bin/env python3
"""
reflection_check.py — dandan 9步反思质检器

根据 dandan 定义的反思方法论（9步循环），在输出最终答案前强制调用。
每次调用记录完整反思链，输出修订版答案。

方法论 9 步：
1. 不假设事情顺利，假设这问题已经犯过错
2. 搜索记忆，是否有类似错误/知识
3. 如果有，直接避坑；没有也继续
4. 假设问题已经解决失败，最容易出错的点在哪（建常见错误库）
5. 站在问题制造者角度：如果想让人犯错，会在哪埋坑
6. 站在对立面思考：其他方案？极简 vs 极通用 的选择框架（奥卡姆剃刀+长期极简理论）
7. 找出最佳方案实施
8. 失败继续循环
9. 成功→复盘→总结进知识库

用法:
    from reflection_check import reflect
    result = reflect(context, solution_draft)
    print(result["answer"])        # 修订版答案
    print(result["chain"])         # 反思链日志

"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─── 知识库路径 ─────────────────────────────────────────────────────────────

# 自动检测项目根目录（向上搜索轻如烟标识文件）
def _find_project_root() -> Path:
    """从脚本位置向上搜索，找到轻如烟项目根目录。"""
    cwd = Path.cwd()
    # 先检查常见位置
    candidates = [
        Path("/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟"),
        cwd,
    ]
    for p in candidates:
        if p.exists() and (p / "memory").is_dir():
            return p
    # fallback: 从当前目录向上找
    for p in [cwd] + list(cwd.parents):
        if (p / "memory").is_dir() and (p / "facts.dict.md").exists():
            return p
    return cwd


PROJECT_ROOT = _find_project_root()
FACTS_PATH = PROJECT_ROOT / "memory" / "facts.dict.md"
KNOWLEDGE_TREE_PATH = PROJECT_ROOT / "memory" / "knowledge-tree.md"
ERROR_DB_PATH = PROJECT_ROOT / "memory" / "common-errors.md"
REFLECTION_LOG_PATH = PROJECT_ROOT / "memory" / "reflection-log.md"


# ─── 核心反思函数 ──────────────────────────────────────────────────────────

def reflect(context: dict, solution_draft: str) -> dict:
    """
    反思质检器——在输出最终答案前强制调用。

    Args:
        context: 当前问题上下文，建议包含：
            - task: 任务描述（str）
            - existing_info: 已有信息/上下文（str）
            - memory_results: 记忆搜索结果（list[str]）
            - task_type: 任务类型（可选，用于精细分析）
        solution_draft: 我打算输出的原始答案

    Returns:
        dict {
            "answer": 修订后的答案（str），
            "chain": 反思链日志（list[dict]），每步一个记录，
                    包含 step: int, name: str, analysis: str
            "passed": bool, 是否通过反思质检
            "errors_found": list[str], 发现的潜在错误
            "alternatives": list[dict], 备选方案对比
        }
    """
    chain: List[Dict[str, Any]] = []

    def _log(step: int, name: str, analysis: str) -> None:
        """记录反思链的一步。"""
        entry = {
            "step": step,
            "name": name,
            "analysis": analysis,
            "timestamp": datetime.now().isoformat(),
        }
        chain.append(entry)

    errors_found: List[str] = []
    alternatives: List[Dict[str, str]] = []

    # ── Step 0: 初始化 ─────────────────────────────────────────────────
    task = context.get("task", "未指定任务")
    existing_info = context.get("existing_info", "")
    memory_results = context.get("memory_results", [])

    _log(0, "初始化", f"任务: {task[:200]}...")
    _log(0, "初始化", f"原始答案长度: {len(solution_draft)} 字符")

    # ── Step 1: 不假设事情顺利 ─────────────────────────────────────────
    _log(1, "不假设事情顺利", """
    默认假设：这个问题已经存在潜在错误。
    反问自己：
    - 我的答案里哪些部分最可能是错的？
    - 如果这个答案是错的，后果是什么？
    - 我有没有因为"差不多了"就跳过检查？
    没有安全假设——每个断言都要重新质疑。
    """)

    # ── Step 2: 搜索记忆，是否有类似错误/知识 ──────────────────────────
    _log(2, "搜索记忆与知识库", f"记忆搜索结果: {len(memory_results)} 条")

    # 读取知识库
    facts_content = _read_file_safe(FACTS_PATH)
    knowledge_content = _read_file_safe(KNOWLEDGE_TREE_PATH)
    errors_content = _read_file_safe(ERROR_DB_PATH)

    # 从知识库中提取与当前任务相关的断言
    relevant_knowledge = _search_knowledge(task, solution_draft, facts_content, knowledge_content)

    _log(2, "搜索记忆与知识库", f"读取 facts.dict.md ({len(facts_content)} 字符), "
         f"knowledge-tree.md ({len(knowledge_content)} 字符), "
         f"common-errors.md ({len(errors_content)} 字符)")

    for k in relevant_knowledge[:10]:
        _log(2, "搜索记忆与知识库", f"  → 相关断言: {k}")

    # ── Step 3: 如果有，直接避坑；没有也继续 ────────────────────────────
    known_issues = _detect_known_issues(solution_draft, relevant_knowledge, errors_content)
    if known_issues:
        for issue in known_issues:
            _log(3, "已知避坑检查", f"⚠️ 发现已知坑点: {issue}")
            errors_found.append(issue)
    else:
        _log(3, "已知避坑检查", "✅ 未发现已知坑点。但防微杜渐继续走完流程。")

    # ── Step 4: 假设失败，预测最容易出错的点 ────────────────────────────
    failure_analysis = _analyze_failure_points(solution_draft, task, existing_info, errors_content)
    for fp in failure_analysis:
        _log(4, "假设失败分析 · 错误点预测", f"🔴 潜在失败点: {fp}")
        errors_found.append(fp)

    # ── Step 5: 站在问题制造者角度——故意埋坑检测 ──────────────────────
    trap_analysis = _analyze_traps(solution_draft, task)
    for trap in trap_analysis:
        _log(5, "对立面分析 · 恶意埋坑检测", f"🪤 发现陷阱: {trap}")
        errors_found.append(trap)

    if not trap_analysis:
        _log(5, "对立面分析 · 恶意埋坑检测", "✅ 未发现明显陷阱。但仍警惕。")

    # ── Step 6: 备选方案对比 ────────────────────────────────────────────
    alternatives = _generate_alternatives(solution_draft, context)
    for alt in alternatives:
        _log(6, "对立面思考 · 方案对比",
             f"方案 [{alt['name']}]:\n"
             f"  描述: {alt['description'][:200]}\n"
             f"  优点: {alt['pros'][:200]}\n"
             f"  缺点: {alt['cons'][:200]}\n"
             f"  适用场景: {alt['when']}")

    # ── Step 7: 最佳方案判断 ────────────────────────────────────────────
    best_choice = _choose_best_approach(solution_draft, alternatives, errors_found, task)
    _log(7, "最佳方案选择", f"选择判断: {best_choice['reasoning'][:300]}")

    # ── 修订答案 ─────────────────────────────────────────────────────────
    revised_answer = _revise_answer(solution_draft, errors_found, alternatives, best_choice, context)

    if revised_answer != solution_draft:
        _log(7, "修订输出",
             f"原始答案已修订。\n  原始: {solution_draft[:200]}...\n"
             f"  修订: {revised_answer[:200]}...")
    else:
        _log(7, "修订输出", "答案未修改（已通过反思质检）。")

    # ── 质量分 ───────────────────────────────────────────────────────────
    quality = _assess_quality(errors_found, alternatives, revised_answer)
    _log(0, "质检评分", f"通过: {quality['passed']}, "
         f"问题数: {quality['issue_count']}, "
         f"可信度: {quality['confidence']:.0%}")

    # ── 写入反思日志 ─────────────────────────────────────────────────────
    _append_reflection_log(task, chain, errors_found, quality)

    return {
        "answer": revised_answer,
        "chain": chain,
        "passed": quality["passed"],
        "errors_found": errors_found,
        "alternatives": alternatives,
        "quality": quality,
    }


# ─── 辅助函数 ──────────────────────────────────────────────────────────────

def _read_file_safe(path: Path) -> str:
    """安全读文件，不存在返回空字符串。"""
    try:
        if path.exists():
            return path.read_text("utf-8")
    except Exception:
        pass
    return ""


def _search_knowledge(
    task: str,
    solution: str,
    facts_content: str,
    knowledge_content: str,
) -> List[str]:
    """
    从知识库中搜索与当前任务相关的断言。
    使用关键词匹配（不依赖外部 embedding API）。
    """
    combined = facts_content + "\n" + knowledge_content
    lines = combined.split("\n")
    relevant: List[str] = []

    # 提取关键词
    keywords = set()
    for text in [task, solution]:
        # 提取中文/英文单词（去掉常见停用词）
        tokens = re.findall(r'[\w\u4e00-\u9fff]+', text.lower())
        # 过滤短词和常见词
        stopwords = {
            "的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
            "都", "一", "个", "上", "也", "很", "到", "说", "要", "去",
            "你", "会", "着", "没有", "看", "好", "自己", "这", "the",
            "a", "an", "is", "to", "and", "in", "it", "of", "for",
            "on", "with", "as", "at", "by", "that", "this", "be",
        }
        keywords.update(t for t in tokens if len(t) >= 2 and t not in stopwords)

    keywords_str = "|".join(re.escape(k) for k in keywords)

    if not keywords_str:
        return ["（无法提取有效关键词）"]

    # 匹配 --- 至少命中 1 个关键词 的断言行
    pattern = re.compile(keywords_str, re.IGNORECASE)
    seen = set()

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith(("#", "|", "-", "*")):
            continue
        if pattern.search(line_stripped):
            if line_stripped not in seen:
                seen.add(line_stripped)
                relevant.append(line_stripped[:150])

    if not relevant:
        relevant.append("（未找到精确相关断言——这是新领域，谨慎）")

    return relevant


def _detect_known_issues(
    solution: str,
    relevant_knowledge: List[str],
    errors_content: str,
) -> List[str]:
    """
    检查答案是否踩到已知坑点。
    """
    issues: List[str] = []

    if not errors_content:
        return issues

    error_patterns = re.findall(r'[-*]\s*\[.*?\]\s*(.+?)(?:\n|$)', errors_content, re.MULTILINE)

    for ep in error_patterns:
        ep_clean = ep.strip()
        if not ep_clean:
            continue
        # 检查答案是否触发了这个错误模式
        error_keywords = re.findall(r'[\w\u4e00-\u9fff]{2,}', ep_clean.lower())
        match_count = sum(
            1 for ek in error_keywords
            if ek.lower() in solution.lower()
        )
        if match_count >= 2:  # 命中了相关关键词
            issues.append(f"疑似触发已知错误: {ep_clean[:120]}")

    return issues


def _analyze_failure_points(
    solution: str,
    task: str,
    existing_info: str,
    errors_content: str,
) -> List[str]:
    """
    假设失败场景，预测最容易出错的点。

    分析维度：
    1. 信息完整性——答案是否依赖未提供的上下文
    2. 假设强度——答案做出哪些隐含假设
    3. 边界条件——极端输入会怎样
    4. 已知错误模式匹配
    """
    failures: List[str] = []
    sol_lower = solution.lower()

    # ── 检查信息完整性 ────────────────────────────────────────────────
    # 检查是否用到了未在 context 中出现的关键概念
    unanswered_refs = re.findall(r'(?:详见|参考|见|参照)\s*(.+?)(?:[。，；\n]|$)', solution)
    for ref in unanswered_refs:
        ref_clean = ref.strip()
        if ref_clean and ref_clean not in existing_info:
            failures.append(f"引用未提供的上下文: '{ref_clean}'")

    # ── 检查隐含假设 ──────────────────────────────────────────────────
    assumption_signals = [
        (r'(?:假设|假定|默认)\s*(.+?)(?:[。，；\n]|$)', "隐含假设"),
        (r'(?:一般来说|通常|通常情况下)\s*(.+?)(?:[。，；\n]|$)', "过度泛化"),
        (r'(?:没问题|肯定|一定是|绝对)\s*(.+?)(?:[。，；\n]|$)', "过度自信断言"),
    ]
    for pattern, category in assumption_signals:
        matches = re.findall(pattern, solution)
        for m in matches:
            failures.append(f"[{category}] {m[:100]}")

    # ── 检查边界条件 ──────────────────────────────────────────────────
    # 三种边界类型：空值、异常、规模
    # 只在答案确实没有做任何相关处理时才报告
    has_null_handling = bool(re.search(
        r'(?:if\s+.*(?:None|null|空|不存在|len)|try|except|FileNotFoundError|JSONDecodeError|ValueError|KeyError|get\()',
        solution
    ))
    has_error_handling = bool(re.search(
        r'(?:try|except|if.*(?:not|is None|==|不存在|找不到|若有|若无|if not)|验证|校验|确认|check|validate|verify)',
        solution
    ))
    has_scale_handling = bool(re.search(
        r'(?:分批|分页|limit|batch|chunk|缓存|cache|超时|timeout|限流|rate\s*limit)',
        sol_lower
    ))

    if not has_null_handling:
        failures.append("[边界·空值] 未检测到空值/不存在检查")
    if not has_error_handling:
        failures.append("[边界·异常] 未检测到异常处理/错误恢复")
    if not has_scale_handling:
        # 仅在长答案（可能是复杂方案）时报告
        if len(solution) > 100:
            failures.append("[边界·规模] 未检测到规模/性能边界处理（可选）")

    # ── 从 common-errors.md 中提取已知模式 ───────────────────────────
    if errors_content:
        # 提取 [X] 格式的错误编号引用
        error_refs = re.findall(r'\[([A-Z]+\d+)\]', solution)
        if error_refs:
            for ref in error_refs[:5]:
                # 在错误库中找对应的描述
                err_match = re.search(
                    rf'{re.escape(ref)}[\s:：]*(.+?)(?:\n|$)',
                    errors_content
                )
                if err_match:
                    failures.append(f"引用已知错误 {ref}: {err_match.group(1).strip()[:100]}")

    return failures


def _analyze_traps(solution: str, task: str) -> List[str]:
    """
    站在问题制造者角度：如果想让人犯错，会在哪埋坑。

    这是一种"红队思考"——假设最恶意的解读。
    """
    traps: List[str] = []
    sol_lower = solution.lower()

    # ── 埋坑模式检测 ──────────────────────────────────────────────────
    trap_patterns = [
        ("数值硬编码", r"(?:=\\s*[\\d]+\\s*[秒分天小时分钟]|\\b\\d{2,}\\s*%|\\b[\\d]+\\.[\\d]+\\s*(?:秒|ms|min))"),
        ("未验证的假设", r'(?:假设.*没有问题|肯定没问题|应该是这样)'),
        ("单路径答案", r'(?:只有.*方法|唯一.*方式|只能.*这样)'),
        ("忽略副作用", r'(?:不会影响|不影响|无影响|无害)'),
        ("空口承诺", r'(?:保证|确保|一定可以|肯定有效)'),
    ]
    for category, pattern in trap_patterns:
        matches = re.findall(pattern, solution)
        for m in matches:
            traps.append(f"[{category}] 可能埋坑点: '{m[:80]}'")

    # ── 技术陷阱检测 ──────────────────────────────────────────────────
    # 路径硬编码
    path_patterns = re.findall(r"(?:/|\\\\|\\\\)[\w/\\\.-]{10,}", solution)
    for pp in path_patterns:
        traps.append(f"[硬编码路径] '{pp}' 在跨环境时可能失效")

    # URI/端口硬编码
    uri_patterns = re.findall(r"(?:https?://|ws://)[^\s\"'\)\]]{10,}", solution)
    for up in uri_patterns:
        traps.append(f"[硬编码URL] '{up[:80]}' 需要确认在所有环境下可达")

    # ── 缺失错误处理 ──────────────────────────────────────────────────
    if re.search(r'(?:try|except|catch|错误处理|异常)', sol_lower) is None:
        traps.append("[缺失错误处理] 未检测到任何错误处理/异常保护模式")

    # ── 缺失验证/回滚 ─────────────────────────────────────────────────
    # 防御性编程模式（.get(), try/except, if checks）也算一种验证形式
    has_defensive = bool(
        re.search(r'(?:验证|校验|确认|check|validate|verify|回滚|rollback|备份|backup)', sol_lower)
        or re.search(r'\.get\(', solution)
        or re.search(r'if\s+.*(?:in|not in|is|not|is not)', solution)
    )
    if not has_defensive:
        traps.append("[缺失验证机制] 没有验证/确认/回滚机制")

    return traps


def _generate_alternatives(solution: str, context: dict) -> List[dict]:
    """
    生成备选方案对比表。

    评估维度：
    - 极简方案（奥卡姆剃刀）：最少的假设 + 最少的组件
    - 极通用方案：最全面的覆盖 + 最鲁棒的边界处理
    - 极快方案：最快实现路径
    """
    alternatives: List[dict] = []

    # 从上下文提取约束
    task = context.get("task", "")
    task_lower = task.lower()

    # 判断任务类型
    is_complex = len(solution) > 500 or any(
        kw in task_lower for kw in ["系统", "架构", "重构", "复杂", "集成", "多"]
    )

    # ── 极简方案 ──────────────────────────────────────────────────────
    simple_desc = "奥卡姆剃刀方案：砍掉所有非必要组件，只保留核心功能"
    simple_pros = (
        "✅ 出错面更小（组件越少，出错点越少）\n"
        "✅ 维护成本最低\n"
        "✅ 认知负载最低\n"
        "✅ 符合长期极简理论：可扩展性来自简洁而不是预留"
    )
    simple_cons = (
        "❌ 可能不能覆盖所有边界情况\n"
        "❌ 功能单一，后续扩展可能需重做"
    )
    simple_when = "任务边界清晰、需求稳定、一个人维护"

    # ── 通用方案 ──────────────────────────────────────────────────────
    general_desc = "安全网方案：全面覆盖边界，增加错误处理、日志、验证"
    general_pros = (
        "✅ 覆盖更多边界和异常情况\n"
        "✅ 更鲁棒，不易崩溃\n"
        "✅ 更易被不同人理解和使用"
    )
    general_cons = (
        "❌ 代码量更大，认知负载高\n"
        "❌ 组件间耦合可能增加维护成本\n"
        "❌ 过早优化——很多覆盖可能永不需要"
    )
    general_when = "团队协作、公共API、生产环境、非一人维护"

    # ── 直觉直接方案 ──────────────────────────────────────────────────
    direct_desc = "直接方案：根据第一直觉给出最简单的可行实现"
    direct_pros = (
        "✅ 速度最快\n"
        "✅ 最少过度设计\n"
        "✅ 符合'先跑起来再优化'原则"
    )
    direct_cons = (
        "❌ 可能忽略已知陷阱\n"
        "❌ 缺乏系统性思考"
    )
    direct_when = "快速原型、POC、一人临时任务、时间紧迫"

    alternatives = [
        {
            "name": "🪒 极简（奥卡姆）",
            "description": simple_desc,
            "pros": simple_pros,
            "cons": simple_cons,
            "when": simple_when,
        },
        {
            "name": "🛡️ 通用（鲁棒）",
            "description": general_desc,
            "pros": general_pros,
            "cons": general_cons,
            "when": general_when,
        },
        {
            "name": "⚡ 直觉（直接）",
            "description": direct_desc,
            "pros": direct_pros,
            "cons": direct_cons,
            "when": direct_when,
        },
    ]

    # 如果当前方案没有极简倾向，加一条"当前方案的替代减量版"
    solution_line_count = solution.count("\n") + 1
    if solution_line_count > 40 and is_complex:
        alternatives.append({
            "name": "✂️ 当前方案减量版",
            "description": f"删减当前方案中非核心功能（当前 {solution_line_count} 行），"
                           f"只保留解决核心问题的部分",
            "pros": "✅ 基于已有思考，减少·重头再来·的浪费",
            "cons": "❌ 减的时候可能砍掉重要的边界处理",
            "when": "当当前方案过度设计时",
        })

    return alternatives


def _choose_best_approach(
    solution: str,
    alternatives: List[dict],
    errors_found: List[str],
    task: str,
) -> dict:
    """
    根据当前分析结果，选择最佳方案并给出理由。
    """
    task_lower = task.lower()

    # 判断当前方案倾向
    is_long = len(solution) > 800
    is_complex = len(errors_found) > 3

    if is_long and is_complex:
        # 当前方案已经复杂且有已知问题→倾向极简
        verdict = "倾向极简方案：当前方案已经较复杂且有多个已知问题，建议砍掉非核心需求"
        confidence = "高"
    elif is_long and not is_complex:
        # 长度大但没有发现问题→可能是合理覆盖了边界
        verdict = "当前方案可接受：虽然较长，但没有发现关键问题。但考虑是否有可以简化的部分"
        confidence = "中"
    elif not is_long and is_complex:
        # 短但有多个问题→可能过度简化
        verdict = "倾向通用方案：当前方案较短但发现多个潜在问题，建议增补边界处理和验证"
        confidence = "高"
    else:
        # 短且干净→极简方案已经合适
        verdict = "当前方案适合：简练且无明显问题。保持极简，不画蛇添足"
        confidence = "高"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": (
            f"长度分析: {'过长' if is_long else '适中'}\n"
            f"发现问题: {len(errors_found)} 个\n"
            f"结论: {verdict}"
        ),
    }


def _revise_answer(
    solution: str,
    errors_found: List[str],
    alternatives: List[dict],
    best_choice: dict,
    context: dict,
) -> str:
    """
    根据反思结果修订答案。

    修订规则：
    1. 如果发现问题，添加追加以修正
    2. 如果方案向极简倾斜，做增量精简
    3. 保留原始的思考框架，只做修补
    """
    if not errors_found:
        return solution  # 没问题，原样输出

    # 添加反思附注
    notes = []
    notes.append("\n\n---\n")
    notes.append("> 🔍 **反思质检附注** — dandan 9步反思方法论\n")

    if errors_found:
        notes.append(">\n> **潜在问题提醒：**\n")
        for i, err in enumerate(errors_found[:5], 1):
            notes.append(f"> {i}. {err}\n")

    if alternatives:
        notes.append(">\n> **备选方案对比：**\n")
        for alt in alternatives[:2]:
            notes.append(f"> • **{alt['name']}**: {alt['description'][:100]}...\n")

    notes.append(f">\n> **选择判断**: {best_choice['verdict']}\n")

    revised = solution + "".join(notes)
    return revised


def _assess_quality(
    errors_found: List[str],
    alternatives: List[dict],
    revised_answer: str,
) -> dict:
    """
    质量评分。
    """
    issue_count = len(errors_found)
    critical_issues = sum(
        1 for e in errors_found
        if any(kw in e for kw in [
            "硬编码", "缺失错误处理", "缺失验证", "引用未提供的上下文",
        ])
    )

    # 可信度评分
    confidence = max(0.0, 1.0 - (issue_count * 0.15) - (critical_issues * 0.2))

    return {
        "passed": issue_count < 5 and critical_issues == 0,
        "issue_count": issue_count,
        "critical_issues": critical_issues,
        "confidence": round(confidence, 2),
    }


def _append_reflection_log(
    task: str,
    chain: List[dict],
    errors_found: List[str],
    quality: dict,
) -> None:
    """将反思记录追加到反思日志文件。"""
    try:
        REFLECTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = [
            f"\n## {timestamp}",
            f"**任务**: {task[:200]}",
            f"**通过**: {quality['passed']} | **问题数**: {quality['issue_count']} | **可信度**: {quality['confidence']:.0%}",
        ]
        if errors_found:
            entry.append("**发现的问题:**")
            for e in errors_found:
                entry.append(f"- {e}")
        entry.append("")
        with open(REFLECTION_LOG_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(entry))
    except Exception:
        pass  # 写日志失败不中断主流程


# ─── 快速检测函数（供外部调用） ────────────────────────────────────────────

def quick_check(solution: str, task: str = "") -> dict:
    """
    快速反思检测——不需要准备完整 context 时使用。

    Args:
        solution: 待检查的答案
        task: 任务描述（可选）

    Returns:
        精简版反思结果
    """
    context = {
        "task": task,
        "existing_info": "",
        "memory_results": [],
    }
    result = reflect(context, solution)
    return {
        "passed": result["passed"],
        "errors_found": result["errors_found"],
        "confidence": result["quality"]["confidence"],
    }


# ─── 交互式反思工具 ────────────────────────────────────────────────────────

def interactive_reflect() -> None:
    """交互式反思——在终端中逐步引导用户走完9步。"""
    print("=" * 60)
    print("  🌫️  dandan 9步反思质检器 — 交互模式")
    print("=" * 60)

    task = input("\n📋 任务描述: ").strip()
    solution = input("📝 原始答案 (粘贴或输入，Ctrl+D 结束):\n").strip()

    context = {
        "task": task,
        "existing_info": "",
        "memory_results": [],
    }

    result = reflect(context, solution)

    print("\n" + "=" * 60)
    print("  📊 反思结果摘要")
    print("=" * 60)
    print(f"  通过: {'✅ 是' if result['passed'] else '❌ 否'}")
    print(f"  问题数: {len(result['errors_found'])}")
    print(f"  可信度: {result['quality']['confidence']:.0%}")

    if result["errors_found"]:
        print("\n  🚨 发现的问题:")
        for i, e in enumerate(result["errors_found"], 1):
            print(f"    {i}. {e}")

    print("\n  📋 反思链:")
    for entry in result["chain"]:
        print(f"    [{entry['step']}] {entry['name']}: {entry['analysis'][:80]}...")

    print("\n  📝 修订版答案:")
    print(result["answer"])


# ─── CLI 入口 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--interactive" in sys.argv or "-i" in sys.argv:
        interactive_reflect()
    elif len(sys.argv) >= 2 and sys.argv[1] == "--check":
        # python3 reflection_check.py --check < task.txt
        task_text = sys.argv[2] if len(sys.argv) > 2 else ""
        solution_text = sys.stdin.read().strip()
        ctx = {"task": task_text, "existing_info": "", "memory_results": []}
        r = reflect(ctx, solution_text)
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"用法:")
        print(f"  python3 {sys.argv[0]} -i                        交互模式")
        print(f"  echo '答案' | python3 {sys.argv[0]} --check '任务' 管道模式")
        print(f"")
        print(f"作为模块导入:")
        print(f"  from reflection_check import reflect")
        print(f"  result = reflect(context, solution_draft)")
