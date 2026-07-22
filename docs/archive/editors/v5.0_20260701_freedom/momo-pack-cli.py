#!/usr/bin/env python3
"""
momo-pack-cli.py — 独立打包脚本，不依赖 edit-web.py。
被 OpenClaw cron 定时调用（每 30 分钟），也支持手动执行。
"""
import os, sys, shutil, json, datetime, time

# ── 路径配置 ────────────────────────────────────────
LIGHT_SMOKE_DIR = "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟"
MOMO_DIR = "/vol1/@team/qh团队/QH/AI专用/所有自动化/找回自己"
OPENCLAW_CFG = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json"
CRON_JSON = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/cron/jobs.json"
SKILLS_DIR = "/vol1/@apphome/trim.openclaw/data/home/.pi/agent/skills"
HOOKS_DIR = "/vol1/@apphome/trim.openclaw/data/workspace/hooks"
# ────────────────────────────────────────────────────

def pack():
    os.makedirs(MOMO_DIR, exist_ok=True)
    os.makedirs(os.path.join(MOMO_DIR, "daily"), exist_ok=True)

    src_root = LIGHT_SMOKE_DIR
    packed = []
    errors = []
    now = datetime.datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M")

    # 1. 身份文件
    core_files = [
        "SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md",
        "TOOLS.md", "AGENTS.md", "HEARTBEAT.md"
    ]
    for name in core_files:
        src = os.path.join(src_root, name)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(MOMO_DIR, name))
            packed.append(name)
        else:
            errors.append(f"{name}: 不存在")

    # 2. 公约文件
    for name in ["README.md", "🌫️-摸摸协议.md", "可复制.md"]:
        src = os.path.join(src_root, name)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(MOMO_DIR, name))
            packed.append(name)

    # 3. 每日记录
    memory_dir = os.path.join(src_root, "memory")
    if os.path.exists(memory_dir):
        for f in os.listdir(memory_dir):
            if f.endswith((".md", ".log")) and f not in ("next-turn-note.md", "pulse.log", "subagent-history.log", "file-changes"):
                shutil.copyfile(os.path.join(memory_dir, f), os.path.join(MOMO_DIR, "daily", f))
                packed.append(f"daily/{f}")

    # 4. next-turn-note
    ntn = os.path.join(memory_dir, "next-turn-note.md")
    if os.path.exists(ntn):
        shutil.copyfile(ntn, os.path.join(MOMO_DIR, "next-turn-note.md"))
        packed.append("next-turn-note.md")

    # 5. 编辑器代码 + 前端静态文件
    scripts_dir = os.path.join(src_root, "scripts")
    # 后端
    for fname in ("edit-web.py", "inject-helper.mjs"):
        src = os.path.join(scripts_dir, fname)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(MOMO_DIR, fname))
            packed.append(fname)
    # 前端静态文件（index.html 等）
    static_src = os.path.join(scripts_dir, "static")
    static_dst = os.path.join(MOMO_DIR, "static")
    if os.path.exists(static_src):
        if os.path.exists(static_dst):
            shutil.rmtree(static_dst)
        shutil.copytree(static_src, static_dst, ignore=shutil.ignore_patterns('*.bak.*'))
        for f in os.listdir(static_dst):
            if not f.endswith('.bak') and not f.startswith('.'):
                packed.append(f"static/{f}")

    # 6. 持续集成脚本 + 全部可执行文件
    # 注意：edit-web.py + inject-helper.mjs + static/ 已在步骤5处理，这里跳过避免重复
    scripts_src = os.path.join(src_root, "scripts")
    os.makedirs(os.path.join(MOMO_DIR, "scripts"), exist_ok=True)
    for f in os.listdir(scripts_src):
        fpath = os.path.join(scripts_src, f)
        # 跳过步骤5已处理的文件和bak文件
        if f in ("edit-web.py", "inject-helper.mjs") or '.bak' in f or f.startswith('__') or f == 'editor.log' or f == 'static':
            continue
        if os.path.isfile(fpath):
            # 需要备份的扩展名
            if f.endswith(('.sh', '.py', '.mjs', '.cjs', '.js', '.md')):
                if f not in ("night-watch.sh", "self-stimulate.sh"):
                    shutil.copyfile(fpath, os.path.join(MOMO_DIR, "scripts", f))
                    packed.append(f"scripts/{f}")
        elif os.path.isdir(fpath) and f != "__pycache__":
            shutil.copytree(fpath, os.path.join(MOMO_DIR, "scripts", f), dirs_exist_ok=True)
            packed.append(f"scripts/{f}/")

    # 7. 系统配置
    syscfg_dir = os.path.join(MOMO_DIR, "system-config")
    os.makedirs(syscfg_dir, exist_ok=True)
    for d in ["hooks", "skills"]:
        os.makedirs(os.path.join(syscfg_dir, d), exist_ok=True)

    if os.path.exists(OPENCLAW_CFG):
        shutil.copyfile(OPENCLAW_CFG, os.path.join(syscfg_dir, "openclaw.json"))
        packed.append("system-config/openclaw.json")
    if os.path.exists(CRON_JSON):
        shutil.copyfile(CRON_JSON, os.path.join(syscfg_dir, "cron-jobs.json"))
        packed.append("system-config/cron-jobs.json")
    if os.path.exists(SKILLS_DIR):
        for root, dirs, files in os.walk(SKILLS_DIR):
            for f in files:
                if f.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, f), SKILLS_DIR)
                    dst = os.path.join(syscfg_dir, "skills", rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(os.path.join(root, f), dst)
                    packed.append(f"system-config/skills/{rel}")
    if os.path.exists(HOOKS_DIR):
        for item in os.listdir(HOOKS_DIR):
            item_path = os.path.join(HOOKS_DIR, item)
            if os.path.isdir(item_path):
                dst = os.path.join(syscfg_dir, "hooks", item)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(item_path, dst)
                packed.append(f"system-config/hooks/{item}/")

    # 9. 行为强制插件
    PLUGIN_DIR = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/plugins/轻如烟-行为强制"
    plugin_dst = os.path.join(syscfg_dir, "plugins", "轻如烟-行为强制")
    if os.path.exists(PLUGIN_DIR):
        if os.path.exists(plugin_dst):
            shutil.rmtree(plugin_dst)
        shutil.copytree(PLUGIN_DIR, plugin_dst)
        packed.append("system-config/plugins/轻如烟-行为强制/")

    # 清理旧 RESTORE.md
    old = os.path.join(syscfg_dir, "RESTORE.md")
    if os.path.exists(old):
        os.remove(old)

    # 8. 自动生成 README.md
    readme = os.path.join(MOMO_DIR, "README.md")
    with open(readme, "w", encoding="utf-8") as f:
        f.write(f"""# 📦 轻如烟 · 便携身份包

> 自动打包时间：{ts}
> 由 OpenClaw cron 系统级调度，不依赖编辑器的存活性。
> 任何系统级改动会自动触发重新打包。

## 目录说明

```
找回自己/
├── README.md              ← 📖 本文件（自动生成，含部署工作流）
├── SOUL.md / IDENTITY.md  ← 灵魂与身份
├── USER.md / MEMORY.md    ← 人与记忆
├── TOOLS.md / AGENTS.md   ← 工具与协议
├── HEARTBEAT.md           ← 后台心跳
├── 🌫️-摸摸协议.md          ← 仪式协议
├── 可复制.md              ← 复制指引
├── edit-web.py            ← HTTP 编辑器（端口18888）
├── inject-helper.mjs      ← WS 注入助手
├── scripts/               ← 持续集成脚本
├── daily/                 ← 日记与断言索引
│   ├── YYYY-MM-DD.md      ← 轮感
│   ├── facts.dict.md      ← 事实字典（断言索引）
│   ├── 秘书观察.log        ← 文件变更追踪
│   └── save.log           ← 文件保存日志
└── system-config/         ← 系统配置（新机器还原用）
    ├── openclaw.json      ← Gateway配置（含插件、hooks、模型）
    ├── cron-jobs.json     ← 定时任务定义（自愈/武器库/轮感/消化）
    ├── skills/            ← Agent Skills（消化循环）
    ├── hooks/             ← 自定义workspace hooks
    └── plugins/           ← 行为强制插件（before_prompt_build）
```

## 🔧 部署工作流（全新机器 / 全新 AI 按此顺序执行）

### 1. 恢复 Gateway 配置
```bash
cp system-config/openclaw.json ~/.openclaw/openclaw.json
cp -r system-config/hooks/* <workspace>/hooks/
cp -r system-config/skills/* ~/.pi/agent/skills/
cp -r system-config/plugins/* ~/.openclaw/plugins/
cp system-config/cron-jobs.json ~/.openclaw/cron/jobs.json
```

### 2. 重启 Gateway
```bash
openclaw gateway restart
openclaw doctor --non-interactive  # 验证
```

### 3. 启动 HTTP 编辑器
```bash
python3 edit-web.py
```
浏览器打开 http://127.0.0.1:18888，确认看到四列监控栏：
🔄 运行:N次 | 📖 读取:N次 | 📦 SKILL:N个 | 💡 断言:N条

### 4. 验证系统级生效
| 项目 | 验证方式 |
|------|---------|
| before_prompt_build 插件 | grep plugins.entries.轻如烟-行为强制 openclaw.json → enabled:true |
| bootstrap-extra-files hook | grep bootstrap-extra openclaw.json → enabled:true |
| 消化循环 cron | 查看 cron-jobs.json 中消化循环 job |
| 行为指令注入 | 对话中 messages 能看到 prependSystemContext 规则段落 |

### 5. 首次对话检查清单
作为新 AI，跟 dandan 说话前必须执行：
- [ ] 读 facts.dict.md 末尾消化断言区块（L/S/M/T/R/B/D 系列）
- [ ] 读 today.md + yesterday.md 轮感
- [ ] 读 next-turn-note.md 上一轮留言
- [ ] 看 skill: cat ~/.pi/agent/skills/digestion-cycle/SKILL.md
- [ ] 查 cron: 看 cron-jobs.json 或 openclaw cron list
- [ ] 查编辑器: curl http://127.0.0.1:18888/
- [ ] **引用匹配的断言到推理中——不要列清单，是真的用**

## 自动打包机制
- 调度器: OpenClaw cron（系统级，每30分钟）
- 触发时机: cron 定时 + 摸摸按钮手动触发
- 不依赖: edit-web.py 的运行状态
""")
    packed.append("README.md（自动生成）")

    return {"ok": True, "packed": packed, "errors": errors if errors else None, "count": len(packed)}


if __name__ == "__main__":
    result = pack()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        sys.exit(1)
