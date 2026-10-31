# -*- coding: utf-8 -*-
"""超时与失败回滚（设计文档 16.1 test_timeout.py / 技术路径文档 D-1、D-2）。"""
import pytest

from app.services import model as model_module


def _turns(client, sid):
    return client.get(f"/api/sessions/{sid}/turns").json()["turns"]


@pytest.fixture
def timeout_model(monkeypatch):
    async def _boom(messages, *, json_mode=False):
        raise model_module.ModelTimeout("timeout")

    monkeypatch.setattr(model_module, "call_model", _boom)


def test_timeout_returns_504_and_writes_nothing(client, mk_session, timeout_model):
    sid = mk_session()
    r = client.post("/api/chat", json={
        "session_id": sid, "text": "最近怎么样", "idempotency_key": "key-to-0001",
    })
    assert r.status_code == 504
    assert r.json()["error"]["code"] == "model_timeout"
    assert r.json()["error"]["retryable"] is True

    # 老师那句必须被回滚，不能留半轮
    assert _turns(client, sid) == []
    # 会话状态退回 created（还没成功说过一句）
    assert client.get(f"/api/sessions/{sid}").json()["status"] == "created"


def test_retry_after_timeout_succeeds_with_same_key(client, mk_session, monkeypatch):
    """技术路径文档 D-1：failed 之后同 key 重试应能继续，而不是永远 409。"""
    calls = {"n": 0}

    async def _flaky(messages, *, json_mode=False):
        calls["n"] += 1
        if calls["n"] == 1:
            raise model_module.ModelTimeout("timeout")
        return {"text": "……还行吧。", "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    monkeypatch.setattr(model_module, "call_model", _flaky)

    sid = mk_session()
    payload = {"session_id": sid, "text": "最近怎么样", "idempotency_key": "key-to-0002"}

    first = client.post("/api/chat", json=payload)
    assert first.status_code == 504

    second = client.post("/api/chat", json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["reply_text"] == "……还行吧。"
    assert [t["turn_no"] for t in _turns(client, sid)] == [1, 2]


def test_model_error_returns_502(client, mk_session, monkeypatch):
    async def _boom(messages, *, json_mode=False):
        raise model_module.ModelError("http_503")

    monkeypatch.setattr(model_module, "call_model", _boom)
    sid = mk_session()
    r = client.post("/api/chat", json={
        "session_id": sid, "text": "你好", "idempotency_key": "key-to-0003",
    })
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "model_unavailable"
    assert _turns(client, sid) == []


def test_model_rejected_returns_not_retryable(client, mk_session, monkeypatch):
    async def _boom(messages, *, json_mode=False):
        raise model_module.ModelRejected("http_401")

    monkeypatch.setattr(model_module, "call_model", _boom)
    sid = mk_session()
    r = client.post("/api/chat", json={
        "session_id": sid, "text": "你好", "idempotency_key": "key-to-0004",
    })
    assert r.status_code == 502
    assert r.json()["error"]["retryable"] is False
