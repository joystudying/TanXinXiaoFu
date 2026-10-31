"""应用配置：环境变量 → Settings。

路径一律基于项目根目录（D:\\tanxin）解析，避免"换个目录启动就读不到 .env"的问题。
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/config.py → parents[0]=app, [1]=backend, [2]=项目根
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = ""
    model_base_url: str = "https://api.deepseek.com"
    model_name: str = "deepseek-chat"
    model_timeout_s: float = 20.0
    model_max_tokens: int = 200
    temperature: float = 0.8
    ctx_max_turns: int = 8
    # 可插拔 Provider（合并自合作仓库）：换厂商只改这里
    llm_provider: str = "deepseek"
    asr_provider: str = "stub"          # stub | funasr
    funasr_service_url: str = "http://127.0.0.1:8001/transcribe"
    tts_provider: str = "edge"          # edge | stub
    tts_voice: str = "zh-CN-YunxiNeural"  # 云希：年轻男声，贴合大学生角色
    tts_rate: str = "+4%"

    db_path: str = "data/tanxin.db"
    allow_origins: str = "http://127.0.0.1:8000"

    @property
    def db_file(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def frontend_dir(self) -> Path:
        return PROJECT_ROOT / "frontend"

    @property
    def model_configured(self) -> bool:
        return bool(self.deepseek_api_key.strip())

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allow_origins.split(",") if o.strip()]


settings = Settings()
