"""异步数据库：默认 SQLite（开箱即用），改 DATABASE_URL 可切 PostgreSQL。"""
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    url = get_settings().database_url
    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移：create_all 不会给已存在的表加列，老库手动补
        if url.startswith("sqlite"):
            cols = (await conn.execute(text("PRAGMA table_info(turns)"))).fetchall()
            if "mode" not in {row[1] for row in cols}:
                await conn.execute(text(
                    "ALTER TABLE turns ADD COLUMN mode VARCHAR(16) NOT NULL DEFAULT 'pipeline'"
                ))
            cols = (await conn.execute(text("PRAGMA table_info(cases)"))).fetchall()
            if "tags" not in {row[1] for row in cols}:
                await conn.execute(text("ALTER TABLE cases ADD COLUMN tags JSON DEFAULT '[]'"))
        else:
            # PostgreSQL：补 cases.tags（检索关键词）
            await conn.execute(text(
                "ALTER TABLE cases ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::jsonb"
            ))

    # 案例库种子：cases 表为空时写入 18 条（公开 + 私有两层）
    from .core.cases import SEED_CASES
    from .repo import seed_cases_if_empty

    await seed_cases_if_empty(SEED_CASES)
