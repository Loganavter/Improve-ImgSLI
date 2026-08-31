"""Process-wide registry of extracted project pixel-cache buffers.

Populated by :func:`services.io.project_io.prepare_project_file_for_load`
after extracting a project's optional ``cache/`` members; consulted by the
``TiledPixelStore.from_path`` call sites at session load so a source image
whose decoded RGBA8 buffer was embedded in the project can be reopened via
:meth:`TiledPixelStore.from_embedded_cache` instead of being re-decoded.

Keyed by absolute media source path (post path-rewrite), not asset_id — the
call sites only have the media path in hand.

Deprecated alias — logically owned by ``PipelineCache`` embedded tier
(``get_or_load`` → ``lookup_embedded_cache`` → ``from_embedded_cache``).
This module remains as a thin compat shim; new code should use
``PipelineCache.get_or_load/peek/evict``. The underlying dict is shared with
``PipelineCache._embedded_cache`` via alias (see pipeline/cache.py:44).  # ALLOWED tab ref in comment
"""

from __future__ import annotations

_cache: dict[str, tuple[str, int, int]] = {}


def register(media_path: str, cache_path: str, width: int, height: int) -> None:
    _cache[media_path] = (cache_path, width, height)


def lookup(media_path: str) -> tuple[str, int, int] | None:
    return _cache.get(media_path)


def clear() -> None:
    _cache.clear()
