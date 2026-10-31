"""上下文裁剪（设计文档 9.4）。

turn_no 的分配在 db/repo.py（要和事务绑在一起），这里只负责"取最近几轮"。
"""
from ..config import settings


def trim(history: list, max_turns: int | None = None) -> list:
    """history 是 sqlite Row 的列表，按 turn_no 升序。

    一个"轮"= 老师一句 + 学生一句，所以保留 max_turns*2 条。
    """
    n = max_turns if max_turns is not None else settings.ctx_max_turns
    if n <= 0:
        return []
    return list(history)[-n * 2:]
