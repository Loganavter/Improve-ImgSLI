"""Quick look metrics — plain functions taking overlay as first arg.

Was ``ui/quick_look/metrics.py``; split by concern into ``theme``, ``cache`` and
``rows`` (plan-gallery-split-2026-10-17, Part C2). Bodies moved verbatim;
function names and signatures are unchanged, and every name is re-exported here
so ``tabs.image_gallery.ui.quick_look.metrics`` keeps its full surface for
importers and tests.

- ``theme``: colour-token/translator/judgment-domain reads.
- ``cache``: fingerprint identity + bounded row-container cache (hit/store).
- ``rows``: ``rebuild_metrics`` / ``warm_metrics_for`` / ``ssim_subline``.

This is a NORMAL submodule of the ``quick_look`` package; the file/package
importlib shim lives in ``quick_look/__init__.py`` and is not involved here.
"""

from __future__ import annotations

from .cache import (
    _METRICS_ROW_CACHE_MAX,
    _metrics_cache_hit,
    _metrics_cache_store,
    _metrics_fingerprint,
    _metrics_series_snapshot,
    _mode_str_for,
)
from .rows import rebuild_metrics, ssim_subline, warm_metrics_for
from .theme import (
    _is_dark_theme,
    _metric_label,
    _metric_note,
    _overlay_judgment_domain,
    _ql_text,
    _token_qcolor,
)
