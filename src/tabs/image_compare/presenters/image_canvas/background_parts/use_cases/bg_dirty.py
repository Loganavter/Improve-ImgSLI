"""Background dirty + diff ssim + pick/gap/apply.

Extracted from ``use_cases/render_gate.py`` per ``docs/dev/CODE_PATTERNS.md``
thin owner + ``use_cases/`` and ``docs/dev/FILE_SIZE_POLICY.md`` (500L).
Owns ``compute_background_signature`` / ``is_background_dirty``, the
``ssim`` diff request + ``sync_diff_texture`` call, and the
``bg_is_dirty`` → ``pick`` → ``gap`` → ``apply_store_to_canvas`` branch
(``render_flow.py:447-746``). Throttle globals for gap logs live here —
the module that owns the logging decision.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QPixmap

from shared.rendering.image_identity import image_uid
from tabs.image_compare.canvas.helpers import get_canvas_widget as _orig_get_canvas_widget
from tabs.image_compare.canvas.presentation.surface import apply_store_to_canvas as _orig_apply_store_to_canvas
from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.canvas.scene import build_render_scene as _orig_build_render_scene
from tabs.image_compare.debug import (
    ic_gap_debug as _gap_log,
    ic_gap_debug_enabled as _gap_enabled,
    ic_preview_debug as _preview_log,
    ic_preview_source_tier as _source_tier,
)
from tabs.image_compare.presenters.image_canvas.background_parts.diff import sync_diff_texture as _orig_sync_diff_texture  # noqa: F401

from .geometry import _size_or_none
from .preview import (
    _display_cache_key,
    _update_preview_tracking,
    pick_display_with_preview_backing,
)

_mlog = logging.getLogger("ImproveImgSLI.magnifier.render_flow")

_last_gap_pick_sig = None  # type: ignore
_last_gap_apply_sig = None  # type: ignore


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


def _apply_store_to_canvas(*a, **kw):
    return _resolve_rf("apply_store_to_canvas", _orig_apply_store_to_canvas)(*a, **kw)


def _build_render_scene(*a, **kw):
    return _resolve_rf("build_render_scene", _orig_build_render_scene)(*a, **kw)


def _sync_diff_texture(*a, **kw):
    return _resolve_rf("sync_diff_texture", _orig_sync_diff_texture)(*a, **kw)


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


def handle_background(presenter, source1, source2, peeked, current_label_dims, label_width, label_height) -> bool:
    """Bg signature + dirty + ssim diff + pick/gap/apply.

    Mirrors ``render_gate.py:423-608``. Returns True if the caller should
    early-return ``False`` (not a canvas widget), else False to continue to
    overlay/magnifier. Updates ``presenter._last_bg_signature``,
    ``_last_label_dims``, ``_last_mag_signature``, ``_last_img_sig`` and
    ``_cached_base_pixmap`` exactly as the original gate, preserving
    ``[ic-preview]`` and ``[ic-gap]`` throttled logs (throttle globals live
    here).
    """
    current_bg_sig = compute_background_signature(presenter, source1, source2)
    bg_is_dirty = is_background_dirty(presenter, current_bg_sig, current_label_dims)
    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    if presenter.view.is_canvas_widget() and diff_mode == "ssim":
        request_cached_diff = registry().get_feature_command_by_alias("overlay.request_cached_diff")
        if request_cached_diff is not None:
            request_cached_diff(presenter, source1, source2, diff_mode)
    if presenter.view.is_canvas_widget():
        _sync_diff_texture(presenter, diff_mode)

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
            # Joint preview hold: preview never deleted until BOTH halves have
            # complete tile replacement. While both previews exist and at least
            # one side's full-res store is not yet pyramid-complete OR still
            # inflight (pyvips streaming / unify), keep both sides on preview
            # instead of flipping one side early to a low-res intermediate
            # store (1024/1440) that would then be used as fallback baseline
            # for the final hires (5760) swap.
            try:
                _both_previews = peeked["peeked_preview1"] is not None and peeked["peeked_preview2"] is not None
                if _both_previews:
                    from shared.image_processing.pyramid_registry import pyramid_for
                    from shared.image_processing.tiled_pixel_store import TiledPixelStore as _TPS

                    def _pyramid_complete(img):
                        if img is None:
                            return False
                        if isinstance(img, _TPS):
                            p = pyramid_for(img)
                            return p is not None and p.is_complete()
                        return False

                    _s1 = presenter.store.viewport.session_data.image_state.image1
                    _s2 = presenter.store.viewport.session_data.image_state.image2
                    _both_stores_present = _s1 is not None and _s2 is not None
                    # Joint hold only matters for dual comparison (both sides have
                    # an image). Single-side / live-half case must stay per-slot
                    # or the flip-flop test's [preview, store] sequence breaks.
                    if not _both_stores_present:
                        _s1_ready = _s2_ready = True
                    else:
                        _s1_ready = _pyramid_complete(_s1)
                        _s2_ready = _pyramid_complete(_s2)
                    _pending = False
                    try:
                        _ctrl = getattr(presenter, "session_controller", None) or getattr(presenter, "controller", None)
                        _svc = getattr(_ctrl, "_image_load_service", None) if _ctrl is not None else None
                        if _svc is None and _ctrl is not None:
                            _svc = getattr(_ctrl, "pipeline", None)
                        if _svc is not None and hasattr(_svc, "is_loading"):
                            _cs = None
                            try:
                                if hasattr(_ctrl, "_get_crop_service"):
                                    _cs = _ctrl._get_crop_service()
                            except Exception:
                                _cs = None
                            _path1 = peeked.get("path1")
                            _path2 = peeked.get("path2")
                            if _path1 and _svc.is_loading(_path1, _cs):
                                _pending = True
                            if _path2 and _svc.is_loading(_path2, _cs):
                                _pending = True
                        # also check unify still in progress via render_cache flag
                        try:
                            if getattr(presenter.store.viewport.session_data.render_cache, "unification_in_progress", False):
                                _pending = True
                        except Exception:
                            pass
                    except Exception:
                        _pending = False
                    if not (_s1_ready and _s2_ready) or _pending:
                        # would we have flipped at least one side to store?
                        _t1_pick = "full_res" if img1 is peeked["peeked_pixel1"] and img1 is not None else _source_tier(img1, peeked["peeked_preview1"], None, _s1)
                        _t2_pick = "full_res" if img2 is peeked["peeked_pixel2"] and img2 is not None else _source_tier(img2, peeked["peeked_preview2"], None, _s2)
                        if _t1_pick != "preview" or _t2_pick != "preview":
                            _preview_log(
                                "joint preview hold: both previews available but stores not both pyramid-complete/pending s1_ready=%s s2_ready=%s pending=%s -> force preview/preview (was %s/%s)",
                                _s1_ready, _s2_ready, _pending, _t1_pick, _t2_pick,
                            )
                            img1 = peeked["peeked_preview1"]
                            img2 = peeked["peeked_preview2"]
            except Exception:
                pass
            # Unify size-mismatch gate: even when both pyramids are "complete"
            # (small store) and is_loading/unification_in_progress flag hasn't
            # yet propagated, a store/store pair with w1!=w2 && cache miss would
            # still be sent to the renderer as 5760 vs 1440 (108 vs 9 tiles,
            # half-transparent placeholder). Hold preview/preview until the
            # unified  max(w1,w2) pair is cached. Single-side / same-size
            # stays unaffected (need_unify False).
            try:
                _s1u = presenter.store.viewport.session_data.image_state.image1
                _s2u = presenter.store.viewport.session_data.image_state.image2
                if _s1u is not None and _s2u is not None:
                    from shared.image_processing.tiled_pixel_store import pixel_source_size as _pss

                    try:
                        _w1, _h1 = _pss(_s1u)
                    except Exception:
                        _w1, _h1 = int(getattr(_s1u, "width", 0) or 0), int(getattr(_s1u, "height", 0) or 0)
                    try:
                        _w2, _h2 = _pss(_s2u)
                    except Exception:
                        _w2, _h2 = int(getattr(_s2u, "width", 0) or 0), int(getattr(_s2u, "height", 0) or 0)
                    if (_w1 != _w2 or _h1 != _h2) and _w1 > 0 and _w2 > 0:
                        _preview_log("unify gate check: size mismatch %sx%s vs %sx%s", _w1, _h1, _w2, _h2)
                        _ps = None
                        try:
                            _ps = presenter.store.get_session_state_slot("pipeline")
                        except Exception:
                            _ps = None
                        _cache_u = None
                        _ctrl_u = None
                        if _ps is not None:
                            try:
                                from tabs.image_compare.pipeline.cache import _unify_key as _ukey_store
                                class _StoreCacheWrapper:
                                    def get_unified(self, u1, u2, m, w, h):
                                        k = _ukey_store(u1, u2, m, w, h)
                                        v = _ps.unify.get(k) if isinstance(_ps.unify, dict) else None
                                        if v is None:
                                            return None
                                        try:
                                            for s in v:
                                                if hasattr(s, "is_open") and not s.is_open:
                                                    return None
                                                if hasattr(s, "isNull") and s.isNull():
                                                    return None
                                        except Exception:
                                            pass
                                        return v
                                    @property
                                    def _preview(self):
                                        return getattr(_ps, "preview", {})
                                _cache_u = _StoreCacheWrapper()
                            except Exception:
                                _cache_u = None
                            _preview_log("unify gate: Store pipeline %s cache %s", _ps is not None, _cache_u is not None)
                        else:
                            _ctrl_u = getattr(presenter, "session_controller", None) or getattr(presenter, "controller", None)
                            if _ctrl_u is None:
                                try:
                                    _mw = getattr(presenter, "main_window_app", None) or getattr(getattr(presenter, "widget", None), "main_window_app", None)
                                    if _mw is not None:
                                        _tab = getattr(getattr(_mw, "tab_registry", None), "get_tab", lambda *_a, **_kw: None)("image_compare")
                                        _ctrl_u = getattr(_tab, "session_controller", None) if _tab else None
                                except Exception:
                                    _ctrl_u = None
                            _pl_u = getattr(_ctrl_u, "pipeline", None) if _ctrl_u is not None else None
                            if _pl_u is None:
                                try:
                                    _pl_u = getattr(presenter, "pipeline", None)
                                except Exception:
                                    _pl_u = None
                            _cache_u = getattr(_pl_u, "cache", None) if _pl_u is not None else None
                            _preview_log("unify gate: legacy pipeline %s cache %s ctrl=%s", _pl_u is not None, _cache_u is not None, type(_ctrl_u).__name__ if _ctrl_u else None)
                        if _cache_u is not None:
                            try:
                                from shared.rendering.image_identity import image_uid as _uid2
                                from shared.rendering.interpolation import get_effective_main_interpolation_method as _get_method

                                _method_u = _get_method(presenter.store.viewport)
                                _wh_u = (max(_w1, _w2), max(_h1, _h2))
                                _uid1 = _uid2(_s1u)
                                _uid2v = _uid2(_s2u)
                                _miss = _cache_u.get_unified(_uid1, _uid2v, _method_u, _wh_u[0], _wh_u[1]) is None
                                _preview_log("unify gate: get_unified %s/%s %s %s miss=%s", _uid1, _uid2v, _method_u, _wh_u, _miss)
                                if _miss:
                                    # Robust preview fetch: peek may be None due to key mismatch
                                    # (crop_service), scan cache directly as fallback.
                                    _pp1 = peeked["peeked_preview1"]
                                    _pp2 = peeked["peeked_preview2"]
                                    if _pp1 is None or _pp2 is None:
                                        try:
                                            import os as _os2

                                            _norm1 = _os2.path.normpath(peeked.get("path1") or "")
                                            _norm2 = _os2.path.normpath(peeked.get("path2") or "")
                                            for _k, _v in list(getattr(_cache_u, "_preview", {}).items()):
                                                try:
                                                    if _pp1 is None and _k[0] == _norm1 and _v is not None and not getattr(_v, "isNull", lambda: True)():
                                                        _pp1 = _v
                                                    if _pp2 is None and _k[0] == _norm2 and _v is not None and not getattr(_v, "isNull", lambda: True)():
                                                        _pp2 = _v
                                                except Exception:
                                                    continue
                                        except Exception:
                                            pass
                                    _both_have_preview = _pp1 is not None and _pp2 is not None
                                    _t1_u = "full_res" if img1 is peeked["peeked_pixel1"] and img1 is not None else _source_tier(img1, _pp1, None, _s1u)
                                    _t2_u = "full_res" if img2 is peeked["peeked_pixel2"] and img2 is not None else _source_tier(img2, _pp2, None, _s2u)
                                    if _t1_u != "preview" or _t2_u != "preview":
                                        if _both_have_preview:
                                            _preview_log(
                                                "joint preview hold: size mismatch %sx%s vs %sx%s need_unify miss %s/%s wh=%s -> force preview/preview (was %s/%s)",
                                                _w1, _h1, _w2, _h2, _uid1, _uid2v, _wh_u, _t1_u, _t2_u,
                                            )
                                            img1 = _pp1
                                            img2 = _pp2
                                        else:
                                            _preview_log(
                                                "joint preview hold: size mismatch %sx%s vs %sx%s need_unify miss %s/%s wh=%s -> preview missing (pp1=%s pp2=%s) cannot force, fallback will hold via atomic",
                                                _w1, _h1, _w2, _h2, _uid1, _uid2v, _wh_u, _pp1 is not None, _pp2 is not None,
                                            )
                            except Exception:
                                pass
            except Exception:
                pass
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
            return True
    else:
        _preview_log("update: skip apply - background signature unchanged")
    return False
