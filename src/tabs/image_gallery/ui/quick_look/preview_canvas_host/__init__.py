"""Quick-look GPU preview hosting — canvas slot lifecycle (no owner state).
Audit-Meta: pattern=thin-owner size=exempt reason="package shell: re-exports the split canvas-slot lifecycle for importers/tests"

Split from ``preview.py`` (500-line contract gate): the canvas slot
lifecycle lives here, preview pixmaps stay there. The QRhiWidget canvas is
the only live image surface; the cover plate is a static pre-first-frame
fallback (kept when no frame ever presents). All functions fail open —
import this module lazily and treat ``None`` / ``False`` as "no GPU today".

Module -> package (plan-gallery-split-2026-10-17, Part C2): this was
``preview_canvas_host.py``; the host-glue bodies moved verbatim into five
concern modules — function names and signatures unchanged — and are
re-exported here so ``tabs.image_gallery.ui.quick_look.preview_canvas_host``
keeps its full surface for importers and tests:

- ``store_cache``: QL-cover debug gates + the bounded preview/tiled store
  memos (lookup/store/discard/drop, close, memo-identity).
- ``tiled_source``: canvas ensure + the tiled full-store source (bounded
  coarse build, uncapped worker decode, populate).
- ``prefetch``: dwell-gated tiled kick, settle-time neighbor prefetch and
  metrics warm.
- ``cover``: reveal/fit of the first-frame cover and the canvas slot.
- ``fallback``: RHI-fail probe/recovery and the release paths.

Cross-concern calls resolve through this package namespace at call time
(``_refs.host()``), so this module stays the single patch point (e.g. tests
patching ``_ensure_preview_canvas``); direct submodule imports would bind
the originals once and silently bypass those patches.
"""

from __future__ import annotations

from .cover import (
    _cover_pixmap_from_full,
    _cover_until_first_frame,
    _drop_cover,
    _fit_cover,
    _fit_preview_slot,
    reveal_pending_preview_canvas,
    reveal_preview_canvas,
    settle_first_frame,
)
from .fallback import (
    _drop_poisoned_canvas,
    _install_memo_probe,
    _on_canvas_rhi_failed,
    _RHI_MAX_RECOVERIES,
    _RHI_PREFRAME_FAIL_THRESHOLD,
    _watch_canvas_rhi,
    _wire_canvas_fallback,
    release_preview_canvas,
    release_preview_canvas_for_walk,
)
from .prefetch import (
    _arm_tiled_dwell,
    _fire_scheduled_prefetch,
    _prefetch_neighbors,
    _schedule_prefetch,
    _warm_metrics_neighbors,
)
from .store_cache import (
    _close_preview_store,
    _close_store_quiet,
    _drop_preview_store_cache,
    _drop_tiled_store_cache,
    _is_preview_store_memo,
    _preview_store_cache_discard,
    _preview_store_cache_lookup,
    _preview_store_cache_max,
    _preview_store_cache_store,
    _qlc_enabled,
    _qlc_log,
    _tiled_store_cache_lookup,
    _tiled_store_cache_store,
)
from .tiled_source import (
    _coarse_store_for,
    _decode_full_store_uncapped,
    _ensure_preview_canvas,
    _populate_preview_canvas,
    _populate_tiled_source,
    _store_from_pixmap,
)
