"""模型调用的统一入口（薄适配层）。

真正的 HTTP 现在在 `providers/` 里（合并自合作仓库的可插拔设计）。
这一层保留原来的函数名与异常别名，所以 `/api/chat`、WebSocket、单测里的
`monkeypatch.setattr(model, "call_model", ...)` 都不用改。

边界：只有 providers/ 碰 HTTP；services/ 和 api/ 都不直接 import httpx。
"""
from ..providers import get_llm
from ..providers.base import (
    ProviderBadJson,
    ProviderError,
    ProviderRejected,
    ProviderTimeout,
)

# 旧名字继续可用（上层与测试都在用）
ModelError = ProviderError
ModelTimeout = ProviderTimeout
ModelRejected = ProviderRejected
ModelBadJson = ProviderBadJson


async def call_model(messages: list[dict], *, json_mode: bool = False) -> dict:
    """返回 {"text": str, "usage": dict}，与合并前完全一致。"""
    result = await get_llm().chat(messages, json_mode=json_mode)
    return {"text": result.text, "usage": result.usage or {}}
