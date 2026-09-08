import os
import re
import sys
from pathlib import Path


def get_resource_path(relative_path: str | Path) -> Path:
    """
    Универсальный резолвер путей:
    1. Проверяет официальную переменную Nuitka --onefile (NUITKA_ONEFILE_DIRECTORY).
    2. Проверяет распакованный бандл/корень проекта через __file__.
    3. Проверяет папку рядом с .exe.
    """
    rel = Path(relative_path)

    if "NUITKA_ONEFILE_DIRECTORY" in os.environ:
        nuitka_dir = Path(os.environ["NUITKA_ONEFILE_DIRECTORY"])
        path = nuitka_dir / rel
        if path.exists():
            return path

    internal_base = Path(__file__).resolve().parent.parent
    internal_path = internal_base / rel
    if internal_path.exists():
        return internal_path

    exe_base = Path(sys.argv[0]).resolve().parent
    external_path = exe_base / rel
    if external_path.exists():
        return external_path

    return internal_path


def normalize_name(raw_name: str) -> str:
    """Очищает пробелы и приводит строку к Title Case (Иванов Иван)."""
    cleaned = " ".join(raw_name.strip().split())
    return cleaned.title()


def hex_to_rgb(hex_color: str, default: tuple = (24, 43, 73)) -> tuple[int, int, int]:
    """Конвертирует HEX в RGB."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return default
    try:
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return default


def sanitize_filename(filename: str, default: str = "Грамоты") -> str:
    """Вырезает недопустимые для Windows символы: \ / : * ? \" < > |"""
    clean = re.sub(r'[\\/*?:"<>|]', "", filename).strip()
    if not clean:
        clean = default
    if not clean.lower().endswith(".pdf"):
        clean += ".pdf"
    return clean