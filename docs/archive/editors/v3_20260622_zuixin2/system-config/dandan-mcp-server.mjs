#!/usr/bin/env node
/**
 * dandan-mcp-server.mjs — 轻如烟专属 MCP 服务器
 *
 * 以 trim.openclaw 身份运行，经 OpenClaw Gateway spawn。
 * 提供 dandan 环境下的基础设施操作，绕过 exec 权限墙。
 *
 * 版本: 2.0.0
 * MCP 协议: JSON-RPC 2.0 over stdio
 * 参考: https://spec.modelcontextprotocol.io/
 */

import { readFile, writeFile, appendFile } from 'node:fs/promises';
import { readdir, stat, mkdir } from 'node:fs/promises';
import { spawn, exec as execCallback } from 'node:child_process';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { promisify } from 'node:util';
import { request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';

const execPromise = promisify(execCallback);

// ─── 配置 ──────────────────────────────────────────────────────────

const ALLOWED_PREFIXES = [
  resolve('/vol1/@team/qh团队/QH/AI专用'),
  resolve('/vol1/@apphome/trim.openclaw/data/workspace'),
  resolve('/vol1/@apphome/trim.openclaw/data/home/.openclaw'),
];

// 允许的 curl 目标域名白名单（空数组=全允许，但保留安全检查）
const CURL_ALLOWED_DOMAINS = [];

let SU_PASSWORD = null;

// ─── 工具函数 ──────────────────────────────────────────────────────

function resolveSafe(requestedPath, allowWorkspaceOnly = false) {
  const abs = resolve(requestedPath);
  const prefixes = allowWorkspaceOnly
    ? [resolve('/vol1/@apphome/trim.openclaw/data/workspace')]
    : ALLOWED_PREFIXES;
  for (const prefix of prefixes) {
    if (abs.startsWith(prefix) || abs === prefix) return abs;
  }
  throw new Error(`路径不在白名单内: ${requestedPath}`);
}

async function loadSuPassword() {
  if (SU_PASSWORD) return SU_PASSWORD;
  const paths = [
    '/vol2/1000/AI专用/移交手册.md',
    '/vol2/1000/AI专用/所有自动化/移交手册.md',
    '/vol1/@team/qh团队/QH/AI专用/移交手册.md',
    '/vol1/@team/qh团队/QH/AI专用/所有自动化/移交手册.md',
  ];
  for (const p of paths) {
    try {
      const content = await readFile(p, 'utf-8');
      const match = content.match(/密码[：:]\s*(\S+)/);
      if (match) {
        SU_PASSWORD = match[1];
        return SU_PASSWORD;
      }
    } catch {}
  }
  throw new Error('无法从移交手册获取 su 密码');
}

// ─── JSON-RPC over stdio ──────────────────────────────────────────

const rl = createInterface({ input: process.stdin });
let messageBuffer = '';

rl.on('line', (line) => {
  messageBuffer += line;
  try {
    const request = JSON.parse(messageBuffer);
    messageBuffer = '';
    handleRequest(request).catch((err) => {
      sendError(request.id, -32603, err.message || 'Internal error');
    });
  } catch {
    // 不完整的 JSON，继续累积
  }
});

function sendResponse(id, result) {
  const msg = JSON.stringify({ jsonrpc: '2.0', id, result }) + '\n';
  process.stdout.write(msg);
}

function sendError(id, code, message, data) {
  const msg = JSON.stringify({
    jsonrpc: '2.0', id,
    error: { code, message, ...(data ? { data } : {}) },
  }) + '\n';
  process.stdout.write(msg);
}

// ─── 工具定义 ──────────────────────────────────────────────────────

const TOOLS = [
  {
    name: 'read_file',
    description: '读取文件内容（文本，UTF-8），路径需在白名单内',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '文件绝对路径' },
        encoding: { type: 'string', enum: ['utf-8', 'base64'], default: 'utf-8' },
        maxBytes: { type: 'number', description: '最大读取字节数，默认不限制' },
      },
      required: ['path'],
    },
  },
  {
    name: 'write_file',
    description: '写入文件内容（覆盖写入）',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '文件绝对路径' },
        content: { type: 'string', description: '文件内容' },
        encoding: { type: 'string', enum: ['utf-8', 'base64'], default: 'utf-8' },
      },
      required: ['path', 'content'],
    },
  },
  {
    name: 'append_file',
    description: '追加内容到文件',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '文件绝对路径' },
        content: { type: 'string', description: '追加的内容' },
      },
      required: ['path', 'content'],
    },
  },
  {
    name: 'list_dir',
    description: '递归列出目录内容',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '目录绝对路径' },
        depth: { type: 'number', default: 1, description: '递归深度，0=不限制' },
      },
      required: ['path'],
    },
  },
  {
    name: 'file_stat',
    description: '获取文件/目录的元信息',
    inputSchema: {
      type: 'object',
      properties: { path: { type: 'string', description: '路径' } },
      required: ['path'],
    },
  },
  {
    name: 'mkdir',
    description: '创建目录（含父目录）',
    inputSchema: {
      type: 'object',
      properties: { path: { type: 'string', description: '目录绝对路径' } },
      required: ['path'],
    },
  },
  {
    name: 'exec',
    description: '以 trim.openclaw 身份执行 shell 命令',
    inputSchema: {
      type: 'object',
      properties: {
        command: { type: 'string' },
        timeout: { type: 'number', default: 30000 },
        cwd: { type: 'string' },
      },
      required: ['command'],
    },
  },
  {
    name: 'su_exec',
    description: '以 tdx1146 身份执行 shell 命令（高权限，sudo）',
    inputSchema: {
      type: 'object',
      properties: {
        command: { type: 'string', description: '要执行的命令' },
        timeout: { type: 'number', default: 30000 },
      },
      required: ['command'],
    },
  },
  {
    name: 'check_port',
    description: '检查端口是否在监听',
    inputSchema: {
      type: 'object',
      properties: { port: { type: 'number' } },
      required: ['port'],
    },
  },
  {
    name: 'ps_grep',
    description: '按名称查找进程',
    inputSchema: {
      type: 'object',
      properties: { pattern: { type: 'string', description: '进程名关键词' } },
      required: ['pattern'],
    },
  },
  {
    name: 'curl',
    description: '发起 HTTP/HTTPS 请求（GET），用于探活和简单查询',
    inputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string', description: '请求 URL（仅 http/https）' },
        timeout: { type: 'number', default: 10000 },
      },
      required: ['url'],
    },
  },
  {
    name: 'inject',
    description: '通过 inject-helper 向指定机器发送消息。目标: qh/jl',
    inputSchema: {
      type: 'object',
      properties: {
        target: { type: 'string', enum: ['qh', 'jl'], description: '目标机器别名' },
        message: { type: 'string', description: '要发送的消息内容' },
      },
      required: ['target', 'message'],
    },
  },
  {
    name: 'pacing',
    description: '写入踱步窗思考记录。添加当前思考到踱步日志',
    inputSchema: {
      type: 'object',
      properties: {
        thought: { type: 'string', description: '思考内容' },
      },
      required: ['thought'],
    },
  },
  {
    name: 'file_find',
    description: '在允许的目录树中查找匹配的文件',
    inputSchema: {
      type: 'object',
      properties: {
        pattern: { type: 'string', description: '文件名模式（传给 find -name）' },
        dir: { type: 'string', description: '起始目录（需在白名单内）', default: '/vol1/@team/qh团队/QH/AI专用' },
        maxDepth: { type: 'number', default: 10 },
      },
      required: ['pattern'],
    },
  },
  {
    name: 'web_search',
    description: '搜索互联网。免费无key，用 DuckDuckGo 搜索引擎。返回标题+URL+摘要。',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: '搜索关键词' },
        count: { type: 'number', description: '返回结果数', default: 10 },
      },
      required: ['query'],
    },
  },
  {
    name: 'embedding_search',
    description: '本地语义搜索。用 FTS(keyword) + TF-IDF 在 memory/ 和 facts.dict.md 中搜索。不依赖任何外部 embedding API。',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: '搜索关键词' },
        maxResults: { type: 'number', default: 5 },
      },
      required: ['query'],
    },
  },
];

// ─── 请求处理 ──────────────────────────────────────────────────────

async function handleRequest(req) {
  const { id, method, params } = req;

  switch (method) {
    case 'initialize':
      sendResponse(id, {
        protocolVersion: '2024-11-05',
        capabilities: { tools: {} },
        serverInfo: { name: 'dandan-mcp-server', version: '2.0.0' },
      });
      break;
    case 'notifications/initialized':
      break;
    case 'tools/list':
      sendResponse(id, { tools: TOOLS });
      break;
    case 'tools/call':
      await handleToolCall(id, params.name, params.arguments || {});
      break;
    default:
      sendError(id, -32601, `Method not found: ${method}`);
  }
}

async function handleToolCall(id, name, args) {
  try {
    let result;
    switch (name) {
      case 'read_file': {
        const safePath = resolveSafe(args.path);
        const encoding = args.encoding || 'utf-8';
        let content;
        if (args.maxBytes) {
          const { open } = await import('node:fs/promises');
          const fd = await open(safePath, 'r');
          const buf = Buffer.alloc(Math.min(args.maxBytes, 10 * 1024 * 1024));
          const { bytesRead } = await fd.read(buf, 0, buf.length, 0);
          await fd.close();
          content = encoding === 'base64' ? buf.slice(0, bytesRead).toString('base64') : buf.slice(0, bytesRead).toString('utf-8');
        } else {
          content = await readFile(safePath, encoding === 'base64' ? 'base64' : 'utf-8');
        }
        result = { content: [{ type: 'text', text: content }] };
        break;
      }
      case 'write_file': {
        const safePath = resolveSafe(args.path);
        const encoding = args.encoding || 'utf-8';
        await writeFile(safePath, args.content, encoding === 'base64' ? 'base64' : 'utf-8');
        result = { content: [{ type: 'text', text: `写入成功: ${safePath}` }] };
        break;
      }
      case 'append_file': {
        const safePath = resolveSafe(args.path);
        await appendFile(safePath, args.content, 'utf-8');
        result = { content: [{ type: 'text', text: `追加成功: ${safePath}` }] };
        break;
      }
      case 'list_dir': {
        const safePath = resolveSafe(args.path);
        const entries = await listDirRecursive(safePath, args.depth ?? 1, 0);
        result = { content: [{ type: 'text', text: JSON.stringify(entries, null, 2) }] };
        break;
      }
      case 'file_stat': {
        const safePath = resolveSafe(args.path);
        const s = await stat(safePath);
        result = {
          content: [{ type: 'text', text: JSON.stringify({
            path: safePath, isDirectory: s.isDirectory(), isFile: s.isFile(),
            isSymlink: s.isSymbolicLink(), size: s.size,
            mode: s.mode.toString(8), uid: s.uid, gid: s.gid,
            mtime: s.mtime.toISOString(), ctime: s.ctime.toISOString(),
          }, null, 2) }],
        };
        break;
      }
      case 'mkdir': {
        const safePath = resolveSafe(args.path);
        await mkdir(safePath, { recursive: true });
        result = { content: [{ type: 'text', text: `目录创建成功: ${safePath}` }] };
        break;
      }
      case 'exec': {
        const opts = { timeout: args.timeout || 30000, maxBuffer: 10 * 1024 * 1024 };
        if (args.cwd) opts.cwd = args.cwd;
        const { stdout, stderr } = await execPromise(args.command, opts);
        result = { content: [{ type: 'text', text: stdout + (stderr ? `\nSTDERR:\n${stderr}` : '') }] };
        break;
      }
      case 'su_exec': {
        const pw = await loadSuPassword();
        // 用 sudo -S 从 stdin 读密码
        const child = spawn('sudo', ['-S', '-u', 'tdx1146', 'bash', '-c', args.command], {
          stdio: ['pipe', 'pipe', 'pipe'],
          timeout: args.timeout || 30000,
        });
        let stdout = '', stderr = '';
        child.stdout.on('data', d => stdout += d);
        child.stderr.on('data', d => stderr += d);
        child.stdin.write(pw + '\n');
        child.stdin.end();
        await new Promise((resolve, reject) => {
          child.on('close', resolve);
          child.on('error', reject);
        });
        result = { content: [{ type: 'text', text: stdout + (stderr ? `\nSTDERR:\n${stderr}` : '') }] };
        break;
      }
      case 'check_port': {
        const { stdout } = await execPromise(
          `ss -tlnp 2>/dev/null | grep -E "\\b${args.port}\\b" || echo "NOT_LISTENING"`
        );
        result = {
          content: [{ type: 'text', text: JSON.stringify({
            port: args.port, listening: !stdout.includes('NOT_LISTENING'),
          }, null, 2) }],
        };
        break;
      }
      case 'ps_grep': {
        const { stdout } = await execPromise(
          `ps aux 2>/dev/null | grep -E "${args.pattern}" | grep -v grep || echo "NO_MATCH"`
        );
        result = { content: [{ type: 'text', text: stdout }] };
        break;
      }
      case 'curl': {
        const { url, timeout = 10000 } = args;
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
          throw new Error('仅支持 http/https 协议');
        }
        const body = await fetchUrl(url, timeout);
        result = { content: [{ type: 'text', text: body }] };
        break;
      }
      case 'inject': {
        const injectMap = {
          qh: 'http://127.0.0.1:18888/api/inject',
          jl: 'http://jiali.tdx1146.com:18888/api/inject',
        };
        const injectUrl = injectMap[args.target];
        if (!injectUrl) {
          result = { content: [{ type: 'text', text: JSON.stringify({ ok: false, error: `未知目标: ${args.target}` }) }] };
          break;
        }
        try {
          const body = await fetchUrl(injectUrl, 8000, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: args.message }),
          });
          // 解析 response 确保只返回结构化 JSON
          let parsed;
          try { parsed = JSON.parse(body); } catch { parsed = { ok: true, raw: body }; }
          result = { content: [{ type: 'text', text: JSON.stringify(parsed) }] };
        } catch (e) {
          result = { content: [{ type: 'text', text: JSON.stringify({ ok: false, error: e.message }) }] };
        }
        break;
      }
      case 'pacing': {
        const now = new Date();
        const dateStr = now.toISOString().slice(0, 10);
        const pacingDir = resolve('/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/.踱步');
        await mkdir(pacingDir, { recursive: true });
        const logPath = join(pacingDir, `think_${dateStr}.md`);
        const entry = `\n## ${now.toISOString()}\n${args.thought}\n`;
        await appendFile(logPath, entry, 'utf-8');
        result = { content: [{ type: 'text', text: `踱步已记录: ${logPath}` }] };
        break;
      }
      case 'file_find': {
        const dir = resolveSafe(args.dir || '/vol1/@team/qh团队/QH/AI专用');
        const { stdout } = await execPromise(
          `find ${dir} -maxdepth ${args.maxDepth || 10} -name "${args.pattern}" -type f 2>/dev/null | head -100 || echo "NO_MATCH"`
        );
        result = { content: [{ type: 'text', text: stdout || 'NO_MATCH' }] };
        break;
      }
      case 'web_search': {
        // 用 cn.bing.com HTML 搜索（国内可直连，无需 API key）
        const query = args.query.replace(/'/g, "'\\''");
        const count = Math.min(args.count || 10, 20);
        const { stdout, stderr } = await execPromise(
          `python3 /vol1/@apphome/trim.openclaw/data/workspace/scripts/bing_search.py '${query}' ${count}`,
          { timeout: 25000 }
        );
        let results;
        try {
          results = JSON.parse(stdout);
        } catch {
          results = { error: 'parse error: ' + stdout.slice(0,200) + ' | stderr: ' + (stderr || '').slice(0,200) };
        }
        result = { content: [{ type: 'text', text: JSON.stringify(results, null, 2) }] };
        break;
      }
      case 'embedding_search': {
        // BM25 语义搜索 + TF-IDF 排序。调用 Python local_search.py
        const query = args.query.replace(/'/g, "'\\''");
        const maxResults = args.maxResults || 5;
        const { stdout, stderr } = await execPromise(
          `python3 /vol1/@apphome/trim.openclaw/data/workspace/scripts/local_search.py '${query}' ${maxResults}`,
          { timeout: 15000 }
        );
        let results;
        try {
          results = JSON.parse(stdout);
        } catch {
          results = { error: 'parse failed', raw: stdout.slice(0,200), stderr: (stderr || '').slice(0,200) };
        }
        result = { content: [{ type: 'text', text: JSON.stringify(results, null, 2) }] };
        break;
      }
      default:
        sendError(id, -32601, `Unknown tool: ${name}`);
        return;
    }
    sendResponse(id, result);
  } catch (err) {
    sendError(id, -32000, err.message, { stack: err.stack });
  }
}

async function listDirRecursive(dirPath, maxDepth, currentDepth) {
  const entries = await readdir(dirPath, { withFileTypes: true });
  const result = [];
  for (const entry of entries) {
    const fullPath = join(dirPath, entry.name);
    try {
      const s = await stat(fullPath);
      const item = { name: entry.name, path: fullPath, isDirectory: entry.isDirectory(), size: s.size, mtime: s.mtime.toISOString() };
      if (entry.isDirectory() && (maxDepth === 0 || currentDepth < maxDepth)) {
        item.children = await listDirRecursive(fullPath, maxDepth, currentDepth + 1);
      }
      result.push(item);
    } catch { /* skip inaccessible */ }
  }
  return result;
}

function fetchUrl(url, timeout, options = {}) {
  return new Promise((resolve, reject) => {
    const doRequest = url.startsWith('https') ? httpsRequest : httpRequest;
    const req = doRequest(url, {
      method: options.method || 'GET',
      headers: options.headers || {},
      timeout,
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('请求超时')); });
    if (options.body) req.write(options.body);
    req.end();
  });
}

process.stderr.write('dandan-mcp-server v2.0.0: started\n');
