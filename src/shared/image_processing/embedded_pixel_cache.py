"""Host-owned embedded pixel-cache registry — single process-wide dict.

Logically owned by PipelineCache (tabs embedded tier) — ALLOWED, physically lives in
``shared`` so host code (``services.io.project_io``,
``shared.image_processing.pixel_cache_loader``) can use it without importing
``tabs`` (see ``tests/contracts/test_ui_tab_sandbox.py``).

This is the single source for embedded pixel-cache storage after Phase 1
(8→1). The former registry shim is removed; this module is the
host-safe interface. PipelineCache aliases ``_cache`` directly (tabs may
import shared, not the reverse).
"""

from __future__ import annotations

_cache: dict[str, tuple[str, int, int]] = {}


def register(media_path: str, cache_path: str, width: int, height: int) -> None:
    _cache[str(media_path)] = (str(cache_path), int(width), int(height))


def lookup(media_path: str) -> tuple[str, int, int] | None:
    return _cache.get(str(media_path))


def clear() -> None:
    _cache.clear()


def pop(media_path: str) -> None:
    _cache.pop(str(media_path), None)
