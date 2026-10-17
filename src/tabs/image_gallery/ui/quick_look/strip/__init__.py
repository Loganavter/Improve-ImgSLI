"""Quick Look series strip — filmstrip (module -> package).

Was ``ui/quick_look/strip.py``; split by concern into ``helpers``, ``paint``,
``filters`` and ``rebuild`` (plan-gallery-split-2026-10-17, Part C2). Bodies
moved verbatim; function/class names and signatures are unchanged, and every
name is re-exported here so ``tabs.image_gallery.ui.quick_look.strip`` keeps
its full surface for importers and tests.

The bodies are plain functions taking the overlay as their first argument
(``CODE_PATTERNS.md`` "thin owner + use_cases module"):

- ``helpers``: geometry/ranking/family/fingerprint.
- ``paint``: thumb overlay painters, selection refresh, wheel scroll.
- ``filters``: wheel/lasso/repin ``QObject`` event filters.
- ``rebuild``: ``rebuild_strip`` + scroll follow (``ensure_strip_*``).

This is a NORMAL submodule of the ``quick_look`` package; the file/package
importlib shim lives in ``quick_look/__init__.py`` and is not involved here.
No QSS — painter pipeline only.
"""

from __future__ import annotations

from .filters import _StripLassoFilter, _StripRepinFilter, _StripWheelFilter
from .helpers import (
    _repin_strip_rank_buttons,
    _strip_family,
    _strip_family_add,
    _strip_fingerprint,
    _strip_rank_key,
    _strip_rank_text_and_style,
    _strip_thumb_pitch,
    _strip_wheel_step,
    open_strip_thumb_menu,
)
from .paint import (
    _refresh_strip_selection,
    _strip_apply_lasso_selection,
    _strip_lasso_pick,
    _strip_overlay_painter,
    _strip_refresh_selection,
    _strip_scroll_wheel,
    _strip_selection_overlay,
    _strip_source_outline,
)
from .rebuild import ensure_strip_scroll, ensure_strip_visible, rebuild_strip
