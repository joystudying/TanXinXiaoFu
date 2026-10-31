"""唯一 HTTP 出口（设计文档 9.2 / 硬约束 1）。

这个文件之外不允许出现 `api.deepseek.com`，也不允许出现第二个 HTTP 客户端。
"""
import asyncio
import json

import httpx

from ..config import settings


class ModelError(Exception):
    """模型调用失败（可重试）。"""


class ModelTimeout(ModelError):
    """超时。"""


class ModelBadJson(ModelError):
    """要求 JSON 输出但解析失败。"""


class ModelRejected(ModelError):
    """4xx（key 失效、参数错）——重试没有意义。"""


def _chat_url() -> str:
    return settings.model_base_url.rstrip("/") + "/chat/completions"


async def call_model(messages: list[dict], *, json_mode: bool = False) -> dict:
    """调一次模型。返回 {"text": str, "usage": dict}。

    重试策略：超时 / 429 / 5xx 重试 2 次；4xx（除 429）立即失败。
    """
    payload = {
        "model": settings.model_name,
        "messages": messages,
        "temperature": settings.temperature,
        "max_tokens": settings.model_max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last: Exception | None = None

    for attempt in range(3):  # 1 次 + 2 次重试
        try:
            async with httpx.AsyncClient(timeout=settings.model_timeout_s) as client:
                resp = await client.post(
                    _chat_url(),
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json=payload,
                )

            if resp.status_code == 429 or resp.status_code >= 500:
                last = ModelError(f"http_{resp.status_code}")
            elif 400 <= resp.status_code < 500:
                # key 错、模型名错之类：重试也没用
                raise ModelRejected(f"http_{resp.status_code}")
            else:
                try:
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError) as exc:
                    raise ModelError(f"bad_response: {exc}") from exc
                if json_mode:
                    try:
                        json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise ModelBadJson(text[:80]) from exc
                return {"text": text, "usage": data.get("usage") or {}}

        except httpx.TimeoutException:
            last = ModelTimeout("timeout")
        except httpx.HTTPError as exc:
            last = ModelError(str(exc))

        if attempt < 2:
            await asyncio.sleep(0.5 * (2 ** attempt))  # 0.5s, 1.0s

    raise last or ModelError("unknown")
