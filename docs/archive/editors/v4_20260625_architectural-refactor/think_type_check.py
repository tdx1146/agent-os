"""
think_type_check.py - 思维断言类型检查器

给推理文本中的断言标注来源类型（因果/举例/推理/猜测），
并检测类型不匹配（如结论标为「因果」但前提仅为「猜测」或「单个例子」）。

纯规则实现，不依赖外部库。
仅供内部调用，不设 CLI。

函数签名：
    check_types(text) -> list
"""

import re
import json


# ---------------------------------------------------------------------------
# 关键词定义
# ---------------------------------------------------------------------------

# 因果类关键词（表明因果关系）
CAUSAL_PATTERNS = [
    r'因为.*所以', r'由于.*因此', r'导致', r'致使', r'引发',
    r'原因在于', r'根源是', r'由.*引起', r'受.*影响', r'促成',
    r'因而', r'故而', r'可见', r'由此可见', r'说明', r'表明',
    r'决定了', r'依赖于', r'取决于', r'造成', r'带来',
    r'推知', r'由此', r'既然.*那么', r'如果.*则',
]

# 举例类关键词（表明举例说明）
EXAMPLE_PATTERNS = [
    r'例如', r'比如', r'举例', r'譬如', r'如.*所示',
    r'像.*一样', r'类似', r'以.*为例', r'拿.*来说',
    r'其中一个', r'某个', r'具体来看', r'从.*看',
    r'比如说', r'就像', r'比方说', r'一个例子',
]

# 推理类关键词（表明逻辑推导）
REASONING_PATTERNS = [
    r'根据.*可以', r'基于.*推断', r'由此推出', r'综合来看',
    r'分析可知', r'可以推断', r'合理推测', r'逻辑上',
    r'归纳', r'总结', r'整体上', r'结合.*考虑',
    r'从.*角度', r'推导', r'推论', r'演绎',
    r'可以认为', r'可谓', r'本质上', r'意味着',
]

# 猜测类关键词（表明不确定 / 推测）
GUESS_PATTERNS = [
    r'可能', r'也许', r'或许', r'大概', r'估计',
    r'似乎', r'看起来', r'好像', r'说不定', r'没准',
    r'推测', r'猜测', r'臆测', r'盲猜', r'揣测',
    r'不知是否', r'大概率是', r'倾向于', r'八成',
    r'大抵', r'疑似', r'或', r'莫非',
]

# 结论性表述（用于 mismatch 检测：结论的前提不能只是猜测/单个例子）
CONCLUSION_PATTERNS = [
    r'总之', r'综上所述', r'总而言之', r'结论是',
    r'最终', r'因此', r'所以', r'故而', r'可以断定',
    r'可以确定', r'毫无疑问', r'必然', r'必定',
]

# 单个例子标记（用于检测「举例冒充因果」）
SINGLE_EXAMPLE_MARKERS = [
    r'仅.*一例', r'只有一个', r'某.*一次', r'唯一',
    r'仅.*个', r'单个',
]


# ---------------------------------------------------------------------------
# 编译正则
# ---------------------------------------------------------------------------

def _compile(patterns):
    return [re.compile(p) for p in patterns]

RE_CAUSAL = _compile(CAUSAL_PATTERNS)
RE_EXAMPLE = _compile(EXAMPLE_PATTERNS)
RE_REASONING = _compile(REASONING_PATTERNS)
RE_GUESS = _compile(GUESS_PATTERNS)
RE_CONCLUSION = _compile(CONCLUSION_PATTERNS)
RE_SINGLE_EXAMPLE = _compile(SINGLE_EXAMPLE_MARKERS)


# ---------------------------------------------------------------------------
# 断言切分
# ---------------------------------------------------------------------------

def _split_assertions(text):
    """
    将文本按常见断言分隔符切分为句子/断言列表。
    保留句号、问号、感叹号、分号、换行作为分隔符。
    """
    # 保留分隔符位置，用于还原原文摘取
    parts = re.split(r'([。！？\n;；]+)', text)
    assertions = []
    for i in range(0, len(parts), 2):
        segment = parts[i]
        # 拼接后面的分隔符
        if i + 1 < len(parts):
            segment += parts[i + 1]
        segment = segment.strip()
        if segment:
            assertions.append(segment)
    return assertions


# ---------------------------------------------------------------------------
# 类型判断
# ---------------------------------------------------------------------------

def _classify_assertion(assertion):
    """
    对单个断言分类，返回 (type, confidence)。
    优先级：因果 > 举例 > 推理 > 猜测（按关键词命中数量和强度）。
    """
    scores = {
        '因果': 0,
        '举例': 0,
        '推理': 0,
        '猜测': 0,
    }

    for re_list, label in [
        (RE_CAUSAL, '因果'),
        (RE_EXAMPLE, '举例'),
        (RE_REASONING, '推理'),
        (RE_GUESS, '猜测'),
    ]:
        for re_obj in re_list:
            if re_obj.search(assertion):
                scores[label] += 1

    # 选最高分类型；分数相同按优先级
    best_type = max(scores, key=lambda k: (scores[k], {'因果': 4, '举例': 3, '推理': 2, '猜测': 1}[k]))

    # 如果都没命中，默认「推理」
    if scores[best_type] == 0:
        return '推理', 0.3

    # confidence = min(1.0, 命中数 * 0.4)
    confidence = min(1.0, scores[best_type] * 0.4)
    return best_type, confidence


# ---------------------------------------------------------------------------
# 上下文 mismatch 检测
# ---------------------------------------------------------------------------

def _detect_mismatch(assertions_info):
    """
    检测类型不匹配。
    规则：
    1. 结论类断言（含「总之/综上所述」等）标注为「因果」时，
       若其前面的前提断言全是「猜测」或「举例」，则 mismatch。
    2. 标注为「因果」的断言，若前面紧邻的断言是「猜测」且无其他「因果」支撑，则 mismatch。
    3. 标注为「因果」的断言，若仅基于「单个例子」（举例且含单个例子标记），则 mismatch。
    """
    results = []

    for i, info in enumerate(assertions_info):
        assertion = info['assertion']
        atype = info['type']
        mismatch = False
        reason = ''

        # 规则 1：结论类断言的前提检查
        is_conclusion = any(re_obj.search(assertion) for re_obj in RE_CONCLUSION)
        if is_conclusion and atype in ('因果', '推理'):
            # 查看前面所有前提
            pre_types = [assertions_info[j]['type'] for j in range(i)]
            if pre_types and all(t in ('猜测', '举例') for t in pre_types):
                mismatch = True
                reason = '结论标注为「{}」，但所有前提仅为「猜测」或「举例」，缺乏可靠支撑'.format(atype)

        # 规则 2：因果断言的前置猜测检查
        if not mismatch and atype == '因果':
            if i > 0 and assertions_info[i - 1]['type'] == '猜测':
                # 检查前面是否有其他因果断言
                has_causal_before = any(assertions_info[j]['type'] == '因果' for j in range(i))
                if not has_causal_before:
                    mismatch = True
                    reason = '标注为「因果」，但前置断言为「猜测」且无其他因果支撑'

        # 规则 3：单个例子冒充因果
        if not mismatch and atype == '因果':
            if i > 0 and assertions_info[i - 1]['type'] == '举例':
                prev = assertions_info[i - 1]['assertion']
                is_single = any(re_obj.search(prev) for re_obj in RE_SINGLE_EXAMPLE)
                if is_single:
                    mismatch = True
                    reason = '标注为「因果」，但仅基于单个例子，无法构成因果链'

        results.append({
            'assertion': assertion,
            'type': atype,
            'confidence': info['confidence'],
            'mismatch': mismatch,
            'mismatch_reason': reason,
        })

    return results


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def check_types(text):
    """
    输入推理文本，返回每个断言的类型检查结果。

    返回格式：
    [
      {
        "assertion": "原文摘取",
        "type": "因果|举例|推理|猜测",
        "confidence": 0.0-1.0,
        "mismatch": true/false,
        "mismatch_reason": "类型不匹配说明"
      }
    ]
    """
    if not text or not text.strip():
        return []

    assertions = _split_assertions(text)

    # 第一步：给每个断言分类
    assertions_info = []
    for a in assertions:
        atype, conf = _classify_assertion(a)
        assertions_info.append({
            'assertion': a,
            'type': atype,
            'confidence': conf,
        })

    # 第二步：上下文 mismatch 检测
    return _detect_mismatch(assertions_info)


# ---------------------------------------------------------------------------
# 便捷打印（调试用，非 CLI）
# ---------------------------------------------------------------------------

def pretty_print(result):
    """格式化打印检查结果，方便调试。"""
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # 仅供开发调试，不构成 CLI
    sample = (
        "今天天气似乎要下雨了，可能下午会有暴雨。"
        "比如昨天就下了一场大雨。"
        "由于云层太厚，所以今天很可能会持续降雨。"
        "综上所述，今天应该取消户外活动。"
    )
    result = check_types(sample)
    pretty_print(result)
