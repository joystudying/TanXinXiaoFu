# -*- coding: utf-8 -*-
"""接入 AI 的配置接口。

注意：这些测试会把 .env 路径替换成临时文件，
绝不能碰项目根目录的真实 .env。
"""
import pytest

from app.services import config_store


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """把生效的 .env 指到临时文件，返回该路径。"""
    p = tmp_path / ".env"
    p.write_text("DEEPSEEK_API_KEY=sk-temporary\nMODEL_NAME=deepseek-chat\n", encoding="utf-8")
    monkeypatch.setattr(config_store, "ENV_PATH", p)
    return p


def test_masked_state_never_returns_key(client, tmp_env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-secret-should-not-leak", raising=False)
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "sk-secret-should-not-leak" not in r.text
    assert body["llm"]["key_set"] is True
    assert "deepseek_api_key" not in r.text


def test_empty_payload_rejected(client, tmp_env):
    r = client.post("/api/settings", json={})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "bad_request"


def test_save_writes_env_and_applies_immediately(client, tmp_env):
    r = client.post("/api/settings", json={"tts_voice": "zh-CN-XiaoyiNeural"})
    assert r.status_code == 200
    body = r.json()
    assert "tts_voice" in body["saved"]
    assert body["state"]["tts"]["voice"] == "zh-CN-XiaoyiNeural"

    text = tmp_env.read_text(encoding="utf-8")
    assert "TTS_VOICE=zh-CN-XiaoyiNeural" in text
    # 原有键不能丢
    assert "DEEPSEEK_API_KEY=" in text


def test_blank_value_means_keep(client, tmp_env):
    before = tmp_env.read_text(encoding="utf-8")
    r = client.post("/api/settings", json={"deepseek_api_key": "   "})
    assert r.status_code == 422          # 全空 → 视为没有要保存的内容
    assert tmp_env.read_text(encoding="utf-8") == before


def test_unknown_field_ignored(client, tmp_env):
    before = tmp_env.read_text(encoding="utf-8")
    r = client.post("/api/settings", json={"db_path": "/etc/passwd"})
    # db_path 不在可编辑白名单里，且整体为空 → 422，文件不变
    assert r.status_code == 422
    assert tmp_env.read_text(encoding="utf-8") == before


def test_full_flow_key_then_ready(client, tmp_env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "deepseek_api_key", "", raising=False)

    r = client.post("/api/settings", json={"deepseek_api_key": "sk-new-key-1234567890"})
    assert r.status_code == 200
    assert r.json()["state"]["llm"]["ready"] is True
    assert "sk-new-key-1234567890" in tmp_env.read_text(encoding="utf-8")
