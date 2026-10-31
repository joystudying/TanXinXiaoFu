# 谈心小辅 · 语音对练

辅导员对着一个「由大模型扮演的学生」练习谈心谈话，结束后拿到复盘。
浏览器打开就能用，不需要安装客户端。

> 这是**训练模拟器**，不是心理咨询工具，也不做任何诊断。

---

## 三十秒跑起来

```powershell
cd D:\tanxin
copy .env.example .env          # 然后填入 DEEPSEEK_API_KEY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000 --no-server-header
```

打开 <http://127.0.0.1:8000/> ，点任一案例 → 开始谈话。

装依赖：`.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`

---

## 现在能做什么

| 能力 | 状态 |
|---|---|
| 文字对练（打字） | ✅ 完整可用 |
| 语音对练（说话 → 学生语音回答） | ✅ 浏览器识别；服务端识别待装 FunASR |
| 随时打断学生 | ⚠️ 有本地检测，真双工待接实时语音服务 |
| 结束后复盘评分 | ⬜ 页面是版式样例，评分链路未做 |
| 训练记录列表 | ⬜ 同上 |
| 案例导入 | ⬜ 只有表单流程，不落库 |

详细进度见 [`docs/CHANGELOG.md`](docs/CHANGELOG.md)。

---

## 目录结构

```
backend/
  app/
    api/          HTTP 与 WebSocket 端点（只做参数校验和转发）
    services/     业务逻辑（角色设定、守卫、一轮对话的编排）
    providers/    语音与模型的可插拔实现（换厂商只改这里）
    db/           建表语句与全部 SQL
    config.py     所有配置项
  services/funasr_server.py   本地离线识别服务（独立进程）
  tests/        42 条自动化测试
frontend/       原生 HTML+JS，无构建步骤
  js/           语音采集、识别、朗读、状态机
tools/caddy/    静态页与 WebSocket 的反向代理配置
docs/           设计文档、架构说明、变更记录
scripts/        边界检查、数据库备份、端到端自检
```

---

## 三条硬约束

违反任意一条，代码会被 `scripts/check_boundaries.py` 拦下。

1. **HTTP 只能在 `providers/` 里发** —— 其他层想调外部服务，加一个 Provider 实现。
2. **SQL 只能写在 `db/` 里** —— 业务层不许出现 `SELECT / INSERT / UPDATE / DELETE`。
3. **私有设定只能被 `services/persona.py` 读取** —— 学生的隐藏背景永不出接口、不进日志。

---

## 改代码之前

先读这三份，按顺序：

1. [`docs/架构说明.md`](docs/架构说明.md) —— 分层、数据流、Provider 怎么加
2. [`CONTRIBUTING.md`](CONTRIBUTING.md) —— 分支、提交、必跑的检查
3. [`docs/语音链路与降级.md`](docs/语音链路与降级.md) —— 语音怎么走、弱机怎么降级

每次提交前跑：

```powershell
python scripts\check_boundaries.py
python -m pytest backend\tests
```

---

## 代码托管

- **主仓库**：`git@github.com:joystudying/TanXinXiaoFu.git`
- 个人备份：`git@github.com:lovezexiaoze/tanxin.git`

当前开发分支 `integrate`。

```powershell
git add -A
git commit -m "说明"
git push collab integrate
```

---

## 配置项

全部在 `.env`（不进仓库），模板见 [`.env.example`](.env.example)。

最常改的三个：

| 变量 | 作用 | 默认 |
|---|---|---|
| `ASR_PROVIDER` | 语音识别用谁：`stub` 不接 / `funasr` 本地服务 | `stub` |
| `TTS_PROVIDER` | 语音合成用谁：`edge` 微软在线 / `stub` 不发声 | `edge` |
| `DEEPSEEK_API_KEY` | 扮演学生的模型密钥 | 空（启动会报错） |

---

## 已知限制

- **语音识别目前依赖浏览器**（Chrome / Edge 自带的在线识别），Firefox 不支持。
  想让任何浏览器都能用，需要启动 `backend/services/funasr_server.py` 并把 `ASR_PROVIDER` 改成 `funasr`。
- **不是真双工**：现在的流程是「你说完 → 学生回答」，不能两人同时说。
  真双工要接端到端实时语音服务，见 [`docs/语音链路与降级.md`](docs/语音链路与降级.md)。
- FunASR 需要 **Python 3.10/3.11** 的独立环境，不要和主后端混装。
