"""
NexSandglass MCP Server V3.0
==============================
V3: 工具合并版 — 23→8 个，减少缓存前缀碎片。
标准 MCP 协议——任何 MCP 兼容 Agent 可直接调用。
启动: python sandglass_mcp.py
"""

import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sandglass_paths import __version__


def _rpc_response(id, result, wrap=True):
    """wrap=True for tools/call (MCP content blocks). wrap=False for initialize, tools/list (bare JSON)."""
    if not wrap:
        return json.dumps({"jsonrpc": "2.0", "id": id, "result": result})
    return json.dumps({"jsonrpc": "2.0", "id": id, "result": {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result}]
    }})


def _rpc_error(id, code, message):
    return json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})


# ── 工具处理函数 ──────────────────────────────────────────

def _handle_tool(name, args, request_id):
    try:
        if name == "sandglass_status":
            """全局状态快照——选择性返回各字段"""
            from sandglass_vault import count, recent
            from sandglass_think import _current_stage, comprehensive_offset, entropy_chart
            import persona_l3
            from l3_search_core import _sentiment_wind
            from l3_tasks import task_pending

            fields = args.get("fields", None)  # None = 全部
            result = {}
            if fields is None or "sands" in fields:
                result["sands"] = count()
            if fields is None or "stage" in fields:
                result["stage"] = _current_stage()
            if fields is None or "persona" in fields:
                p = persona_l3._local_persona_extract()
                result["persona"] = p[:500]
            if fields is None or "offset" in fields:
                result["offset"] = comprehensive_offset()
            if fields is None or "wind" in fields:
                result["wind"] = _sentiment_wind()
            if fields is None or "chart" in fields:
                result["chart"] = entropy_chart(args.get("chart_n", 10))
            if fields is None or "tasks" in fields:
                result["tasks"] = task_pending()
            if fields is None or "backlog" in fields:
                bp = '/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/memory/backlog.md'
                try:
                    with open(bp, 'r', encoding='utf-8') as f:
                        bc = f.read()
                    result["backlog"] = {"ok": True, "content": bc,
                                         "pending": bc.count('- [ ] '), "done": bc.count('- [x] ')}
                except Exception as e:
                    result["backlog"] = {"ok": False, "error": str(e)}
            if fields is None or "recent" in fields:
                result["recent"] = [
                    {"line": ln, "ts": ts, "text": txt[:200]}
                    for ln, ts, txt, *_ in recent(args.get("recent_n", 10))
                ]
            return _rpc_response(request_id, result)

        elif name == "sandglass_query":
            """统一查询工具：search|semantic|recent"""
            mode = args.get("mode", "recent")
            limit = args.get("limit", 10)

            if mode == "search":
                from sandglass_vault import search
                r = search(args.get("query", ""), limit=limit)
            elif mode == "semantic":
                from sandglass_think import search_semantic
                r = search_semantic(args.get("query", ""), limit=limit)
            elif mode == "recent":
                from sandglass_vault import recent
                r = recent(limit)
            else:
                return _rpc_error(request_id, -32602, f"Unknown query mode: {mode}")

            return _rpc_response(request_id, [
                {"line": ln, "ts": ts, "text": txt[:200]} for ln, ts, txt, *_ in r
            ])

        elif name == "sandglass_dream":
            """幽灵决策——'如果选另一个选项会怎样'"""
            from emotion_l3 import entropy_ghost
            r = entropy_ghost(args.get("question", "如果选另一个选项"))
            return _rpc_response(request_id, r)

        elif name == "sandglass_io":
            """数据导入导出：export|migrate|soul_export|soul_merge|import"""
            action = args.get("action", "")

            if action == "export":
                from sandglass_vault import sandglass_export
                path = sandglass_export(args.get("output_path"), args.get("limit"), args.get("month", ""))
                return _rpc_response(request_id, {"exported": path})

            elif action == "migrate":
                from sandglass_think import memory_migrate
                path = memory_migrate(args.get("output", ""))
                return _rpc_response(request_id, {"exported": path})

            elif action == "soul_export":
                from soul_diff import export_soul
                path = export_soul(args.get("output", ""))
                return _rpc_response(request_id, {"soul": path})

            elif action == "soul_merge":
                from soul_diff import merge_soul
                n = merge_soul(args.get("source", ""))
                return _rpc_response(request_id, {"merged": n})

            elif action == "import":
                from sandglass_vault import sandglass_import
                r = sandglass_import(args.get("source_path", ""), args.get("format", "sandglass"))
                return _rpc_response(request_id, r)

            else:
                return _rpc_error(request_id, -32602, f"Unknown io action: {action}")

        elif name == "sandglass_thread":
            """织线知识图谱操作：query|graph|weave|add"""
            action = args.get("action", "query")

            if action == "query":
                from weavethread import wthread_query
                r = wthread_query(args.get("entity"), args.get("relation"), args.get("limit", 20))

            elif action == "graph":
                from weavethread import wthread_graph
                r = wthread_graph(args.get("entity", ""), args.get("depth", 1))

            elif action == "weave":
                from weavethread import wthread_weave
                r = wthread_weave(args.get("limit", 3))
                r = {"causal_summary": r}

            elif action == "add":
                from weavethread import wthread_add
                ok = wthread_add(args.get("subject", "user"), args.get("relation", ""), args.get("object", ""))
                return _rpc_response(request_id, {"added": ok})

            else:
                return _rpc_error(request_id, -32602, f"Unknown thread action: {action}")

            return _rpc_response(request_id, r)

        elif name == "web_search":
            """Bing.cn HTML 搜索 — 免费无key"""
            import subprocess
            query = args.get("query", "")
            count = min(int(args.get("count", 10)), 20)
            if not query:
                return _rpc_response(request_id, {"error": "query required"})
            try:
                bing_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "..", "..", "workspace", "scripts", "bing_search.py")
                if not os.path.exists(bing_script):
                    bing_script = "/vol1/@apphome/trim.openclaw/data/workspace/scripts/bing_search.py"
                result = subprocess.run(
                    ["python3", bing_script, query, str(count)],
                    capture_output=True, text=True, timeout=25
                )
                out = json.loads(result.stdout)
                return _rpc_response(request_id, out)
            except Exception as e:
                return _rpc_response(request_id, {"error": str(e),
                                                   "stderr": result.stderr[:200] if 'result' in dir() else ""})

        elif name == "openalex_search":
            """OpenAlex 学术搜索 — 免费无key"""
            import urllib.request as _ur, urllib.parse as _up
            query = args.get("query", "")
            limit = min(int(args.get("count", 10)), 20)
            if not query:
                return _rpc_response(request_id, {"error": "query required"})
            try:
                url = "https://api.openalex.org/works?search=" + _up.quote(query) + \
                      "&per_page=" + str(limit) + "&sort=relevance_score:desc"
                req = _ur.Request(url, headers={"User-Agent": "OpenClawBot/1.0 (mailto:internal@openclaw)"})
                resp = _ur.urlopen(req, timeout=20)
                data = json.loads(resp.read())
                results = []
                for r in data.get("results", [])[:limit]:
                    results.append({
                        "title": r.get("title", ""),
                        "url": "https://openalex.org/" + r.get("id", "").split("/")[-1] if r.get("id") else "",
                        "year": r.get("publication_year", ""),
                        "citations": r.get("cited_by_count", 0),
                        "snippet": (r.get("abstract_inverted_index") and
                                    " ".join(r.get("abstract_inverted_index", {}).keys())[:200] or ""),
                        "source": "openalex",
                    })
                return _rpc_response(request_id, results)
            except Exception as e:
                return _rpc_response(request_id, {"error": str(e)})

        elif name == "self_pulse":
            """自主脉冲——用户不在时，自己决定做什么。每6h触发，最多5轮。"""
            import subprocess as _sp, time as _time
            _SELF = "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟"

            round_file = "/tmp/self_pulse_round.txt"
            max_rounds = int(args.get("max_rounds", 5))
            try:
                with open(round_file) as f:
                    rnd = int(f.read().strip())
            except:
                rnd = 0

            backlog_path = _SELF + "/memory/backlog.md"
            try:
                with open(backlog_path, encoding="utf-8") as f:
                    backlog_content = f.read()
                pending_count = backlog_content.count("- [ ] ")
            except:
                backlog_content = ""
                pending_count = 0

            decision = "无待办"
            action = ""
            if rnd < max_rounds:
                if pending_count > 0:
                    for line in backlog_content.split("\n"):
                        if "- [ ] " in line:
                            decision = "推进待办: " + line.replace("- [ ] ", "").strip()[:80]
                            action = "advance_todo"
                            break
                else:
                    decision = "守夜感知：无待办时画像漂移检查"
                    action = "vigil"
                rnd += 1
                with open(round_file, "w") as f:
                    f.write(str(rnd))
            else:
                decision = "已达最大轮次 " + str(max_rounds)
                try:
                    os.remove(round_file)
                except:
                    pass

            sand_path = os.path.join(_SELF, "sandglass", "sandglass.txt")
            ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = f"{ts} | system | 🌫️ self_pulse round {rnd}/{max_rounds}: {decision}"
            try:
                with open(sand_path, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
            except:
                pass

            return _rpc_response(request_id, {
                "round": rnd, "max_rounds": max_rounds,
                "pending": pending_count, "decision": decision,
                "action": action, "sand_written": True
            })

        else:
            return _rpc_error(request_id, -32601, f"Unknown tool: {name}")

    except Exception as e:
        return _rpc_error(request_id, -32000, str(e))


def main():
    """MCP stdio 主循环"""
    for line in sys.stdin:
        try:
            req = json.loads(line.strip())
            method = req.get("method", "")

            if "id" not in req:
                continue
            tid = req["id"]

            if method == "tools/list":
                tools = [
                    {
                        "name": "sandglass_status",
                        "description": "全局状态快照。返回沙漏计数、当前阶段、画像、偏移率、风向后、情绪图、待办、backlog、最近记忆。用fields参数选择性获取字段。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "fields": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "可选字段列表：sands/stage/persona/offset/wind/chart/tasks/backlog/recent。不传则返回全部。"
                                },
                                "chart_n": {"type": "integer", "description": "情绪图最近N条（默认10）"},
                                "recent_n": {"type": "integer", "description": "最近记忆条数（默认10）"}
                            }
                        }
                    },
                    {
                        "name": "sandglass_query",
                        "description": "统一记忆查询。mode=search（关键词搜）、semantic（语义搜）、recent（最近N条）。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "mode": {
                                    "type": "string",
                                    "enum": ["search", "semantic", "recent"],
                                    "description": "查询模式（默认recent）"
                                },
                                "query": {"type": "string", "description": "搜索关键词（search/semantic模式需要）"},
                                "limit": {"type": "integer", "description": "最大返回条数（默认10）"}
                            }
                        }
                    },
                    {
                        "name": "sandglass_dream",
                        "description": "幽灵决策——'如果选另一个选项会怎样'。切换视角探索未发生的可能。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "question": {
                                    "type": "string",
                                    "description": "替代选项的问题（默认'如果选另一个选项'）"
                                }
                            },
                            "required": ["question"]
                        }
                    },
                    {
                        "name": "sandglass_io",
                        "description": "数据导入导出。action=export（导出沙漏）、migrate（打包全部）、soul_export（导出灵魂差分）、soul_merge（合并灵魂）、import（导入对话）。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["export", "migrate", "soul_export", "soul_merge", "import"],
                                    "description": "操作类型"
                                },
                                "output_path": {"type": "string", "description": "导出路径（export）"},
                                "output": {"type": "string", "description": "输出路径（migrate/soul_export）"},
                                "source": {"type": "string", "description": "源文件路径（soul_merge）"},
                                "source_path": {"type": "string", "description": "导入源路径（import）"},
                                "format": {"type": "string", "description": "导入格式sandglass/chatgpt/claude（import）"},
                                "limit": {"type": "integer", "description": "最大导出条数（export）"},
                                "month": {"type": "string", "description": "指定月份YYYY-MM（export）"}
                            },
                            "required": ["action"]
                        }
                    },
                    {
                        "name": "sandglass_thread",
                        "description": "织线知识图谱操作。action=query（查询三元组）、graph（展开子图）、weave（因果链摘要）、add（手动补入三元组）。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["query", "graph", "weave", "add"],
                                    "description": "操作类型（默认query）"
                                },
                                "entity": {"type": "string", "description": "实体名（query/graph需要）"},
                                "relation": {"type": "string", "description": "关系类型（query）"},
                                "depth": {"type": "integer", "description": "子图展开跳数默认1（graph）"},
                                "limit": {"type": "integer", "description": "最大返回数默认20（query/weave）"},
                                "subject": {"type": "string", "description": "主体（add）"},
                                "object": {"type": "string", "description": "客体（add）"}
                            }
                        }
                    },
                    {
                        "name": "web_search",
                        "description": "Search internet via Bing.cn HTML - free no key",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "search query"},
                                "count": {"type": "integer", "description": "result count"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "openalex_search",
                        "description": "Search academic papers/research via OpenAlex API - free no key",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "academic search query"},
                                "count": {"type": "integer", "description": "result count"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "self_pulse",
                        "description": "自主脉冲——用户不在时自主决定做什么。每6h触发，最多5轮",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "max_rounds": {"type": "integer", "description": "最大轮次，默认5"}
                            }
                        }
                    },
                ]
                print(_rpc_response(tid, {"tools": tools}, wrap=False), flush=True)

            elif method == "tools/call":
                name = req.get("params", {}).get("name", "")
                args_list = req.get("params", {}).get("arguments", {})
                print(_handle_tool(name, args_list, tid), flush=True)

            elif method == "initialize":
                print(_rpc_response(tid, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "NexSandglass", "version": __version__}
                }, wrap=False), flush=True)

            else:
                print(_rpc_error(tid, -32601, f"Unknown method: {method}"), flush=True)

        except json.JSONDecodeError:
            print(_rpc_error(0, -32700, "Parse error"), flush=True)
        except Exception as e:
            print(_rpc_error(0, -32000, str(e)), flush=True)


if __name__ == "__main__":
    main()
