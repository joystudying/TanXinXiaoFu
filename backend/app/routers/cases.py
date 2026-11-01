"""案例库 REST：只暴露公开层；私有层（隐藏背景/表达特点/分支/开场白）永不出服务端。"""
from fastapi import APIRouter, HTTPException

from ..core.cases import public_detail, public_summary
from ..repo import case_to_dict, get_case, list_cases

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("")
async def cases_list() -> list[dict]:
    return [public_summary(case_to_dict(c)) for c in await list_cases()]


@router.get("/{case_id}")
async def case_detail(case_id: str) -> dict:
    c = await get_case(case_id)
    if c is None:
        raise HTTPException(404, "案例不存在")
    return public_detail(case_to_dict(c))
