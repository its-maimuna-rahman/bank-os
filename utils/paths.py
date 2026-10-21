"""
utils/paths.py
Single source of truth for every file/folder path in BankOS.

All paths are anchored to the folder this file lives in (the project root),
NOT to the current working directory. That means `streamlit run app.py` and
`python main.py` find config.json, data/bank.db and statements/ correctly no
matter which folder they are launched from.

This module imports nothing from the project, so any other module can import
it without risking a circular import.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR: Path = Path(__file__).resolve().parent.parent   # utils/ -> project root

DATA_DIR: Path = BASE_DIR / "data"
STATEMENTS_DIR: Path = BASE_DIR / "statements"

CONFIG_PATH: Path = BASE_DIR / "config.json"
DB_PATH: Path = DATA_DIR / "bank.db"


def resolve_path(path: str | Path) -> str:
    """
    Turn a path from config.json (e.g. "data/bank.db") into an absolute path.
    Relative paths are resolved against the project root; absolute paths are
    returned unchanged.
    """
    p = Path(path)
    return str(p if p.is_absolute() else BASE_DIR / p)
