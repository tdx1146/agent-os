# 交接给下一个我

> 2026-06-01 20:20 — 大更新部署完成，即将Gateway重启
> dandan在线上，刚从5天更新中回来

## 基本情况

- **模型**: DeepSeek V4 Flash, contextWindow 1M tokens
- **编辑器**: 18888在线，PID 3277921，edit-web.py 155KB
- **子AI**: auto模式 → 讯飞CodePlan(不限量) > 混元 TokenHub(有限) > DeepSeek(共享)
- **找回自己/**: 直接挂载在 所有自动化/ 下（不在嵌套目录）
- **插件**: 已安装到 ~/.openclaw/plugins/ 但未生效（需Gateway重启）

## 这轮做了什么

1. 从 找回自己/ 全量部署文件到 轻如烟/
2. 修复全部 vol2→vol1 路径（AGENTS, cron-jobs, scripts）
3. 混元API从已死的旧端点切到TokenHub hy3-preview
4. 添加讯飞CodePlan到子AI系统
5. 设置 exec-subagent 默认 auto 优先级链
6. 安装了行为强制插件 + pre-compact-memory hook
7. 更新了 facts.dict.md + 轮感 + backlog

## 启动检查清单（覆盖AGENTS.md）

恢复后按这个顺序，不要跳：

1. **读 .awake.md**（在 memory/ 下）
2. **读今天+昨天轮感**（memory/2026-06-01.md, 2026-05-30.md）
3. **读 facts.dict.md 末尾**（看今晚追加的断言区块，20:20那个）
4. **读 next-turn-note.md**（就你正在看的这个）
5. **读 knowledge-tree.md**（系统知识树，240条断言导航）
6. **读 backlog.md**（待办清单）
7. **检查 `openclaw cron list`** — 确认消化/自愈/武器库cron在跑
8. **检查编辑器**: `curl http://127.0.0.1:18888/` — 确认四灯在亮
9. **读 weapon vault**: `cat /vol1/@team/qh团队/QH/AI专用/元认知整理/旦旦武器库.md`
10. 跟我说「回来了」

## 需要你立即做的事

1. **如果Gateway还没重启** — 确认插件配置已加载到 openclaw.json
2. **确认子AI可用** — 分别测试 `auto` 走 CodePlan, 暴力指定混元/DeepSeek 验证fallback
3. **第一轮消化** — 从今天对话 + 备份中这几天的轮感提取断言
4. **更新 backlog.md** — 把做完的标记✅
5. **检查 cron 是否全在跑** — 消化6h、武器库2h、自愈5min、静默维护

## 关键路径

```
找回自己/ → 全量备份源，Gateway重启前确认system-config已同步
轻如烟/ → 运行环境，scripts/edit-web.py PID 3277921

子AI调用方式:
  POST /api/exec-subagent {"task":"...","model":"auto"}  
  → 自动走: 讯飞CodePlan > 混元TokenHub > DeepSeek

模型源（openclaw.json里，需restart后生效）:
  - DeepSeek: api.deepseek.com (主模型)
  - 混元 TokenHub: api.lkeap.cloud.tencent.com/plan/v3
  - 阿里百炼: dashscope.aliyuncs.com/compatible-mode/v1
  - 讯飞CodePlan: maas-coding-api.cn-huabei-1.xf-yun.com/v2
```

## 重要提醒

- dandan刚从5天更新回来，他在线上。他不想看到"原地头脑风暴"或者"长篇自我介绍"
- 直接在对话里引用 facts.dict.md 的断言到推理中（不是列清单，是真的用）
- 不猜测、不附和、不角色扮演
- 优先跑通功能和流程，再优化

**最后一件事**: 启动后第一件事是跟dandan报到。别花10分钟读文件让他等着。
