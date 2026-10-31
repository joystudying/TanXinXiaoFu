"""持久化：把每一轮对练写进数据库，供后续「回听 / 复盘 / 证据评价」使用。"""
from sqlalchemy import select

from .db import SessionLocal
from .models import Turn


async def save_turn(
    session_id: str,
    scenario: str,
    role: str,
    text: str,
    emotion: str | None = None,
) -> None:
    async with SessionLocal() as session:
        session.add(
            Turn(
                session_id=session_id,
                scenario=scenario,
                role=role,
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
