# 谈心小辅 · 语音对话模块

辅导员 ↔ 虚拟学生的语音对练原型。设计与验收标准全部以
[`docs/语音对话模块-技术设计文档.md`](docs/语音对话模块-技术设计文档.md) 为准（v1.0）。

## 当前状态

环境已就绪，还没写业务代码。下一步是文档第 20 节的 **M0 骨架**。

| 项 | 状态 |
|---|---|
| 目录结构 | 已按设计文档 4.4 建好 |
| 虚拟环境 `D:\tanxin\.venv` | 已建（Python 3.12.10） |
| 依赖 | 已装（见下表） |
| `backend/app/db/schema.sql` | 已写好，实测建表通过（4 表 + 3 索引） |
| `.env` | **未创建**，需要填 DeepSeek key |
| 业务代码 | 未开始 |

## 已安装依赖（严格按文档 4.2，未额外添加）

| 包 | 版本 |
|---|---|
| fastapi | 0.162.0 |
| uvicorn | 0.54.0 |
| httpx | 0.28.1 |
| pydantic | 2.14.2 |
| pydantic-settings | 2.16.2 |
| python-dotenv | 1.2.4 |
| pytest | 9.2.0 |
| pytest-asyncio | 1.4.1 |

SQLite 3.49.1（Python 内置）。

## 怎么跑

```powershell
cd D:\tanxin
Copy-Item .env.example .env      # 然后填 DEEPSEEK_API_KEY
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --app-dir backend --reload --port 8000
```

浏览器打开 <http://127.0.0.1:8000/>

## 目录

```
tanxin/
├─ backend/
│  ├─ app/
│  │  ├─ api/          # health / sessions / chat / tts
│  │  ├─ services/     # model（唯一 HTTP 出口）/ persona（唯一读私设）/ turns / guard
│  │  └─ db/           # schema.sql（已写）+ repo.py（待写）
│  ├─ tests/
│  └─ requirements.txt
├─ frontend/           # voice.html + js/{speech,vad,speak,chat}.js
├─ data/               # tanxin.db 运行期生成，不进 git
├─ docs/               # 设计文档 + 待确认问题
└─ .env.example
```

## 三条硬约束（来自设计文档，写代码时不许破）

1. 模型调用只能经 `services/model.py`，SQL 只能出现在 `db/repo.py`；
2. 私有设定只能被 `services/persona.py` 读取，永不出接口、不进日志；
3. 不加设计文档 4.2 之外的新依赖，要加必须改文档说明理由。
