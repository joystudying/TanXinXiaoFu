"""依赖注入：每请求一个数据库连接。"""
import sqlite3

from .db import repo


def get_db():
    conn = repo.connect()
    try:
        yield conn
    finally:
        conn.close()
