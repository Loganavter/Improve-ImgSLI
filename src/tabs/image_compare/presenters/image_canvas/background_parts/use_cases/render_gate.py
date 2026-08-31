# Audit-Meta: pattern=thin-owner-target reason="render_gate thin orchestrator per CODE_PATTERNS — delegates to have_gate, bg_dirty, geometry, preview"
"""Render gate — thin orchestrator for ``update_comparison_if_needed``.

Thin-owner target per ``docs/dev/CODE_PATTERNS.md`` and template
``docs/dev/plan_rhi_renderer_decomposition.md`` (Phase 2-5 pattern:
``func(renderer, ...)`` in ``use_cases/``). Extracted from
``background_parts/render_flow.py:501`` (~620L ``update_comparison_if_needed``).

Sequencing owned here::

    geometry.update_comparison_geometry
      → have_gate (have1/have2 wait + live-half)
      → bg_dirty (bg_is_dirty + ssim diff + pick/gap/apply)
      → overlay/magnifier rebuild

Owner (``render_flow.py``) keeps only wiring / instance state
(``presenter.widget``, ``presenter.store``, ``_last_*_signature`` caches).
``use_cases/`` modules own the bodies as plain functions taking
``presenter`` as first argument. Throttle globals live in the module
that owns the logging decision (``_last_document_log_sig`` here,
``_last_one_side_log_sig`` in ``have_gate``, ``_last_gap_*`` in
``bg_dirty``).

Verification: ``QT_QPA_PLATFORM=offscreen pytest src/tabs/image_compare/tests/render/ -q`` stays ``211 passed``.
"""

from __future__ import annotations

from shared.rendering.image_identity import image_uid
from tabs.image_compare.canvas.helpers import reset_canvas_overlays as _orig_reset_canvas_overlays
from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.debug import ic_preview_debug as _preview_log

from .bg_dirty import handle_background
from .geometry import update_comparison_geometry
from .have_gate import _peek_sources, handle_have_gate
from .preview import _update_preview_tracking

# Backward compat re-exports — external callers may import from render_gate
from .bg_dirty import compute_background_signature as compute_background_signature  # noqa: F401
from .bg_dirty import is_background_dirty as is_background_dirty  # noqa: F401
from .have_gate import _have_gate as _have_gate  # noqa: F401
# _peek_sources already imported above; re-exported for tests

_last_document_log_sig = None  # type: ignore


def _resolve_rf(name, orig):
    try:
        import tabs.image_compare.presenters.image_canvas.background_parts.render_flow as _rf

        patched = getattr(_rf, name, None)
        if patched is not None:
            return patched
    except Exception:
        pass
    return orig


def _reset_canvas_overlays(label):
    return _resolve_rf("reset_canvas_overlays", _orig_reset_canvas_overlays)(label)


def _query_overlay(store, capability_id: str, default=None):
    command = registry().get_feature_command_by_alias(capability_id)
    if command is None:
        return default
    result = command(store)
    return default if result is None else result


def _pick_and_apply(presenter, peeked, current_label_dims, source_key=None):  # noqa: ARG001
    """Backward compat stub — real body now in ``bg_dirty.handle_background``."""
    raise NotImplementedError("pick_and_apply moved to bg_dirty.handle_background")


def update_comparison_if_needed(presenter):
    """Thin orchestrator — sequencing only, bodies in ``use_cases/*``."""
    from .background import is_background_tab as _is_background_tab, mark_render_stale as _mark_render_stale

    if _is_background_tab(presenter):
        _preview_log("update: deferred - background tab (render marked stale)")
        _mark_render_stale(presenter)
        return False
    if not getattr(presenter.main_window_app, "_is_ui_stable", False) or presenter.store.viewport.interaction_state.resize_in_progress:
        _preview_log("update: deferred - ui not stable / resize in progress")
        return False
    if not presenter.main_window_app.isVisible() or presenter.main_window_app.isMinimized():
        _preview_log("update: deferred - window hidden or minimized")
        return False
    label_width, label_height = presenter.get_current_label_dimensions()
    if label_width <= 2 or label_height <= 2:
        _preview_log("update: deferred - label too small (%dx%d)", label_width, label_height)
        return False
    _document = presenter.store.get_session_state_slot("document")
    if _document is None:
        _preview_log("update: deferred - no document slot")
        return False

    peeked = _peek_sources(presenter, _document)
    source1 = peeked["source1"]
    source2 = peeked["source2"]

    global _last_document_log_sig
    _doc_sig = (
        image_uid(peeked["peeked_pixel1"]) if peeked["peeked_pixel1"] is not None else None,
        image_uid(peeked["peeked_pixel2"]) if peeked["peeked_pixel2"] is not None else None,
        image_uid(peeked["peeked_preview1"]) if peeked["peeked_preview1"] is not None else None,
        image_uid(peeked["peeked_preview2"]) if peeked["peeked_preview2"] is not None else None,
        image_uid(presenter.store.viewport.session_data.image_state.image1) if presenter.store.viewport.session_data.image_state.image1 is not None else None,
        image_uid(presenter.store.viewport.session_data.image_state.image2) if presenter.store.viewport.session_data.image_state.image2 is not None else None,
        peeked["path1"],
        peeked["path2"],
    )
    if _doc_sig != _last_document_log_sig:
        _last_document_log_sig = _doc_sig
        _preview_log(
            "document state: pixel uid1=%s uid2=%s preview uid1=%s uid2=%s image_state uid1=%s uid2=%s paths=%s/%s",
            _doc_sig[0], _doc_sig[1], _doc_sig[2], _doc_sig[3], _doc_sig[4], _doc_sig[5], _doc_sig[6], _doc_sig[7],
        )

    update_comparison_geometry(presenter, source1, source2, label_width, label_height)

    if getattr(presenter.store.viewport.session_data.render_cache, "unification_in_progress", False):
        if presenter.store.viewport.session_data.image_state.image1 is None:
            if source1 is None or source2 is None:
                _preview_log("update: deferred - unification in progress, image1 not ready")
                return False
            _preview_log("update: unification in progress but both document sources ready - proceeding with preview/full_res (image_state not yet ready)")

    if presenter.store.viewport.view_state.showing_single_image_mode != 0:
        _preview_log("update: single-image mode %s - display_single_image_on_label", presenter.store.viewport.view_state.showing_single_image_mode)
        from shared.rendering.display_image_picker import pick_display_image as _pick

        image_to_show = (
            _pick(presenter.store.viewport.session_data.image_state.image1, source1, peeked["peeked_preview1"], None)
            if presenter.store.viewport.view_state.showing_single_image_mode == 1
            else _pick(presenter.store.viewport.session_data.image_state.image2, source2, peeked["peeked_preview2"], None)
        )
        presenter.view.display_single_image_on_label(image_to_show)
        try:
            slot = int(presenter.store.viewport.view_state.showing_single_image_mode)
            if image_to_show is not None:
                _update_preview_tracking(presenter, {slot: image_to_show})
        except Exception:
            pass
        return False

    # have1/have2 wait + live-half paint (owned by have_gate)
    if handle_have_gate(presenter, source1, source2, _document, peeked):
        return False

    # bg dirty + diff ssim + pick/gap/apply (owned by bg_dirty)
    current_label_dims = (label_width, label_height)
    if handle_background(presenter, source1, source2, peeked, current_label_dims, label_width, label_height):
        return False

    # --- overlay / magnifier ---
    visible_models = [model for model in (_query_overlay(presenter.store, "overlay.all_states", ()) or ()) if bool(model.get("visible", False))]
    _should_render = bool(_query_overlay(presenter.store, "overlay.enabled", False))
    if _should_render and visible_models:
        current_mag_sig = presenter.overlay.get_signature()
        last_mag_sig = getattr(presenter, "_last_mag_signature", None)
        image_label = presenter.widget.image_label
        try:
            from shared.rendering.image_identity import image_uid as _mag_image_uid

            _rc = presenter.store.viewport.session_data.render_cache
            _cached_diff = getattr(_rc, "cached_diff_image", None)
            _cached_diff_uid = _mag_image_uid(_cached_diff) if _cached_diff is not None else None
            _cached_diff_source_key = getattr(_rc, "cached_diff_source_key", None)
        except Exception:
            _cached_diff_uid = None
            _cached_diff_source_key = None
        try:
            _pending_diff_key = getattr(presenter, "_pending_cached_diff_request_key", None)
        except Exception:
            _pending_diff_key = None
        current_mag_state = (current_mag_sig, getattr(image_label, "_source_images_ready", False), tuple(getattr(image_label, "_source_image_ids", []) or []), _cached_diff_uid, _cached_diff_source_key, _pending_diff_key)
        mag_is_dirty = current_mag_state != last_mag_sig
        if mag_is_dirty:
            presenter.overlay.rebuild_overlay()
            presenter._last_mag_signature = current_mag_state
            return True
    else:
        _reset_canvas_overlays(presenter.widget.image_label)
        presenter._last_mag_signature = None
    return False
