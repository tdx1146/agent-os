#!/usr/bin/env python3
"""
think_test.py — 思维断言单元测试模块

对一条思维断言自动生成三组测试：
  1. 前提反转测试  — 把前提条件反过来，结论还成立吗？
  2. 语境迁移测试  — 换到另一个类似场景，断言还成立吗？
  3. 冲突检测测试  — 和已有断言列表是否矛盾？

纯规则实现（正则 + 反义词替换 + 模式匹配），不依赖外部库。

函数签名：
    test_assertion(text, history=None) -> dict

输出格式：
    {
      "assertion": "原始断言",
      "tests": [
        {
          "test_type": "前提反转|语境迁移|冲突检测",
          "passed": true/false,
          "reason": "测试结论"
        }
      ]
    }
"""

import re
from typing import List, Dict, Optional, Any

# ---------------------------------------------------------------------------
# 反义词表
# ---------------------------------------------------------------------------
ANTONYMS = {
    # 逻辑量词
    "所有": "没有", "每个": "不是每个", "全部": "部分", "都": "不都",
    "任何": "没有任何", "必然": "可能不", "一定": "未必",
    "总是": "有时不", "经常": "很少", "多数": "少数",
    # 属性/状态
    "存在": "不存在", "有": "没有", "无": "有",
    "是": "不是", "真": "假", "实": "虚",
    "正确": "错误", "有效": "无效", "成功": "失败",
    "好": "坏", "坏": "好", "善": "恶", "美": "丑",
    "新": "旧", "旧": "新", "热": "冷", "冷": "热",
    "干": "湿", "湿": "干", "亮": "暗", "暗": "亮",
    "开": "关", "关": "开", "生": "死", "死": "生",
    "进": "退", "退": "进", "上": "下", "下": "上",
    "内": "外", "外": "内", "先": "后", "后": "先",
    "前": "后", "左": "右", "右": "左",
    "高": "低", "大": "小", "多": "少", "快": "慢", "早": "晚",
    # 时间
    "过去": "未来", "未来": "过去", "现在": "曾经",
    "永远": "暂时", "永久": "短暂", "短暂": "永久",
    "以后": "以前", "以前": "以后", "之后": "之前", "之前": "之后",
    # 抽象
    "简单": "复杂", "复杂": "简单", "容易": "困难", "困难": "容易",
    "自由": "受限", "独立": "依赖", "主动": "被动", "被动": "主动",
    "积极": "消极", "消极": "积极", "正面": "负面", "负面": "正面",
    "内部": "外部", "外部": "内部", "局部": "整体", "整体": "局部",
    "微观": "宏观", "宏观": "微观", "具体": "抽象", "抽象": "具体",
    "表面": "深层", "深层": "表面", "显性": "隐性", "隐性": "显性",
    "可见": "不可见", "透明": "不透明", "公开": "秘密",
    "合法": "非法", "非法": "合法", "正当": "不当", "合理": "不合理",
    "公平": "不公平", "公正": "不公正", "正义": "非正义", "道德": "不道德",
    "诚实": "不诚实", "真诚": "虚伪", "虚伪": "真诚",
    "可靠": "不可靠", "可信": "不可信",
    "一致": "不一致", "统一": "分裂", "团结": "分裂",
    "合作": "对抗", "对抗": "合作", "竞争": "协作", "协作": "竞争",
    "和谐": "冲突", "冲突": "和谐", "稳定": "不稳定", "平衡": "失衡",
    "正常": "异常", "异常": "正常", "规范": "不规范",
    # 行为/变化
    "增长": "下降", "增加": "减少", "上升": "下降",
    "提高": "降低", "提升": "下降", "扩大": "缩小",
    "扩展": "收缩", "膨胀": "萎缩", "进步": "退步",
    "改善": "恶化", "恶化": "改善",
    "开放": "封闭", "进入": "退出", "加入": "退出",
    "拥有": "失去", "保护": "破坏", "安全": "危险",
    "创新": "守旧", "改革": "保守", "变革": "维持",
    "升级": "降级", "更新": "停用", "淘汰": "保留",
    "放弃": "坚持", "坚持": "放弃",
    "接受": "拒绝", "拒绝": "接受", "同意": "反对",
    "支持": "反对", "赞成": "反对", "拥护": "抵制",
    "欢迎": "排斥", "吸引": "排斥",
    "推动": "阻碍", "阻碍": "推动", "促进": "阻碍",
    "加速": "减速", "减速": "加速",
    "鼓励": "打击", "激励": "压制", "引导": "误导",
    "保护": "伤害", "维护": "破坏", "修复": "毁坏",
    # 关系
    "包含": "排除", "包括": "排除",
    "属于": "不属于", "隶属": "不隶属",
    "相关": "无关", "有关": "无关",
    "依赖": "独立", "取决于": "独立于",
    "优于": "劣于", "劣于": "优于", "强于": "弱于",
}

# 二元关系谓词（用于语境迁移时的替换）
RELATION_PAIRS = [
    ("大于", "小于"), ("等于", "不等于"),
    ("高于", "低于"), ("强于", "弱于"),
    ("快于", "慢于"), ("早于", "晚于"),
    ("优于", "劣于"), ("多于", "少于"),
    ("包含于", "包含"), ("属于", "包含"),
    ("支配", "服从"), ("支配", "被支配"),
]

# 逻辑连接词模式
# 注意：中文条件句用逗号分隔前提和结论，模式强制匹配逗号后面的中文内容
CONDITIONAL_PATTERNS = [
    re.compile(r"如果(.+?)，(.+?)[。\.]?$"),
    re.compile(r"若(.+?)，(.+?)[。\.]?$"),
    re.compile(r"只要(.+?)[，,](.+?)[。\.]?$"),
    re.compile(r"只有(.+?)[，,](.+?)[。\.]?$"),
    re.compile(r"因为(.+?)[，,](.+?)[。\.]?$"),
    re.compile(r"由于(.+?)[，,](.+?)[。\.]?$"),
    re.compile(r"(.+?)[，,](.+?)，从而(.+?)[。\.]?$"),
]

# 因果关系词
CAUSAL_WORDS = ["因为", "所以", "因此", "因而", "从而", "导致", "使得", "引发", "引起"]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _replace_antonyms(text: str) -> str:
    """对 text 中的所有反义词进行一次替换（最长匹配优先）。"""
    result = text
    # 按长度降序排列，避免短词先匹配
    for word in sorted(ANTONYMS, key=len, reverse=True):
        antonyms = ANTONYMS[word]
        if isinstance(antonyms, list):
            replacement = antonyms[0]
        else:
            replacement = antonyms
        # 只替换第一个出现的（避免过度反转）
        if word in result:
            result = result.replace(word, replacement, 1)
            break
    return result


def _negate_sentence(text: str) -> str:
    """对句子进行否定化：添加否定词 + 替换反义词。"""
    # 先试反义词替换
    negated = _replace_antonyms(text)
    if negated != text:
        return negated
    # 如果没有命中的反义词，加"不"
    if "不" not in text and "没" not in text and "非" not in text:
        # 在谓语位置插入否定
        for verb in ["是", "有", "会", "能", "可以", "应该", "必须", "需要"]:
            if verb in negated:
                negated = negated.replace(verb, f"不{verb}", 1)
                return negated
        return f"并非 ({negated})"
    return f"非 ({negated})"


def _extract_claims(text: str) -> List[str]:
    """从断言文本中提取子断言/子句列表。"""
    # 按句号、分号、逗号分割（保留长句）
    parts = re.split(r"[。；\n]", text)
    claims = [p.strip() for p in parts if len(p.strip()) > 3]
    if not claims:
        claims = [text.strip()]
    return claims


def _has_conditional(text: str) -> bool:
    """检测是否包含条件/因果结构。"""
    for pat in CONDITIONAL_PATTERNS:
        if pat.search(text):
            return True
    for w in CAUSAL_WORDS:
        if w in text:
            return True
    return False


def _replace_relation(text: str) -> str:
    """替换二元关系词（如 大于↔小于）。"""
    result = text
    for a, b in RELATION_PAIRS:
        if a in result:
            result = result.replace(a, b, 1)
            break
        elif b in result:
            result = result.replace(b, a, 1)
            break
    return result


def _extract_entities(text: str) -> List[str]:
    """提取文本中的实体名词（启发式：2-4字名词候选）。
    优先提取长实体（3-6字），过滤动词/虚词/逻辑词。
    """
    # 尽量提取长实体（3-6字），避免动词和逻辑词
    tokens_3_6 = re.findall(r"[\u4e00-\u9fff]{3,6}", text)
    stop_words = {"因为", "所以", "如果", "但是", "而且", "虽然", "由于",
                   "因此", "然后", "并且", "或者", "还是", "一个", "这个",
                   "那个", "这些", "那些", "什么", "怎么", "可以", "没有",
                   "不是", "就是", "也是", "都是", "是是", "所有", "有些",
                   "很多", "很少", "很大", "很小", "情况", "时候", "地方",
                   "东西", "方式", "方法", "问题", "原因", "结果", "过程",
                   "不能", "不会", "不一定", "可能", "应该", "必须",
                   "之后", "之前", "目前", "当前", "过去", "将来", "未来",
                   "一般", "通常", "往往", "有时", "经常", "已经", "正在",
                   "仍然", "依然", "还是", "就是", "只是", "但是", "不过",
                   "推理能力", "能力", "不能", "增加", "减少", "提升", "下降",
                   "提高", "降低", "进入", "退出", "加入", "离开",
                   "拥有", "失去", "变成", "成为", "显示", "表明",
                   "需要", "必须", "应该", "可以", "可能", "一定",
                   "就是", "不是", "都是", "还是", "没有", "什么",
                   "这样", "那样", "这种", "那种", "这些", "那些"}
    entities = [t for t in tokens_3_6 if t not in stop_words]
    if not entities:
        # 回退到2字词
        tokens_2 = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
        entities = [t for t in tokens_2 if t not in stop_words and t not in ("更多", "更少", "更大", "更小", "更快", "更慢", "更好", "更差", "很多", "很少", "所有", "有些", "一些", "这个", "那个", "这些", "那些", "有的", "别的", "其他", "其余")]
    return list(set(entities))


# ---------------------------------------------------------------------------
# 测试生成器
# ---------------------------------------------------------------------------

def _test_premise_inversion(text: str) -> Dict[str, Any]:
    """测试1：前提反转 — 把前提条件反过来，结论还成立吗？"""
    claims = _extract_claims(text)

    if _has_conditional(text):
        # 处理条件结构
        inverted_text = text
        for pat in CONDITIONAL_PATTERNS:
            m = pat.search(text)
            if m:
                condition = m.group(1)
                conclusion = m.group(2)
                neg_cond = _negate_sentence(condition)
                # 构造反向前提
                inverted_text = text.replace(condition, neg_cond, 1)
                reason = (
                    f"将前提「{condition}」反转为「{neg_cond}」后，"
                    f"原结论「{conclusion}」可能需要重新检验。"
                    f"反转前提不一定导致结论否定——但至少说明该断言"
                    f"对前提条件敏感，不可无条件推广。"
                )
                return {
                    "test_type": "前提反转",
                    "passed": True,
                    "inverted": inverted_text,
                    "reason": reason
                }
    else:
        # 处理普通断言：逐个反转子断言
        inverted_claims = []
        for c in claims:
            inverted_claims.append(_negate_sentence(c))
        inverted_text = "；".join(inverted_claims)
        reason = (
            f"将断言各分句分别否定后得到「{inverted_text}」——"
            f"反转版本和原断言通常不能同时成立，"
            f"说明该断言有确定的真值方向，不是同义反复。"
        )
        return {
            "test_type": "前提反转",
            "passed": True,
            "inverted": inverted_text,
            "reason": reason
        }

    return {
        "test_type": "前提反转",
        "passed": True,
        "reason": "未检测到可反转结构，视为平凡通过。"
    }


def _test_context_migration(text: str) -> Dict[str, Any]:
    """测试2：语境迁移 — 换到另一个类似场景，断言还成立吗？"""
    entities = _extract_entities(text)

    if not entities:
        return {
            "test_type": "语境迁移",
            "passed": True,
            "reason": "未提取到可迁移的实体，无法构造迁移场景。视为平凡通过。"
        }

    # 根据实体长度排序，优先替换长实体（更有语义价值）
    entities.sort(key=len, reverse=True)
    target = entities[0]

    # 构建迁移场景的替换词候选
    migration_pairs = {
        "模型参数": "知识库规模", "参数": "数据",
        "推理能力": "创造力", "能力": "局限性",
        "机器": "人", "人类": "AI",
        "AI": "人类", "模型": "系统", "算法": "方法",
        "程序": "流程", "代码": "文档", "数据": "知识",
        "系统": "组织", "网络": "社区", "平台": "市场",
        "公司": "团队", "企业": "个人", "组织": "个体",
        "政府": "企业", "国家": "城市", "城市": "乡村",
        "中国": "外国", "东方": "西方", "传统": "现代",
        "过去": "现在", "现在": "未来", "短期": "长期",
        "理论": "实践", "理想": "现实", "抽象": "具体",
        "整体": "部分", "宏观": "微观", "内部": "外部",
        "白天": "夜晚", "晴天": "雨天", "夏天": "冬天",
        "考试": "面试", "学习": "工作", "研究": "应用",
        "写作": "编程", "绘画": "音乐", "阅读": "观看",
        "记忆": "经验", "思考": "直觉",
    }

    replacement = migration_pairs.get(target, f"[类比:{target}]")

    migrated_text = text.replace(target, replacement, 1)

    reason = (
        f"将「{target}」替换为「{replacement}」得到迁移版本。"
        f"如果断言在迁移后仍然合理，说明有跨场景通用性；"
        f"如果显得牵强，则说明断言可能只在特定语境成立。"
    )

    return {
        "test_type": "语境迁移",
        "passed": True,
        "migrated": migrated_text,
        "reason": reason
    }


def _test_conflict_detection(text: str, history: List[str]) -> Dict[str, Any]:
    """测试3：冲突检测 — 和已有断言列表是否矛盾？"""
    if not history:
        return {
            "test_type": "冲突检测",
            "passed": True,
            "reason": "无可比对的已有断言历史，冲突检测无结论。"
        }

    # 提取当前断言的关键词
    current_keywords = set(_extract_entities(text))
    if not current_keywords:
        current_keywords = set(re.findall(r"[\u4e00-\u9fff]{2,4}", text))

    conflicts = []

    for i, h in enumerate(history):
        # 关键词重叠度
        h_keywords = set(re.findall(r"[\u4e00-\u9fff]{2,4}", h))
        overlap = current_keywords & h_keywords
        if not overlap:
            continue

        # 检测是否包含对立结构
        current_ant = set()
        for kw in current_keywords:
            a = ANTONYMS.get(kw)
            if a:
                if isinstance(a, list):
                    current_ant.update(a)
                else:
                    current_ant.add(a)

        # 如果历史断言包含当前断言的反义词，标记潜在冲突
        has_conflict = False
        conflict_reason = ""
        for ant in current_ant:
            if ant in h:
                has_conflict = True
                conflict_reason = (
                    f"当前断言含有关键词（如{'、'.join(list(overlap)[:3])}），"
                    f"而历史断言 #{i+1} 含有对应的反义词「{ant}」，"
                    f"两断言方向相反，可能存在矛盾。"
                )
                break

        if has_conflict:
            conflicts.append(conflict_reason)

    if conflicts:
        return {
            "test_type": "冲突检测",
            "passed": False,
            "reasons": conflicts
        }

    return {
        "test_type": "冲突检测",
        "passed": True,
        "reason": f"与 {len(history)} 条历史断言比较，未检测到明显矛盾。"
    }


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def test_assertion(text: str, history: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    对一条断言进行三组自动测试。

    Args:
        text: 原始断言文本
        history: 可选的已有断言列表，用于冲突检测

    Returns:
        {
            "assertion": str,
            "tests": [
                {"test_type": str, "passed": bool, "reason": str},
                ...
            ]
        }
    """
    if history is None:
        history = []

    tests = [
        _test_premise_inversion(text),
        _test_context_migration(text),
        _test_conflict_detection(text, history),
    ]

    return {
        "assertion": text,
        "tests": tests,
    }


# ---------------------------------------------------------------------------
# 命令行入口（自测用）
# ---------------------------------------------------------------------------

def main():
    """命令行测试入口。"""
    import sys

    if len(sys.argv) < 2:
        print("用法: python3 think_test.py <断言文本>")
        print("      从 stdin 读入多行（每行一条历史断言，最后一行是待测断言）")
        sys.exit(1)

    if sys.argv[1] == "--stdin":
        lines = [l.strip() for l in sys.stdin if l.strip()]
        if len(lines) < 1:
            print("错误：stdin 至少需要一行（待测断言）")
            sys.exit(1)
        text = lines[-1]
        history = lines[:-1]
    else:
        text = " ".join(sys.argv[1:])
        history = []

    import json
    result = test_assertion(text, history)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
