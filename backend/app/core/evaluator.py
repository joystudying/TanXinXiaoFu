"""复盘评价：评分要点（评审表）+ 对话按轮切分 + 转写格式化。

「角色与评价分离」：这里只负责把原始对话整理成评价模型能读的输入，
不涉及扮学生的 system prompt；评分要点来自《谈心谈话环节评审表(1023)》口径，
与前端 review.html 的 rubric-legend 保持一致。
"""

# 五维评分要点（每维满分 20，合计 100）
DIMENSIONS = [
    {"name": "共情引导", "criteria": "尊重接纳学生情绪，换位思考，快速建立信任。"},
    {"name": "思想引领", "criteria": "立场鲜明、价值导向正确，自然融入谈话。"},
    {"name": "问题解决", "criteria": "研判问题实质，提出可行的思路与办法。"},
    {"name": "临场应变", "criteria": "应对情绪变化与突发状况，调整策略和节奏。"},
    {"name": "语言表达", "criteria": "表达流畅、条理清晰，有感染力和说服力。"},
]


def build_rubric_text() -> str:
    lines = ["以下五个维度各满分 20 分，合计 100 分："]
    for d in DIMENSIONS:
        lines.append(f"- {d['name']}（20 分）：{d['criteria']}")
    return "\n".join(lines)


def turns_to_transcript(turns) -> str:
    """把 turns（已按 id 排序）切分成「第 N 轮：老师 → 学生」的文本。

    实时模式下老师侧可能被 ASR 断成多段、或学生先于老师转写到达，
    这里做两道容错：连续同角色合并成一条；学生先到时落到开场而不丢。
    """
    rounds = []
    for t in turns:
        role = t.role
        text = (t.text or "").strip()
        if not text:
            continue
        if role == "teacher":
            if rounds and rounds[-1]["teacher"] and not rounds[-1]["student"]:
                # 上一轮老师还没等到学生回应，又是老师 → 并入上一轮（不拆轮）
                rounds[-1]["teacher"] += "\n" + text
            else:
                rounds.append({"teacher": text, "student": ""})
        else:  # student
            if not rounds:
                rounds.append({"teacher": "", "student": ""})
            rounds[-1]["student"] = (rounds[-1]["student"] + "\n" + text).strip()

    lines = []
    for i, r in enumerate(rounds, 1):
        lines.append(f"第 {i} 轮")
        if r["teacher"]:
            lines.append(f"老师：{r['teacher']}")
        if r["student"]:
            lines.append(f"学生：{r['student']}")
    return "\n".join(lines)
