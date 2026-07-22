#!/usr/bin/env python3
"""NexSandglass 落沙封装——给 edit-web.py 调用。"""
import sys, os
sys.path.insert(0, '/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass_source')
os.environ['NEXSANDBASE_HOME'] = '/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass'

from sandglass_log import log_message
from sandglass_paths import _SANDGLASS, _SHADOW_DB
from sandglass_vault import rebuild_index

def log(content, role='user'):
    """落沙一条"""
    log_message(content, role)
    # 同步影子沙索引
    rebuild_index()
    print(f"✅ 沙漏写入: {content[:50]}...")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 sandglass_log_wrapper.py <内容> [role]")
        sys.exit(1)
    content = sys.argv[1]
    role = sys.argv[2] if len(sys.argv) > 2 else 'user'
    log(content, role)
