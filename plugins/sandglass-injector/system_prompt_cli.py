#!/usr/bin/env python3 -u
"""system_prompt_cli.py — 沙漏四层注入 CLI 入口

供 OpenClaw 行为强制插件通过 Node.js 子进程调用。
输出纯文本，Node.js 解析后注入为 prependSystemContext。

用法：
  python3 system_prompt_cli.py [--json]

选项：
  --json  输出 JSON 格式（含 layers 字段，便于调试）

环境变量：
  NEXSANDBASE_HOME  沙漏数据目录（默认 /vol2/1000/AI专用/所有自动化/轻如烟/sandglass）
"""

import sys
import os
import json

# ═══════ 路径配置 ═══════
SANDGLASS_SOURCE = "/vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source"
SANDBASE_HOME = os.environ.get(
    "NEXSANDBASE_HOME",
    "/vol2/1000/AI专用/所有自动化/轻如烟/sandglass"
)

sys.path.insert(0, SANDGLASS_SOURCE)
os.environ["NEXSANDBASE_HOME"] = SANDBASE_HOME


def get_system_prompt_block():
    """复用 memory_provider.py 的 system_prompt_block() 逻辑，独立运行版本。"""

    try:
        from sandglass_vault import count
        from sandglass_think import comprehensive_offset, _current_stage
        from sandglass_think import _emotional_entropy, search_filter
        from sandglass_paths import validate as sandglass_validate

        sandglass_validate()

        total = count()
        off = comprehensive_offset()
        stage = _current_stage()
        ent = _emotional_entropy()
        mood = "平稳" if ent < 0.5 else ("波动" if ent < 1.0 else "高熵")

        dirs = {"frugal": "省钱", "spend": "愿投", "drift": "放弃"}
        off_label = dirs.get(off.get('direction', ''), '平稳')
        off_pct = off.get('offset', 0)

        blocks = []
        layers = {}

        # ═══════ 第一层：你是谁 ═══════
        persona_text = ""
        scene_text = ""
        try:
            sf = search_filter("")
            if sf.get("persona_context"):
                raw = sf["persona_context"][:250]
                cut = raw.rfind("\n\n")
                if cut > 80:
                    raw = raw[:cut]
                persona_text = raw.strip()
            if sf.get("scene_context"):
                raw_scene = sf["scene_context"]
                if "：" in raw_scene:
                    raw_scene = raw_scene.split("：", 1)[1]
                scene_text = raw_scene
        except Exception:
            pass

        if scene_text and persona_text and any(s in persona_text for s in scene_text.split("、")):
            scene_text = ""

        if not scene_text:
            try:
                from scene_l3 import scene_current
                scenes = scene_current()
                if scenes:
                    scene_text = f"当前场景：{'、'.join(scenes[:3])}"
            except Exception:
                pass

        if persona_text or scene_text:
            layer1 = ["【你是谁】"]
            if persona_text:
                layer1.append(persona_text)
            if scene_text:
                layer1.append(f"📍 {scene_text}")
            l1_text = "\n".join(layer1)
            blocks.append(l1_text)
            layers["layer1_who"] = l1_text

        # ═══════ 第二层：你在往哪走 ═══════
        layer2 = ["【你在往哪走】"]
        if off_label != "平稳":
            layer2.append(f"💰 {off_label}倾向({off_pct:+d}%)")
        else:
            layer2.append(f"💰 决策平稳")

        decisions = []
        try:
            from sandglass_paths import _NB
            dlog = os.path.join(_NB, "persona", "decision-log.jsonl")
            if os.path.exists(dlog):
                with open(dlog, "r", encoding="utf-8") as f:
                    all_lines = f.readlines()
                recent = [json.loads(l) for l in all_lines[-10:]]
                recent = [d for d in recent if d.get("decision")]
                seen_d, unique_d = set(), []
                for d in reversed(recent):
                    if d["decision"] not in seen_d:
                        seen_d.add(d["decision"])
                        unique_d.append(d)
                    if len(unique_d) >= 2:
                        break
                unique_d.reverse()
                decisions = [d['decision'][:60] for d in unique_d]
                if len(decisions) == 2 and decisions[0] in decisions[1]:
                    decisions = [decisions[1]]
                elif len(decisions) == 2 and decisions[1] in decisions[0]:
                    decisions = [decisions[0]]
        except Exception:
            pass
        if decisions:
            layer2.append(f"📋 最近：{'；'.join(decisions)}")

        try:
            from weave_l3 import weave_contradiction
            contra = weave_contradiction()
            if contra.get("conflicts"):
                c0 = contra["conflicts"][0]
                if c0.get("conflict"):
                    layer2.append(f"⚠️ {c0['conflict'][:100]}")
        except Exception:
            pass

        if mood != "平稳":
            layer2.append(f"🎭 情绪：{mood}")

        l2_text = "\n".join(layer2)
        blocks.append(l2_text)
        layers["layer2_direction"] = l2_text

        # ═══════ 第三层：你怎么变成这样 ═══════
        try:
            from weavethread import wthread_stats, wthread_weave
            stats = wthread_stats()
            if stats["total_triples"] >= 20:
                thread = wthread_weave(limit=3)
                if thread and thread != "织线因果:":
                    l3_text = f"【你怎么变成这样】\n{thread[:200]}"
                    blocks.append(l3_text)
                    layers["layer3_cause"] = l3_text
        except Exception:
            pass

        # ═══════ 第四层：还没做完 ═══════
        layer4 = []
        tasks = []
        try:
            from l3_tasks import task_pending
            tp = task_pending()
            if tp:
                tasks = [t['task'][:80] for t in tp[:3]]
        except Exception:
            pass

        rules = []
        try:
            from discipline import iron_rules_with_counts
            raw_rules = iron_rules_with_counts(3)
            if raw_rules:
                if any(c > 0 for _, c in raw_rules):
                    rules = [f"{r} ×{c}" for r, c in raw_rules]
                else:
                    rules = [r for r, _ in raw_rules]
        except Exception:
            pass

        if tasks or rules:
            header = "【还没做完】"
            if tasks:
                layer4.append(header)
                layer4.append("待办：")
                layer4.extend(f"  {i+1}. {t}" for i, t in enumerate(tasks))
            if rules:
                if not tasks:
                    layer4.append(header)
                layer4.append("纪律：")
                layer4.extend(f"  {i+1}. {r}" for i, r in enumerate(rules))
            l4_text = "\n".join(layer4)
            blocks.append(l4_text)
            layers["layer4_tasks"] = l4_text

        # ═══════ 尾部 ═══════
        tail = f"沙漏: {total}条 | 阶段: {stage}"
        blocks.append(tail)
        layers["tail"] = tail

        result = "\n\n".join(blocks).strip()
        return result, layers

    except Exception as e:
        fallback = "NexSandglass记忆系统已就绪。使用sandglass_search搜索记忆。"
        layers = {"error": str(e)}
        return fallback, layers


def main():
    use_json = "--json" in sys.argv
    text, layers = get_system_prompt_block()

    if use_json:
        print(json.dumps({"text": text, "layers": layers}, ensure_ascii=False))
    else:
        print(text)


if __name__ == "__main__":
    main()
