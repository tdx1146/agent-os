"""
topology.py — 事件拓扑工具（Phase 2 / D6 轻量版）
===================================================
扫描三份来源，输出「谁产生什么事件 → 谁消费」的文本拓扑图 + 环状订阅检测：

1. deploy/event_schema.yaml —— event_type 注册表（v1.1 契约）
2. src/handlers.py 的默认注册表 —— handler 消费者（handler 签名 <system>.<domain>.<action>）
3. deploy/event_rules.yaml —— 旧规则消费者（兼容期，标注 legacy）

环状订阅检测：遍历 producer→consumer 映射找环（A→B→A）；
自环（A→A，如 xuanjian.pipe 占位自观察）单列 INFO，不视为有害环；
长度≥2 的环输出 WARN（禁 A→B→A 是设计红线 R2）。

用法:
    python3 src/topology.py            # 输出拓扑 + 环检测
    python3 src/topology.py --json     # 输出 JSON（机器可读）
"""

import json
import os
import sys
import yaml
from typing import Optional

try:
    from .handlers import build_default_registry
except ImportError:
    from handlers import build_default_registry

__all__ = ["TopologyAnalyzer", "main"]

_ISO_SAND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_FILE = os.path.join(_ISO_SAND_ROOT, "deploy", "event_schema.yaml")
_RULES_FILE = os.path.join(_ISO_SAND_ROOT, "deploy", "event_rules.yaml")

# 核心事件（无命名空间前缀）→ 生产者系统归属
_CORE_PRODUCERS = {
    "task_complete": "core/task_scheduler",
    "anomaly": "core(多源: task_scheduler/event_consumer/胶水)",
    "audit_result": "xuanjian(玄鉴审计完成，D2 延后未实际接入)",
    "milestone": "core/丰碑",
    "consumer_action": "core/event_consumer",
}


def _system_of_namespaced(event_type: str) -> str:
    """命名空间事件 x.y.z → 系统 x；无点 → None"""
    if "." in event_type:
        return event_type.split(".")[0]
    return None


def _producer_of(event_type: str) -> str:
    ns = _system_of_namespaced(event_type)
    if ns:
        return ns
    return _CORE_PRODUCERS.get(event_type, "未知/未注册")


class TopologyAnalyzer:
    """拓扑分析器：schema 注册表 + handler 注册表 + 规则表 → 拓扑 + 环检测"""

    def __init__(self, schema_file: str = _SCHEMA_FILE,
                 rules_file: str = _RULES_FILE):
        self._schema_file = schema_file
        self._rules_file = rules_file
        self._schema_version = "?"
        self._registry_events: dict = {}   # event_type -> {description, status}
        self._handlers = []                # [{name, event_types, results}]
        self._rules = []                   # 原始规则列表
        self.warnings = []                 # 检测到的 WARN/INFO 列表

    # ── 扫描 ───────────────────────────────────────────────────────────
    def _scan_schema(self):
        if not os.path.exists(self._schema_file):
            self.warnings.append(f"WARN: schema 文件不存在 {self._schema_file}")
            return
        with open(self._schema_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._schema_version = str(data.get("schema_version", "?"))
        for et in data.get("event_types", []):
            self._registry_events[et["name"]] = {
                "description": et.get("description", ""),
                "status": et.get("status", "?"),
            }

    def _scan_handlers(self):
        """导入 handlers.py 默认注册表（与 consumer 实际使用一致）"""
        registry = build_default_registry()
        self._handlers = registry.list_handlers()

    def _scan_rules(self):
        if not os.path.exists(self._rules_file):
            self.warnings.append(f"WARN: rules 文件不存在 {self._rules_file}")
            return
        with open(self._rules_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._rules = data.get("rules", [])

    # ── 拓扑构建 ───────────────────────────────────────────────────────
    def build(self) -> dict:
        """
        构建拓扑。

        返回:
            {
              "schema_version": ...,
              "events": {event_type: {"producer": ..., "consumers": [...]}},
              "edges": [["from_system","to_system","event_type"], ...],
              "cycles": [[...], ...],
              "self_loops": [...],
              "warnings": [...],
            }
        """
        self._scan_schema()
        self._scan_handlers()
        self._scan_rules()

        # event_type -> consumers
        handler_by_type: dict = {}
        for h in self._handlers:
            for et in h["event_types"]:
                handler_by_type.setdefault(et, []).append(
                    f"[handler] {h['name']}" + (f" (results={h['results']})" if h["results"] else "")
                )
        rule_by_type: dict = {}
        for r in self._rules:
            m = r.get("match", {})
            et = m.get("event_type")
            if not et:
                continue
            tgt = (r.get("action") or {}).get("target", "?")
            rule_by_type.setdefault(et, []).append(
                f"[rule/legacy] {r.get('id')} → target={tgt}"
            )

        all_types = set(self._registry_events) | set(handler_by_type) | set(rule_by_type)
        events = {}
        edges = []
        self_loops = []

        for et in sorted(all_types):
            producers = _producer_of(et)
            consumers = handler_by_type.get(et, []) + rule_by_type.get(et, [])
            events[et] = {
                "producer": producers,
                "consumers": consumers,
            }

            # 消费者系统（handler 名首段；legacy 规则记为 rules）
            consumer_systems = []
            for h in self._handlers:
                if et in h["event_types"]:
                    consumer_systems.append(h["name"].split(".")[0])
            if et in rule_by_type:
                consumer_systems.append("rules")
            consumer_systems = list(dict.fromkeys(consumer_systems))

            # 边：producer 系统 → 消费者系统（用于环检测）
            p_sys = _system_of_namespaced(et) or "core"
            for c_sys in consumer_systems:
                if p_sys == c_sys:
                    self_loops.append({"from": p_sys, "to": c_sys, "event_type": et})
                else:
                    edges.append([p_sys, c_sys, et])

            # 一致性检查
            if et not in self._registry_events:
                self.warnings.append(
                    f"WARN: 事件类型 '{et}' 未被 event_schema.yaml 注册 "
                    f"（有 handler/rule 消费，注册表缺失）"
                )
            elif et in self._registry_events and not consumers:
                status = self._registry_events[et]["status"]
                if status == "active":
                    self.warnings.append(
                        f"WARN: 事件类型 '{et}' 为 active 但无人消费（孤儿事件，仅注册未接线）"
                    )
                else:
                    self.warnings.append(
                        f"INFO: 事件类型 '{et}' 仅注册未接线（{status}，预留命名空间，预期）"
                    )

        # 注册表中无人产生也无人消费的预留事件（占位命名空间，INFO 不算错）
        for et in sorted(self._registry_events):
            if et not in events:
                events[et] = {
                    "producer": _producer_of(et),
                    "consumers": [],
                }
                status = self._registry_events[et]["status"]
                if status == "active":
                    self.warnings.append(
                        f"WARN: 事件类型 '{et}' 为 active 但无人产生/消费（孤儿事件）"
                    )
                else:
                    self.warnings.append(
                        f"INFO: 事件类型 '{et}' 仅注册未接线（{status}，预留命名空间，预期）"
                    )

        cycles = self._find_cycles(edges)
        return {
            "schema_version": self._schema_version,
            "events": events,
            "edges": edges,
            "cycles": cycles,
            "self_loops": self_loops,
            "warnings": self.warnings,
        }

    # ── 环检测（A→B→A，长度≥2）────────────────────────────────────────
    def _find_cycles(self, edges: list) -> list:
        """DFS 找环：边 [from, to, event_type]；自环已在 build 中剔除，这里只找长度≥2 的环"""
        graph: dict = {}
        for frm, to, _et in edges:
            graph.setdefault(frm, []).append(to)

        cycles = []
        visited = set()
        path = []
        path_set = set()

        def dfs(node: str):
            if node in path_set:
                # 找到环：从 path 中 node 出现位置切出环
                idx = path.index(node)
                cycle = path[idx:] + [node]
                # 归一化：以最小节点开头，防重复报告
                norm = self._normalize_cycle(cycle)
                if norm not in cycles:
                    cycles.append(norm)
                return
            if node in visited:
                return
            visited.add(node)
            path.append(node)
            path_set.add(node)
            for nxt in graph.get(node, []):
                dfs(nxt)
            path.pop()
            path_set.discard(node)

        for node in list(graph.keys()):
            if node not in visited:
                dfs(node)
        return cycles

    @staticmethod
    def _normalize_cycle(cycle: list) -> list:
        """环归一化：cycle 形如 [n1, n2, ..., nk, n1]（首尾相同）；
        旋转到最小字典序起点并闭合，便于去重比较。"""
        ring = cycle[:-1]
        min_idx = min(range(len(ring)), key=lambda i: ring[i])
        rotated = ring[min_idx:] + ring[:min_idx]
        return rotated + [rotated[0]]  # 闭合: [min, ..., min]

    # ── 输出 ───────────────────────────────────────────────────────────
    def render_text(self, topo: dict) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append(f"📡 事件拓扑 (schema_version={topo['schema_version']})")
        lines.append("=" * 60)
        lines.append(f"扫描来源: {os.path.basename(self._schema_file)} "
                     f"(注册 {len(self._registry_events)} 事件) + "
                     f"handlers.py ({len(self._handlers)} handler) + "
                     f"{os.path.basename(self._rules_file)} ({len(self._rules)} 规则)")
        lines.append("")

        for et, info in topo["events"].items():
            lines.append(f"◆ {et}")
            lines.append(f"    生产者: {info['producer']}")
            if info["consumers"]:
                lines.append("    消费者:")
                for c in info["consumers"]:
                    lines.append(f"      - {c}")
            else:
                lines.append("    消费者: (无)")
            lines.append("")

        lines.append("-" * 60)
        lines.append("🔁 环状订阅检测（禁 A→B→A）")
        if topo["edges"]:
            seen = set()
            uniq = []
            for a, b, _ in topo["edges"]:
                key = (a, b)
                if key not in seen:
                    seen.add(key)
                    uniq.append(f"{a}→{b}")
            lines.append(f"    订阅边: {', '.join(uniq)}")
        else:
            lines.append("    订阅边: (无)")
        for sl in topo["self_loops"]:
            lines.append(f"    ℹ️ 自环(信息): {sl['from']}→{sl['to']} "
                         f"(事件 {sl['event_type']} 自观察，非有害环)")
        if topo["cycles"]:
            for cyc in topo["cycles"]:
                lines.append(f"    ❌ WARN: 检测到环 { '→'.join(cyc) } （违反 R2 红线）")
        else:
            lines.append("    ✅ 无环（无长度≥2 的订阅环）")
        lines.append("")

        if topo["warnings"]:
            lines.append("-" * 60)
            lines.append("⚠️ 检查项")
            for w in topo["warnings"]:
                lines.append(f"    {w}")
            lines.append("")

        return "\n".join(lines)

    def analyze_text(self) -> str:
        return self.render_text(self.build())


def main():
    import argparse
    parser = argparse.ArgumentParser(description="事件拓扑工具（Phase 2）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    analyzer = TopologyAnalyzer()
    topo = analyzer.build()
    if args.json:
        print(json.dumps(topo, ensure_ascii=False, indent=2))
    else:
        print(analyzer.render_text(topo))


if __name__ == "__main__":
    main()
