# Audit-Meta: pattern=thin-owner reason="IC render gate thin owner delegates to use_cases/geometry,preview,background,schedule,render_gate per CODE_PATTERNS — sequencing only"
import logging

from PySide6.QtGui import QImage, QPixmap

from domain.types import Rect
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.display_image_picker import pick_display_image
from shared.rendering.image_identity import image_uid
from tabs.image_compare.canvas.registry import registry

_mlog = logging.getLogger("ImproveImgSLI.magnifier.render_flow")
from tabs.image_compare.canvas.presentation.surface import apply_store_to_canvas
from tabs.image_compare.canvas.helpers import get_canvas_widget, reset_canvas_overlays
from tabs.image_compare.canvas.scene import build_render_scene
from tabs.image_compare.debug import (
    ic_gap_debug as _gap_log,
    ic_gap_debug_enabled as _gap_enabled,
    ic_preview_debug as _preview_log,
    ic_preview_source_tier as _source_tier,
)

from .diff import sync_diff_texture
from .use_cases.preview import (  # noqa: F401 — thin delegators per CODE_PATTERNS
    _display_cache_key,
    _update_preview_tracking,
    pick_display_with_preview_backing,
)


from .use_cases.geometry import update_comparison_geometry
from .use_cases.geometry import _size_or_none  # noqa: F401 — helper for gap logs

_update_comparison_geometry = update_comparison_geometry  # noqa: F401 — keep private name for gate call-site


def _query_overlay(store, capability_id: str, default=None):
    command = registry().get_feature_command_by_alias(capability_id)
    if command is None:
        return default
    result = command(store)
    return default if result is None else result


# Background-tab gate — thin delegators (CODE_PATTERNS).
# Bodies live in ``use_cases/background.py`` + ``use_cases/schedule.py``;
# this module keeps the imports so callers via ``render_flow`` keep working.
from .use_cases.background import (  # noqa: F401 — thin delegator forwarding
    flush_stale_render as _flush_stale_render_impl,
    is_background_tab as _is_background_tab_impl,
    is_render_stale as _is_render_stale_impl,
    mark_render_stale as _mark_render_stale_impl,
)
from .use_cases.schedule import schedule_update as _schedule_update_impl


def _is_background_tab(presenter) -> bool:
    """Thin delegator to ``use_cases.background.is_background_tab``.

    Preserve ``stack.currentWidget`` vs ``isVisible`` fallback per
    ``docs/dev/tabs/isolation.md`` (body lives in background.py).
    """
    return _is_background_tab_impl(presenter)


def _mark_render_stale(presenter) -> None:
    return _mark_render_stale_impl(presenter)


def is_render_stale(presenter) -> bool:
    return _is_render_stale_impl(presenter)


def flush_stale_render(presenter) -> bool:
    return _flush_stale_render_impl(presenter)


# 500ms throttle lives in ``use_cases/schedule.py`` — keep alias so
# ``schedule_update._last_armed_log`` is shared (no wrapper-split state).
schedule_update = _schedule_update_impl

# Public aliases for new-name imports (``is_background_tab`` etc).
is_background_tab = _is_background_tab_impl  # noqa: F401
mark_render_stale = _mark_render_stale_impl  # noqa: F401


_last_document_log_sig = None  # type: ignore
_last_one_side_log_sig = None  # type: ignore
_last_gap_geometry_sig = None  # type: ignore
_last_gap_geometry_input_sig = None  # type: ignore
_last_gap_pick_sig = None  # type: ignore
_last_gap_apply_sig = None  # type: ignore
_last_schedule_log_sig = None  # type: ignore

def update_comparison_if_needed(presenter):
    """Thin delegator — sequencing lives in ``use_cases/render_gate.py``.

    Keeps ``CODE_PATTERNS: thin owner + use_cases`` (owner holds wiring /
    Qt-required names, bodies are ``func(presenter, ...)`` in ``use_cases/``).
    See ``docs/dev/plan_rhi_renderer_decomposition.md`` for the thin-owner
    template and ``use_cases/render_gate.py`` for the ``_update_comparison_geometry
    → have1/have2 wait → bg_is_dirty → pick → apply_store_to_canvas`` sequencing.
    """
    from .use_cases.render_gate import update_comparison_if_needed as _gate
    return _gate(presenter)

def should_use_dirty_rects_optimization(presenter, render_params_dict, label_dims=None):
    if not presenter.store.viewport.interaction_state.is_interactive_mode:
        return False
    if render_params_dict.get("use_magnifier", False):
        return False
    if not presenter._cached_base_pixmap or presenter._cached_base_pixmap.isNull():
        return False
    if label_dims is None:
        label_dims = presenter.get_current_label_dimensions()

    current_params = (
        render_params_dict.get("diff_mode", "off"),
        render_params_dict.get("channel_view_mode", "RGB"),
        render_params_dict.get("is_horizontal", False),
        render_params_dict.get("include_file_names_in_saved", False),
        label_dims,
    )
    if (
        presenter._cached_render_params
        and presenter._cached_render_params[:4] != current_params[:4]
    ):
        return False
    return True
