# -*- coding: utf-8 -*-
"""正常一轮对话（设计文档 16.1 test_chat.py）。"""


def _turns(client, sid):
    return client.get(f"/api/sessions/{sid}/turns").json()["turns"]


def test_one_round(client, mk_session, fake_model):
    sid = mk_session()
    r = client.post("/api/chat", json={
        "session_id": sid, "text": "最近怎么样", "idempotency_key": "key-00000001",
    })
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["turn_no"] == 2
    assert body["reply_text"] == "就……还行吧。您是说哪方面？"
    assert body["degraded"] is False
    assert body["state"] == "done"
    assert body["usage"]["prompt_tokens"] == 500
    assert body["latency_ms"]["total"] >= 0
    assert fake_model["n"] == 1

    turns = _turns(client, sid)
    assert [t["turn_no"] for t in turns] == [1, 2]
    assert [t["role"] for t in turns] == ["teacher", "student"]
    assert turns[0]["text"] == "最近怎么样"


def test_session_becomes_active(client, mk_session, fake_model):
    sid = mk_session()
    assert client.get(f"/api/sessions/{sid}").json()["status"] == "created"
    client.post("/api/chat", json={
        "session_id": sid, "text": "第一句", "idempotency_key": "key-00000002",
    })
    assert client.get(f"/api/sessions/{sid}").json()["status"] == "active"


def test_two_rounds_turn_no_increments(client, mk_session, fake_model):
    sid = mk_session()
    for i, text in enumerate(["第一句", "第二句"], start=1):
        r = client.post("/api/chat", json={
            "session_id": sid, "text": text, "idempotency_key": f"key-0000001{i}",
        })
        assert r.status_code == 200, r.text
        assert r.json()["turn_no"] == i * 2

    turns = _turns(client, sid)
    assert [t["turn_no"] for t in turns] == [1, 2, 3, 4]
    assert client.get(f"/api/sessions/{sid}").json()["turn_count"] == 4


def test_private_setting_not_in_public_response(client, mk_session, fake_model):
    sid = mk_session()
    r = client.post("/api/chat", json={
        "session_id": sid, "text": "你最近怎么样", "idempotency_key": "key-00000003",
    })
    raw = r.text
    assert "父亲生病住院" not in raw
    assert "便利店" not in raw


def test_system_prompt_contains_private_setting(client, mk_session, fake_model):
    """私有设定必须进 system prompt（否则人设失效），但只出现在发往模型的请求里。"""
    sid = mk_session()
    client.post("/api/chat", json={
        "session_id": sid, "text": "你好", "idempotency_key": "key-00000004",
    })
    messages = fake_model["messages"][0]
    assert messages[0]["role"] == "system"
    assert "父亲生病住院" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "你好"}


def test_history_is_included_in_messages(client, mk_session, fake_model):
    sid = mk_session()
    client.post("/api/chat", json={
        "session_id": sid, "text": "第一句", "idempotency_key": "key-00000005",
    })
    client.post("/api/chat", json={
        "session_id": sid, "text": "第二句", "idempotency_key": "key-00000006",
    })
    second = fake_model["messages"][1]
    contents = [m["content"] for m in second]
    assert "第一句" in contents            # 老师上一轮
    assert "就……还行吧。您是说哪方面？" in contents  # 学生上一轮
    assert second[-1]["content"] == "第二句"
    # 老师这句只能出现一次（begin_turn 已写库，构造 messages 时不能重复）
    assert contents.count("第二句") == 1
