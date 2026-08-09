"""
handlers.py — 统一 handler 机制（Phase 2 / D6）
================================================
- `Handler` 抽象基类：`handle(event) -> bool`（True=处理成功）
- `HandlerRegistry`：按 event_type 注册 handler（一个 event_type 可多个 handler），
  按注册顺序执行；单个 handler 抛异常只记死信/日志，不拖垮消费循环（异常隔离）
- 命名空间规范：handler 签名 `<system>.<domain>.<action>`（如 `audit.task_complete`、
  `interfaces.store`；玄鉴预留 `xuanjian.pipe` 先注册占位 no-op，D2 延后）
- 生命周期：`load_all()`（启动加载）/ `unload_all()`（停止清理）
- 迁移策略：新子系统接入 = 注册 handler，不再改 event_rules.yaml + 重启；
  旧 3 条 rules 保留为兼容回退（consumer 仅在 event_type 无注册 handler 时走 rules）

内置 handler（与 Phase 1 3 条 rules 语义完全等价）：
  1. audit.task_complete  —— 等价 rule-task-complete（调 丰碑 core/audit.py --event {trace_id}）
  2. alert.anomaly        —— 等价 rule-anomaly-escalate（写 丰碑 data/alerts.log）
  3. archive.audit_result —— 等价 rule-audit-archive（调 丰碑 core/archive.py --event {trace_id}）
  4. xuanjian.pipe        —— 玄鉴预留占位（D2 延后，no-op 仅记录）
"""

import json
import os
import re
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    from .log_writer import LogWriter
except ImportError:
    from log_writer import LogWriter

__all__ = ["Handler", "HandlerRegistry", "build_default_registry",
           "AuditTaskCompleteHandler", "AlertAnomalyHandler",
           "ArchiveAuditResultHandler", "XuanjianPipePlaceholder",
           "InterfacesStoreHandler", "InterfacesRecallHandler",
           "LmsFeedHandler",
           "GlueHttpMixin",
           "quick_test"]

_BJT = timezone(timedelta(hours=8))

# 默认死信队列（与 consumer 共用同一文件，保证同源可查）
_DEFAULT_DEAD_LETTER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", ".dead_letter_queue.jsonl"
)

# 丰碑桥接目标（与 deploy/event_rules.yaml 中 3 条规则完全一致）
_FENG_BEI_CODE = "/vol2/1000/AI专用/丰碑网络/code"
_AUDIT_PY = os.path.join(_FENG_BEI_CODE, "core", "audit.py")
_ARCHIVE_PY = os.path.join(_FENG_BEI_CODE, "core", "archive.py")
_ALERT_LOG = "/vol2/1000/AI专用/丰碑网络/data/alerts.log"

# 胶水层 HTTP 服务（Phase 3 D4：handler 宿主，shell 降为一种 handler）
_GLUE_SERVER_URL = os.environ.get("GLUE_SERVER_URL", "http://127.0.0.1:19000")
_OPERATION_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "operation_log.jsonl",
)

# LMS 塑形喂入目标（Phase 4 D0：总线 → LMS /feed，只喂不指挥）
_LMS_URL = os.environ.get("LMS_URL", "http://127.0.0.1:8190")
_LMS_FEED_TIMEOUT = float(os.environ.get("LMS_FEED_TIMEOUT", "10"))

# P1-4（T1.7）：总线系统事件停喂 LMS。
# 证据：bus 脑 1212+ 轮几乎全是 "任务 bus_heartbeat 完成 (exit=0)"（每 5 分钟
# 一条 task_complete），占满快照槽位并参与做梦写 latest.pt（见 P1-4 问题表）。
# 处理：
#   1) 总开关 LMS_FEED_ENABLED=0 → 完全停喂（运维逃生门，不改代码即可熔断；
#      在 handle() 时实时读取，无需重启消费者即可生效）；
#   2) 噪声过滤：事件生产者/类型/文本命中 heartbeat/心跳 模式 → 静默跳过，
#      不喂入、不记操作日志（避免 operation_log 也被刷屏）。
_LMS_FEED_NOISE_RE = re.compile(
    r"heartbeat|心跳|HEARTBEAT_OK|bus_heartbeat", re.IGNORECASE)


def _lms_feed_enabled() -> bool:
    """LMS 喂入总开关（实时读 env，可热切换，默认开启）。"""
    return os.environ.get(
        "LMS_FEED_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _is_lms_feed_noise(event: dict, text: str) -> bool:
    """判断事件是否为系统噪声（不应喂入 LMS）。

    按生产者/事件类型/文本三重匹配（任一命中即视为噪声）：
      - producer 含 heartbeat（如 task_scheduler/bus_heartbeat）
      - event_type 含 heartbeat（如 sandglass.heartbeat）
      - 文本含 心跳/HEARTBEAT_OK/bus_heartbeat（防 payload 直塞心跳内容）
    """
    producer = str(event.get("producer") or "")
    event_type = str(event.get("event_type") or "")
    if _LMS_FEED_NOISE_RE.search(producer) or _LMS_FEED_NOISE_RE.search(event_type):
        return True
    return bool(_LMS_FEED_NOISE_RE.search(text))


class GlueHttpMixin:
    """胶水层 HTTP 调用工具（urllib 标准库，零额外依赖）。

    Phase 3 D4：总线 handler 通过 HTTP 调 glue_server（127.0.0.1:19000），
    不做 shell 调用 —— 胶水层作为 hexagon handler 宿主，shell 降级为一种 handler。
    """

    @staticmethod
    def post(path: str, body: dict, timeout: float = 30.0):
        import urllib.request
        req = urllib.request.Request(
            _GLUE_SERVER_URL + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def health(timeout: float = 5.0):
        """GET /health；不可达返回 None（fail-open，不抛）"""
        import urllib.request
        try:
            with urllib.request.urlopen(_GLUE_SERVER_URL + "/health", timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None


class Handler(ABC):
    """
    handler 抽象基类。

    属性:
        name:        签名 `<system>.<domain>.<action>`（如 audit.task_complete）
        event_types: 订阅的 event_type 列表（一个 handler 可订阅多个事件类型）
        results:     result 过滤（None=全部；如 ["OK"] 只处理 OK 事件）
        rate_limit:  秒，同 handler 最小分派间隔（0=不限）
        description: 描述
    方法:
        load()/unload(): 生命周期钩子（默认空实现）
        handle(event):   处理事件，返回 True=成功；抛异常视为失败（异常隔离）
    """

    name: str = ""
    event_types: list = []
    results: Optional[list] = None
    rate_limit: float = 0.0
    description: str = ""

    def load(self):
        """启动时加载（默认空实现，子类可按需覆写）"""
        pass

    def unload(self):
        """停止时清理（默认空实现，子类可按需覆写）"""
        pass

    @abstractmethod
    def handle(self, event: dict) -> bool:
        """
        处理事件。

        返回:
            True 表示处理成功；False 表示处理失败（记死信）；
            抛异常也视为失败（记死信），且不影响同一事件类型的其他 handler。
        """
        raise NotImplementedError


class AuditTaskCompleteHandler(Handler):
    """等价 rule-task-complete：调 audit.py --event {trace_id}（安全数组传参，shell=False）"""

    name = "audit.task_complete"
    event_types = ["task_complete"]
    results = ["OK"]
    rate_limit = 1800.0  # Phase6 低频化：30 分钟一次（原 1.0s，丰碑 audit_bridge 54条/天空转）
    description = "任务完成后桥接下游机制（审计任务完成）→ 丰碑 audit.py（Phase6 起 30min 限流）"

    def handle(self, event: dict) -> bool:
        trace_id = str(event.get("trace_id", "unknown"))
        result = subprocess.run(
            [sys.executable, _AUDIT_PY, "--event", trace_id],
            timeout=25, capture_output=True, text=True, shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"audit.py failed: {result.stderr[:200]}")
        return True


class AlertAnomalyHandler(Handler):
    """等价 rule-anomaly-escalate：异常事件写 丰碑 data/alerts.log（JSON 行）"""

    name = "alert.anomaly"
    event_types = ["anomaly"]
    results = ["FAIL"]
    rate_limit = 5.0  # 与规则一致
    description = "检测到异常时升级告警 → 丰碑 alerts.log"

    def handle(self, event: dict) -> bool:
        entry = {
            "t": datetime.now(_BJT).isoformat(),
            "level": "ALERT",
            "event_type": "anomaly",
            "result": "FAIL",
            "producer": str(event.get("producer", "unknown")),
            "detail": str(event.get("detail", "")),
            "trace_id": str(event.get("trace_id", "unknown")),
        }
        os.makedirs(os.path.dirname(_ALERT_LOG), exist_ok=True)
        with open(_ALERT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True


class ArchiveAuditResultHandler(Handler):
    """等价 rule-audit-archive：审计完成后归档结果 → 丰碑 archive.py"""

    name = "archive.audit_result"
    event_types = ["audit_result"]
    results = ["OK"]
    rate_limit = 2.0  # 与规则一致
    description = "审计完成后归档结果 → 丰碑 archive.py"

    def handle(self, event: dict) -> bool:
        trace_id = str(event.get("trace_id", "unknown"))
        result = subprocess.run(
            [sys.executable, _ARCHIVE_PY, "--event", trace_id],
            timeout=25, capture_output=True, text=True, shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"archive.py failed: {result.stderr[:200]}")
        return True


class XuanjianPipePlaceholder(Handler):
    """
    玄鉴预留占位 handler（D2 已延后：玄鉴评分是关键词启发式、无校准、无消费方）。
    仅注册占位 + 记录收到事件，不执行任何动作（no-op）。
    等 D2 重启时替换为真实玄鉴接入 handler。
    """

    name = "xuanjian.pipe"
    event_types = ["xuanjian.pipe"]
    results = None  # 任意 result 都接收（仅记录）
    rate_limit = 0.0
    description = "玄鉴评分结果占位（D2 延后，no-op 仅记录，注册表预留）"

    def handle(self, event: dict) -> bool:
        print(f"[handlers] 📝 占位 handler {self.name} 收到事件: "
              f"producer={event.get('producer')} result={event.get('result')} "
              f"(D2 延后，不处理)")
        return True


class InterfacesStoreHandler(Handler, GlueHttpMixin):
    """胶水层记忆写入：event_type=interfaces.store → POST glue_server /store。

    - payload.text / payload.source 作为写入内容（缺 text 视为非法事件 → 死信）
    - 调 glue 失败 raise → registry 异常隔离记死信，不拖垮消费循环（fail-open）
    - 成功后写 operation_log 详情（store 结果含 id/vector/entropy/surprise）
    """

    name = "interfaces.store"
    event_types = ["interfaces.store"]
    results = None  # 命令通道：任意 result 都接收（生产者想写记忆就写）
    rate_limit = 0.0
    description = "胶水层记忆写入：总线事件 → glue_server /store（沙漏+LMS+向量聚合写入）"

    def __init__(self):
        self._op_writer = LogWriter(_OPERATION_LOG)

    def load(self):
        h = self.health()
        if h is None:
            print(f"[handlers] ⚠️ {self.name} load(): glue_server({_GLUE_SERVER_URL}) 不可达"
                  f"（handler 已注册，将 fail-open：调 glue 失败记死信不崩总线）")
        else:
            print(f"[handlers] ✅ {self.name} load(): glue_server 健康 {h.get('status')}")

    def handle(self, event: dict) -> bool:
        payload = event.get("payload") or {}
        text = str(payload.get("text") or event.get("detail") or "").strip()
        source = str(payload.get("source") or "bus").strip()
        if not text:
            raise ValueError(f"interfaces.store: payload.text 必填 (trace_id={event.get('trace_id')})")
        try:
            result = self.post("/store", {"text": text, "source": source})
        except Exception as e:
            raise RuntimeError(f"glue /store 失败: {type(e).__name__}: {e}") from e
        if not result.get("ok"):
            raise RuntimeError(f"glue /store 返回失败: {result}")
        self._op_writer.write({
            "event_type": "consumer_action",
            "producer": "interfaces.store",
            "result": "OK",
            "detail": (f"胶水层 store 成功: id={result.get('id')} "
                       f"vector={result.get('vector')} entropy={result.get('entropy')} "
                       f"surprise={result.get('surprise')}"),
            "trace_id": event.get("trace_id"),
            "event_id": event.get("event_id"),
        })
        return True


class InterfacesRecallHandler(Handler, GlueHttpMixin):
    """胶水层记忆召回：event_type=interfaces.recall → POST glue_server /recall。

    - payload.query / payload.k 作为召回参数（缺 query 视为非法事件 → 死信）
    - 结果写回 operation_log（count + 各条 origin/scores/text 摘要），供审计回读
    - 调 glue 失败 raise → registry 异常隔离记死信，不拖垮消费循环（fail-open）
    """

    name = "interfaces.recall"
    event_types = ["interfaces.recall"]
    results = None  # 命令通道：任意 result 都接收
    rate_limit = 0.0
    description = "胶水层记忆召回：总线事件 → glue_server /recall（沙漏+LMS+向量加权融合），结果写回 operation_log"

    def __init__(self):
        self._op_writer = LogWriter(_OPERATION_LOG)

    def load(self):
        h = self.health()
        if h is None:
            print(f"[handlers] ⚠️ {self.name} load(): glue_server({_GLUE_SERVER_URL}) 不可达"
                  f"（handler 已注册，将 fail-open：调 glue 失败记死信不崩总线）")
        else:
            print(f"[handlers] ✅ {self.name} load(): glue_server 健康 {h.get('status')}")

    def handle(self, event: dict) -> bool:
        payload = event.get("payload") or {}
        query = str(payload.get("query") or "").strip()
        try:
            k = int(payload.get("k", 3))
        except (TypeError, ValueError):
            k = 3
        if not query:
            raise ValueError(f"interfaces.recall: payload.query 必填 (trace_id={event.get('trace_id')})")
        try:
            result = self.post("/recall", {"query": query, "k": k}, timeout=30.0)
        except Exception as e:
            raise RuntimeError(f"glue /recall 失败: {type(e).__name__}: {e}") from e
        items = result.get("results", [])
        summary = [{
            "origin": it.get("origin"),
            "system": it.get("system"),
            "scores": it.get("scores"),
            "text": (it.get("text") or "")[:60],
        } for it in items[:k]]
        self._op_writer.write({
            "event_type": "consumer_action",
            "producer": "interfaces.recall",
            "result": "OK",
            "detail": (f"胶水层 recall 成功: query='{query}' count={result.get('count')} "
                       f"top={json.dumps(summary, ensure_ascii=False)}"),
            "trace_id": event.get("trace_id"),
            "event_id": event.get("event_id"),
        })
        return True


class LmsFeedHandler(Handler):
    """LMS 塑形喂入（Phase 4 D0 方向 1：只喂不指挥）。

    订阅 interfaces.store（记忆写入）/ task_complete（任务完成）/ milestone（里程碑）
    / doubt.episode（怀疑闭环，Phase 6 新增：自我怀疑喂潜意识塑形）
    事件 → 提取文本摘要 → POST LMS /feed（LMS_URL 可覆盖，urllib，shell=False）。
    LMS 内部如何塑形（权重/吸引子演化）是它自己的事，总线只负责"把事件送到嘴边"。

    - 不订阅心跳（噪音，如 sandglass.heartbeat）
    - 失败 fail-open：调 LMS 失败 raise → registry 异常隔离记死信，不拖垮总线
    - load() 探活：LMS 不可达仅警告（handler 已注册，将 fail-open）
    - 限流：rate_limit=1.0s（≥1s 间隔，防总线风暴）
    """

    name = "lms.feed"
    event_types = ["interfaces.store", "task_complete", "milestone", "doubt.episode"]
    results = None  # 任意 result 都接收（喂塑形是软参考，失败可忽略）
    rate_limit = 1.0  # ≥1s 间隔
    description = "LMS 塑形喂入：总线事件文本摘要 → LMS /feed（只喂不指挥，软参考）"

    def __init__(self):
        self._op_writer = LogWriter(_OPERATION_LOG)

    def load(self):
        """启动探活：LMS /health 不可达仅警告，不阻断注册（fail-open）。"""
        import urllib.request
        try:
            with urllib.request.urlopen(
                    _LMS_URL + "/health", timeout=5.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            print(f"[handlers] ✅ {self.name} load(): LMS 健康 {body.get('status')}")
        except Exception as e:
            print(f"[handlers] ⚠️ {self.name} load(): LMS({_LMS_URL}) 不可达"
                  f"（{type(e).__name__}: {e}；handler 已注册，将 fail-open："
                  f"调 LMS 失败记死信不崩总线）")

    @staticmethod
    def _extract_text(event: dict) -> str:
        """从事件提取可喂入的文本摘要（优先 payload.text → payload.detail → detail）。"""
        payload = event.get("payload") or {}
        text = str(payload.get("text") or "").strip()
        if not text:
            text = str(payload.get("detail") or "").strip()
        if not text:
            text = str(event.get("detail") or "").strip()
        if not text:
            # 兜底：事件类型+生产者，保证 feed 端 text 非空
            text = f"{event.get('event_type')}/{event.get('producer')}"
        return text

    def handle(self, event: dict) -> bool:
        # P1-4：总开关熔断（LMS_FEED_ENABLED=0 → 完全停喂，不喂不记；热切换）
        if not _lms_feed_enabled():
            return True

        text = self._extract_text(event)

        # P1-4：噪声过滤（heartbeat/心跳类系统事件不进 LMS，bus 脑不再长垃圾）
        if _is_lms_feed_noise(event, text):
            return True

        # 喂塑形是软参考：截断超长文本（LMS 侧也有总量限流）
        text = text[:2000]
        trace_id = str(event.get("trace_id", "unknown"))
        try:
            result = self._post_feed({
                "text": text,
                "session_id": "bus",
                "source": "event_bus",
            })
        except Exception as e:
            raise RuntimeError(
                f"LMS /feed 失败: {type(e).__name__}: {e}"
                f" (trace_id={trace_id})") from e
        if not result or result.get("status") != "ok":
            raise RuntimeError(f"LMS /feed 返回异常: {result}")
        self._op_writer.write({
            "event_type": "consumer_action",
            "producer": "lms.feed",
            "result": "OK",
            "detail": (f"LMS 塑形喂入成功: turn_count={result.get('turn_count')} "
                       f"entropy={result.get('entropy')} "
                       f"surprise={result.get('surprise')} "
                       f"text_len={len(text)}"),
            "trace_id": trace_id,
            "event_id": event.get("event_id"),
        })
        return True

    @staticmethod
    def _post_feed(body: dict):
        """urllib POST LMS /feed（shell=False，零额外依赖）。"""
        import urllib.request
        req = urllib.request.Request(
            _LMS_URL + "/feed",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_LMS_FEED_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))


class HandlerRegistry:
    """
    handler 注册表：按 event_type 注册/执行 handler 链。

    - 一个 event_type 可注册多个 handler，按注册顺序执行
    - 异常隔离：单个 handler 抛异常/返回 False → 记死信，继续下一个 handler
    - 限流：每个 handler 独立 rate_limit（与旧 rules 的 rate_limit 语义对齐）
    - 生命周期：load_all() 启动时调用；unload_all() 停止时调用
    """

    def __init__(self, dead_letter_file: str = _DEFAULT_DEAD_LETTER):
        self._handlers: dict = {}          # event_type -> [Handler, ...]
        self._by_name: dict = {}           # name -> Handler
        self._order: list = []             # 注册顺序（名字列表，用于统一顺序）
        self._dead_writer = LogWriter(dead_letter_file)
        self._rate_limits: dict = {}       # name -> last dispatch time
        self._loaded = False

    # ── 注册/注销 ──────────────────────────────────────────────────────
    def register(self, handler: Handler) -> bool:
        """注册一个 handler。重复 name 拒绝注册。"""
        if not handler.name:
            print("[handlers] ⚠️ 拒绝注册：handler 缺少 name")
            return False
        if handler.name in self._by_name:
            print(f"[handlers] ⚠️ 拒绝注册：name 已存在 {handler.name}")
            return False
        for et in handler.event_types:
            self._handlers.setdefault(et, []).append(handler)
        self._by_name[handler.name] = handler
        self._order.append(handler.name)
        print(f"[handlers] ✅ 注册 handler: {handler.name} → "
              f"event_types={handler.event_types} results={handler.results}")
        return True

    def unregister(self, name: str) -> bool:
        """注销一个 handler（含从各 event_type 链移除）。"""
        handler = self._by_name.pop(name, None)
        if handler is None:
            return False
        for et in handler.event_types:
            chain = self._handlers.get(et, [])
            if handler in chain:
                chain.remove(handler)
            if not chain:
                self._handlers.pop(et, None)
        if name in self._order:
            self._order.remove(name)
        print(f"[handlers] 🗑️ 注销 handler: {name}")
        return True

    # ── 查询 ───────────────────────────────────────────────────────────
    def get_handlers(self, event_type: str) -> list:
        """返回该 event_type 注册的 handler 列表（按注册顺序）。"""
        return list(self._handlers.get(event_type, []))

    def has_handlers(self, event_type: str) -> bool:
        """该 event_type 是否注册了 handler（consumer 据此决定走 handler 链还是旧 rules）。"""
        return bool(self._handlers.get(event_type))

    def list_handlers(self) -> list:
        """返回全部 handler 元信息（拓扑工具用）。"""
        return [
            {
                "name": h.name,
                "event_types": list(h.event_types),
                "results": h.results,
                "rate_limit": h.rate_limit,
                "description": h.description,
            }
            for h in (self._by_name[n] for n in self._order)
        ]

    # ── 生命周期 ───────────────────────────────────────────────────────
    def load_all(self):
        """启动时加载：逐个调用 handler.load()；单个失败不阻断其他。"""
        for name in self._order:
            h = self._by_name[name]
            try:
                h.load()
            except Exception as e:
                print(f"[handlers] ⚠️ handler {name} load() 异常: {e}")
        self._loaded = True
        print(f"[handlers] 🔄 生命周期 load_all 完成（{len(self._order)} 个 handler）")

    def unload_all(self):
        """停止时清理：逐个调用 handler.unload()；单个失败不阻断其他。"""
        for name in self._order:
            h = self._by_name[name]
            try:
                h.unload()
            except Exception as e:
                print(f"[handlers] ⚠️ handler {name} unload() 异常: {e}")
        self._loaded = False
        print(f"[handlers] 🔄 生命周期 unload_all 完成")

    # ── 执行（异常隔离核心）────────────────────────────────────────────
    def dispatch(self, event: dict) -> dict:
        """
        按注册顺序执行该 event_type 的 handler 链。

        异常隔离：单个 handler 抛异常 → 记死信（含 handler 名与异常信息），
        继续执行下一个 handler，绝不拖垮消费循环。

        返回:
            {"handled": n, "failed": n, "skipped": n}
        """
        event_type = event.get("event_type", "")
        stats = {"handled": 0, "failed": 0, "skipped": 0}
        result = event.get("result")

        for handler in self.get_handlers(event_type):
            # result 过滤（handler.results 为空/None = 全部接收）
            if handler.results is not None and result not in handler.results:
                stats["skipped"] += 1
                continue

            # 限流（与旧 rules rate_limit 语义对齐）
            now = time.time()
            last = self._rate_limits.get(handler.name, 0.0)
            if handler.rate_limit > 0 and now - last < handler.rate_limit:
                stats["skipped"] += 1
                continue

            try:
                ok = handler.handle(event)
                self._rate_limits[handler.name] = now
                if ok:
                    stats["handled"] += 1
                    print(f"[handlers] ✅ {handler.name} 处理成功 "
                          f"({event_type}/{result})")
                else:
                    stats["failed"] += 1
                    self._write_dead_letter(event, handler,
                                            f"handler 返回 False")
            except Exception as e:
                stats["failed"] += 1
                self._write_dead_letter(event, handler,
                                        f"异常: {type(e).__name__}: {e}")
                print(f"[handlers] 💀 {handler.name} 异常隔离: {type(e).__name__}: {e}"
                      f" → 已记死信，继续下一个 handler")

        return stats

    def _write_dead_letter(self, event: dict, handler: Handler, reason: str):
        """handler 失败 → 死信队列（带 handler 名，可追溯）"""
        record = {
            "t": datetime.now(_BJT).isoformat(),
            "event_type": "consumer_action",
            "producer": "handler_registry",
            "result": "FAIL",
            "detail": f"死信: handler={handler.name} {reason}",
            "trace_id": event.get("trace_id"),
            "original_event": {
                "event_type": event.get("event_type"),
                "producer": event.get("producer"),
                "result": event.get("result"),
                "trace_id": event.get("trace_id"),
                "event_id": event.get("event_id"),
            },
        }
        try:
            self._dead_writer.write(record)
        except Exception as e:
            print(f"[handlers] ⚠️ 死信写入失败: {e}")
        print(f"[handlers] 💀 写入死信: handler={handler.name} {reason}")


# ── 默认注册表 ─────────────────────────────────────────────────────────
def build_default_registry(dead_letter_file: str = _DEFAULT_DEAD_LETTER) -> HandlerRegistry:
    """
    构建默认注册表：内置 3 个业务 handler（与旧 rules 语义等价）+ 玄鉴占位
    + 胶水层 2 个 handler（Phase 3 D4：interfaces.store/recall，HTTP 调 glue_server）
    + LMS 塑形喂入 1 个（Phase 4 D0：lms.feed，订阅 interfaces.store/task_complete/milestone）。
    新子系统接入 = 在这里（或调用方）追加注册自己的 handler。
    """
    registry = HandlerRegistry(dead_letter_file=dead_letter_file)
    registry.register(AuditTaskCompleteHandler())
    registry.register(AlertAnomalyHandler())
    registry.register(ArchiveAuditResultHandler())
    registry.register(XuanjianPipePlaceholder())
    registry.register(InterfacesStoreHandler())
    registry.register(InterfacesRecallHandler())
    registry.register(LmsFeedHandler())
    return registry


# ── 单元测试 ───────────────────────────────────────────────────────────
def quick_test():
    """handlers.py 快速自测：注册 / 执行 / 异常隔离 / 生命周期 / result 过滤 / 限流"""
    import tempfile
    import time as _time

    print("=" * 50)
    print("🧪 handlers.py 快速自测")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmpdir:
        dead_letter = os.path.join(tmpdir, ".dead_letter_queue.jsonl")
        registry = HandlerRegistry(dead_letter_file=dead_letter)

        # ── 1. 注册 ──
        class GoodHandler(Handler):
            name = "test.good"
            event_types = ["test_event"]
            results = ["OK"]
            description = "测试正常 handler"

            def __init__(self):
                self.calls = 0

            def handle(self, event):
                self.calls += 1
                return True

        class BadHandler(Handler):
            """抛异常的 handler（异常隔离测试）"""
            name = "test.bad"
            event_types = ["test_event"]
            results = ["OK"]
            description = "测试崩溃 handler"

            def handle(self, event):
                raise RuntimeError("boom")

        class FalseHandler(Handler):
            """返回 False 的 handler"""
            name = "test.false"
            event_types = ["test_event"]
            results = ["OK"]
            description = "测试返回 False"

            def handle(self, event):
                return False

        good, bad, false = GoodHandler(), BadHandler(), FalseHandler()
        assert registry.register(good), "注册 good 应成功"
        assert registry.register(bad), "注册 bad 应成功"
        assert registry.register(false), "注册 false 应成功"
        assert not registry.register(good), "重复 name 应拒绝"
        assert len(registry.get_handlers("test_event")) == 3, "同一 event_type 应可注册 3 个 handler"
        print("✅ 注册/重复拒绝正常")

        # ── 2. 执行链 + 异常隔离（bad 抛异常，good/false 仍执行）──
        registry.load_all()
        stats = registry.dispatch({
            "t": "2026-08-04T17:00:00+08:00",
            "schema_version": "1.1",
            "event_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "event_type": "test_event",
            "producer": "test",
            "result": "OK",
            "trace_id": "handlers-test-001",
        })
        assert stats == {"handled": 1, "failed": 2, "skipped": 0}, \
            f"bad 异常 + false 返回 False 应 failed=2，good 应 handled=1，实际 {stats}"
        assert good.calls == 1, "good 应执行 1 次"
        print("✅ 异常隔离：bad 抛异常未拖垮链，good 仍执行，false 记失败")

        # ── 3. 死信记录（bad + false 两条）──
        dl = []
        if os.path.exists(dead_letter):
            with open(dead_letter, "r", encoding="utf-8") as f:
                dl = [json.loads(l) for l in f if l.strip()]
        assert len(dl) == 2, f"死信应有 2 条（bad 异常 + false），实际 {len(dl)}"
        names = {r["detail"].split("handler=")[1].split(" ")[0] for r in dl}
        assert names == {"test.bad", "test.false"}, f"死信应含 bad/false，实际 {names}"
        assert any("boom" in r["detail"] for r in dl), "死信应含异常信息 boom"
        print("✅ 死信队列：失败 handler 落死信（含异常信息）")

        # ── 4. result 过滤（results=["OK"] 的 handler 不处理 FAIL 事件）──
        stats2 = registry.dispatch({
            "event_type": "test_event", "producer": "test",
            "result": "FAIL", "trace_id": "t2",
        })
        assert stats2["skipped"] == 3 and stats2["handled"] == 0, \
            f"FAIL 事件应全部 skip，实际 {stats2}"
        assert good.calls == 1, "FAIL 事件不应触发 good"
        print("✅ result 过滤：FAIL 事件被跳过，不误触发")

        # ── 5. 限流（rate_limit>0 时短时间内重复分派被跳过）──
        class RateHandler(Handler):
            name = "test.rate"
            event_types = ["rate_event"]
            rate_limit = 60.0

            def __init__(self):
                self.calls = 0

            def handle(self, event):
                self.calls += 1
                return True

        rate = RateHandler()
        registry.register(rate)
        registry.dispatch({"event_type": "rate_event", "producer": "t", "result": "OK"})
        registry.dispatch({"event_type": "rate_event", "producer": "t", "result": "OK"})
        assert rate.calls == 1, f"60s 限流内第二次应跳过，实际 {rate.calls}"
        print("✅ 限流：rate_limit 内重复事件被跳过")

        # ── 6. 注销 + 生命周期 ──
        assert registry.unregister("test.good"), "注销应成功"
        assert registry.get_handlers("test_event") == [bad, false], "注销后链应更新"
        assert not registry.unregister("test.good"), "重复注销应返回 False"
        registry.unload_all()
        print("✅ 注销/生命周期 load/unload 正常")

    print("=" * 50)
    print("✅ handlers.py 快速自测通过")
    print("=" * 50)


if __name__ == "__main__":
    quick_test()
