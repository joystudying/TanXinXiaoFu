"""私有角色设定 + 服务端注入。

「隐藏背景、表达特点、可控分支」全部在这里组装成 system prompt，
只在服务端拼好喂给 LLM，浏览器永远拿不到这些隐藏事实。
"""
from pydantic import BaseModel, Field


class RoleConfig(BaseModel):
    name: str = "小悦"
    grade_major: str = ""          # 如「大二 · 电气工程」
    scenario: str = "情绪困扰"
    # 隐藏背景：学生不主动说、但影响回答的事实（仅服务端）
    hidden_background: str = ""
    # 表达特点：说话风格、沉默、回避等行为特征
    speech_style: str = ""
    # 可观察近况 / 公开背景（老师已知的信息）
    notes: str = ""
    # 可控分支：服务端可在对话中动态注入的事件/背景（后续扩展）
    branches: list[str] = Field(default_factory=list)
    # 开场白：学生谈话开始时的第一句（可选）
    opening: str = ""


def build_system_prompt(role: RoleConfig) -> str:
    lines = [f"你现在扮演一名学生「{role.name}」。"]
    if role.grade_major:
        lines.append(f"基本情况：{role.grade_major}。")
    lines.append(f"当前谈心场景：{role.scenario}。")
    if role.hidden_background:
        lines.append(f"【隐藏背景】{role.hidden_background}")
    if role.speech_style:
        lines.append(f"【表达特点】{role.speech_style}")
    if role.notes:
        lines.append(f"【可观察近况 / 已知信息】{role.notes}")
    if role.opening:
        lines.append(f"【开场】谈话开始时，你可以用这句话或类似的话开场：{role.opening}")
    lines.append(
        "请始终以这名学生的身份、用口语化的中文简短回应（一两句即可），"
        "符合你的年龄与情绪状态；不要跳出角色，不要解释你在扮演，不要使用括号动作描述。"
    )
    return "\n".join(lines)


# 兜底角色（未指定案例时用）：隐藏背景只在此处、只在服务端。
# 供 /ws/chat（回合制）与 /ws/voice（真双工）在未传 case_id 时兜底。
DEFAULT_ROLE = RoleConfig(
    name="小悦",
    grade_major="大二",
    scenario="情绪困扰",
    hidden_background=(
        "最近一次月考成绩下滑明显；父母近期经常争吵；"
        "不想让老师知道自己昨晚偷偷哭过。"
    ),
    speech_style=(
        "说话简短，常先否认自己有事（比如「没事」「我挺好的」），"
        "被温和追问几次后才会慢慢透露真实感受，偶尔沉默。"
    ),
    notes="该生近期上课走神、作业完成质量下降、与同学互动减少。",
    branches=["被问到成绩时情绪激动", "提到父母时沉默回避"],
)
