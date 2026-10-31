# CHANGELOG

## M1 · 2026-10-31

**新增**
- `backend/app/db/schema.sql`：4 张表 + 3 个索引，实测建表通过
- 示例案例「小陈 · 学业困难」启动时自动灌入（设计文档 7.5）
- `POST /api/sessions`、`GET /api/sessions/{id}`、`GET /api/sessions/{id}/turns`、`POST /api/sessions/{id}/end`
- `GET /api/health`：db / model_configured / version
- 统一错误形状 `{"error":{code,message,retryable}}`，含 422 字段级说明
- 请求号中间件（`X-Request-Id`）、`Cache-Control: no-store`
- `frontend/voice.html`：M1 占位页（自检 + 建会话 + 查轮次）
- `scripts/check_boundaries.py`：四条分层边界检查
- `scripts/backup-db.ps1` / `backup_db.py`：SQLite 在线备份

**验证记录（curl，全部通过）**
```
GET  /api/health                    → 200 {"ok":true,"db":"ok","model_configured":true}
POST /api/sessions                  → 201 {"session_id":"s_20261031_0001", ... 仅公开字段}
GET  /api/sessions/{id}             → 200 status=created turn_count=0
GET  /api/sessions/{id}/turns       → 200 {"turns":[]}
POST /api/sessions/{id}/end         → 200 status=ended
GET  /api/sessions/s_nope           → 404 session_not_found
POST /api/sessions (缺 case_id)      → 422 bad_request + fields
GET  /                              → 200 静态页
响应头                               → x-request-id / cache-control: no-store / 无 server
```

**修掉的问题**
- `response.headers.pop("server")` — Starlette 的 MutableHeaders 没有 `pop`，导致所有请求 500；
  改用 uvicorn 的 `--no-server-header` 启动参数。
- 根路径 404 — `StaticFiles(html=True)` 只认 `index.html`，而设计文档指定文件名为 `voice.html`；
  改为显式 `FileResponse`。

**未做（后续里程碑）**
- `/api/chat`、幂等、私有设定注入、守卫（M2）
- 语音识别、朗读、状态机（M3）
- 打断、失败矩阵 14 条（M4）

**环境**
- Python 3.12.10 / SQLite 3.49.1 / fastapi 0.162.0 / uvicorn 0.54.0
- DeepSeek key 已配置并实测：HTTP 200，首包 776 ms
