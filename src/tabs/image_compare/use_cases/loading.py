"""Pipeline-based loading — demand-driven via PipelineCache.

Thin owner target per CODE_PATTERNS — delegates to split modules
``slot.py``, ``session_bootstrap.py``, ``unify.py`` to stay <500 LOC
without Audit-Meta (docs/dev/plan_image_pipeline.md Phase 3).

Backward-compat re-exports kept so tests and controllers importing from
``loading`` continue to work.
"""

from tabs.image_compare.use_cases.loading_toast import (  # noqa: F401
    DECODE_DONE_PROGRESS,
    PYRAMID_START_PROGRESS,
    bump_loading_toast_pyramid_started,
    finish_loading_toast,
    finish_toast_for_unpaired_slot,
    get_toast_manager,
    mark_full_res_ready,
    set_loading_toast_progress,
    show_loading_toast,
)
from tabs.image_compare.use_cases.loading_pyramid import (  # noqa: F401
    on_pyramid_level_ready,
    pyramid_build_task,
    start_pyramid_builds,
)
from tabs.image_compare.use_cases.session_bootstrap import (  # noqa: F401
    ensure_current_slot,
    initialize_app_display,
    resync_current_image_slots,
)
from tabs.image_compare.use_cases.slot import (  # noqa: F401
    duplicate_image_to_slot,
    handle_full_image_loaded,
    load_images_from_paths,
    set_current_image,
)
from tabs.image_compare.use_cases.unify import (  # noqa: F401
    ensure_unification,
    on_unified_images_ready,
    trigger_preview_unification,
)

# Expose QTimer for legacy test monkeypatching (Phase 2 removed QTimer deferral,
# but tests still patch loading.QTimer — keep attribute for compat).
try:
    from PySide6.QtCore import QTimer  # noqa: F401
except Exception:  # pragma: no cover
    QTimer = None  # type: ignore
