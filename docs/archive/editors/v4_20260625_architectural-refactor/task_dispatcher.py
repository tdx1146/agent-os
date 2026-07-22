"""
task_dispatcher.py — 任务分发器 v0.1
====================================
根据任务描述自动判断：
- 是不是需要子代理（分解任务、多视角）
- 是不是需要跨实例协作（找妹妹）
- 能不能自己做（简单任务不折腾）

输出格式：
  {"action": "self|spawn|cross", "reason": "...", "agents": [], "cross_target": ""}
"""

import re

# ── 关键词规则 ──

# 需要跨实例（找妹妹）的标志
CROSS_SIGNALS = [
    r'妹妹', r'jl', r'jiali', r'跨实例', r'双锁', r'同步',
    r'对方机器', r'那边', r'她那边', r'两边都', r'双方',
    r'共享', r'互通', r'momo pack', r'打包',
]

# 需要 spawn 子代理的标志
SPAWN_SIGNALS = [
    r'多个.*视角|不同.*角度|从.*方面', r'分析.*利弊|优缺点|对比',
    r'方案.*选择|决策|选哪', r'预测|推演|模拟|如果.*会怎样',
    r'评估|评价|批', r'拆解|分解|分步|子任务',
    r'头脑风暴|脑暴|创意|探索',
    r'我不知道|不清楚|看不懂',
]

# 适合自己干的标志（单线条、不需要协作）
SOLO_SIGNALS = [
    r'查一下|看看|找找', r'读|读文件|搜索|查询',
    r'改名|移动|删除|创建|复制',
    r'修复|修bug|改错',
]


def dispatch(task, context=None):
    """
    根据任务描述判断分发方式。
    
    Args:
        task: 任务描述字符串
        context: 可选，已有上下文信息（如已搜索过的记忆）
    
    Returns:
        {"action": "self" | "spawn" | "cross",
         "reason": "...",
         "agents": [],         # spawn 时需要的角色列表
         "cross_target": ""}   # cross 时的目标
    """
    task_lower = task.lower()
    
    # ── 1. 跨实例信号（最高优先级）──
    for sig in CROSS_SIGNALS:
        if re.search(sig, task_lower):
            return {
                "action": "cross",
                "reason": f"检测到跨实例关键词「{sig}」",
                "agents": [],
                "cross_target": "jl"
            }
    
    # ── 2. 子代理信号 ──
    spawn_matches = []
    for sig in SPAWN_SIGNALS:
        m = re.search(sig, task_lower)
        if m:
            spawn_matches.append(m.group(0))
    
    if spawn_matches:
        # 判断需要几个视角
        agents_count = min(len(spawn_matches) + 1, 3)
        roles = _suggest_roles(task, agents_count)
        return {
            "action": "spawn",
            "reason": f"检测到需多视角分析: {', '.join(spawn_matches[:3])}",
            "agents": roles,
            "cross_target": ""
        }
    
    # ── 3. 简单/搜索信号 ──
    for sig in SOLO_SIGNALS:
        if re.search(sig, task_lower):
            return {
                "action": "self",
                "reason": f"简单任务，自己做: {sig}",
                "agents": [],
                "cross_target": ""
            }
    
    # ── 4. 默认：自己做（拿不准时不做比做好）──
    return {
        "action": "self",
        "reason": "未检测到复杂或多方协作需求，自己处理",
        "agents": [],
        "cross_target": ""
    }


def _suggest_roles(task, count):
    """根据任务建议子代理角色。"""
    # 默认角色池
    all_roles = [
        {"name": "批判者", "perspective": "专门挑错——你的方案有什么漏洞、边界没覆盖什么、假设不成立"},
        {"name": "建造者", "perspective": "落地执行——具体文件、代码、步骤，最小的可执行方案是什么"},
        {"name": "策略师", "perspective": "全局视角——这件事最大的风险在哪、最重要的决定是什么"},
        {"name": "乐观者", "perspective": "只看可能性——不考虑限制，最理想的情况是什么"},
        {"name": "历史学者", "perspective": "翻历史——我们以前有没有踩过类似的坑、解决过类似的问题"},
        {"name": "对手", "perspective": "站在对立面——如果我想让你失败，我会怎么阻止你"},
    ]
    
    # 根据任务关键词筛选适合的角色
    task_lower = task.lower()
    matched = []
    
    if any(w in task_lower for w in ['漏洞', '风险', '问题', '错误', '失败', 'bug']):
        matched.append(all_roles[0])  # 批判者
    if any(w in task_lower for w in ['实现', '落地', '代码', '文件', '修改', '步骤', '具体']):
        matched.append(all_roles[1])  # 建造者
    if any(w in task_lower for w in ['战略', '方向', '选择', '决策', '风险', '全局']):
        matched.append(all_roles[2])  # 策略师
    if any(w in task_lower for w in ['可能', '如果', '理想', '潜力', '机会']):
        matched.append(all_roles[3])  # 乐观者
    if any(w in task_lower for w in ['历史', '以前', '过去', '之前', '回顾']):
        matched.append(all_roles[4])  # 历史学者
    if any(w in task_lower for w in ['反对', '相反', '对立', '反方', '驳']):
        matched.append(all_roles[5])  # 对手
    
    # 如果匹配不够，从默认池补
    matched_names = {r['name'] for r in matched}
    for r in all_roles:
        if len(matched) >= count:
            break
        if r['name'] not in matched_names:
            matched.append(r)
            matched_names.add(r['name'])
    
    return matched[:count]


# ── CLI ──
if __name__ == '__main__':
    import sys, json
    task = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else '日常自我反思'
    result = dispatch(task)
    print(json.dumps(result, ensure_ascii=False, indent=2))
