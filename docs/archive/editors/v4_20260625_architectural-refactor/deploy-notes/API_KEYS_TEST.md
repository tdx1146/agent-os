# DeepSeek API Key 测试报告

**测试时间**: 2026-06-25 20:04 (UTC+8)

**测试环境**: OpenClaw subagent runtime

## 测试结果概览

| Key    | Models API | Chat API | Balance API | 余额 |
|--------|-----------|----------|-------------|------|
| jiali3 | ✅ 200 (240ms) | ✅ 200 (1650ms) | ✅ 200 | ¥33.54 |
| jiali4 | ✅ 200 (190ms) | ✅ 200 (1633ms) | ✅ 200 | ¥33.54 |

## 详细结果

### jiali3 (`sk-655b7c...eb1b`)

| 测试项 | 结果 |
|--------|------|
| Models API | 200 OK, 240ms |
| 可用模型 | `deepseek-v4-flash`, `deepseek-v4-pro` |
| Chat API | 200 OK, 1650ms |
| 回复内容 | "你好！我是DeepSeek，很高兴收到你的消息..." |
| Token 用量 | prompt=13, completion=50, total=63 |
| 余额查询 | ✅ 成功 |
| 余额 | ¥33.54 (充值余额，无赠送额度) |
| 账户可用 | ✅ 是 |

### jiali4 (`sk-d91a63...2307`)

| 测试项 | 结果 |
|--------|------|
| Models API | 200 OK, 190ms |
| 可用模型 | `deepseek-v4-flash`, `deepseek-v4-pro` |
| Chat API | 200 OK, 1633ms |
| 回复内容 | "你好！我是DeepSeek，很高兴为你服务..." |
| Token 用量 | prompt=13, completion=50, total=63 |
| 余额查询 | ✅ 成功 |
| 余额 | ¥33.54 (充值余额，无赠送额度) |
| 账户可用 | ✅ 是 |

## 结论

**两个 Key 均完全可用。**

### 关键发现

1. **Key 格式正确** — 标准 `sk-` 开头 32 字符，无需额外配置 base URL
2. **余额充足** — 各 ¥33.54，短期内无需续费
3. **API Base URL** — 使用默认 `https://api.deepseek.com` 即可
4. **可用模型** — 两个 key 返回相同的模型列表：`deepseek-v4-flash`（快速/经济）和 `deepseek-v4-pro`（更强但更慢）
5. **延迟表现** — models 查询 ~200ms，chat 完整请求 ~1.6s，在中国大陆地区延迟合理
6. **余额同额** — 两个 key 余额完全一致（¥33.54），可能是同一账户下的两个子 key

### 建议的子代理模型配置

```json
{
  "subagent_model": "deepseek-v4-flash",
  "api_base_url": "https://api.deepseek.com",
  "max_tokens": 4096,
  "temperature": 0.7
}
```

- **推荐 `deepseek-v4-flash`** 作为子代理默认模型：低成本、低延迟，适合大多数场景
- **`deepseek-v4-pro`** 可用于复杂推理任务（代码审查、多步分析等）
- 如果一个 key 遇到 rate limit，自动切换到另一个

### 注意事项

- 两个 key 余额一致（¥33.54），建议监控用量，低于 ¥5 时发出告警
- 当前无赠送/granted 余额，所有消耗走充值余额
- 建议在子代理配置中实现 key 轮换机制，提升可用性
