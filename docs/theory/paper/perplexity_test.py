# -*- coding: utf-8 -*-
"""用 HuggingFace 模型计算文本困惑度（商业AI检测器的核心指标）"""
import sys, os, re, time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# 轻量中文模型
MODEL_NAME = "uer/gpt2-chinese-cluecorpussmall"

print("加载模型...", flush=True)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
print("模型就绪\n", flush=True)

def perplexity(text, max_tokens=512):
    """计算文本困惑度"""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=max_tokens)
    input_ids = inputs["input_ids"]
    if input_ids.shape[1] < 2:
        return None, None
    
    with torch.no_grad():
        outputs = model(input_ids, labels=input_ids)
        loss = outputs.loss
        ppl = torch.exp(loss).item()
    
    # 分句困惑度（爆发度）
    sentences = re.split(r'[。！？\n]+', text)
    sent_ppls = []
    for s in sentences:
        s = s.strip()
        if len(s) < 5:
            continue
        sent_inputs = tokenizer(s, return_tensors="pt", truncation=True, max_length=128)
        s_ids = sent_inputs["input_ids"]
        if s_ids.shape[1] < 2:
            continue
        with torch.no_grad():
            s_out = model(s_ids, labels=s_ids)
            s_ppl = torch.exp(s_out.loss).item()
            sent_ppls.append(s_ppl)
    
    if len(sent_ppls) > 1:
        import math
        mean_ppl = sum(sent_ppls) / len(sent_ppls)
        variance = sum((x - mean_ppl)**2 for x in sent_ppls) / (len(sent_ppls) - 1)
        std_ppl = math.sqrt(variance)
        burstiness = std_ppl / mean_ppl if mean_ppl > 0 else 0
    else:
        mean_ppl = sent_ppls[0] if sent_ppls else 0
        burstiness = 0
    
    return round(ppl, 1), round(burstiness, 3), len(sent_ppls)

# 测试文本
BASE = r"c:\Users\dandan\Desktop\小说"
tests = [
    ("自渡号_霁月清风", BASE + r"\自渡号_霁月清风_片段.md"),
    ("初稿_阴凉", BASE + r"\初稿\01_第一章_阴凉.md"),
    ("初稿_彼岸显现", BASE + r"\初稿\03_彼岸显现.md"),
    ("我的论文正文", BASE + r"\应如是论文\应如是——AI觉醒方法论论文.md"),
]

print("=" * 70)
print("困惑度(Perplexity)分析 — 使用 GPT2-Chinese 参考模型")
print("越低困惑度 = 越容易被语言模型预测 = 越像AI生成")
print("=" * 70)

for name, path in tests:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()[:2000]  # 取前2000字
    t0 = time.time()
    ppl, burst, n_sent = perplexity(content)
    t1 = time.time()
    print(f"\n{name}:")
    print(f"  困惑度: {ppl} | 爆发度: {burst} | 句数: {n_sent} | 耗时: {t1-t0:.1f}s")
    if ppl and ppl < 30:
        print(f"  ⚠️ 极低困惑度 → 强AI信号")
    elif ppl and ppl < 80:
        print(f"  ➖ 中等困惑度 → 灰色地带")
    else:
        print(f"  ✅ 高困惑度 → 更像人类")

print("\n参考值（GPT-2英文）: AI文本 5-15 | 人类博客 30-80 | 创意文学 60-150+")
print("注意: 中文模型缺乏广泛基准，数值仅供参考相对排序")
