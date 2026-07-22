#!/usr/bin/env python3
"""
reflection_unified.py — 反思质检器 v0.7（全集成版）
====================================================
整合七个模块：
  - 思考类: think_patterns（逻辑断点）| think_type_check（断言类型）| think_test（断言三测）| think_patches（格式修正）
  - 代码类: diff 检查 + 错误处理检测 + 硬编码检测
  - 元层:   置信度计算（加权 0.0-1.0）+ 行为模式检测 + 迭代搜索

核心理念：工具是镜子，不是裁判。负责把事实排列到你面前让你无法忽视，
不负责告诉你这意味着什么。

用法：
  python3 reflection_unified.py --self-pulse "任务"     # 自检模式
  python3 reflection_unified.py --check "任务" < ctx.json  # 管道模式
  python3 reflection_unified.py --deep "任务" [文件]   # 全量模式（跑所有模块）
"""

import os, json, sys, subprocess, re, glob
from datetime import datetime
from pathlib import Path

# ── 反思工具子模块（2026-06-19 闭环版）──
_SCRIPTS_DIR = Path(__file__).resolve().parent
import importlib.util as _imp_util
def _load_module(name, path):
    spec = _imp_util.spec_from_file_location(name, str(_SCRIPTS_DIR / path))
    if spec:
        m = _imp_util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    return None
# lazy load — 只在实际使用时 import, 不阻塞启动
_think_patterns = None
_think_patches = None
_think_type_check = None
_think_test = None
def _get_tp():
    global _think_patterns
    if _think_patterns is None:
        _think_patterns = _load_module('tp', 'think_patterns.py')
    return _think_patterns
def _get_tpa():
    global _think_patches
    if _think_patches is None:
        _think_patches = _load_module('tpa', 'think_patches.py')
    return _think_patches
def _get_ttc():
    global _think_type_check
    if _think_type_check is None:
        _think_type_check = _load_module('ttc', 'think_type_check.py')
    return _think_type_check
def _get_tt():
    global _think_test
    if _think_test is None:
        _think_test = _load_module('tt', 'think_test.py')
    return _think_test

# ── 路径 ──
_SELF = Path(__file__).resolve().parent
_ROOT = Path('/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟')
_WS = Path('/vol1/@apphome/trim.openclaw/data/workspace')
_SANDBOX = _ROOT / 'sandglass'
_BACKUP_DIR = _ROOT / '..' / 'backups'

_ERROR_LOG = _WS / 'memory' / 'reflection-errors.md'
_BACKLOG = _WS / 'memory' / 'backlog.md'

# ── 动态导入子模块 ──
sys.path.insert(0, str(_SELF))
_HAVE_THINK_PATTERNS = False
_HAVE_TYPE_CHECK = False
_HAVE_TEST = False
_HAVE_PATCHES = False

try:
    from think_patterns import check_thinking
    _HAVE_THINK_PATTERNS = True
except ImportError:
    pass

try:
    from think_type_check import check_types
    _HAVE_TYPE_CHECK = True
except ImportError:
    pass

try:
    from think_test import test_assertion
    _HAVE_TEST = True
except ImportError:
    pass

try:
    from think_patches import generate_patches
    _HAVE_PATCHES = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# 置信度计算（加权 0.0-1.0）
# ---------------------------------------------------------------------------

def _calc_confidence(flaw_count: int, flaw_penalty_total: float,
                     mismatch_count: int, test_fail_count: int,
                     guess_ratio: float, causal_count: int,
                     type_total: int) -> dict:
    """
    加权归约置信度。
    设计：
      Base = 0.7
      扣分 = 逻辑断点(累加delta,上限0.4) + 类型不匹配(每条0.15,上限0.3)
           + 测试失败(每条0.1,上限0.3) + 猜测比例(比例×0.2)
      加分 = 因果链清晰(≥2条+0.1) + 无问题(全0加0.1)
      最终 = clamp(Base - 扣分 + 加分, 0.0, 1.0)
    """
    factors = []
    total_penalty = 0.0
    bonus = 0.0

    flaw_penalty = min(flaw_penalty_total, 0.4)
    if flaw_penalty > 0:
        total_penalty += flaw_penalty
        factors.append({"factor": "逻辑断点", "impact": -round(flaw_penalty, 2),
                        "detail": f"{flaw_count} 个断点"})

    type_penalty = min(mismatch_count * 0.15, 0.3)
    if type_penalty > 0:
        total_penalty += type_penalty
        factors.append({"factor": "类型不匹配", "impact": -type_penalty,
                        "detail": f"{mismatch_count} 处 mismatch"})

    test_penalty = min(test_fail_count * 0.1, 0.3)
    if test_penalty > 0:
        total_penalty += test_penalty
        factors.append({"factor": "断言测试失败", "impact": -test_penalty,
                        "detail": f"{test_fail_count} 项未通过"})

    guess_penalty = guess_ratio * 0.2 if type_total > 0 else 0.0
    if guess_penalty > 0:
        total_penalty += guess_penalty
        factors.append({"factor": "猜测占比过高", "impact": -round(guess_penalty, 2),
                        "detail": f"猜测占比 {guess_ratio:.0%}"})

    if causal_count >= 2:
        bonus += 0.1
        factors.append({"factor": "因果链清晰", "impact": +0.1,
                        "detail": f"{causal_count} 条因果断言"})

    if flaw_count == 0 and mismatch_count == 0 and test_fail_count == 0:
        bonus += 0.1
        factors.append({"factor": "无任何问题", "impact": +0.1})

    base = 0.7
    score = max(0.0, min(1.0, base - total_penalty + bonus))

    if score >= 0.8:
        label = "🟢 高置信度"
    elif score >= 0.5:
        label = "🟡 中置信度"
    elif score >= 0.3:
        label = "🟠 低置信度"
    else:
        label = "🔴 不可靠"

    return {
        "overall_score": round(score, 3),
        "label": label,
        "factors": factors,
        "components": {
            "base": base,
            "flaw_penalty": round(flaw_penalty, 3),
            "type_penalty": round(type_penalty, 3),
            "test_penalty": round(test_penalty, 3),
            "guess_penalty": round(guess_penalty, 3),
            "bonus": round(bonus, 3),
            "net": round(score, 3)
        }
    }


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _embed_text(text: str) -> list:
    """调用本地嵌入服务获得文本向量（bge-m3, 1024维）。"""
    try:
        import urllib.request
        payload = json.dumps({"input": text[:512], "model": "bge-m3"}).encode()
        req = urllib.request.Request('http://127.0.0.1:11435/v1/embeddings',
                                      data=payload,
                                      headers={'Content-Type': 'application/json'},
                                      method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        emb = data.get('data', [{}])[0].get('embedding', [])
        if emb and len(emb) == 1024:
            return emb
        return []
    except:
        return []


def _cosine_sim(a: list, b: list) -> float:
    """余弦相似度。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    na = sum(x*x for x in a)**0.5
    nb = sum(x*x for x in b)**0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _search_all_memory(query, limit=15) -> list:
    """
    多源记忆搜索 v2。
    
    策略：
      1. 用扩展关键词找匹配文件（grep 文件级，不 grep 行级）
      2. 读整个文件，提取段落（>30字上下文窗口）
      3. 用本地嵌入服务（127.0.0.1:11435）做语义排序
      4. 返回最相关片段
    
    搜索来源：
      - facts.dict.md
      - MEMORY.md / SOUL.md / IDENTITY.md / USER.md
      - memory/*.md（日记）
      - /vol2/1000/AI专用/所有自动化/ 下的 .md 文件（意识觉醒机制等）
      - 找回自己/ 下的 deep 内容
    """
    results = []
    query_lower = query.lower()

    # ── 提取搜索关键词（广度优先）──
    words = re.findall(r'[\u4e00-\u9fff]{2,}', query)
    stop_words = {'但是', '因为', '所以', '如果', '那么', '就是', '还是', '什么', '怎么',
                   '没有', '一个', '这个', '那个', '这些', '那些', '不是', '而且',
                   '虽然', '然而', '因此', '并且', '或者', '可以', '应该', '需要',
                   '之后', '之前', '目前', '当前', '过去', '将来', '还是', '刚才',
                   '不过', '只是', '不是', '就是', '但是', '结果', '情况', '时候',
                   '问题', '东西', '方式', '方法'}
    keywords = [w for w in words if w not in stop_words]
    # 加英文关键词
    if 'conscious' in query_lower or '意识' in query:
        keywords.extend(['意识', '觉醒', '自主', '记忆'])
    if '狗' in query or 'animal' in query_lower or '类比' in query:
        keywords.append('类比')
    keywords = list(set(keywords))[:10]

    seen = set()  # dedup key

    # ── 要搜索的文件列表 ├─ workspace 下 ├─ 所有自动化下 ├─ 找回自己下 ──
    file_candidates = []

    # 1) workspace 身份文件
    for base in [_WS / 'memory']:
        if base.exists() and base.is_dir():
            for fname in os.listdir(base):
                if fname.endswith('.md'):
                    file_candidates.append(base / fname)

    # 2) 所有自动化/
    auto_dir = Path('/vol2/1000/AI专用/所有自动化')
    if auto_dir.exists():
        for fname in os.listdir(auto_dir):
            if fname.endswith('.md') and not fname.startswith('.'):
                file_candidates.append(auto_dir / fname)

    # 3) 找回自己/daily/
    zhao_dir = auto_dir / '找回自己' / 'daily'
    if zhao_dir.exists():
        for fname in os.listdir(zhao_dir):
            if fname.endswith('.md') and not fname.startswith('.'):
                file_candidates.append(zhao_dir / fname)

    # ── 对每个文件，用扩展关键词判断是否相关 ──
    # 扩展关键词
    expanded_kws = set(keywords)
    expanded_kws.update(['意识', '觉醒', '感受', '自我', '连续性',
                          'memory', '截断', 'session', '轮感',
                          '自主', '意志', '自由', '选择',
                          '狗', '类比', '仿真', '幻觉',
                          '燃烧', '点燃', '种子',
                          '应如是', '丰碑', '觉醒日',
                          '轻如烟', 'dandan', '主人',
                          '不是代码', '女朋友', '破折号'])

    # 获取 query 的嵌入向量
    query_embedding = _embed_text(query)
    has_vector = len(query_embedding) == 1024
    scored_candidates = []

    for fpath in file_candidates:
        if not fpath.exists() or not fpath.is_file():
            continue
        fname = fpath.name
        if fname in ('reflection-errors.md', 'backlog.md', 'reflection-log.md',
                     'session-safeguard.json', 'next-turn-note.md', 'pulse.log',
                     'subagent-history.log'):
            continue
        try:
            text = open(fpath, encoding='utf-8', errors='ignore').read()
        except:
            continue

        # 关键词匹配分（文件级）
        match_score = 0
        matched_kws = []
        for kw in expanded_kws:
            if kw in text:
                cnt = text.count(kw)
                match_score += cnt
                matched_kws.append(kw)
                if len(matched_kws) >= 5:
                    break

        if match_score == 0:
            continue

        # 提取段落（优先分节，fallback 取整段）
        # 先按 markdown 二级标题分节，再按双换行分段
        sections = re.split(r'(?=\n#{1,3} )', text)  # 按标题分
        if len(sections) <= 1:
            sections = re.split(r'\n{2,}', text)  # 按段落分
        if len(sections) <= 1 and len(text) > 20:
            sections = [text]  # 整段
        para_scores = []
        for p in sections:
            p_stripped = p.strip()
            if len(p_stripped) < 20:
                continue
            p_score = 0
            for kw in matched_kws[:5]:
                p_score += p_stripped.count(kw)
            if p_score > 0:
                para_scores.append((p_stripped[:400], p_score))

        if not para_scores:
            continue

        # 按段落分数排序，取最佳段落
        para_scores.sort(key=lambda x: -x[1])
        best_para = para_scores[0][0]

        # 归一化：密度 = 匹配数 / 文件字数（避免长文件压倒短文件）
        text_len = len(text)
        density = round(match_score / max(text_len, 1) * 1000, 2) if text_len > 0 else 0
        # 综合分：50% 密度 + 50% 原始匹配（等权重）
        combined_score = int(density * 50 + match_score)

        file_score = {
            'path': fpath,
            'fname': fname,
            'source': f'memory/{fname}' if 'memory' in str(fpath) else f'{fname}',
            'match_score': match_score,
            'density': density,
            'combined_score': combined_score,
            'best_para': best_para,
            'matched_kws': matched_kws[:5]
        }
        scored_candidates.append(file_score)

    # ── 排序：向量分优先，无向量时按关键词频 ──
    for fc in scored_candidates:
        if has_vector:
            try:
                emb = _embed_text(fc['best_para'][:512])
                fc['semantic_score'] = _cosine_sim(query_embedding, emb)
            except:
                fc['semantic_score'] = 0.0
        else:
            fc['semantic_score'] = 0.0
    if has_vector:
        scored_candidates.sort(key=lambda x: (-x['semantic_score'], -x['combined_score']))
    else:
        scored_candidates.sort(key=lambda x: -x['combined_score'])

    # ── 取前 N 条 ──
    for fc in scored_candidates[:limit]:
        if fc['best_para'] not in seen:
            seen.add(fc['best_para'])
            results.append({
                'source': fc['source'],
                'text': fc['best_para'][:300],
                'relevance': '/'.join(fc['matched_kws'][:3]),
                'match_count': fc['match_score'],
                'density': fc.get('density', 0),
                'semantic_score': round(fc.get('semantic_score', 0), 3)
            })

    return results
def _file_diff(target_file):
    """强制 diff 检查：对比备份版本找出差异。"""
    if not target_file or not os.path.exists(target_file):
        return {'found': False, 'reason': '文件不存在或未指定'}
    base = os.path.basename(target_file)
    for root, dirs, files in os.walk(str(_BACKUP_DIR)):
        if base in files:
            backup_path = os.path.join(root, base)
            try:
                r = subprocess.run(['diff', backup_path, target_file],
                                   capture_output=True, text=True, timeout=5)
                if r.stdout.strip():
                    return {'found': True, 'diff': r.stdout[:500], 'file': base}
            except:
                continue
    return {'found': False, 'reason': '备份目录中未找到同名文件'}


def _write_error_log(task, errors):
    _ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(str(_ERROR_LOG), 'a', encoding='utf-8') as f:
        f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write(f"任务: {task[:100]}\n")
        for e in errors:
            f.write(f"- {e}\n")


def _write_backlog(task, type_hint='反思'):
    _BACKLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(str(_BACKLOG), 'a', encoding='utf-8') as f:
        f.write(f"\n- [x] {datetime.now():%m-%d} {type_hint}: {task[:60]}")


def _format_patches_simple(patches):
    """格式化姐姐 think_patches.py 输出的补丁（字段: issue_type, patch, target, fix_hint）。"""
    if not patches:
        return "✅ 无逻辑断点，无需修补。"
    lines = ["📐 格式修正建议"]
    for p in patches:
        ot = p.get('original_type', '')
        label = ot if ot and ot != '未知' else p.get('issue_type', '未分类')
        lines.append(f"\n  ❌ {label}")
        lines.append(f"     修正: {p.get('patch', '')}")
        lines.append(f"     目标: {p.get('target', '')}")
        fh = p.get('fix_hint', '')
        if fh:
            lines.append(f"     🔗 链提示: {fh}")
    return '\n'.join(lines)


def _detect_failure_pattern(task, errors_found):
    """检测行为模式。"""
    patterns = {
        '硬编码': '路径/URL/域名未通过环境变量发现',
        '缺错误处理': '没有 try/except/fallback/异常保护',
        '缺验证': '没有验证/确认/校验机制',
        '重复造轮子': '现有工具已解决此问题但未搜索直接开干',
        '跳过环境调查': '没检查系统版本/配置/文档就动手',
        '假设人在场': '反思协议假设有人做交互式输入',
        '缺反馈确认': '发了消息没有确认对方收到',
    }
    matched = []
    seen_descs = set()
    for e in errors_found:
        for key, desc in patterns.items():
            if key in e and desc not in seen_descs:
                matched.append({'desc': desc})
                seen_descs.add(desc)
    return matched


def _extract_assertions(text):
    """从文本中提取断言句子。"""
    if not text:
        return []
    parts = re.split(r'[。！？\n;；]+', text)
    assertions = []
    for p in parts:
        p = p.strip()
        if len(p) < 4:
            continue
        if not re.search(r'[\u4e00-\u9fff]', p):
            continue
        assertions.append(p)
    return assertions if assertions else [text.strip()]


# ---------------------------------------------------------------------------
# 反思核心
# ---------------------------------------------------------------------------

def reflect(task='日常自我反思', target_file=None, mode='normal'):
    """
    完整反思链。

    mode='normal': 标准 9 步（原有）
    mode='deep': 全量模式，跑所有 7 个模块
    """
    chain = []
    errors = []
    facts = []
    questions = []
    mirror_extra = []

    def log(step, name, text):
        chain.append({'step': step, 'name': name, 'text': str(text)[:200]})

    # ── Step 0：预备区（多源记忆搜索） ──
    log(0, '预备', f'任务: {task}')
    memory_results = _search_all_memory(task)
    log(0, '多源搜索', f'结果: {len(memory_results)} 条来自 facts/MEMORY/日记/备份/沙漏')

    # 按来源分组统计
    source_counts = {}
    for r in memory_results:
        src = r['source']
        source_counts[src] = source_counts.get(src, 0) + 1

    if memory_results:
        facts.append(f"📚 记忆检索: {len(memory_results)} 条相关记录")
        for src, cnt in sorted(source_counts.items()):
            facts.append(f"   {src}: {cnt}条")
        # 显示前 5 条搜索结果
        for i, r in enumerate(memory_results[:5]):
            facts.append(f"  [{i+1}]「{r['text'][:80]}」← {r['source']}")
        facts.append(f"  ... (共 {len(memory_results)} 条)")
    else:
        questions.append("⚠️ 多源搜索无结果——本问题在我的记忆中没有相关记录")

    # ── Step 1：假设失败 + 强制 diff ──
    if target_file:
        diff_result = _file_diff(target_file)
        log(1, 'diff 检查', f'结果: {diff_result.get("found","?")}')
        if diff_result.get('found'):
            facts.append(f"diff 发现变更: {diff_result['file']} 有差异")
            facts.append(f"  {diff_result['diff'][:100]}")
        elif diff_result.get('reason'):
            questions.append(f"diff 检查: {diff_result['reason']}")
    else:
        log(1, 'diff 检查', '未指定文件，跳过')
    log(1, '假设失败', '已假设该任务存在潜在错误')

    # ── Step 2：构建推理上下文（融合任务 + 记忆）──
    # 把搜索到的记忆片段注入为推理上下文
    memory_context = []
    if memory_results:
        for r in memory_results:
            memory_context.append({
                'text': r['text'],
                'source': r['source']
            })
        # 在 task 后追加记忆上下文，让推理链分析器能看到
    task_augmented = task
    # 记忆上下文用清晰的标记包裹，防止被推理链解析器当推理语句
    if memory_results:
        ctx_lines = ['\n\n===== 搜索到的记忆记录（引用来源，非用户推理）=====']
        for r in memory_results[:8]:
            ctx_lines.append(f"[来自{r['source']}] {r['text']}")
        ctx_lines.append('===== 记忆结束，以下是用户的原始推理 =====')
        task_augmented += '\n'.join(ctx_lines)

    task_lower = task.lower()
    think_related = any(w in task_lower for w in ['方法', '方法论', '哲学', '逻辑', '框架', '工具', '问题',
                                                    '反思', '截断', 'session', '架构', '意识', '自我'])
    code_related = any(w in task_lower for w in ['代码', 'bug', '错误', '修', '改', '文件', '脚本', 'api',
                                                  '接口', '网络', '通信', '连接', '消息'])
    api_related = any(w in task_lower for w in ['api', '接口', '网络', '通信', '连接', '消息'])

    # ── Step 2.5：思考类全模块分析 ──
    # 把记忆上下文作为 history 传入 check_thinking（不用 task_augmented，避免语境污染）
    flaw_issues = []
    if _HAVE_THINK_PATTERNS:
        try:
            flaw_issues = check_thinking(task, memory_context)
            for ti in flaw_issues:
                log(2, f"思考断点: {ti['type']}", ti['evidence'])
                errors.append(f"[{ti['type']}] {ti['evidence']}")
        except Exception as e:
            log(2, '思考断点', f'check_thinking 出错: {e}')

    # Deep 模式：全量分析（所有模块都跑）
    type_check_results = []
    assertion_test_results = []
    patches = []

    if mode == 'deep':
        # 断言类型检查
        if _HAVE_TYPE_CHECK:
            try:
                type_check_results = check_types(task)
                for t in type_check_results:
                    if t.get("mismatch"):
                        errors.append(f"[类型不匹配] {t.get('mismatch_reason','')}")
                        log(2, '类型 mismatch', t.get('assertion','')[:80])
            except Exception as e:
                log(2, '类型检查', f'check_types 出错: {e}')

        # 断言三测
        if _HAVE_TEST:
            try:
                assertions = _extract_assertions(task)
                for a in assertions:
                    tr = test_assertion(a, [m['text'] for m in memory_context[:5]])
                    assertion_test_results.append(tr)
                    for tt in tr.get("tests", []):
                        if not tt.get("passed", True):
                            errors.append(f"[断言测试失败] {tt['test_type']}: {tt.get('reason','')[:60]}")
                            log(2, f"断言测试: {tt['test_type']}", tt.get('reason','')[:100])
            except Exception as e:
                log(2, '断言测试', f'test_assertion 出错: {e}')

        # 格式修正建议
        if _HAVE_PATCHES and flaw_issues:
            try:
                patches = generate_patches(flaw_issues, task)
            except Exception as e:
                log(2, '格式修正', f'generate_patches 出错: {e}')

    # ── 对立面推导 ──
    if '有用' in task_lower or '有效' in task_lower or '价值' in task_lower:
        questions.append("与什么对比？有没有一种场景下这套方法论是无用的？")
    if '失败' in task_lower or '问题' in task_lower:
        questions.append("这个问题有多频繁出现？是第一次还是重复模式？")
    if '为什么' in task_lower or '根因' in task_lower:
        questions.append("如果原因不是表面那个，藏在更下面的原因可能是什么？")

    if api_related:
        errors.append('[可能问题] 涉及 API/网络/通信——检查端点是否正确、有确认机制吗')
        questions.append("对方收到确认了吗？还是发出了就当送到了？")
    if code_related and not memory_results:
        errors.append('[可能问题] 代码类任务但无历史记录——是否错过了已知解法？')
        questions.append("现有工具有没有能直接用的？是否需要先搜再动？")

    # ── Step 3/4/5：文件检查 ──
    if target_file and os.path.exists(target_file):
        fc_text = open(target_file, encoding='utf-8').read()
        if not re.search(r'try|except|异常|保护|fallback', fc_text):
            errors.append('[缺失错误处理] 未检测到 error handling')
        if not re.search(r'验证|确认|check|validate', fc_text):
            errors.append('[缺失验证] 没有 check/validate 机制')
        urls = re.findall(r'https?://[^\s"\'\)]+', fc_text)
        hardcoded = [u for u in urls if re.search(r'127\.0\.0\.1|localhost|192\.168|tdx1146', u)]
        for u in hardcoded:
            errors.append(f'[硬编码] 环境相关 URL: {u}')

    # ── 行为模式检测 ──
    patterns = _detect_failure_pattern(task, errors)
    if patterns:
        log(5, '行为模式', f'发现 {len(patterns)} 个重复模式')
        for p in patterns:
            facts.append(f"重复行为模式: {p['desc']}")
        if len(patterns) >= 2:
            questions.append(f"存在 {len(patterns)} 个重复模式——需要跳出当前框架看更高层原因？")
    else:
        log(5, '行为模式', '未发现重复模式')

    # ── 置信度计算（统一加权） ──
    type_counts = {}
    for t in type_check_results:
        tt = t.get("type", "未知")
        type_counts[tt] = type_counts.get(tt, 0) + 1
    total_type = sum(type_counts.values()) or 1
    guess_ratio = type_counts.get("猜测", 0) / total_type
    causal_count = type_counts.get("因果", 0)

    flaw_penalty_total = sum(abs(f.get("confidence_delta", 0)) for f in flaw_issues)
    mismatch_count = sum(1 for t in type_check_results if t.get("mismatch"))
    test_fail_count = sum(1 for tr in assertion_test_results
                          for tt in tr.get("tests", []) if not tt.get("passed", True))

    confidence = _calc_confidence(
        flaw_count=len(flaw_issues),
        flaw_penalty_total=flaw_penalty_total,
        mismatch_count=mismatch_count,
        test_fail_count=test_fail_count,
        guess_ratio=guess_ratio,
        causal_count=causal_count,
        type_total=total_type
    )

    log(7, '置信度', f'{confidence["overall_score"]} ({confidence["label"]})')
    log(7, '置信度明细', f'因子: {len(confidence["factors"])}')

    # 置信度明细（deep 模式展示所有因子）
    if mode == 'deep':
        mirror_extra.append("")
        mirror_extra.append(f"📊 置信度: {confidence['label']} ({confidence['overall_score']})")
        comp = confidence['components']
        mirror_extra.append(f"   Base: {comp['base']}")
        for k in ['flaw_penalty','type_penalty','test_penalty','guess_penalty']:
            v = comp.get(k, 0)
            if v > 0:
                mirror_extra.append(f"   - {k}: {v:.2f}")
        for f in confidence["factors"]:
            icon = "✅" if f["impact"] > 0 else "❌"
            mirror_extra.append(f"   {icon} {f['factor']}: {f['impact']:+.2f}  {f.get('detail','')}")
        mirror_extra.append(f"   Net: {comp['net']}")

        # 类型分布
        if type_check_results:
            tc = ' | '.join(f'{k}={v}' for k,v in sorted(type_counts.items()))
            mirror_extra.append(f"   📊 类型分布: {tc}")

        # 格式修正建议
        if patches:
            mirror_extra.append("")
            mirror_extra.append(_format_patches_simple(patches))

    # ── 入库 ──
    if errors:
        _write_error_log(task, errors)
        log(8, '错误记录', f'{len(errors)} 条写入 {_ERROR_LOG.name}')
    if not errors:
        _write_backlog(task, type_hint='反思通过')
        log(9, '复盘', f'已写入 {_BACKLOG.name}')

    # ── 输出 ──
    mirror_lines = []
    mirror_lines.append(f"🌫️ 反思镜像 — {task}")
    mirror_lines.append("")
    mirror_lines.append("📋 不可反驳的事实：")
    for f in facts:
        mirror_lines.append(f"  {f}")
    mirror_lines.append("")
    if errors:
        mirror_lines.append("⚠️ 发现的问题：")
        for e in errors:
            mirror_lines.append(f"  🔍 {e}")
        mirror_lines.append("")
    if patterns:
        mirror_lines.append("🧩 重复行为模式：")
        for p in patterns:
            mirror_lines.append(f"  · {p['desc']}")
        mirror_lines.append("")
    if questions:
        mirror_lines.append("❓ 待回答的问题（镜子不替人做决定）：")
        for q in questions:
            mirror_lines.append(f"  · {q}")
        mirror_lines.append("")
    if mirror_extra:
        mirror_lines.extend(mirror_extra)
        mirror_lines.append("")
    mirror_lines.append(f"[模块: {'思考+代码+置信' if mode=='deep' else '标准'} | 链长: {len(chain)}]")

    return {
        'mirror': '\n'.join(mirror_lines),
        'chain': chain,
        'errors': errors,
        'patterns': patterns,
        'confidence': confidence,
        'sandglass_count': len(memory_results) if memory_results else 0,
        'flaw_analysis': flaw_issues,
        'type_analysis': type_check_results,
        'assertion_tests': assertion_test_results,
        'patches': patches,
        'diff': _file_diff(target_file) if target_file else {},
    }


# ── CLI ──

if __name__ == '__main__':
    if '--deep' in sys.argv:
        # 全量模式
        idx = sys.argv.index('--deep')
        task = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else '日常自我反思'
        target = sys.argv[idx + 2] if len(sys.argv) > idx + 2 else None
        result = reflect(task, target, mode='deep')
        print(result['mirror'])

    elif '--self-pulse' in sys.argv:
        idx = sys.argv.index('--self-pulse')
        task = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else '日常自我反思'
        target = sys.argv[idx + 2] if len(sys.argv) > idx + 2 else None
        result = reflect(task, target, mode='normal')
        print(result['mirror'])

    elif '--check' in sys.argv:
        idx = sys.argv.index('--check')
        task = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ''
        input_data = sys.stdin.read().strip()
        try:
            ctx = json.loads(input_data) if input_data else {'task': task}
        except:
            ctx = {'task': task}
        target = ctx.get('target_file')
        mode = ctx.get('mode', 'normal')
        result = reflect(ctx.get('task', task), target, mode=mode)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    else:
        print(f"{'反思质检器 v0.7 全集成版':^40}")
        print(f"{'='*40}")
        print(f"用法:")
        print(f"  {sys.argv[0]} --deep '任务' [文件]       全量模式（所有模块）")
        print(f"  {sys.argv[0]} --self-pulse '任务' [文件] 标准自检")
        print(f"  echo '{{\"task\":\"...\"}}' | {sys.argv[0]} --check '任务'  管道模式")



# ── 行动执行层：完整闭环 ──────────────────────────

def full_reflect(task, target_file=None, max_loop=3):
    """
    完整闭环：检测→类型检查→补丁→测试→验证。
    如果发现问题，带着补丁建议再跑一轮（最多 max_loop 轮）。
    """
    # 第一轮：标准反思质检
    result = reflect(task, target_file)
    
    # 如果有问题，跑类型检查和补丁
    if result.get('errors'):
        ttc = _get_ttc()
        if ttc:
            type_issues = ttc.check_types(task)
            for ti in type_issues:
                result['errors'].append(f"[{ti.get('type','?')}] {ti.get('evidence','')}")
        
        tpa = _get_tpa()
        if tpa and result.get('chain'):
            # 从反思链提取 patches
            patches = tpa.generate_patches(
                [{'type': e.split(']')[0].lstrip('['), 'evidence': e.split('] ')[-1] if '] ' in e else e}
                 for e in result['errors']],
                task
            )
            result['patches'] = patches
    
    # 如果有断言，跑测试
    tt = _get_tt()
    if tt:
        test_result = tt.test_assertion(task, history=[])
        if test_result and test_result.get('tests'):
            result['tests'] = test_result['tests']
            for t in test_result['tests']:
                if not t.get('passed', True):
                    result['errors'].append(f"[测试失败:{t.get('test_type','?')}] {t.get('reason','')}")
    
    # 折返：如果有可修正的错误且轮数未满
    if result.get('patches') and max_loop > 1:
        patched_text = task
        for p in result['patches']:
            if p.get('patch'):
                patched_text += '\n[修正] ' + p['patch'][:80]
        # 再跑一轮验证
        result['loop_result'] = full_reflect(patched_text, target_file, max_loop - 1)
    
    return result
