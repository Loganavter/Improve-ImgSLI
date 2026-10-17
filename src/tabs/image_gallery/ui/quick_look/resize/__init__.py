"""Quick Look card resize — border/ring drag + card re-layout (module → package).

Was ``ui/quick_look/resize.py``; split by concern into ``zones``, ``cursors``,
``relayout`` and ``handlers`` (plan-gallery-split-2026-10-17, Part C2). Bodies
moved verbatim; function names and signatures are unchanged, and every name is
re-exported here so ``tabs.image_gallery.ui.quick_look.resize`` keeps its full
surface for importers and tests.

The bodies are plain functions taking the overlay as their first argument
(``CODE_PATTERNS.md`` "thin owner + use_cases module"):

- ``zones``: border/ring hit-testing, size clamp, ``reposition_grip``.
- ``cursors``: resize-cursor apply + ql-resize debug tracing.
- ``relayout``: column floors, report-row re-seat, footer reflow.
- ``handlers``: press/move/release for the border strip + outer ring.

This is a NORMAL submodule of the ``quick_look`` package; the file/package
importlib shim lives in ``quick_look/__init__.py`` and is not involved here.

Session-only clamp (floor 1040x680), 8px inner border strip + outer ring
drags, card re-layout entry (``_relayout_on_card_resize``).
Extracted verbatim from ``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.

NOTE: user drags are ENABLED (``QL_RESIZABLE = True``) — border/ring
resizing live; nav-arrow walks, stranded-
drag guards (D2/D4), release clears (D3) and cursor clearing (D1/D5)
keep working. Pure geometry (``resize_zone_at`` / ``ring_zone_at`` /
``clamp_card_size``) is untouched.
"""

from __future__ import annotations

from .cursors import (
    _cursor_name,
    _effective_cursor_name,
    _override_cursor_name,
    _resize_dbg,
    _resize_trace_on,
    _winfilter_state,
    apply_resize_cursor,
    trace_move,
)
from .handlers import (
    handle_border_move,
    handle_border_press,
    handle_border_release,
    handle_ring_hover,
    handle_ring_press,
    handle_ring_release,
)
from .relayout import (
    _distribute_column_floors,
    _reflow_footer,
    _relayout_on_card_resize,
    _repin_after_card_resize,
    relayout_report_rows,
)
from .zones import (
    QL_RESIZABLE,
    RESIZE_BORDER_PX,
    clamp_card_size,
    reposition_grip,
    resize_cursor_for,
    resize_zone_at,
    ring_zone_at,
)
