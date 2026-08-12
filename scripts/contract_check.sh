#!/bin/bash
# =============================================================
# contract_check.sh — Agent OS 契约层校验（只读）
# -------------------------------------------------------------
# 读 CONTRACTS.yaml，逐项机器校验组件存在性 + 组件间契约，
# 输出 ✅/⚠️/❌ + 证据；契约漂移（改 A 的 API，B/C/D 悄悄坏）
# 在当天被 ❌ 拦住。
#
# 用法：
#   bash scripts/contract_check.sh           # 手动校验（stdout；不改任何系统状态）
#   bash scripts/contract_check.sh --cron    # cron 模式：追加 logs/contract_check.log
#                                            #   + 状态变化才告警（供 crontab 调用）
#
# 退出码：0=全绿  1=有警告  2=有故障（对齐 system_health_check.sh）
#
# 与 system_health_check.sh 的关系：
#   health_check = 单组件健康（进程/端口/文件新鲜度）
#   contract_check = 契约层（组件间接口/数据流/字段 schema/同步率）
#   两者互补；可在 health_check 末尾「可选调用」本脚本，本脚本自身不侵入任何现有代码。
#
# 设计纪律：
#   - 零硬编码：所有路径从 Agent OS/env.local 推导（$VAR 插值），缺失时相对推导
#   - 只读：不调用任何写接口（C-05 /feed 用日志证据校验，不做真发）
#   - 路径含空格（所有自动化/轻如烟）：全部引号包裹
# =============================================================
set -u

AGENT_OS_HOME="$(cd "$(dirname "$0")/.." && pwd)"
CONTRACTS_FILE="${CONTRACTS_FILE:-$AGENT_OS_HOME/CONTRACTS.yaml}"
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi

MODE="${1:-manual}"
RUN_DIR="${RUN_DIR:-$AGENT_OS_HOME/run}"
LOG_DIR="${LOG_DIR:-$AGENT_OS_HOME/logs}"

[ -f "$CONTRACTS_FILE" ] || { echo "❌ CONTRACTS.yaml 不存在: $CONTRACTS_FILE" >&2; exit 2; }

python3 - "$CONTRACTS_FILE" "$MODE" "$RUN_DIR" "$LOG_DIR" <<'PY'
import json, os, re, sqlite3, socket, subprocess, sys, datetime

CONTRACTS_FILE, MODE, RUN_DIR, LOG_DIR = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
try:
    import yaml
except ImportError:
    print("❌ 缺少 PyYAML（python3 -m pip install pyyaml）"); sys.exit(2)

def env(s):
    """$VAR / ${VAR} 插值（env.local 已由 shell source 进环境）"""
    def repl(m):
        name = m.group(1) or m.group(2)
        return os.environ.get(name, m.group(0))
    return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)', repl, s)

# ---- 派生路径（不硬编码；env.local 已由 shell source）----
def derive(name, dflt):
    return os.environ.get(name) or dflt
AGENT_OS_HOME = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.dirname(CONTRACTS_FILE))
PARENT = os.path.dirname(os.path.dirname(AGENT_OS_HOME))  # /vol2/1000/AI专用
NEX = derive("NEXSANDBASE_HOME", os.path.join(PARENT, "所有自动化", "轻如烟", "sandglass"))
LMS_HOME = derive("LMS_HOME", os.path.join(PARENT, "living-memory-system-cloud"))
# 玄鉴已并入 agent-os/xuanjian（2026-08-12）；优先新路径，旧同构沙盘回退
_xj = os.path.join(AGENT_OS_HOME, "xuanjian")
VERIFY_HOME = derive("VERIFY_HOME", _xj if os.path.isdir(os.path.join(_xj, "src")) else os.path.join(PARENT, "AgentOS-IsoSand", "同构沙盘"))
ISO_SAND_HOME = derive("ISO_SAND_HOME", os.path.join(AGENT_OS_HOME, "iso-sand"))
LIGHT_HOME = derive("LIGHT_HOME", os.path.join(PARENT, "所有自动化", "轻如烟"))
FACTS = os.environ.get("FACTS_DICT_PATH", "")
WORKSPACE = os.path.dirname(os.path.dirname(FACTS)) if FACTS else "/vol1/@apphome/trim.openclaw/data/workspace"
BACKUP_ROOT = os.path.join(os.path.dirname(LMS_HOME), "backups", "lms")
# 预置插值变量（脚本内部使用，不经 YAML）
os.environ.setdefault("NEXSANDBASE_HOME", NEX)
os.environ.setdefault("LMS_HOME", LMS_HOME)
os.environ.setdefault("VERIFY_HOME", VERIFY_HOME)
os.environ.setdefault("ISO_SAND_HOME", ISO_SAND_HOME)
os.environ.setdefault("AGENT_OS_HOME", AGENT_OS_HOME)
os.environ.setdefault("WORKSPACE", WORKSPACE)
os.environ.setdefault("BACKUP_ROOT", BACKUP_ROOT)

NOW = datetime.datetime.now().astimezone()
NOW_ISO = NOW.strftime("%F %T")
results = []  # (id, component, name, status, evidence)

def add(cid, comp, name, status, evidence):
    results.append((cid, comp, name, status, evidence))

# ---------------- 工具 ----------------
def file_age(path):
    try:
        return NOW.timestamp() - os.stat(path).st_mtime
    except OSError:
        return 999999.0

def age_label(s):
    s = float(s)
    if s >= 86400: return f"{int(s//86400)}天前"
    if s >= 3600: return f"{int(s//3600)}小时前"
    if s >= 60: return f"{int(s//60)}分钟前"
    return f"{int(s)}秒前"

def http_json(method, url, body, timeout):
    """返回 (ok, data_or_err)"""
    import urllib.request, urllib.error
    req = urllib.request.Request(url, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return True, json.loads(raw)
            except Exception:
                return True, raw
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)[:80]

def nav(obj, path):
    """'a.b.0.c' 路径导航；不存在返回 (False, None)"""
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, list) and seg.isdigit() and int(seg) < len(cur):
            cur = cur[int(seg)]
        else:
            return False, None
    return True, cur

def check_assert(obj, a):
    """单条断言 → (pass, detail)"""
    path = a.get("path", "")
    exists, val = nav(obj, path)
    # 找出断言类型键（eq/gt/ge/exists/type/nonempty）
    atype = None
    for k in ("eq", "gt", "ge", "exists", "type", "nonempty"):
        if k in a: atype = k; break
    if atype is None:
        return True, ""
    if atype == "exists":
        return exists, f"{path}={val if exists else '缺失'}"
    if not exists:
        return False, f"{path} 缺失"
    if atype == "eq":
        exp = a["eq"]
        if isinstance(exp, bool):
            ok = bool(val) is exp
        elif isinstance(exp, (int, float)) and isinstance(val, (int, float)):
            ok = val == exp
        else:
            ok = str(val) == str(exp)
        return ok, f"{path}={val}"
    if atype == "gt":
        return float(val) > float(a["gt"]), f"{path}={val}"
    if atype == "ge":
        return float(val) >= float(a["ge"]), f"{path}={val}"
    if atype == "type":
        t = a["type"]
        mapping = {"int": int, "float": (int, float), "str": str, "bool": bool, "list": list, "dict": dict}
        return isinstance(val, mapping.get(t, object)), f"{path} 类型={type(val).__name__}"
    if atype == "nonempty":
        return bool(val), f"{path} 非空={bool(val)}"
    return True, ""

def run_http_check(c):
    url = env(c.get("url", ""))
    method = c.get("method", "GET")
    body = c.get("body")
    timeout = float(c.get("timeout", 6))
    ok, data = http_json(method, url, body, timeout)
    if not ok:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{method} {url} 失败: {data}")
        return
    if not isinstance(data, dict):
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{url} 返回非 JSON: {str(data)[:60]}")
        return
    root = data
    if c.get("json_root"):
        okr, root = nav(data, c["json_root"])
        if not okr:
            add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"json_root '{c['json_root']}' 缺失")
            return
    fails, notes = [], []
    for a in c.get("asserts", []):
        passed, detail = check_assert(root, a)
        notes.append(detail)
        if not passed:
            fails.append(a.get("note", a.get("path", "?")))
    # 可选字段（历史陷阱：缺席不算违反）
    for of in c.get("optional_fields", []):
        exists, val = nav(root, of.get("path", ""))
        if not exists:
            notes.append(f"{of.get('path')} 缺席(允许)")
            continue
        sub_ok = True
        for k, v in (of.get("if_present") or {}).items():
            if k == "type":
                mapping = {"int": int, "float": (int, float), "str": str, "bool": bool, "list": list, "dict": dict}
                if not isinstance(val, mapping.get(v, object)): sub_ok = False
            elif k == "ge":
                try:
                    if not (float(val) >= float(v)): sub_ok = False
                except Exception: sub_ok = False
            elif k == "gt":
                try:
                    if not (float(val) > float(v)): sub_ok = False
                except Exception: sub_ok = False
        if sub_ok:
            notes.append(f"{of.get('path')}={val}（在场且合法）")
        else:
            fails.append(of.get("note", f"{of.get('path')} 在场但不合法"))
    status = "OK" if not fails else ("WARN" if len(fails) <= 1 else "FAULT")
    add(c["id"], c.get("component", "?"), c["name"], status, "；".join(notes[:6]) + (f"；违反: {'; '.join(fails)}" if fails else ""))

def run_json_file_check(c):
    path = env(c.get("path", ""))
    try:
        data = json.load(open(path))
    except Exception as e:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{path} 不可读: {e}")
        return
    fails, notes = [], []
    for a in c.get("asserts", []):
        passed, detail = check_assert(data, a)
        notes.append(detail)
        if not passed: fails.append(a.get("note", a.get("path", "?")))
    status = "OK" if not fails else "FAULT"
    add(c["id"], c.get("component", "?"), c["name"], status, "；".join(notes[:5]) + (f"；违反: {'; '.join(fails)}" if fails else ""))

def run_file_fresh(c):
    path = env(c.get("path", ""))
    age = file_age(path)
    ok_s = float(c.get("ok_seconds", 1800)); warn_s = float(c.get("warn_seconds", 21600))
    if age >= 999000:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{path} 不存在")
    elif age < ok_s:
        add(c["id"], c.get("component", "?"), c["name"], "OK", f"{path} {age_label(age)} 更新")
    elif age < warn_s:
        add(c["id"], c.get("component", "?"), c["name"], "WARN", f"{path} {age_label(age)} 偏旧")
    else:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{path} {age_label(age)} 停更")

def run_file_grep_recent(c):
    path = env(c.get("path", ""))
    pattern = c.get("pattern", "")
    age = file_age(path)
    found = False
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); size = f.tell()
            f.seek(max(0, size - 200000))
            tail = f.read().decode("utf-8", "replace")
        found = re.search(pattern, tail) is not None
    except OSError:
        pass
    ok_s = float(c.get("ok_seconds", 86400)); warn_s = float(c.get("warn_seconds", 604800))
    if age >= 999000:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{path} 不存在")
    elif not found:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{path} 近期无 '{pattern}' 匹配")
    elif age < ok_s:
        add(c["id"], c.get("component", "?"), c["name"], "OK", f"{path} {age_label(age)} 且含 '{pattern}'")
    elif age < warn_s:
        add(c["id"], c.get("component", "?"), c["name"], "WARN", f"{path} {age_label(age)} 偏旧（仍含 '{pattern}'）")
    else:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{path} {age_label(age)} 停更（含 '{pattern}' 但太久无写入）")

def run_process_alive(c):
    pidfile = env(c.get("pidfile", ""))
    try:
        pid = int(open(pidfile).read().strip())
        os.kill(pid, 0)
        add(c["id"], c.get("component", "?"), c["name"], "OK", f"pid={pid} 存活")
    except FileNotFoundError:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{pidfile} 不存在（进程未起？）")
    except (ProcessLookupError, ValueError):
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"pid 死亡或非法（{pidfile}）")

def run_port_listen(c):
    port = int(c.get("port", 0))
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            add(c["id"], c.get("component", "?"), c["name"], "OK", f"端口 {port} 在听")
    except OSError:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"端口 {port} 未监听")

def run_sqlite_ratio(c):
    db = env(c.get("db", ""))
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        num = con.execute(c["numerator"]).fetchone()[0]
        den = con.execute(c["denominator"]).fetchone()[0]
        con.close()
    except Exception as e:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{db} 查询失败: {e}")
        return
    if den == 0:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{db} 分母=0")
        return
    ratio = num / den
    ok_min = float(c.get("ok_min", 0.95)); warn_min = float(c.get("warn_min", 0.80))
    status = "OK" if ratio >= ok_min else ("WARN" if ratio >= warn_min else "FAULT")
    add(c["id"], c.get("component", "?"), c["name"], status, f"{num}/{den} = {ratio*100:.1f}% (SLO≥{ok_min*100:.0f}%)")

def run_sqlite_gt(c):
    db = env(c.get("db", ""))
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        val = con.execute(c["query"]).fetchone()[0]
        con.close()
    except Exception as e:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{db} 查询失败: {e}")
        return
    status = "OK" if int(val) > int(c.get("gt", 0)) else "FAULT"
    add(c["id"], c.get("component", "?"), c["name"], status, f"{c['query']} = {val}")

def run_sandglass_mirror(c):
    txt = env(c.get("txt", "")); db = env(c.get("db", ""))
    try:
        # txt 权威源计数：去重后的有效条目（与 db 镜像语义一致）
        # 背景：txt 有双写历史（同一 (ts,sender,text) 出现两次，2026-08-11 实测 563 行），
        # db 镜像按失忆根因-2 修复设计去重 → 分母必须用去重条目数，否则永久假红（63.7%≠缺 484 条）。
        tcnt = 0
        seen = set()
        with open(txt, "r", errors="replace") as f:
            for line in f:
                parts = line.strip().split(" | ", 2)
                if len(parts) < 3:
                    continue
                ts, sender, text = parts[0], parts[1], parts[2].strip()
                if ts and re.match(r'^\d{4}-\d{2}-\d{2}', ts):
                    key = (ts, sender, text)
                    if key not in seen:
                        seen.add(key); tcnt += 1
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        dcnt = con.execute(f"SELECT COUNT(*) FROM {c['table']}").fetchone()[0]
        recent = con.execute("SELECT COUNT(*) FROM %s WHERE timestamp >= datetime('now','-1 day','localtime')" % c["table"]).fetchone()[0]
        con.close()
    except Exception as e:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"镜像比对失败: {e}")
        return
    ratio = dcnt / tcnt if tcnt else 0
    ok_min = float(c.get("ok_min", 0.95)); warn_min = float(c.get("warn_min", 0.80))
    status = "OK" if ratio >= ok_min else ("WARN" if ratio >= warn_min else "FAULT")
    add(c["id"], c.get("component", "?"), c["name"], status,
        f"db={dcnt} txt去重条目={tcnt} 同步率={ratio*100:.1f}% (SLO≥{ok_min*100:.0f}%)，近24h新增={recent}")

def run_jsonl_level_count(c):
    log = env(c.get("log", ""))
    try:
        with open(log, "r", errors="replace") as f:
            lines = f.readlines()[-int(c.get("tail_lines", 300)):]
    except OSError:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{log} 不可读")
        return
    cnt = sum(1 for l in lines if re.search(r'"level":\s*"%s"' % re.escape(c.get("level", "FAIL")), l))
    ok_max = int(c.get("ok_max", 0)); warn_max = int(c.get("warn_max", 5))
    status = "OK" if cnt <= ok_max else ("WARN" if cnt <= warn_max else "FAULT")
    add(c["id"], c.get("component", "?"), c["name"], status, f"近{c.get('tail_lines')}行 FAIL={cnt}")

def run_dlq_recent(c):
    dlq = env(c.get("dlq", ""))
    cnt24 = 0
    try:
        with open(dlq, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    d = json.loads(line)
                    t = d.get("t", "")
                    if t:
                        ts = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
                        if (NOW - ts.astimezone()).total_seconds() <= 86400:
                            cnt24 += 1
                    else:
                        cnt24 += 1
                except Exception:
                    cnt24 += 1
    except OSError:
        add(c["id"], c.get("component", "?"), c["name"], "OK", f"{dlq} 不存在（无死信）")
        return
    ok_max = int(c.get("ok_max", 0)); warn_max = int(c.get("warn_max", 5))
    status = "OK" if cnt24 <= ok_max else ("WARN" if cnt24 <= warn_max else "FAULT")
    add(c["id"], c.get("component", "?"), c["name"], status, f"近24h死信={cnt24} 条")

def run_jsonl_event_recent(c):
    log = env(c.get("log", ""))
    ev = c.get("event_type", "")
    try:
        out = subprocess.run(["tail", "-3000", log], capture_output=True, text=True, errors="replace").stdout
    except OSError:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{log} 不可读")
        return
    last_t = None
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line: continue
        try:
            d = json.loads(line)
            if d.get("event_type") == ev:
                last_t = d.get("t"); break
        except Exception:
            continue
    if last_t is None:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"近3000行无 '{ev}' 事件")
        return
    try:
        ts = datetime.datetime.fromisoformat(last_t.replace("Z", "+00:00"))
        age = (NOW - ts.astimezone()).total_seconds()
    except Exception:
        age = 0
    ok_s = float(c.get("ok_seconds", 1800)); warn_s = float(c.get("warn_seconds", 7200))
    status = "OK" if age < ok_s else ("WARN" if age < warn_s else "FAULT")
    add(c["id"], c.get("component", "?"), c["name"], status, f"最后 '{ev}' @ {last_t}（{age_label(age)}）")

def run_log_failure_ratio(c):
    log = env(c.get("log", ""))
    try:
        with open(log, "r", errors="replace") as f:
            lines = f.readlines()[-int(c.get("tail_lines", 100)):]
    except OSError:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{log} 不可读")
        return
    fails = sum(1 for l in lines if re.search(c.get("fail_pattern", ""), l))
    oks = sum(1 for l in lines if re.search(c.get("ok_pattern", ""), l))
    ok_max = int(c.get("ok_max_fail", 0)); warn_max = int(c.get("warn_max_fail", 3))
    status = "OK" if fails <= ok_max else ("WARN" if fails <= warn_max else "FAULT")
    add(c["id"], c.get("component", "?"), c["name"], status,
        f"近{c.get('tail_lines')}行: 失败={fails} 成功={oks}（SLO: 失败≤{ok_max}）")

def run_crontab_has(c):
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except Exception:
        cron = ""
    missing = [k for k in c.get("keys", []) if k not in cron]
    if not missing:
        add(c["id"], c.get("component", "?"), c["name"], "OK", f"cron 关键任务全在位（{len(c['keys'])}项）")
    else:
        add(c["id"], c.get("component", "?"), c["name"], "WARN", f"crontab 缺失: {' '.join(missing)}")

def run_backup_log(c):
    log = env(c.get("log", ""))
    snap_dir = env(c.get("snap_dir", ""))
    try:
        tail = open(log, "r", errors="replace").readlines()[-40:]
        errs = sum(1 for l in tail if re.search(c.get("no_error_pattern", "ERROR|失败|rc=[^0]"), l))
    except OSError:
        errs = -1
    # 快照新鲜度：递归找最新文件
    newest = 0.0
    if os.path.isdir(snap_dir):
        for root, dirs, files in os.walk(snap_dir):
            for fn in files:
                try:
                    newest = max(newest, os.stat(os.path.join(root, fn)).st_mtime)
                except OSError:
                    pass
    age = (NOW.timestamp() - newest) if newest else 999999.0
    ok_s = float(c.get("ok_seconds", 1800)); warn_s = float(c.get("warn_seconds", 7200))
    if errs < 0:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{log} 不可读")
    elif errs > 0:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"备份日志近40行含 ERROR/失败 x{errs}")
    elif age < ok_s:
        add(c["id"], c.get("component", "?"), c["name"], "OK", f"日志无 ERROR，快照 {age_label(age)}")
    elif age < warn_s:
        add(c["id"], c.get("component", "?"), c["name"], "WARN", f"快照 {age_label(age)} 偏旧")
    else:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"快照 {age_label(age)} 停更")

def run_date_file_recent(c):
    path = env(c.get("path", ""))
    try:
        content = open(path).read().strip()
    except OSError:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"{path} 不存在（夜巡从未成功？）")
        return
    today = datetime.date.today().isoformat()
    yday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if content in (today, yday):
        add(c["id"], c.get("component", "?"), c["name"], "OK", f"marker={content}（今天或昨天）")
    else:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"marker 停在 {content}——夜巡多日未成功")

def run_git_sync(c):
    repo = env(c.get("repo", ""))
    remote = c.get("remote", "origin")
    timeout = int(c.get("timeout", 20))
    try:
        local = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as e:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"本地 HEAD 读取失败: {e}")
        return
    try:
        out = subprocess.run(["git", "-C", repo, "ls-remote", remote, "HEAD"],
                             capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            add(c["id"], c.get("component", "?"), c["name"], "WARN", "远端无法核验（ls-remote 失败/网络）——玄鉴近期 WARN 来源")
            return
        remote_head = out.stdout.split()[0] if out.stdout.strip() else ""
    except subprocess.TimeoutExpired:
        add(c["id"], c.get("component", "?"), c["name"], "WARN", "远端核验超时（网络）——玄鉴近期 WARN 来源")
        return
    if local == remote_head:
        add(c["id"], c.get("component", "?"), c["name"], "OK", f"本地={local[:12]} == 远端={remote_head[:12]}")
    else:
        add(c["id"], c.get("component", "?"), c["name"], "FAULT",
            f"本地 {local[:12]} ≠ 远端 {remote_head[:12]}（push_verify FAIL 根因）")

HANDLERS = {
    "http_json": run_http_check,
    "json_file_assert": run_json_file_check,
    "file_fresh": run_file_fresh,
    "file_grep_recent": run_file_grep_recent,
    "process_alive": run_process_alive,
    "port_listen": run_port_listen,
    "sqlite_ratio": run_sqlite_ratio,
    "sqlite_gt": run_sqlite_gt,
    "sandglass_mirror": run_sandglass_mirror,
    "jsonl_level_count": run_jsonl_level_count,
    "dlq_recent": run_dlq_recent,
    "jsonl_event_recent": run_jsonl_event_recent,
    "log_failure_ratio": run_log_failure_ratio,
    "crontab_has": run_crontab_has,
    "backup_log": run_backup_log,
    "date_file_recent": run_date_file_recent,
    "git_sync": run_git_sync,
}

# ---------------- 主流程 ----------------
try:
    doc = yaml.safe_load(open(CONTRACTS_FILE))
except Exception as e:
    print(f"❌ CONTRACTS.yaml 解析失败: {e}"); sys.exit(2)

checks = doc.get("checks", [])
unknown = sorted({c.get("type") for c in checks} - set(HANDLERS))
if unknown:
    print(f"❌ CONTRACTS.yaml 含未实现的 check type: {unknown}"); sys.exit(2)

for c in checks:
    handler = HANDLERS.get(c.get("type"))
    if handler:
        try:
            handler(c)
        except Exception as e:
            add(c["id"], c.get("component", "?"), c["name"], "FAULT", f"校验异常: {e}")

# ---------------- 输出 ----------------
EMOJI = {"OK": "✅", "WARN": "⚠️", "FAULT": "❌"}
V = {"OK": 0, "WARN": 0, "FAULT": 0}
for _, _, _, st, _ in results:
    V[st] += 1

lines = []
lines.append("")
lines.append(f"===== Agent OS 契约校验 contract_check · {NOW_ISO} =====")
lines.append(f"契约注册表: {CONTRACTS_FILE}（schema {doc.get('schema_version', '?')}）")
lines.append(f"覆盖: {len(checks)} 项机器校验 / {len(doc.get('contracts', []))} 条组件间契约")
lines.append("")
comp_order = {}
for cid, comp, name, st, ev in results:
    comp_order.setdefault(comp, []).append((cid, name, st, ev))
for comp in sorted(comp_order, key=lambda x: (x != "contract", x)):
    for cid, name, st, ev in comp_order[comp]:
        lines.append(f"{EMOJI[st]} [{cid}] {name}: {ev}")
lines.append("")
lines.append(f"===== 汇总 =====")
lines.append(f"绿={V['OK']} 黄={V['WARN']} 红={V['FAULT']}")
if V["FAULT"] > 0:
    lines.append("判定: ❌ 有契约违反（exit 2）——见红色项；契约漂移=改 A 砸 B/C/D 的预警")
    EXIT = 2
elif V["WARN"] > 0:
    lines.append("判定: ⚠️ 有警告（exit 1）")
    EXIT = 1
else:
    lines.append("判定: ✅ 全绿（exit 0）——契约层无漂移")
    EXIT = 0

report = "\n".join(lines)
print(report)

# ---------------- cron 模式：追加日志 + 状态变化告警 ----------------
if MODE == "--cron":
    os.makedirs(LOG_DIR, exist_ok=True)
    HL_LOG = os.path.join(LOG_DIR, "contract_check.log")
    STATE_FILE = os.path.join(RUN_DIR, "contract_check.state")
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(HL_LOG, "a") as f:
        f.write("\n########## %s 契约校验 (cron) ##########\n" % NOW_ISO)
        f.write(report + "\n")
    # 状态变化检测
    new_state = {cid: st for cid, _, _, st, _ in results}
    old = {}
    if os.path.exists(STATE_FILE):
        for line in open(STATE_FILE):
            line = line.strip()
            if "|" in line:
                k, v = line.split("|", 1)
                old[k] = v
    with open(HL_LOG, "a") as f:
        for cid, st in new_state.items():
            old_st = old.get(cid)
            if old_st is None: continue
            if st != old_st:
                ev = next((e for c2, _, _, s2, e in results if c2 == cid), "")
                if st == "OK":
                    f.write(f"✅ [{NOW_ISO}] [{cid}] 恢复: {ev}\n")
                elif old_st == "OK":
                    f.write(f"🚨 [{NOW_ISO}] [{cid}] 契约违反: {ev}\n")
                else:
                    f.write(f"⚠️ [{NOW_ISO}] [{cid}] 状态变化 {old_st}→{st}: {ev}\n")
    with open(STATE_FILE, "w") as f:
        for cid, st in new_state.items():
            f.write(f"{cid}|{st}\n")
    print(f"[cron] 已追加 {HL_LOG}，状态文件 {STATE_FILE}")

sys.exit(EXIT)
PY
