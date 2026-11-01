"""复盘评价 REST 端点：对一次会话的转写做五维评分 + 证据复盘。"""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.evaluator import build_rubric_text, turns_to_transcript
from ..providers import build_evaluator
from ..repo import get_evaluation, list_sessions, list_turns, save_evaluation

router = APIRouter(prefix="/sessions", tags=["sessions"])

evaluator = build_evaluator()


class ReviewResponse(BaseModel):
    session_id: str
    scenario: str
    total_score: int
    dimensions: list
    summary: str
    suggestions: str
    turns: list = []   # [{role, mode, text}]，按发言顺序，供前端展示完整对话


class SessionSummary(BaseModel):
    session_id: str
    scenario: str
    started_at: datetime
    turn_count: int
    total_score: int | None = None
    reviewed: bool = False


@router.get("", response_model=list[SessionSummary])
async def sessions_list() -> list[SessionSummary]:
    return [SessionSummary(**s) for s in await list_sessions()]


@router.get("/{session_id}/review", response_model=ReviewResponse)
async def get_review(session_id: str) -> ReviewResponse:
    e = await get_evaluation(session_id)
    if e is None:
        raise HTTPException(404, "该会话尚未生成复盘")
    return await _to_response(session_id, e)


@router.post("/{session_id}/review", response_model=ReviewResponse)
async def create_review(session_id: str) -> ReviewResponse:
    turns = await list_turns(session_id)
    if not turns:
        raise HTTPException(404, "该会话没有对话记录")

    scenario = turns[0].scenario
    transcript = turns_to_transcript(turns)
    if not transcript.strip():
        raise HTTPException(422, "该会话缺少老师侧对话，无法生成复盘")
    result = await evaluator.evaluate(transcript, build_rubric_text())

    await save_evaluation(
        session_id,
        scenario,
        result.total_score,
        result.dimensions,
        result.summary,
        result.suggestions,
    )
    return ReviewResponse(
        session_id=session_id,
        scenario=scenario,
        total_score=result.total_score,
        dimensions=result.dimensions,
        summary=result.summary,
        suggestions=result.suggestions,
        turns=[{"role": t.role, "mode": t.mode, "text": t.text} for t in turns],
    )


async def _to_response(session_id: str, e) -> ReviewResponse:
    turns = await list_turns(session_id)
    return ReviewResponse(
        session_id=session_id,
        scenario=e.scenario,
        total_score=e.total_score,
        dimensions=e.dimensions,
        summary=e.summary,
        suggestions=e.suggestions,
        turns=[{"role": t.role, "mode": t.mode, "text": t.text} for t in turns],
    )
