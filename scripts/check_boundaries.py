# -*- coding: utf-8 -*-
"""分层边界检查。任一项失败 → 退出码 1。

用法：python scripts\\check_boundaries.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "backend" / "app"

SQL_WORDS = re.compile(r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", re.I)
HTTP_IMPORT = re.compile(r"^\s*(import\s+httpx|from\s+httpx)", re.M)
DB_TO_SERVICE = re.compile(r"from\s+\.\.services|import\s+services")

failures: list[str] = []


def py_files(folder: Path):
    return sorted(p for p in folder.rglob("*.py")) if folder.exists() else []


# 1) services/ 不许写 SQL
for p in py_files(APP / "services"):
    for m in SQL_WORDS.finditer(p.read_text(encoding="utf-8")):
        failures.append(f"[SQL in services] {p.relative_to(ROOT)} → {m.group(0)}")
        break

# 2) api/ 不许直接 import httpx
for p in py_files(APP / "api"):
    if HTTP_IMPORT.search(p.read_text(encoding="utf-8")):
        failures.append(f"[httpx in api] {p.relative_to(ROOT)}")

# 3) db/ 不许 import services
for p in py_files(APP / "db"):
    if DB_TO_SERVICE.search(p.read_text(encoding="utf-8")):
        failures.append(f"[services import in db] {p.relative_to(ROOT)}")

# 4) 全仓库不许硬编码密钥
SKIP_DIRS = {".venv", ".git", "__pycache__", "data", "node_modules"}
for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    if any(part in SKIP_DIRS for part in p.parts):
        continue
    if p.suffix.lower() not in {".py", ".js", ".html", ".ps1", ".md", ".json", ".sql", ".txt"}:
        continue
    if p.name == ".env":
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    for m in re.finditer(r"sk-[A-Za-z0-9]{20,}", text):
        failures.append(f"[hardcoded key] {p.relative_to(ROOT)} → {m.group(0)[:6]}…")
        break

print("边界检查：")
if failures:
    for f in failures:
        print("  [FAIL] " + f)
    print(f"\n失败 {len(failures)} 项")
    sys.exit(1)

print("  [OK] services 无 SQL")
print("  [OK] api 无 httpx")
print("  [OK] db 无 services 依赖")
print("  [OK] 无硬编码密钥")
print("\n全部通过")
