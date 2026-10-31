"""会话接口（设计文档 6.1 / 6.2 / 6.3 / 6.5）。"""
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import errors
from ..db import repo
from ..deps import get_db

router = APIRouter()


class CreateSessionIn(BaseModel):
    case_id: str = Field(min_length=1)
    prep_note: str | None = Field(default=None, max_length=2000)


class EndSessionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


def _public_case(case_row) -> dict:
    """只回公开字段；private_json 永不出现（6.1 规则）。"""
    return {
        "id": case_row["id"],
        "version": case_row["version"],
        "category": case_row["category"],
        "public": json.loads(case_row["public_json"]),
    }


@router.post("/api/sessions", status_code=201)
def create_session(payload: CreateSessionIn, db=Depends(get_db)):
    case_row = repo.get_case(db, payload.case_id)
    if case_row is None:
        raise errors.ApiError(404, "case_not_found", "案例不存在", False)

    row = repo.create_session(
        db,
        case_id=case_row["id"],
        case_version=case_row["version"],
        prep_note=(payload.prep_note or "").strip() or None,
    )
    return {
        "session_id": row["id"],
        "case": _public_case(case_row),
        "prep_note": row["prep_note"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


@router.get("/api/sessions/{session_id}")
def get_session(session_id: str, db=Depends(get_db)):
    row = repo.get_session(db, session_id)
    if row is None:
        raise errors.ApiError(404, "session_not_found", "会话不存在", False)
    return {
        "session_id": row["id"],
        "case_id": row["case_id"],
        "case_version": row["case_version"],
        "status": row["status"],
        "prep_note": row["prep_note"],
        "created_at": row["created_at"],
        "ended_at": row["ended_at"],
        "turn_count": repo.count_turns(db, session_id),
    }


@router.get("/api/sessions/{session_id}/turns")
def get_turns(session_id: str, db=Depends(get_db)):
    if repo.get_session(db, session_id) is None:
        raise errors.ApiError(404, "session_not_found", "会话不存在", False)
    rows = repo.get_turns(db, session_id)
    return {
        "session_id": session_id,
        "turns": [
            {"turn_no": r["turn_no"], "role": r["role"], "text": r["text"], "created_at": r["created_at"]}
            for r in rows
        ],
    }


@router.post("/api/sessions/{session_id}/end")
def end_session(session_id: str, payload: EndSessionIn | None = None, db=Depends(get_db)):
    if repo.get_session(db, session_id) is None:
        raise errors.ApiError(404, "session_not_found", "会话不存在", False)
    row = repo.end_session(db, session_id)
    return {
        "session_id": row["id"],
        "status": row["status"],
        "ended_at": row["ended_at"],
        "turn_count": repo.count_turns(db, session_id),
    }
