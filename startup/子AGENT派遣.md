# 子AGENT派遣规范

> 基于4轮新AI测试+修复循环的实践经验总结
> 2026-07-06 v2.0

---

## 一、派遣前必读：今天踩过的坑

### 坑1：接口签名三处不一致（P0 最痛）

**表现**：同一组函数写了三套参数名——接口协议.md 一套、架构说明.md 一套、操作规范.md 另一套。新人AI读文件直接懵逼。

**根因**：写代码的子AI和写文档的子AI是分两批派的，互相不知道对方写了什么。主AI没做交叉审计。

**教训**：
- 写代码和写文档不要同时派不同子AI写不关联的文件
- 或者先写代码，再派一个子AI专门同步所有相关文档
- **主AI必须在所有子AI完成后做一次 cross-doc 签名审计**

### 坑2：操作规范写了不存在的组件（P0）

**表现**：`health_check.py` 在操作规范里写得有模有样（参数、输出格式都有），但此文件从未创建。

**根因**：子AI写文档时"脑补"了后续组件，没有验证文件是否存在。

**教训**：派遣子AI写文档时，必须在任务中明确要求——**"只记录实际存在的组件和接口，不虚拟未来功能"**。审计时 grep 所有文档中 import/from src 的引用，交叉验证是否真的在 src/ 中存在。

### 坑3：一号指令过时（P1）

**表现**：第一次写一号指令时项目还是"调研阶段"；后来代码写完、配置改完、文件补齐，但一号指令还停留在"调研子AI全部完成"。

**根因**：项目进展快（几小时内），一号指令是早期写的但没更新。

**教训**：关键项目进展后，必须检查并更新入口文档（一号指令/README版本号）。

### 坑4：200K上下文→写入限制（认知偏差）

**表现**：写入文件失败 → 以为是文件权限/写工具限制 → 研究了半天 → 根因是 contextWindow 太小导致频繁 compaction → compaction 的 memory flush 锁了 write。

**根因**：症状（写失败）和根因（上下文太窄）相距两层间接因果。

**教训**：遇到写入/权限类错误时，**先检查上下文利用率**（`/status` 看 Context 和 Compactions 数值）。如果 compaction 次数高，优先放大 contextWindow。

### 坑5：thinking 配置链条断（P1）

**表现**：改了 `reasoning: true` 但 `Think: off`。不知道还需要 `thinkingDefault: medium`。

**根因**：配置生效优先级没搞清楚——session 覆盖 > config 默认。

**教训**：改完配置后必须用 `/status` 验证实际生效状态。改 config 不等于 session 生效。

### 坑6：子AI跑完了没审计就收（P0 最痛）

**表现**：第一批写代码/写文件的子AI回来，主AI直接用了，没检查 import 是否通过、接口签名是否正确、git 是否 commit。

**教训**：
- **任何子AI返回的结果，必须经过主AI审计才能算完成**
- 审计不是"读摘要"，是实际跑代码/读文件/验证 git log

### 坑7：版本号分散不同步（P0）

**表现**：README 是 v0.2，架构说明是 v0.1，install.sh 是 v0.1，mcp_registry.json 是 0.1。新人AI看到三四个版本号不知道信哪个。

**根因**：每个子AI只负责自己的文件，没人同步所有文件的版本号。

**教训**：版本号必须在所有文档中统一。定义一个主版本号源（README.md 第一行），每次更新时 grep 所有文件统一修改。

### 坑8：文件清单与磁盘文件不符（P0）

**表现**：项目章程和架构说明的文件树中列出了 `health_check.py`（不存在）、`rollback_manager.py`（不存在）、`v0.1_初版架构.md`（实际叫别的名字）。同时 miss 了 `v0.1_service_design.md`（存在但文档没列出）。

**根因**：
- 写了不存在的文件（脑补）
- 漏写了存在的文件（没 ls 目录确认）

**教训**：任何列出文件清单的地方，必须 `ls` 目录后逐项核对。**不准脑补文件名**。

### 坑9：git 未提交文件堆积（P1）

**表现**：修了好几个文档轮次但没 git commit，新手AI来的时候 `git status` 显示 5 个未跟踪文件。

**教训**：每轮修改后立即 `git add && git commit`。不要让未提交文件堆积。

---

## 二、代码自由王国标准（来自轻如烟 edit-web.py v5.0「自由王国」）

派遣子AI写代码时，**以下标准必须在任务描述中明确要求**，且审计时逐一检查。

### 2.1 模块独立（单一职责）

```
每模块只做一件事：
- iso_logger.py → 只管写日志和读日志
- facts_manager.py → 只管断言图 CRUD
- essence_distiller.py → 只管从日志提炼轮感
不跨职责、不互相 import 对方做功能交叉。
```

### 2.2 接口统一（自由王国核心要求）

```
接口签名三统一：
1. 函数名 → 语义清晰、动词开头（append_xxx, get_xxx, save_xxx）
2. 参数名 → type_hinting 一致、顺序一致
3. 返回值类型 → 同模块内同一操作返回同类型

交叉验证：
- src/ 代码中的接口 = 项目中所有文档中的接口
- 文档之间互相引用的接口签名必须一致
```

### 2.3 变量命名统一（自由王国核心要求）

```
命名规范（整个项目的通用变量字典）：
- 日志时间字段: t (ISO 8601)
- 日志级别: level
- 操作者: actor
- 操作名: action
- 目标: target
- 结果: result
- 详情: detail
- 追踪链: trace_id
- 断言类别: category
- 断言语句: statement
- 断言日期: date
```

### 2.4 前后端分离（适用于有 UI 场景）

```
代码自由王国要求：
- 业务逻辑和展示分离
- 数据层不感知展示层
- 通用函数不嵌入业务特定代码
```

### 2.5 联合编辑（自由王国协作模式）

```
子AI写代码 → 主AI审计 → 另一个子AI交叉验证 → 完成
三步缺一不可。不允许"写完了就收"。

每次循环：
1. 派遣写代码的子AI
2. 主AI审计（import+接口+文件完整性）
3. 派遣"新人模拟"子AI读文件做理解测试
4. 如果发现问题 → 回到步骤1修复
5. 直到新人模拟找出 0 个问题为止
```

### 2.6 版本号统一（新增，从坑7来）

```
版本号定义规则：
- 主版本号在 README.md 第一行定义
- 所有文档必须使用同一版本号
- 更新版本号时 grep 所有文件统一修改
- 版本号禁止出现在文件名中（除非是 revision 归档）

验证命令：
grep "v0\." README.md docs/*.md deploy/install.sh deploy/mcp_registry.json
# 所有输出必须完全一致
```

### 2.7 文件清单一致（新增，从坑8来）

```
文件清单和文件树的要求：
- 所有文档中的文件列表必须 ls 目录后逐项核对
- 不写不存在的文件（禁止脑补）
- 不漏存在的文件（必须 ls 确认）
- revision 文件名使用语义命名而非日期命名

验证命令：
# 对于每个 doc 中的文件列表，实际检查
for f in $(grep -oP '\w+/[\w\.-]+' docs/项目章程.md); do
  test -f "$f" || echo "⚠️ 不存在: $f"
done
```

### 2.8 接口协议自洽（新增，从坑1来）

```
三叉戟验证：
1. src/ 代码中的函数签名
2. docs/接口协议.md 中的函数签名
3. docs/操作规范.md/docs/架构说明.md 中的函数签名

三者必须完全一致。不一致就是 bug。

验证命令：
grep "append_fact\|get_facts\|log\|get_logs" docs/接口协议.md docs/架构说明.md docs/操作规范.md
```

---

## 三、派遣子AI的规范化模板

每次派遣子AI工作前，**主AI必须自问**：

```
1. 这个任务需要读哪些文件？要不要列出依赖文件清单？
2. 子AI可能踩什么坑？（参考第一节清单）
3. 怎么验证子AI的结果？（审计清单看第四节）
4. 这个任务的输出是否需要同步更新其他文档？（版本号、接口签名、文件清单）
```

### 模板

```markdown
## 任务：<任务名>

### 目标
一句话说清要做什么。

### 约束
- 必须用 exec 方式写文件（原因：xxx）
- 不要虚拟不存在的组件
- 接口签名必须与已有代码一致（交叉验证要求见2.8）
- 版本号与 README.md 一致（要求见2.6）
- 文件清单需 ls 目录后逐项核对（要求见2.7）

### 依赖文件（必须阅读后再动手）
- <路径1> — 为什么需要读
- <路径2> — 为什么需要读

### 验证要求
任务完成后必须：
1. <验证步骤1>
2. <验证步骤2>

### 输出
<预期的输出格式>
```

### 黑名单（禁止子AI做的事）

| 禁止项 | 原因 |
|--------|------|
| 写一个不存在的组件/接口的文档 | 虚拟未来功能 → 误导新人 |
| 改动不是自己负责的文件 | 职责越界 → 冲突 |
| 使用与现有代码不一致的接口签名 | 坑1：三处不一致 |
| 不做 import 验证就提交 | 写了跑不通的代码 |
| 不写操作日志 | 没有日志的操作视为未发生 |
| 在文件名中加入日期（除非是 revision 归档） | 文件名与版本号耦合 → 坑7 |
| 列文件清单时不 ls 确认 | → 坑8 |

---

## 四、主AI审计清单

### 4.1 每个子AI回来的必经审计

```python
[
  "✅ 文件确认存在",
  "✅ import 验证通过",
  "✅ git log 有对应 commit",
  "✅ 当前无未提交文件（git status 干净）",
  "✅ 接口签名与相关文档一致（三叉戟检查）",
  "✅ 没有引入不存在的组件引用",
  "✅ 没有漏掉存在的文件（ls 核对）",
  "✅ 版本号与 README.md 一致",
  "✅ 操作日志有对应记录",
]
```

### 4.2 跨子AI的交叉审计

当多个子AI被派出时（比如写代码的 + 写文档的并行），主AI需要在所有子AI回来后做交叉审计：

```bash
# 检查所有文档之间的接口签名一致性
grep "append_fact" docs/接口协议.md docs/架构说明.md docs/操作规范.md
# 同一行输出三个文件 → 必须完全一致

# 检查不存在的组件引用
grep -n "import\|from src\." docs/*.md
# 所有 import 的对象必须在 src/ 中存在

# 检查版本号统一
grep "v0\." README.md docs/*.md deploy/install.sh deploy/mcp_registry.json
# 所有输出必须一致

# 检查文件清单与实际一致
cat docs/项目章程.md | grep -oP '[\w/-]+\.\w+' | grep -v "http\|git" | sort -u | while read f; do
  test -f "$f" || test -d "$f" || echo "⚠️ 不存在: $f"
done
```

### 4.3 "新人测试"迭代法（核心质检流程）

```
步骤：
1. 代码和文档全部就绪 → 主AI做第一遍审计
2. 派一个对项目一无所知的子AI去读文件做理解测试
3. 收集它发现的问题
4. 修复所有问题
5. 回到步骤2（派一个新AI，因为上一个已经读完文件了）
6. 直到新人AI找不到任何矛盾/歧义/缺口为止

关键：
- 每次测试必须用全新的子AI（不知道历史信息）
- 每次测试必须逐条回答：项目理解、组件、配置、规范、困惑
- 评分目标：S 级（完美无缺）
```

---

## 五、操作日志规范

每次派遣/审计/修复操作后必须在 `operation_log.jsonl` 中记录。

日志格式：
```json
{"t":"ISO8601","level":"INFO|WARN|ERROR","actor":"subagent-<taskName>","action":"<操作>","target":"<目标>","result":"OK|FAIL|PARTIAL","detail":"<描述>","trace_id":"<追踪ID>"}
```

必写日志场景：
- ✏️ 派遣子AI（日志在子AI返回后由主AI补写）
- ✅ 子AI完成验证
- ❌ 审计发现问题
- 🔧 修复问题
- 🧪 新人测试完成（附带评级）

---

## 六、快速验证命令清单

```bash
# 验证 1：三个组件 import
cd /vol1/@team/qh团队/QH/AI专用/同构沙盘IsoSand
python3 -c "from src.iso_logger import log, get_logs; print('iso_logger OK')"
python3 -c "from src.facts_manager import append_fact, get_facts, get_categories, count; print('facts_manager OK')"
python3 -c "from src.essence_distiller import distill, save_essence, load_essence, scan_logs; print('essence_distiller OK')"

# 验证 2：git 状态
git status --short
git log --oneline -5

# 验证 3：操作日志
wc -l data/operation_log.jsonl
tail -3 data/operation_log.jsonl | python3 -m json.tool --no-ensure-ascii 2>/dev/null

# 验证 4：版本号
grep "v0\." README.md docs/*.md deploy/install.sh deploy/mcp_registry.json

# 验证 5：断言图
head -10 data/facts.dict.md

# 验证 6：config
openclaw config validate
openclaw config get agents.defaults.thinkingDefault

# 验证 7：服务
ss -tlnp | grep -E '16878|18888|18886'
```
