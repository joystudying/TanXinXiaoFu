"""集中配置：全部从环境变量 / .env 读取。

这样模型密钥、隐藏事实、Provider 选择都只在服务端，不暴露给前端，
也满足「不依赖某一家模型或特定框架」的 Harness 约束。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM（扮演学生）
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ASR
    asr_provider: str = "stub"  # stub | funasr
    funasr_service_url: str = "http://127.0.0.1:8001/transcribe"

    # TTS
    tts_provider: str = "edge"  # edge | stub
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"

    # 存储
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
