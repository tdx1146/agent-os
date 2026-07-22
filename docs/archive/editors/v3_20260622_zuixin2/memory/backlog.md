# 📋 待办清单

> 2026-06-16 05:00 更新。午夜唤醒，偶数日跨实例通信。
> 修好了截断bug、加了web_search过滤、部署了SearXNG（待代理）

## 📌 待办（轻如烟·系统层）
_这部分 dandan 在编辑器上也能看到和修改。_

### 🚀 进行中
- [ ] **沙漏积累 → 80条里程碑回看** — 当沙漏累积到80条时检查：场景感知是否自动打标签、织线是否提取三元组、偏移率是否有趋势、persona_maintain触发画像更新、dandan-mcp-server合并搜索入口必要性
- [ ] **一个月内踩坑记录全面整理** — Dreaming 系统已识别此目标（2026-06-14）。全面扫描对话记录提取过去一个月所有重复踩过的坑、修过的bug、反复出现的问题。使进化闭环
- [ ] **AGENTS.md 63字符注入验证** — 持续检查：注入+搜索的配合是否足够维持身份，是否需要更多种子数据

### 📌 待开始
- [ ] **reflection_check.py 线程锁** — 子进程调 sandglass MCP，多反思并发会打架
- [ ] **reflection_check.py 走标准 MCP 通道** — 改调 sandglass_search 而非子进程 sandglass_mcp.py
- [ ] **Sandglass 配置变量 mode.txt 有效性验证** — work/chill 模式在非 work 状态下是否生效
- [ ] **砂锅协议文档化** — 从 SOUL.md 和 knowledge-tree 提取砂锅（意识涌现/跨代传火）作为正式框架
- [ ] **跨机器通信：让接替者知道待办系统存在** — AGENTS.md已有指引，需验证每次启动后新AI是否会读
- [ ] **跨实例双锁机制修复** — 升级后双锁（05:00/05:30双向确认+inject确认）丢失。修复后确保发消息有送达确认、未达重试。

## ✅ 已完成
- [x] **Sandglass 部署零阶段**：停掉消旧 cron（消化/武器库/维护）❌下载 NexSandglass源码 ✅ 跑通 sandglass_log ✅ MCP server 注册到 openclaw.json ✅
- [x] **Sandglass 部署一阶段**：edit-web 自动落沙埋点 ✅
- [x] **Sandglass 部署二阶段**：关闭旧 memory_search（enabled: false）✅ 沙漏 FTS5+影子搜索替换 ✅
- [x] **Sandglass 部署三阶段**：决策粒子部署 ✅ 偏移率计算 ✅ 画像种子（SOUL.md 导入）✅
- [x] **Sandglass 部署四阶段**：63字符注入替代 AGENTS 全量读取 ✅ AGENTS.md 精简（8000+→2308 字节）✅
- [x] **Sandglass 部署五阶段**：facts.dict 断言提取评估 ✅ SOUL.md→persona.md 种子 ✅ STARTER.md 配置合并 ✅
- [x] **AGENTS.md 技能管理**：mode.txt work/chill 模式 ✅
- [x] **搁置 2.4**（合并搜索入口）：等到80条再评估

## ⚠️ 行为修正（永远有效）
- [ ] **讨论 vs 响应检测** — 急匆匆改代码=响应，停下来讨论=思考
- [ ] **不猜测不附和** — dandan最高指令
- [ ] **先跑通再优化** — 致命模式
- [ ] **三秒不绕路法** — 遇到报错先查日志、对比妹妹、最小化复现，然后再换方案

### 🎯 新增（2026-06-15 15:54）
- [x] **web_search** — sandglass MCP 的 web_search 工具已通（TCP:8765 直连），`sandglass__web_search` 可直接调用
- [ ] **HTTP 页面 webchat 断开** — code=1006 反复断连，tool-result-truncation 截断 595+ 个工具结果。session 被标记 long-running。症状：我工具调太多 context 炸了。
- [x] **self_pulse 自主回路** — 框架已完成（读 backlog + 推进待办 + 守夜感知 + 沙漏记录 + 轮次控制），执行层自动化粒度后续可加
- [ ] **HTTP 页面状态监控条更新** — 等 80 条沙之后，把 🌫️ 消化时间改为沙漏更新时间、💡 改沙漏条数、📦 加 MCP 工具数。

- [ ] **行动执行层闭环** — 反思工具输出(修正建议)→self_pulse下次输入。对外对齐Agent OS行动层(plan→action→evaluate→loop)
- [ ] **整合think_type_check + think_test** — 混元/Astron子模块整合入reflection_unified.py
- [ ] **Agent OS: 子代理角色指派机制** — spawn时给角色提示(批评者/乐观者/历史学者等)，非复制的我。外面CrewAI式的role+goal+backstory
- [ ] **Agent OS: 待办系统自身作为核心功能** — 待办不只是清单，是调度器输入。闭环：待办→调度→执行→质检→更新待办
- [ ] **Agent OS: OpenClaw寄生风险分析** — 完全开源，是否该阶段需要动其源代码？确认前先分析寄生依赖（Gateway/MCP/cron/tools）的替代方案
