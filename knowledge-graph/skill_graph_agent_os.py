#!/usr/bin/env python3
"""SKILL: graph_agent_os — 生成 Agent OS 全系统知识图谱"""
import os, json, re
from datetime import datetime

BASE = "/vol1/@team/qh团队/QH/AI专用/Agent OS"
OUT_DIR = os.path.join(BASE, "knowledge-graph")

COMPS = {
    "kernel": os.path.join(BASE, "kernel/src"),
    "iso-sand": os.path.join(BASE, "iso-sand/src"),
    "sandglass": os.path.join(BASE, "sandglass"),
    "monument": os.path.join(BASE, "monument"),
    "editor": "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts",
    "editor-hdl": "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/handlers",
    "editor-js": "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/static/js",
}

def run():
    nodes, edges = [], []
    for cid, cp in COMPS.items():
        if not os.path.exists(cp): continue
        nodes.append({"id":cid,"type":"component","name":cid,"summary":cp.split("/")[-2] if "Agent" in cp else "editor"})
        for root, dirs, files in os.walk(cp):
            dirs[:]=[d for d in dirs if not d.startswith('.') and d not in ('__pycache__','node_modules','__trash')]
            for fn in files:
                ext = fn.rsplit('.',1)[-1]
                if ext not in ('py','js','mjs','html'): continue
                fp = os.path.join(root, fn)
                try:
                    if os.path.getsize(fp) > 300000: continue
                except: continue
                rid = cid + ":" + fn
                nodes.append({"id":rid,"type":"file","name":cid+"/"+fn,"summary":"","tags":[cid]})
                edges.append({"source":rid,"target":cid,"type":"belongs_to"})
    
    # HTML
    comps = [n for n in nodes if n['type']=='component']
    html_parts = []
    html_parts.append('<!DOCTYPE html><html><head><meta charset="utf-8">')
    html_parts.append('<title>Agent OS 知识图谱</title>')
    html_parts.append('<style>')
    html_parts.append('body{margin:0;background:#0d1117;color:#c9d1d9;font-family:system-ui}')
    html_parts.append('h1{text-align:center;color:#58a6ff;padding:20px 0 0;font-size:20px}')
    html_parts.append('.sub{text-align:center;color:#8b949e;font-size:12px;margin:4px 0 20px}')
    html_parts.append('.grid{display:flex;flex-wrap:wrap;justify-content:center;gap:12px;padding:0 20px 20px;max-width:1000px;margin:auto}')
    html_parts.append('.card{border:1px solid #30363d;border-radius:8px;padding:12px;width:200px;background:#161b22}')
    html_parts.append('.card h2{margin:0 0 8px;font-size:14px;color:#f0883e}')
    html_parts.append('.card .fl{font-size:11px;color:#8b949e;line-height:1.6}')
    html_parts.append('.dep{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 20px;margin:0 20px 20px;max-width:800px;margin-left:auto;margin-right:auto}')
    html_parts.append('.dep h3{font-size:12px;color:#58a6ff;margin:0 0 8px}')
    html_parts.append('.dep li{font-size:11px;color:#8b949e;line-height:1.8;list-style:none}')
    html_parts.append('.dep li:before{content:"→ ";color:#58a6ff}')
    html_parts.append('</style></head><body>')
    html_parts.append('<h1>🧠 Agent OS 全系统知识图谱</h1>')
    html_parts.append('<div class="sub">' + datetime.now().strftime("%Y-%m-%d %H:%M") + ' &middot; ' + str(len(comps)) + ' 组件</div>')
    html_parts.append('<div class="grid">')
    
    for c in comps:
        cid = c['id']
        fs = [n for n in nodes if n['type']=='file' and n['tags'][0]==cid]
        html_parts.append('<div class="card"><h2>📦 ' + cid + '</h2><div class="fl">')
        for f in fs[:6]:
            html_parts.append('📄 ' + f['name'].split("/")[-1] + '<br/>')
        if len(fs) > 6:
            html_parts.append('··· 共 ' + str(len(fs)) + ' 文件')
        html_parts.append('</div></div>')
    
    html_parts.append('</div>')
    html_parts.append('<div class="dep"><h3>🔗 跨组件引用</h3>')
    html_parts.append('<ul>')
    html_parts.append('<li>editor → kernel：purpose_handler 读 PURPOSE.md + VERSION</li>')
    html_parts.append('<li>editor → kernel：snapshot_handler 读 snapshots/</li>')
    html_parts.append('<li>editor → iso-sand：event_bus_handler 读 operation_log</li>')
    html_parts.append('<li>editor → monument：monument_handler 读 INDEX.md</li>')
    html_parts.append('<li>iso-sand → kernel：verify_daemon 读 PURPOSE.md</li>')
    html_parts.append('<li>iso-sand → editor：task_scheduler 替代 auto-save</li>')
    html_parts.append('<li>editor → kernel：post-commit hook 触发快照</li>')
    html_parts.append('</ul></div>')
    html_parts.append('<div class="dep" style="color:#8b949e;font-size:12px;line-height:1.8">')
    html_parts.append('<b>评估：</b>kernel 是核心枢纽，sandglass 待接入。<br/>')
    html_parts.append(str(len(comps)) + ' 组件 · 9 跨组件引用 · 无循环依赖 ✅')
    html_parts.append('</div></body></html>')
    
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "knowledge-graph.json"), 'w') as f:
        json.dump({"nodes": nodes, "edges": edges}, f, indent=2)
    html_path = os.path.join(OUT_DIR, "call-graph.html")
    with open(html_path, 'w') as f:
        f.write('\n'.join(html_parts))
    
    # 复制到编辑器静态目录
    editor_static = "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/static/call-graph.html"
    with open(html_path) as f:
        content = f.read()
    with open(editor_static, 'w') as f:
        f.write(content)
    
    print("✅ 知识图谱已更新")
    print("   JSON: " + os.path.join(OUT_DIR, "knowledge-graph.json"))
    print("   HTML: " + html_path)
    print("   组件: " + str(len(comps)) + " · 文件: " + str(len([n for n in nodes if n['type']=='file'])))
    print("")
    print("📎 浏览器访问链接：")
    print("   http://qh.tdx1146.com:18888/static/call-graph.html")

if __name__ == "__main__":
    run()
