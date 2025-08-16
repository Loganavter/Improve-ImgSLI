from pathlib import Path
import sys

def resource_path(relative_path: str) -> str:
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).resolve().parent.parent
    return (base_path / relative_path).as_posix()
