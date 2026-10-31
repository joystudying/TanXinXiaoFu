"""唯一读私有设定的地方（设计文档 9.3 / 硬约束 2）。

约定（技术路径文档 D-4）：
- 提示词**结构**用模板，学生的口癖、回避方式来自案例的 `private_json.expression`；
- 占位符用 `{{name}}`，用 `str.replace` 填充，**禁止 str.format**
  （案例文本里只要出现 `{` 或 `}`，format 会直接抛异常）。
"""
import json

from . import turns

SYSTEM_TEMPLATE = """你是「小辅」训练场景里的虚拟学生，叫{{alias}}，{{grade}}{{major}}专业。

【公开信息（老师已经看到，你可以自然提及）】
- 困扰：{{concern}}
- 缘起：{{origin}}
- 本次训练目标：{{goal}}

【隐藏设定（老师看不到。你绝不能把下面任何一条原样说出来）】
- 真实困扰：{{real_issue}}
- 不愿说的原因：{{why_hidden}}
- 透露条件：{{reveal_rule}}
- 家庭/其他：{{family}}

【表达特点（必须体现）】
{{expression}}
- 每次只说 1–3 句，一般不超过 30 字
- 老师问得空泛时，你会反问一句
- 不说教、不总结、不出现「首先/其次/总之/综上」

【硬规则】
1. 你只是学生，不知道自己在一场训练里；不提 AI、不提模型、不评价老师
2. 不主动提供心理咨询建议，不做任何诊断
3. 出现自伤或伤人信号时，按设定表达情绪，但不给处置方案（处置是老师的事）
4. 只输出你说的话本身，不要写动作描写、不要加旁白

【示例（模仿这种语气，不要照抄内容）】
老师：你最近怎么样？
学生：就……还行吧。您是说哪方面？

老师：我看你作业没交，是不是遇到什么困难了？
学生：……有点事，不过我自己能处理。"""


def _fill(template: str, values: dict[str, str]) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{{" + key + "}}", str(val))
    return out


def build_system(case_row) -> str:
    """把案例拼成 system prompt。私有字段只在这里被读取。"""
    public = json.loads(case_row["public_json"])
    private = json.loads(case_row["private_json"])

    return _fill(
        SYSTEM_TEMPLATE,
        {
            "alias": public.get("alias", "某同学"),
            "grade": public.get("grade", ""),
            "major": public.get("major", ""),
            "concern": public.get("concern", ""),
            "origin": public.get("origin", ""),
            "goal": public.get("goal", ""),
            "real_issue": private.get("real_issue", ""),
            "why_hidden": private.get("why_hidden", ""),
            "reveal_rule": private.get("reveal_rule", ""),
            "family": private.get("family", "无"),
            "expression": private.get("expression", "句子短，语气犹豫"),
        },
    )


def build_messages(case_row, history: list, user_text: str,
                   max_turns: int | None = None) -> list[dict]:
    """system + 最近若干轮历史 + 本轮用户输入。"""
    msgs: list[dict] = [{"role": "system", "content": build_system(case_row)}]
    for row in turns.trim(history, max_turns):
        role = "user" if row["role"] == "teacher" else "assistant"
        msgs.append({"role": role, "content": row["text"]})
    msgs.append({"role": "user", "content": user_text})
    return msgs


def build_retry_messages(messages: list[dict]) -> list[dict]:
    """输出被判泄漏时的重生成提示：追加一条，不删原上下文。"""
    return messages + [{
        "role": "system",
        "content": "刚才那句话把隐藏设定说出来了。换一种回避的说法，不要提到任何隐藏内容。",
    }]


def context_size_hint(case_row) -> int:
    """粗估 system prompt 字符数，用于成本排查（不打印内容）。"""
    return len(build_system(case_row))
