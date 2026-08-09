"""Opt-in per-tile debug dump for the texture-array/instanced tile pipeline.

``IMGSLI_RESIZE_DEBUG``'s ``rhi_render_debug`` calls (see ``render_debug.py``)
go through the normal logger as free-text lines -- fine for "did this code
path run" questions, useless for tile-orientation/parity bugs (flipped,
missing, or shrunk tiles) where the actual numbers (which (row, col) got which
GPU layer, what content_scale/tile_rect a given instance carried) need to be
grepped/joined across hundreds of frames, and the tile's actual pixel content
needs to be seen, not just described. This module is the dedicated tool for
that: gated by ``IMGSLI_TILE_DUMP=1``, it writes one JSONL event per tile
decision (crop, array-slot assignment, per-instance pack) to a fresh
timestamped directory under the app's log dir, plus the cropped tile's actual
PNG bytes alongside -- so a suspect frame's geometry and its pixels sit next
to each other on disk instead of needing separate capture steps.

Off by default, near-zero overhead when disabled (one env-var bool check per
call site, cached at import time -- toggling requires a restart, matching
``rhi_render_debug_enabled``'s own semantics).
"""

from __future__ import annotations

import json
import os
import threading
import time

from sli_ui_toolkit.core.logging import get_log_directory

_ENABLED = os.environ.get("IMGSLI_TILE_DUMP", "").strip().lower() not in (
    "",
    "0",
    "false",
    "no",
    "off",
)

_lock = threading.Lock()
_file_handle = None
_dump_dir: str | None = None
_seq = 0


def tile_dump_enabled() -> bool:
    return _ENABLED


def _ensure_sink() -> None:
    global _file_handle, _dump_dir
    if _file_handle is not None:
        return
    base = get_log_directory("ImproveImgSLI")
    run_dir = os.path.join(base, "tile_debug", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(run_dir, exist_ok=True)
    _dump_dir = run_dir
    _file_handle = open(
        os.path.join(run_dir, "tiles.jsonl"), "w", encoding="utf-8", buffering=1
    )


def log_tile_event(kind: str, **fields) -> None:
    """Appends one JSONL record ``{seq, ts, kind, **fields}``. No-op unless
    ``IMGSLI_TILE_DUMP`` is set. ``row``/``col`` fields should also carry
    ``row_parity``/``col_parity`` when the caller suspects an even/odd-index
    bug -- makes ``jq 'select(.row_parity==0)'``-style filtering trivial
    instead of computing parity by hand while reading the log."""
    if not _ENABLED:
        return
    global _seq
    with _lock:
        _ensure_sink()
        _seq += 1
        record = {"seq": _seq, "ts": time.monotonic(), "kind": kind, **fields}
        _file_handle.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
        _file_handle.flush()


def dump_tile_image(image, name: str) -> str | None:
    """Saves ``image`` (a ``QImage``) as ``<run_dir>/<name>.png``. Returns the
    path (embed it as an ``image_path`` field in the paired ``log_tile_event``
    call so the JSONL record and the pixels are cross-referenced), or
    ``None`` if dumping is disabled."""
    if not _ENABLED:
        return None
    with _lock:
        _ensure_sink()
        path = os.path.join(_dump_dir, f"{name}.png")
    image.save(path, "PNG")
    return path
