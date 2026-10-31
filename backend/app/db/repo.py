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
    conn = sqlite3.connect(
        db,
        isolation_level=None,   # 自动提交，事务在需要处显式 BEGIN IMMEDIATE
        check_same_thread=False,  # 连接的创建（线程池里的依赖注入）和 async 处理函数不是同一线程
    )
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


# ---------- 幂等与一轮对话（设计文档 7.3 / 9.4 / 11.2） ----------

RATE_LIMIT_PER_MINUTE = 10


def count_recent_requests(conn: sqlite3.Connection, session_id: str, seconds: int = 60) -> int:
    """近 N 秒内该会话发起的请求数，用于限流（6.4）。

    注意：created_at 存的是带 +08:00 的本地时间，不能用 SQL 的 datetime('now')（那是 UTC）
    直接比字符串，否则永远为真。这里统一截到秒再按本地时间比较。
    """
    cutoff = (datetime.now(TZ) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S")
    return conn.execute(
        "SELECT COUNT(*) AS n FROM request_log "
        "WHERE session_id=? AND substr(created_at, 1, 19) >= ?",
        (session_id, cutoff),
    ).fetchone()["n"]


def _next_turn_no(conn: sqlite3.Connection, session_id: str) -> int:
    return conn.execute(
        "SELECT COALESCE(MAX(turn_no), 0) + 1 AS n FROM turns WHERE session_id=?", (session_id,)
    ).fetchone()["n"]


def begin_turn(conn: sqlite3.Connection, *, session_id: str, text: str,
               key: str, req_hash: str, source: str = "text") -> dict:
    """占幂等键 + 分配 turn_no + 写老师那句。整个过程在一个写事务里。

    返回：
      {"status":"new",       "turn_no": N}
      {"status":"duplicate", "response": {...}}   # 同 key 已完成
      {"status":"in_flight"}                       # 同 key 或同会话还有请求在跑
      {"status":"mismatch"}                        # 同 key 不同内容
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        # 1) 会话级串行：本会话只要还有 pending，就拒绝新请求（技术路径文档 D-3）
        pending = conn.execute(
            "SELECT idempotency_key FROM request_log WHERE session_id=? AND status='pending' LIMIT 1",
            (session_id,),
        ).fetchone()
        if pending is not None:
            conn.execute("ROLLBACK")
            return {"status": "in_flight"}

        # 2) 占键
        ts = now_iso()
        cur = conn.execute(
            "INSERT INTO request_log(idempotency_key, session_id, request_hash, status, created_at, updated_at) "
            "VALUES(?,?,?, 'pending', ?, ?) ON CONFLICT(idempotency_key) DO NOTHING",
            (key, session_id, req_hash, ts, ts),
        )

        if cur.rowcount == 0:  # 键已存在
            row = conn.execute(
                "SELECT * FROM request_log WHERE idempotency_key=?", (key,)
            ).fetchone()
            if row["request_hash"] != req_hash:
                conn.execute("ROLLBACK")
                return {"status": "mismatch"}
            if row["status"] == "done":
                conn.execute("ROLLBACK")
                return {"status": "duplicate", "response": json.loads(row["response_json"])}
            if row["status"] == "failed":
                # 技术路径文档 D-1：失败后允许同 key 重试，重置为 pending 继续
                conn.execute(
                    "UPDATE request_log SET status='pending', updated_at=? WHERE idempotency_key=?",
                    (ts, key),
                )
            else:
                conn.execute("ROLLBACK")
                return {"status": "in_flight"}

        # 3) 分配轮次 + 写老师那句
        turn_no = _next_turn_no(conn, session_id)
        conn.execute(
            "INSERT INTO turns(session_id, turn_no, role, text, source, created_at) "
            "VALUES(?,?, 'teacher', ?,?,?)",
            (session_id, turn_no, text, source, now_iso()),
        )
        conn.execute(
            "UPDATE sessions SET status='active' WHERE id=? AND status='created'", (session_id,)
        )
        conn.execute("COMMIT")
        return {"status": "new", "turn_no": turn_no}
    except Exception:
        conn.execute("ROLLBACK")
        raise


def finish_turn(conn: sqlite3.Connection, *, key: str, session_id: str, turn_no: int,
                reply: str, usage: dict, latency_ms: int) -> dict:
    """写学生那句 + 缓存响应。返回给前端的响应体。"""
    student_no = turn_no + 1
    response = {"turn_no": student_no, "reply_text": reply}

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO turns(session_id, turn_no, role, text, source, created_at) "
            "VALUES(?,?, 'student', ?, 'text', ?)",
            (session_id, student_no, reply, now_iso()),
        )
        conn.execute(
            "UPDATE request_log SET status='done', turn_no=?, response_json=?, tokens_in=?, "
            "tokens_out=?, latency_ms=?, updated_at=? WHERE idempotency_key=?",
            (
                turn_no,
                json.dumps(response, ensure_ascii=False),
                (usage or {}).get("prompt_tokens", 0),
                (usage or {}).get("completion_tokens", 0),
                latency_ms,
                now_iso(),
                key,
            ),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return response


def fail_turn(conn: sqlite3.Connection, *, key: str, session_id: str,
              turn_no: int, latency_ms: int = 0) -> None:
    """失败回滚：删掉老师那句，request_log 置 failed（技术路径文档 D-2）。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "DELETE FROM turns WHERE session_id=? AND turn_no=?", (session_id, turn_no)
        )
        conn.execute(
            "UPDATE request_log SET status='failed', latency_ms=?, updated_at=? "
            "WHERE idempotency_key=?",
            (latency_ms, now_iso(), key),
        )
        # 若本次是会话的第一句，把状态退回 created，保持状态机干净
        left = conn.execute(
            "SELECT COUNT(*) AS n FROM turns WHERE session_id=?", (session_id,)
        ).fetchone()["n"]
        if left == 0:
            conn.execute(
                "UPDATE sessions SET status='created' WHERE id=? AND status='active'", (session_id,)
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
