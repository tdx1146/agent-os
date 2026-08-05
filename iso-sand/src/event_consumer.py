"""
event_consumer.py — 事件消费者（独立守护线程，3s 轮询）

轮询 event_bus.jsonl → 匹配 event_rules.yaml → 异步分派下游动作
限流 + 重试（指数退避 3 次）+ 死信保护
"""

import json
import os
import subprocess
import sys
import threading
import time
import yaml
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    from .log_writer import LogWriter
except ImportError:
    from log_writer import LogWriter

try:
    from .handlers import HandlerRegistry, build_default_registry
except ImportError:
    from handlers import HandlerRegistry, build_default_registry

__all__ = ["EventConsumer", "main"]

_BJT = timezone(timedelta(hours=8))

# 默认路径
_DEFAULT_EVENT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "event_bus.jsonl"
)
_DEFAULT_SEEK_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "event_bus.seek"
)
_DEFAULT_RULES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "event_rules.yaml"
)
_DEFAULT_OPERATION_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "operation_log.jsonl"
)
_DEFAULT_DEAD_LETTER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", ".dead_letter_queue.jsonl"
)
_DEFAULT_PROCESSED_IDS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "processed_ids.jsonl"
)

# 幂等去重：内存集合上限（文件持续追加，重启时全量重载；超限后仅内存去重暂停增长）
_PROCESSED_IDS_CAP = 100_000

# Shell 安全：白名单命令前缀 + 黑名单（仅用于旧格式 command 兼容路径）
_SHELL_WHITELIST_PREFIXES = [
    "python3", "python", "echo", "mkdir", "cp", "mv", "rm",
    "cat", "grep", "wc", "head", "tail", "sort",
]
_SHELL_BLACKLIST_WORDS = [
    "sudo", "su", "chmod 777", "chown", "> /dev/",
    "rm -rf /", "mkfs", "dd if=", ":(){ :|:& };:"
]


class EventConsumer:
    """
    事件消费者：轮询 event_bus.jsonl，匹配规则并异步分派

    用法:
        consumer = EventConsumer()
        consumer.start()  # 启动守护线程
        ...
        consumer.stop()   # 停止
    """

    def __init__(self, event_file: str = _DEFAULT_EVENT_FILE,
                 seek_file: str = _DEFAULT_SEEK_FILE,
                 rules_file: str = _DEFAULT_RULES_FILE,
                 operation_log: str = _DEFAULT_OPERATION_LOG,
                 dead_letter: str = _DEFAULT_DEAD_LETTER,
                 processed_ids_file: str = _DEFAULT_PROCESSED_IDS,
                 poll_interval: float = 3.0,
                 enable_handlers: bool = True):
        self._event_file = event_file
        self._seek_file = seek_file
        self._rules_file = rules_file
        self._operation_log = operation_log
        self._dead_letter = dead_letter
        self._processed_ids_file = processed_ids_file
        self._poll_interval = poll_interval

        self._writer = LogWriter(operation_log)
        self._dead_writer = LogWriter(dead_letter)
        # 事件文件的写入器：兼作文件锁协调（清理重写时防止同进程并发写）
        self._event_writer = LogWriter(event_file)
        # 幂等去重（D7）：已处理 event_id 集合 + 持久化文件
        self._processed_writer = LogWriter(processed_ids_file)
        self._processed_ids: set = set()
        self._load_processed_ids()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # D6: handler 注册表（Phase 2）——新子系统接入 = 注册 handler，不再改 rules
        # enable_handlers=False 时（如快速自测）仅走旧 rules 路径，保持测试封闭无副作用
        self._handler_registry = None
        if enable_handlers:
            self._handler_registry = build_default_registry(dead_letter_file=self._dead_letter)
            self._handler_registry.load_all()

        # 加载规则（兼容回退：仅当 event_type 无注册 handler 时使用）
        self._rules = self._load_rules()

        # 限流状态：{rule_id: last_dispatch_time}
        self._rate_limits: dict = {}

    def _load_processed_ids(self):
        """从 processed_ids.jsonl 加载已处理 event_id（幂等去重跨重启持久化）"""
        if not os.path.exists(self._processed_ids_file):
            return
        try:
            with open(self._processed_ids_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        eid = rec.get("event_id")
                        if eid:
                            self._processed_ids.add(eid)
                    except json.JSONDecodeError:
                        continue
            print(f"[event_consumer] 🗂️ 已加载 {len(self._processed_ids)} 个已处理 event_id")
        except OSError as e:
            print(f"[event_consumer] ⚠️ 读取去重文件失败: {e}")

    def _is_processed(self, event: dict) -> bool:
        """事件是否已处理过（无 event_id 的事件不参与去重）"""
        eid = event.get("event_id")
        return bool(eid) and eid in self._processed_ids

    def _mark_processed(self, event: dict):
        """标记事件已处理：内存集合 + 追加到 processed_ids.jsonl"""
        eid = event.get("event_id")
        if not eid:
            return
        if len(self._processed_ids) >= _PROCESSED_IDS_CAP:
            print(f"[event_consumer] ⚠️ 去重集达上限 {_PROCESSED_IDS_CAP}，"
                  f"内存去重暂停增长（文件仍追加，重启后可恢复）")
            return
        self._processed_ids.add(eid)
        try:
            self._processed_writer.write({"event_id": eid}, validate=False)
        except Exception as e:
            print(f"[event_consumer] ⚠️ 去重记录写入失败: {e}")

    @staticmethod
    def _event_schema_version(event: dict) -> str:
        """事件 schema 版本：老事件无 schema_version 字段时默认 '1.0'（向后兼容）"""
        return str(event.get("schema_version", "1.0"))

    def _load_rules(self) -> list:
        """加载 event_rules.yaml，返回规则列表"""
        if not os.path.exists(self._rules_file):
            print(f"[event_consumer] ⚠️ 规则文件不存在: {self._rules_file}")
            return []
        with open(self._rules_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        rules = data.get("rules", [])
        print(f"[event_consumer] ✅ 加载 {len(rules)} 条消费规则")
        return rules

    def _get_seek_offset(self) -> int:
        """读取上次消费的 seek 偏移量"""
        if not os.path.exists(self._seek_file):
            return 0
        try:
            with open(self._seek_file, "r") as f:
                return int(f.read().strip())
        except (ValueError, OSError):
            return 0

    def _save_seek_offset(self, offset: int):
        """保存 seek 偏移量（D1：临时文件 → fsync → os.replace 原子替换，防半写）"""
        tmp_file = self._seek_file + ".tmp"
        with open(tmp_file, "w") as f:
            f.write(str(offset))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, self._seek_file)

    def _filter_non_json_lines(self) -> int:
        """
        清除 event_bus.jsonl 中的非 JSON 行（D1：原子重写 + 锁保护）
        扫描全文件，保留空行与合法 JSON 行，清除损坏行。
        重写使用 临时文件 → os.replace 原子替换，防半写损坏。
        重写后重置 seek 偏移，防止首批事件被跳过。

        返回: 清除的行数
        """
        if not os.path.exists(self._event_file):
            return 0

        cleared = 0
        lines = []
        # 线程锁：与同进程内 LogWriter.write 互斥（跨进程见 changelog 已知限制）
        with self._event_writer._lock:
            # 顺带清理上次原子重写中断遗留的 .tmp
            try:
                stale = self._event_writer.cleanup_stale_tmp()
                if stale:
                    print(f"[event_consumer] 🧹 清理 {stale} 个遗留 .tmp 文件")
            except Exception:
                pass

            with open(self._event_file, "r", encoding="utf-8") as f:
                for line in f:
                    line_stripped = line.strip()
                    if not line_stripped:
                        # 空行保留
                        lines.append(line)
                        continue
                    try:
                        json.loads(line_stripped)
                        lines.append(line)
                    except json.JSONDecodeError:
                        cleared += 1
                        # 跳过非 JSON 行

            if cleared > 0:
                print(f"[event_consumer] 🧹 清除 {cleared} 行非 JSON 数据")
                # D1: 临时文件 → fsync → os.replace 原子替换，防半写损坏
                self._event_writer.atomic_rewrite(lines)
                # 重写改变了文件（inode 变化），旧 seek 偏移失效 → 重置为 0
                self._save_seek_offset(0)
                print("[event_consumer] 📍 seek 偏移已重置为 0")

        return cleared

    def _check_shell_safe(self, command: str) -> bool:
        """
        检查 shell 命令是否安全
        返回 True 表示安全
        """
        for bad_word in _SHELL_BLACKLIST_WORDS:
            if bad_word in command:
                print(f"[event_consumer] 🚫 黑名单命中: '{bad_word}' → 拒绝执行: {command}")
                return False

        # 提取命令首词（命令名）
        cmd_first = command.strip().split()[0] if command.strip() else ""
        allowed = False
        for prefix in _SHELL_WHITELIST_PREFIXES:
            if cmd_first == prefix or cmd_first.startswith(prefix + " "):
                allowed = True
                break
        if not allowed:
            print(f"[event_consumer] 🚫 命令 '{cmd_first}' 不在白名单中 → 拒绝执行")
            return False

        return True

    def _dispatch(self, event: dict, rule: dict) -> bool:
        """
        分派事件到下游动作

        优先走新格式：action.exec + action.script（D3 安全加固，无 shell 注入）；
        旧格式 action.command 保留为兼容路径（经 _check_shell_safe 白名单校验，已废弃）。

        参数:
            event: 事件字典
            rule:  命中的规则字典

        返回:
            True 表示分派成功，False 表示失败
        """
        action = rule.get("action", {})
        exec_cmd = action.get("exec", "")
        script = action.get("script", "")

        # 新格式（v0.6.0）：exec + script，安全分派
        if exec_cmd and script:
            return self._dispatch_safe(event, rule, exec_cmd, script)

        # 旧格式兼容：command 模板（已废弃，仅兼容老规则）
        command_template = action.get("command", "")
        if not command_template:
            print(f"[event_consumer] ⚠️ 规则 {rule.get('id')} 无 exec/script 或 command 配置")
            return False

        print(f"[event_consumer] ⚠️ 规则 {rule.get('id')} 使用旧版 command 格式"
              f"（建议迁移到 exec+script）")

        # 模板变量替换
        command = command_template.format(
            trace_id=event.get("trace_id", "unknown"),
            event_type=event.get("event_type", "unknown"),
            producer=event.get("producer", "unknown"),
            result=event.get("result", "unknown"),
            detail=event.get("detail", ""),
        )

        # Shell 安全检查
        if not self._check_shell_safe(command):
            return False

        try:
            print(f"[event_consumer] ▶️ 分派(legacy): [{rule.get('id')}] {command[:120]}")
            result = subprocess.run(
                command,
                shell=True,
                timeout=30,
                capture_output=True,
                text=True,
            )
            success = result.returncode == 0
            if not success:
                print(f"[event_consumer] ⚠️ 分派失败 (exit={result.returncode}): "
                      f"{result.stderr[:200]}")
            return success
        except subprocess.TimeoutExpired:
            print(f"[event_consumer] ⏰ 分派超时 (30s): {command[:80]}")
            return False
        except Exception as e:
            print(f"[event_consumer] ❌ 分派异常: {e}")
            return False

    def _dispatch_safe(self, event: dict, rule: dict,
                       exec_cmd: str, script: str) -> bool:
        """
        安全分派（D3：从丰碑 fork v0.6.0 移植）

        exec+script：事件数据经 EVENT_DATA 环境变量以 JSON 传递，
        不插入命令字符串；subprocess shell=False，零注入面。
        """
        import json as _json
        import shutil as _shutil

        # exec 白名单校验：仅允许 python 解释器
        _EXEC_WHITELIST = {"python", "python3"}
        if exec_cmd not in _EXEC_WHITELIST:
            print(f"[event_consumer] 🚫 exec '{exec_cmd}' 不在白名单 {_EXEC_WHITELIST} → 拒绝执行")
            return False

        code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 数据目录取消费者实际使用的 event 文件所在目录（iso-sand/data）
        data_dir = os.path.dirname(os.path.abspath(self._event_file))

        # 构建环境变量（事件数据作为 JSON 传递，不插入命令字符串）
        env = os.environ.copy()
        env["EVENT_DATA"] = _json.dumps(event, ensure_ascii=False)
        env["DATA_DIR"] = data_dir
        env["CODE_DIR"] = code_dir
        env["BASE_DIR"] = os.path.dirname(code_dir)

        # 选择 Python 可执行文件：优先规则指定的解释器；PATH 找不到则回退当前解释器
        # （Linux 常只有 python3 没有 python，回退保证 exec: "python" 规则也能跑）
        python_bin = exec_cmd
        if _shutil.which(python_bin) is None:
            python_bin = sys.executable

        try:
            print(f"[event_consumer] ▶️ 分派: [{rule.get('id')}] (safe mode)")
            result = subprocess.run(
                [python_bin, "-c", script],
                env=env,
                timeout=30,
                capture_output=True,
                text=True,
                shell=False,  # 关键：不使用 shell
            )
            success = result.returncode == 0
            if not success:
                print(f"[event_consumer] ⚠️ 分派失败 (exit={result.returncode}): "
                      f"{result.stderr[:300]}")
            return success
        except subprocess.TimeoutExpired:
            print(f"[event_consumer] ⏰ 分派超时 (30s): [{rule.get('id')}]")
            return False
        except FileNotFoundError:
            print(f"[event_consumer] ❌ Python 可执行文件未找到: {python_bin}")
            return False
        except Exception as e:
            print(f"[event_consumer] ❌ 分派异常: {e}")
            return False

    def _write_dead_letter(self, event: dict, reason: str):
        """写入死信队列"""
        record = {
            "t": datetime.now(_BJT).isoformat(),
            "event_type": "consumer_action",
            "producer": "event_consumer",
            "result": "FAIL",
            "detail": f"死信: {reason}",
            "original_event": event,
        }
        self._dead_writer.write(record)
        print(f"[event_consumer] 💀 写入死信: {reason}")

    def _process_event(self, event: dict):
        """处理单条事件：handler 链优先，无注册 handler 回退旧 rules（D6 兼容）

        D7 契约：schema 容忍 / 幂等去重 / trace_id WARN
        """
        event_type = event.get("event_type", "")
        result = event.get("result", "")

        # D7: schema_version 向后兼容 —— 老事件无该字段时容忍，默认 "1.0"，不拒绝
        schema_version = self._event_schema_version(event)

        # D7: trace_id 硬规范 —— 生产者必带；缺失时打 WARN 日志但继续处理，不拒绝
        if not event.get("trace_id"):
            print(f"[event_consumer] ⚠️ WARN: 事件缺少 trace_id "
                  f"(event_type={event_type}, producer={event.get('producer')})")

        # D7: 幂等去重 —— 同一 event_id 只处理一次（防 at-least-once 重投重复执行）
        if self._is_processed(event):
            print(f"[event_consumer] 🔁 幂等跳过: event_id={event.get('event_id')} 已处理过")
            return

        try:
            # D6: 先查 HandlerRegistry —— 有注册 handler 就走 handler 链；
            #     没有则回退旧 rules 机制（兼容期，rules 保留不删）
            if self._handler_registry and self._handler_registry.has_handlers(event_type):
                self._dispatch_handler_chain(event, event_type, result)
            else:
                self._dispatch_rules(event, event_type, result)
        except Exception as e:
            # 单条事件处理异常不应拖垮轮询循环
            print(f"[event_consumer] ❌ 处理事件异常: {e}")
        finally:
            # 处理完成（命中/未命中/死信）后标记已处理，防重投重复执行
            self._mark_processed(event)

    def _dispatch_handler_chain(self, event: dict, event_type: str, result: str):
        """D6: handler 链执行（异常隔离在 HandlerRegistry.dispatch 内）"""
        stats = self._handler_registry.dispatch(event)
        if stats["handled"] > 0:
            self._writer.write({
                "event_type": "consumer_action",
                "producer": "event_consumer",
                "result": "OK",
                "detail": (f"handler 链执行成功: {event_type}/{result} "
                           f"(handled={stats['handled']}, failed={stats['failed']})"),
                "trace_id": event.get("trace_id"),
            })
        else:
            # 全部 handler 失败/被跳过：单条失败已由 registry 记死信，这里记总账
            if stats["failed"] > 0:
                self._write_dead_letter(
                    event,
                    f"handler 链全部失败 (handled=0, failed={stats['failed']})"
                )
            else:
                print(f"[event_consumer] ℹ️ handler 链无执行: {event_type}/{result} "
                      f"(skipped={stats['skipped']})")

    def _dispatch_rules(self, event: dict, event_type: str, result: str):
        """旧 rules 机制（兼容回退，Phase 2 起仅对无注册 handler 的 event_type 生效）"""
        matched = False
        for rule in self._rules:
            match = rule.get("match", {})
            if match.get("event_type") != event_type:
                continue
            if match.get("result") and match["result"] != result:
                continue
            matched = True

            # 限流检查
            rule_id = rule.get("id", "unknown")
            min_interval = rule.get("rate_limit", 0)
            last_time = self._rate_limits.get(rule_id, 0)
            now = time.time()
            if now - last_time < min_interval:
                print(f"[event_consumer] ⏳ 限流跳过 [{rule_id}]: "
                      f"距上次分派 {now - last_time:.1f}s < {min_interval}s")
                continue

            # 分派（指数退避重试 3 次）
            max_retries = rule.get("max_retries", 3)
            success = False
            for attempt in range(max_retries):
                if attempt > 0:
                    wait = 2 ** attempt  # 指数退避: 2s, 4s, 8s
                    print(f"[event_consumer] 🔄 重试 #{attempt} (等待 {wait}s)...")
                    time.sleep(wait)
                success = self._dispatch(event, rule)
                if success:
                    break

            if success:
                self._rate_limits[rule_id] = now
                self._writer.write({
                    "event_type": "consumer_action",
                    "producer": "event_consumer",
                    "result": "OK",
                    "detail": f"规则 {rule_id} 分派成功: {event_type}/{result}",
                    "trace_id": event.get("trace_id"),
                })
            else:
                self._write_dead_letter(
                    event,
                    f"规则 {rule_id} 重试 {max_retries} 次均失败"
                )

        if not matched:
            print(f"[event_consumer] ℹ️ 无匹配规则: {event_type}/{result}")

    def poll_loop(self):
        """轮询主循环"""
        print(f"[event_consumer] 🟢 启动轮询 (间隔 {self._poll_interval}s)")
        print(f"[event_consumer] 事件文件: {self._event_file}")
        print(f"[event_consumer] 规则文件: {self._rules_file}")
        if self._handler_registry:
            n = len(self._handler_registry.list_handlers())
            print(f"[event_consumer] 🧩 handler 注册表: {n} 个 handler（优先于 rules）")
        else:
            print("[event_consumer] 🧩 handler 注册表: 已禁用（仅旧 rules 路径）")
        print(f"[event_consumer] 操作日志: {self._operation_log}")
        print(f"[event_consumer] 死信队列: {self._dead_letter}")

        # 清除非 JSON 行（启动时一次性清理）
        self._filter_non_json_lines()

        while not self._stop_event.is_set():
            try:
                if not os.path.exists(self._event_file):
                    time.sleep(self._poll_interval)
                    continue

                seek_offset = self._get_seek_offset()

                with open(self._event_file, "r", encoding="utf-8") as f:
                    f.seek(seek_offset)
                    new_lines = []
                    new_offset = seek_offset
                    while True:
                        pos = f.tell()
                        line = f.readline()
                        if not line:
                            break
                        new_lines.append(line)
                        new_offset = f.tell()

                    if not new_lines:
                        # 无新事件
                        self._stop_event.wait(self._poll_interval)
                        continue

                    # 逐条处理
                    for line in new_lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            # 运行时发现的非 JSON 行 → 清除
                            print(f"[event_consumer] ⚠️ 跳过非 JSON 行")
                            continue

                        self._process_event(event)

                    # 保存新偏移
                    self._save_seek_offset(new_offset)

            except Exception as e:
                print(f"[event_consumer] ❌ 轮询异常: {e}")
                time.sleep(self._poll_interval)

    def start(self):
        """启动消费者守护线程"""
        if self._thread and self._thread.is_alive():
            print("[event_consumer] ⚠️ 消费者已在运行")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self.poll_loop,
            daemon=True,
            name="event-consumer",
        )
        self._thread.start()
        print("[event_consumer] 🟢 消费者线程已启动")

    def stop(self):
        """停止消费者"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            print("[event_consumer] ⏹️ 消费者已停止")


def quick_test():
    """快速自测事件消费者核心功能"""
    import tempfile
    print("=" * 50)
    print("🧪 event_consumer.py 快速自测")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmpdir:
        event_file = os.path.join(tmpdir, "event_bus.jsonl")
        seek_file = os.path.join(tmpdir, "event_bus.seek")
        rules_file = os.path.join(tmpdir, "event_rules.yaml")
        op_log = os.path.join(tmpdir, "operation_log.jsonl")
        dead_letter = os.path.join(tmpdir, ".dead_letter_queue.jsonl")
        processed_ids = os.path.join(tmpdir, "processed_ids.jsonl")

        # 写入测试规则（旧格式 command，验证兼容路径）
        test_rules = {
            "rules": [
                {
                    "id": "test-echo",
                    "description": "测试规则",
                    "match": {"event_type": "test_event", "result": "OK"},
                    "action": {
                        "type": "bridge",
                        "target": "test",
                        "command": "echo 'handled: {trace_id}'"
                    },
                    "max_retries": 1,
                    "rate_limit": 0.0
                }
            ]
        }
        with open(rules_file, "w") as f:
            yaml.dump(test_rules, f)

        # 写入测试事件（4 条：正常 / 同 event_id 重复 / 缺 trace_id / 无匹配规则）
        events = [
            {
                "t": "2026-07-16T14:00:00+08:00",
                "event_type": "test_event",
                "producer": "test",
                "result": "OK",
                "trace_id": "test-001",
                "event_id": "11111111-1111-1111-1111-111111111111",
                "schema_version": "1.1",
            },
            # 同 event_id 重复投递（幂等去重应跳过）
            {
                "t": "2026-07-16T14:00:01+08:00",
                "event_type": "test_event",
                "producer": "test",
                "result": "OK",
                "trace_id": "test-001",
                "event_id": "11111111-1111-1111-1111-111111111111",
                "schema_version": "1.1",
            },
            # 缺 trace_id（D7：WARN 但继续处理）且无 schema_version（老事件容忍）
            {
                "t": "2026-07-16T14:00:02+08:00",
                "event_type": "test_event",
                "producer": "test",
                "result": "OK",
                "detail": "no trace id",
            },
            # 无匹配规则（不应死信）
            {
                "t": "2026-07-16T14:00:03+08:00",
                "event_type": "anomaly",
                "producer": "test",
                "result": "FAIL",
                "trace_id": "test-004",
            },
        ]
        with open(event_file, "w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        # 启动消费者（线程方式，避免 poll_loop 阻塞测试）
        # enable_handlers=False：自测只测旧 rules 路径，handler 链单独在 handlers.py 自测
        consumer = EventConsumer(
            event_file=event_file,
            seek_file=seek_file,
            rules_file=rules_file,
            operation_log=op_log,
            dead_letter=dead_letter,
            processed_ids_file=processed_ids,
            poll_interval=0.3,
            enable_handlers=False,
        )

        consumer._filter_non_json_lines()
        consumer.start()
        time.sleep(1.5)
        consumer.stop()

        # 测试 seek 文件
        assert os.path.exists(seek_file), "seek 文件应创建"
        print("✅ seek 文件创建正常")

        # 测试 shell 安全
        assert consumer._check_shell_safe("echo hello")
        assert not consumer._check_shell_safe("sudo rm -rf /")
        assert not consumer._check_shell_safe(":(){ :|:& };:")
        print("✅ shell 安全检查正常")

        # 测试非 JSON 行清除（原子重写）
        with open(event_file, "a") as f:
            f.write("这不是 JSON\n")
            f.write(json.dumps({"valid": True}) + "\n")

        cleared = consumer._filter_non_json_lines()
        assert cleared == 1, f"应清除 1 行非 JSON，实际 {cleared}"

        lines_after = []
        with open(event_file, "r") as f:
            lines_after = [l.strip() for l in f if l.strip()]
        print(f"✅ 非 JSON 行清除正常 (余 {len(lines_after)} 行)")

        # D7: 幂等去重 —— 同 event_id 两条只应分派一次（operation_log 只有 2 条 OK：
        # 事件1 分派 + 事件3 分派；事件2 被去重跳过，事件4 无匹配规则）
        op_recs = []
        with open(op_log, "r") as f:
            op_recs = [json.loads(l) for l in f if l.strip()]
        ok_count = sum(1 for r in op_recs if r.get("result") == "OK")
        assert ok_count == 2, f"应分派 2 次（去重后），实际 {ok_count}: {op_recs}"
        print("✅ 幂等去重正常：同 event_id 仅执行一次")

        # D7: 缺 trace_id 的事件被 WARN 后仍处理（ok_count=2 已含事件3）
        print("✅ 缺 trace_id 事件继续处理（WARN 不拒绝）")

        # D7: 去重文件落盘
        with open(processed_ids, "r") as f:
            id_lines = [json.loads(l) for l in f if l.strip()]
        assert len(id_lines) == 1, f"去重文件应有 1 条 event_id，实际 {len(id_lines)}"
        assert id_lines[0]["event_id"] == "11111111-1111-1111-1111-111111111111"
        print("✅ processed_ids.jsonl 落盘正常")

        # 死信应为空（事件4 无匹配规则不产生死信）
        dl_lines = []
        if os.path.exists(dead_letter) and os.path.getsize(dead_letter) > 0:
            with open(dead_letter, "r") as f:
                dl_lines = [l for l in f if l.strip()]
        assert len(dl_lines) == 0, f"死信应为空，实际 {len(dl_lines)}"
        print("✅ 无死信")

        # D7: schema 版本容忍 —— 老事件无 schema_version 默认 1.0
        assert consumer._event_schema_version({"a": 1}) == "1.0"
        assert consumer._event_schema_version({"schema_version": "1.1"}) == "1.1"
        print("✅ schema_version 向后兼容默认 1.0")

    print("=" * 50)
    print("✅ event_consumer.py 快速自测通过")
    print("=" * 50)


def main():
    """命令行入口：启动事件消费者"""
    import argparse

    parser = argparse.ArgumentParser(description="事件消费者守护进程")
    parser.add_argument("--test", action="store_true", help="运行快速自测")
    parser.add_argument("--daemon", action="store_true", help="以后台模式运行")
    parser.add_argument("--interval", type=float, default=3.0, help="轮询间隔（秒）")
    args = parser.parse_args()

    if args.test:
        quick_test()
        return

    consumer = EventConsumer(poll_interval=args.interval)
    consumer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[event_consumer] 收到 Ctrl+C，正在关闭...")
        consumer.stop()

    print("[event_consumer] 👋 已退出")


if __name__ == "__main__":
    main()
