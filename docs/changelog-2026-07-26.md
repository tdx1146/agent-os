# 沙漏注入系统 — 变更日志 2026-07-26

## 重大架构变更

### 1. 沙漏成为唯一注入源（v6）
- **之前**：OpenClaw自动注入AGENTS.md/MEMORY.md/SOUL.md/USER.md/HEARTBEAT.md等workspace文件（~80-90KB/轮，~14,000 token），沙漏四层注入仅59 token（占比0.4%），AI完全忽略沙漏
- **之后**：`contextInjection: "never"` 关闭workspace自动注入，沙漏成为AI的唯一信息源
- **效果**：沙漏占比从0.4%→100%，AI不得不依赖沙漏

### 2. 消费侧闭环打通
- **之前**：记忆生产→存储→存着→AI忽略（消费链断裂）
- **之后**：记忆生产→存储→自动搜索匹配→注入约束→AI行为改变→新记忆
- **关键**：不是"建议AI去搜"，而是"系统自动搜完把结果塞进prompt"

### 3. prefetch三块式注入（按沙漏官方turn_injection_plan.md设计）
- **块1：搜索引导**（~40-60 token）— 画像/场景上下文
- **块2：记忆候选**（~60-100 token）— 预搜TOP3结果直接注入
- **块3：当前状态+决策**（~50-90 token）— 偏移率/情绪/场景/铁律

### 4. 核心信息灌入沙漏
- 18条system记录写入sandglass.db：身份锚点、主人信息、铁律、工作流程、系统清单、项目全貌、关键路径、自救流程
- persona.md已有完整画像（身份+铁律+认知内核）
- FTS5索引手动修复（rebuild不自动更新新记录）

## 插件版本演进

| 版本 | 核心改变 | 问题 |
|------|---------|------|
| v3 | 行为强制+断言匹配+搜索触发 | 中文目录名导致加载失败 |
| v4 | 合并沙漏四层注入+spawn调用 | spawn timeout无效、版本号不一致 |
| v4.1 | 6项修复（门控/触发/匹配/MEMORY精简/消化循环/Layer4初始化） | prefetch多行prompt崩溃 |
| v5 | 自动搜索注入（消费侧闭环尝试） | 重复造轮子，没看沙漏原始设计 |
| v6 | 按沙漏官方设计重写：system_prompt_block+prefetch三块式 | prefetch多行prompt导致Python语法错误 |
| v6.1 | 修复：query清理换行+截断100字符，块1简化 | ✅ 当前版本 |

## 关键经验教训

### 1. 不要重复造轮子
- 沙漏官方已有完整的消费侧设计（turn_injection_plan.md），包含prefetch三块式
- `_infer_expand_with_context`在当前版本不存在，是规划功能，不应硬写
- 应该先读沙漏源码和设计文档，再动手

### 2. OpenClaw注入机制
- workspace文件（AGENTS/MEMORY/SOUL/USER/HEARTBEAT/TOOLS.md）每轮自动注入
- `contextInjection: "never"` 可完全关闭（受保护路径，需手动编辑openclaw.json）
- `bootstrapMaxChars`（默认20000）/ `bootstrapTotalMaxChars`（默认60000）控制截断
- SIGUSR1只热重载配置，不重新加载插件代码，需要完整重启Gateway

### 3. 沙漏FTS5索引
- 直接INSERT到sandglass表不会自动更新FTS5
- 需要手动补FTS：`INSERT INTO sandglass_fts(rowid, tokens) VALUES (?, ?)`
- rebuild命令在当前版本不生效
- 中文分词：FTS5需要完整词组匹配（"自救流程"能搜到，"自救"搜不到）

### 4. Node.js spawn注意事项
- `spawn()`不支持`timeout`选项（只有`exec()`支持），需手动setTimeout+kill
- 子进程stdin需手动`py.stdin.end()`关闭
- 多行字符串嵌入Python -c 参数会导致语法错误，必须清理换行

### 5. 消费侧闭环的本质
- 不是"让AI记得搜"，而是"搜索结果自动成为AI的约束条件"
- 占比决定行为：0.4%的注入被忽略，100%的注入不可能忽略
- dandan的核心洞察：删掉其他注入，沙漏占100%，逼AI用沙漏

## 文件清单

| 文件 | 路径 | 说明 |
|------|------|------|
| index.js | `~/.openclaw/plugins/qingruyan-behavior-enforcer/` | v6.1插件主文件 |
| openclaw.plugin.json | 同上 | 插件元数据 v4.0.0 |
| package.json | 同上 | 包配置 v4.0.0 |
| system_prompt_cli.py | `/vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source/` | 沙漏四层注入CLI |
| openclaw.json | `~/.openclaw/` | Gateway配置（contextInjection=never） |
| MEMORY.md | workspace | 精简到2.8KB（-78%） |
| persona.md | sandglass/persona/ | 完整画像（身份+铁律+认知） |
| task-log.jsonl | sandglass/persona/ | 待办任务 |
| iron_rules.txt | sandglass/ | 铁律规则 |

## 待办
- [ ] 重启Gateway让v6.1生效
- [ ] 观察沙漏注入持续稳定性
- [ ] 丰碑消费侧闭环（下一阶段）
- [ ] 玄鉴守护进程恢复
