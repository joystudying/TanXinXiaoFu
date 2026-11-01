"""案例库 REST：只暴露公开层；私有层（隐藏背景/表达特点/分支/开场白）永不出服务端。

另有：GET /cases/search 混合检索（关键词 + 语义）、POST /cases 导入/自建案例。
"""
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import retrieval
from ..core.cases import CATEGORY_ORDER, public_detail, public_summary
from ..repo import case_to_dict, create_case, get_case, list_cases

router = APIRouter(prefix="/cases", tags=["cases"])


class CreateCaseRequest(BaseModel):
    category: str
    name: str
    grade_major: str = ""
    tagline: str = ""
    quote: str = ""
    public_background: str = ""
    goals: list[str] = []
    training_focus: str = ""
    duration: str = ""
    tags: list[str] = []
    # 私有层（可选，仅服务端进 system prompt）
    hidden_background: str = ""
    speech_style: str = ""
    branches: list[str] = []
    opening: str = ""


@router.get("")
async def cases_list() -> list[dict]:
    return [public_summary(case_to_dict(c)) for c in await list_cases()]


@router.get("/search")
async def search_cases(q: str = "", limit: int = 10) -> list[dict]:
    """混合检索：关键词（BM25）+ 语义（BGE）RRF 融合，返回相关度排序的案例。"""
    return await retrieval.search(q, limit=min(max(limit, 1), 20))


@router.post("")
async def create_case_endpoint(req: CreateCaseRequest) -> dict:
    """导入/自建一个案例：写入 cases 表并重建检索索引。"""
    if req.category not in CATEGORY_ORDER:
        raise HTTPException(400, f"未知分类：{req.category}")
    if not req.name.strip():
        raise HTTPException(400, "缺少案例化名")

    case_id = f"custom-{uuid.uuid4().hex[:8]}"
    await create_case(
        {
            "id": case_id,
            "category": req.category,
            "name": req.name.strip(),
            "grade_major": req.grade_major,
            "tagline": req.tagline,
            "quote": req.quote,
            "public_background": req.public_background,
            "goals": req.goals,
            "training_focus": req.training_focus,
            "duration": req.duration,
            "tags": req.tags,
            "hidden_background": req.hidden_background,
            "speech_style": req.speech_style,
            "branches": req.branches,
            "opening": req.opening,
            "version": 1,
        }
    )
    await retrieval.reindex_all()
    return public_summary(case_to_dict(await get_case(case_id)))


@router.get("/{case_id}")
async def case_detail(case_id: str) -> dict:
    c = await get_case(case_id)
    if c is None:
        raise HTTPException(404, "案例不存在")
    return public_detail(case_to_dict(c))
