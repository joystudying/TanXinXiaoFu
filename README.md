# 谈心小辅 · 语音对话模块

辅导员 ↔ 虚拟学生的语音对练原型。

## 文档（先读这里）

| 文档 | 作用 |
|---|---|
| [`docs/语音对话模块-技术设计文档.md`](docs/语音对话模块-技术设计文档.md) | 需求与验收标准（v1.0，权威） |
| [`docs/技术路径文档.md`](docs/技术路径文档.md) | **代码怎么分层、改的时候动哪里、怎么备份** |
| [`docs/待确认问题.md`](docs/待确认问题.md) | 六项决策的结论 + 历史提问 |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | 每个里程碑改了什么、怎么验的 |

## 当前进度

| 里程碑 | 状态 |
|---|---|
| M0 骨架（health / 静态页 / 缺 key 退出） | ✅ |
| M1 存储与案例（建表 / 案例 / 会话接口） | ✅ |
| M2 模型与单轮（`/api/chat` + 幂等） | ⬜ 下一步 |
| M3–M6 | ⬜ |

## 怎么跑

```powershell
cd D:\tanxin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000 --reload --no-server-header
```

浏览器打开 <http://127.0.0.1:8000/>

`.env` 已配置（不进 git）。`GET /api/health` 应返回 `{"ok":true,...}`。

## 日常操作

```powershell
# 分层边界检查（改完代码就跑）
python scripts\check_boundaries.py

# 数据库备份（改 schema 之前必须做）
.\scripts\backup-db.ps1

# 代码回滚到某个里程碑
git checkout m1 -- backend/
```

## 三条硬约束

1. 模型调用只能经 `services/model.py`，SQL 只能出现在 `db/repo.py`；
2. 私有设定只能被 `services/persona.py` 读取，永不出接口、不进日志；
3. 不加设计文档 4.2 之外的新依赖。

改完代码跑 `python scripts\check_boundaries.py`，它会替你检查前两条。