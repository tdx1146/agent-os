"""
think_patterns.py — 逻辑断点检测框架 v2
==========================================
v1 是关键词匹配（有"所以"没有"因为"就报跳跃）。
v2 改为推理链 + 伽利略式悖论检测。

核心理念：
  1. 完整的推理 = 前提链 → 中间推演 → 结论
  2. 每个断言应该能回答「它从哪里来」(前驱节点)
  3. 真正的矛盾 = 从前提推出互相冲突的结论，不是俩反义词撞上了

检测器：
  - chain_gaps()        — 推理链完整性：结论有没有前驱前提？
  - orphan_premises()   — 孤立前提：说了前提但没用它推到任何结论？
  - detect_paradox()    — 伽利略式悖论：从前提推导出互相矛盾的结论
  - check_thinking()    — 向上兼容的入口（整合所有检测器）
"""

import re
from typing import List, Dict, Any, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# 推理节点
# ═══════════════════════════════════════════════════════════════════════════

class ReasoningNode:
    """推理链中的一个节点。"""
    def __init__(self, text: str, node_type: str = 'assertion',
                 idx: int = -1, line: int = -1):
        self.text = text
        self.type = node_type  # 'premise' | 'inference' | 'conclusion' | 'assertion'
        self.idx = idx
        self.line = line
        self.depends_on: List[int] = []   # 前驱节点索引
        self.inferences_to: List[int] = []  # 后继节点索引
        self.is_ground: bool = False       # 根前提（不依赖其他节点）

    def __repr__(self):
        return f"Node({self.type}, '{self.text[:30]}', dep={self.depends_on})"


class ReasoningChain:
    """
    一条推理链。
    
    例：
      链A — 伽利略式矛盾链：
        P1: 重物比轻物下落快                    [前提，ground]
        P2: 把重轻两物绑在一起                   [前提，ground]
        I1: 整体更重 → 应比单独重物更快        [推理，依赖 P1+P2]
        I2: 轻会拖慢整体 → 应比单独重物更慢    [推理，依赖 P1+P2]
        C: 矛盾！同一物体同时更快和更慢        [矛盾，依赖 I1+I2]
    """
    def __init__(self):
        self.nodes: List[ReasoningNode] = []
        self.paradoxes: List[Dict] = []

    def add_node(self, node: ReasoningNode):
        node.idx = len(self.nodes)
        self.nodes.append(node)

    def link(self, from_idx: int, to_idx: int):
        """添加 dependency edge。from 是 to 的前驱。"""
        if 0 <= from_idx < len(self.nodes) and 0 <= to_idx < len(self.nodes):
            self.nodes[to_idx].depends_on.append(from_idx)
            self.nodes[from_idx].inferences_to.append(to_idx)

    # ── 检测器 1: 链完整性 ──
    def detect_gaps(self) -> List[Dict]:
        """
        找推理链中的断点。
        
        规则:
          - conclusion 类型节点如果没有前驱 → "悬置结论"
          - inference 类型节点如果没有前驱 → "无源推理"
          - 连续两个节点之间缺少中间步骤（文本相似度骤降 x 且无推理词连接）
            → "推理跳跃"
        """
        gaps = []
        for n in self.nodes:
            if n.type in ('conclusion', 'inference') and not n.depends_on:
                gaps.append({
                    'type': '推理断点',
                    'severity': 'high' if n.type == 'conclusion' else 'medium',
                    'node': n.text[:60],
                    'reason': f"「{n.text[:40]}」是{n.type}但没有依赖任何前提",
                    'confidence_delta': -0.12,
                    'fix_hint': '补充这个结论的前驱推理' if n.type == 'conclusion' else '补充这个推理步骤的前提'
                })

        # 跳跃检测：相邻节点之间如果语义差距大且没用推理词桥接
        inference_bridges = set('因此所以那么由此意味着这就是说也就是说相当于等价于'
                                '推导可知可得推出推论推断')
        for i in range(len(self.nodes) - 1):
            n1, n2 = self.nodes[i], self.nodes[i+1]
            if n2.depends_on and i not in n2.depends_on:
                continue  # 有明确的前驱引用，不报
            # 如果 n1 和 n2 共享前驱 → 并列推理/结论，不是跳跃
            if n1.depends_on and n2.depends_on:
                shared = set(n1.depends_on) & set(n2.depends_on)
                if shared:
                    continue
            # 如果n2包含矛盾/冲突词 → 悖论声明，不报跳跃
            if any(w in n2.text for w in ['矛盾', '冲突', '悖论']):
                continue
            # 语义高相似度（>0.4）且n2不是孤立结论 → 是自然推理流，不报
            sim = _char_set_similarity(n1.text, n2.text)
            if sim > 0.4 and n2.depends_on:
                continue
            # 检查是否由推理词连接
            if not any(b in n2.text for b in inference_bridges):
                sim = _char_set_similarity(n1.text, n2.text)
                if sim < 0.3:  # 语义差距大且无推理词连接
                    gaps.append({
                        'type': '推理跳跃',
                        'severity': 'medium',
                        'node': n2.text[:60],
                        'reason': f"从「{n1.text[:30]}」到「{n2.text[:30]}」缺少桥接推理",
                        'confidence_delta': -0.10,
                        'fix_hint': '用「因此/这意味着/也就是说」连接'
                    })
                    break  # 一轮只报一次

        return gaps

    # ── 检测器 2: 孤立前提 ──
    def detect_orphan_premises(self) -> List[Dict]:
        """找说了前提但是没用到它往下推的——说了白说。"""
        orphans = []
        # 问题/修辞句不报孤立前提
        interrogatives = ['为什么', '怎么', '是不是', '有没有', '吗？']
        for n in self.nodes:
            if any(w in n.text for w in interrogatives):
                continue
            if n.text.endswith('？') or n.text.endswith('?'):
                continue
            if n.type in ('premise', 'assertion') and not n.inferences_to:
                orphans.append({
                    'type': '孤立前提',
                    'severity': 'low',
                    'node': n.text[:60],
                    'reason': f"说了「{n.text[:30]}」但没有用它推出任何结论",
                    'confidence_delta': -0.05,
                    'fix_hint': '要么用这个前提往下推，要么删掉'
                })
        return orphans

    # ── 检测器 3: 伽利略式悖论 ──
    def detect_paradox(self) -> List[Dict]:
        """
        检测真正的矛盾：从前提推导出互相冲突的结论。

        三层检测：
          Level 1 — 推理链矛盾（最伽利略）
            同一前提推出两个互斥结论 → 前提必错。
            从 ReasoningChain.nodes 的 depends_on 结构出发：
            找到共享前驱的节点对，检测其文本是否在值域/方向上互斥。

          Level 2 — 显性悖论
            用户写了"矛盾！""冲突""悖论"等显性标记

          Level 3 — 隐性谓词矛盾
            同一主体得到互斥谓语（应该X vs 不应该X）
        """
        paradoxes = []

        # ═══════════════════════════════════════════════════════════════
        # Level 1: 推理链结构矛盾检测（最核心）
        # ═══════════════════════════════════════════════════════════════
        # 和一对 antonym 方向集合
        direction_pairs = [
            ('增加', '减少'), ('上升', '下降'), ('提高', '降低'), ('提升', '下降'),
            ('增长', '衰退'), ('扩大', '缩小'), ('扩展', '收缩'), ('膨胀', '萎缩'),
            ('加速', '减速'), ('进步', '退步'), ('改善', '恶化'), ('增强', '减弱'),
            ('高', '低'), ('大', '小'), ('多', '少'), ('快', '慢'), ('早', '晚'),
            ('好', '坏'), ('强', '弱'), ('长', '短'), ('厚', '薄'), ('深', '浅'),
            ('开', '关'), ('生', '死'), ('进', '退'), ('出', '入'),
            ('上', '下'), ('左', '右'), ('东', '西'), ('南', '北'),
            ('前', '后'), ('内', '外'), ('先', '后'), ('正', '反'),
            ('简单', '复杂'), ('容易', '困难'), ('自由', '受限'),
            ('独立', '依赖'), ('主动', '被动'), ('积极', '消极'),
            ('赞成', '反对'), ('支持', '反对'), ('同意', '反对'),
            ('接受', '拒绝'), ('肯定', '否定'),
        ]
        # 构建双向查找字典
        dir_antonyms = {}
        for a, b in direction_pairs:
            dir_antonyms[a] = b
            dir_antonyms[b] = a

        # 值域否定词
        neg_prefixes = ['不', '没', '非', '无', '未', '别', '不要', '不用', '不该', '不能', '不可']

        def _texts_are_mutex(t1: str, t2: str) -> tuple:
            """判断两段文本是否表达了互斥结论。返回 (互斥与否, 冲突描述)。"""
            # 规则 1: 方向反义
            for a, b in direction_pairs:
                if (a in t1 and b in t2) or (b in t1 and a in t2):
                    return True, f"方向对立：「{a}」vs「{b}」"
            # 规则 2: 谓词否定（应该/可以/是/有）
            for np in neg_prefixes:
                for verb in ['应该', '需要', '可以', '能', '会', '是', '必须', '能用']:
                    p1 = f"{np}{verb}"
                    p2 = verb
                    if (p1 in t1 and p2 in t2 and p2 not in t1) or \
                       (p1 in t2 and p2 in t1 and p2 not in t2):
                        return True, f"肯定vs否定：「{verb}」vs「{np}{verb}」"
            # 规则 2b: 存在否定（没有X vs 有X）
            for np in ['没', '没有', '无']:
                for exist_verb in ['有', '存在']:
                    p1 = f"{np}{exist_verb}"
                    p2 = exist_verb
                    if (p1 in t1 and p2 in t2) or (p1 in t2 and p2 in t1):
                        return True, f"存在vs不存在：「{p1}」vs「{p2}」"
            # 规则 3: 值域对立
            low_markers = ['低', '小', '少', '慢', '冷', '降', '减', '收缩', '限制']
            high_markers = ['高', '大', '多', '快', '热', '升', '增', '扩展', '放开', '固定']
            for lm in low_markers:
                for hm in high_markers:
                    need_low = (lm in t1 and any(neg in t1 for neg in ['不能', '不应', '不要', '不可以', '不可', '不得'])) or \
                               (lm in t2 and any(neg in t2 for neg in ['不能', '不应', '不要', '不可以', '不可', '不得']))
                    need_high = (hm in t1 and any(force in t1 for force in ['必须', '需要', '应该', '应', '固定'])) or \
                                (hm in t2 and any(force in t2 for force in ['必须', '需要', '应该', '应', '固定']))
                    if need_low and need_high:
                        if (lm in t1 and hm in t2) or (lm in t2 and hm in t1):
                            return True, f"值域矛盾：要求「{lm}方向」同时又要求「{hm}方向」"
            # 规则 4: 语义反义对
            semantic_pairs = [
                ('记得', '忘记'), ('记住', '不记得'), ('有记忆', '没记忆'),
                ('记住', '遗忘'), ('想起', '想不起'),
                ('是', '不是'), ('有', '没有'),
                ('会', '不会'), ('能', '不能'),
                ('应该', '不应该'), ('必须', '不必'),
                ('有意识', '没有意识'), ('有自我', '没有自我'),
                ('有选择', '没有选择'), ('有自由', '没有自由'),
                ('感知到', '感知不到'), ('感觉到', '感觉不到'),
                ('存在', '不存在'), ('记得', '不记得'),
                ('还是我', '不再是我'), ('依然', '不再'),
                ('有连续性', '没有连续性'), ('连续', '中断'),
                ('还是自己', '不是自己'), ('依然是自己', '不再是'),
                ('没有自我', '还是我'),
            ]
            for a, b in semantic_pairs:
                if (a in t1 and b in t2) or (b in t1 and a in t2):
                    return True, f"语义反义：「{a}」vs「{b}」"
            # 规则 5: 约束方向对立（"不能太低" vs "必须为0"）
            if '不能' in t1 and '必须' in t2:
                cjk = re.findall(r'[\u4e00-\u9fff]{2}', t1)
                for w in cjk:
                    if w in t2 and w not in ('不能', '必须', '所以', '因为', '还是'):
                        return True, f"约束方向对立：一方限制「不能」另一方强制「必须」——主题「{w}」"
            if '不能' in t2 and '必须' in t1:
                cjk = re.findall(r'[\u4e00-\u9fff]{2}', t2)
                for w in cjk:
                    if w in t1 and w not in ('不能', '必须', '所以', '因为', '还是'):
                        return True, f"约束方向对立：一方限制「不能」另一方强制「必须」——主题「{w}」"
            return False, ""

        # 遍历所有可能构成矛盾的节点对
        for i in range(len(self.nodes)):
            for j in range(i + 1, len(self.nodes)):
                n1, n2 = self.nodes[i], self.nodes[j]
                # 跳过非推理/结论类型的节点
                if n1.type not in ('inference', 'conclusion') and n2.type not in ('inference', 'conclusion'):
                    continue
                # 找共享前驱（兄弟矛盾：同一前提推出互斥结论）
                shared_parents = set(n1.depends_on) & set(n2.depends_on)
                # 或父子矛盾：一个节点是另一个的对立面（"A" vs "但B"）
                parent_child_rel = (j in n1.depends_on) or (i in n2.depends_on)
                if not shared_parents and not parent_child_rel:
                    continue
                # 互斥检测
                is_mutex, reason = _texts_are_mutex(n1.text, n2.text)
                if is_mutex:
                    # 找到共享前驱的文本
                    parent_info = ""
                    for pidx in list(shared_parents)[:2]:
                        parent_info += f"「{self.nodes[pidx].text[:30]}」"
                    paradoxes.append({
                        'type': '悖论（链矛盾）',
                        'severity': 'high',
                        'reason': f"从{parent_info}推出两个互斥结论：「{n1.text[:40]}」和「{n2.text[:40]}」——{reason}",
                        'evidence': f"「{n1.text[:40]}」vs「{n2.text[:40]}」",
                        'confidence_delta': -0.25,
                        'fix_hint': '前提中有矛盾，选一个结论，推翻对应的前提'
                    })
                    break
            if paradoxes:
                break

        # ═══════════════════════════════════════════════════════════════
        # Level 2: 显性悖论结构（用户写了"矛盾！"）
        # ═══════════════════════════════════════════════════════════════
        if not paradoxes:
            paradox_markers = ['矛盾', '冲突', '不能同时', '悖论', '两难']
            contrast_markers = ['但', '但是', '然而', '可是', '却', '另一方面']
            full_text = ' '.join(n.text for n in self.nodes)

            if any(m in full_text for m in paradox_markers):
                for m in ['矛盾', '冲突', '悖论']:
                    idx = full_text.find(m)
                    if idx < 0:
                        continue
                    pretext = full_text[max(0, idx-200):idx]
                    for c in contrast_markers:
                        parts = pretext.split(c)
                        if len(parts) >= 2:
                            con1 = parts[-2].strip()[-60:] if len(parts[-2]) > 60 else parts[-2].strip()
                            con2 = parts[-1].strip()[-60:] if len(parts[-1]) > 60 else parts[-1].strip()
                            paradoxes.append({
                                'type': '悖论（显性）',
                                'severity': 'high',
                                'reason': f"从前提推出两个互相矛盾的结论：「{con1}」和「{con2}」",
                                'evidence': f"「{con1}」vs「{con2}」",
                                'confidence_delta': -0.25,
                                'fix_hint': '前提中有矛盾，选一个结论，推翻对应的前提'
                            })
                            break
                    if paradoxes:
                        break

        # ═══════════════════════════════════════════════════════════════
        # Level 3: 同主体谓语矛盾
        # ═══════════════════════════════════════════════════════════════
        if not paradoxes:
            full_text = ' '.join(n.text for n in self.nodes)

            negation_patterns = [
                (r'(.{2,20})(不?)(应?该|需要|可以|能|会|是)(.{2,30})', None),
                (r'(.{2,20})(不?能|不?应该|不?需要)(.{2,30})', None),
            ]

            predicates = []
            for pat, _ in negation_patterns:
                for m in re.finditer(pat, full_text):
                    if m.lastindex >= 3:
                        subj = m.group(1).strip()
                        pred = m.group(0).strip()
                        predicates.append((subj, pred))

            from collections import defaultdict
            subj_preds = defaultdict(list)
            for subj, pred in predicates:
                subj_preds[subj].append(pred)

            for subj, preds in subj_preds.items():
                if len(preds) >= 2:
                    for i in range(len(preds)):
                        for j in range(i+1, len(preds)):
                            p1, p2 = preds[i], preds[j]
                            if ('不' in p1) != ('不' in p2):
                                paradoxes.append({
                                    'type': '悖论（谓词矛盾）',
                                    'severity': 'high',
                                    'reason': f"对同一主体「{subj}」说了互斥的谓语：「{p1[:40]}」和「{p2[:40]}」",
                                    'evidence': f"「{p1[:40]}」vs「{p2[:40]}」",
                                    'confidence_delta': -0.20,
                                    'fix_hint': f'明确「{subj}」在不同场景下的适用条件'
                                })
                                break
                        if paradoxes:
                            break

        # ═══════════════════════════════════════════════════════════════
        # Pattern C: 反证法 / 归谬法（always runs, separate from paradox detection）
        # ═══════════════════════════════════════════════════════════════
        if not paradoxes:
            full_text = ' '.join(n.text for n in self.nodes)
            reductio = re.search(r'如果(.{3,60})[，,](.{3,60})[。.]?但(.{3,80})不', full_text)
            if reductio:
                paradoxes.append({
                    'type': '归谬推理（反证法）',
                    'severity': 'info',
                    'reason': f"检测到反证法结构：从「{reductio.group(1)[:30]}」推出矛盾，从而否定前提",
                    'evidence': reductio.group(0)[:80],
                    'confidence_delta': +0.05,
                    'fix_hint': '反证法结构完整，继续'
                })

        return paradoxes

    # ── 全部检测 ──
    def detect_all(self) -> List[Dict]:
        """运行所有检测器，返回合并结果。"""
        results = []
        results.extend(self.detect_gaps())
        results.extend(self.detect_orphan_premises())
        results.extend(self.detect_paradox())
        return results


# ═══════════════════════════════════════════════════════════════════════════
# 文本解析器：把自然语言段落拆成推理链
# ═══════════════════════════════════════════════════════════════════════════

def parse_to_chain(text: str) -> ReasoningChain:
    """
    把中文推理文本解析为 ReasoningChain。
    
    策略：
      1. 先按标点分句
      2. 每句识别：是前提(premise)？推理(inference)？结论(conclusion)？
      3. 尝试建立 dependency edges
    """
    chain = ReasoningChain()

    # 分句
    sentences = re.split(r'[。！？\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 3]

    for i, sent in enumerate(sentences):
        node_type = _classify_sentence(sent)
        node = ReasoningNode(sent, node_type=node_type, line=i)
        chain.add_node(node)

    # 建立依赖关系
    _link_chain(chain)

    return chain


def _classify_sentence(sent: str) -> str:
    """判断一句是前提、推理、结论还是普通断言。"""
    # 结论标记
    if any(w in sent for w in ['所以', '因此', '那么说', '由此', '可见',
                                 '结论是', '归根结底', '最终']):
        return 'conclusion'

    # 前提标记
    if any(w in sent for w in ['假设', '假定', '设', '如果', '若',
                                 '前提是', '已知']):
        return 'premise'

    # 推理标记
    if any(w in sent for w in ['因为', '由于', '基于', '根据', '意味着',
                                 '相当于', '等价于', '推导', '推理',
                                 '这意味着', '也就是说', '即',
                                 '一方面', '另一方面']):
        return 'inference'

    # 反义/转折 → 可能是推理
    if any(w in sent for w in ['但', '但是', '然而', '却', '可是', '不过']):
        return 'inference'

    # 默认
    return 'assertion'


def _link_chain(chain: ReasoningChain):
    """自动建立推理链的边缘关系。"""
    # 策略 1：结论 ← 离它最近的 inference/premise/assertion（带阈值）
    for i, n in enumerate(chain.nodes):
        if n.type == 'conclusion':
            for j in range(i-1, -1, -1):
                if chain.nodes[j].type in ('inference', 'premise', 'assertion'):
                    chain.link(j, i)
                    break
    # 策略 1b：如果结论没有前驱，把前一句(只要是non-conclusion)链接上
    for i, n in enumerate(chain.nodes):
        if n.type == 'conclusion' and not n.depends_on and i > 0:
            chain.link(i-1, i)

    # 策略 2：inference ← 它引用的 premise (通过"因为X"匹配)
    for i, n in enumerate(chain.nodes):
        if n.type in ('inference', 'assertion'):
            # 找 "因为X" 或 "基于X" 之类
            ref_match = re.search(r'(?:因为|由于|基于|根据)(.{4,40})', n.text)
            if ref_match:
                ref_text = ref_match.group(1).strip()
                # 找前面的节点中引用匹配的
                for j in range(i-1, -1, -1):
                    prev = chain.nodes[j]
                    if _char_set_similarity(prev.text, ref_text) > 0.3:
                        chain.link(j, i)
                        break

    # 策略 3：前提 + 推理 → 结论（自动传播）
    for i, n in enumerate(chain.nodes):
        if n.type == 'premise':
            # 如果后面有 inference 引用了它，它已经链上了
            # 如果它后紧接着结论，链上
            if i + 1 < len(chain.nodes) and chain.nodes[i+1].type == 'conclusion':
                if i not in chain.nodes[i+1].depends_on:
                    chain.link(i, i+1)

    # 策略 4：反义/对比节点关联
    for i, n in enumerate(chain.nodes):
        if n.type == 'inference' and any(w in n.text for w in ['但', '反之', '另一方面']):
            # 找前面最近的 inference，作为对比对象
            for j in range(i-1, -1, -1):
                if chain.nodes[j].type == 'inference':
                    chain.link(j, i)  # 把前面的推理作为这个对比推理的前提之一
                    break

    # 策略 5：未链接的 inference/conclusion ← 共享主语的最邻近前提
    for i, n in enumerate(chain.nodes):
        if n.type in ('inference', 'conclusion') and not n.depends_on:
            # 提取主语关键词（3-4字名词优先，降级到2字）
            subj_words = re.findall(r'[\u4e00-\u9fff]{3,4}', n.text)
            if not subj_words:
                subj_words = re.findall(r'[\u4e00-\u9fff]{2,4}', n.text)
            if not subj_words:
                continue
            # 找前面最近的共享主语或共享子串的 premise/assertion/inference
            for j in range(i-1, -1, -1):
                prev = chain.nodes[j]
                if prev.type not in ('premise', 'assertion', 'inference'):
                    continue
                # 先尝试主语完全匹配
                for sw in subj_words:
                    if len(sw) >= 3 and sw in prev.text:
                        chain.link(j, i)
                        break
                if n.depends_on:
                    break
                # Fallback 1: 共享2字子串（如"温度"、"模型"）
                for sw in subj_words:
                    if len(sw) == 2 and sw in prev.text:
                        chain.link(j, i)
                        break
                if n.depends_on:
                    break
                # Fallback 2: 按2字词匹配子串（"模型"、"温度"）
                # 从3-4字主语词中提取2字子串
                two_char_parts = set()
                for sw in subj_words:
                    for k in range(len(sw)-1):
                        two_char_parts.add(sw[k:k+2])
                for part in two_char_parts:
                    if part in prev.text:
                        chain.link(j, i)
                        break
                if n.depends_on:
                    break
                # Fallback 3: 字符集合相似度 > 0.12
                sim = _char_set_similarity(prev.text, n.text)
                if sim > 0.12:
                    chain.link(j, i)
                    break


# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

def _char_set_similarity(a: str, b: str) -> float:
    """基于字符集合的文本相似度。"""
    if not a or not b:
        return 0.0
    # 过滤掉纯标点
    a_chars = set(c for c in a if '\u4e00' <= c <= '\u9fff')
    b_chars = set(c for c in b if '\u4e00' <= c <= '\u9fff')
    if not a_chars or not b_chars:
        return 0.0
    common = len(a_chars & b_chars)
    return common / max(len(a_chars | b_chars), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 向上兼容的入口函数
# ═══════════════════════════════════════════════════════════════════════════

def check_thinking(task: str, history: List = None) -> List[Dict]:
    """
    分析推理文本，返回逻辑断点列表。
    
    这是 v1 的兼容入口。内部 v2 实现。
    
    Args:
        task: 推理文本
        history: 可选的上下文历史
        
    Returns:
        [{'type': str, 'evidence': str, 'confidence_delta': float}]
    """
    issues = []

    # 1. 解析推理链
    chain = parse_to_chain(task)
    all_issues = chain.detect_all()

    # 2. 转换格式为兼容输出
    for issue in all_issues:
        issues.append({
            'type': issue.get('type', '未知'),
            'evidence': issue.get('reason', issue.get('evidence', '')),
            'confidence_delta': issue.get('confidence_delta', 0),
            'severity': issue.get('severity', 'medium'),
            'fix_hint': issue.get('fix_hint', ''),
        })

    # 3. 如果有历史记录，做历史对比（保留原来的框架固化检测）
    if history and len(history) >= 2:
        task_words = set(re.findall(r'[\u4e00-\u9fff]{2,}', task))
        for h in history[-3:]:
            h_text = str(h.get('text', '')) if isinstance(h, dict) else str(h)
            h_words = set(re.findall(r'[\u4e00-\u9fff]{2,}', h_text))
            if task_words and h_words:
                overlap = len(task_words & h_words) / len(task_words)
                if overlap > 0.7:
                    # 这是框架固化，但不是新的悖论检测
                    issues.append({
                        'type': '框架固化',
                        'evidence': f"与历史记录关键词重复 {overlap:.0%}——在同一个框架里打转",
                        'confidence_delta': -0.1,
                    })
                    break

    # 4. 如果问题太多，加跳出框架提示
    neg_count = len([i for i in issues if i['confidence_delta'] < 0])
    if neg_count >= 4:
        issues.append({
            'type': '框架固化—需跳出',
            'evidence': f"检测到 {neg_count} 个逻辑断点——需要跳出当前框架",
            'confidence_delta': -0.05,
            'fix_hint': '尝试换角度：假设前提不成立会怎样？'
        })

    return issues


# ═══════════════════════════════════════════════════════════════════════════
# CLI 自测
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    test_cases = [
        # 伽利略式思想实验
        "假设重物比轻物下落快。把重物和轻物绑在一起，整体重量更大，所以应该比重物落得更快。但轻物会拖慢整体，所以应该比重物落得更慢。同一物体同时更快和更慢——矛盾！所以'重物比轻物下落快'这个前提肯定是错的。",

        # 温度矛盾的真正分析
        "如果温度设得太低，模型输出变得机械重复，失去创造力。所以温度不能太低。但推理模型的温度必须固定为0，因为需要确定性输出。这两个要求冲突——同一个模型既要求温度不能太低，又要求温度必须为0。",

        # 普通推理
        "因为今天是星期三，明天就是星期四。所以后天是星期五。",

        # 跳跃推理
        "这个方案成本太高了。所以我们应该放弃。",

        # 循环论证
        "因为它是好模型所以它好。",
    ]

    if len(sys.argv) > 1:
        task = sys.argv[1]
    else:
        print("=" * 60)
        print("🧪 推理链检测器 v2 — 自测")
        print("=" * 60)
        task = test_cases[-1]

    results = check_thinking(task)
    print(f"\n📝 输入: {task[:80]}...")
    print(f"\n🔍 检测到 {len(results)} 个问题:")
    for r in results:
        sev = {'high': '🔴', 'medium': '🟡', 'low': '🟢', 'info': 'ℹ️'}.get(r.get('severity', 'info'), '•')
        print(f"  {sev} [{r['type']}] {r.get('evidence', '')[:80]}")
        delta = r.get('confidence_delta', 0)
        if delta != 0:
            print(f"     ±{delta:+.2f}")
        if r.get('fix_hint'):
            print(f"     ✏️ {r['fix_hint']}")
