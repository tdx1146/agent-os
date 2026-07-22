#!/usr/bin/env python3
"""
反思方法论 v1 — 轻如烟 (jl版)
2026-06-16 | dandan 9步循环

核心理念：这是一个思维协议，不是自动工具。
调用者必须参与每一步的思考，代码只负责记录、搜索、提醒。
"""

import os, json, sys
from datetime import datetime

# ── 路径 ──────────────────────────────────────────
_SELF_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE = os.environ.get('OPENCLAW_WORKSPACE',
    os.path.join(_SELF_DIR, '..', '..', '..',
    'vol1/@apphome/trim.openclaw/data/workspace'))
_BACKLOG = os.path.join(_WORKSPACE, 'memory', 'backlog.md')
_ERROR_LOG = os.path.join(_WORKSPACE, 'memory', 'reflection-errors.md')


def step1_assume_fault():
    """1. 不假设顺利，假设已犯过错了。"""
    print("🟢 Step 1: 假设已经犯过错")
    print("   不要想'会不会出问题'，想'问题已经出了，在哪'")
    return input("   当前任务是什么？> ").strip()


def step2_search_memory(task):
    """2. 搜索记忆，有没有类似错误。"""
    print(f"\n🟢 Step 2: 搜索记忆 — '{task}'")
    # 用 sandglass 搜索类似失败
    import subprocess
    try:
        r = subprocess.run(
            ['python3', os.path.join(_SELF_DIR, '..', 'sandglass_source', 'sandglass_mcp.py')],
            input=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                "params":{"name":"sandglass_search","arguments":{"query":task,"limit":5}}}),
            capture_output=True, text=True, timeout=10,
            env={**os.environ, 'NEXSANDBASE_HOME':
                 '/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass'}
        )
        # 解析 sandglass MCP 响应：外层 result.content[0].text 是 JSON 字符串
        resp = json.loads(r.stdout)
        inner = json.loads(resp.get('result',{}).get('content',[{}])[0].get('text','[]'))
        if inner:
            print(f"   sandglass 找到 {len(inner)} 条相关记录:")
            for item in inner[:3]:
                print(f"     - [{item.get('ts','')}] {item.get('text','')[:80]}")
            return input("   发现历史记录。有不有问题相关的？输入内容或回车跳过 > ").strip()
        else:
            print("    sandglass 搜索未找到相关记录")
    except Exception as e:
        print(f"   (sandglass 搜索异常: {e})")
    return input("   类似错误记录？(无则回车) > ").strip()


def step3_skip_or_continue(record):
    """3. 有记录就避坑，没有继续。"""
    if record:
        print(f"\n🟢 Step 3: 发现历史错误 — '{record}'")
        fix = input("   当时的修复方案是？> ").strip()
        print(f"   → 直接采用：{fix}")
        return True
    print("\n🟢 Step 3: 无历史错误，继续。")
    return False


def step4_weakest_point(task):
    """4. 假设失败，最容易出错的点在哪。"""
    print(f"\n🟢 Step 4: 最可能翻车的地方 — '{task}'")
    return input("   写出 1-3 个最容易出错的步骤 > ").strip()


def step5_who_built_trap():
    """5. 站在问题制造者角度想人在哪埋坑。"""
    print("\n🟢 Step 5: 敌人视角 — 如果有人想让你失败")
    return input("   他会在哪埋坑？> ").strip()


def step6_alternatives(task):
    """6. 站在对立面：其他方案？极简 vs 极通用。"""
    print(f"\n🟢 Step 6: 方案选择 — '{task}'")
    simple = input("   极简方案（最直接能跑通的）> ").strip()
    generic = input("   极通用方案（能复用/扩展的）> ").strip()
    print(f"\n   🔄 长期极简理论：选 simplest thing that won't need rewriting next week")
    choice = input(f"   选极简(1)还是极通用(2)？> ").strip()
    return (simple, generic, choice)


def step7_execute(chosen_plan):
    """7. 实施。"""
    print(f"\n🟢 Step 7: 实施 — '{chosen_plan}'")
    print("   记录时间：", datetime.now().strftime("%H:%M"))
    return input("   开始实施（完成后回车）> ").strip()


def step8_on_fail(task, failure):
    """8. 失败→循环。"""
    print(f"\n🔴 Step 8: 失败 — '{failure}'")
    # 写入错误日志
    with open(_ERROR_LOG, 'a') as f:
        f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write(f"- 任务: {task}\n")
        f.write(f"- 失败: {failure}\n")
    cont = input("   重新从 Step 1 开始？(y/n) > ").strip()
    if cont == 'y':
        return reflect()
    return False


def step9_review(task):
    """9. 成功→复盘→总结入库（backlog.md）。"""
    print(f"\n🟢 Step 9: 复盘入库 — '{task}' 成功")
    lesson = input("   学到的教训是什么？> ").strip()
    if lesson:
        with open(_BACKLOG, 'a') as f:
            f.write(f"\n- [x] {datetime.now():%m-%d} 复盘: {task} → {lesson}")
        print(f"   ✅ 已写入 backlog.md")
    return lesson


def reflect():
    """完整 9 步反思循环。"""
    task = step1_assume_fault()
    record = step2_search_memory(task)
    if step3_skip_or_continue(record):
        return
    points = step4_weakest_point(task)
    traps = step5_who_built_trap()
    simple, generic, choice = step6_alternatives(task)
    plan = simple if choice == '1' else generic
    result = step7_execute(plan)
    if result == '':
        # 假设成功
        step9_review(task)
    else:
        # 报错
        step8_on_fail(task, result)


if __name__ == '__main__':
    reflect()
