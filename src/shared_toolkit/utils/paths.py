

import sys
from pathlib import Path

def resource_path(relative_path: str) -> str:

    try:

        base_path = Path(sys._MEIPASS)
    except Exception:

        current_file = Path(__file__).resolve()
        base_path = current_file.parent.parent.parent.parent

    full_path = base_path / relative_path

    return str(full_path)

