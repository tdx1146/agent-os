#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memory_trust 测试（自我怀疑系统 P3.2 数据层）
=============================================
临时库验证：引用 / 反驳 / 时效加权 / 强制降权 / 账本联动 / JSON 输出 / CLI。

运行：
  /vol1/@apphome/trim.openclaw/data/home/agentos/living-memory-system/.venv/bin/python \
      /vol1/@apphome/trim.openclaw/data/workspace/scripts/test_memory_trust.py

退出码：0=全部通过，1=有失败。
"""

import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta

# 保证能 import 脚本目录里的 memory_trust
_SCRIPTS = "/vol1/@apphome/trim.openclaw/data/workspace/scripts"
sys.path.insert(0, _SCRIPTS)

import memory_trust as mt  # noqa: E402

VENV_PY = "/vol1/@apphome/trim.openclaw/data/home/agentos/living-memory-system/.venv/bin/python"

NOW = time.time()
# 注意：strftime 秒级截断（丢弃小数秒），与 time.time() 最多差 ~1s。
# 纯函数测试显式传 now= 对齐；存储层测试用宽松 eps=1e-3。
TS_NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
TS_NOW_EPOCH = datetime.strptime(TS_NOW, "%Y-%m-%d %H:%M:%S").timestamp()
TS_30D = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
TS_5D = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
TS_1D = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = ""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ {name}  {detail}")


def approx(a, b, eps=1e-6):
    return abs(a - b) <= eps


# 存储层依赖 time.time()（带小数秒），而测试用 ts 是秒级截断 → 用宽松容差
APPROX_STORE = 1e-3


def setup_env():
    """建临时 sandglass.db + doubt.db，返回 (tmpdir, store)。"""
    tmp = tempfile.mkdtemp(prefix="memtrust_test_")
    sg = os.path.join(tmp, "sandglass.db")
    db = os.path.join(tmp, "doubt.db")

    con = sqlite3.connect(sg)
    con.execute("CREATE TABLE sandglass (id INTEGER PRIMARY KEY, ts TEXT, sender TEXT, text TEXT)")
    rows = [
        (1, TS_NOW, "user", "alpha 事实：服务器在南京"),
        (2, TS_30D, "user", "beta 事实：旧配置"),
        (3, "- 新断言 3条：F178 沙漏注入p", "system", "alpha 更新：无时间戳"),
        (4, TS_5D, "user", "alpha 第三：端口 18888"),
        (5, TS_1D, "user", "gamma 其他：无关"),
        (6, TS_NOW, "user", "alpha 第四：最新一条"),
        (7, "【事件】事件ID 98765", "system", "junk ts 另一条"),
    ]
    con.executemany("INSERT INTO sandglass VALUES (?,?,?,?)", rows)
    con.commit()
    con.close()

    con = sqlite3.connect(db)
    con.execute(
        """CREATE TABLE doubt_episode (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            t REAL NOT NULL,
            trigger_type TEXT NOT NULL,
            suspicion TEXT,
            queried INTEGER NOT NULL DEFAULT 0,
            answer_changed INTEGER NOT NULL DEFAULT 0,
            overturn_evidence TEXT,
            user_reaction TEXT,
            topic TEXT,
            confidence_after REAL
        )"""
    )
    con.commit()
    con.close()

    store = mt.TrustStore(doubt_db=db, sandglass_db=sg)
    return tmp, store, sg, db


def main() -> int:
    print("== 1. 纯函数：信任度计算 ==")
    # 新鲜、无反驳、无引用 → 1.0（now 显式对齐，避免秒级截断误差）
    check("fresh 0/0 → 1.0",
          approx(mt.compute_trust_weight(TS_NOW, 0, 0, now=TS_NOW_EPOCH), 1.0))
    # 30 天旧 → 1/31
    check("30d old 0/0 → 1/31",
          approx(mt.compute_trust_weight(TS_30D, 0, 0,
                                         now=TS_NOW_EPOCH), 1.0 / 31.0))
    # 新鲜 1 反驳 0 引用 → 1×(1-1/1)=0
    check("fresh 1 rebuttal/0 ref → 0.0",
          approx(mt.compute_trust_weight(TS_NOW, 1, 0, now=TS_NOW_EPOCH), 0.0))
    # 新鲜 1 反驳 3 引用 → 0.75
    check("fresh 1/3 → 0.75",
          approx(mt.compute_trust_weight(TS_NOW, 1, 3, now=TS_NOW_EPOCH), 0.75))
    # ≥2 反驳 → 强制 0.1（即使引用很多）
    check("rebuttal=2 强制 0.1",
          approx(mt.compute_trust_weight(TS_NOW, 2, 99), 0.1))
    check("rebuttal=5 强制 0.1",
          approx(mt.compute_trust_weight(TS_NOW, 5, 99), 0.1))
    # ts 无法解析 → age_days=0 不惩罚
    check("junk ts → 不惩罚", approx(mt.compute_trust_weight("- 新断言 x", 0, 0), 1.0))
    # 未来时间戳 → age_days 收敛 0
    check("future ts → clamp", approx(mt.compute_trust_weight("2999-01-01 00:00:00", 0, 0), 1.0))

    print("== 2. 容错 ts 解析 ==")
    check("epoch float", approx(mt.parse_ts(1700000000.0), 1700000000.0))
    check("标准格式", approx(mt.parse_ts(TS_NOW), datetime.strptime(TS_NOW, "%Y-%m-%d %H:%M:%S").timestamp()))
    check("ISO T 格式", approx(mt.parse_ts("2026-08-03T12:00:00"),
                               datetime.strptime("2026-08-03 12:00:00", "%Y-%m-%d %H:%M:%S").timestamp()))
    check("纯日期", approx(mt.parse_ts("2026-08-03"),
                           datetime.strptime("2026-08-03", "%Y-%m-%d").timestamp()))
    check("junk → None", mt.parse_ts("- 新断言 3条：F178") is None)
    check("空 → None", mt.parse_ts("") is None and mt.parse_ts(None) is None)

    tmp, store, sg, db = setup_env()
    try:
        print("== 3. 引用 / 反驳 / 查询接口 ==")
        w = store.record_reference(1)
        check("record_reference(1) → ~1.0", approx(w, 1.0, APPROX_STORE), f"got {w}")
        row = sqlite3.connect(db).execute(
            "SELECT reference_count, last_referenced_at FROM memory_trust WHERE memory_id=1"
        ).fetchone()
        check("引用计数=1", row[0] == 1, f"got {row}")
        check("last_referenced_at 已写", row[1] is not None and len(row[1]) >= 19)

        store.record_reference(2)  # 30 天旧
        w2 = store.get_trust_weight(2)
        check("30d 旧 +1引用 → 1/31", approx(w2, 1.0 / 31.0), f"got {w2}")

        w = store.record_rebuttal(1)
        check("rebuttal(1) → 0.5", approx(w, 0.5, APPROX_STORE), f"got {w}")
        check("get_trust_weight(1) 动态一致",
              approx(store.get_trust_weight(1), 0.5, APPROX_STORE))

        w = store.record_rebuttal(1)
        check("第二次反驳 → 强制 0.1", approx(w, 0.1), f"got {w}")
        check("get_trust_weight(1) = 0.1", approx(store.get_trust_weight(1), 0.1))

        # 未跟踪记忆 → 默认 1.0
        check("未跟踪 memory → 1.0", approx(store.get_trust_weight(999), 1.0))
        # junk ts 的记忆可跟踪且不惩罚
        store.record_reference(3)
        check("junk ts 记忆 weight=1.0", approx(store.get_trust_weight(3), 1.0), f"got {store.get_trust_weight(3)}")

        print("== 4. get_trust_map / limit ==")
        m = store.get_trust_map()
        check("map 返回全部已跟踪", len(m) == 3, f"got {len(m)}: {[e['memory_id'] for e in m]}")
        keys = {"memory_id", "ts", "trust_weight", "rebuttal_count", "reference_count"}
        check("map 条目字段齐全", keys.issubset(set(m[0].keys())))
        m2 = store.get_trust_map(limit=2)
        check("limit=2", len(m2) == 2, f"got {len(m2)}")
        check("map 按 memory_id 倒序", [e["memory_id"] for e in m] == [3, 2, 1])

        print("== 5. JSON 输出（原子写） ==")
        payload = store.refresh_json()
        check("payload count=3", payload["count"] == 3, f"got {payload['count']}")
        with open("/tmp/memory-trust.json", encoding="utf-8") as f:
            data = json.load(f)
        check("JSON 可解析且 updated_at 存在", "updated_at" in data and "entries" in data)
        check("JSON entries 字段齐全",
              all(set(e.keys()) == {"memory_id", "ts", "trust_weight", "rebuttal_count", "reference_count"}
                  for e in data["entries"]))
        e1 = next(e for e in data["entries"] if e["memory_id"] == 1)
        check("JSON 中 memory 1 权重=0.1", approx(e1["trust_weight"], 0.1))
        leftovers = glob.glob("/tmp/memory-trust.json.tmp.*")
        check("无 tmp 残留（原子写）", len(leftovers) == 0, f"leftovers={leftovers}")

        print("== 6. doubt 账本联动（conflict + answer_changed） ==")
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO doubt_episode (t, trigger_type, suspicion, answer_changed, topic) "
            "VALUES (?, 'conflict', '上次说南京', 1, 'alpha')",
            (NOW,),
        )
        con.execute(
            "INSERT INTO doubt_episode (t, trigger_type, suspicion, answer_changed, topic) "
            "VALUES (?, 'conflict', '翻案', 0, 'alpha')",  # answer_changed=0 → 不处理
            (NOW,),
        )
        con.execute(
            "INSERT INTO doubt_episode (t, trigger_type, suspicion, answer_changed, topic) "
            "VALUES (?, 'user_correction', '纠正但非conflict', 1, 'beta')",  # 非 conflict → 不处理
            (NOW,),
        )
        con.commit()
        con.close()

        r = store.sync_from_doubt_ledger()
        # alpha 最近 3 条：id 6,4,3（id 1 不在 top3）
        check("联动命中 3 条", r["rebutted_count"] == 3, f"got {r}")
        check("命中 id 6/4/3", set(r["rebutted_memory_ids"]) == {6, 4, 3}, f"got {r}")
        rc = {mid: store.get_trust_weight(mid) for mid in (6, 4, 3, 1)}
        # 公式：1-反驳/(引用+1)。id6/4 引用=0、反驳=1 → 比率 1.0 → 权重 0
        check("id6 被反驳且0引用 → 0.0", approx(rc[6], 0.0, APPROX_STORE), f"got {rc[6]}")
        check("id4 被反驳且0引用 → 0.0", approx(rc[4], 0.0, APPROX_STORE), f"got {rc[4]}")
        check("id3 被反驳但1引用 → 0.5", approx(rc[3], 0.5, APPROX_STORE), f"got {rc[3]}")
        check("id1 未被额外反驳（保持 0.1）", approx(store.get_trust_weight(1), 0.1))
        # 幂等：再跑一次不叠加
        r2 = store.sync_from_doubt_ledger()
        check("幂等：二次 sync 不叠加", r2["episodes_seen"] == 0 and r2["rebutted_count"] == 0, f"got {r2}")
        check("id6 仍为 0.0", approx(store.get_trust_weight(6), 0.0, APPROX_STORE))

        # 新账本（gamma topic）→ 只动 id5
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO doubt_episode (t, trigger_type, answer_changed, topic) "
            "VALUES (?, 'conflict', 1, 'gamma')",
            (NOW,),
        )
        con.commit()
        con.close()
        r3 = store.sync_from_doubt_ledger()
        check("gamma 联动 id5", set(r3["rebutted_memory_ids"]) == {5}, f"got {r3}")
        check("id5 0引用被反驳 → 0.0", approx(store.get_trust_weight(5), 0.0, APPROX_STORE),
              f"got {store.get_trust_weight(5)}")

        print("== 7. 沙漏主表未被改动 ==")
        con = sqlite3.connect(sg)
        tables = [t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        con.close()
        check("sandglass.db 仅原表（未 ALTER）", tables == ["sandglass"], f"got {tables}")

        print("== 8. CLI：refresh / status ==")
        env = dict(os.environ, NEXSANDBASE_HOME=tmp)
        p = subprocess.run(
            [VENV_PY, os.path.join(_SCRIPTS, "memory_trust.py"), "refresh"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        check("CLI refresh 退出码 0", p.returncode == 0, p.stderr[-300:])
        out = json.loads(p.stdout)
        check("CLI refresh 输出条目数", out["entries"] == 6, f"got {out}")
        p2 = subprocess.run(
            [VENV_PY, "-m", "memory_trust", "status"],
            capture_output=True, text=True, env=env, cwd=_SCRIPTS, timeout=60,
        )
        check("CLI -m status 退出码 0", p2.returncode == 0, p2.stderr[-300:])
        st = json.loads(p2.stdout)
        check("status tracked=6", st["tracked"] == 6, f"got {st}")
        check("status 强制降权≥1", st["forced_low"] >= 1, f"got {st}")
        check("status 账本游标=4", st["ledger_cursor"] == 4, f"got {st}")

        print("== 9. reset_trust ==")
        store.reset_trust(1)
        w = store.get_trust_weight(1)
        check("reset 后权重回 ~1.0", approx(w, 1.0, APPROX_STORE), f"got {w}")
        row = sqlite3.connect(db).execute(
            "SELECT rebuttal_count, reference_count FROM memory_trust WHERE memory_id=1"
        ).fetchone()
        check("reset 后计数器清零", row == (0, 0), f"got {row}")
    finally:
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n结果：{_passed} 通过，{_failed} 失败")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
