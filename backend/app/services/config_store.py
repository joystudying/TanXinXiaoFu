"""读写 .env 配置（唯一碰配置文件的地方）。

为什么放 services 而不是 api：写文件属于业务动作，端点只做校验与转发。
写入后会同步刷新内存里的 settings 并重置 Provider 缓存，做到"保存即生效"。
"""
from pathlib import Path

from ..config import PROJECT_ROOT, settings
from ..providers import reset_providers

ENV_PATH = PROJECT_ROOT / ".env"

# 允许通过页面修改的键（其余一律不碰）
EDITABLE = {
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "model_base_url": "MODEL_BASE_URL",
    "model_name": "MODEL_NAME",
    "asr_provider": "ASR_PROVIDER",
    "tts_provider": "TTS_PROVIDER",
    "tts_voice": "TTS_VOICE",
    "volc_app_id": "VOLC_APP_ID",
    "volc_access_token": "VOLC_ACCESS_TOKEN",
}


def _read_pairs() -> list[tuple[str, str]]:
    if not ENV_PATH.exists():
        return []
    pairs = []
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        pairs.append((k.strip(), v.strip()))
    return pairs


def _write_pairs(pairs: list[tuple[str, str]]) -> None:
    lines = ["# 由「接入 AI」页面生成；改动会立即生效，重启后依然保留。"]
    lines += [f"{k}={v}" for k, v in pairs]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def masked_state() -> dict:
    """给页面看的状态：只说有没有，不返回密钥本身。"""
    return {
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.model_name,
            "base_url": settings.model_base_url,
            "key_set": bool(settings.deepseek_api_key.strip()),
            "ready": settings.model_configured,
        },
        "tts": {
            "provider": settings.tts_provider,
            "voice": settings.tts_voice,
        },
        "asr": {"provider": settings.asr_provider},
        "realtime": {
            "app_id_set": bool(settings.volc_app_id.strip()),
            "token_set": bool(settings.volc_access_token.strip()),
            "ready": settings.realtime_configured,
        },
        "env_file": str(ENV_PATH),
    }


def apply_updates(updates: dict) -> dict:
    """把页面提交的字段写进 .env 并立即生效。空字符串表示"保持原值不变"。"""
    changed = {k: v for k, v in updates.items() if k in EDITABLE and isinstance(v, str) and v.strip()}

    pairs = dict(_read_pairs())
    for field, value in changed.items():
        env_key = EDITABLE[field]
        pairs[env_key] = value.strip()
        setattr(settings, field, value.strip())      # 立即生效

    if changed:
        _write_pairs(list(pairs.items()))
        reset_providers()                            # 让 Provider 用新配置重建

    return {"saved": sorted(changed.keys()), "state": masked_state()}
