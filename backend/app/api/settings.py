"""接入 AI 的配置接口（供页面上的「接入 AI」使用）。

安全边界：只允许本机访问。这个项目是本地训练工具，如果在公网部署后
把"改密钥"开放给所有人，等于把账单送人。所以写操作只放行回环地址。
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import errors
from ..services import config_store

router = APIRouter()

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


class SettingsIn(BaseModel):
    deepseek_api_key: str | None = None
    model_base_url: str | None = None
    model_name: str | None = None
    asr_provider: str | None = None
    tts_provider: str | None = None
    tts_voice: str | None = None
    volc_app_id: str | None = None
    volc_access_token: str | None = None


def _require_local(request: Request) -> None:
    host = (request.client.host if request.client else "") or ""
    if host not in LOCAL_HOSTS:
        raise errors.ApiError(403, "forbidden", "只允许在本机修改接入配置", False)


@router.get("/api/settings")
async def read_settings(request: Request):
    _require_local(request)
    return config_store.masked_state()


@router.post("/api/settings")
async def write_settings(payload: SettingsIn, request: Request):
    _require_local(request)
    # 空白值视为"不修改"，所以一律在边界就剔掉，避免写进 .env 变成空配置
    data = {k: v.strip() for k, v in payload.model_dump().items() if isinstance(v, str) and v.strip()}
    if not data:
        raise errors.ApiError(422, "bad_request", "没有需要保存的内容", False)
    return config_store.apply_updates(data)
