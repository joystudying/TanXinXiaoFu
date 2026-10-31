# -*- coding: utf-8 -*-
"""幂等（设计文档 16.1 test_idempotency.py / 11.2）。"""
import uuid

from app import deps
from app.config import settings
from app.db import repo


def _turns(client, sid):
    return client.get(f"/api/sessions/{sid}/turns").json()["turns"]


def test_same_key_returns_cache_without_calling_model(client, mk_session, fake_model):
    sid = mk_session()
    key = "key-idem-0001"
    payload = {"session_id": sid, "text": "最近怎么样", "idempotency_key": key}

    first = client.post("/api/chat", json=payload)
    assert first.status_code == 200
    assert fake_model["n"] == 1

    second = client.post("/api/chat", json=payload)
    assert second.status_code == 200
    assert fake_model["n"] == 1, "同 key 重试不应再调模型"
    assert second.json()["reply_text"] == first.json()["reply_text"]
    assert second.json()["turn_no"] == first.json()["turn_no"]
    assert second.json().get("cached") is True

    assert len(_turns(client, sid)) == 2, "重复提交不应多写轮次"


def test_same_key_different_text_is_mismatch(client, mk_session, fake_model):
    sid = mk_session()
    key = "key-idem-0002"
    client.post("/api/chat", json={"session_id": sid, "text": "第一句", "idempotency_key": key})

    r = client.post("/api/chat", json={"session_id": sid, "text": "换了内容", "idempotency_key": key})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "idempotency_mismatch"


def test_pending_request_blocks_new_one(client, mk_session, fake_model):
    """会话级串行：还有 pending 时，新请求一律 409（技术路径文档 D-3）。"""
    sid = mk_session()
    conn = repo.connect()
    try:
        conn.execute(
            "INSERT INTO request_log(idempotency_key, session_id, request_hash, status, created_at, updated_at) "
            "VALUES(?,?,?, 'pending', datetime('now'), datetime('now'))",
            (str(uuid.uuid4()), sid, "fake-hash"),
        )
    finally:
        conn.close()

    r = client.post("/api/chat", json={
        "session_id": sid, "text": "插一句", "idempotency_key": "key-idem-0003",
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "duplicate_in_flight"
    assert fake_model["n"] == 0


def test_rate_limit(client, mk_session, fake_model):
    """同会话 60 秒内最多 10 次（6.4）。"""
    sid = mk_session()
    for i in range(repo.RATE_LIMIT_PER_MINUTE):
        r = client.post("/api/chat", json={
            "session_id": sid, "text": f"第{i}句", "idempotency_key": f"key-rate-{i:04d}",
        })
        assert r.status_code == 200, r.text

    r = client.post("/api/chat", json={
        "session_id": sid, "text": "第11句", "idempotency_key": "key-rate-9999",
    })
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert r.json()["error"]["retryable"] is True
