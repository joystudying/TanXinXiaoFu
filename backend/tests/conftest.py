# -*- coding: utf-8 -*-
"""pytest 公共夹具：临时数据库 + 假模型（单测不触网，设计文档 16.1）。"""
import os
import pathlib
import sys
import tempfile

# 必须在 import app 之前做两件事：把 backend 放进 sys.path、把库指向临时文件
_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))
_TMPDIR = pathlib.Path(tempfile.mkdtemp(prefix="tanxin-test-"))
os.environ["DB_PATH"] = str(_TMPDIR / "test.db")
# 单测不碰外部服务：识别与合成都用桩实现
os.environ["ASR_PROVIDER"] = "stub"
os.environ["TTS_PROVIDER"] = "stub"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import model as model_module  # noqa: E402

CASE_ID = "c_academic_01"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_model(monkeypatch):
    """替换模型调用，返回固定台词；记录调用次数与收到的 messages。"""
    calls = {"n": 0, "messages": []}

    async def _fake(messages, *, json_mode=False):
        calls["n"] += 1
        calls["messages"].append(messages)
        return {
            "text": "就……还行吧。您是说哪方面？",
            "usage": {"prompt_tokens": 500, "completion_tokens": 20},
        }

    monkeypatch.setattr(model_module, "call_model", _fake)
    return calls


@pytest.fixture
def mk_session(client):
    """建一个会话，返回 session_id。"""
    def _mk(prep_note: str | None = None) -> str:
        body = {"case_id": CASE_ID}
        if prep_note:
            body["prep_note"] = prep_note
        r = client.post("/api/sessions", json=body)
        assert r.status_code == 201, r.text
        return r.json()["session_id"]

    return _mk
