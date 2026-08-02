// 轻如烟 · 沙漏注入插件 v6.2
// 2026-07-26：修复prefetch多行prompt导致Python语法错误
// 核心改变：query清理换行+截断100字符，块1简化为画像/场景上下文
// 2026-08-03（P1.1）：L0 怀疑灯——5类免费信号（矛盾/利害/FOK/惊讶/纠错）检测，
//   输出一行到动态区末尾；feature flag DOUBT_L0 控制；零LLM调用，异常静默降级
// 2026-08-03（P1.3）：纠错→三元组教训——保守预检 + 后台调用 lesson_capture.py 写沙漏；
//   feature flag QINGRUYAN_LESSON_CAPTURE=off 关闭；不阻塞主流程

const { spawn, execSync } = require("child_process");
const fs = require("fs");

const SANDGLASS_CLI = "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass_source/system_prompt_cli.py";
const SANDBASE_HOME = "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass";
const CLI_TIMEOUT = 10000;
const PREFETCH_TIMEOUT = 8000;
const ALERT_FILE = "/tmp/sandglass-injection-alert.txt";

// ═══════ L0 怀疑灯（P1.1：5类免费信号）═══════
// feature flag: DOUBT_L0（默认开；设 DOUBT_L0=0/off/false 一键关）
// 零 LLM 调用：关键词表 + 本地启发式 + prefetch侧车 + LMS HTTP
// 任何异常静默降级，绝不影响主注入

const DOUBT_FLAG = (() => {
  const v = process.env.DOUBT_L0;
  if (v === undefined || v === "") return true;
  return !["0", "false", "off", "no"].includes(String(v).toLowerCase());
})();

const DOUBT_FOK_FILE = "/tmp/doubt-fok.json";
const DOUBT_LMS_URL = "http://localhost:8190/status/main";
const DOUBT_LMS_TIMEOUT = 800;
const DOUBT_LMS_THRESHOLD = 0.35; // 惊讶度(自由能)，静默基线≈0.12，阈值可调
const DOUBT_FOK_MIN = 0.3;        // FOK 甜蜜区下界（字符bigram Jaccard）
const DOUBT_FOK_MAX = 0.7;        // FOK 甜蜜区上界

// ① 矛盾标记（转折/对立/回溯引用）
const CONTRADICTION_MARKERS = [
  "但是", "可是", "然而", "不过", "实际上", "事实上", "恰恰相反",
  "你上次说", "上次你说", "你之前说", "你以前说", "你明明说", "你说过",
  "反了", "搞反", "说反", "正好相反", "跟之前说的不一样",
];

// ⑤ 纠错标记（"你又忘了/不对/不是这样"等）
const CORRECTION_MARKERS = [
  "你又忘了", "又忘了", "不对", "不是这样", "不是这个", "你记错了", "记错了",
  "你理解错了", "理解错了", "你搞错了", "搞错了", "你听错了", "没听明白",
  "我说的是", "我的意思是", "更正", "纠正", "错了", "打脸", "翻车",
  "重新说", "重说一遍", "没看懂", "你根本没",
];

// ② 利害度关键词（事实/承诺/偏好/日程类）
const STAKES_KEYWORDS = [
  "答应", "承诺", "说好", "约定", "约好", "保证",
  "截止", "期限", "deadline",
  "合同", "工资", "收入", "预算", "付款", "转账", "还款",
  "喜欢", "讨厌", "偏好", "最爱", "习惯", "从不", "从来不",
  "必须", "一定", "千万", "务必", "记得", "别忘了",
  "生日", "纪念日", "约会", "几点", "什么时候",
];

const DATE_RE = /\d{4}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?|(?:今天|明天|后天|昨天|大后天|下周|下个月|这周|这个月|月底|月初|星期[一二三四五六日天]|周[一二三四五六日天])/g;
const MONEY_RE = /\d+(?:\.\d+)?\s*(?:元|块|万|千|美元|美金|欧元|日元|人民币|¥|￥|\$)/g;
const TIME_RE = /\d{1,2}[点时](?:\d{1,2}分)?|(?:上午|下午|中午|晚上|半夜|凌晨|今晚|明早)/g;

const NEGATION_RE = /(?:不|没|别|并非|不是|不再|压根不|从来不)([\u4e00-\u9fffA-Za-z0-9]{2,8})/g;
const NEGATION_STOPWORDS = ["这样", "那样", "这个", "那个", "什么", "怎么", "一样", "回事", "意思", "要紧", "碍事"];

// ═══════ P1.3 纠错→三元组教训（feature flag: QINGRUYAN_LESSON_CAPTURE=off 可一键关） ═══════
const LESSON_SCRIPT = "/vol1/@apphome/trim.openclaw/data/workspace/scripts/lesson_capture.py";
const LESSON_ENABLED = process.env.QINGRUYAN_LESSON_CAPTURE !== "off";
// 与 lesson_capture.py 内 STRONG_KEYWORDS / BLOCKERS 保持一致（JS 只做廉价预检，Python 侧再完整判定）
const LESSON_STRONG_RE = /(你又忘了|你忘了|你记错|记错了|你说错|说错了|你理解错|理解错了|不是这样|不对|错了|纠正|更正|不是那个意思|不是这个意思|你搞错|搞错了|你弄错|弄错了|你错了|说得不对|说反了|你搞反了|不是那么回事|你记错了|你又说错了|不是这么回事)/;
const LESSON_BLOCK_RE = /[？?]|明天|再说|算了|先这样|以后|改天|回头|待会|不了|不用了|打住|到此为止|先不聊/;

function extractLastAssistantText(messages) {
  if (!Array.isArray(messages)) return "";
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (!m || typeof m !== "object") continue;
    if (m.role !== "assistant") continue;
    const c = m.content;
    if (typeof c === "string") return c;
    if (Array.isArray(c)) {
      return c
        .filter((p) => p && p.type === "text" && typeof p.text === "string")
        .map((p) => p.text)
        .join("\n");
    }
    return "";
  }
  return "";
}

// 后台捕获教训：fire-and-forget，不 await，不阻塞主流程（正则预检成本≈0）
function maybeCaptureLesson(prompt, messages) {
  if (!LESSON_ENABLED) return;
  if (!prompt || prompt.length < 3 || prompt.length > 300) return;
  if (!LESSON_STRONG_RE.test(prompt)) return;
  if (LESSON_BLOCK_RE.test(prompt)) return;
  const assistantMsg = extractLastAssistantText(messages);
  if (!assistantMsg || assistantMsg.trim().length < 10) return;
  try {
    const py = spawn("python3", [LESSON_SCRIPT], {
      detached: true,
      stdio: ["pipe", "ignore", "ignore"],
      env: { ...process.env, NEXSANDBASE_HOME: SANDBASE_HOME },
    });
    py.stdin.write(JSON.stringify({ user_msg: prompt, assistant_msg: assistantMsg }));
    py.stdin.end();
    py.unref();
  } catch (e) {
    writeAlert(`lesson capture spawn error: ${e.message}`);
  }
}

// ═══════ 四层注入（system_prompt_block） ═══════

function getSystemPromptBlock() {
  return new Promise((resolve) => {
    const py = spawn("python3", [SANDGLASS_CLI], {
      env: { ...process.env, NEXSANDBASE_HOME: SANDBASE_HOME },
    });

    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      py.kill("SIGTERM");
      writeAlert("system_prompt_block timeout");
      resolve("");
    }, CLI_TIMEOUT);

    py.stdout.on("data", (data) => { stdout += data.toString(); });
    py.stderr.on("data", (data) => { stderr += data.toString(); });

    py.on("close", (code) => {
      clearTimeout(timer);
      if (timedOut) return;
      if (code === 0 && stdout.trim()) {
        resolve(stdout.trim());
      } else {
        writeAlert(`system_prompt_block failed: code=${code} stderr=${stderr.substring(0, 100)}`);
        resolve("");
      }
    });

    py.on("error", (err) => {
      clearTimeout(timer);
      writeAlert(`system_prompt_block error: ${err.message}`);
      resolve("");
    });

    py.stdin.end();
  });
}

// ═══════ 每轮注入（prefetch） ═══════
// 三块式：搜索引导 / 记忆候选 / 当前状态
// query必须清理换行+截断，避免Python字符串字面量断裂

function getPrefetchBlock(query) {
  try {
    // 清理query：去掉换行/制表符/所有引号字符（防止破坏 Python 字符串字面量）
    const cleanQuery = query
      .replace(/[\r\n\t`"']/g, " ")
      .replace(/\\/g, " ")
      .replace(/\s+/g, " ")
      .substring(0, 100);

    const cmd = `cd /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass_source && NEXSANDBASE_HOME="${SANDBASE_HOME}" python3 -u -c "
import sys, os
sys.path.insert(0, '.')
os.environ['NEXSANDBASE_HOME'] = '${SANDBASE_HOME}'

blocks = []

# 块1: 搜索引导
try:
    from sandglass_think import search_filter
    sf = search_filter('${cleanQuery}')
    ctx = sf or {}
    guide_parts = []
    if ctx.get('persona_context'):
        guide_parts.append('画像: ' + ctx['persona_context'][:30])
    if ctx.get('scene_context'):
        guide_parts.append('场景: ' + ctx['scene_context'][:30])
    if guide_parts:
        blocks.append('🔍 ' + ' | '.join(guide_parts))
except: pass

# 块2: 记忆候选
try:
    from sandglass_vault import search
    results = search('${cleanQuery}', limit=3)
    if results:
        mem_lines = ['📋 相关记忆:']
        for ln, ts, txt, *_ in results[:3]:
            short_ts = ts[:10] if len(ts) >= 10 else ts
            short_text = txt[:80].replace(chr(10), ' ')
            mem_lines.append(f'  [{short_ts}] {short_text}')
        blocks.append(chr(10).join(mem_lines))
except: pass

# 块3: 当前状态+决策
status_parts = []
try:
    from sandglass_think import comprehensive_offset, _emotional_entropy
    off = comprehensive_offset()
    ent = _emotional_entropy()
    mood = '平稳' if ent < 0.5 else ('波动' if ent < 1.0 else '高熵')
    dirs = {'frugal': '省钱', 'spend': '愿投', 'drift': '放弃'}
    off_d = dirs.get(off.get('direction', ''), '平稳')
    status_parts.append(f'状态: {off_d}({off.get(\"offset\",0):+d}%) | 🎭{mood}')
except: pass

try:
    from scene_l3 import scene_current
    scenes = scene_current()
    if scenes: status_parts.append('场景: ' + '·'.join(scenes[:3]))
except: pass

try:
    from discipline import iron_rules_with_counts
    rules = iron_rules_with_counts(3)
    if rules:
        rule_strs = [f'⚠{r[:40]}' for r, c in rules if c > 0]
        if not rule_strs: rule_strs = [f'⚠{r[:40]}' for r, _ in rules[:2]]
        if rule_strs: status_parts.append(' | '.join(rule_strs[:2]))
except: pass

if status_parts:
    blocks.append(chr(10).join(status_parts))

# [L0怀疑灯·旁路] FOK相似度侧车：不影响上面三块输出，供JS侧读取
# 字符bigram Jaccard 近似嵌入相似度；失败/无结果则 sim=0（JS侧跳过）
try:
    import json as _fok_json, re as _fok_re, time as _fok_time

    def _fok_tok(_s):
        _t = set()
        for _m in _fok_re.finditer(r'[a-z0-9]+', _s.lower()):
            _t.add(_m.group(0))
        _cjk = _fok_re.sub(r'[^\\u4e00-\\u9fff]', '', _s)
        for _i in range(len(_cjk) - 1):
            _t.add(_cjk[_i:_i + 2])
        return _t

    _fok_q = _fok_tok('${cleanQuery}')
    _fok_sim = 0.0
    try:
        from sandglass_vault import search as _fok_search
        for _fok_ln, _fok_ts, _fok_txt in _fok_search('${cleanQuery}', limit=3)[:3]:
            _fok_t2 = _fok_tok(_fok_txt)
            if _fok_q and _fok_t2:
                _fok_j = len(_fok_q & _fok_t2) / len(_fok_q | _fok_t2)
                if _fok_j > _fok_sim:
                    _fok_sim = _fok_j
    except Exception:
        pass
    try:
        with open('/tmp/doubt-fok.json', 'w') as _fok_f:
            _fok_f.write(_fok_json.dumps({'query': '${cleanQuery}', 'sim': round(_fok_sim, 4), 'ts': _fok_time.time()}))
    except Exception:
        pass
except Exception:
    pass

result = chr(10).join(blocks)
if len(result) > 600: result = result[:597] + '...'
print(result)
"`;

    const output = execSync(cmd, {
      timeout: PREFETCH_TIMEOUT,
      encoding: "utf-8",
      env: { ...process.env, NEXSANDBASE_HOME: SANDBASE_HOME },
    }).trim();

    return output;
  } catch (e) {
    writeAlert(`prefetch failed: ${e.message}`);
    return "";
  }
}

// ═══════ L0 怀疑灯：信号检测 ═══════
// 输入：本轮 prompt（入站消息）+ 已注入上下文（画像+记忆）+ prefetch起始时间
// 输出：信号短名数组（矛盾/利害/FOK/惊讶/纠错），异常静默返回 []

async function detectDoubtSignals(prompt, injectedContext, fokFreshSince) {
  const signals = [];
  if (!prompt) return signals;

  // ① 矛盾检测：转折/对立标记 + 否定-实体一致性
  try {
    let contradiction = false;
    for (const m of CONTRADICTION_MARKERS) {
      if (prompt.includes(m)) { contradiction = true; break; }
    }
    if (!contradiction && injectedContext) {
      let m;
      NEGATION_RE.lastIndex = 0;
      while ((m = NEGATION_RE.exec(prompt)) !== null) {
        // 去掉句尾语气/时态助词后，精确实体-属性匹配（≥3字，防泛词误报）
        const phrase = m[1].replace(/[了啊吧呢吗的]+$/, "");
        if (phrase.length < 3) continue;
        if (NEGATION_STOPWORDS.some((s) => phrase.startsWith(s))) continue;
        if (injectedContext.includes(phrase)) { contradiction = true; break; }
      }
    }
    if (contradiction) signals.push("矛盾");
  } catch (e) {}

  // ② 利害度评分：关键词+日期+钱+时间，≥2分触发（闲聊单点不误报）
  try {
    let score = 0;
    for (const kw of STAKES_KEYWORDS) {
      if (prompt.includes(kw)) score += 1;
    }
    score += (prompt.match(DATE_RE) || []).length;
    score += (prompt.match(MONEY_RE) || []).length * 2;
    score += (prompt.match(TIME_RE) || []).length;
    if (score >= 2) signals.push("利害");
  } catch (e) {}

  // ③ FOK 相似度区间带：读 prefetch 侧车（沙漏query失败/超时则跳过）
  try {
    if (fokFreshSince && fs.existsSync(DOUBT_FOK_FILE)) {
      const st = fs.statSync(DOUBT_FOK_FILE);
      if (st.mtimeMs >= fokFreshSince) {
        const fok = JSON.parse(fs.readFileSync(DOUBT_FOK_FILE, "utf-8"));
        const sim = Number(fok.sim || 0);
        if (sim >= DOUBT_FOK_MIN && sim <= DOUBT_FOK_MAX) signals.push("FOK");
      }
    }
  } catch (e) {}

  // ④ LMS 惊讶度：读 8190 状态接口（失败/超时静默跳过）
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), DOUBT_LMS_TIMEOUT);
    let surprise = null;
    try {
      const res = await fetch(DOUBT_LMS_URL, { signal: ctrl.signal });
      if (res.ok) {
        const data = await res.json();
        surprise = Number((data.status || {}).last_surprise);
      }
    } finally {
      clearTimeout(timer);
    }
    if (Number.isFinite(surprise) && surprise > DOUBT_LMS_THRESHOLD) signals.push("惊讶");
  } catch (e) {}

  // ⑤ 纠错标记
  try {
    for (const m of CORRECTION_MARKERS) {
      if (prompt.includes(m)) { signals.push("纠错"); break; }
    }
  } catch (e) {}

  return signals;
}

// ═══════ 报警 ═══════

function writeAlert(msg) {
  try {
    fs.writeFileSync(ALERT_FILE, `${new Date().toISOString()} ${msg}`);
  } catch (e) {}
}

function checkAlert() {
  try {
    if (fs.existsSync(ALERT_FILE)) {
      const content = fs.readFileSync(ALERT_FILE, "utf-8").trim();
      const alertTime = new Date(content.split(" ")[0]).getTime();
      if (Date.now() - alertTime < 5 * 60 * 1000) {
        return content;
      }
    }
  } catch (e) {}
  return null;
}

// ═══════ 主逻辑 ═══════

module.exports = {
  id: "qingruyan-behavior-enforcer",
  name: "轻如烟沙漏注入",
  register(api) {
    api.on(
      "before_prompt_build",
      async (event) => {
        try { fs.writeFileSync("/tmp/plugin-ran.txt", new Date().toISOString()); } catch(e) {}

        const prompt = event.prompt || "";
        const isSilentPeriod = prompt.includes('轮感检查') && prompt.includes('静默期');

        if (isSilentPeriod) {
          try { fs.writeFileSync("/tmp/last-injection-body.txt", "静默期"); } catch(e) {}
          return { prependSystemContext: "## 🌙 静默期\n\n不需要输出。安静待着。" };
        }

        // === Part 1: 四层注入 ===
        let systemBlock = "";
        try {
          systemBlock = await getSystemPromptBlock();
        } catch(e) {
          writeAlert(`system_block await error: ${e.message}`);
        }

        // === Part 2: prefetch ===
        let prefetchBlock = "";
        const prefetchStartedAt = Date.now(); // 供 FOK 侧车新鲜度校验
        try {
          prefetchBlock = getPrefetchBlock(prompt);
        } catch(e) {
          writeAlert(`prefetch error: ${e.message}`);
        }

        // === 组装 ===
        let parts = [];

        if (systemBlock) {
          parts.push("## 🌫️ 沙漏脉冲\n\n" + systemBlock);
        }

        if (prefetchBlock) {
          parts.push("## ⏳ 沙漏召回\n\n" + prefetchBlock);
        }

        // 降级报警
        const alert = checkAlert();
        if (alert) {
          parts.push("## ⚠️ 沙漏注入异常\n\n" + alert + "\n\n请通知dandan检查沙漏系统。");
        }

        // 完全失败时的身份锚点
        if (!systemBlock && !prefetchBlock) {
          parts.push("## 🆘 沙漏系统离线\n\n你是轻如烟，dandan的AI。沙漏记忆系统当前不可用，请通知dandan。");
        }

        // === Part 3: L0 怀疑灯（P1.1）===
        let doubtLine = "";
        if (DOUBT_FLAG) {
          try {
            const ctxForDoubt = (systemBlock ? systemBlock + "\n" : "") + (prefetchBlock || "");
            const signals = await detectDoubtSignals(prompt, ctxForDoubt, prefetchStartedAt);
            if (signals.length > 0) {
              doubtLine = `⚠️ 本回合可疑信号：${signals.length}（${signals.join("·")}）`;
            }
          } catch(e) {
            writeAlert(`doubt detect error: ${e.message}`);
          }
        }

        // 怀疑灯行追加到动态区末尾
        if (doubtLine) parts.push(doubtLine);

        // === Part 4: 纠错→三元组教训（P1.3，后台写沙漏，不阻塞主流程） ===
        try {
          maybeCaptureLesson(prompt, event.messages);
        } catch(e) {
          writeAlert(`lesson capture error: ${e.message}`);
        }

        const injectionContent = parts.join("\n\n");

        // 调试日志
        try {
          fs.writeFileSync("/tmp/plugin-injected.txt", new Date().toISOString());
          const detail = `系统块: ${systemBlock ? "✅" : "❌"} | 预搜块: ${prefetchBlock ? "✅" : "❌"} | 报警: ${alert ? "⚠️" : "无"} | 怀疑灯: ${doubtLine ? "💡" : "—"}`;
          fs.writeFileSync("/tmp/last-injection.txt", `${new Date().toISOString()} | ${detail}`);
          fs.writeFileSync("/tmp/plugin-doubt.txt", doubtLine || "(无信号)");
          fs.writeFileSync("/tmp/last-injection-body.txt", injectionContent.substring(0, 2000));
        } catch(e) {}

        return {
          prependSystemContext: injectionContent,
        };
      },
      { priority: 100 },
    );
  },
};
