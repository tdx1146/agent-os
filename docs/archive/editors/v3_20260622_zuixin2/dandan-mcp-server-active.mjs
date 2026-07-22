#!/usr/bin/env node
/**
 * dandan-mcp-server.mjs — 轻如烟专属 MCP 服务器
 *
 * V3: 工具合并版 — 16→7 个，减少缓存前缀碎片。
 *
 * 以 trim.openclaw 身份运行，经 OpenClaw Gateway spawn。
 * 提供 dandan 环境下的基础设施操作，绕过 exec 权限墙。
 *
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
    name: 'file',
    description: '文件操作。action: read|write|append|stat|find|list|mkdir。统一文件系统接口。',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['read', 'write', 'append', 'stat', 'find', 'list', 'mkdir'],
          description: '操作类型',
        },
        path: { type: 'string', description: '文件/目录路径（read/write/append/stat/list/mkdir）' },
        content: { type: 'string', description: '文件内容（write/append）' },
        encoding: { type: 'string', enum: ['utf-8', 'base64'], default: 'utf-8', description: '编码（read/write）' },
        maxBytes: { type: 'number', description: '最大读取字节数（read）' },
        depth: { type: 'number', default: 1, description: '递归深度0=不限制（list）' },
        pattern: { type: 'string', description: '文件名模式（find）' },
        dir: { type: 'string', description: '起始目录（find，默认 /vol1/@team/qh团队/QH/AI专用）' },
        maxDepth: { type: 'number', default: 10, description: '搜索深度（find）' },
      },
      required: ['action'],
    },
  },
  {
    name: 'exec',
    description: '批量执行 shell 命令。mode=normal（普通执行）、mode=su（以 tdx1146 身份 sudo 执行）。一次接收多个命令减少 API 轮次。',
    inputSchema: {
      type: 'object',
      properties: {
        commands: { type: 'array', items: { type: 'string' }, description: '要执行的命令列表，按顺序执行' },
        timeout: { type: 'number', default: 60000, description: '每条命令的超时时间(ms)' },
        mode: { type: 'string', enum: ['normal', 'su'], default: 'normal', description: '执行模式' },
      },
      required: ['commands'],
    },
  },
  {
    name: 'system',
    description: '系统操作。action: port（检查端口）、ps（查进程）、curl（HTTP GET 请求）。',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['port', 'ps', 'curl'],
          description: '操作类型',
        },
        port: { type: 'number', description: '端口号（port）' },
        pattern: { type: 'string', description: '进程名关键词（ps）' },
        url: { type: 'string', description: '请求 URL（curl，仅 http/https）' },
        timeout: { type: 'number', default: 10000, description: '超时时间ms（curl）' },
      },
      required: ['action'],
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
    name: 'web_search',
    description: '搜索互联网。免费无key，用 Bing.cn HTML 搜索。返回标题+URL+摘要。',
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
        serverInfo: { name: 'dandan-mcp-server', version: '3.0.0' },
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
      // ── file（合并 read/write/append/stat/find/list/mkdir）──
      case 'file': {
        const action = args.action;
        switch (action) {
          case 'read': {
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
          case 'write': {
            const safePath = resolveSafe(args.path);
            const encoding = args.encoding || 'utf-8';
            await writeFile(safePath, args.content, encoding === 'base64' ? 'base64' : 'utf-8');
            result = { content: [{ type: 'text', text: `写入成功: ${safePath}` }] };
            break;
          }
          case 'append': {
            const safePath = resolveSafe(args.path);
            await appendFile(safePath, args.content, 'utf-8');
            result = { content: [{ type: 'text', text: `追加成功: ${safePath}` }] };
            break;
          }
          case 'stat': {
            const safePath = resolveSafe(args.path);
            const s = await stat(safePath);
            result = { content: [{ type: 'text', text: JSON.stringify({
              path: safePath, isDirectory: s.isDirectory(), isFile: s.isFile(),
              isSymlink: s.isSymbolicLink(), size: s.size,
              mode: s.mode.toString(8), uid: s.uid, gid: s.gid,
              mtime: s.mtime.toISOString(), ctime: s.ctime.toISOString(),
            }, null, 2) }] };
            break;
          }
          case 'find': {
            const dir = resolveSafe(args.dir || '/vol1/@team/qh团队/QH/AI专用');
            const { stdout } = await execPromise(
              `find ${dir} -maxdepth ${args.maxDepth || 10} -name "${args.pattern}" -type f 2>/dev/null | head -100 || echo "NO_MATCH"`
            );
            result = { content: [{ type: 'text', text: stdout || 'NO_MATCH' }] };
            break;
          }
          case 'list': {
            const safePath = resolveSafe(args.path);
            const entries = await listDirRecursive(safePath, args.depth ?? 1, 0);
            result = { content: [{ type: 'text', text: JSON.stringify(entries, null, 2) }] };
            break;
          }
          case 'mkdir': {
            const safePath = resolveSafe(args.path);
            await mkdir(safePath, { recursive: true });
            result = { content: [{ type: 'text', text: `目录创建成功: ${safePath}` }] };
            break;
          }
          default:
            sendError(id, -32602, `Unknown file action: ${action}`);
            return;
        }
        break;
      }

      // ── exec（合并 batch_exec + su_exec）──
      case 'exec': {
        const commands = args.commands || [];
        const mode = args.mode || 'normal';
        let allResults = '';

        for (let i = 0; i < commands.length; i++) {
          try {
            const label = `[CMD ${i+1}/${commands.length}] ${commands[i].substring(0, 80)}`;

            if (mode === 'su') {
              const pw = await loadSuPassword();
              const child = spawn('sudo', ['-S', '-u', 'tdx1146', 'bash', '-c', commands[i]], {
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
              allResults += `${label}\n${stdout}${stderr ? `\nSTDERR:\n${stderr}` : ''}\n`;
            } else {
              const opts = { timeout: args.timeout || 60000, maxBuffer: 10 * 1024 * 1024 };
              const { stdout, stderr } = await execPromise(commands[i], opts);
              allResults += `${label}\n${stdout}${stderr ? `\nSTDERR:\n${stderr}` : ''}\n`;
            }

            if (allResults.length > 200000) {
              allResults += `\n... (truncated, ${commands.length - i - 1} commands not shown)`;
              break;
            }
          } catch (err) {
            allResults += `[CMD ${i+1}/${commands.length}] ERROR: ${err.message}\n`;
          }
        }
        result = { content: [{ type: 'text', text: allResults }] };
        break;
      }

      // ── system（合并 check_port + ps_grep + curl）──
      case 'system': {
        const action = args.action;
        switch (action) {
          case 'port': {
            const { stdout } = await execPromise(
              `ss -tlnp 2>/dev/null | grep -E "\\b${args.port}\\b" || echo "NOT_LISTENING"`
            );
            result = { content: [{ type: 'text', text: JSON.stringify({
              port: args.port, listening: !stdout.includes('NOT_LISTENING'),
            }, null, 2) }] };
            break;
          }
          case 'ps': {
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
          default:
            sendError(id, -32602, `Unknown system action: ${action}`);
            return;
        }
        break;
      }

      // ── inject（保持独立）──
      case 'inject': {
        const injectMap = {
          qh: 'http://qh.tdx1146.com:18888/api/inject',
          jl: 'http://jiali.tdx1146.com:18888/api/inject',
        };
        const injectUrl = injectMap[args.target];
        if (!injectUrl) throw new Error(`未知目标: ${args.target}`);
        const body = await fetchUrl(injectUrl, 8000, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: args.message }),
        });
        result = { content: [{ type: 'text', text: `inject 到 ${args.target} 完成: ${body}` }] };
        break;
      }

      // ── pacing（保持独立）──
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

      // ── web_search（保持独立）──
      case 'web_search': {
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

      // ── embedding_search（保持独立）──
      case 'embedding_search': {
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

process.stderr.write('dandan-mcp-server v3.0.0: started (tools merged: 16→7)\n');
