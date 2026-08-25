import sys
from pathlib import Path


def resource_path(relative_path: str) -> str:
    try:
        base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]  # PyInstaller-only
    except Exception:

        current_file = Path(__file__).resolve()
        base_path = current_file.parent.parent
    return (base_path / relative_path).as_posix()
