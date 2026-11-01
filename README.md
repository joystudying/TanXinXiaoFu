# 谈心小辅 · 语音对练

学生心理辅导的**语音对练训练系统**——老师（辅导员）通过语音或文字，与一个「由 LLM 扮演的学生」对话，练习谈心与危机处置能力。

当前仓库先落地**语音对话链路**：

```
老师语音/文字 → [ASR] → 学生角色 LLM → [TTS] → 学生语音
```

## 目录结构

```
backend/               FastAPI 服务端（编排 + 可插拔 Provider + 转写存储）
  app/
    providers/         ASR / LLM / TTS 接口与实现（换厂商=改配置，不改业务代码）
    core/              角色设定、system prompt 注入、对话编排
    ws/                WebSocket 端点（文字 / 语音）
    models.py          转写记录数据表
  services/
    funasr_server.py   独立 FunASR 识别服务（自部署）
谈心小辅-HTML界面/      原生 HTML 前端（6 页：场景选择→案例详情→谈话→复盘→训练记录）
  voice.js             语音对接：WebSocket + 录音 + 播放（把界面接到后端）
tools/                 部署辅助
  caddy/Caddyfile      静态页面 + /ws/chat、/sessions 反向代理（监听 5180）
```

## 技术栈（可插拔）

| 环节 | 默认实现 | 状态 |
|------|----------|------|
| LLM（扮学生）| DeepSeek | ✅ 已接 |
| TTS | edge-tts（免费，无需 GPU）| ✅ 已接 |
| ASR | FunASR（自部署）| ✅ 已接 |
| VAD / 打断 | Silero | 🔜 后续（当前整句往返）|
| 存储 | SQLite（默认）/ PostgreSQL | ✅ |

> 未来升级：TTS 换成 IndexTTS2（需 GPU + 情绪向量），ASR 可换讯飞/阿里，LLM 可换 Claude——都只需新增一个 Provider 实现类。

## 快速开始

### 1. 后端（FastAPI，端口 8000）

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env        # 编辑 .env：填 DEEPSEEK_API_KEY，ASR_PROVIDER=funasr

uvicorn app.main:app --port 8000
```

验证：浏览器打开 `http://127.0.0.1:8000/health` 应返回 `{"status":"ok"}`。

### 2. FunASR 识别服务（端口 8001，语音输入需要）

```bash
cd backend
pip install funasr fastapi uvicorn
python services/funasr_server.py     # 首次自动下载 paraformer-zh 模型（约 1GB）
```

> **Python 版本**：主后端用 Python 3.11+；FunASR、IndexTTS2 需要 **Python 3.10–3.11**，请为它们单独建环境，不要和主后端混用。

### 3. 前端（原生 HTML，无需构建）

文字对练开箱即用；语音输入需先启动 FunASR（第 2 步）。

- **本机测试**：双击 `谈心小辅-HTML界面/index.html` 即可（`voice.js` 会自动连本机后端 `ws://127.0.0.1:8000`）。
- **或用 Caddy**（静态页 + `/ws/chat` 转发，更接近真实部署）：

```bash
caddy run --config tools/caddy/Caddyfile
# 打开 http://localhost:5180/conversation.html
```

## WebSocket 协议

客户端 → 服务端（JSON）：

```json
{"type":"text","text":"老师说的话"}
{"type":"audio","audio_b64":"...","audio_format":"pcm16"}
{"type":"reset"}
```

服务端 → 客户端：

```json
{"type":"ready","session_id":"...","student_name":"小悦","scenario":"情绪困扰"}
{"type":"reply","text":"学生回复","emotion":null,"audio_b64":"...","audio_format":"mp3"}
```

## 关键设计（对应需求文档）

- **服务端注入 / 私有角色设定**：学生「隐藏背景、表达特点、可控分支」在 `app/core/role.py` 组装成 system prompt，只在服务端，浏览器不可见。
- **转写记录**：每轮对话写入 `turns` 表（角色 / 轮次 / 时间 / 情绪），供后续回听与证据评价。
- **不依赖单一厂商**：`providers/` 下每个环节都是接口 + 实现，换厂商只改 `.env` 的 Provider 名。
- **模型密钥仅在服务端**：密钥、隐藏事实都在 `.env` / 服务端，前端只拿音频和文字。

## 后续路线

1. VAD + 打断（Silero，本地）
2. 场景选择 + 谈前准备 + 可控分支（服务端动态注入事件）
3. 谈话复盘 / 证据评价链路（按轮切分 + RAG + 评价大模型，角色与评价分离）
4. 历史记录查询 + PDF/Word 报告导出
5. TTS 升级 IndexTTS2（GPU，接 8 维情绪向量）
6. 危机专项（风险识别与转介）
