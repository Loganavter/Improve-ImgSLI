"""``IMGSLI_GALLERY_DEBUG``-gated tracing for the Image Gallery tab.

Covers drag & drop, folder open, and triage paths — the same convention as
``shared/rendering/render_debug.py``'s ``IMGSLI_RESIZE_DEBUG`` and
``ui/widgets/flyout_debug.py``'s ``IMGSLI_FLYOUT_DEBUG``: gate on an env var,
tag every line with a unique bracketed prefix, near-zero overhead when
disabled.

Env var:
    IMGSLI_GALLERY_DEBUG=1  — enable all gallery debug streams.

Tags:
    [gallery-dnd]   — DnD entry points, handle_drop / dropEvent decisions,
                      open_folder / open_paths routing.
    [gallery-debug] — generic gallery lifecycle (pick dialog, fallback branches).

Usage:
    from tabs.image_gallery.debug import gallery_dnd_debug, gallery_debug
    gallery_dnd_debug("handle_drop: %d paths %r", len(paths), paths[:3])
    gallery_debug("pick_folder_dialog chosen: %s", p)

Both helpers call ``logger.debug`` (visible only with ``--debug`` /
``debug_mode_enabled`` + the env flag) — no ``logger.warning`` spam at
INFO level. See ``docs/dev/LOGGING.md`` unique-prefix convention.
"""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def gallery_debug_enabled() -> bool:
    return _env_flag("IMGSLI_GALLERY_DEBUG")


def gallery_dnd_debug_enabled() -> bool:
    # Same flag for now — keeps one knob for the whole tab.
    # Split to IMGSLI_GALLERY_DND_DEBUG if DnD needs its own gate later.
    # Per LOGGING.md noisy-subsystem rule: only explicit env, not default --debug.
    return _env_flag("IMGSLI_GALLERY_DEBUG")


def _emit(prefix: str, msg: str, *args, **kwargs) -> None:
    # When explicit env flag is set, use WARNING so the trace is visible
    # even without --debug (hang diagnosis before user knows to enable --debug).
    # Otherwise fall back to DEBUG (requires --debug / debug_mode_enabled).
    if _env_flag("IMGSLI_GALLERY_DEBUG"):
        logger.warning(prefix + " " + msg, *args, **kwargs)
    else:
        logger.debug(prefix + " " + msg, *args, **kwargs)


def gallery_debug(msg: str, *args, **kwargs) -> None:
    if gallery_debug_enabled():
        _emit("[gallery-debug]", msg, *args, **kwargs)


def gallery_dnd_debug(msg: str, *args, **kwargs) -> None:
    if gallery_dnd_debug_enabled():
        _emit("[gallery-dnd]", msg, *args, **kwargs)


def gallery_events_enabled() -> bool:
    """Raw Qt input firehose — separate flag per DEBUGGING.md rule 5.

    The causal tracer only sees dispatches; hover never dispatches, so it
    is invisible there by construction. This stream logs every Enter/Leave
    / mouse press-release-move with position + receiver instead. Default
    off, session-only, never mixed into the curated ``[gallery-debug]``
    stream.
    """
    return _env_flag("IMGSLI_GALLERY_EVENTS_DEBUG")


def gallery_event(msg: str, *args, **kwargs) -> None:
    if gallery_events_enabled():
        logger.warning("[gallery-events] " + msg, *args, **kwargs)


def ql_cover_enabled() -> bool:
    """First-frame warmup trace — separate flag per DEBUGGING.md rule 5.

    Env var:
        IMGSLI_QL_COVER_DEBUG=1 — quick-look canvas warmup timeline:
        populate (canvas/store/pixmap/warm-cold), cover create/sync/drop,
        canvas initialize/render/first-frame, watchdog/fallback.
    """
    return _env_flag("IMGSLI_QL_COVER_DEBUG")


def ql_cover(msg: str, *args, **kwargs) -> None:
    if ql_cover_enabled():
        logger.warning("[ql-cover] " + msg, *args, **kwargs)
