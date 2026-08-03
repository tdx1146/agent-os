// 轻如烟 · 沙漏注入插件 v6.4
// 2026-07-26：修复prefetch多行prompt导致Python语法错误
// 核心改变：query清理换行+截断100字符，块1简化为画像/场景上下文
// 2026-08-03（P1.1）：L0 怀疑灯——5类免费信号（矛盾/利害/FOK/惊讶/纠错）检测，
//   输出一行到动态区末尾；feature flag DOUBT_L0 控制；零LLM调用，异常静默降级
// 2026-08-03（P1.3）：纠错→三元组教训——保守预检 + 后台调用 lesson_capture.py 写沙漏；
//   feature flag QINGRUYAN_LESSON_CAPTURE=off 关闭；不阻塞主流程
// 2026-08-03（P2.2）：L1 检索层升级——prefetch 异步化（spawn）+ TTL缓存24h + 语义/BM25混合 + 多样性防锚定；
//   feature flag QINGRUYAN_PREFETCH_V2=off 退回 v6.2 同步路径；不破坏 P1.1/P1.3
// 2026-08-03（P2.1）：L2 幽灵决策接线——决策场景检测→entropy_ghost，TTL 24h/主题、日≤5次；
//   feature flag QINGRUYAN_GHOST_DECISION=off 关闭；失败静默降级
// 2026-08-03（P2.4）：topic_risk.json——风险分维护（失败+2/夜巡+3/审查-1/日衰减0.5，≥4升级 ≥8强制）+
//   高风险注入提示；feature flag QINGRUYAN_TOPIC_RISK=off 关闭；原子写+串行锁
// 2026-08-03（P3.1）：L3 子代理审查——高风险检测（不可逆操作/金额承诺/topic_risk≥4/连续否定2次）→
//   注入 🚨 建议审查 + 原子写 /tmp/l3-review-request.json（主AI/夜巡消费）；同一主题1h去重；
//   feature flag QINGRUYAN_L3_REVIEW=off 关闭；插件无 sessions_spawn 权限，只提需求不自动 spawn
// 2026-08-03（P3.2）：记忆信任度注入加权——prefetch 候选排序改 relatedness × freshness_weight；
//   数据层 /tmp/memory-trust.json 就绪用真实公式 1/(1+age)×(1-反驳率)，否则年龄分桶降级+doubt.db 反驳近似；
//   被推翻≥2次权重压到 0.1（防回声室）；feature flag QINGRUYAN_MEMORY_TRUST=off；注入格式不变（📋 相关记忆 3条）
// 2026-08-03（P3.3）：反教条提示——记忆被引用≥3次且>30天 → ⚠️ 复核提示（每天每topic≤1次，全局日≤3次兜底）；
//   或匹配夜巡 /tmp/observer-alerts.json“可能已过时”警讯；feature flag QINGRUYAN_ANTI_DOGMA=off

const { spawn, execSync } = require("child_process");
const crypto = require("crypto");
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

// ═══════ P2.2 L1 检索层升级（异步 + TTL缓存 + 语义/BM25混合 + 多样性防锚定） ═══════
// feature flag: QINGRUYAN_PREFETCH_V2=off 退回 v6.2 同步路径
const PREFETCH_V2 = process.env.QINGRUYAN_PREFETCH_V2 !== "off";
const SANDGLASS_SOURCE = "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass_source";
const PREFETCH_CACHE_FILE = "/tmp/prefetch-cache.json";
const PREFETCH_CACHE_TTL = 24 * 3600 * 1000; // 24h：同 query 只查一次
const SHOUJI_SEARCH_URL = "http://shouji.tdx1146.cc/api/memory_search";
const SHOUJI_TIMEOUT = 3000;
const PREFETCH_CACHE = new Map(); // hash -> {result, fokSim, ts}

function md5(s) {
  return crypto.createHash("md5").update(String(s)).digest("hex");
}

function sanitizeQuery(query) {
  return (query || "")
    .replace(/[\r\n\t`"']/g, " ")
    .replace(/\\/g, " ")
    .replace(/\s+/g, " ")
    .substring(0, 100);
}

function prefetchCacheGet(hash) {
  const e = PREFETCH_CACHE.get(hash);
  if (!e) return null;
  if (Date.now() - e.ts > PREFETCH_CACHE_TTL) {
    PREFETCH_CACHE.delete(hash);
    return null;
  }
  return e;
}

function prefetchCacheSet(hash, result, fokSim) {
  PREFETCH_CACHE.set(hash, { result, fokSim: Number(fokSim || 0), ts: Date.now() });
  try {
    const obj = {};
    for (const [k, v] of PREFETCH_CACHE) obj[k] = v;
    fs.writeFileSync(PREFETCH_CACHE_FILE + ".tmp", JSON.stringify(obj));
    fs.renameSync(PREFETCH_CACHE_FILE + ".tmp", PREFETCH_CACHE_FILE); // 原子替换
  } catch (e) {}
}

function loadPrefetchCache() {
  try {
    if (fs.existsSync(PREFETCH_CACHE_FILE)) {
      const obj = JSON.parse(fs.readFileSync(PREFETCH_CACHE_FILE, "utf-8"));
      for (const [k, v] of Object.entries(obj)) {
        if (v && Date.now() - v.ts <= PREFETCH_CACHE_TTL) PREFETCH_CACHE.set(k, v);
      }
    }
  } catch (e) {}
}
loadPrefetchCache();

// 缓存命中时刷新 FOK 侧车，保证 P1.1 怀疑灯在二次命中时行为一致
function refreshFokSidecar(cleanQuery, sim) {
  try {
    fs.writeFileSync(DOUBT_FOK_FILE, JSON.stringify({ query: cleanQuery, sim: Number(sim || 0), ts: Date.now() / 1000 }));
  } catch (e) {}
}

function readFokSim() {
  try {
    if (fs.existsSync(DOUBT_FOK_FILE)) {
      const fok = JSON.parse(fs.readFileSync(DOUBT_FOK_FILE, "utf-8"));
      const sim = Number(fok.sim);
      return Number.isFinite(sim) ? sim : 0;
    }
  } catch (e) {}
  return 0;
}

// V2 内嵌 Python：块1搜索引导 + 状态块 + 候选JSON（取5条供多样性挑选）+ FOK旁路（与v6.2一致）
function buildPrefetchScriptV2(cleanQuery) {
  return `import sys, os, json
sys.path.insert(0, '.')
os.environ['NEXSANDBASE_HOME'] = '${SANDBASE_HOME}'

guide_parts = []

# 块1: 搜索引导
try:
    from sandglass_think import search_filter
    ctx = search_filter('${cleanQuery}') or {}
    if ctx.get('persona_context'):
        guide_parts.append('画像: ' + ctx['persona_context'][:30])
    if ctx.get('scene_context'):
        guide_parts.append('场景: ' + ctx['scene_context'][:30])
except: pass

# 状态块
status_parts = []
try:
    from sandglass_think import comprehensive_offset, _emotional_entropy
    off = comprehensive_offset()
    ent = _emotional_entropy()
    mood = '平稳' if ent < 0.5 else ('波动' if ent < 1.0 else '高熵')
    dirs = {'frugal': '省钱', 'spend': '愿投', 'drift': '放弃'}
    off_d = dirs.get(off.get('direction', ''), '平稳')
    status_parts.append(f'状态: {off_d}({off.get("offset",0):+d}%) | 🎭{mood}')
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

# 语义候选（沙漏 vault，取5条供JS侧多样性挑选）
candidates = []
try:
    from sandglass_vault import search
    candidates = [{"ln": ln, "ts": ts, "txt": txt} for ln, ts, txt, *_ in search('${cleanQuery}', limit=5)]
except: pass

# [L0怀疑灯·旁路] FOK相似度侧车：与 v6.2 完全一致，写 /tmp/doubt-fok.json 供JS侧读取
# 字符bigram Jaccard 近似嵌入相似度；失败/无结果则 sim=0（JS侧跳过）
try:
    import re as _fok_re, time as _fok_time

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
            _fok_f.write(json.dumps({'query': '${cleanQuery}', 'sim': round(_fok_sim, 4), 'ts': _fok_time.time()}))
    except Exception:
        pass
except Exception:
    pass

print('###GUIDE###')
if guide_parts:
    print('🔍 ' + ' | '.join(guide_parts))
print('###STATUS###')
if status_parts:
    print(chr(10).join(status_parts))
print('###CAND_JSON###')
print(json.dumps(candidates, ensure_ascii=False))
`;
}

// 异步 spawn 跑沙漏语义检索（不阻塞事件循环）
function runPrefetchPython(cleanQuery) {
  return new Promise((resolve) => {
    let py;
    try {
      py = spawn("python3", ["-u", "-c", buildPrefetchScriptV2(cleanQuery)], {
        cwd: SANDGLASS_SOURCE,
        env: { ...process.env, NEXSANDBASE_HOME: SANDBASE_HOME },
      });
    } catch (e) {
      writeAlert(`prefetch spawn error: ${e.message}`);
      resolve({ ok: false });
      return;
    }
    let stdout = "", stderr = "", timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      try { py.kill("SIGTERM"); } catch (e) {}
      writeAlert("prefetch timeout");
      resolve({ ok: false, err: "timeout" });
    }, PREFETCH_TIMEOUT);
    py.stdout.on("data", (d) => { stdout += d.toString(); });
    py.stderr.on("data", (d) => { stderr += d.toString(); });
    py.on("close", (code) => {
      clearTimeout(timer);
      if (timedOut) return;
      if (code === 0 && stdout.trim()) {
        resolve({ ok: true, out: stdout.trim() });
      } else {
        writeAlert(`prefetch failed: code=${code} stderr=${stderr.substring(0, 120)}`);
        resolve({ ok: false });
      }
    });
    py.on("error", (err) => {
      clearTimeout(timer);
      writeAlert(`prefetch error: ${err.message}`);
      resolve({ ok: false });
    });
  });
}

// shouji BM25 检索（HTTP，失败静默降级）
async function callShoujiMemorySearch(query, limit) {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), SHOUJI_TIMEOUT);
    try {
      const res = await fetch(SHOUJI_SEARCH_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit }),
        signal: ctrl.signal,
      });
      if (!res.ok) return [];
      const data = await res.json();
      return normalizeShoujiResults(data);
    } finally {
      clearTimeout(timer);
    }
  } catch (e) {
    return []; // 静默降级
  }
}

function normalizeShoujiResults(data) {
  try {
    let arr = data;
    if (Array.isArray(data)) arr = data;
    else if (data && Array.isArray(data.results)) arr = data.results;
    else if (data && Array.isArray(data.items)) arr = data.items;
    else if (data && Array.isArray(data.data)) arr = data.data;
    else return [];
    const out = [];
    for (const item of arr) {
      if (typeof item === "string") { out.push({ ln: "", ts: "", txt: item }); continue; }
      if (!item || typeof item !== "object") continue;
      const txt = item.snippet || item.text || item.content || item.summary || item.txt || "";
      if (!txt) continue;
      const file = String(item.file || item.path || "");
      const m = file.match(/(\d{4}-\d{2}-\d{2})/);
      const ts = item.ts || item.date || (m ? m[1] : "");
      out.push({ ln: item.line != null ? item.line : (item.id != null ? item.id : ""), ts: String(ts || ""), txt: String(txt) });
    }
    return out;
  } catch (e) { return []; }
}

function parsePrefetchOutput(out) {
  let guide = "", status = "", candidates = [];
  let section = null;
  const guideLines = [], statusLines = [], jsonLines = [];
  for (const line of String(out).split("\n")) {
    if (line === "###GUIDE###") { section = "guide"; continue; }
    if (line === "###STATUS###") { section = "status"; continue; }
    if (line === "###CAND_JSON###") { section = "cand"; continue; }
    if (section === "guide") guideLines.push(line);
    else if (section === "status") statusLines.push(line);
    else if (section === "cand") jsonLines.push(line);
  }
  guide = guideLines.join("\n").trim();
  status = statusLines.join("\n").trim();
  try {
    candidates = JSON.parse(jsonLines.join("\n"));
    if (!Array.isArray(candidates)) candidates = [];
  } catch (e) { candidates = []; }
  return { guide, status, candidates };
}

function tokenizeText(s) {
  const t = new Set();
  const str = String(s || "").toLowerCase();
  for (const m of str.matchAll(/[a-z0-9]+/g)) t.add(m[0]);
  const cjk = str.replace(/[^\u4e00-\u9fff]/g, "");
  for (let i = 0; i < cjk.length - 1; i++) t.add(cjk.substring(i, i + 2));
  return t;
}

function textSimilarity(a, b) {
  const ta = tokenizeText(a), tb = tokenizeText(b);
  if (!ta.size || !tb.size) return 0;
  let inter = 0;
  for (const x of ta) if (tb.has(x)) inter++;
  return inter / (ta.size + tb.size - inter);
}

// 合并去重：语义（沙漏）+ BM25（shouji）
function mergeCandidates(sandCands, shoujiCands) {
  const seen = new Set();
  const merged = [];
  for (const c of [...(sandCands || []), ...(shoujiCands || [])]) {
    const txt = String(c.txt || "");
    if (!txt) continue;
    const day = String(c.ts || "").substring(0, 10);
    const key = day + "|" + txt.substring(0, 40);
    if (seen.has(key)) continue;
    let dup = false;
    for (const m of merged) {
      if (textSimilarity(m.txt, txt) > 0.85) { dup = true; break; }
    }
    if (dup) continue;
    seen.add(key);
    merged.push(c);
  }
  return merged;
}

// 多样性检查（防锚定）：top3 尽量不同日期/不同话题；三轮放宽，尽力而为
function diversifyCandidates(merged, limit) {
  const L = limit || 3;
  if (merged.length <= L) return merged.slice(0, L);
  const picked = [];
  const dayOf = (c) => String(c.ts || "").substring(0, 10);
  const distinctTopic = (c) => picked.every((p) => textSimilarity(p.txt, c.txt) < 0.5);
  const distinctDay = (c) => picked.every((p) => dayOf(p) !== dayOf(c));
  for (const c of merged) { // 轮1：严格——不同日+不同话题
    if (picked.length >= L) break;
    if (distinctDay(c) && distinctTopic(c)) picked.push(c);
  }
  for (const c of merged) { // 轮2：放宽——仅不同话题
    if (picked.length >= L) break;
    if (picked.includes(c)) continue;
    if (distinctTopic(c)) picked.push(c);
  }
  for (const c of merged) { // 轮3：填空
    if (picked.length >= L) break;
    if (!picked.includes(c)) picked.push(c);
  }
  return picked;
}

// 保持现有注入格式：📋 相关记忆
function buildMemoryBlock(cands) {
  const lines = ["📋 相关记忆:"];
  for (const c of cands) {
    const short_ts = String(c.ts || "").substring(0, 10);
    const short_text = String(c.txt || "").replace(/\s+/g, " ").substring(0, 80);
    lines.push(`  [${short_ts}] ${short_text}`);
  }
  return lines.join("\n");
}

// 新 prefetch 主流程：TTL缓存 → 异步沙漏语义 + shouji BM25 → 合并去重 → 多样性 → 组装
async function getPrefetchBlock(query) {
  const cleanQuery = sanitizeQuery(query);
  if (!cleanQuery) return "";
  if (!PREFETCH_V2) return getPrefetchBlockV1(query); // 退回 v6.2 同步路径
  const hash = md5(cleanQuery);
  const cached = prefetchCacheGet(hash);
  if (cached) {
    refreshFokSidecar(cleanQuery, cached.fokSim);
    trackInjectedFromBlock(cached.result); // P3.3: 缓存命中也是注入，引用计数照记
    return cached.result; // 24h 内二次命中 0 延迟
  }
  const [pyRes, shoujiCands] = await Promise.all([
    runPrefetchPython(cleanQuery),
    callShoujiMemorySearch(cleanQuery, 3),
  ]);
  if (!pyRes.ok) {
    if (shoujiCands.length) {
      const block = buildMemoryBlock(diversifyCandidates(shoujiCands, 3));
      prefetchCacheSet(hash, block, 0);
      return block;
    }
    return "";
  }
  const { guide, status, candidates } = parsePrefetchOutput(pyRes.out);
  const fokSim = readFokSim();
  const merged = mergeCandidates(candidates, shoujiCands);
  // P3.2: 记忆信任度加权（relatedness × freshness_weight）——旧记忆/被推翻记忆降权
  const weighted = await applyTrustWeighting(merged);
  const top = diversifyCandidates(weighted, 3);
  // P3.3: 登记本次注入引用的记忆（反教条引用计数）
  trackInjectedMemories(top);
  const parts = [];
  if (guide) parts.push(guide);
  if (top.length) parts.push(buildMemoryBlock(top));
  if (status) parts.push(status);
  let result = parts.join("\n");
  if (result.length > 600) result = result.substring(0, 597) + "...";
  prefetchCacheSet(hash, result, fokSim);
  return result;
}

// ═══════ P2.1 L2 幽灵决策接线（决策场景→entropy_ghost，TTL 24h/主题） ═══════
// feature flag: QINGRUYAN_GHOST_DECISION=off 关闭；失败静默降级
const GHOST_FLAG = process.env.QINGRUYAN_GHOST_DECISION !== "off";
const GHOST_DECISION_FILE = "/tmp/ghost-decision-ttl.json";
const GHOST_TTL = 24 * 3600 * 1000;
const GHOST_MAX_PER_DAY = 5;
const GHOST_TIMEOUT = 6000;
const DECISION_STRONG_RE = /(要不要|该不该|选哪个|选什么|怎么选|该选|哪个好|抉择|犹豫|纠结|拿不准|权衡|方向|选择|定不下来|两条路|挑一个|哪个方案|哪个合适)/;
const DECISION_WEAK_RE = /(还是|决定|比较|更好|更合适|更划算)/;
const DECISION_ALT_RE = /([^，。？！,?!]{1,12})还是([^，。？！,?!]{1,12})/; // A还是B 二选一结构
const DECISION_BLOCK_RE = /(我还是|我们还是|他还是|她还是|还是算了|还是先|还是别|还是不要|还是想|还是去|还是回来|天气|吃饭|晚安|早安|拜拜|哈哈|嘻嘻|在吗|无所谓|困了|饿了|累死|开玩笑|随便说说)/;

// 主题归一化：提取“决策标记词+目标短语”，消除口语前缀差异（我在犹豫/我还在犹豫→同一主题）
function extractDecisionTopic(prompt) {
  const m = prompt.match(/(?:要不要|该不该|是否|选哪个|选什么|怎么选|哪个好|哪个方案|挑一个|两条路|还是)([^，。？！,?!]{1,20})/);
  if (m && m[1]) return "决策:" + m[1].replace(/[的了呢吗吧啊呀]+\s*$/, "");
  const m2 = prompt.match(/(?:犹豫|纠结|权衡|选择|方向)([^，。？！,?!]{1,20})/);
  if (m2 && m2[1]) return "决策:" + m2[1].replace(/[的了呢吗吧啊呀]+\s*$/, "");
  return prompt.replace(/\s+/g, " ").substring(0, 50);
}

// 决策场景检测：强词≥1（或强/弱合计≥2 或 A还是B结构）且非闲聊阻断词；返回 {topic} 或 null
function detectDecision(prompt) {
  if (!prompt || prompt.length < 4) return null;
  if (DECISION_BLOCK_RE.test(prompt)) return null;
  let score = 0;
  if (DECISION_STRONG_RE.test(prompt)) score += 2;
  if (DECISION_WEAK_RE.test(prompt)) score += 1;
  if (DECISION_ALT_RE.test(prompt)) score += 2; // A还是B 结构明确的二选一
  if (score < 2) return null;
  if (!/[？?]/.test(prompt) && prompt.length < 8) return null;
  return { topic: extractDecisionTopic(prompt) };
}

// TTL + 日频控：同主题 24h 内只触发一次，每日≤5次
function ghostDecisionTTL(topic) {
  const hash = md5(topic);
  let store = { entries: {}, day: "", count: 0 };
  try { store = JSON.parse(fs.readFileSync(GHOST_DECISION_FILE, "utf-8")); } catch (e) {}
  if (!store.entries) store.entries = {};
  const d = new Date();
  const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  if (store.day !== today) { store.day = today; store.count = 0; }
  const lastTs = store.entries[hash];
  if (lastTs && Date.now() - lastTs < GHOST_TTL) return false;
  if ((store.count || 0) >= GHOST_MAX_PER_DAY) return false;
  store.entries[hash] = Date.now();
  store.count = (store.count || 0) + 1;
  for (const k of Object.keys(store.entries)) {
    if (Date.now() - store.entries[k] > GHOST_TTL) delete store.entries[k];
  }
  try { fs.writeFileSync(GHOST_DECISION_FILE, JSON.stringify(store)); } catch (e) {}
  return true;
}

// 调沙漏源码幽灵决策函数（entropy_ghost，即 sandglass_dream 同一实现）
function runGhostDecision(topic) {
  return new Promise((resolve) => {
    const topicSafe = String(topic).replace(/[\r\n\t`"'\\]/g, " ").substring(0, 60);
    const script = `import sys, os, json
sys.path.insert(0, '.')
os.environ['NEXSANDBASE_HOME'] = '${SANDBASE_HOME}'
try:
    from emotion_l3 import entropy_ghost
    r = entropy_ghost('${topicSafe}')
    print(json.dumps(r, ensure_ascii=False))
except Exception as e:
    print(json.dumps({'error': str(e)}))
`;
    let py;
    try {
      py = spawn("python3", ["-u", "-c", script], {
        cwd: SANDGLASS_SOURCE,
        env: { ...process.env, NEXSANDBASE_HOME: SANDBASE_HOME },
      });
    } catch (e) {
      resolve("");
      return;
    }
    let stdout = "", timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      try { py.kill("SIGTERM"); } catch (e) {}
      resolve("");
    }, GHOST_TIMEOUT);
    py.stdout.on("data", (d) => { stdout += d.toString(); });
    py.on("close", () => {
      clearTimeout(timer);
      if (timedOut) return;
      try {
        const r = JSON.parse(stdout.trim());
        const inf = String(r.inference || "").trim();
        resolve(inf ? inf.substring(0, 60) : "");
      } catch (e) { resolve(""); }
    });
    py.on("error", () => { clearTimeout(timer); resolve(""); });
  });
}

// 决策场景 → 💭 幽灵视角 一行（简短反事实）；失败静默降级
async function maybeGhostDecision(prompt) {
  if (!GHOST_FLAG) return "";
  const dec = detectDecision(prompt);
  if (!dec) return "";
  if (!ghostDecisionTTL(dec.topic)) return "";
  const inference = await runGhostDecision(dec.topic);
  if (!inference) return "";
  return `💭 幽灵视角: ${inference}`;
}

// ═══════ P2.4 topic_risk.json（失败+2/夜巡+3/审查-1/日衰减0.5；≥4升级 ≥8强制） ═══════
// feature flag: QINGRUYAN_TOPIC_RISK=off 关闭注入提示；写入函数供其他模块调用（原子写+串行锁）
const RISK_FLAG = process.env.QINGRUYAN_TOPIC_RISK !== "off";
const TOPIC_RISK_FILE = "/tmp/topic_risk.json";
const TOPIC_RISK_UPGRADE = 4;
const TOPIC_RISK_FORCE = 8;
const TOPIC_DECAY_PER_DAY = 0.5;
let topicRiskWriteChain = Promise.resolve();

function defaultTopicRiskStore() {
  return { topics: {}, meta: { lastDecay: Date.now() } };
}

// 读取 + 懒衰减（0.5/天，衰减到0则移除）；衰减生效时持久化
function loadTopicRiskStore() {
  let store = defaultTopicRiskStore();
  try {
    if (fs.existsSync(TOPIC_RISK_FILE)) {
      store = JSON.parse(fs.readFileSync(TOPIC_RISK_FILE, "utf-8"));
    }
  } catch (e) {}
  if (!store.topics) store.topics = {};
  if (!store.meta) store.meta = {};
  const now = Date.now();
  const last = Number(store.meta.lastDecay || now);
  const days = Math.floor((now - last) / 86400000);
  if (days >= 1) {
    for (const t of Object.keys(store.topics)) {
      store.topics[t].score = Math.max(0, (Number(store.topics[t].score) || 0) - TOPIC_DECAY_PER_DAY * days);
      if (store.topics[t].score <= 0) delete store.topics[t];
    }
    store.meta.lastDecay = now;
    try {
      fs.writeFileSync(TOPIC_RISK_FILE + ".tmp", JSON.stringify(store));
      fs.renameSync(TOPIC_RISK_FILE + ".tmp", TOPIC_RISK_FILE);
    } catch (e) {}
  }
  return store;
}

function writeTopicRiskStoreSync(store) {
  const tmp = TOPIC_RISK_FILE + ".tmp." + process.pid;
  fs.writeFileSync(tmp, JSON.stringify(store, null, 2));
  fs.renameSync(tmp, TOPIC_RISK_FILE); // 原子替换
}

// 供其他模块调用的写接口（串行锁保证读-改-写原子性；返回 Promise<新分数>）
function updateTopicRisk(topic, delta) {
  const run = topicRiskWriteChain.then(() => {
    if (!topic) return null;
    const store = loadTopicRiskStore();
    const cur = store.topics[topic] || { score: 0, updated: Date.now() };
    cur.score = Math.max(0, Math.round((Number(cur.score || 0) + Number(delta || 0)) * 100) / 100);
    cur.updated = Date.now();
    if (cur.score <= 0) delete store.topics[topic];
    else store.topics[topic] = cur;
    writeTopicRiskStoreSync(store);
    return cur.score;
  });
  topicRiskWriteChain = run.catch(() => {});
  return run;
}

function readTopicRiskScores() {
  const store = loadTopicRiskStore();
  const out = {};
  for (const [t, v] of Object.entries(store.topics)) out[t] = Number(v.score) || 0;
  return out;
}

// 高风险主题（≥4）提示行；无则返回空串
function highRiskLine() {
  const scores = readTopicRiskScores();
  const high = Object.entries(scores)
    .filter(([t, s]) => s >= TOPIC_RISK_UPGRADE)
    .sort((a, b) => b[1] - a[1]);
  if (!high.length) return "";
  const names = high.map(([t, s]) => `${t}(${s})`).slice(0, 3).join("、");
  return `🚨 高风险主题: ${names}`;
}

// ═══════ P3.1 L3 子代理审查（高风险触发 → 注入提示 + 审查请求文件） ═══════
// feature flag: QINGRUYAN_L3_REVIEW=off 关闭
// 插件无 sessions_spawn 权限，只负责“提出审查需求”：注入区提示 + 原子写 /tmp/l3-review-request.json，
// 由主 AI 响应提示主动触发 sessions_spawn，或夜巡消费请求文件。
// 触发源：不可逆操作 / 金额承诺 / topic_risk≥4 连续失败 / 用户连续否定2次
// 去重：同一主题 1 小时内只写一次（原子写）
const L3_FLAG = process.env.QINGRUYAN_L3_REVIEW !== "off";
const L3_REVIEW_FILE = "/tmp/l3-review-request.json";
const L3_STATE_FILE = "/tmp/l3-review-state.json";
const L3_DEDUP_TTL = 3600 * 1000; // 同一主题 1h 去重
const L3_IRREVERSIBLE_RE = /(删除|删掉|删了|覆盖|覆写|迁移|搬家|发布|上线|部署|格式化|清空|重置|初始化|rm\s+-[a-z]+|drop\s+table|truncate\s+table|覆盖写入)/i;
const L3_MONEY_AMOUNT_RE = /(?:¥|￥|\$)\s*\d+|\d+(?:\.\d+)?\s*(?:元|块|万|千|美元|美金|欧元|日元|人民币)/;
const L3_MONEY_COMMIT_RE = /(答应|承诺|保证|说好|约好|付款|转账|还款|价格|报价)/;
const L3_NEGATION_RE = /(你错了|你说错了|你又说错了|不对|不是这样|不是这个|不是那么回事|你理解错了|理解错了|你搞错了|搞错了|你记错了|记错了|你弄错了|弄错了|说得不对|说反了|你根本没|打脸|翻车|更正|纠正)/;

// 主题键：去口语前缀/语气，取前30字（L3 去重、反教条日频控共用）
function deriveTopicKey(prompt) {
  let p = String(prompt || "").trim();
  p = p.replace(/^(姐姐|dandan|烟|小烟|那个|对了|还有|顺便|帮我|请|麻烦你|话说|我说|我想问|问一下|你)[，,：:\s]*/, "");
  p = p.replace(/[\r\n\t]+/g, " ").replace(/\s+/g, " ").trim();
  return p.substring(0, 30) || "(未知)";
}

// 同一主题 1 小时内只写一次；通过则记录并返回 true
function l3Dedup(topicKey) {
  const hash = md5(String(topicKey || ""));
  let state = { topics: {} };
  try {
    if (fs.existsSync(L3_STATE_FILE)) state = JSON.parse(fs.readFileSync(L3_STATE_FILE, "utf-8"));
  } catch (e) {}
  if (!state.topics) state.topics = {};
  const now = Date.now();
  if (state.topics[hash] && now - state.topics[hash] < L3_DEDUP_TTL) return false;
  state.topics[hash] = now;
  for (const k of Object.keys(state.topics)) {
    if (now - state.topics[k] > 24 * 3600 * 1000) delete state.topics[k];
  }
  try {
    fs.writeFileSync(L3_STATE_FILE + ".tmp", JSON.stringify(state));
    fs.renameSync(L3_STATE_FILE + ".tmp", L3_STATE_FILE);
  } catch (e) {}
  return true;
}

// 原子写审查请求文件（供主 AI / 夜巡消费）
function writeL3ReviewRequest(reason, topic, prompt) {
  const req = {
    time: new Date().toISOString(),
    reason,
    topic,
    context_preview: String(prompt || "").replace(/[\r\n\t]+/g, " ").substring(0, 120),
  };
  const tmp = L3_REVIEW_FILE + ".tmp." + process.pid;
  fs.writeFileSync(tmp, JSON.stringify(req, null, 2));
  fs.renameSync(tmp, L3_REVIEW_FILE); // 原子替换
  return req;
}

// 用户连续否定检测：当前 prompt + 最近一条用户消息均为否定 → ≥2 次
function countConsecutiveNegations(prompt, messages) {
  let n = 0;
  try { if (L3_NEGATION_RE.test(prompt)) n = 1; } catch (e) {}
  if (Array.isArray(messages)) {
    for (let i = messages.length - 1; i >= 0 && n < 2; i--) {
      const m = messages[i];
      if (!m || m.role !== "user") continue;
      let c = "";
      if (typeof m.content === "string") c = m.content;
      else if (Array.isArray(m.content)) c = m.content.map((p) => (p && p.text) || "").join(" ");
      if (c && c === prompt) continue; // 当前消息已在上方计过
      if (L3_NEGATION_RE.test(c)) n++;
      else break; // 最近一条用户消息非否定 → 断链
    }
  }
  return n;
}

// 高风险检测：返回 {reason, topic} 或 null
function detectL3Review(prompt, messages) {
  const reasons = [];
  let topic = deriveTopicKey(prompt);
  try { if (L3_IRREVERSIBLE_RE.test(prompt)) reasons.push("检测到不可逆操作词（删除/覆盖/迁移/发布等）"); } catch (e) {}
  try {
    if (L3_MONEY_AMOUNT_RE.test(prompt) && L3_MONEY_COMMIT_RE.test(prompt)) reasons.push("涉及金额承诺");
  } catch (e) {}
  try { if (countConsecutiveNegations(prompt, messages) >= 2) reasons.push("用户连续否定2次"); } catch (e) {}
  try {
    const scores = readTopicRiskScores();
    const pTokens = tokenizeText(prompt);
    for (const [t, s] of Object.entries(scores)) {
      if (s < TOPIC_RISK_UPGRADE) continue;
      // 同主题连续失败：仅当当前 prompt 与风险主题相关才触发（避免无关话题也被牵连）
      const tTokens = tokenizeText(t);
      let inter = 0;
      for (const x of tTokens) if (pTokens.has(x)) inter++;
      const overlap = tTokens.size ? inter / tTokens.size : 0;
      if (prompt.includes(t) || overlap >= 0.34) {
        reasons.push(`主题「${t}」风险分${s}≥${TOPIC_RISK_UPGRADE}（连续失败）`);
        topic = t; // 去重按风险主题名
        break;
      }
    }
  } catch (e) {}
  if (!reasons.length) return null;
  return { reason: reasons.join("；"), topic };
}

// 返回注入行（命中且去重通过）；同时原子写请求文件
function l3ReviewLine(prompt, messages) {
  if (!L3_FLAG) return "";
  try {
    const hit = detectL3Review(prompt, messages);
    if (!hit) return "";
    if (!l3Dedup(hit.topic)) return ""; // 同一主题 1h 内只提示/写一次
    writeL3ReviewRequest(hit.reason, hit.topic, prompt);
    return `🚨 建议审查: ${hit.reason}`;
  } catch (e) {
    writeAlert(`l3 review error: ${e.message}`);
    return "";
  }
}

// ═══════ P3.2 记忆信任度注入加权（relatedness × freshness_weight） ═══════
// feature flag: QINGRUYAN_MEMORY_TRUST=off 关闭
// 数据层接口就绪（/tmp/memory-trust.json 含 rebuttal_count/reference_count）→ 用真实公式
//   freshness_weight = 1/(1+age_days) × (1 - 反驳率)，反驳率 = rebuttal_count/(reference_count+1)
// 未就绪 → 保守降级：年龄分桶（7天1.0/30天0.7/90天0.4/更久0.2）× (1 - doubt.db 反驳近似/2)
// 被推翻 ≥2 次 → 权重压到 0.1（防回声室）；注入格式不变（📋 相关记忆 3条）
const TRUST_FLAG = process.env.QINGRUYAN_MEMORY_TRUST !== "off";
const TRUST_FILE = "/tmp/memory-trust.json";
const DOUBT_DB_PATH = "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass/doubt.db";
const TRUST_OVERTURN_MIN = 2;
const TRUST_FLOOR = 0.1;
const TRUST_CACHE_TTL = 3600 * 1000;
const TRUST_FUZZY_MAX_KEYS = 300; // 模糊匹配上限，防止超大信任表拖慢注入
let trustCache = { ts: 0, data: null, source: "none" };

// 记忆日期 → 年龄（天）
function memoryAgeDays(ts) {
  if (!ts) return 0;
  const t = Date.parse(String(ts).substring(0, 10));
  if (Number.isNaN(t)) return 0;
  return Math.max(0, (Date.now() - t) / 86400000);
}

// 降级年龄分桶权重
function degradationWeight(ageDays) {
  if (ageDays <= 7) return 1.0;
  if (ageDays <= 30) return 0.7;
  if (ageDays <= 90) return 0.4;
  return 0.2;
}

// 候选记忆指纹（ln 优先，否则 日期+文本前缀）
function memoryFingerprint(cand) {
  if (cand && cand.ln && String(cand.ln).trim()) return "ln:" + String(cand.ln).trim();
  const txt = String((cand && cand.txt) || "");
  return "tx:" + md5(String((cand && cand.ts) || "").substring(0, 10) + "|" + txt.substring(0, 60));
}

// 真实数据层：/tmp/memory-trust.json（{memories|entries: {指纹或ln: {rebuttal_count, reference_count, ...}}}）
function readTrustFile() {
  try {
    if (!fs.existsSync(TRUST_FILE)) return null;
    const raw = JSON.parse(fs.readFileSync(TRUST_FILE, "utf-8"));
    const mems = (raw && (raw.memories || raw.entries)) || raw;
    if (mems && typeof mems === "object" && !Array.isArray(mems)) return { source: "file", data: mems };
  } catch (e) {}
  return null;
}

// 降级数据源：doubt.db answer_changed=true 按 topic 计数（异步 spawn + 1h 缓存，失败静默降级）
function queryDoubtRebuttals() {
  return new Promise((resolve) => {
    if (!fs.existsSync(DOUBT_DB_PATH)) { resolve({ source: "none", data: {} }); return; }
    const script = `import sqlite3, json
db = '${DOUBT_DB_PATH}'
out = {}
try:
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT topic, COUNT(*) FROM doubt_episode WHERE answer_changed=1 GROUP BY topic")
    for t, c in cur.fetchall():
        if t: out[str(t)] = int(c)
    conn.close()
except Exception:
    pass
print(json.dumps(out))
`;
    let py;
    try {
      py = spawn("python3", ["-c", script], { stdio: ["ignore", "pipe", "ignore"] });
    } catch (e) { resolve({ source: "none", data: {} }); return; }
    let stdout = "", timedOut = false;
    const timer = setTimeout(() => { timedOut = true; try { py.kill("SIGTERM"); } catch (e) {} resolve({ source: "none", data: {} }); }, 3000);
    py.stdout.on("data", (d) => { stdout += d.toString(); });
    py.on("close", () => {
      clearTimeout(timer);
      if (timedOut) return;
      try { resolve({ source: "doubtdb", data: JSON.parse(stdout.trim()) }); }
      catch (e) { resolve({ source: "none", data: {} }); }
    });
    py.on("error", () => { clearTimeout(timer); resolve({ source: "none", data: {} }); });
  });
}

// 信任数据（file 优先，doubt.db 兜底；1h 缓存）
async function readTrustData() {
  if (trustCache.data && Date.now() - trustCache.ts < TRUST_CACHE_TTL) return trustCache;
  const fileData = readTrustFile();
  if (fileData) { trustCache = { ts: Date.now(), ...fileData }; return trustCache; }
  const dbData = await queryDoubtRebuttals();
  trustCache = { ts: Date.now(), ...dbData };
  return trustCache;
}

// 候选记忆 → 对应信任条目（指纹/ln 精确优先，文本模糊兜底）
function matchTrustEntry(cand, trustData) {
  if (!trustData || typeof trustData !== "object") return null;
  const fp = memoryFingerprint(cand);
  if (trustData[fp]) return trustData[fp];
  if (cand && cand.ln && trustData[String(cand.ln)]) return trustData[String(cand.ln)];
  const txt = String((cand && cand.txt) || "");
  if (!txt) return null;
  let best = null, bestSim = 0.2;
  const keys = Object.keys(trustData);
  if (keys.length > TRUST_FUZZY_MAX_KEYS) return null;
  for (const k of keys) {
    const v = trustData[k];
    if (!v || typeof v !== "object") continue;
    const sim = textSimilarity(txt, String(k));
    if (sim > bestSim) { bestSim = sim; best = v; }
  }
  return best;
}

// 单条记忆信任权重
function computeTrustWeight(cand, trust) {
  const age = memoryAgeDays(cand && cand.ts);
  const entry = matchTrustEntry(cand, trust.data);
  const rebuttals = Math.max(0, Number((entry && (entry.rebuttal_count ?? entry.rebuttals ?? entry.overturn_count)) || 0));
  let w;
  if (trust.source === "file") {
    const refs = Math.max(1, Number((entry && (entry.reference_count ?? entry.refs ?? entry.references)) || 1));
    w = (1 / (1 + age)) * (1 - rebuttals / (refs + 1)); // 数据层公式
  } else {
    w = degradationWeight(age) * (1 - rebuttals / 2);   // 降级：年龄分桶 × (1-反驳率近似, refs≈1)
  }
  if (rebuttals >= TRUST_OVERTURN_MIN) w = Math.min(w, TRUST_FLOOR); // 被推翻≥2次 → 0.1
  return Math.max(0, w);
}

// 加权排序：relatedness(检索位置) × freshness_weight；任何异常原序返回
async function applyTrustWeighting(candidates) {
  if (!TRUST_FLAG || !Array.isArray(candidates) || candidates.length < 2) return candidates;
  let trust;
  try { trust = await readTrustData(); } catch (e) { return candidates; }
  const scored = candidates.map((c, idx) => ({
    c,
    score: (1 / (idx + 1)) * computeTrustWeight(c, trust), // 检索返回顺序即相关度
  }));
  scored.sort((a, b) => b.score - a.score);
  return scored.map((s) => s.c);
}

// ═══════ P3.3 反教条提示（高引用旧记忆复核 + 夜巡 observer-alerts 匹配） ═══════
// feature flag: QINGRUYAN_ANTI_DOGMA=off 关闭
// 记忆在最近注入中被引用 ≥3 次 且 记忆年龄 >30 天 → ⚠️ 复核提示
// 或夜巡 /tmp/observer-alerts.json 产出“可能已过时”警讯且 topic 匹配 → 同样提示
// 低频：每天同一 topic 最多 1 次；全局每日 ≤3 次兜底
const DOGMA_FLAG = process.env.QINGRUYAN_ANTI_DOGMA !== "off";
const DOGMA_REFS_FILE = "/tmp/anti-dogma-refs.json";
const DOGMA_OBSERVER_FILE = "/tmp/observer-alerts.json";
const DOGMA_REF_MIN = 3;
const DOGMA_AGE_DAYS = 30;
const DOGMA_DAILY_MAX = 3; // 全局每日兜底（防刷屏）
const DOGMA_STALE_KEYWORDS = ["过时", "已过时", "可能已过时", "stale"];

function defaultDogmaRefs() { return { refs: {}, nudges: {}, daily: {} }; }

function loadDogmaRefs() {
  let s = defaultDogmaRefs();
  try {
    if (fs.existsSync(DOGMA_REFS_FILE)) s = JSON.parse(fs.readFileSync(DOGMA_REFS_FILE, "utf-8"));
  } catch (e) {}
  if (!s.refs || typeof s.refs !== "object") s.refs = {};
  if (!s.nudges || typeof s.nudges !== "object") s.nudges = {};
  if (!s.daily || typeof s.daily !== "object") s.daily = {};
  return s;
}

function saveDogmaRefs(s) {
  try {
    fs.writeFileSync(DOGMA_REFS_FILE + ".tmp", JSON.stringify(s));
    fs.renameSync(DOGMA_REFS_FILE + ".tmp", DOGMA_REFS_FILE);
  } catch (e) {}
}

// 每次注入后登记被引用的记忆（引用计数；30天未再引用则清理）
function trackInjectedMemories(cands) {
  if (!DOGMA_FLAG || !Array.isArray(cands) || !cands.length) return;
  try {
    const s = loadDogmaRefs();
    const now = Date.now();
    for (const c of cands) {
      const fp = memoryFingerprint(c);
      const e = s.refs[fp] || {
        count: 0,
        firstTs: now,
        lastTs: now,
        memTs: String((c && c.ts) || "").substring(0, 10),
        summary: String((c && c.txt) || "").replace(/\s+/g, " ").substring(0, 60),
      };
      e.count = (Number(e.count) || 0) + 1;
      e.lastTs = now;
      s.refs[fp] = e;
    }
    for (const k of Object.keys(s.refs)) {
      if (now - s.refs[k].lastTs > 30 * 86400000) delete s.refs[k];
    }
    saveDogmaRefs(s);
  } catch (e) {}
}

// TTL 缓存命中也是注入，从注入块解析记忆行登记引用
function trackInjectedFromBlock(block) {
  if (!DOGMA_FLAG || !block) return;
  try {
    const cands = [];
    for (const line of String(block).split("\n")) {
      const m = line.match(/^\s*\[(\d{4}-\d{2}-\d{2}[^\]]*)\]\s+(.+)$/);
      if (m) cands.push({ ts: m[1].trim(), txt: m[2] });
    }
    if (cands.length) trackInjectedMemories(cands);
  } catch (e) {}
}

function todayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// 夜巡 observer-alerts.json：topic 与当前 prompt 匹配 且 含“过时”类警讯
function matchObserverStaleAlert(prompt) {
  try {
    if (!fs.existsSync(DOGMA_OBSERVER_FILE)) return null;
    const arr = JSON.parse(fs.readFileSync(DOGMA_OBSERVER_FILE, "utf-8"));
    if (!Array.isArray(arr)) return null;
    const pTokens = tokenizeText(prompt);
    for (const a of arr) {
      const topic = String((a && a.topic) || "");
      if (!topic) continue;
      const tTokens = tokenizeText(topic);
      let inter = 0;
      for (const x of tTokens) if (pTokens.has(x)) inter++;
      const overlap = tTokens.size ? inter / tTokens.size : 0;
      const blob = String((a && (a.suggestion || a.evidence || a.tag)) || "") + " " + topic;
      const stale = DOGMA_STALE_KEYWORDS.some((k) => blob.includes(k));
      if (stale && (prompt.includes(topic) || overlap >= 0.34)) {
        return { summary: topic };
      }
    }
  } catch (e) {}
  return null;
}

// 返回复核提示行（低频：每天每 topic 1 次 + 全局每日 ≤3 次）
function antiDogmaLine(prompt) {
  if (!DOGMA_FLAG || !prompt) return "";
  try {
    const topicKey = deriveTopicKey(prompt);
    const s = loadDogmaRefs();
    const now = Date.now();
    const today = todayKey();
    if (s.daily[today] && s.daily[today] >= DOGMA_DAILY_MAX) return ""; // 全局兜底
    const nudgeKey = md5(topicKey);
    if (s.nudges[nudgeKey] === today) return ""; // 同一 topic 每天最多 1 次

    let candidate = null;
    for (const [fp, e] of Object.entries(s.refs)) {
      if (!e) continue;
      if (Number(e.count) >= DOGMA_REF_MIN && memoryAgeDays(e.memTs) > DOGMA_AGE_DAYS) {
        if (!candidate || Number(e.count) > Number(candidate.count)) candidate = e;
      }
    }
    const obs = matchObserverStaleAlert(prompt);
    if (obs) candidate = { summary: obs.summary, obs: true }; // 夜巡警讯优先（证据更强）
    if (!candidate) return "";

    s.nudges[nudgeKey] = today;
    s.daily[today] = (s.daily[today] || 0) + 1;
    // 清理：nudges 保留 7 天，daily 保留 2 天
    for (const k of Object.keys(s.nudges)) {
      const d = s.nudges[k];
      if (typeof d !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(d)) { delete s.nudges[k]; continue; }
      const dt = Date.parse(d);
      if (!Number.isNaN(dt) && now - dt > 7 * 86400000) delete s.nudges[k];
    }
    for (const k of Object.keys(s.daily)) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(k)) { delete s.daily[k]; continue; }
      const dt = Date.parse(k);
      if (!Number.isNaN(dt) && now - dt > 2 * 86400000) delete s.daily[k];
    }
    saveDogmaRefs(s);
    return `⚠️ 复核提示: 这条记忆已过时? ${String(candidate.summary || "").substring(0, 50)}`;
  } catch (e) {
    writeAlert(`anti-dogma error: ${e.message}`);
    return "";
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

// ═══════ 每轮注入（prefetch v6.2 同步路径，P2.2 降级用） ═══════
// 三块式：搜索引导 / 记忆候选 / 当前状态
// query必须清理换行+截断，避免Python字符串字面量断裂
// 仅在 QINGRUYAN_PREFETCH_V2=off 时使用（execSync 同步，保持 v6.2 原行为）

function getPrefetchBlockV1(query) {
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
  // P2.4: topic_risk 写入接口（供其他模块调用；文件 /tmp/topic_risk.json，原子写+串行锁）
  topicRisk: {
    file: TOPIC_RISK_FILE,
    update: updateTopicRisk,
    get: readTopicRiskScores,
    read: readTopicRiskScores,
    highRiskLine,
  },
  // P3.1: L3 审查请求文件（主 AI / 夜巡消费；原子写）
  l3Review: {
    file: L3_REVIEW_FILE,
    request: writeL3ReviewRequest,
  },
  // P3.2: 记忆信任加权（数据层就绪用真实数据，否则降级）
  trust: {
    file: TRUST_FILE,
    applyWeighting: applyTrustWeighting,
  },
  // P3.3: 反教条引用账本文件
  antiDogma: {
    refsFile: DOGMA_REFS_FILE,
  },
  // 测试钩子：纯函数，供端到端/单元验证（不改变运行行为）
  _test: {
    deriveTopicKey,
    detectL3Review,
    l3ReviewLine,
    countConsecutiveNegations,
    memoryAgeDays,
    degradationWeight,
    computeTrustWeight,
    applyTrustWeighting,
    antiDogmaLine,
    trackInjectedMemories,
  },
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

        // === Part 2: prefetch（P2.2：异步+TTL缓存+语义/BM25混合+多样性） ===
        let prefetchBlock = "";
        const prefetchStartedAt = Date.now(); // 供 FOK 侧车新鲜度校验
        try {
          prefetchBlock = await getPrefetchBlock(prompt);
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

        // === Part 3b: P2.4 高风险主题（topic_risk.json ≥4 升级阈值） ===
        let riskLine = "";
        if (RISK_FLAG) {
          try { riskLine = highRiskLine(); } catch(e) { writeAlert(`topic_risk read error: ${e.message}`); }
        }
        if (riskLine) parts.push(riskLine);

        // === Part 3c: P2.1 幽灵决策（决策场景→entropy_ghost，TTL 24h/主题、日≤5次） ===
        let ghostLine = "";
        try { ghostLine = await maybeGhostDecision(prompt); } catch(e) { writeAlert(`ghost decision error: ${e.message}`); }
        if (ghostLine) parts.push(ghostLine);

        // === Part 3d: P3.1 L3 审查请求（高风险触发 → 🚨 建议审查 + /tmp/l3-review-request.json） ===
        let l3Line = "";
        try { l3Line = l3ReviewLine(prompt, event.messages); } catch(e) { writeAlert(`l3 review error: ${e.message}`); }
        if (l3Line) parts.push(l3Line);

        // === Part 3e: P3.3 反教条复核提示（高引用旧记忆/夜巡警讯，每天每topic≤1次） ===
        let dogmaLine = "";
        try { dogmaLine = antiDogmaLine(prompt); } catch(e) { writeAlert(`anti-dogma error: ${e.message}`); }
        if (dogmaLine) parts.push(dogmaLine);

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
          const detail = `系统块: ${systemBlock ? "✅" : "❌"} | 预搜块: ${prefetchBlock ? "✅" : "❌"} | 报警: ${alert ? "⚠️" : "无"} | 怀疑灯: ${doubtLine ? "💡" : "—"} | 幽灵: ${ghostLine ? "👻" : "—"} | 风险: ${riskLine ? "🚨" : "—"} | 审查: ${l3Line ? "🛡️" : "—"} | 复核: ${dogmaLine ? "🔁" : "—"}`;
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
