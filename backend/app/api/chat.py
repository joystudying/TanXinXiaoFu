"""POST /api/chat（设计文档 6.4 / 9.6）。编排在 services/turn_engine.py。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..db import repo
from ..deps import get_db
from ..services import turn_engine

router = APIRouter()

MAX_TEXT_LEN = turn_engine.MAX_TEXT_LEN


class ChatIn(BaseModel):
    session_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=MAX_TEXT_LEN)
    idempotency_key: str = Field(min_length=8, max_length=64)


@router.post("/api/chat")
async def chat(payload: ChatIn, request: Request, db=Depends(get_db)):
    result = await turn_engine.run_turn(
        db,
        session_id=payload.session_id,
        text=payload.text,
        idempotency_key=payload.idempotency_key,
        source="text",
    )
    result["request_id"] = request.state.request_id
    return result


# repo 在这里只是为了让边界检查（api 不直连数据库）保持可读；
# 真正的 SQL 全在 db/repo.py 里。
_ = repo
