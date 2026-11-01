# 谈心小辅 · 语音对练

学生心理辅导的**语音对练训练系统**——老师（辅导员）通过语音或文字，与一个「由 LLM 扮演的学生」对话，练习谈心与危机处置能力。

核心链路：

```
老师语音/文字 → [ASR] → 学生角色 LLM → [TTS] → 学生语音
```

已完成能力：**实时语音对话**、**训练记录列表**、**五维复盘评价**（督导 LLM 与学生 LLM 分离）。

## 目录结构

```
backend/                   FastAPI 服务端（编排 + 可插拔 Provider + 持久化）
  app/
    main.py                FastAPI 入口（CORS、挂载 REST 路由）
    config.py              读 .env 配置（pydantic-settings）
    db.py / models.py      异步 SQLite；turns / evaluations 表
    repo.py                转写、评价、会话列表的读写
    core/
      role.py              学生角色/隐藏事实 → system prompt（仅服务端）
      orchestrator.py      对话编排
      evaluator.py         复盘评分要点 + 转写组装
    providers/             ASR / LLM / TTS / Evaluator 接口与实现（换厂商=改配置）
      llm_deepseek.py      学生 LLM
      evaluator_deepseek.py 督导 LLM（评价，角色与评价分离）
      asr_funasr.py / tts_edge.py / *_stub.py
    routers/sessions.py    REST：训练记录 + 复盘
    ws/chat.py             WebSocket 实时对话（文字/语音）
  services/
    funasr_server.py       独立 FunASR 识别服务（自部署）
  requirements.txt
  .env.example             配置模板（复制为 .env 填密钥）
frontend/             原生 HTML 前端（无需构建）
  index.html               首页 / 场景选择（静态）
  conversation.html + voice.js   谈话训练（语音/文字，接后端）
  records.html + records.js      训练记录列表（接 GET /sessions）
  review.html + review.js        复盘报告（接 GET/POST /sessions/{id}/review）
  details.html / import.html 等  案例详情 / 导入（UI 壳，待接 RAG）
  shared.js / styles.css    公共布局与样式
tools/
  caddy/Caddyfile          静态页面 + /ws/chat、/sessions 反向代理（监听 5180）
```

## 技术栈（可插拔）

| 环节 | 默认实现 | 状态 |
|------|----------|------|
| LLM（扮学生）| DeepSeek | ✅ 已接 |
| 评价 LLM（督导）| DeepSeek（独立模型/提示词）| ✅ 已接 |
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

cp .env.example .env        # 编辑 .env：填 DEEPSEEK_API_KEY
                            # ASR_PROVIDER=stub 可先跑纯文字；=funasr 走本地识别

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

- **本机测试**：双击 `frontend/index.html`（`voice.js` 会自动连本机后端 `ws://127.0.0.1:8000`）。
- **或用 Caddy**（静态页 + 反代，更接近真实部署）：

```bash
caddy run --config tools/caddy/Caddyfile
# 打开 http://localhost:5180/conversation.html
```

## 接口

### WebSocket `/ws/chat`

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

### REST

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/sessions` | 训练记录列表（时间/轮数/是否已复盘/得分）|
| GET | `/sessions/{id}/review` | 读取已生成的复盘 |
| POST | `/sessions/{id}/review` | 生成复盘（五维评分 + 证据 + 建议）|

复盘五维：共情引导、思想引领、问题解决、临场应变、语言表达，各 0–20，合计 100。

## 关键设计（对应需求文档）

- **服务端注入 / 私有角色设定**：学生「隐藏背景、表达特点、可控分支」在 `app/core/role.py` 组装成 system prompt，只在服务端，浏览器不可见。
- **角色与评价分离**：扮学生的 LLM 与打分的督导 LLM 是两个独立 Provider，可分别换模型；评价走独立 system prompt。
- **转写与评价持久化**：每轮对话写 `turns` 表，复盘写 `evaluations` 表（session 唯一），供回听与证据评价。
- **不依赖单一厂商**：`providers/` 下每个环节都是接口 + 实现，换厂商只改 `.env` 的 Provider 名。
- **模型密钥仅在服务端**：密钥、隐藏事实都在 `.env` / 服务端，前端只拿音频和文字。

## 后续路线

1. 场景选择 + 谈前准备 + 可控分支（当前角色/场景服务端硬编码为「小悦 / 情绪困扰」）
2. VAD + 打断（Silero，本地）
3. 真实案例库（RAG 检索）：导入页已有 UI，缺后端检索与知识库
4. PDF / Word 报告导出
5. TTS 升级 IndexTTS2（GPU，接 8 维情绪向量）
6. 危机专项（风险识别与转介）
