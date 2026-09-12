"""Resolve Help markdown placeholders.

- ``{{tr:dotted.key}}`` → UI / tab i18n string for the active language
- ``{{img:figure.slot}}`` → asset path from package ``figures.json`` maps

Host map: ``resources/help/figures.json``.
Tab maps: ``tabs/<tab>/resources/help/figures.json`` (merged by discovery).

See docs/dev/HELP_SYSTEM.md § Language keys and § Figure tokens.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from resources.translations import tr

_TR_PLACEHOLDER_RE = re.compile(r"\{\{tr:([a-zA-Z0-9_.]+)\}\}")
_IMG_PLACEHOLDER_RE = re.compile(r"\{\{img:([a-zA-Z0-9_.]+)\}\}")

_figures_cache: dict[str, str] | None = None


def _src_root() -> Path:
    return Path(__file__).resolve().parents[2]


def host_help_figures_path() -> Path:
    return _src_root() / "resources" / "help" / "figures.json"


def discover_help_figure_map_paths() -> tuple[Path, ...]:
    """Host figures.json first, then each tab package's figures.json."""
    paths: list[Path] = []
    host = host_help_figures_path()
    if host.is_file():
        paths.append(host)
    tabs = _src_root() / "tabs"
    if tabs.is_dir():
        for path in sorted(tabs.glob("*/resources/help/figures.json")):
            if path.is_file():
                paths.append(path)
    return tuple(paths)


def help_figures_path() -> Path:
    """Backward-compatible alias for the host map path."""
    return host_help_figures_path()


def _load_figures_file(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in raw.items()
        if isinstance(key, str) and isinstance(value, str) and key and value
    }


def load_help_figures(*, force_reload: bool = False) -> dict[str, str]:
    """Merge all package figure maps (host + tabs). Later packages override."""
    global _figures_cache
    if _figures_cache is not None and not force_reload:
        return _figures_cache
    merged: dict[str, str] = {}
    for path in discover_help_figure_map_paths():
        merged.update(_load_figures_file(path))
    _figures_cache = merged
    return _figures_cache


def clear_help_figures_cache() -> None:
    global _figures_cache
    _figures_cache = None


def resolve_help_figure(slot: str) -> str | None:
    """Map ``{{img:slot}}`` id to an asset-relative path, or ``None`` if unknown."""
    return load_help_figures().get(slot)


def interpolate_help_markdown(text: str, language: str) -> str:
    """Replace ``{{tr:…}}`` and ``{{img:…}}`` placeholders in a Help body."""

    def _replace_tr(match: re.Match[str]) -> str:
        key = match.group(1)
        value = tr(key, language=language)
        if not value or value == key:
            return key
        return value

    def _replace_img(match: re.Match[str]) -> str:
        slot = match.group(1)
        path = resolve_help_figure(slot)
        if path is None:
            return match.group(0)
        return path

    out = _TR_PLACEHOLDER_RE.sub(_replace_tr, text)
    return _IMG_PLACEHOLDER_RE.sub(_replace_img, out)
