"""
事件总线系统 v0.7.0（Phase 2 / D6：handler 注册表 + 生命周期 + 异常隔离）

定时调度器 + 事件消费者 + 写入锁中间件 + 统一 handler 机制 + 事件拓扑工具
为 Agent OS 统一总线提供事件驱动基础设施。

导出:
    LogWriter       — 线程/进程安全的 JSONL 写入器
    EventConsumer   — 事件消费者（3s 轮询；handler 链优先，旧 rules 兼容回退）
    TaskScheduler   — 定时调度器（30s tick；从 tasks.yaml 加载真实任务）
    Handler         — handler 抽象基类（<system>.<domain>.<action>）
    HandlerRegistry — handler 注册表（注册/执行/异常隔离/生命周期）
    build_default_registry — 默认注册表（3 内置 handler + 玄鉴占位）
    TopologyAnalyzer — 事件拓扑工具（谁产生 → 谁消费 + 环状订阅检测）
"""

from .log_writer import LogWriter
from .event_consumer import EventConsumer
from .task_scheduler import TaskScheduler
from .handlers import Handler, HandlerRegistry, build_default_registry
from .topology import TopologyAnalyzer

__all__ = ["LogWriter", "EventConsumer", "TaskScheduler",
           "Handler", "HandlerRegistry", "build_default_registry",
           "TopologyAnalyzer"]
__version__ = "0.7.0"
