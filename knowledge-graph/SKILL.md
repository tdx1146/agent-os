# graph_agent_os — Agent OS 全系统知识图谱 Skill

## 用途
自动扫描 Agent OS 六大组件（kernel/iso-sand/sandglass/monument/editor），
生成文件级依赖关系图谱（JSON + HTML 可视化），展示系统的"骨架"。

## 执行
```bash
python3 /vol1/@team/qh团队/QH/AI专用/Agent OS/knowledge-graph/skill_graph_agent_os.py
```

## 输出
- `Agent OS/knowledge-graph/knowledge-graph.json` — 图谱数据
- `Agent OS/knowledge-graph/call-graph.html` — 可视化页面（也可通过编辑器访问）

## 集成到 OpenClaw
可以在 AGENTS.md 中引用本文件，或在 cron 中定时触发图谱更新。
