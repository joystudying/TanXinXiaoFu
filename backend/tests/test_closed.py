# -*- coding: utf-8 -*-
"""会话结束与参数校验（设计文档 16.1 test_closed.py）。"""


def test_chat_after_end_returns_409(client, mk_session, fake_model):
    sid = mk_session()
    client.post(f"/api/sessions/{sid}/end", json={"reason": "训练完成"})

    r = client.post("/api/chat", json={
        "session_id": sid, "text": "还能说吗", "idempotency_key": "key-cl-0001",
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "session_closed"
    assert fake_model["n"] == 0


def test_chat_unknown_session(client, fake_model):
    r = client.post("/api/chat", json={
        "session_id": "s_nope", "text": "你好", "idempotency_key": "key-cl-0002",
    })
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "session_not_found"


def test_chat_text_too_long(client, mk_session, fake_model):
    sid = mk_session()
    r = client.post("/api/chat", json={
        "session_id": sid, "text": "啊" * 501, "idempotency_key": "key-cl-0003",
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "bad_request"


def test_chat_blank_text(client, mk_session, fake_model):
    sid = mk_session()
    r = client.post("/api/chat", json={
        "session_id": sid, "text": "   ", "idempotency_key": "key-cl-0004",
    })
    assert r.status_code == 422
    assert fake_model["n"] == 0


def test_chat_missing_key(client, mk_session, fake_model):
    sid = mk_session()
    r = client.post("/api/chat", json={"session_id": sid, "text": "你好"})
    assert r.status_code == 422


def test_turn_count_after_end(client, mk_session, fake_model):
    sid = mk_session()
    client.post("/api/chat", json={
        "session_id": sid, "text": "第一句", "idempotency_key": "key-cl-0005",
    })
    r = client.post(f"/api/sessions/{sid}/end", json={"reason": "结束"})
    assert r.json()["turn_count"] == 2
