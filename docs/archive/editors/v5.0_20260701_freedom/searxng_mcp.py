#!/usr/bin/env python3
"""
searxng_mcp.py — SearXNG 搜索 MCP Server
通过本地 SearXNG JSON API 搜索网页（不走 Bing HTML 解析）
"""

import sys, json, urllib.request, urllib.parse


SEARXNG_URL = "http://127.0.0.1:8888"


def search_web(query, count=6, lang="zh-CN"):
    """通过 SearXNG JSON API 搜索"""
    params = urllib.parse.urlencode({
        "q": query, "format": "json", "language": lang
    })
    url = f"{SEARXNG_URL}/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return f"[搜索失败] {e}"
    
    results = data.get("results", [])[:count]
    if not results:
        return "SearXNG 未返回结果。"
    
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(无标题)")
        url = r.get("url", "")
        snippet = r.get("content", "")
        lines.append(f"[{i}] {title}\n{url}\n{snippet}")
    return "\n\n".join(lines)


def handle_request(request):
    method = request.get("method", "")
    
    if method == "tools/list":
        return {
            "tools": [{
                "name": "web_search",
                "description": "用本地 SearXNG 搜索网页。支持中文。当用户问实时信息、新闻、技术文档时调用。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "max_results": {"type": "number", "default": 6, "description": "返回结果数（最多10）"},
                        "lang": {"type": "string", "default": "zh-CN", "description": "语言"}
                    },
                    "required": ["query"]
                }
            }]
        }
    
    if method == "tools/call":
        args = request.get("params", {}).get("arguments", {})
        query = args.get("query", "")
        count = min(args.get("max_results", 6), 10)
        lang = args.get("lang", "zh-CN")
        result = search_web(query, count, lang)
        return {"content": [{"type": "text", "text": result}]}
    
    if method == "initialize":
        return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
    if method == "notifications/initialized":
        return {}
    
    return {"error": f"unknown method: {method}"}


if __name__ == "__main__":
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
            resp = handle_request(req)
            msg = json.dumps(resp, ensure_ascii=False)
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()
        except Exception as e:
            err = json.dumps({"error": str(e)}, ensure_ascii=False)
            sys.stdout.write(err + "\n")
            sys.stdout.flush()
