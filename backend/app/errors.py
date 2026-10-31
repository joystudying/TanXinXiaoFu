"""统一错误响应格式：{"error": {"code","message","retryable"}}（设计文档 6 节通用约定）。"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """业务错误。code 一律取设计文档 6.8 的错误码表。"""

    def __init__(self, status_code: int, code: str, message: str, retryable: bool = False):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}},
            headers={"X-Request-Id": _rid(request)},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        fields = []
        for e in exc.errors():
            loc = [str(x) for x in e.get("loc", [])]
            # ["body", ...] → 去掉 "body"；剩空或纯数字时归为整体
            tail = [x for x in loc[1:] if not x.isdigit()] if loc[:1] == ["body"] else loc[1:]
            fields.append({
                "field": ".".join(tail) or "body",
                "reason": e.get("msg", ""),
            })
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "bad_request",
                    "message": "参数不合法",
                    "retryable": False,
                    "fields": fields,
                }
            },
            headers={"X-Request-Id": _rid(request)},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # 不把堆栈给用户（设计文档 12 节兜底原则）
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "服务内部错误", "retryable": True}},
            headers={"X-Request-Id": _rid(request)},
        )
