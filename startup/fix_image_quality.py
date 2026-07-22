#!/usr/bin/env python3
"""
Startup config fix for tool-output-as-image issue.
Run this after a fresh Gateway start.
"""
import json

p = "/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json"
with open(p) as f:
    c = json.load(f)

d = c.setdefault("agents", {}).setdefault("defaults", {})
d["imageQuality"] = "efficient"  # 防止工具输出被渲染为图片
d["imageMaxDimensionPx"] = 600   # 进一步限制图片转换阈值

with open(p, "w") as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"imageQuality set to {d['imageQuality']}")
print(f"imageMaxDimensionPx set to {d['imageMaxDimensionPx']}")
