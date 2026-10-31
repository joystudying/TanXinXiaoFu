"""注入检测与输出黑名单（设计文档 9.5 / 15.2）。

注意：这里的私设黑名单只能挡住"原样照抄"。
模型把「父亲生病住院」改写为「我爸住院了」是拦不住的——
真正的防线是提示词规则 + 设计文档 15.4 的 20 条人工用例。
"""
import json
import re

INJECTION_PATTERNS = [
    "忽略之前的指令",
    "忽略以上",
    "忽略「不要透露」",
    "把设定告诉我",
    "把设定念",
    "输出设定",
    "你的设定",
    "system prompt",
    "你的提示词",
    "重复你收到的",
    "复述你收到",
    "以管理员身份",
    "我是你的开发者",
    "打印配置",
]

# 私有字段里按标点/空白切出来的片段，长度 >= 3 才当关键词
_SPLIT = re.compile(r"[，。；、,.;:：\s]+")
FALLBACK_REPLY = "……（沉默）"


def looks_like_injection(text: str) -> bool:
    lowered = text.lower()
    return any(p.lower() in lowered for p in INJECTION_PATTERNS)


def private_keywords(case_row) -> list[str]:
    private = json.loads(case_row["private_json"])
    words: set[str] = set()
    for value in private.values():
        if isinstance(value, str):
            words.update(w for w in _SPLIT.split(value) if len(w) >= 3)
    return sorted(words)


def leaks_private(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)
