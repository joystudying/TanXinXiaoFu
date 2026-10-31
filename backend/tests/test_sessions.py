# -*- coding: utf-8 -*-
"""会话接口（设计文档 16.1 test_sessions.py）。"""
from conftest import CASE_ID


def test_create_session_returns_public_only(client):
    r = client.post("/api/sessions", json={"case_id": CASE_ID, "prep_note": "先问睡眠"})
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["session_id"].startswith("s_")
    assert body["status"] == "created"
    assert body["case"]["id"] == CASE_ID
    assert body["case"]["public"]["alias"] == "小陈"

    # 只回公开字段：整个响应里不许出现私有设定
    raw = r.text
    assert "private" not in raw
    assert "父亲生病住院" not in raw
    assert "便利店" not in raw


def test_create_session_unknown_case(client):
    r = client.post("/api/sessions", json={"case_id": "c_not_exist"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "case_not_found"


def test_create_session_missing_field(client):
    r = client.post("/api/sessions", json={"prep_note": "x"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "bad_request"
    assert any(f["field"] == "case_id" for f in err["fields"])


def test_get_session_and_turns(client, mk_session):
    sid = mk_session()

    r = client.get(f"/api/sessions/{sid}")
    assert r.status_code == 200
    assert r.json()["turn_count"] == 0
    assert r.json()["status"] == "created"

    r = client.get(f"/api/sessions/{sid}/turns")
    assert r.status_code == 200
    assert r.json() == {"session_id": sid, "turns": []}


def test_get_session_not_found(client):
    r = client.get("/api/sessions/s_不存在")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "session_not_found"


def test_turns_not_found(client):
    r = client.get("/api/sessions/s_不存在/turns")
    assert r.status_code == 404


def test_end_session(client, mk_session):
    sid = mk_session()
    r = client.post(f"/api/sessions/{sid}/end", json={"reason": "训练完成"})
    assert r.status_code == 200
    assert r.json()["status"] == "ended"

    r = client.get(f"/api/sessions/{sid}")
    assert r.json()["status"] == "ended"
    assert r.json()["ended_at"]


def test_response_headers(client):
    r = client.get("/api/health")
    assert r.headers.get("x-request-id", "").startswith("req_")
    assert r.headers.get("cache-control") == "no-store"
