"""
Path utilities for resource management.
"""

import sys
from pathlib import Path

def resource_path(relative_path: str) -> str:
    """
    Get the absolute path to a resource, works for both development and PyInstaller.

    This function handles the case where the application is bundled with PyInstaller
    by checking for the _MEIPASS attribute, and falls back to the normal file system
    for development.

    Args:
        relative_path: Path relative to the resources directory

    Returns:
        Absolute path to the resource

    Note:
        Logs a warning if the resource is not found (useful for debugging)
    """
    try:

        base_path = Path(sys._MEIPASS)
    except Exception:

        base_path = Path(__file__).resolve().parent.parent

    full_path = base_path / relative_path

    return str(full_path)
