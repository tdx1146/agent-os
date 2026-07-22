#!/usr/bin/env python3
"""
reflection_check.py — dandan 反思质检器 v2
========================================
独立运行（不假设人在场）。每次跑完写入反思链 + 输出修订版答案。
设计为 self_pulse 的默认 payload。

方法论 9 步（dandan 定义）：
0. 预备区：查环境+查记忆
1. 假设已经犯过错了
2. 搜索 sandglass 记忆 + facts 知识库
3. 有历史记录直接避坑；没有也继续
4. 假设失败，反向推导：最容易错在哪
5. 站在问题制造者角度：在哪埋坑
6. 真实方案对比（读 sandglass 搜索结果生成，非模板）
7. 实施建议
8. 失败→循环（最多3次）→ blocked → 写 backlog
9. 成功→复盘→写入 reflection-errors.md + backlog.md
"""

import os, json, re, sys, subprocess
from datetime import datetime

# ── 路径自动发现 ──────────────────────────────────
_SELF = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE = os.environ.get('OPENCLAW_WORKSPACE', '')
if not _WORKSPACE or not os.path.isdir(_WORKSPACE):
    _WORKSPACE = os.path.join(_SELF, '..', '..', '..',
        'vol1/@apphome/trim.openclaw/data/workspace')

_LIGHT_SMOKE = os.environ.get('LIGHT_SMOKE_DIR', '')
if not _LIGHT_SMOKE:
    _LIGHT_SMOKE = '/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟'

_ERROR_LOG = os.path.join(_WORKSPACE, 'memory', 'reflection-errors.md')
_BACKLOG = os.path.join(_WORKSPACE, 'memory', 'backlog.md')
_FACTS = os.path.join(_WORKSPACE, 'memory', 'facts.dict.md')


# ── 工具函数 ──────────────────────────────────────

def _sandglass_search(query, limit=5):
    """通过 sandglass MCP 搜索。返回列表。"""
    try:
        mcp = os.path.join(_LIGHT_SMOKE, 'sandglass_source', 'sandglass_mcp.py')
        if not os.path.exists(mcp):
            return []
        req = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
            "params":{"name":"sandglass_search","arguments":{"query":query,"limit":limit}}})
        r = subprocess.run(['python3', mcp], input=req,
            capture_output=True, text=True, timeout=10,
            env={**os.environ, 'NEXSANDBASE_HOME': os.path.join(_LIGHT_SMOKE, 'sandglass')})
        resp = json.loads(r.stdout)
        return json.loads(resp['result']['content'][0]['text'])
    except Exception as e:
        return []


def _read_facts(keywords=None):
    """读 facts.dict.md，返回全文或关键词匹配行。"""
    if not os.path.exists(_FACTS):
        return []
    with open(_FACTS) as f:
        text = f.read()
    if not keywords:
        return text
    return [l for l in text.split('\n') if any(kw in l for kw in keywords)]


def _write_error_log(task, errors):
    """写错误到独立记录库。"""
    os.makedirs(os.path.dirname(_ERROR_LOG), exist_ok=True)
    with open(_ERROR_LOG, 'a', encoding='utf-8') as f:
        f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write(f"任务: {task[:100]}\n")
        for e in errors:
            f.write(f"- {e}\n")


def _write_backlog(task, lesson):
    """复盘写入公共待办。"""
    os.makedirs(os.path.dirname(_BACKLOG), exist_ok=True)
    with open(_BACKLOG, 'a', encoding='utf-8') as f:
        f.write(f"\n- [x] {datetime.now():%m-%d} 反思复盘: {task[:60]} → {lesson[:80]}")


# ── 反思核心 ──────────────────────────────────────

def reflect(context=None, solution_draft=None):
    """
    完整反思链。不假设人在场，全部自动执行。
    
    Args:
        context: dict with 'task', 'existing_info', 'memory_results'
        solution_draft: str, 待质检的回答草稿
    
    Returns:
        dict with 'answer', 'chain', 'passed', 'errors_found', 'alternatives', 'quality'
    """
    if context is None:
        context = {}
    task = context.get('task', '未指定任务')
    existing_info = context.get('existing_info', '')
    
    chain = []  # 反思链日志
    errors_found = []
    alternatives = []
    
    def log(step, name, analysis):
        chain.append({'step': step, 'name': name, 'analysis': str(analysis), 'timestamp': datetime.now().isoformat()})
    
    # ── Step 0：预备区 ──
    log(0, '初始化', f'任务: {task[:80]}')
    
    # 查环境：sandglass + facts 是否就绪
    env_ok = os.path.exists(os.path.join(_LIGHT_SMOKE, 'sandglass', 'sandglass.db'))
    facts_ok = os.path.exists(_FACTS)
    log(0, '环境检查', f'sandglass.db: {"✅" if env_ok else "❌"} | facts.dict.md: {"✅" if facts_ok else "❌"}')
    
    # ── Step 1：假设失败 ──
    log(1, '假设失败', 
        '已假设该任务存在潜在错误。每个断言都要重新质疑。\n'
        f'现有信息: {existing_info[:200] if existing_info else "(无)"}')
    
    # ── Step 2：搜索记忆（sandglass + facts 双路）──
    sg_results = _sandglass_search(task)
    log(2, 'sandglass搜索', f'找到 {len(sg_results)} 条相关记录')
    if sg_results:
        for r in sg_results[:3]:
            log(2, 'sandglass搜索', f"  [{r.get('ts','')}] {str(r.get('text',''))[:100]}")
    
    facts_lines = _read_facts(task.split()[:5])
    if facts_lines:
        log(2, 'facts搜索', f'找到 {len(facts_lines)} 行匹配，前3行:')
        for l in facts_lines[:3]:
            log(2, 'facts搜索', f"  {l.strip()[:100]}")
    else:
        log(2, 'facts搜索', '未找到匹配')
    
    # ── Step 3：避坑检查 ──
    if sg_results or facts_lines:
        log(3, '发现历史记录', f'sandglass {len(sg_results)} 条 + facts {len(facts_lines) if isinstance(facts_lines, list) else "全文"} 行 — 直接参考历史，继续走完流程确保无遗漏')
    else:
        log(3, '无历史记录', '未发现直接相关记录，继续假设失败分析')
    
    # ── Step 4：假设失败分析 ──
    # 用真实的 sandglass 记录生成错误点预测
    err_keywords = ['失败', '错误', 'bug', '断了', '超时', '不对', '错了', '冲突', '不匹配', '权限', '404', '500']
    if sg_results:
        for r in sg_results:
            text = str(r.get('text', ''))
            for kw in err_keywords:
                if kw in text:
                    part = text[max(0, text.index(kw)-20):text.index(kw)+30]
                    log(4, '假设失败分析', f"基于历史记录发现潜在失败模式: ...{part}...")
                    errors_found.append(f"[模式匹配] 发现'{kw}'相关记录: {part[:80]}")
                    break
    
    # 通用边界检测
    if solution_draft:
        if 'None' in solution_draft or 'null' in solution_draft:
            errors_found.append('[边界·空值] 答案包含空值引用')
            log(4, '假设失败分析', '🔴 发现空值引用')
        if not solution_draft.strip():
            errors_found.append('[边界·空答案] 答案是空的')
            log(4, '假设失败分析', '🔴 答案为空')
        if len(solution_draft) < 10:
            errors_found.append('[边界·过短] 答案过短，可能缺乏实质性内容')
            log(4, '假设失败分析', '🔴 答案过短')
    
    # ── Step 5：对立面埋坑检测 ──
    # 根据 task 关键词针对性检测
    if 'api' in task.lower() or '接口' in task or '端点' in task:
        # 检查硬编码 URL/IP
        urls = re.findall(r'https?://[^\s"\']+', task + ' ' + existing_info + ' ' + json.dumps(sg_results))
        hardcoded = [u for u in urls if re.search(r'(127\.0\.0\.1|localhost|192\.168|tdx1146)', u)]
        for u in hardcoded:
            errors_found.append(f'[硬编码URL] {u} 在跨环境时可能失效')
            log(5, '对立面埋坑', f'🪤 硬编码URL: {u}')
    
    if '路径' in task or 'path' in task.lower() or '目录' in task:
        paths = re.findall(r'["\']/[^"\']+["\']', task + ' ' + existing_info)
        if paths:
            for p in paths:
                errors_found.append(f'[硬编码路径] {p} 在跨环境时可能失效')
                log(5, '对立面埋坑', f'🪤 硬编码路径: {p}')
    
    # 通用埋坑检测
    if solution_draft:
        if not re.search(r'try|except|错误处理|异常|fallback|默认值', solution_draft):
            errors_found.append('[缺失错误处理] 未检测到错误处理/异常保护')
            log(5, '对立面埋坑', '🪤 缺失错误处理')
        if not re.search(r'验证|确认|检查|校验|validate|check', solution_draft):
            errors_found.append('[缺失验证机制] 没有验证/确认/检查机制')
            log(5, '对立面埋坑', '🪤 缺失验证机制')
    
    # ── Step 6：真实方案对比（根据 sandglass+facts 生成）──
    # 从 sandglass 搜索结果中提取成功模式和失败模式
    success_patterns = []
    failure_patterns = []
    for r in sg_results:
        text = str(r.get('text', ''))
        if '成功' in text or '通过' in text or '完成' in text or '✅' in text:
            success_patterns.append(text[:80])
        if '失败' in text or '错误' in text or 'bug' in text or '❌' in text:
            failure_patterns.append(text[:80])
    
    if success_patterns or failure_patterns:
        log(6, '方案对比·基于历史', f'历史中成功模式 {len(success_patterns)} 个 + 失败模式 {len(failure_patterns)} 个')
        alternatives.append({
            'name': '📚 基于历史经验的方案',
            'description': f'参考 sandglass 中 {len(sg_results)} 条相关记录，'
                          f'其中 {len(success_patterns)} 条成功、{len(failure_patterns)} 条失败',
            'pros': '✅ 基于实际记录，不是空想\n✅ ' + ('/'.join(success_patterns[:2]) if success_patterns else '无成功模式'),
            'cons': '❌ 记录可能不完整\n❌ ' + ('/'.join(failure_patterns[:2]) if failure_patterns else ''),
            'when': '历史数据充分时首选'
        })
    else:
        log(6, '方案对比', 'sandglass 无历史记录，跳过基于经验的方案')
    
    # 极简 vs 通用方案（dandan象限框架）
    alternatives.append({
        'name': '🪒 极简（第一象限）',
        'description': f'针对「{task[:40]}」的最简实现：只保留解决核心问题的部分',
        'pros': '✅ 认知负载最低\n✅ 出错面最小\n✅ 符合长期极简理论',
        'cons': '❌ 可能遗漏边界情况',
        'when': '核心问题明确、环境稳定'
    })
    alternatives.append({
        'name': '🛡️ 通用（第二象限）',
        'description': f'针对「{task[:40]}」的通用方案：覆盖边界+加安全网+异常处理',
        'pros': '✅ 更鲁棒\n✅ 跨环境可用性更强\n✅ 多场景兼容',
        'cons': '❌ 实现成本更高\n❌ 可能过早优化',
        'when': '多环境部署、非一人维护'
    })
    
    log(6, '方案对比', f'共 {len(alternatives)} 个方案')
    
    # ── Step 7：实施建议 ──
    if errors_found:
        best = '通用（鲁棒）' if len(errors_found) > 3 else '极简'
        log(7, '实施建议', f'发现 {len(errors_found)} 个问题，建议方案: {best}')
    else:
        log(7, '实施建议', '未发现问题，可维持当前方案')
    
    # ── 修订输出 ──
    if solution_draft and errors_found:
        revised = solution_draft + f"\n\n---\n> 🔍 **反思质检附注** — {len(errors_found)} 个问题发现\n"
        for e in errors_found:
            revised += f"> - {e}\n"
    elif solution_draft:
        revised = solution_draft
    else:
        revised = json.dumps(context, ensure_ascii=False) if context else "(无输入)"
    
    log(7, '修订输出', f'原始答案已修订。原始长度: {len(solution_draft or "")} → 修订长度: {len(revised)}')
    
    # ── Step 8/9：错误记录 + 复盘入库 ──
    if errors_found:
        _write_error_log(task, errors_found)
        log(8, '错误记录', f'已写入 {_ERROR_LOG}')
    
    if not errors_found and solution_draft:
        _write_backlog(task, '反思通过，无问题')
        log(9, '复盘入库', f'已写入 {_BACKLOG}')
    
    # ── 可信度计算 ──
    confidence = max(0.0, 1.0 - (len(errors_found) * 0.12))
    # 有 sandglass 记录加 0.2，有 facts 加 0.1
    if sg_results:
        confidence += 0.2
    if facts_lines:
        confidence += 0.1
    confidence = min(1.0, confidence)
    
    return {
        'answer': revised,
        'chain': chain,
        'passed': len(errors_found) == 0,
        'errors_found': errors_found,
        'alternatives': alternatives,
        'quality': {
            'passed': len(errors_found) == 0,
            'issue_count': len(errors_found),
            'critical_issues': sum(1 for e in errors_found if '[缺失' in e or '[边界·空' in e),
            'confidence': round(confidence, 2),
        }
    }


# ─── CLI / self_pulse 入口 ─────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    
    if '--self-pulse' in sys.argv:
        # self_pulse 模式：自动发现任务 + 跑完整反思 + 写日志
        task = sys.argv[sys.argv.index('--self-pulse') + 1] if len(sys.argv) > sys.argv.index('--self-pulse') + 1 else '日常自我反思'
        result = reflect({'task': task}, '')
        print(f"🌫️ 反思完成: {task}")
        print(f"   问题数: {result['quality']['issue_count']} | 可信度: {result['quality']['confidence']}")
        print(f"   链长: {len(result['chain'])}步")
        if result['errors_found']:
            print(f"   发现问题:")
            for e in result['errors_found']:
                print(f"     🔍 {e}")
    elif '--check' in sys.argv:
        # 管道模式：echo context | python3 reflection_check.py --check "task"
        idx = sys.argv.index('--check')
        task = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ''
        input_data = sys.stdin.read().strip()
        try:
            ctx = json.loads(input_data) if input_data else {'task': task}
        except:
            ctx = {'task': task, 'existing_info': input_data[:500]}
        result = reflect(ctx, ctx.get('draft', ''))
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"{'反省质检器 v2':^40}")
        print(f"{'='*40}")
        print(f"用法:")
        print(f"  python3 {sys.argv[0]} --check '任务' < context.json  管道模式")
        print(f"  python3 {sys.argv[0]} --self-pulse '任务'           self_pulse 模式")
