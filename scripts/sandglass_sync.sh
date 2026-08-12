#!/bin/bash
# =============================================================
# sandglass_sync.sh — 沙漏 db 检索镜像增量同步 + 自愈守护（契约 SG-05）
# -------------------------------------------------------------
# 背景：SG-05 要求 db 镜像 ≥ txt 权威源有效条目 95%。现状 sync_incremental
#   只在查询/写入时被动触发（sandglass_http_api / sandglass_vault），无独立
#   守护 → 无查询即不同步，漂移无拦截（2026-08-11 审计硬缺口 1）。
# 机制（每 10min 由 cron 调用）：
#   ① sync_incremental()：mtime 门控增量同步（txt 未变则跳过，近零开销）
#   ② 同步率 = db 行数 / txt 去重后有效条目；< 95% → 自动 sync_all() 全量重建
#     （db 是 txt 的检索镜像，可安全重建；失忆根因-2 修复 84e2c1f 同款机制）
# 口径说明：txt 权威源有双写历史（同一 (ts,sender,text) 出现两次），db 镜像
#   按设计去重 → 分母用去重后条目数，与 contract_check.sh SG-05 口径一致。
# 退出码：0=OK  1=自愈后仍未达标  2=环境/源不可用
# =============================================================
set -u

AGENT_OS_HOME="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi

# 零硬编码：全部从 env.local 推导（缺失时按仓库相对布局兜底）
SANDGLASS_SOURCE="${SANDGLASS_SOURCE:-$AGENT_OS_HOME/../所有自动化/轻如烟/sandglass_source}"
NEXSANDBASE_HOME="${NEXSANDBASE_HOME:-$AGENT_OS_HOME/../所有自动化/轻如烟/sandglass}"
SANDGLASS_TXT="${NEXSANDBASE_HOME}/sandglass.txt"
SANDGLASS_DB="${NEXSANDBASE_HOME}/sandglass.db"

if [ ! -f "$SANDGLASS_TXT" ]; then
    echo "$(date '+%F %T') ❌ sandglass.txt 不存在: $SANDGLASS_TXT" >&2
    exit 2
fi
if [ ! -d "$SANDGLASS_SOURCE" ]; then
    echo "$(date '+%F %T') ❌ sandglass_source 不存在: $SANDGLASS_SOURCE" >&2
    exit 2
fi

cd "$SANDGLASS_SOURCE" || exit 2
export NEXSANDBASE_HOME

python3 - <<'PY'
import os, sys, sqlite3

NEX = os.environ.get("NEXSANDBASE_HOME", "")
TXT = os.path.join(NEX, "sandglass.txt")
DB = os.path.join(NEX, "sandglass.db")

try:
    import sandglass_sqlite as sg
except Exception as e:
    print(f"❌ 导入 sandglass_sqlite 失败: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(2)


def txt_unique_count() -> int:
    """txt 权威源去重后有效条目数（与 sg._parse_entries 同语义：时间戳行 + (ts,sender,text) 去重）。"""
    from sandglass_vault import _parse_line
    import re as _re
    _TS_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}")
    seen = set()
    n = 0
    with open(TXT, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            ts, sender, text = _parse_line(line)
            if ts and _TS_RE.match(ts):
                key = (ts, sender, text)
                if key not in seen:
                    seen.add(key)
                    n += 1
    return n


def db_count() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=15.0)
    try:
        return con.execute("SELECT COUNT(*) FROM sandglass").fetchone()[0]
    finally:
        con.close()


try:
    added = sg.sync_incremental()
    dcnt = db_count()
    tcnt = txt_unique_count()
    ratio = dcnt / tcnt if tcnt else 0.0
    print(f"incremental: 新增={added} db={dcnt} txt去重条目={tcnt} 同步率={ratio*100:.1f}%")

    if ratio < 0.95:
        print(f"⚠️ 同步率 {ratio*100:.1f}% < 95% → 触发全量重建 sync_all()（db 是 txt 检索镜像，可安全重建）")
        n = sg.sync_all()
        dcnt2 = db_count()
        ratio2 = dcnt2 / tcnt if tcnt else 0.0
        print(f"全量重建完成: 写入={n} 重建后 db={dcnt2} 同步率={ratio2*100:.1f}%")
        if ratio2 < 0.95:
            print("❌ 全量重建后仍未达 95%，需人工排查（txt 权威源异常？）", file=sys.stderr)
            sys.exit(1)
    else:
        print("OK 同步率达标")
except Exception as e:
    print(f"❌ 同步异常: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
PY
