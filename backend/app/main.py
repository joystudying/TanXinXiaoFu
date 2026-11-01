"""谈心小辅 · 语音对练后端入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers.sessions import router as sessions_router
from .ws.chat import router as chat_router
from .ws.voice import router as voice_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


settings = get_settings()
app = FastAPI(title="谈心小辅 · 语音对练", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(sessions_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
