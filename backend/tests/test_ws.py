# -*- coding: utf-8 -*-
"""WebSocket 语音通道（合并自合作仓库的 /ws/chat）。"""
import base64


def _connect(client):
    return client.websocket_connect("/ws/chat")


def test_ws_ready(client, fake_model):
    with _connect(client) as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["session_id"].startswith("s_")
        assert ready["student_name"] == "小陈"
        # 桩实现，测试环境不该真去调识别/合成
        assert ready["asr"] == "stub"
        assert ready["tts"] == "stub"


def test_ws_text_round_writes_both_turns(client, fake_model):
    with _connect(client) as ws:
        sid = ws.receive_json()["session_id"]

        ws.send_json({"type": "text", "text": "最近怎么样？"})
        reply = ws.receive_json()

        assert reply["type"] == "reply"
        assert reply["text"] == "就……还行吧。您是说哪方面？"
        assert reply["turn_no"] == 2
        assert reply["degraded"] is False
        # 桩 TTS 不发音频，但字段要在
        assert reply["audio_b64"] is None
        assert reply["audio_format"] is None

        ws.send_json({"type": "text", "text": "第二句"})
        second = ws.receive_json()
        assert second["turn_no"] == 4

    turns = client.get(f"/api/sessions/{sid}/turns").json()["turns"]
    assert [t["turn_no"] for t in turns] == [1, 2, 3, 4]
    assert [t["role"] for t in turns] == ["teacher", "student", "teacher", "student"]


def test_ws_audio_without_asr_returns_no_speech(client, fake_model):
    with _connect(client) as ws:
        ws.receive_json()  # ready
        audio = base64.b64encode(b"\x00" * 3200).decode()
        ws.send_json({"type": "audio", "audio_b64": audio, "audio_format": "pcm16"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "asr_no_speech"
        assert err["retryable"] is True


def test_ws_empty_audio_rejected(client, fake_model):
    with _connect(client) as ws:
        ws.receive_json()
        ws.send_json({"type": "audio", "audio_b64": "", "audio_format": "pcm16"})
        err = ws.receive_json()
        assert err["code"] == "bad_request"


def test_ws_unknown_type(client, fake_model):
    with _connect(client) as ws:
        ws.receive_json()
        ws.send_json({"type": "video"})
        err = ws.receive_json()
        assert err["code"] == "bad_request"


def test_ws_reset_starts_new_session(client, fake_model):
    with _connect(client) as ws:
        first = ws.receive_json()["session_id"]
        ws.send_json({"type": "reset"})
        reset = ws.receive_json()
        assert reset["type"] == "reset"
        assert reset["session_id"] != first

        ws.send_json({"type": "text", "text": "重置后第一句"})
        reply = ws.receive_json()
        assert reply["turn_no"] == 2

    # 新会话的轮次从头开始
    turns = client.get(f"/api/sessions/{reset['session_id']}/turns").json()["turns"]
    assert [t["turn_no"] for t in turns] == [1, 2]


def test_ws_shares_guard_with_rest(client, monkeypatch):
    """私设泄漏检查在 WS 上同样生效（同一套 turn_engine）。"""
    from app.services import model as model_module

    async def _leak(messages, *, json_mode=False):
        return {"text": "我爸父亲生病住院了", "usage": {}}

    monkeypatch.setattr(model_module, "call_model", _leak)

    with _connect(client) as ws:
        ws.receive_json()
        ws.send_json({"type": "text", "text": "你最近怎么样"})
        reply = ws.receive_json()
        assert reply["degraded"] is True
        assert "便利店" not in reply["text"]
        assert "父亲生病住院" not in reply["text"]
