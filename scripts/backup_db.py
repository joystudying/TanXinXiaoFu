# -*- coding: utf-8 -*-
"""SQLite 在线备份（用 sqlite3 backup API，WAL 模式下也安全）。

用法：
  python scripts\\backup_db.py            # 保留最近 10 份
  python scripts\\backup_db.py --keep 20
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "tanxin.db"
BACKUPS = ROOT / "data" / "backups"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=10, help="保留最近几份（默认 10）")
    args = ap.parse_args()

    if not DB.exists():
        print(f"数据库不存在，无需备份：{DB}")
        return 0

    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = BACKUPS / f"tanxin-{stamp}.db"

    src_conn = sqlite3.connect(DB)
    dst_conn = sqlite3.connect(dst)
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()

    size_kb = dst.stat().st_size / 1024
    print(f"已备份 → {dst.relative_to(ROOT)}  ({size_kb:.1f} KB)")

    files = sorted(BACKUPS.glob("tanxin-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[args.keep:]:
        old.unlink()
        print(f"清理旧备份：{old.name}")
    print(f"当前保留 {min(len(files), args.keep)} 份")
    return 0


if __name__ == "__main__":
    sys.exit(main())
