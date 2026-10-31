# 参与指南

给要改这个项目的人（包括三个月后的自己）。照着做就不会踩坑。

---

## 一、先把项目跑起来

```powershell
git clone git@github.com:joystudying/TanXinXiaoFu.git
cd TanXinXiaoFu
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
copy .env.example .env           # 填 DEEPSEEK_API_KEY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000 --no-server-header
```

浏览器打开 <http://127.0.0.1:8000/>，能看到「场景选择」就说明通了。

**没有密钥也能跑起来吗**：不能。启动自检会直接报错退出并告诉你缺什么。这是故意的——
宁可启动失败，也不要跑到一半才发现模型调不通。

---

## 二、分支与提交

| 分支 | 用途 |
|---|---|
| `main` | 随时可以演示的稳定版 |
| `integrate` | 当前开发分支（合并了两边的成果） |
| `feature/xxx` | 你自己的一次改动 |

提交信息写清楚**做了什么、为什么**：

```
好： M4: 加 WebSocket 语音通道，复用 turn_engine 避免逻辑分叉
差： update
```

### 提交前必须跑（两条都不能红）

```powershell
python scripts\check_boundaries.py     # 分层边界
python -m pytest backend\tests         # 42 条测试
```

改了数据库结构，先备份：

```powershell
.\scripts\backup-db.ps1
```

---

## 三、代码放在哪

先看这张表，再决定文件写在哪个目录。写错目录会被边界检查拦下。

| 你想做的事 | 写在哪 | 不许做什么 |
|---|---|---|
| 加一个 HTTP 接口 | `backend/app/api/` | 不许写 SQL、不许 import httpx |
| 加业务逻辑 | `backend/app/services/` | 不许写 SQL、不许直接发 HTTP |
| 接一个新的语音/模型厂商 | `backend/app/providers/` | 不许 import `db` |
| 加表、加查询 | `backend/app/db/` | 不许 import `services` |
| 改页面 | `frontend/` | 不许把私有设定写进前端 |

### 一次对话是怎么走完的（最重要的数据流）

```
前端 → api/chat.py（校验参数）
     → services/turn_engine.py::run_turn()   ← 所有业务都在这
         → db/repo.py      占幂等键、分配轮次、写老师这句话
         → services/persona.py   把案例拼成 system prompt（唯一读私有设定的地方）
         → services/guard.py     注入检测
         → services/model.py     调模型
         → services/guard.py     检查输出有没有泄露私有设定
         → db/repo.py      写学生回答、标记完成
     → 返回
```

**REST 和 WebSocket 都走这一个 `run_turn()`。**
不要为某个端点单独写一套流程，两边一定会慢慢分叉。

---

## 四、怎么加一个新的厂商（最常见的改动）

以「把语音合成换成火山引擎」为例，三步：

**第 1 步** 在 `backend/app/providers/` 下新建 `tts_volcengine.py`：

```python
from .base import TTSProvider, TTSResult

class VolcengineTTSProvider(TTSProvider):
    async def synthesize(self, text: str) -> TTSResult:
        # 你的实现
        return TTSResult(audio=mp3_bytes, format="mp3")
```

**第 2 步** 在 `providers/__init__.py` 的 `get_tts()` 里加一个分支：

```python
if settings.tts_provider == "volcengine":
    _tts = VolcengineTTSProvider()
```

**第 3 步** 在 `.env` 里改一行：

```
TTS_PROVIDER=volcengine
```

业务代码一行都不用动。这就是 Provider 层存在的意义。

---

## 五、几个必须知道的约定

### 不要用 `str.format` 拼提示词

案例文本里有花括号就会炸。用 `str.replace` 或 `string.Template`。
`services/persona.py` 里已有例子。

### 私有设定只有一个出口

学生的「真实困扰 / 家庭情况 / 透露条件」存在 `cases.private_json`，
只能被 `services/persona.py` 读取，拼进 system prompt。

**不许**：返回给前端、写日志、存进 turns 表、放进错误信息。

加完功能想验证，跑 `pytest backend\tests\test_guard.py`。

### 数据库连接用完必须关

`repo.connect()` 每个请求开一个。用完不关会把 SQLite 锁住，
下一个请求全部超时——这个坑已经踩过一次。

### 前端不跑模型

客户端只做三件事：收音、放音、显示。所有重活都在服务端。
这样低配电脑和老浏览器也能用。

---

## 六、常见故障

| 现象 | 原因 | 怎么修 |
|---|---|---|
| 启动报「缺少 DEEPSEEK_API_KEY」 | `.env` 没填 | 填上，注意不要提交到 git |
| 所有接口 500 | 多半是数据库被占 | 检查有没有进程没关连接 |
| 语音识别没反应 | Firefox 不支持 | 换 Chrome/Edge，或起 FunASR |
| 朗读没声音 | 系统没中文音色 | 换 Edge 浏览器，或改用服务端 TTS |
| `check_boundaries` 报 FAIL | 分层写错了 | 看报错的文件和目录，按第三节的表挪 |

---

## 七、改完怎么证明它好用

不要只说「改好了」，给证据：

1. `pytest` 输出（多少条通过）
2. 关键接口的实测请求与响应
3. 页面截图或操作步骤

`docs/CHANGELOG.md` 里每个版本都按这个格式写，照着来就行。
