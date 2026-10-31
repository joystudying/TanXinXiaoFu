"""FastAPI 入口：自检、CORS、请求号、路由、静态页（设计文档 2.1 / 4.6）。"""
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import errors
from .api import chat, health, sessions
from .config import settings
from .db import repo


def _self_check() -> list[str]:
    """启动自检三件事：数据库可写、key 存在、静态目录存在。"""
    problems: list[str] = []

    if not settings.model_configured:
        problems.append(
            "缺少 DEEPSEEK_API_KEY：请把 key 写进 D:\\tanxin\\.env 的 DEEPSEEK_API_KEY 一行"
        )

    if not settings.frontend_dir.exists():
        problems.append(f"静态目录不存在：{settings.frontend_dir}")

    try:
        conn = repo.connect()
        try:
            repo.init_db(conn)
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"数据库不可用（{settings.db_file}）：{exc}")

    return problems


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = _self_check()
    if problems:
        print("\n启动失败：", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        print("", file=sys.stderr)
        raise RuntimeError("启动自检未通过，服务未启动")

    print(f"\n谈心小辅 语音对话模块 v{health.VERSION}")
    print(f"  数据库   {settings.db_file}")
    print(f"  模型     {settings.model_name} @ {settings.model_base_url}")
    print(f"  访问     http://127.0.0.1:8000/\n")
    yield


app = FastAPI(title="谈心小辅 · 语音对话模块", version=health.VERSION, lifespan=lifespan)

errors.install(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_id(request: Request, call_next):
    rid = "req_" + uuid.uuid4().hex[:8]
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(chat.router)


@app.get("/", include_in_schema=False)
def _root():
    """根路径直接给语音页（设计文档 4.4 的文件名是 voice.html）。"""
    from fastapi.responses import FileResponse

    return FileResponse(settings.frontend_dir / "voice.html")


# 静态页挂根路径（必须在 API 路由之后注册）
app.mount("/", StaticFiles(directory=str(settings.frontend_dir), html=True), name="static")
