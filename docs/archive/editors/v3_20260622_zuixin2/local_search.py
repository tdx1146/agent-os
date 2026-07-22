#!/usr/bin/env python3
"""
本地记忆搜索：BM25 关键词 + 简单 TF-IDF 排序。
不依赖任何外部模型或 API，纯标准库。
在 memory/、facts.dict.md、SOUL.md 等文件中搜索。
"""
import sys, json, os, re, math
from collections import Counter
from pathlib import Path

# 索引路径
SEARCH_PATHS = [
    '/vol1/@apphome/trim.openclaw/data/workspace/memory',
    '/vol1/@apphome/trim.openclaw/data/workspace/memory/facts.dict.md',
    '/vol1/@apphome/trim.openclaw/data/workspace/SOUL.md',
    '/vol1/@apphome/trim.openclaw/data/workspace/MEMORY.md',
    '/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/facts.dict.md',
    '/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/memory/next-turn-note.md',
]

def tokenize(text):
    """基础分词：中英文+数字"""
    text = text.lower()
    # 中文：按单字/词分割
    tokens = re.findall(r'[\u4e00-\u9fff]+|[a-z]+|\d+', text)
    return [t for t in tokens if len(t) >= 1]

def bm25_score(query_tokens, doc_tokens, avg_dl, N, idf_cache):
    """BM25 得分"""
    k1, b = 1.5, 0.75
    dl = len(doc_tokens)
    doc_counter = Counter(doc_tokens)
    score = 0
    for qt in query_tokens:
        if qt in idf_cache and idf_cache[qt] > 0:
            tf = doc_counter.get(qt, 0)
            idf = idf_cache[qt]
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
    return score

def search(query, max_results=5):
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    
    all_docs = []
    
    # 收集所有文档
    for p in SEARCH_PATHS:
        path = Path(p)
        if not path.exists():
            continue
        if path.is_dir():
            for f in sorted(path.iterdir()):
                if f.suffix == '.md' and f.is_file():
                    try:
                        text = f.read_text('utf-8', errors='replace')
                        all_docs.append({'path': str(f), 'text': text})
                    except:
                        pass
        elif path.is_file():
            try:
                text = path.read_text('utf-8', errors='replace')
                all_docs.append({'path': str(path), 'text': text})
            except:
                pass
    
    # 分词所有文档
    doc_tokens_list = []
    for doc in all_docs:
        tokens = tokenize(doc['text'])
        doc_tokens_list.append(tokens)
    
    # 计算 IDF 和平均文档长度
    N = len(all_docs)
    if N == 0:
        return []
    
    avg_dl = sum(len(t) for t in doc_tokens_list) / max(N, 1)
    
    idf_cache = {}
    for qt in query_tokens:
        doc_count = sum(1 for tokens in doc_tokens_list if qt in tokens)
        idf_cache[qt] = math.log((N - doc_count + 0.5) / (doc_count + 0.5) + 1)
    
    # 计算 BM25 得分
    scored = []
    for i, doc in enumerate(all_docs):
        score = bm25_score(query_tokens, doc_tokens_list[i], avg_dl, N, idf_cache)
        if score > 0:
            # 提取摘要（首次匹配附近 ±100 字符）
            excerpt = ''
            for qt in query_tokens:
                pos = doc['text'].lower().find(qt)
                if pos >= 0:
                    start = max(0, pos - 100)
                    end = min(len(doc['text']), pos + 200)
                    excerpt = doc['text'][start:end].replace('\n', ' | ').strip()
                    break
            if not excerpt:
                excerpt = doc['text'][:300].replace('\n', ' ').strip()
            
            scored.append({
                'path': doc['path'],
                'score': round(score, 4),
                'keywords': len([qt for qt in query_tokens if qt in set(doc_tokens_list[i])]),
                'excerpt': excerpt[:300]
            })
    
    scored.sort(key=lambda x: -x['score'])
    return scored[:max_results]

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'need query'}))
        sys.exit(1)
    query = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    results = search(query, count)
    print(json.dumps(results, ensure_ascii=False, indent=2))
