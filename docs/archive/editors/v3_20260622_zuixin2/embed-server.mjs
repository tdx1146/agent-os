// embed-server.mjs — 本地 embedding HTTP 服务
// 支持 OpenAI-compatible /v1/embeddings 路由
// 使用 node-llama-cpp + bge-m3 Q2_K GGUF 模型

import { getLlama } from "/vol1/@apphome/trim.openclaw/data/home/.openclaw/npm/projects/openclaw-llama-cpp-provider-15b2d859e6/node_modules/@openclaw/llama-cpp-provider/node_modules/node-llama-cpp/dist/index.js";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";

const MODEL_PATH = "/vol1/@apphome/trim.openclaw/data/workspace/bge-small-zh-v1.5-q8_0.gguf";
const PORT = parseInt(process.env.EMBED_PORT || "11435", 10);
const CONTEXT_SIZE = 8192;

let llama, model, context;
let initPromise = null;

async function ensureContext() {
  if (context) return context;
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const { LlamaLogLevel } = await import("/vol1/@apphome/trim.openclaw/data/home/.openclaw/npm/projects/openclaw-llama-cpp-provider-15b2d859e6/node_modules/@openclaw/llama-cpp-provider/node_modules/node-llama-cpp/dist/index.js");
    llama = await getLlama({ logLevel: LlamaLogLevel.error });
    model = await llama.loadModel({ modelPath: MODEL_PATH });
    context = await model.createEmbeddingContext({ contextSize: CONTEXT_SIZE });
    return context;
  })();
  return initPromise;
}

async function getEmbedding(text) {
  const ctx = await ensureContext();
  const result = await ctx.getEmbeddingFor(text);
  return new Float32Array(result.vector);
}

function sendJSON(res, status, obj) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(obj));
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", chunk => body += chunk);
    req.on("end", () => {
      try { resolve(JSON.parse(body)); }
      catch { reject(new Error("invalid JSON")); }
    });
    req.on("error", reject);
  });
}

const server = createServer(async (req, res) => {
  // CORS
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") {
    res.writeHead(204); res.end(); return;
  }

  // Only accept POST to /v1/embeddings or /
  const urlPath = new URL(req.url, `http://${req.headers.host}`).pathname;
  const isEmbeddings = urlPath === "/v1/embeddings" || urlPath === "/embeddings" || urlPath === "/";
  
  if (req.method !== "POST" || !isEmbeddings) {
    res.writeHead(405, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Method not allowed. Use POST /v1/embeddings" }));
    return;
  }

  try {
    const data = await parseBody(req);
    const input = data.input || "";
    const model = data.model || "bge-m3";
    const inputs = Array.isArray(input) ? input : [input];

    const embeddings = await Promise.all(inputs.map(t => getEmbedding(String(t))));

    // OpenAI-compatible response format
    sendJSON(res, 200, {
      object: "list",
      model: model,
      data: embeddings.map((emb, i) => ({
        object: "embedding",
        index: i,
        embedding: Array.from(emb),
      })),
      usage: { prompt_tokens: 0, total_tokens: 0 }
    });
  } catch (err) {
    sendJSON(res, 500, { error: err.message });
  }
});

server.listen(PORT, "127.0.0.1", async () => {
  console.log(`🌫️ Embed server ready on port ${PORT}`);
  console.log(`   Model: bge-m3-Q2_K.gguf`);
  console.log(`   Context: ${CONTEXT_SIZE}`);
  console.log(`   Endpoints: POST /v1/embeddings`);
  // Warm up
  try {
    await ensureContext();
    console.log("   Model loaded and ready");
  } catch (e) {
    console.error("   Load error:", e.message);
  }
});
