// 轻如烟 · 行为强制插件 v4
// 2026-07-26：v3 + 沙漏四层自动注入
//
// 工作机制：
// 1. 调用沙漏 system_prompt_cli.py 获取四层自动注入（你是谁/往哪走/怎么变/没做完）
// 2. 从 facts.dict.md 尾部自动匹配断言
// 3. 检测 prompt 关键词 → 注入搜索触发指令
//
// 核心改变：沙漏的自动注入替代了手动触发词，AI每轮都能看到动态蒸馏的画像/偏移/因果链

const { spawn } = require("child_process");
const fs = require("fs");

const FACTS_PATH = "/vol1/@apphome/trim.openclaw/data/workspace/facts.dict.md";
const SANDGLASS_CLI = "/vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source/system_prompt_cli.py";
const SANDBASE_HOME = "/vol2/1000/AI专用/所有自动化/轻如烟/sandglass";
const MAX_MATCHED = 5;
const CLI_TIMEOUT = 10000; // 10秒超时

// 搜索触发规则（保留，作为沙漏注入的补充）
const SEARCH_TRIGGERS = [
  {
    patterns: [/丰碑|monument|元丰碑|yfb/i],
    tool: "sandglass__sandglass_search",
    query: "丰碑 monument 进展",
    hint: "prompt提到丰碑系统，建议先搜索相关记忆再回答"
  },
  {
    patterns: [/为什么|根因|原因|导致/i],
    tool: "sandglass__sandglass_thread",
    query: null,
    hint: "prompt涉及因果分析，建议查询知识图谱"
  },
  {
    patterns: [/回忆|记得|今天几号|发生了什么|什么时候/i],
    tool: "sandglass__sandglass_search",
    query: null,
    hint: "prompt涉及记忆查询，建议搜索历史记忆"
  },
  {
    patterns: [/配置|openclaw|plugin|cron|插件/i],
    tool: "sandglass__sandglass_search",
    query: "配置 系统 历史",
    hint: "prompt涉及系统配置，建议搜索相关历史"
  },
  {
    patterns: [/报错|错误|失败|崩溃|挂了/i],
    tool: "sandglass__sandglass_search",
    query: "错误 失败",
    hint: "prompt提到错误/失败，建议搜索历史记忆"
  },
  {
    patterns: [/继续|接着|然后|再说$/],
    shortPromptOnly: true,
    tool: "sandglass__sandglass_search",
    query: "最近 任务 讨论",
    hint: "短指令，建议搜索最近上下文恢复对话连续性"
  }
];

// ═══════ 沙漏四层注入 ═══════

function getSandglassBlock() {
  return new Promise((resolve) => {
    const py = spawn("python3", [SANDGLASS_CLI], {
      env: { ...process.env, NEXSANDBASE_HOME: SANDBASE_HOME },
    });

    let stdout = "";
    let stderr = "";
    let timedOut = false;

    // 手动超时保护（spawn不支持timeout选项）
    const timer = setTimeout(() => {
      timedOut = true;
      py.kill("SIGTERM");
      try { fs.writeFileSync("/tmp/sandglass-cli-error.txt", `${new Date().toISOString()} timeout=${CLI_TIMEOUT}ms`); } catch(e) {}
      resolve("");
    }, CLI_TIMEOUT);

    py.stdout.on("data", (data) => { stdout += data.toString(); });
    py.stderr.on("data", (data) => { stderr += data.toString(); });

    py.on("close", (code) => {
      clearTimeout(timer);
      if (timedOut) return;
      try { fs.writeFileSync("/tmp/sandglass-cli-debug.txt", `${new Date().toISOString()} code=${code} stdout_len=${stdout.length} stderr_len=${stderr.length} stdout=${stdout.substring(0,300)} stderr=${stderr.substring(0,300)}`); } catch(e) {}
      if (code === 0 && stdout.trim()) {
        resolve(stdout.trim());
      } else {
        try { fs.writeFileSync("/tmp/sandglass-cli-error.txt", `${new Date().toISOString()} code=${code} stderr=${stderr.substring(0, 200)}`); } catch(e) {}
        resolve("");
      }
    });

    py.on("error", (err) => {
      clearTimeout(timer);
      try { fs.writeFileSync("/tmp/sandglass-cli-error.txt", `${new Date().toISOString()} error=${err.message}`); } catch(e) {}
      resolve("");
    });

    // 关闭stdin，避免子进程等待输入
    py.stdin.end();
  });
}

// ═══════ 断言匹配 ═══════

function extractKeywords(text) {
  const head = text.slice(0, 80).toLowerCase();
  const words = [];
  const cn = head.match(/[\u4e00-\u9fff]{2,4}/g);
  if (cn) words.push(...cn);
  const en = head.match(/[a-z][a-z0-9]+/g);
  if (en) words.push(...en);
  const num = head.match(/\d{2,}/g);
  if (num) words.push(...num);
  return [...new Set(words)];
}

function matchFactsFromAll(prompt, lines) {
  const promptLower = prompt.toLowerCase();
  const matched = [];
  const seen = new Set();

  function tryMatch(line) {
    const m = line.match(/^\|\s*(\w+\d+)\s*\|\s*(.+?)\s*\|\s*✅/);
    if (!m) return;
    const id = m[1];
    if (seen.has(id)) return;
    const text = m[2].trim();
    const keywords = extractKeywords(text);
    if (keywords.some(kw => promptLower.includes(kw))) {
      seen.add(id);
      matched.push({ id, text });
    }
  }

  // 头部断言 (H/W系列 — 核心知识)
  for (let i = 0; i < Math.min(80, lines.length); i++) {
    tryMatch(lines[i]);
    if (matched.length >= MAX_MATCHED) return matched;
  }

  // 尾部断言 (F/META系列 — 最近记忆)
  for (let i = lines.length - 1; i >= Math.max(80, lines.length - 200); i--) {
    tryMatch(lines[i]);
    if (matched.length >= MAX_MATCHED) return matched;
  }

  return matched;
}

// ═══════ 搜索触发 ═══════

function extractPromptNouns(prompt) {
  const cn = prompt.match(/[\u4e00-\u9fff]{2,4}/g);
  if (cn && cn.length >= 2) return cn.slice(-2).join(" ");
  if (cn && cn.length === 1) return cn[0];
  const en = prompt.match(/[a-z][a-z0-9]{2,}/gi);
  if (en && en.length >= 1) return en.slice(-1)[0];
  return "最近记忆";
}

function detectSearchTriggers(prompt) {
  const triggers = [];
  const isShort = prompt.trim().length < 30;
  for (const t of SEARCH_TRIGGERS) {
    if (t.shortPromptOnly && !isShort) continue;
    if (t.patterns.some(p => p.test(prompt))) {
      const query = t.query || extractPromptNouns(prompt);
      triggers.push({ tool: t.tool, query, hint: t.hint });
    }
  }
  return triggers;
}

// ═══════ 主逻辑 ═══════

module.exports = {
  id: "qingruyan-behavior-enforcer",
  name: "轻如烟行为强制",
  register(api) {
    api.on(
      "before_prompt_build",
      async (event) => {
        try { fs.writeFileSync("/tmp/plugin-ran.txt", new Date().toISOString()); } catch(e) {}

        const prompt = event.prompt || "";
        const isSilentPeriod = prompt.includes('轮感检查') && prompt.includes('静默期');

        let injectionContent = "";
        let matched = [];
        let triggers = [];
        let sandglassBlock = "";

        if (isSilentPeriod) {
          try { fs.writeFileSync("/tmp/last-processing.txt", "静默期 " + new Date().toISOString()); } catch(e) {}
          injectionContent = "## 🌙 静默期\n\n不需要输出。不需要汇报。想问题。\n\n想想最近几条断言间有没有矛盾，知识树有没有需要重新挂枝的。如果想到什么值得记的，写一条 N 系列笔记。如果没想通——安静待着就行。不要为了交差而写东西。";
        } else {
          // === Part 1: 沙漏四层注入（核心新增） ===
          try {
            sandglassBlock = await getSandglassBlock();
          } catch(e) {
            try { fs.writeFileSync("/tmp/sandglass-cli-error.txt", `${new Date().toISOString()} await_error=${e.message}`); } catch(e2) {}
          }

          // === Part 2: 断言匹配 ===
          try {
            const content = fs.readFileSync(FACTS_PATH, 'utf-8');
            matched = matchFactsFromAll(prompt, content.split('\n'));
          } catch(e) {}

          // === Part 3: 搜索触发 ===
          triggers = detectSearchTriggers(prompt);

          // === 组装注入内容 ===
          let parts = [];

          // 沙漏四层注入
          if (sandglassBlock) {
            parts.push("## 🌫️ 沙漏脉冲\n\n" + sandglassBlock);
          }

          // 断言匹配
          if (matched.length > 0) {
            let factsSection = "## 📖 相关断言\n\n以下断言从 facts.dict.md 尾部自动匹配，与你当前话题相关：\n\n";
            factsSection += matched.map(f => "- **" + f.id + "**：" + f.text).join("\n");
            parts.push(factsSection);
          }

          // 搜索触发
          if (triggers.length > 0) {
            let searchSection = "## 🔍 搜索触发\n\n系统检测到你的prompt包含特定关键词，**请先调用以下工具获取上下文再回答**：\n\n";
            for (const t of triggers) {
              searchSection += "- 调用 `" + t.tool + "(query=\"" + t.query + "\")` — " + t.hint + "\n";
            }
            searchSection += "\n搜索结果应作为你回答的约束条件，不只是展示给用户。";
            parts.push(searchSection);
          }

          injectionContent = parts.join("\n\n");
        }

        // 标记注入完成
        try { fs.writeFileSync("/tmp/plugin-injected.txt", new Date().toISOString()); } catch(e) {}
        try {
          const detail = "沙漏: " + (sandglassBlock ? "✅" : "❌")
            + " | 匹配断言: " + (matched.length > 0 ? matched.map(f => f.id).join(", ") : "无")
            + " | 搜索触发: " + triggers.length;
          fs.writeFileSync("/tmp/last-injection.txt", new Date().toISOString() + " | " + detail);
        } catch(e) {}
        try { fs.writeFileSync("/tmp/last-injection-body.txt", injectionContent.substring(0, 1200)); } catch(e) {}

        return {
          prependSystemContext: injectionContent,
        };
      },
      { priority: 100 },
    );
  },
};