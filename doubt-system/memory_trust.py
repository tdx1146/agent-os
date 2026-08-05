#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆信任度系统（自我怀疑系统 P3.2 数据层）
============================================
防回声室：被推翻的记忆要降权，旧记忆要衰减。
注入选择加权 = freshness × (1 - 反驳率)

  trust_weight = 1/(1+age_days) × (1 - rebuttal/(reference+1))
  被反驳 ≥2 次 → trust_weight 强制 0.1

存储设计（P3.2 要求）：
  - 独立表 memory_trust 建在 doubt.db（不 ALTER 沙漏主表，防破坏 sync_all）
  - memory_id 对应 sandglass.id；沙漏主表只读（SQLite mode=ro / 只 SELECT）
  - 单写者：memory_trust / memory_trust_meta 只由本模块写入

接口（函数）：
  record_reference(memory_id)          引用 +1（last_referenced_at 刷新，重算权重）
  record_rebuttal(memory_id)           反驳 +1（触发信任度重算，≥2 强制 0.1）
  get_trust_weight(memory_id)          查询时动态重算（含时效衰减，无需等待 refresh）
  get_trust_map(limit=None)            全表或 topN（按 memory_id 倒序），动态重算
  reset_trust(memory_id)               清零计数器（运维/测试用）
  refresh_json(limit=None)             重算全部 + 原子写 /tmp/memory-trust.json
  sync_from_doubt_ledger()             doubt 账本联动（见下）

doubt 账本联动（启发式）：
  doubt_episode 里 answer_changed=1 且 trigger_type='conflict' 的记录
  → 对应 topic 的近期记忆 rebuttal+1（同 topic 最近 3 条）
  → 幂等：last_synced_episode_id 记于 memory_trust_meta，重复执行不叠加

CLI：
  python3 -m memory_trust refresh [--limit N]   重算并刷新 /tmp/memory-trust.json
  python3 -m memory_trust sync                  doubt 账本 → rebuttal 联动
  python3 -m memory_trust status                摘要（条目数/降权数/账本游标）
  python3 -m memory_trust reset <memory_id>     清零单条计数器
  （在 scripts/ 目录下运行，或 PYTHONPATH=scripts）

环境变量：
  NEXSANDBASE_HOME  沙漏数据目录（默认 /vol2/1000/AI专用/所有自动化/轻如烟/sandglass）
"""

import argparse
import fcntl
import json
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime

# ── 路径（与 night_patrol.py / lesson_capture.py 一致）─────────
_SANDBASE_HOME = os.environ.get(
    "NEXSANDBASE_HOME",
    "/vol2/1000/AI专用/所有自动化/轻如烟/sandglass",
)
_DOUBT_DB = os.path.join(_SANDBASE_HOME, "doubt.db")
_SANDGLASS_DB = os.path.join(_SANDBASE_HOME, "sandglass.db")
_OP_LOG = "/vol2/1000/AI专用/Agent OS/iso-sand/data/operation_log.jsonl"
_TRUST_JSON = "/tmp/memory-trust.json"
_TRUST_JSON_LOCK = "/tmp/memory-trust.lock"

# 强制降权阈值：被反驳 ≥2 次 → trust_weight = 0.1
REBUTTAL_FORCE_FLOOR = 2
FORCED_WEIGHT = 0.1
# 默认权重：未被跟踪/无法解析的记忆（中性，不惩罚也不奖励）
DEFAULT_WEIGHT = 1.0
# 同 topic 反驳联动的近期记忆条数
TOPIC_REBUTTAL_K = 3

_TS_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)


# ── 纯函数：信任度计算 ────────────────────────────────────────

def parse_ts(ts) -> float | None:
    """容错解析沙漏 ts → 秒级时间戳。

    支持：'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD HH:MM' / 'YYYY-MM-DD' /
          ISO 'T' 分隔 / 数字 epoch；带多余尾巴时先取前 19 字符。
    解析失败返回 None（调用方按 age_days=0 处理，不惩罚）。
    """
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    s = str(ts).strip()
    if not s:
        return None
    # 数字 epoch（可能是字符串形态）
    try:
        return float(s)
    except ValueError:
        pass
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    # 带其他尾巴的 'YYYY-MM-DD ...'：取前 19 字符再试
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        head = s[:19] if len(s) >= 19 else s[:10]
        for fmt in _TS_FORMATS:
            try:
                return datetime.strptime(head, fmt).timestamp()
            except ValueError:
                continue
    return None


def compute_trust_weight(ts, rebuttal_count: int, reference_count: int,
                         now: float | None = None) -> float:
    """trust_weight = 1/(1+age_days) × (1 - rebuttal/(reference+1))。

    - age_days 由记忆 ts 计算；ts 无法解析 → age_days=0（不额外惩罚）
    - 被反驳 ≥2 次 → 强制 0.1（推翻过两次的记忆基本不可信）
    - 结果收敛到 [0.0, 1.0]
    """
    now = time.time() if now is None else now
    rebuttal_count = max(0, int(rebuttal_count or 0))
    reference_count = max(0, int(reference_count or 0))
    if rebuttal_count >= REBUTTAL_FORCE_FLOOR:
        return FORCED_WEIGHT
    age_days = 0.0
    t = parse_ts(ts)
    if t is not None:
        age_days = max(0.0, (now - t) / 86400.0)
    freshness = 1.0 / (1.0 + age_days)
    rebuttal_rate = rebuttal_count / (reference_count + 1.0)  # +1 防除零
    w = freshness * (1.0 - rebuttal_rate)
    return max(0.0, min(1.0, w))


# ── 存储层 ────────────────────────────────────────────────────

class TrustStore:
    """memory_trust 数据访问层。

    参数可覆盖路径，便于测试用临时库；默认走 NEXSANDBASE_HOME。
    """

    def __init__(self, doubt_db: str | None = None, sandglass_db: str | None = None):
        self.doubt_db = doubt_db or _DOUBT_DB
        self.sandglass_db = sandglass_db or _SANDGLASS_DB
        self._sg_con: sqlite3.Connection | None = None

    # ---- 连接 ----
    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.doubt_db, timeout=30)
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA foreign_keys=OFF")
        return con

    def _init_schema(self, con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_trust (
                memory_id         INTEGER PRIMARY KEY,
                rebuttal_count    INTEGER NOT NULL DEFAULT 0,
                reference_count   INTEGER NOT NULL DEFAULT 0,
                last_referenced_at TEXT,
                trust_weight      REAL    NOT NULL DEFAULT 1.0,
                updated_at        TEXT    NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_trust_meta (
                k TEXT PRIMARY KEY,
                v TEXT
            )
            """
        )

    def _sandglass_con(self) -> sqlite3.Connection:
        """只读沙漏主表连接（懒加载，mode=ro 绝不写）"""
        if self._sg_con is None:
            self._sg_con = sqlite3.connect(
                f"file:{self.sandglass_db}?mode=ro", uri=True, timeout=30
            )
            self._sg_con.execute("PRAGMA busy_timeout=30000")
        return self._sg_con

    def close(self) -> None:
        if self._sg_con is not None:
            self._sg_con.close()
            self._sg_con = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ---- 内部 ----
    def _memory_ts(self, memory_id: int) -> str | None:
        try:
            row = self._sandglass_con().execute(
                "SELECT ts FROM sandglass WHERE id=?", (memory_id,)
            ).fetchone()
        except sqlite3.Error:
            return None
        return row[0] if row else None

    def _ensure_row(self, con: sqlite3.Connection, memory_id: int) -> None:
        con.execute(
            "INSERT OR IGNORE INTO memory_trust "
            "(memory_id, rebuttal_count, reference_count, last_referenced_at, trust_weight, updated_at) "
            "VALUES (?,0,0,NULL,?,?)",
            (memory_id, DEFAULT_WEIGHT, _now_str()),
        )

    def _recompute(self, con: sqlite3.Connection, memory_id: int) -> float:
        row = con.execute(
            "SELECT rebuttal_count, reference_count FROM memory_trust WHERE memory_id=?",
            (memory_id,),
        ).fetchone()
        if row is None:
            return DEFAULT_WEIGHT
        w = compute_trust_weight(self._memory_ts(memory_id), row[0], row[1])
        con.execute(
            "UPDATE memory_trust SET trust_weight=?, updated_at=? WHERE memory_id=?",
            (w, _now_str(), memory_id),
        )
        return w

    # ---- 公开接口 ----
    def record_reference(self, memory_id: int) -> float:
        """引用 +1：刷新 last_referenced_at 并重算信任度。返回新权重。"""
        memory_id = int(memory_id)
        con = self._connect()
        try:
            self._init_schema(con)
            self._ensure_row(con, memory_id)
            con.execute(
                "UPDATE memory_trust SET reference_count=reference_count+1, "
                "last_referenced_at=?, updated_at=? WHERE memory_id=?",
                (_now_str(), _now_str(), memory_id),
            )
            w = self._recompute(con, memory_id)
            con.commit()
            return w
        finally:
            con.close()

    def record_rebuttal(self, memory_id: int) -> float:
        """反驳 +1：触发信任度重算。被反驳 ≥2 次后权重强制 0.1。返回新权重。"""
        memory_id = int(memory_id)
        con = self._connect()
        try:
            self._init_schema(con)
            self._ensure_row(con, memory_id)
            con.execute(
                "UPDATE memory_trust SET rebuttal_count=rebuttal_count+1, "
                "updated_at=? WHERE memory_id=?",
                (_now_str(), memory_id),
            )
            w = self._recompute(con, memory_id)
            con.commit()
            return w
        finally:
            con.close()

    def get_trust_weight(self, memory_id: int) -> float:
        """查询时动态重算（含时效衰减，无需等待 refresh）。未跟踪 → 1.0。"""
        memory_id = int(memory_id)
        con = self._connect()
        try:
            self._init_schema(con)
            row = con.execute(
                "SELECT rebuttal_count, reference_count FROM memory_trust WHERE memory_id=?",
                (memory_id,),
            ).fetchone()
            if row is None:
                return DEFAULT_WEIGHT
            return compute_trust_weight(self._memory_ts(memory_id), row[0], row[1])
        finally:
            con.close()

    def get_trust_map(self, limit: int | None = None) -> list[dict]:
        """全表或 topN（memory_id 倒序），每条动态重算权重。

        返回：[{memory_id, ts, trust_weight, rebuttal_count, reference_count,
                last_referenced_at, updated_at}]
        """
        con = self._connect()
        try:
            self._init_schema(con)
            rows = con.execute(
                "SELECT memory_id, rebuttal_count, reference_count, "
                "last_referenced_at, updated_at FROM memory_trust "
                "ORDER BY memory_id DESC"
            ).fetchall()
        finally:
            con.close()
        if limit is not None and limit > 0:
            rows = rows[: int(limit)]
        if not rows:
            return []
        # 批量取 ts（一次只读查询）
        ids = [r[0] for r in rows]
        ts_map: dict[int, str | None] = {}
        try:
            placeholders = ",".join("?" * len(ids))
            for rid, ts in self._sandglass_con().execute(
                f"SELECT id, ts FROM sandglass WHERE id IN ({placeholders})", ids
            ):
                ts_map[rid] = ts
        except sqlite3.Error:
            ts_map = {}
        out = []
        for mid, rb, rc, last_ref, upd in rows:
            ts = ts_map.get(mid)
            out.append(
                {
                    "memory_id": mid,
                    "ts": ts,
                    "trust_weight": compute_trust_weight(ts, rb, rc),
                    "rebuttal_count": rb,
                    "reference_count": rc,
                    "last_referenced_at": last_ref,
                    "updated_at": upd,
                }
            )
        return out

    def reset_trust(self, memory_id: int) -> None:
        """清零单条计数器（运维/测试用）。"""
        memory_id = int(memory_id)
        con = self._connect()
        try:
            self._init_schema(con)
            self._ensure_row(con, memory_id)
            con.execute(
                "UPDATE memory_trust SET rebuttal_count=0, reference_count=0, "
                "trust_weight=?, updated_at=? WHERE memory_id=?",
                (DEFAULT_WEIGHT, _now_str(), memory_id),
            )
            con.commit()
        finally:
            con.close()

    # ---- doubt 账本联动 ----
    def _recent_memories_for_topic(self, topic: str, k: int = TOPIC_REBUTTAL_K) -> list[int]:
        """启发式：topic 关键词 → 沙漏文本 LIKE 匹配 → 最近 k 条 memory_id。"""
        topic = (topic or "").strip()
        if not topic:
            return []
        candidates = [topic]
        # 长关键词拆分兜底（多词 topic 取最长片段）
        for sep in (" ", "，", ",", "/", "／"):
            if sep in topic:
                parts = [p.strip() for p in topic.split(sep) if len(p.strip()) >= 2]
                if parts:
                    candidates = [max(parts, key=len)] + candidates
                break
        seen: set[int] = set()
        result: list[int] = []
        try:
            con = self._sandglass_con()
            for kw in candidates:
                if len(seen) >= k:
                    break
                pat = "%" + kw.replace("%", "\\%").replace("_", "\\_") + "%"
                rows = con.execute(
                    "SELECT id FROM sandglass WHERE text LIKE ? ESCAPE '\\' "
                    "ORDER BY id DESC LIMIT ?",
                    (pat, k),
                ).fetchall()
                for (mid,) in rows:
                    if mid not in seen:
                        seen.add(mid)
                        result.append(mid)
                    if len(seen) >= k:
                        break
        except sqlite3.Error:
            return []
        return result[:k]

    def sync_from_doubt_ledger(self) -> dict:
        """doubt 账本 → rebuttal 联动（幂等）。

        处理 answer_changed=1 且 trigger_type='conflict' 的账本记录：
        其 topic 对应的近期记忆（最近 3 条）rebuttal+1。
        游标 last_synced_episode_id 存 memory_trust_meta，重复执行不叠加。
        """
        con = self._connect()
        try:
            self._init_schema(con)
            meta_row = con.execute(
                "SELECT v FROM memory_trust_meta WHERE k='last_synced_episode_id'"
            ).fetchone()
            cursor = int(meta_row[0]) if meta_row and meta_row[0] else 0
            eps = con.execute(
                "SELECT id, topic FROM doubt_episode "
                "WHERE answer_changed=1 AND trigger_type='conflict' AND id>? "
                "ORDER BY id",
                (cursor,),
            ).fetchall()
            rebutted: list[int] = []
            last = cursor
            for eid, topic in eps:
                last = max(last, eid)
                for mid in self._recent_memories_for_topic(topic):
                    self.record_rebuttal(mid)
                    rebutted.append(mid)
            if last > cursor:
                con.execute(
                    "INSERT INTO memory_trust_meta (k, v) VALUES ('last_synced_episode_id', ?) "
                    "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    (str(last),),
                )
                con.commit()
            return {"episodes_seen": len(eps), "cursor": last,
                    "rebutted_memory_ids": sorted(set(rebutted)),
                    "rebutted_count": len(set(rebutted))}
        finally:
            con.close()

    # ---- 输出接口 ----
    def refresh_json(self, limit: int | None = None) -> dict:
        """重算全部信任度并原子写 /tmp/memory-trust.json。

        原子性：tmp 文件 + os.replace + flock 互斥；插件侧每轮可安全读取。
        """
        entries = self.get_trust_map(limit)
        payload = {
            "updated_at": _now_str(),
            "count": len(entries),
            "entries": [
                {
                    "memory_id": e["memory_id"],
                    "ts": e["ts"],
                    "trust_weight": round(e["trust_weight"], 6),
                    "rebuttal_count": e["rebuttal_count"],
                    "reference_count": e["reference_count"],
                }
                for e in entries
            ],
        }
        fd = os.open(_TRUST_JSON_LOCK, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            tmp_path = os.path.join(
                tempfile.gettempdir(), f"memory-trust.json.tmp.{os.getpid()}"
            )
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, _TRUST_JSON)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return payload

    def status(self) -> dict:
        con = self._connect()
        try:
            self._init_schema(con)
            n = con.execute("SELECT COUNT(*) FROM memory_trust").fetchone()[0]
            forced = con.execute(
                "SELECT COUNT(*) FROM memory_trust WHERE rebuttal_count>=?", 
                (REBUTTAL_FORCE_FLOOR,),
            ).fetchone()[0]
            rebutted = con.execute(
                "SELECT COUNT(*) FROM memory_trust WHERE rebuttal_count>0"
            ).fetchone()[0]
            meta_row = con.execute(
                "SELECT v FROM memory_trust_meta WHERE k='last_synced_episode_id'"
            ).fetchone()
        finally:
            con.close()
        return {
            "tracked": n,
            "rebutted": rebutted,
            "forced_low": forced,
            "ledger_cursor": int(meta_row[0]) if meta_row and meta_row[0] else 0,
            "json": _TRUST_JSON,
        }


# ── 工具 ──────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_op(action: str, result: str, detail: str) -> None:
    """记录 operation_log（审计串联；失败不阻塞主流程）"""
    try:
        rec = {
            "t": datetime.now().isoformat(),
            "level": "info" if result == "ok" else "warn",
            "actor": "memory_trust",
            "action": action,
            "target": "memory_trust",
            "result": result,
            "detail": detail,
        }
        with open(_OP_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── CLI ───────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="memory_trust", description="记忆信任度系统（P3.2 数据层）"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_refresh = sub.add_parser("refresh", help="重算信任度并写 /tmp/memory-trust.json")
    p_refresh.add_argument("--limit", type=int, default=None,
                           help="只输出 topN 条（默认全部）")

    sub.add_parser("sync", help="doubt 账本冲突翻案 → 同topic近期记忆 rebuttal+1")
    sub.add_parser("status", help="摘要")
    p_reset = sub.add_parser("reset", help="清零单条计数器")
    p_reset.add_argument("memory_id", type=int)

    args = parser.parse_args(argv)
    store = TrustStore()
    try:
        if args.cmd == "refresh":
            payload = store.refresh_json(args.limit)
            print(json.dumps({"updated_at": payload["updated_at"],
                              "entries": payload["count"],
                              "json": _TRUST_JSON}, ensure_ascii=False))
            log_op("memory_trust_refresh", "ok",
                   f"entries={payload['count']}")
        elif args.cmd == "sync":
            r = store.sync_from_doubt_ledger()
            print(json.dumps(r, ensure_ascii=False))
            log_op("memory_trust_sync", "ok",
                   f"episodes={r['episodes_seen']} rebutted={r['rebutted_count']}")
        elif args.cmd == "status":
            print(json.dumps(store.status(), ensure_ascii=False))
        elif args.cmd == "reset":
            store.reset_trust(args.memory_id)
            print(json.dumps({"reset": args.memory_id}, ensure_ascii=False))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
