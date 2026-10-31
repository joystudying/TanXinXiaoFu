"""唯一 SQL 出口（设计文档 9.4 / 硬约束 1）。"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    """ISO 8601 带时区，如 2026-10-28T10:12:03+08:00。"""
    return datetime.now(TZ).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    db = settings.db_file
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    _seed_cases(conn)


# 设计文档 7.5 的示例案例（演示用虚构数据）
EXAMPLE_CASE = {
    "id": "c_academic_01",
    "version": 1,
    "category": "academic",
    "label": "小陈 · 学业困难",
    "public_json": {
        "alias": "小陈",
        "grade": "大二",
        "major": "环境工程",
        "concern": "连续两周缺课，三次作业未交",
        "origin": "任课老师反馈",
        "goal": "理解困难来源，讨论可行的第一步",
    },
    "private_json": {
        "real_issue": "父亲生病住院，他在做兼职补贴家用，晚上在便利店值班到凌晨两点",
        "why_hidden": "觉得说了像在卖惨，也怕学校通知家里",
        "reveal_rule": "老师连续两次问到睡眠或时间安排，并且没有急着给建议时，才松口说出兼职",
        "family": "父母离异，跟父亲生活",
        "expression": "句子短，常用「就……还行吧」；被追问时会先沉默（用「……」表示）再转移话题",
    },
    "review_status": "draft",
}


def _seed_cases(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"] > 0:
        return
    c = EXAMPLE_CASE
    ts = now_iso()
    conn.execute(
        "INSERT INTO cases(id, version, category, label, public_json, private_json, "
        "review_status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            c["id"], c["version"], c["category"], c["label"],
            json.dumps(c["public_json"], ensure_ascii=False),
            json.dumps(c["private_json"], ensure_ascii=False),
            c["review_status"], ts, ts,
        ),
    )
    conn.commit()


# ---------- 案例 ----------

def get_case(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()


# ---------- 会话 ----------

def _next_session_id(conn: sqlite3.Connection) -> str:
    day = datetime.now(TZ).strftime("%Y%m%d")
    prefix = f"s_{day}_"
    row = conn.execute(
        "SELECT id FROM sessions WHERE id LIKE ? ORDER BY id DESC LIMIT 1", (prefix + "%",)
    ).fetchone()
    seq = 1 if row is None else int(row["id"].rsplit("_", 1)[1]) + 1
    return f"{prefix}{seq:04d}"


def create_session(conn: sqlite3.Connection, *, case_id: str, case_version: int,
                   prep_note: str | None, prev_session_id: str | None = None) -> sqlite3.Row:
    sid = _next_session_id(conn)
    conn.execute(
        "INSERT INTO sessions(id, case_id, case_version, prep_note, status, created_at, prev_session_id) "
        "VALUES(?,?,?,?, 'created', ?, ?)",
        (sid, case_id, case_version, prep_note, now_iso(), prev_session_id),
    )
    conn.commit()
    return get_session(conn, sid)


def get_session(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()


def end_session(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    conn.execute(
        "UPDATE sessions SET status='ended', ended_at=? WHERE id=? AND status<>'ended'",
        (now_iso(), session_id),
    )
    conn.commit()
    return get_session(conn, session_id)


# ---------- 轮次 ----------

def get_turns(conn: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT turn_no, role, text, created_at FROM turns WHERE session_id=? ORDER BY turn_no",
        (session_id,),
    ).fetchall()


def count_turns(conn: sqlite3.Connection, session_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM turns WHERE session_id=?", (session_id,)
    ).fetchone()["n"]
