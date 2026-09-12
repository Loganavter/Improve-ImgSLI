"""App-side theme-token source lookup: token → "themes.json:line".

Themes.json lives in the app's resources; the line lookup makes the
inspector's Theme page point at the exact source of each static token.
"""

from __future__ import annotations

import json
from pathlib import Path


def token_sources(theme_manager) -> dict[str, str]:
    """Map every token of the active theme to ``path:line``."""
    source_path = _theme_source_path(theme_manager)
    if not source_path:
        return {}
    theme = theme_manager.get_current_theme() if hasattr(theme_manager, "get_current_theme") else "light"
    return _theme_key_lines(source_path, theme)


def _theme_source_path(theme_manager) -> str | None:
    for raw in getattr(theme_manager, "_qss_paths", ()) or ():
        path = str(raw)
        if "resources" in path and path.endswith(".qss"):
            candidate = Path(path).parent.parent / "themes.json"
            if candidate.exists():
                return str(candidate)
    return None


def _theme_key_lines(source_path: str, theme_name: str) -> dict[str, str]:
    try:
        with open(source_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    palette = data.get(theme_name, {})
    if not isinstance(palette, dict):
        return {}
    lines = Path(source_path).read_text(encoding="utf-8").splitlines()
    out: dict[str, str] = {}
    for key in palette:
        needle = f'"{key}"'
        for index, line in enumerate(lines, start=1):
            if needle in line:
                out[str(key)] = f"{Path(source_path).name}:{index}"
                break
    return out