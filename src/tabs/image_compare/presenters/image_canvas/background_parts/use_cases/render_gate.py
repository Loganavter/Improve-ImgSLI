# Audit-Meta: pattern=thin-owner-target size=exempt reason="render_gate orchestrator — thin-owner target per CODE_PATTERNS, delegates geometry/preview/background; sequencing only"
"""Render gate — thin orchestrator for ``update_comparison_if_needed``.

Thin-owner target per ``docs/dev/CODE_PATTERNS.md`` and template
``docs/dev/plan_rhi_renderer_decomposition.md`` (Phase 2-5 pattern:
``func(renderer, ...)`` in ``use_cases/``). Extracted from
``background_parts/render_flow.py:501`` (~620L ``update_comparison_if_needed``).

After the three other buckets (geometry, preview, background) are extracted,
``render_flow.update_comparison_if_needed`` becomes a thin delegator
(``CODE_PATTERNS: function-taking-owner``) that sequences::

    geometry.update_comparison_geometry
      → have1/have2 wait (one-side gate)
      → bg_is_dirty (signature + Store image_state uids + label dims)
      → preview.pick_display_with_preview_backing
      → background.apply_store_to_canvas (or scene-only repaint)

Owner (``render_flow.py``) keeps only wiring / instance state
(``presenter.widget``, ``presenter.store``, ``_last_*_signature`` caches,
Qt-required ``schedule_update``/``flush_stale_render``). ``use_cases/`` modules
own the bodies as plain functions taking ``presenter`` as first argument — no
second class, no import cycle (``CODE_PATTERNS: Why functions-taking-owner``).

Throttle globals (``_last_document_log_sig``, ``_last_one_side_log_sig``,
``_last_gap_pick_sig``, ``_last_gap_apply_sig``) live here — the module that
owns the logging decision — not in ``render_flow.py`` (same rule as
``plan_rhi_renderer_decomposition.md: Locked decisions — throttle globals``).

Status: skeleton for next wave. Geometry (``geometry.py`` 196L) and preview
(``preview.py`` 158L) already landed as thin-owner targets; background
(``background.py`` / signature + apply) is the remaining bucket. This file
currently orchestrates via imports from those landed modules and inlines the
not-yet-extracted blocks with ``TODO(background)`` markers so the next wave
can wire the delegator without re-researching the sequencing.

Verification (pre-extraction): ``QT_QPA_PLATFORM=offscreen pytest
src/tabs/image_compare/tests/render/ -q`` stays ``211 passed`` — the
orchestrator is not yet wired into ``render_flow`` (skeleton only, not
imported), so the existing gate remains the single source of truth until
background lands. After wiring, the same suite + ``tests/contracts -q`` and
``IMGSLI_IC_PREVIEW_DEBUG=1`` trace identity are the gates
(``plan_rhi_renderer_decomposition.md: Goal``).
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QPixmap

from shared.rendering.image_identity import image_uid
from tabs.image_compare.canvas.helpers import get_canvas_widget as _orig_get_canvas_widget
from tabs.image_compare.canvas.helpers import reset_canvas_overlays as _orig_reset_canvas_overlays
from tabs.image_compare.canvas.presentation.surface import apply_store_to_canvas as _orig_apply_store_to_canvas
from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.canvas.scene import build_render_scene as _orig_build_render_scene
from tabs.image_compare.debug import (
    ic_gap_debug as _gap_log,
    ic_gap_debug_enabled as _gap_enabled,
    ic_preview_debug as _preview_log,
    ic_preview_source_tier as _source_tier,
)

from tabs.image_compare.presenters.image_canvas.background_parts.diff import sync_diff_texture as _orig_sync_diff_texture  # noqa: F401 — parent package, not use_cases
from .geometry import _size_or_none, update_comparison_geometry


def _resolve_rf(name, orig):
    """Return patched ``render_flow.<name>`` if tests monkeypatched it, else ``orig``."""
    try:
        import tabs.image_compare.presenters.image_canvas.background_parts.render_flow as _rf

        patched = getattr(_rf, name, None)
        if patched is not None:
            return patched
    except Exception:
        pass
    return orig


def _get_canvas_widget(widget):
    return _resolve_rf("get_canvas_widget", _orig_get_canvas_widget)(widget)


def _reset_canvas_overlays(label):
    return _resolve_rf("reset_canvas_overlays", _orig_reset_canvas_overlays)(label)


def _apply_store_to_canvas(*a, **kw):
    return _resolve_rf("apply_store_to_canvas", _orig_apply_store_to_canvas)(*a, **kw)


def _build_render_scene(*a, **kw):
    return _resolve_rf("build_render_scene", _orig_build_render_scene)(*a, **kw)


def _sync_diff_texture(*a, **kw):
    return _resolve_rf("sync_diff_texture", _orig_sync_diff_texture)(*a, **kw)
from .preview import (
    _display_cache_key,
    _update_preview_tracking,
    pick_display_with_preview_backing,
)

def compute_background_signature(presenter, source1, source2):
    sig = presenter.background.get_background_signature(source1, source2)
    try:
        _is1 = presenter.store.viewport.session_data.image_state.image1
        _is2 = presenter.store.viewport.session_data.image_state.image2
    except Exception:
        _is1 = _is2 = None
    return (sig, image_uid(_is1) if _is1 is not None else None, image_uid(_is2) if _is2 is not None else None)


def is_background_dirty(presenter, current_bg_sig, current_label_dims):
    last_bg_sig = getattr(presenter, "_last_bg_signature", None)
    label_dims_changed = presenter._last_label_dims != current_label_dims
    return (current_bg_sig != last_bg_sig) or label_dims_changed or (presenter._cached_base_pixmap is None)


_mlog = logging.getLogger("ImproveImgSLI.magnifier.render_flow")

_last_document_log_sig = None  # type: ignore
_last_one_side_log_sig = None  # type: ignore
_last_gap_pick_sig = None  # type: ignore
_last_gap_apply_sig = None  # type: ignore
_last_schedule_log_sig = None  # type: ignore


def _peek_sources(presenter, document):
    """Resolve (pixel, preview) per slot via PipelineCache / PipelineView.

    Mirrors ``render_flow.py:538-632`` peek helpers — kept here as the gate's
    source-resolution preamble before geometry. Single place to swap to
    ``_peek``/``_peek_pixel``/``_peek_preview`` once background lands.
    """
    _pl = None
    _path1 = getattr(document, "image1_path", None)
    _path2 = getattr(document, "image2_path", None)
    try:
        _ctrl = getattr(presenter, "session_controller", None) or getattr(presenter, "controller", None)
        if _ctrl is None:
            try:
                from tabs.image_compare.pipeline.cache import PipelineCache as _PC  # noqa: F401

                _mw = getattr(presenter, "main_window_app", None)
                if _mw is not None:
                    _tab = getattr(getattr(_mw, "tab_registry", None), "get_tab", lambda *_a, **_kw: None)("image_compare")
                    _ctrl = getattr(_tab, "session_controller", None) if _tab else None
            except Exception:
                _ctrl = None
        _pl = getattr(_ctrl, "pipeline", None) if _ctrl is not None else None
    except Exception:
        _pl = None

    def _peek(path):
        if _pl is not None and path:
            try:
                c = _pl.peek(path)
                if c is not None and getattr(c, "is_open", True):
                    if hasattr(c, "isNull"):
                        try:
                            if not c.isNull():
                                return c
                        except Exception:
                            return c
                    else:
                        return c
            except Exception:
                pass
            try:
                p = _pl.peek_preview(path)
                if p is not None:
                    if hasattr(p, "isNull"):
                        try:
                            if not p.isNull():
                                return p
                        except Exception:
                            return p
                    else:
                        return p
            except Exception:
                pass
        return None

    def _peek_pixel(path):
        if _pl is not None and path:
            try:
                return _pl.peek(path)
            except Exception:
                return None
        return None

    def _peek_preview(path):
        if _pl is not None and path:
            try:
                return _pl.peek_preview(path)
            except Exception:
                return None
        return None

    _peeked_pixel1 = _peek_pixel(_path1)
    _peeked_pixel2 = _peek_pixel(_path2)
    _peeked_preview1 = _peek_preview(_path1)
    _peeked_preview2 = _peek_preview(_path2)
    _img_state = presenter.store.viewport.session_data.image_state
    source1 = _peeked_pixel1 or _peeked_preview1 or getattr(_img_state, "image1", None) or _peek(_path1)
    source2 = _peeked_pixel2 or _peeked_preview2 or getattr(_img_state, "image2", None) or _peek(_path2)
    return {
        "path1": _path1,
        "path2": _path2,
        "peeked_pixel1": _peeked_pixel1,
        "peeked_pixel2": _peeked_pixel2,
        "peeked_preview1": _peeked_preview1,
        "peeked_preview2": _peeked_preview2,
        "source1": source1,
        "source2": source2,
        "pipeline": _pl,
    }


def _have_gate(presenter, source1, source2, document):
    """Have1/have2 wait gate — one-side missing handling.

    Returns (have1, have2, should_return, reason). When ``should_return`` is
    True, caller should return ``False`` (deferred) — either waiting for the
    other side or having just painted the live half via
    ``display_single_image_on_label``. Delegates the live-half pick to
    ``preview`` helpers once background lands; until then keeps the existing
    ``render_flow`` live-half path inline (marked TODO).
    """
    have1 = bool(presenter.store.viewport.session_data.image_state.image1 or source1)
    have2 = bool(presenter.store.viewport.session_data.image_state.image2 or source2)
    if not have1 and not have2:
        _preview_log("update: no sources on either side - label cleared")
        presenter.widget.image_label.clear()
        presenter.current_displayed_pixmap = None
        return have1, have2, True, "no_sources"
    if not have1 or not have2:
        global _last_one_side_log_sig
        try:
            other_list_empty = len(document.image_list2) == 0 if have1 else len(document.image_list1) == 0
        except AttributeError:
            other_list_empty = False
        other_has_path = (document.image2_path is not None) if have1 else (document.image1_path is not None)
        try:
            _pending = getattr(presenter.store, "_pending_image_loads", None)  # type: ignore[attr-defined]
            _ctrl = getattr(presenter, "controller", None) or getattr(presenter, "_controller", None)
            if _ctrl is None:
                _w = getattr(presenter, "widget", None)
                _ctrl = getattr(_w, "_controller", None) if _w is not None else None
            has_pending_other = False
            if _pending:
                other_slot = 2 if have1 else 1
                has_pending_other = any(slot == other_slot for slot, _p in _pending)
            elif _ctrl is not None:
                _cp = getattr(_ctrl, "_pending_image_loads", None)
                if _cp:
                    other_slot = 2 if have1 else 1
                    has_pending_other = any(slot == other_slot for slot, _p in _cp)
            else:
                has_pending_other = False
        except Exception:
            has_pending_other = False
        if other_list_empty or other_has_path or has_pending_other:
            _one_side_sig = (have1, have2, image_uid(source1) if source1 else None, image_uid(source2) if source2 else None, other_list_empty, other_has_path, has_pending_other)
            if _one_side_sig != _last_one_side_log_sig:
                _last_one_side_log_sig = _one_side_sig
                _preview_log(
                    "update: one side missing (have1=%s have2=%s) - wait for other side (other_empty=%s other_has_path=%s pending_other=%s)",
                    have1, have2, other_list_empty, other_has_path, has_pending_other,
                )
            return have1, have2, True, "wait_other_side"
        # live-half paint — TODO(background): delegate to preview.pick_live_half
        return have1, have2, False, "live_half"
    return have1, have2, False, "dual"


def _pick_and_apply(presenter, peeked, current_label_dims, source_key=None):
    """Pick (preview-backed) + apply_store_to_canvas or scene-only repaint.

    This is the ``bg_is_dirty`` branch ``render_flow.py:854-1155``. Kept inline
    with TODO markers until ``background.py`` lands; then delegates to
    ``background.apply_store_if_dirty``. Preview tracking (``_update_preview_tracking``)
    stays via ``preview`` import (already landed).
    """
    # TODO(background): move entire block to background.apply_store_if_dirty(presenter, peeked, current_label_dims, source_key)
    # For skeleton, keep signature parity with future use_cases/background.py so the
    # delegator below can be switched to ``return apply_store_if_dirty(...)`` in one line.
    raise NotImplementedError("pick_and_apply not yet extracted — background bucket pending; see render_flow.py:854")


def update_comparison_if_needed(presenter):
    """Thin orchestrator — sequencing only, bodies in ``use_cases/*``.

    Intended final wiring in ``render_flow.py``::

        from .use_cases.render_gate import update_comparison_if_needed as _gate
        def update_comparison_if_needed(presenter):
            return _gate(presenter)

    Steps (mirrors current ``render_flow.py:501`` gate)::

        1. background_tab / ui-stable / window-visible / label-dims / document gates
        2. _peek_sources → source1/source2 + peeked_* (pipeline view)
        3. throttled document-state log
        4. geometry.update_comparison_geometry(presenter, source1, source2, lw, lh)
        5. unification_in_progress gate
        6. single-image-mode gate
        7. _have_gate → wait or live-half paint
        8. bg signature → is_background_dirty → diff_mode ssim + sync_diff_texture
        9. if bg_is_dirty and is_canvas_widget: _pick_and_apply (picker + GPU apply)
           else: skip apply → overlay/magnifier branch
        10. overlay/magnifier rebuild or reset_canvas_overlays

    Returns ``bool`` (magnifier rebuilt) like the current gate, preserving the
    ``schedule_update`` contract.
    """
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

    # --- throttled document-state log (throttle lives here, not in render_flow) ---
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

    # --- 4. geometry (already extracted) ---
    update_comparison_geometry(presenter, source1, source2, label_width, label_height)

    # --- 5. unification gate ---
    if getattr(presenter.store.viewport.session_data.render_cache, "unification_in_progress", False):
        if presenter.store.viewport.session_data.image_state.image1 is None:
            if source1 is None or source2 is None:
                _preview_log("update: deferred - unification in progress, image1 not ready")
                return False
            _preview_log("update: unification in progress but both document sources ready - proceeding with preview/full_res (image_state not yet ready)")

    # --- 6. single-image mode ---
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

    # --- 7. have1/have2 wait gate ---
    have1, have2, should_return, reason = _have_gate(presenter, source1, source2, _document)
    if reason == "no_sources":
        return False
    if reason == "wait_other_side":
        return False
    if reason == "live_half":
        # live-half paint kept inline until background lands; mirrors render_flow:781-802
        from shared.rendering.display_image_picker import pick_display_image as _pick

        global _last_one_side_log_sig
        _one_side_sig = (have1, have2, image_uid(source1) if source1 else None, image_uid(source2) if source2 else None)
        if _one_side_sig != _last_one_side_log_sig:
            _last_one_side_log_sig = _one_side_sig
            _preview_log("update: one side missing (have1=%s have2=%s) - display live half", have1, have2)
        image_to_show = (
            _pick(presenter.store.viewport.session_data.image_state.image1, source1, peeked["peeked_preview1"], None)
            if have1
            else _pick(presenter.store.viewport.session_data.image_state.image2, source2, peeked["peeked_preview2"], None)
        )
        presenter.view.display_single_image_on_label(image_to_show)
        try:
            slot = 1 if have1 else 2
            if image_to_show is not None:
                _update_preview_tracking(presenter, {slot: image_to_show})
        except Exception:
            pass
        return False

    # --- 8. bg signature + dirty ---
    current_bg_sig = compute_background_signature(presenter, source1, source2)
    current_label_dims = (label_width, label_height)
    bg_is_dirty = is_background_dirty(presenter, current_bg_sig, current_label_dims)
    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    if presenter.view.is_canvas_widget() and diff_mode == "ssim":
        request_cached_diff = registry().get_feature_command_by_alias("overlay.request_cached_diff")
        if request_cached_diff is not None:
            request_cached_diff(presenter, source1, source2, diff_mode)
    if presenter.view.is_canvas_widget():
        _sync_diff_texture(presenter, diff_mode)

    # --- 9. pick + apply — mirrors render_flow.py:447-746, now owned here ---
    if bg_is_dirty:
        if presenter.view.is_canvas_widget():
            image_label = _get_canvas_widget(presenter.widget)
            _last_display_uids = getattr(presenter, "_last_display_uids", None) or {}
            _superseded_uids = getattr(presenter, "_last_superseded_preview_uid", None) or {}
            img1 = pick_display_with_preview_backing(
                presenter.store.viewport.session_data.image_state.image1,
                peeked["peeked_preview1"],
                peeked["peeked_pixel1"],
                None,
                last_applied_uid=_last_display_uids.get(1),
                superseded_preview_uid=_superseded_uids.get(1),
            )
            img2 = pick_display_with_preview_backing(
                presenter.store.viewport.session_data.image_state.image2,
                peeked["peeked_preview2"],
                peeked["peeked_pixel2"],
                None,
                last_applied_uid=_last_display_uids.get(2),
                superseded_preview_uid=_superseded_uids.get(2),
            )
            for _slot_num, _picked, _cand_preview in (
                (1, img1, peeked["peeked_preview1"]),
                (2, img2, peeked["peeked_preview2"]),
            ):
                _cand_full = peeked["peeked_pixel1"] if _slot_num == 1 else peeked["peeked_pixel2"]
                _tier = "full_res" if _picked is _cand_full and _picked is not None else _source_tier(
                    _picked,
                    peeked["peeked_preview1"] if _slot_num == 1 else peeked["peeked_preview2"],
                    None,
                    presenter.store.viewport.session_data.image_state.image1 if _slot_num == 1 else presenter.store.viewport.session_data.image_state.image2,
                )
                _preview_log(
                    "pick slot%d: preview_uid=%s full_res_uid=%s last_applied=%s superseded=%s -> picked uid=%s tier=%s fresh=%s",
                    _slot_num,
                    image_uid(_cand_preview) if _cand_preview is not None else None,
                    image_uid(_cand_full) if _cand_full is not None else None,
                    _last_display_uids.get(_slot_num),
                    _superseded_uids.get(_slot_num),
                    image_uid(_picked) if _picked is not None else None,
                    _tier,
                    _picked is _cand_preview if _cand_preview is not None else False,
                )
            render_img1, render_img2 = img1, img2
            try:
                _update_preview_tracking(presenter, {1: render_img1, 2: render_img2})
            except Exception:
                pass
            if _gap_enabled():
                try:
                    _gap_sig = (
                        image_uid(render_img1) if render_img1 is not None else None,
                        image_uid(render_img2) if render_img2 is not None else None,
                        _size_or_none(render_img1),
                        _size_or_none(render_img2),
                        getattr(presenter.store.viewport.session_data.render_cache, "unification_in_progress", False),
                    )
                    global _last_gap_pick_sig
                    if _gap_sig != _last_gap_pick_sig:
                        _last_gap_pick_sig = _gap_sig
                        _t1_gap = "full_res" if render_img1 is peeked["peeked_pixel1"] and render_img1 is not None else _source_tier(render_img1, peeked["peeked_preview1"], None, presenter.store.viewport.session_data.image_state.image1)
                        _t2_gap = "full_res" if render_img2 is peeked["peeked_pixel2"] and render_img2 is not None else _source_tier(render_img2, peeked["peeked_preview2"], None, presenter.store.viewport.session_data.image_state.image2)
                        _mixed = (_t1_gap != _t2_gap)
                        _geom = getattr(presenter.store.viewport.geometry_state, "image_display_rect_on_label", None)
                        _pix_w = getattr(presenter.store.viewport.geometry_state, "pixmap_width", None)
                        _pix_h = getattr(presenter.store.viewport.geometry_state, "pixmap_height", None)
                        _gap_log(
                            "pick->gap slot1 tier=%s size=%s slot2 tier=%s size=%s mixed=%s unified=%s geom=%s pixmap=%sx%s label=%dx%d gap_id=%s/%s",
                            _t1_gap,
                            _size_or_none(render_img1),
                            _t2_gap,
                            _size_or_none(render_img2),
                            _mixed,
                            getattr(presenter.store.viewport.session_data.render_cache, "unification_in_progress", False),
                            _geom,
                            _pix_w,
                            _pix_h,
                            label_width,
                            label_height,
                            image_uid(render_img1) if render_img1 is not None else None,
                            image_uid(render_img2) if render_img2 is not None else None,
                        )
                        if _mixed:
                            try:
                                from core.tracing.tracer import Tracer
                                if Tracer.enabled():
                                    Tracer.instance().record(
                                        "ic.gap.mixed_tier",
                                        f"mixed tier pick gap risk { _t1_gap}/{_t2_gap}",
                                        {"tier1": _t1_gap, "tier2": _t2_gap, "size1": str(_size_or_none(render_img1)), "size2": str(_size_or_none(render_img2)), "mixed": _mixed},
                                    )
                            except Exception:
                                pass
                except Exception:
                    pass
            gui_source1 = presenter.store.viewport.session_data.image_state.image1
            gui_source2 = presenter.store.viewport.session_data.image_state.image2
            document = presenter.store.get_session_state_slot("document")
            source_key = (
                document.image1_path,
                document.image2_path,
                image_uid(gui_source1),
                image_uid(gui_source2),
                gui_source1.size if gui_source1 is not None else None,
                gui_source2.size if gui_source2 is not None else None,
            )
            img_sig = (
                image_uid(render_img1),
                image_uid(render_img2),
                current_label_dims,
                presenter.store.viewport.view_state.diff_mode,
                presenter.store.viewport.view_state.channel_view_mode,
                source_key,
            )
            if img_sig != getattr(presenter, "_last_img_sig", None):
                _t1 = "full_res" if render_img1 is peeked["peeked_pixel1"] and render_img1 is not None else _source_tier(
                    render_img1, peeked["peeked_preview1"], None, presenter.store.viewport.session_data.image_state.image1,
                )
                _t2 = "full_res" if render_img2 is peeked["peeked_pixel2"] and render_img2 is not None else _source_tier(
                    render_img2, peeked["peeked_preview2"], None, presenter.store.viewport.session_data.image_state.image2,
                )
                _preview_log(
                    "update: apply_store_to_canvas - sig changed (uid1=%s uid2=%s tier1=%s tier2=%s label=%dx%d diff=%s channel=%s)",
                    image_uid(render_img1), image_uid(render_img2), _t1, _t2, current_label_dims[0], current_label_dims[1], presenter.store.viewport.view_state.diff_mode, presenter.store.viewport.view_state.channel_view_mode,
                )
                presenter._last_img_sig = img_sig
                if _gap_enabled():
                    try:
                        global _last_gap_apply_sig
                        _geom2 = getattr(presenter.store.viewport.geometry_state, "image_display_rect_on_label", None)
                        _apply_sig = (image_uid(render_img1), image_uid(render_img2), _geom2, _t1, _t2)
                        if _apply_sig != _last_gap_apply_sig:
                            _last_gap_apply_sig = _apply_sig
                            _gap_log(
                                "apply gap_correlation gap_id=%s/%s tier=%s/%s size=%s/%s geom=%s pixmap=%sx%s label=%dx%d unified=%s",
                                image_uid(render_img1), image_uid(render_img2), _t1, _t2, _size_or_none(render_img1), _size_or_none(render_img2), _geom2, getattr(presenter.store.viewport.geometry_state, "pixmap_width", None), getattr(presenter.store.viewport.geometry_state, "pixmap_height", None), current_label_dims[0], current_label_dims[1], getattr(presenter.store.viewport.session_data.render_cache, "unification_in_progress", False),
                            )
                    except Exception:
                        pass
                if render_img1 and render_img2:
                    _apply_store_to_canvas(
                        image_label, presenter.store, render_img1, render_img2, fit_content=False, source_image1=gui_source1, source_image2=gui_source2, source_key=source_key, display_cache_key=_display_cache_key(render_img1, render_img2), clip_overlays_to_image_bounds=False,
                    )
                    try:
                        _stored_actual = getattr(image_label.runtime_state, "_stored_pil_images", [None, None])
                        _gpu_t1 = "full_res" if _stored_actual[0] is peeked["peeked_pixel1"] and _stored_actual[0] is not None else _source_tier(_stored_actual[0], peeked["peeked_preview1"], None, presenter.store.viewport.session_data.image_state.image1)
                        _gpu_t2 = "full_res" if _stored_actual[1] is peeked["peeked_pixel2"] and _stored_actual[1] is not None else _source_tier(_stored_actual[1], peeked["peeked_preview2"], None, presenter.store.viewport.session_data.image_state.image2)
                        _preview_log("pick->GPU applied: picked tier1=%s tier2=%s GPU tier1=%s tier2=%s picked_uids=%s/%s stored_uids=%s/%s match=%s", _t1, _t2, _gpu_t1, _gpu_t2, image_uid(render_img1), image_uid(render_img2), image_uid(_stored_actual[0]) if _stored_actual[0] is not None else None, image_uid(_stored_actual[1]) if _stored_actual[1] is not None else None, _t1 == _gpu_t1 and _t2 == _gpu_t2)
                    except Exception:
                        pass
            else:
                _t1_skip = "full_res" if render_img1 is peeked["peeked_pixel1"] and render_img1 is not None else _source_tier(render_img1, peeked["peeked_preview1"], None, presenter.store.viewport.session_data.image_state.image1)
                _t2_skip = "full_res" if render_img2 is peeked["peeked_pixel2"] and render_img2 is not None else _source_tier(render_img2, peeked["peeked_preview2"], None, presenter.store.viewport.session_data.image_state.image2)
                _preview_log("update: skip apply - img_sig unchanged (uid1=%s uid2=%s picked_tier=%s/%s) scene-only repaint", image_uid(render_img1), image_uid(render_img2), _t1_skip, _t2_skip)
                runtime_state = getattr(image_label, "runtime_state", None)
                if runtime_state is not None:
                    runtime_state._store = presenter.store
                    image_label.set_render_scene(_build_render_scene(presenter.store, apply_channel_mode_in_shader=bool(getattr(runtime_state, "_apply_channel_mode_in_shader", True)), clip_overlays_to_image_bounds=False))
                    try:
                        _stored_skip = getattr(runtime_state, "_stored_pil_images", [None, None])
                        _gpu_skip_t1 = "full_res" if _stored_skip[0] is peeked["peeked_pixel1"] and _stored_skip[0] is not None else _source_tier(_stored_skip[0], peeked["peeked_preview1"], None, presenter.store.viewport.session_data.image_state.image1)
                        _gpu_skip_t2 = "full_res" if _stored_skip[1] is peeked["peeked_pixel2"] and _stored_skip[1] is not None else _source_tier(_stored_skip[1], peeked["peeked_preview2"], None, presenter.store.viewport.session_data.image_state.image2)
                        _preview_log("pick->GPU scene-only: picked tier=%s/%s GPU tier still %s/%s stored_uids=%s/%s scene_only=True", _t1_skip, _t2_skip, _gpu_skip_t1, _gpu_skip_t2, image_uid(_stored_skip[0]) if _stored_skip[0] is not None else None, image_uid(_stored_skip[1]) if _stored_skip[1] is not None else None)
                    except Exception:
                        pass
            presenter._last_mag_signature = None
            presenter._last_bg_signature = current_bg_sig
            presenter._last_label_dims = current_label_dims
            if presenter._cached_base_pixmap is None:
                presenter._cached_base_pixmap = QPixmap(1, 1)
        else:
            _preview_log("update: skip - not a canvas widget")
            return False
    else:
        _preview_log("update: skip apply - background signature unchanged")
    # --- 10. overlay / magnifier ---
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


def _query_overlay(store, capability_id: str, default=None):
    command = registry().get_feature_command_by_alias(capability_id)
    if command is None:
        return default
    result = command(store)
    return default if result is None else result
