"""转写记录：对应文档里「带角色与轮次的对话记录（文字/音频/角色/轮次/时间）」。

当前先存文字维度（角色/轮次/时间/情绪）；音频文件落盘可作为后续增强。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    scenario: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default="user")  # teacher | student
    mode: Mapped[str] = mapped_column(String(16), default="pipeline")  # pipeline | realtime
    text: Mapped[str] = mapped_column(Text, default="")
    emotion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Evaluation(Base):
    """复盘评价结果：一次会话的五维评分 + 证据 + 建议。

    「角色与评价分离」——评价结果独立存储，与对话转写分开。
    dimensions 形如 [{name, score, comment, evidence:[...]}, ...]，共五维。
    """

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    scenario: Mapped[str] = mapped_column(String(64), default="")
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    dimensions: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    suggestions: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="done")  # done | error
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Case(Base):
    """案例库：6 类 × 3 例 = 18 个学生案例。

    公开层（name / grade_major / tagline / public_background / goals / …）给前端；
    私有层（hidden_background / speech_style / branches / opening）只在服务端进 system prompt。
    """

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True, default="")
    name: Mapped[str] = mapped_column(String(32), default="")
    grade_major: Mapped[str] = mapped_column(String(64), default="")
    tagline: Mapped[str] = mapped_column(String(128), default="")
    quote: Mapped[str] = mapped_column(String(255), default="")
    public_background: Mapped[str] = mapped_column(Text, default="")
    goals: Mapped[list] = mapped_column(JSON, default=list)
    training_focus: Mapped[str] = mapped_column(String(128), default="")
    duration: Mapped[str] = mapped_column(String(32), default="")
    avatar: Mapped[str] = mapped_column(String(128), default="")
    # 私有层（仅服务端）
    hidden_background: Mapped[str] = mapped_column(Text, default="")
    speech_style: Mapped[str] = mapped_column(Text, default="")
    branches: Mapped[list] = mapped_column(JSON, default=list)
    opening: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)


class TrainingSession(Base):
    """训练会话：谈前笔记 + 状态机地基（为后续「进行中 / 已结束 / 重练关联」预留）。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    case_version: Mapped[int] = mapped_column(Integer, default=1)
    prep_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="created")  # created|active|ended
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
