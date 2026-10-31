"""GET /api/health（设计文档 6.6）。"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .. import errors
from ..config import settings
from ..deps import get_db

router = APIRouter()

VERSION = "1.0"


@router.get("/api/health")
def health(db=Depends(get_db)):
    db_ok = True
    db_msg = "ok"
    try:
        db.execute("SELECT 1").fetchone()
    except Exception:  # noqa: BLE001
        db_ok = False
        db_msg = "db_unavailable"

    model_ok = settings.model_configured
    ok = db_ok and model_ok

    body = {
        "ok": ok,
        "db": db_msg,
        "model_configured": model_ok,
        "version": VERSION,
    }
    if not ok:
        problems = []
        if not db_ok:
            problems.append("数据库不可用")
        if not model_ok:
            problems.append("缺少 DEEPSEEK_API_KEY")
        body["error"] = {
            "code": "health_failed",
            "message": "启动自检未通过：" + "；".join(problems),
            "retryable": False,
        }
        return JSONResponse(status_code=503, content=body)
    return body
