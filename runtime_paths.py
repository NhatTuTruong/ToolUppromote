"""Đường dẫn khi chạy nguồn vs khi đóng gói PyInstaller (.exe)."""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Thư mục làm việc: .env, domain.txt, file CSV/XLSX xuất — cạnh file .exe khi đóng gói."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """Thư mục chứa templates/static đi kèm bản build (sys._MEIPASS khi onefile)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent
