# TTS（文字转语音）修复记录

## 故障现象
用户在编辑器页面点击小喇叭按钮(🔊)，提示"TTS服务没有装"或生成失败。

## 原因
`edge-tts` 和 `gTTS` 库均未安装，导致后端 `handle_tts` 函数调用 `import edge_tts` 失败。

## 修复操作

### 1. 安装 edge-tts（主方案）
```bash
pip install edge-tts \
  --target=/vol1/@apphome/trim.openclaw/data/home/.local/lib/python3.11/site-packages
```
- 版本: `edge-tts 7.2.8`
- 免费，无需 API key
- 使用 Microsoft Azure Cognitive Services 的在线语音合成

### 2. 安装 gTTS（备选方案）
```bash
pip install gTTS \
  --target=/vol1/@apphome/trim.openclaw/data/home/.local/lib/python3.11/site-packages
```
- 版本: `gTTS 2.5.4`
- Google TTS 引擎
- 当前未被主要 handler 使用，仅作备选

### 3. 重启服务器
安装后需要重启 edit-web.py 进程以加载新库：
```bash
kill <PID>
cd /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts
nohup python3 edit-web.py > /dev/null 2>&1 &
```

## 代码架构

### 前端 (render.js)
- 每个消息区块后渲染 🔊 按钮 (`tts-btn`)
- 点击调用 `ttsReadBtn(this)` 函数
- 通过 `api.post('/api/tts', {text: text})` 向后端发送请求
- 后端返回 JSON: `{ok: true, audio: "base64_mp3_data", format: "mp3"}`
- 前端使用 `atob()` + `Audio` API 播放

### 后端 (awake_handler.py → handle_tts)
- `POST /api/tts` 路由在 `handlers/router.py` 中注册
- 使用 `edge-tts` 引擎，语音为 `zh-CN-XiaoxiaoNeural`（晓晓中文女声）
- source: `handlers/awake_handler.py` 第95-128行
- 动态导入路径: `path('SITE_PACKAGES')` = `/vol1/@apphome/trim.openclaw/data/home/.local/lib/python3.11/site-packages`

## 验证

### 已安装的中文语音
```
zh-CN-XiaoxiaoNeural: Female - zh-CN (Microsoft Xiaoxiao - 晓晓)
zh-CN-XiaoyiNeural: Female - zh-CN (Microsoft Xiaoyi - 晓伊)
zh-CN-YunjianNeural: Male - zh-CN (Microsoft Yunjian - 云健)
zh-CN-YunxiNeural: Male - zh-CN (Microsoft Yunxi - 云希)
zh-CN-YunxiaNeural: Male - zh-CN (Microsoft Yunxia - 云夏)
zh-CN-YunyangNeural: Male - zh-CN (Microsoft Yunyang - 云扬)
```

### 验证命令
```bash
# 测试 API
curl -s -X POST http://localhost:18888/api/tts \
  -H 'Content-Type: application/json' \
  -d '{"text": "你好，晓晓中文语音测试"}' \
  --max-time 30

# 应返回: {"ok": true, "audio": "//NkxAAAA..."}
```

### 直接 Python 验证
```python
import sys
sys.path.insert(0, '/vol1/@apphome/trim.openclaw/data/home/.local/lib/python3.11/site-packages')
import edge_tts
import asyncio

async def test():
    tts = edge_tts.Communicate("你好", voice='zh-CN-XiaoxiaoNeural')
    async for chunk in tts.stream():
        if chunk['type'] == 'audio':
            print(f"音频流正常, 收到 {len(chunk['data'])} bytes")

asyncio.run(test())
```

## 注意事项
- 服务器启动后 `import edge_tts` 在请求时动态执行（非模块加载时），所以若之前未安装，只需安装后重启
- `edit-web.py` 文件中存在死代码 `_HAS_TTS`（gTTS），不影响功能，未清理
- edge-tts 需要网络连接（调用 Microsoft Azure 在线服务）
- 当前默认语音为 `zh-CN-XiaoxiaoNeural`（晓晓女声），如需切换可在 `awake_handler.py` 第110行修改 `voice` 参数

## 相关文件
- `handlers/awake_handler.py` — TTS 后端处理逻辑 (第95-128行)
- `handlers/router.py` — 路由注册 (第25, 167行)
- `static/js/render.js` — 前端 TTS 按钮和播放逻辑 (第52-117行)
- `static/index.html` — TTS 速度选择器和指示器 (第134-142行)
- `static/css/styles.css` — TTS 按钮样式 (第309-330行)
- `utils/config.py` — SITE_PACKAGES 路径配置 (第115行)
