"""评价大模型实现：独立的「督导」角色，与扮学生的 LLM 分离（角色与评价分离）。

复用 DeepSeek 的 OpenAI 兼容接口，但用不同的 system prompt 与 model，
将来可单独换成更强的推理模型或其它厂商。
"""
import json

import httpx
from openai import AsyncOpenAI

from .base import EvaluationResult, EvaluatorProvider

_SYSTEM_PROMPT = (
    "你是一名资深的高校辅导员谈心谈话督导与评审专家。"
    "请依据给定的《谈心谈话环节评审表》评分要点，对师生对话中「老师（辅导员）」的表现"
    "进行客观评分与复盘。\n"
    "要求：\n"
    "1. 只输出一个 JSON 对象，不要输出任何解释、Markdown 或代码块。\n"
    "2. 每个维度给 0–20 的整数分，五个维度必须齐全，合计 0–100。\n"
    "3. evidence 必须是对话中「老师」的原话引用（尽量简短，每个维度最多 3 条）。\n"
    "4. 打分要有区分度，不要全部给相同分数。\n"
    'JSON 结构：{"total_score": 0, "dimensions": ['
    '{"name": "共情引导", "score": 0, "comment": "理由", "evidence": ["老师原话"]},'
    ' ... 共五个维度 ...'
    '], "summary": "总体评价", "suggestions": "具体可执行的改进建议"}'
)


class EvaluatorDeepSeek(EvaluatorProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.model = model
        # trust_env=False：直连 DeepSeek，不读 Windows 系统代理（与 llm_deepseek 一致）
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.AsyncClient(
                trust_env=False, timeout=httpx.Timeout(600.0, connect=5.0)
            ),
        )

    async def evaluate(self, transcript: str, rubric: str, **kwargs) -> EvaluationResult:
        user = f"【评审表评分要点】\n{rubric}\n\n【师生对话转写】\n{transcript}"
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
            stream=False,
        )
        text = (resp.choices[0].message.content or "").strip()
        data = json.loads(text)
        return _to_result(data)


def _to_result(data: dict) -> EvaluationResult:
    dims = data.get("dimensions", [])
    normalized = []
    for d in dims:
        if not isinstance(d, dict):
            continue
        evidence = d.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = [str(evidence)] if evidence else []
        normalized.append(
            {
                "name": str(d.get("name", "")),
                "score": max(0, min(20, int(d.get("score", 0)))),
                "comment": str(d.get("comment", "")),
                "evidence": [str(e) for e in evidence],
            }
        )
    # 总分以五维之和为准（每维 0–20，合计 0–100），避免模型偶发越界导致总分不一致
    total = sum(x["score"] for x in normalized)
    return EvaluationResult(
        total_score=total,
        dimensions=normalized,
        summary=str(data.get("summary", "")),
        suggestions=str(data.get("suggestions", "")),
    )
