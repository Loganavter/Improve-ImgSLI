"""Comparison letterbox geometry — thin-owner use case for render_flow.

Extracted from ``background_parts/render_flow.py`` per
``docs/dev/CODE_PATTERNS.md`` thin owner + ``use_cases/`` and
``docs/dev/FILE_SIZE_POLICY.md`` (500L). The render gate owns the
decision to call this helper, but the geometry math and its
``[ic-gap]``/``[ic-preview]`` diagnostics live here as plain functions
taking the presenter as first argument.
"""

from PySide6.QtGui import QImage, QPixmap

from domain.types import Rect
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.image_identity import image_uid
from shared.rendering.unified_envelope import eager_envelope_rect
from tabs.image_compare.debug import (
    ic_gap_debug as _gap_log,
    ic_gap_debug_enabled as _gap_enabled,
    ic_preview_debug as _preview_log,
)


def _size_or_none(candidate):
    """``candidate.size``, or ``None`` if unavailable.

    ``image_state.image{1,2}`` is updated by a background unify worker on a
    different schedule than the previous pixel cache (see
    ``_session_controller._unify_images_worker_task`` / ``reducer.py``), so a
    reference here can outlive ``close_pixel_store()`` closing that same
    store from the load path. A closed ``TiledPixelStore`` is still truthy
    (no ``__bool__`` override) but ``.size`` reads ``self._memmap.shape`` on
    a ``None`` memmap and raises -- checked explicitly rather than relying on
    the property to fail safely, since other call sites depend on that
    property staying a bare attribute-style accessor.
    """
    if candidate is None:
        return None
    if isinstance(candidate, TiledPixelStore) and not candidate.is_open:
        return None
    if isinstance(candidate, (QImage, QPixmap)):
        qsize = candidate.size()
        return (qsize.width(), qsize.height())
    try:
        return candidate.size
    except AttributeError:
        # Size-less stand-ins (test doubles, exotic sources) mean "no size
        # known" -- geometry callers then keep the previous rect.
        return None


_last_gap_geometry_sig = None  # type: ignore
_last_gap_geometry_input_sig = None  # type: ignore


def update_comparison_geometry(presenter, source1, source2, label_w, label_h) -> None:
    """Letterbox the comparison to the best sizes available right now.

    Sizes prefer the unified stores (``image_state.image{1,2}``), then the
    full-res/preview/original document sources. Called as early as any side
    has content -- before the gate's unification deferral / one-side returns
    -- so the canvas layout converges to the new comparison while the
    preview is showing, not only when the unified store's tiles land.
    Previews preserve the source aspect, so the pair-fit rect here equals
    the rect the store flip will compute; the flip then changes nothing
    visually. No-op (keeps the previous rect) while neither side has a
    size. ``image_display_rect_on_label`` is only assigned when the rect
    actually changes -- steady-state passes leave it untouched.
    """
    src_resize1 = presenter.store.viewport.session_data.image_state.image1
    src_resize2 = presenter.store.viewport.session_data.image_state.image2
    size1 = _size_or_none(src_resize1) or _size_or_none(source1)
    size2 = _size_or_none(src_resize2) or _size_or_none(source2)
    # W3a: envelope fits the box-clipped content. Boxes resolve through the
    # single-owner interface (session crop service; ``resolve_box_for_path``
    # never blocks the GUI thread on an unwarmed service) and scale to the
    # sizes in hand (unify-resampled stores included). None per slot keeps
    # today's sizes identically. The dispatcher path below still returns
    # early (Bucket A: base_images.update_common_letterbox_geometry owns the
    # Store geometry via transact); this only affects the sizes fed to the
    # envelope helper and the no-dispatcher fallback assignment.
    try:
        from tabs.image_compare.canvas.texture_parts.crop_clip import (
            box_dims as _box_dims,
            resolve_box_for_path as _resolve_box,
            scaled_box_for_source as _scaled_box,
        )

        _doc = None
        try:
            _doc = presenter.store.get_session_state_slot("document")
        except Exception:
            _doc = None
        _p1 = getattr(_doc, "image1_path", None) if _doc is not None else None
        _p2 = getattr(_doc, "image2_path", None) if _doc is not None else None
        _ctrl = getattr(presenter, "session_controller", None) or getattr(
            presenter, "controller", None
        )
        try:
            _svc = _ctrl._get_crop_service() if _ctrl is not None else None
        except Exception:
            _svc = None
        _b1 = _scaled_box(_resolve_box(_p1, _svc), path=_p1, live_size=size1)
        _b2 = _scaled_box(_resolve_box(_p2, _svc), path=_p2, live_size=size2)
        if _b1 is not None and size1 is not None:
            size1 = _box_dims(_b1, size1)
        if _b2 is not None and size2 is not None:
            size2 = _box_dims(_b2, size2)
    except Exception:
        pass
    # Eager max envelope via shared host helper — single
    # resolve_canvas_content_geometry(cw,ch,pw,ph) for both sides, no hold.
    has1 = bool(size1 and size1[0] > 0 and size1[1] > 0)
    has2 = bool(size2 and size2[0] > 0 and size2[1] > 0)
    if not has1 and not has2:
        return
    # Build sizes list for helper; zero where missing (per-image fallback).
    sizes_for_helper: list[tuple[int, int]] = [
        (int(size1[0]), int(size1[1])) if has1 else (0, 0),
        (int(size2[0]), int(size2[1])) if has2 else (0, 0),
    ]
    _lb, _rect = eager_envelope_rect(label_w, label_h, sizes_for_helper)
    scaled_w, scaled_h = int(_rect[2]), int(_rect[3])
    # Recover scale for gap log (derived from envelope vs per-image)
    if has1 and has2:
        pw, ph = max(size1[0], size2[0]), max(size1[1], size2[1])
        # log-friendly envelope sizes
        size1 = (pw, ph)
        size2 = (pw, ph)
        scale = min(label_w / pw, label_h / ph) if pw and ph else 1.0
    elif has1:
        scale = min(label_w / size1[0], label_h / size1[1]) if size1[0] and size1[1] else 1.0
    else:
        scale = min(label_w / size2[0], label_h / size2[1]) if size2[0] and size2[1] else 1.0

    geometry = presenter.store.viewport.geometry_state
    # [ic-gap] input snapshot before guard — throttled: same (state, src, label, unified, size) at 60Hz
    if _gap_enabled():
        try:
            _unified = bool(src_resize1 is not None or src_resize2 is not None)
            _gap_input_sig = (
                image_uid(src_resize1) if src_resize1 is not None else None,
                image_uid(src_resize2) if src_resize2 is not None else None,
                image_uid(source1) if source1 is not None else None,
                image_uid(source2) if source2 is not None else None,
                label_w,
                label_h,
                _unified,
                size1,
                size2,
            )
            global _last_gap_geometry_input_sig
            if _gap_input_sig != _last_gap_geometry_input_sig:
                _gap_log(
                    "geometry input state1=%s state2=%s src1=%s src2=%s label=%dx%d unified=%s size1=%s size2=%s",
                    image_uid(src_resize1) if src_resize1 is not None else None,
                    image_uid(src_resize2) if src_resize2 is not None else None,
                    image_uid(source1) if source1 is not None else None,
                    image_uid(source2) if source2 is not None else None,
                    label_w,
                    label_h,
                    _unified,
                    size1,
                    size2,
                )
        except Exception:
            pass
    img_x, img_y = int(_rect[0]), int(_rect[1])
    new_rect = Rect(img_x, img_y, scaled_w, scaled_h)
    # Guard: throttle 60Hz fps tick — dispatch only when rect actually changes.
    # Single owner via dispatch (was direct assignment) so Store remains source
    # of truth and sync_geometry_state (canvas -> Store) can converge without
    # fighting a second owner. Guard prevents re-arming the fps timer via Store emit.
    try:
        if (
            getattr(geometry, "pixmap_width", None) == scaled_w
            and getattr(geometry, "pixmap_height", None) == scaled_h
            and getattr(geometry, "image_display_rect_on_label", None) == new_rect
        ):
            return
    except Exception:
        pass
    # [ic-gap] rect transition with throttling
    if _gap_enabled():
        try:
            global _last_gap_geometry_sig
            _prev_rect = getattr(geometry, "image_display_rect_on_label", None)
            _prev_w = getattr(geometry, "pixmap_width", None)
            _prev_h = getattr(geometry, "pixmap_height", None)
            _sig = (scaled_w, scaled_h, new_rect, bool(src_resize1 or src_resize2))
            if _sig != _last_gap_geometry_sig:
                _last_gap_geometry_sig = _sig
                _gap_log(
                    "geometry rect before=%s %sx%s after=%s %dx%d label=%dx%d scale=%.5f unified=%s src1=%s src2=%s",
                    _prev_rect,
                    _prev_w,
                    _prev_h,
                    new_rect,
                    scaled_w,
                    scaled_h,
                    label_w,
                    label_h,
                    scale if 'scale' in locals() else 0.0,
                    bool(src_resize1 is not None or src_resize2 is not None),
                    _size_or_none(src_resize1) or _size_or_none(source1),
                    _size_or_none(src_resize2) or _size_or_none(source2),
                )
        except Exception:
            pass
    # Bucket A: single geometry owner is base_images.update_common_letterbox_geometry
    # via store.transact. Hold previous Store rect here (no dispatch) — waits
    # ~400ms for unify when mixed tier (store vs preview). Keep guard 136;
    # for test fakes without dispatcher retain direct assignment so preview-phase
    # geometry tests stay green.
    try:
        dispatcher = getattr(presenter.store, "get_dispatcher", lambda: None)()
        if dispatcher is not None:
            return
    except Exception:
        pass
    # Fallback for test fakes without dispatcher
    geometry.pixmap_width = scaled_w
    geometry.pixmap_height = scaled_h
    if getattr(geometry, "image_display_rect_on_label", None) != new_rect:
        geometry.image_display_rect_on_label = new_rect
        _preview_log(
            "geometry: comparison rect updated to %dx%d (sizes from %s)",
            scaled_w,
            scaled_h,
            "unified stores"
            if (src_resize1 is not None or src_resize2 is not None)
            else "sources/previews",
        )
