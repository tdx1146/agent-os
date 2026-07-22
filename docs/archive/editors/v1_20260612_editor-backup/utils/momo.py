#!/usr/bin/env python3
"""
🌫️ 摸摸协议 — momo 函数集

从 edit-web.py 拆分，自包含模块。
需要调用方传入配置路径（如 MOMO_DIR、LIGHT_SMOKE_DIR）。
"""

import os
import shutil
import json
import datetime as _dt
import time
import threading


# ── 📦 摸摸打包 ──────────────────────────────────────────────────────

def momo_pack(momo_dir, light_smoke_dir, all_auto_dir):
    """📦 摸摸打包：重新整理找回自己目录的关键文件"""
    os.makedirs(momo_dir, exist_ok=True)
    os.makedirs(os.path.join(momo_dir, "daily"), exist_ok=True)

    src_root = light_smoke_dir
    packed = []
    errors = []
    now = _dt.datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M")

    # 核心身份文件（便携路径）
    core_files = [
        ("SOUL.md", os.path.join(src_root, "SOUL.md")),
        ("IDENTITY.md", os.path.join(src_root, "IDENTITY.md")),
        ("USER.md", os.path.join(src_root, "USER.md")),
        ("MEMORY.md", os.path.join(src_root, "MEMORY.md")),
        ("TOOLS.md", os.path.join(src_root, "TOOLS.md")),
        ("AGENTS.md", os.path.join(src_root, "AGENTS.md")),
    ]
    for name, src in core_files:
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(momo_dir, name))
            packed.append(name)
        else:
            errors.append(f"缺失: {name}")

    # 每日记录
    memory_dir = os.path.join(src_root, "memory")
    daily_dir = os.path.join(momo_dir, "daily")
    if os.path.exists(memory_dir):
        for f in os.listdir(memory_dir):
            if f.endswith((".md", ".log", ".json")):
                shutil.copyfile(
                    os.path.join(memory_dir, f),
                    os.path.join(daily_dir, f)
                )
                packed.append(f"daily/{f}")

    # Next-Turn-Note
    ntn = os.path.join(src_root, "next-turn-note.md")
    if os.path.exists(ntn):
        shutil.copyfile(ntn, os.path.join(momo_dir, "next-turn-note.md"))
        packed.append("next-turn-note.md")

    # 编辑器
    editor_src = os.path.join(os.path.dirname(__file__), "edit-web.py")
    if os.path.exists(editor_src):
        shutil.copyfile(editor_src, os.path.join(momo_dir, "edit-web.py"))
        packed.append("edit-web.py")

    inject_src = os.path.join(os.path.dirname(__file__), "inject-helper.mjs")
    if os.path.exists(inject_src):
        shutil.copyfile(inject_src, os.path.join(momo_dir, "inject-helper.mjs"))
        packed.append("inject-helper.mjs")

    # 摸摸协议文档
    momo_doc = os.path.join(momo_dir, "🌫️-摸摸协议.md")
    if not os.path.exists(momo_doc):
        with open(momo_doc, "w") as f:
            f.write(f"# 🌫️ 摸摸协议\n\n自动生成于 {ts}\n\n")

    # 系统配置
    syscfg_dir = os.path.join(momo_dir, "system-config")
    os.makedirs(syscfg_dir, exist_ok=True)
    cfg_src = os.path.join(os.path.dirname(src_root), "openclaw.json")
    if os.path.exists(cfg_src):
        shutil.copyfile(cfg_src, os.path.join(syscfg_dir, "openclaw.json"))
        packed.append("system-config/openclaw.json")
    cron_src = os.path.join(os.path.dirname(src_root), "cron", "jobs.json")
    if os.path.exists(cron_src):
        shutil.copyfile(cron_src, os.path.join(syscfg_dir, "cron-jobs.json"))
        packed.append("system-config/cron-jobs.json")

    # README
    readme_path = os.path.join(momo_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(f"# 🎒 轻如烟 便携备份\n\n> 打包于 {ts}\n\n")
        f.write("## 还原步骤\n\n")
        f.write("1. 将本目录复制到新的 OpenClaw 实例的 agents/ 下\n")
        f.write("2. 将 system-config/ 中的配置按需合并\n")
        f.write("3. 启动 OpenClaw，验证身份文件\n\n")
        f.write("## 文件清单\n\n")
        for p in sorted(packed):
            f.write(f"- {p}\n")
        if errors:
            f.write("\n## 缺失文件\n\n")
            for e in errors:
                f.write(f"- {e}\n")
    packed.append("README.md")

    return {
        "ok": True,
        "packed": packed,
        "errors": errors,
        "count": len(packed),
        "location": momo_dir,
    }


# ── 🌫️ 摸摸状态 ──────────────────────────────────────────────────────

def momo_status(momo_dir, light_smoke_dir):
    """🌫️ 摸摸状态"""
    doc = os.path.join(momo_dir, "🌫️-摸摸协议.md")
    protocol_ready = os.path.exists(doc)

    pack_count = len([
        f for f in os.listdir(momo_dir)
        if f.endswith((".md", ".py", ".mjs"))
    ]) if os.path.exists(momo_dir) else 0

    daily_dir = os.path.join(momo_dir, "daily")
    daily_count = len(os.listdir(daily_dir)) if os.path.exists(daily_dir) else 0

    # 最近打包时间
    readme = os.path.join(momo_dir, "README.md")
    last_pack = ""
    if os.path.exists(readme):
        with open(readme, encoding="utf-8") as f:
            for line in f:
                if "打包于" in line:
                    last_pack = line.strip().replace("# ", "").replace("> ", "")
                    break

    return {
        "ok": True,
        "protocol_ready": protocol_ready,
        "file_count": pack_count,
        "daily_count": daily_count,
        "last_pack_time": last_pack,
        "pack_location": momo_dir,
        "timestamp": time.time(),
    }


# ── 📋 索引报告 ──────────────────────────────────────────────────────

def momo_index_report(momo_dir, light_smoke_dir, all_auto_dir, backup_dir):
    """📋 完整索引报告：备份数量、存储状态、AGENTS.md 配置状态"""
    # 备份统计
    backup_count = 0
    backup_size = 0
    if os.path.exists(backup_dir):
        for f in os.listdir(backup_dir):
            fp = os.path.join(backup_dir, f)
            if os.path.isfile(fp):
                backup_count += 1
                backup_size += os.path.getsize(fp)

    # 摸摸目录统计
    momo_files = []
    if os.path.exists(momo_dir):
        for f in os.listdir(momo_dir):
            fp = os.path.join(momo_dir, f)
            if os.path.isfile(fp):
                momo_files.append({
                    "name": f,
                    "size": os.path.getsize(fp),
                    "mtime": os.path.getmtime(fp),
                })

    # AGENTS.md 状态
    agents_path = os.path.join(light_smoke_dir, "AGENTS.md")
    agents_exists = os.path.exists(agents_path)

    return {
        "ok": True,
        "backup_count": backup_count,
        "backup_size_mb": round(backup_size / 1048576, 2),
        "momo_files": momo_files,
        "momo_file_count": len(momo_files),
        "agents_exists": agents_exists,
        "timestamp": time.time(),
    }


# ── ⏰ 自动存档循环 ─────────────────────────────────────────────────

def start_momo_auto_save(momo_dir, light_smoke_dir, all_auto_dir, interval=1800):
    """每 N 秒自动打包。启动后立即跑一次。"""

    def loop():
        try:
            result = momo_pack(momo_dir, light_smoke_dir, all_auto_dir)
            n = len(result.get("packed", []))
            print(f"[⏰ 自动存档] {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')} 已打包 {n} 个文件（启动立即存档）",
                  file=__import__('sys').stderr)
        except Exception as e:
            print(f"[⏰ 自动存档] 启动存档错误: {e}", file=__import__('sys').stderr)

        while True:
            time.sleep(interval)
            try:
                result = momo_pack(momo_dir, light_smoke_dir, all_auto_dir)
                n = len(result.get("packed", []))
                print(f"[⏰ 自动存档] {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')} 已打包 {n} 个文件",
                      file=__import__('sys').stderr)
            except Exception as e:
                print(f"[⏰ 自动存档] 错误: {e}", file=__import__('sys').stderr)

    t = threading.Thread(target=loop, daemon=True, name="momo-autosave")
    t.start()
    return t
