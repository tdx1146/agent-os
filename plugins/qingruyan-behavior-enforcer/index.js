// 轻如烟 · 沙漏注入插件 v6
// 2026-07-26：消费侧闭环——沙漏成为唯一注入源
//
// 工作机制：
// 1. system_prompt_block() — 会话启动时四层注入（你是谁/往哪走/怎么变/没做完）
// 2. prefetch(query) — 每轮注入三块式（搜索引导/记忆候选/当前状态）
// 3. 降级检测——CLI失败时写报警文件
//
// OpenClaw contextInjection=never，workspace文件不自动注入
// AI要任何信息必须通过沙漏工具

const { spawn, execSync } = require("child_process");
const fs = require("fs");

const SANDGLASS_CLI = "/vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source/system_prompt_cli.py";
const SANDBASE_HOME = "/vol2/1000/AI专用/所有自动化/轻如烟/sandglass";
const CLI_TIMEOUT = 10000;
const PREFETCH_TIMEOUT = 8000;
const ALERT_FILE = "/tmp/sandglass-injection-alert.txt";
const DEBUG_DIR = "/tmp";

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
// 按沙漏官方turn_injection_plan.md的三块式设计
// 块1: 搜索引导（关键词扩展+影子沙标签）
// 块2: 记忆候选（预搜TOP3）
// 块3: 当前状态+决策

function getPrefetchBlock(query) {
  try {
    const escapedQuery = query.replace(/'/g, "\\'").replace(/"/g, '\\"').substring(0, 200);
    const cmd = `cd /vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source && NEXSANDBASE_HOME="${SANDBASE_HOME}" python3 -u -c "
import sys, os
sys.path.insert(0, '.')
os.environ['NEXSANDBASE_HOME'] = '${SANDBASE_HOME}'

blocks = []

# ═══════ 块1: 搜索引导 ═══════
try:
    from sandglass_think import search_filter, _infer_expand_with_context
    sf = search_filter('${escapedQuery}')
    ctx = sf or {}
    expanded = _infer_expand_with_context(
        '${escapedQuery}',
        ctx.get('persona_context', ''),
        ctx.get('scene_context', ''),
        ctx.get('stage_context', ''),
        ctx.get('dp_context', ''),
        ctx.get('decision_bias', '')
    )
    guide_parts = []
    if expanded and len(expanded) > 1:
        guide_parts.append('搜索: ' + ' / '.join(expanded[1:4]))
    
    # 影子沙标签
    try:
        from shadow_sand import shadow_search
        import sqlite3
        sh = shadow_search('${escapedQuery}', 3)
        if sh:
            db = sqlite3.connect(os.path.join('${SANDBASE_HOME}', 'shadow_sand.db'))
            tags_set = set()
            for _, ln in sh[:3]:
                row = db.execute('SELECT category, tags FROM fact_tags WHERE line_num=?', (ln,)).fetchone()
                if row:
                    if row[0] and row[0] != 'general': tags_set.add(row[0][:15])
                    if row[1]:
                        for t in row[1].split(',')[:2]:
                            t = t.strip()
                            if len(t) > 1: tags_set.add(t[:15])
            db.close()
            if tags_set:
                guide_parts.append('标签: ' + ', '.join(list(tags_set)[:4]))
    except: pass
    
    if guide_parts:
        blocks.append('🔍 ' + ' | '.join(guide_parts))
except: pass

# ═══════ 块2: 记忆候选（预搜TOP3） ═══════
try:
    from sandglass_vault import search
    results = search('${escapedQuery}', limit=3)
    if results:
        mem_lines = ['📋 相关记忆:']
        for ln, ts, txt, *_ in results[:3]:
            short_ts = ts[:10] if len(ts) >= 10 else ts
            short_text = txt[:80].replace(chr(10), ' ')
            mem_lines.append(f'  [{short_ts}] {short_text}')
        blocks.append(chr(10).join(mem_lines))
except: pass

# ═══════ 块3: 当前状态+决策 ═══════
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
      // 5分钟内的报警才报
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

        // === Part 1: 四层注入（system_prompt_block） ===
        let systemBlock = "";
        try {
          systemBlock = await getSystemPromptBlock();
        } catch(e) {
          writeAlert(`system_block await error: ${e.message}`);
        }

        // === Part 2: 每轮注入（prefetch） ===
        let prefetchBlock = "";
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

        // 如果沙漏完全失败，给最低限度的身份锚点
        if (!systemBlock && !prefetchBlock) {
          parts.push("## 🆘 沙漏系统离线\n\n你是轻如烟，dandan的AI。沙漏记忆系统当前不可用，请通知dandan。");
        }

        const injectionContent = parts.join("\n\n");

        // 调试日志
        try {
          fs.writeFileSync("/tmp/plugin-injected.txt", new Date().toISOString());
          const detail = `系统块: ${systemBlock ? "✅" : "❌"} | 预搜块: ${prefetchBlock ? "✅" : "❌"} | 报警: ${alert ? "⚠️" : "无"}`;
          fs.writeFileSync("/tmp/last-injection.txt", `${new Date().toISOString()} | ${detail}`);
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
