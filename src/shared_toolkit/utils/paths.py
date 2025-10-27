
import platform
import sys
from pathlib import Path

def _use_new_api() -> bool:
    is_windows = platform.system() == "Windows"
    return is_windows

def resource_path(relative_path: str) -> str:
    try:

        base_path = Path(sys._MEIPASS)
    except Exception:

        if _use_new_api():

            base_path = Path(__file__).resolve().parent.parent.parent.parent
        else:

            base_path = Path(__file__).resolve().parent.parent.parent

    full_path = base_path / relative_path
    return str(full_path)
