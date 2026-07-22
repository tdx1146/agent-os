"""
think_patches.py — 逻辑补丁生成器
===================================
检测到推理断点后，给出修复建议。不替人思考，指出"这里缺什么格式"。
"""

import re

def generate_patches(issues, task):
    patches = []
    for issue in issues:
        t = issue.get('type', '')
        evidence = issue.get('evidence', '')
        fix_hint = issue.get('fix_hint', '')
        severity = issue.get('severity', 'medium')
        # v2 类型映射
        v2_type = _TYPE_MAP_V2_TO_V1.get(t)
        if v2_type is None:
            if '反证法' in t or '归谬' in t:
                continue
        original_type = t
        if v2_type:
            t = v2_type
        if t == '逻辑跳跃':
            p = _patch_jump(task, evidence)
        elif t == '循环论证':
            p = _patch_circle(task, evidence)
        elif t == '假设未验证':
            p = _patch_unverified(task, evidence)
        elif t == '自相矛盾':
            p = _patch_contradiction(task, evidence)
        elif t == '框架固化':
            p = _patch_framework(task, evidence)
        else:
            p = _patch_generic(task, evidence)
        if p:
            # 注入 fix_hint（v2 链检测器的精确节点信息）
            p['fix_hint'] = fix_hint
            p['severity'] = severity
            p['original_type'] = original_type
            patches.append(p)
    return patches


def _patch_jump(task, evidence):
    m = re.search(r'(所以|因此|那么说|由此)(.{3,80})', task)
    if m:
        c = m.group(2).strip()
        return {
            'issue_type': '逻辑跳跃',
            'patch': '你说了一个结论但没有给出理由。尝试结构：\n'
                     '因为（具体原因），所以' + c,
            'target': '在结论前补充「因为」'
        }
    return {
        'issue_type': '逻辑跳跃',
        'patch': '句子有「所以」但没有「因为」——补充推理前提后再下结论。',
        'target': '补充推理前提'
    }


def _patch_circle(task, evidence):
    m = re.search(r'.(.+?).≈.(.+?).', evidence)
    if m:
        a = m.group(1)
        return {
            'issue_type': '循环论证',
            'patch': '理由和结论在绕圈。试试找一个和结论无关的新角度来论证。\n'
                     '比如：' + a + '，是因为（新理由）。',
            'target': '引入独立于结论的新理由'
        }
    return {
        'issue_type': '循环论证',
        'patch': '理由和结论在绕圈。尝试说出一个和结论没有直接关系的新理由。',
        'target': '引入新理由'
    }


def _patch_unverified(task, evidence):
    m = re.search(r'(是|应该|必须|肯定|毫无疑问)(.{3,60})', task)
    if m:
        c = m.group(0).strip()
        return {
            'issue_type': '假设未验证',
            'patch': '断言「' + c + '」但没有给依据。选择一种方式完善：\n'
                     'A) 补充证据：因为（数据/案例/引用）\n'
                     'B) 标记为：这只是猜测',
            'target': '断言标注来源类型'
        }
    return {
        'issue_type': '假设未验证',
        'patch': '有断言没证据。标一下这个断言的来源：是事实、推理、还是猜测？',
        'target': '标注断言类型'
    }


def _patch_contradiction(task, evidence):
    return {
        'issue_type': '自相矛盾',
        'patch': '同时表达了互相冲突的观点。选一个处理方式：\n'
                 '1) 承认矛盾：两种可能都存在\n'
                 '2) 否定一个：排除其中一个\n'
                 '3) 合并：同时为真只是因为视角不同？',
        'target': '消歧冲突断言'
    }


def _patch_framework(task, evidence):
    return {
        'issue_type': '框架固化',
        'patch': '你用同一套框架分析了多次。尝试换框：\n'
                 '1) 对方视角：站在相反立场重新描述\n'
                 '2) 拉长时间：这问题一个月后还重要吗？\n'
                 '3) 极致简化：去掉修饰词后核心是什么？',
        'target': '换分析框架'
    }


def _patch_generic(task, evidence):
    return {
        'issue_type': '通用',
        'patch': '检测到推理问题。试着换一个角度重新说一遍。',
        'target': '重组表述'
    }


# v2 兼容映射：v2 类型名 → v1 类型名
_TYPE_MAP_V2_TO_V1 = {
    '推理断点': '逻辑跳跃',
    '推理跳跃': '逻辑跳跃',
    '孤立前提': '假设未验证',
    '悖论（显性）': '自相矛盾',
    '悖论（隐性）': '自相矛盾',
    '归谬推理（反证法）': None,  # 反证法是加分不是扣分，不生成补丁
    '框架固化—需跳出': '框架固化',
}
