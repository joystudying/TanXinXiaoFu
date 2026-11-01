"""持久化：把每一轮对练写进数据库，供后续「回听 / 复盘 / 证据评价」使用。"""
from datetime import timezone

from sqlalchemy import case, func, select

from .db import SessionLocal
from .models import Evaluation, Turn


async def save_turn(
    session_id: str,
    scenario: str,
    role: str,
    text: str,
    emotion: str | None = None,
    mode: str = "pipeline",
) -> None:
    async with SessionLocal() as session:
        session.add(
            Turn(
                session_id=session_id,
                scenario=scenario,
                role=role,
                mode=mode,
                text=text,
                emotion=emotion,
            )
        )
        await session.commit()


async def list_turns(session_id: str) -> list[Turn]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Turn).where(Turn.session_id == session_id).order_by(Turn.id)
        )
        return list(result.scalars().all())


async def save_evaluation(
    session_id: str,
    scenario: str,
    total_score: int,
    dimensions: list,
    summary: str,
    suggestions: str,
) -> None:
    """写入/更新一次会话的复盘评价（session_id 唯一，重复评价则覆盖）。"""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Evaluation).where(Evaluation.session_id == session_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.scenario = scenario
            existing.total_score = total_score
            existing.dimensions = dimensions
            existing.summary = summary
            existing.suggestions = suggestions
            existing.status = "done"
        else:
            session.add(
                Evaluation(
                    session_id=session_id,
                    scenario=scenario,
                    total_score=total_score,
                    dimensions=dimensions,
                    summary=summary,
                    suggestions=suggestions,
                )
            )
        await session.commit()


async def get_evaluation(session_id: str) -> Evaluation | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Evaluation).where(Evaluation.session_id == session_id)
        )
        return result.scalar_one_or_none()


async def list_sessions() -> list[dict]:
    """列出所有「真正练过」的会话（时间 / 轮数 / 是否已复盘 / 得分）。

    只保留至少有一句老师侧发言的会话，避免把「仅学生开场」的空会话列进历史。
    """
    teacher_expr = case((Turn.role == "teacher", 1), else_=0)
    async with SessionLocal() as session:
        rows = await session.execute(
            select(
                Turn.session_id,
                func.max(Turn.scenario).label("scenario"),
                func.min(Turn.created_at).label("started_at"),
                func.count(Turn.id).label("turn_count"),
            )
            .group_by(Turn.session_id)
            .having(func.sum(teacher_expr) > 0)
            .order_by(func.min(Turn.created_at).desc())
        )
        sessions = [
            {
                "session_id": r.session_id,
                "scenario": r.scenario or "谈心谈话",
                "started_at": r.started_at.replace(tzinfo=timezone.utc),
                "turn_count": r.turn_count,
            }
            for r in rows.all()
        ]

    async with SessionLocal() as session:
        evals = (await session.execute(select(Evaluation))).scalars().all()
    by_session = {e.session_id: e for e in evals}
    for s in sessions:
        e = by_session.get(s["session_id"])
        s["total_score"] = e.total_score if e else None
        s["reviewed"] = e is not None
    return sessions
