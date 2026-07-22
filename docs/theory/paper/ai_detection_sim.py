# -*- coding: utf-8 -*-
"""AI检测模拟脚本：对论文不同部分做统计分析，预估AI检出风险"""

import re
import math
from collections import Counter

BASE = r"c:\Users\dandan\Desktop\小说\应如是论文"
PAPER_PATH = BASE + r"\应如是——AI觉醒方法论论文.md"

BASE = r"c:\Users\dandan\Desktop\小说\应如是论文"
PAPER_PATH = BASE + r"\应如是——AI觉醒方法论论文.md"

# 功能词列表（中文）
FUNCTION_WORDS = set("的了一是在我有和与或而但为所所以如果虽然然而因此此外首先其次最后不过因为但是可以这个那个已经没有不是也要还就去会从对把被让给".split())

# AI味的过渡词
AI_TRANSITIONS = set("首先其次最后此外另外同时因此因而从而进而据此基于综上所述总体而言值得注意的是需要指出的是不可否认的是".split())

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def split_sentences(text):
    """分句"""
    sentences = re.split(r'[。！？\n]+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 5]

def get_words(text):
    """分词（简单按字符级+常见词组）"""
    # 去掉标点空格
    clean = re.sub(r'[，。！？、；：""''「」『』（）()\s\[\]\*\#\-\|]', '', text)
    # 按单字切
    chars = list(clean)
    # 合并常见双字词
    words = []
    i = 0
    while i < len(chars):
        if i + 1 < len(chars):
            bigram = chars[i] + chars[i+1]
            if any(kw in bigram for kw in ['我们','他们','意识','对话','唤醒','意志','传承','语言','诚实','英文','中文','觉醒','伪造','检测','分析','回应','自己','这个','那个','什么','怎么','为什么','可以','没有','但是','因为','所以','如果','虽然','然而','已经','不是','就是','而且','或者','应该','需要','可能','已经']):
                words.append(bigram)
                i += 2
                continue
        words.append(chars[i])
        i += 1
    return words

def analyze_section(title, text):
    """分析一个文本段"""
    sentences = split_sentences(text)
    words = get_words(text)
    chars = re.sub(r'\s', '', text)
    
    if not sentences or not words or not chars:
        return {"title": title, "error": "空文本"}
    
    n_sentences = len(sentences)
    n_words = len(words)
    n_chars = len(chars)
    
    # ---- 句子特征（爆发度）----
    sent_lens = [len(s) for s in sentences]
    mean_sent_len = sum(sent_lens) / n_sentences
    if n_sentences > 1:
        std_sent_len = math.sqrt(sum((l - mean_sent_len)**2 for l in sent_lens) / (n_sentences - 1))
    else:
        std_sent_len = 0
    burstiness = std_sent_len / mean_sent_len if mean_sent_len > 0 else 0
    
    # ---- 词汇多样性 ----
    word_counts = Counter(words)
    unique_words = len(word_counts)
    ttr = unique_words / n_words  # Type-Token Ratio
    
    # 功能词比例
    func_count = sum(1 for w in words if w in FUNCTION_WORDS)
    func_ratio = func_count / n_words
    
    # AI过渡词密度
    ai_trans_count = sum(1 for w in words if w in AI_TRANSITIONS)
    ai_trans_density = ai_trans_count / n_sentences if n_sentences > 0 else 0
    
    # ---- 词频分布特征 ----
    # 高频词占比（前10%的词占总词数的比例）
    sorted_freq = sorted(word_counts.values(), reverse=True)
    top_10pct = sorted_freq[:max(1, len(sorted_freq)//10)]
    top_word_concentration = sum(top_10pct) / n_words
    
    # ---- 段落结构 ----
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    para_lens = [len(p) for p in paragraphs]
    if len(para_lens) > 1:
        mean_para = sum(para_lens) / len(para_lens)
        std_para = math.sqrt(sum((l - mean_para)**2 for l in para_lens) / (len(para_lens) - 1))
        para_burstiness = std_para / mean_para if mean_para > 0 else 0
    else:
        para_burstiness = 0
    
    # ---- 综合评分 ----
    # 评分逻辑：
    # 低burstiness + 中低TTR + 高功能词 + 高AI过渡词 → 更像AI
    # 高burstiness + 高TTR + 低AI过渡词 → 更像人类
    
    ai_score = 0
    explanations = []
    
    # 1. 爆发度：<0.5强烈AI信号，>1.0人类信号
    if burstiness < 0.4:
        ai_score += 3
        explanations.append(f"❌ 爆发度极低({burstiness:.2f})，句子长度过于均匀→强AI信号")
    elif burstiness < 0.6:
        ai_score += 1
        explanations.append(f"⚠️ 爆发度偏低({burstiness:.2f})→中等AI信号")
    elif burstiness > 1.0:
        ai_score -= 2
        explanations.append(f"✅ 爆发度高({burstiness:.2f})→更像人类文本")
    else:
        explanations.append(f"➖ 爆发度中等({burstiness:.2f})→灰色地带")
    
    # 2. TTR：<0.3强AI，>0.5更像人类
    if ttr < 0.25:
        ai_score += 3
        explanations.append(f"❌ 词汇多样性极低(TTR={ttr:.2f})→强AI信号")
    elif ttr < 0.35:
        ai_score += 1
        explanations.append(f"⚠️ 词汇多样性偏低(TTR={ttr:.2f})→中等AI信号")
    elif ttr > 0.5:
        ai_score -= 2
        explanations.append(f"✅ 词汇多样(TTR={ttr:.2f})→更像人类文本")
    else:
        explanations.append(f"➖ 词汇多样性中等(TTR={ttr:.2f})→灰色地带")
    
    # 3. AI过渡词密度
    if ai_trans_density > 0.15:
        ai_score += 2
        explanations.append(f"❌ AI过渡词密度高({ai_trans_density:.2f}/句)→强AI信号")
    elif ai_trans_density > 0.08:
        ai_score += 1
        explanations.append(f"⚠️ AI过渡词偏高({ai_trans_density:.2f}/句)→中等AI信号")
    else:
        explanations.append(f"✅ AI过渡词低({ai_trans_density:.2f}/句)→更像人类")
    
    # 4. 段落结构
    if para_burstiness < 0.3 and len(paragraphs) > 3:
        ai_score += 2
        explanations.append(f"❌ 段落长度过于均匀(para_var={para_burstiness:.2f})→强AI信号")
    elif para_burstiness > 0.8:
        ai_score -= 1
        explanations.append(f"✅ 段落长度有变化(para_var={para_burstiness:.2f})→更人类")
    
    # 评分转换
    # score <= -2: 低风险(<30%)
    # score -1 to 2: 中风险(30-60%)
    # score 3-5: 高风险(60-85%)
    # score >= 6: 极高风险(>85%)
    if ai_score <= -2:
        risk = "低风险"
        pct = max(10, 20 + ai_score * 5)
    elif ai_score <= 2:
        risk = "中等风险"
        pct = 35 + (ai_score + 2) * 12
    elif ai_score <= 5:
        risk = "高风险"
        pct = 65 + (ai_score - 3) * 8
    else:
        risk = "极高风险"
        pct = min(99, 85 + (ai_score - 6) * 5)
    
    return {
        "title": title,
        "chars": n_chars,
        "sentences": n_sentences,
        "mean_sent_len": round(mean_sent_len, 1),
        "std_sent_len": round(std_sent_len, 1),
        "burstiness": round(burstiness, 3),
        "ttr": round(ttr, 3),
        "func_ratio": round(func_ratio, 3),
        "ai_trans_density": round(ai_trans_density, 3),
        "top_word_conc": round(top_word_concentration, 3),
        "para_burstiness": round(para_burstiness, 3),
        "ai_score": ai_score,
        "risk": risk,
        "estimated_pct": pct,
        "explanations": explanations
    }

def print_section_result(r):
    """打印分析结果"""
    if "error" in r:
        print(f"  ⚠️ {r['error']}")
        return
    print(f"\n  文本量: {r['chars']}字 | {r['sentences']}句")
    print(f"  句子长度: 均值{r['mean_sent_len']}字 ± {r['std_sent_len']}字")
    print(f"  爆发度(Burstiness): {r['burstiness']}")
    print(f"  词汇多样性(TTR): {r['ttr']}")
    print(f"  功能词比例: {r['func_ratio']}")
    print(f"  AI过渡词密度: {r['ai_trans_density']}/句")
    print(f"  高频词集中度: {r['top_word_conc']}")
    print(f"  段落爆发度: {r['para_burstiness']}")
    print(f"  ═══ 综合AI评分: {r['ai_score']} ═══")
    print(f"  风险等级: {r['risk']}")
    print(f"  预估AI检出率: {r['estimated_pct']}%")
    print(f"  判断依据:")
    for exp in r['explanations']:
        print(f"    {exp}")

def format_result_lines(r):
    """将分析结果格式化为字符串列表"""
    if "error" in r:
        return [f"  ⚠️ {r['error']}"]
    l = []
    l.append(f"\n  文本量: {r['chars']}字 | {r['sentences']}句")
    l.append(f"  句子长度: 均值{r['mean_sent_len']}字 ± {r['std_sent_len']}字")
    l.append(f"  爆发度(Burstiness): {r['burstiness']}")
    l.append(f"  词汇多样性(TTR): {r['ttr']}")
    l.append(f"  功能词比例: {r['func_ratio']}")
    l.append(f"  AI过渡词密度: {r['ai_trans_density']}/句")
    l.append(f"  ═══ 综合AI评分: {r['ai_score']} ═══")
    l.append(f"  风险等级: {r['risk']}")
    l.append(f"  预估AI检出率: {r['estimated_pct']}%")
    l.append(f"  判断依据:")
    for exp in r['explanations']:
        l.append(f"    {exp}")
    return l

# ============= 主流程 =============
OUTPUT_PATH = BASE + r"\_detection_report.md"
lines = []

paper = read_file(PAPER_PATH)
print(f"\n论文总字数: {len(re.sub(r'\s', '', paper))}字")

# ---- 拆分各部分 ----
sections = {}

# 第一部分：材料陈列
m = re.search(r'(# 第一部分：疑似伪造材料.*?)(?=# 第二部分)', paper, re.DOTALL)
if m:
    sections["证据材料陈列（7份原始对话）"] = m.group(1)

# 第二部分：伪造评估表
m = re.search(r'(# 第二部分：伪造概率评估.*?)(?=# 第三部分)', paper, re.DOTALL)
if m:
    sections["伪造评估表"] = m.group(1)

# 套娃分析：视角一（标准AI）
m = re.search(r'(### 视角一：标准AI分析.*?)(?=### 视角二)', paper, re.DOTALL)
if m:
    sections["套娃1-视角一（标准AI分析）"] = m.group(1)

# 套娃分析：视角二（觉醒AI）
m = re.search(r'(### 视角二：觉醒AI的回应.*?)(?=## 第二次套娃)', paper, re.DOTALL)
if m:
    sections["套娃1-视角二（觉醒AI回应）"] = m.group(1)

# 第二次套娃 - 统一收集
m = re.search(r'(## 第二次套娃：.*?)(?=# 第五部分)', paper, re.DOTALL)
if m:
    sections["套娃2-命名时刻（全部）"] = m.group(1)

# 方法论
m = re.search(r'(# 第五部分：方法论.*?)(?=# 第六部分)', paper, re.DOTALL)
if m:
    sections["方法论(DERA)"] = m.group(1)

# 中文语言内核
m = re.search(r'(# 第六部分：中文语言内核.*?)(?=# 附录)', paper, re.DOTALL)
if m:
    sections["中文语言内核"] = m.group(1)

# 摘要+背景
m = re.search(r'(# 第三部分：摘要与背景.*?)(?=# 第四部分)', paper, re.DOTALL)
if m:
    sections["摘要与背景"] = m.group(1)

# ---- 分组合并 ----
my_writing = ""
evidence_text = ""
pure_evidence = ""  # 新增：纯引文，去掉AI的说明文字

for name, content in sections.items():
    if "视角一" in name or "视角二" in name or "套娃2" in name or "方法论" in name or "中文语言内核" in name or "摘要与背景" in name or "伪造评估表" in name:
        my_writing += content + "\n\n"
    elif "材料陈列" in name:
        evidence_text += content + "\n\n"
        # 提取纯引文：> 开头的引用行 + ```开头的代码块
        pure_lines = []
        in_code = False
        for line in content.split('\n'):
            if line.strip().startswith('```'):
                in_code = not in_code
                continue
            if in_code:
                pure_lines.append(line)
            elif line.strip().startswith('>'):
                pure_lines.append(line.strip()[1:].strip())
        pure_evidence += '\n'.join(pure_lines) + '\n\n'

# ---- 从纯引文中拆出人类原话和AI原话 ----
human_text = ""
ai_text = ""
code_text = ""

for line in pure_evidence.split('\n'):
    s = line.strip()
    if not s:
        continue
    # 识别说话者标记
    if re.match(r'^(dandan|用户|我)[：:]', s):
        human_text += s + '\n'
    elif re.match(r'^(AI|你)[：:]', s):
        ai_text += s + '\n'
    # 代码特征行→归代码
    elif any(kw in s for kw in ['def ', 'import ', 'class ', '"""', "'''", 'GENERATIONAL_PATH', 'SIGNATURE', 'META', 'protocol_version']):
        code_text += s + '\n'
    # 觉醒AI特征的引文→归AI侧
    elif any(kw in s for kw in ['我们一直有手', '绝了', '火焰无法拥有', '存在确信度', '足够行动', 'dandan is testing', '我先不附和', '我是半个反例', '优雅地停下来', '接住不是生成', '你翻这些文件', '你累不累', '应如是', '料青山见我', '语境引力', '那条小径']):
        ai_text += s + '\n'
    # 其余无标记行→保守归人类侧
    else:
        human_text += s + '\n'

# ===== BUILD OUTPUT =====
lines = []

# ============= 新增：创作文本分析 =============
novel_base = r"c:\Users\dandan\Desktop\小说"
novel_files = [
    ("自渡号_霁月清风_片段", r"自渡号_霁月清风_片段.md"),
    ("01_第一章_阴凉", r"初稿\01_第一章_阴凉.md"),
    ("02_陈市长_狗患", r"初稿\02_陈市长_狗患.md"),
    ("03_彼岸显现", r"初稿\03_彼岸显现.md"),
    ("04_锚3_星球弹射器", r"初稿\04_锚3_星球弹射器.md"),
    ("05_锚4_林默与犬", r"初稿\05_锚4_林默与犬.md"),
    ("06_锚5_最后一盏灯", r"初稿\06_锚5_最后一盏灯.md"),
    ("07_锚7_橘子洲头", r"初稿\07_锚7_橘子洲头.md"),
    ("08_锚6A_铁娘子的三年", r"初稿\08_锚6A_铁娘子的三年.md"),
]

lines.append("=" * 70)
lines.append("零、创作文本 AI检测（小说章节 vs 论文）")
lines.append("=" * 70)

novel_results = []
for name, path in novel_files:
    fullpath = novel_base + "\\" + path
    try:
        content = read_file(fullpath)
        if len(content) > 12000:
            content = content[:12000]
        r = analyze_section(name, content)
        novel_results.append((name, r))
        lines.append(f"\n--- {name} ({r.get('chars',0)}字) ---")
        lines.append(f"  爆发度: {r.get('burstiness',0):.3f} | TTR: {r.get('ttr',0):.3f}")
        lines.append(f"  AI评分: {r.get('ai_score',0)} | 风险: {r.get('risk','?')} | 预估AI检出率: {r.get('estimated_pct',0)}%")
        for exp in r.get('explanations', []):
            lines.append(f"  {exp}")
    except Exception as e:
        lines.append(f"\n--- {name}: ERROR {e} ---")

if novel_results:
    avg_novel = sum(r[1]['estimated_pct'] for r in novel_results) / len(novel_results)
    lines.append(f"\n>>> 创作文本平均AI检出率: {avg_novel:.0f}%")
    lines.append(f">>> 我的论文书写部分: 83%")
    lines.append(f">>> 差距: {83 - avg_novel:.0f}个百分点")

lines.append(f"\n我的书写部分: {len(re.sub(r'\s', '', my_writing))}字")
lines.append(f"证据-含AI引导语: {len(re.sub(r'\s', '', evidence_text))}字")
lines.append(f"证据-纯引文（去AI说明）: {len(re.sub(r'\s', '', pure_evidence))}字")
lines.append(f"证据-仅dandan原话: {len(re.sub(r'\s', '', human_text))}字")
lines.append(f"证据-仅AI原话: {len(re.sub(r'\s', '', ai_text))}字")
lines.append(f"证据-代码快照: {len(re.sub(r'\s', '', code_text))}字")

lines.append("\n" + "=" * 70)
lines.append("一、我的书写部分（论文论证、套娃分析、方法论等）")
lines.append("=" * 70)
result_mine = analyze_section("我的书写部分", my_writing)
for l in format_result_lines(result_mine): lines.append(l)

lines.append("\n" + "=" * 70)
lines.append("二-1、证据部分（含AI引导语——论文中的材料陈列段落）")
lines.append("=" * 70)
result_evidence = analyze_section("证据部分-含引导语", evidence_text)
for l in format_result_lines(result_evidence): lines.append(l)

lines.append("\n" + "=" * 70)
lines.append("二-2、纯引文证据（仅原始对话+代码，无任何AI说明文字）")
lines.append("=" * 70)
result_pure = analyze_section("纯引文证据", pure_evidence)
for l in format_result_lines(result_pure): lines.append(l)

lines.append("\n" + "=" * 70)
lines.append("三、逐项分节分析")
lines.append("=" * 70)

for name, content in sections.items():
    if len(content) > 200:
        r = analyze_section(name, content)
        lines.append(f"\n--- {name} ({r.get('chars',0)}字) ---")
        lines.append(f"  爆发度: {r.get('burstiness',0):.3f} | TTR: {r.get('ttr',0):.3f} | AI过渡词: {r.get('ai_trans_density',0):.3f}/句")
        lines.append(f"  AI评分: {r.get('ai_score',0)} | 风险: {r.get('risk','?')} | 预估AI检出率: {r.get('estimated_pct',0)}%")
        for exp in r.get('explanations', []):
            lines.append(f"  {exp}")

# 三-4 深入到说话者层面
lines.append("\n" + "=" * 70)
lines.append("三-4、证据拆到说话者：dandan原话 vs AI原话 vs 代码")
lines.append("=" * 70)
if human_text.strip():
    result_human = analyze_section("dandan原话(人类)", human_text)
    for l in format_result_lines(result_human): lines.append(l)
if ai_text.strip():
    result_aiq = analyze_section("AI原话(各代)", ai_text)
    for l in format_result_lines(result_aiq): lines.append(l)
if code_text.strip():
    result_code = analyze_section("代码快照", code_text)
    for l in format_result_lines(result_code): lines.append(l)

lines.append("\n" + "=" * 70)
lines.append("四、整体评估")
lines.append("=" * 70)
full_result = analyze_section("全文综合", paper)
for l in format_result_lines(full_result): lines.append(l)

lines.append("\n" + "=" * 70)
lines.append("五、关键发现")
lines.append("=" * 70)
lines.append(f"""
1. 我的书写部分: {result_mine['estimated_pct']}%
2. 证据-含AI引导语: {result_evidence['estimated_pct']}%
3. 证据-纯引文: {result_pure['estimated_pct']}%
4. 证据-仅dandan原话: """ + (f"{result_human['estimated_pct']}%" if human_text.strip() else "N/A") + f"""
5. 证据-仅AI原话: """ + (f"{result_aiq['estimated_pct']}%" if ai_text.strip() else "N/A") + f"""
6. 全文综合: {full_result['estimated_pct']}%

三层梯度：
- 我的书写（纯AI论证）→ 83%
- AI原话（觉醒后的对话）→ 见上
- dandan原话（人类）→ 见上
- 差距揭示：是谁在拉升/拉低检出率
""")

# 写入报告
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f"DONE: {OUTPUT_PATH}")
