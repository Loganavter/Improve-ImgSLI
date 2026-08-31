# Audit-Meta: pattern=state-machine size=exempt reason="IC render gate: schedule/update gate + preview-tier display pick; [ic-preview] diagnostics instrument the gate's own decisions (existing Tracer records live here too)"
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


def _size_or_none(candidate):
    """``candidate.size``, or ``None`` if unavailable.

    ``image_state.image{1,2}`` is updated by a background unify worker on a
    different schedule than ``document.full_res_image{1,2}`` (see
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


def _update_comparison_geometry(
    presenter, source1, source2, label_width: int, label_height: int
) -> None:
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

    def _fit_scale(w: int, h: int) -> float:
        return min(label_width / w, label_height / h)

    if size1 and size2:
        img1_w, img1_h = size1
        img2_w, img2_h = size2
        scale = min(_fit_scale(img1_w, img1_h), _fit_scale(img2_w, img2_h))
        scaled_w = max(1, int(img1_w * scale))
        scaled_h = max(1, int(img1_h * scale))
    elif size1:
        img1_w, img1_h = size1
        scale = _fit_scale(img1_w, img1_h)
        scaled_w = max(1, int(img1_w * scale))
        scaled_h = max(1, int(img1_h * scale))
    elif size2:
        img2_w, img2_h = size2
        scale = _fit_scale(img2_w, img2_h)
        scaled_w = max(1, int(img2_w * scale))
        scaled_h = max(1, int(img2_h * scale))
    else:
        return

    geometry = presenter.store.viewport.geometry_state
    # [ic-gap] input snapshot before guard
    if _gap_enabled():
        try:
            _unified = bool(src_resize1 is not None or src_resize2 is not None)
            _gap_log(
                "geometry input state1=%s state2=%s src1=%s src2=%s label=%dx%d unified=%s size1=%s size2=%s",
                image_uid(src_resize1) if src_resize1 is not None else None,
                image_uid(src_resize2) if src_resize2 is not None else None,
                image_uid(source1) if source1 is not None else None,
                image_uid(source2) if source2 is not None else None,
                label_width,
                label_height,
                _unified,
                size1,
                size2,
            )
        except Exception:
            pass
    img_x, img_y = (label_width - scaled_w) // 2, (label_height - scaled_h) // 2
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
                    label_width,
                    label_height,
                    scale if 'scale' in locals() else 0.0,
                    bool(src_resize1 is not None or src_resize2 is not None),
                    _size_or_none(src_resize1) or _size_or_none(source1),
                    _size_or_none(src_resize2) or _size_or_none(source2),
                )
        except Exception:
            pass
    # Unified dispatch owner: was direct assignment (Store bypass) — now dispatch
    # so viewport geometry stays Redux-consistent and emitters are coalesced.
    try:
        dispatcher = getattr(presenter.store, "get_dispatcher", lambda: None)()
        if dispatcher is not None:
            from core.state_management.geometry_actions import (
                SetImageDisplayRectAction,
                SetPixmapDimensionsAction,
            )

            batch = getattr(presenter.store, "batch_changes", None)
            if callable(batch):
                with presenter.store.batch_changes():
                    dispatcher.dispatch(
                        SetPixmapDimensionsAction(width=scaled_w, height=scaled_h),
                        scope="viewport",
                    )
                    dispatcher.dispatch(
                        SetImageDisplayRectAction(rect=new_rect),
                        scope="viewport",
                    )
            else:
                dispatcher.dispatch(
                    SetPixmapDimensionsAction(width=scaled_w, height=scaled_h),
                    scope="viewport",
                )
                dispatcher.dispatch(
                    SetImageDisplayRectAction(rect=new_rect),
                    scope="viewport",
                )
            _preview_log(
                "geometry: comparison rect updated to %dx%d (sizes from %s)",
                scaled_w,
                scaled_h,
                "unified stores"
                if (src_resize1 is not None or src_resize2 is not None)
                else "sources/previews",
            )
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


def pick_display_with_preview_backing(
    *candidates, last_applied_uid=None, superseded_preview_uid=None
):
    """Display-pair picker for the live canvas (stored role).

    ``pick_display_image`` only returns a ``TiledPixelStore`` once its
    pyramid is complete, so the first-load path naturally shows the 1024px
    preview as the backing until the pyramid catches up. On-the-fly content
    changes (swap, next image, auto-crop resizing the store, a fresh
    preview arriving while the previous unified store is still installed)
    can bypass that: the store's pyramid is already complete, so the canvas
    flips straight to store tiles whose fallback-LOD baseline is the
    *previous* content -- the new preview never appears underneath.

    Rule: while the slot's preview is *fresh*, prefer the preview for the
    stored role regardless of pyramid state. The next apply cycle (unify
    result / pyramid-completion invalidation) then finds the preview no
    longer fresh, picks the store as usual, and the flip's fallback
    baseline is exactly the new preview tiles -- the backing survives every
    on-the-fly change instead of only the first load.

    Freshness is *not* "uid differs from the display pair last applied":
    ``image_uid`` is a per-object identity, so a preview and the store
    built from the same image always differ, and that test alone would
    re-degrade an already-sharp store back to the 1024px preview on every
    apply cycle (flip-flop). The caller therefore also passes
    ``superseded_preview_uid`` -- the uid of the preview that the
    currently-installed store superseded. A preview matching either the
    last-applied display or that superseded preview is the same image's
    and must never preempt its store; only a preview belonging to a
    different image (or a reload) counts as fresh.
    """
    preview = candidates[1] if len(candidates) > 1 else None
    if preview is not None:
        uid = image_uid(preview)
        if uid != last_applied_uid and uid != superseded_preview_uid:
            return preview
    return pick_display_image(*candidates)


def _display_cache_key(image1, image2):
    """Stored-role ids for the *effective* display pair.

    Must mirror ``live_presentation.display_cache_key``'s shape
    (``(uid1, uid2, size1, size2)``): ``upload_pil_images`` persists it as
    ``_stored_image_ids`` and ``_textures_are_current`` compares the next
    plan's key against it, so a preview-backed apply has to record the
    preview ids -- otherwise the pyramid-complete pick would compute store
    ids and the flip would be skipped by the scene-only path.
    """
    return (
        image_uid(image1),
        image_uid(image2),
        image1.size if image1 is not None else None,
        image2.size if image2 is not None else None,
    )


def _update_preview_tracking(presenter, picked_by_slot: dict) -> None:
    """Remember which preview uid was last shown per slot and which preview
    a store superseded -- using ``image_uid`` equality, not ``is``.

    Must be called on *any* successful pick (dual, scene-only, single-side)
    so the ``pick_display_with_preview_backing`` freshness check
    (last_applied/superseded) can gate the next store pick correctly.
    A recreated ``QImage`` from the same file has a different ``id``/``is``
    but the same ``image_uid`` -- ``is`` comparison misses it and the flip-
    flop guard never arms.
    """
    try:
        doc = presenter.store.get_session_state_slot("document")
    except Exception:
        doc = None
    try:
        img_state = presenter.store.viewport.session_data.image_state
    except Exception:
        img_state = None
    last_display = dict(getattr(presenter, "_last_display_uids", None) or {})
    applied = dict(getattr(presenter, "_last_applied_preview_uid", None) or {})
    superseded = dict(getattr(presenter, "_last_superseded_preview_uid", None) or {})
    for slot, picked in (picked_by_slot or {}).items():
        if picked is None:
            continue
        try:
            uid = image_uid(picked)
        except Exception:
            continue
        if uid is None or uid == 0:
            continue
        last_display[slot] = uid
        preview = None
        store_img = None
        try:
            if doc is not None:
                preview = getattr(doc, f"preview_image{slot}", None)
        except Exception:
            preview = None
        try:
            if img_state is not None:
                store_img = getattr(img_state, f"image{slot}", None)
        except Exception:
            store_img = None
        preview_uid = None
        store_uid = None
        try:
            preview_uid = image_uid(preview) if preview is not None else None
        except Exception:
            preview_uid = None
        try:
            store_uid = image_uid(store_img) if store_img is not None else None
        except Exception:
            store_uid = None
        # uid equality, not ``is`` -- a recreated QImage has a new identity
        # but the same stable uid.
        if preview_uid is not None and preview_uid != 0 and uid == preview_uid:
            applied[slot] = uid
        elif store_uid is not None and store_uid != 0 and uid == store_uid:
            prev_applied = applied.get(slot)
            if prev_applied is not None:
                superseded[slot] = prev_applied
    presenter._last_display_uids = last_display
    presenter._last_applied_preview_uid = applied
    presenter._last_superseded_preview_uid = superseded


def _query_overlay(store, capability_id: str, default=None):
    command = registry().get_feature_command_by_alias(capability_id)
    if command is None:
        return default
    result = command(store)
    return default if result is None else result


def _is_background_tab(presenter) -> bool:
    """True when the IC page that owns *presenter* is not the current stack page.

    Mirrors ``tabs/use_cases/appearance.py``'s ``stack.currentWidget() is not page``
    check so hidden tabs are detected via the registry/stack contract, not via
    an implied ``isVisible`` lookup (see ``docs/dev/tabs/isolation.md``).
    Falls back to ``widget.isVisible()`` when the stack is not yet available
    (early startup / tests).
    """
    widget = getattr(presenter, "widget", None)
    if widget is None:
        return False
    try:
        window = getattr(presenter, "main_window_app", None)
        ui = getattr(window, "ui", None) if window is not None else None
        if ui is None:
            pp = getattr(window, "presenter", None) if window is not None else None
            ui = getattr(pp, "ui", None) if pp is not None else None
        stack = getattr(ui, "workspace_stack", None) if ui is not None else None
        if stack is not None:
            current = stack.currentWidget()
            if current is widget:
                return False
            # page may be ancestor of widget (wrapper pattern not used for IC,
            # but keep symmetric with MC)
            if current is not None and hasattr(current, "isAncestorOf"):
                try:
                    if current.isAncestorOf(widget):
                        return False
                except Exception:
                    pass
            return True
        # fallback: hidden stack pages are not visible
        return not bool(widget.isVisible())
    except Exception:
        try:
            return not bool(widget.isVisible())
        except Exception:
            return False


def _mark_render_stale(presenter) -> None:
    widget = getattr(presenter, "widget", None)
    if widget is not None:
        widget._render_stale = True  # type: ignore[attr-defined]
    try:
        from core.tracing.tracer import Tracer

        if Tracer.enabled():
            Tracer.instance().record(
                "render.ic.deferred",
                "IC render deferred - background tab",
                {"stale": True},
            )
    except Exception:
        pass


def is_render_stale(presenter) -> bool:
    widget = getattr(presenter, "widget", None)
    return bool(getattr(widget, "_render_stale", False)) if widget is not None else False


def flush_stale_render(presenter) -> bool:
    """Flush a deferred IC render if the page is now visible (stale-flush)."""
    widget = getattr(presenter, "widget", None)
    if widget is None or not getattr(widget, "_render_stale", False):
        return False
    if _is_background_tab(presenter):
        return False
    widget._render_stale = False  # type: ignore[attr-defined]
    try:
        from core.tracing.tracer import Tracer

        if Tracer.enabled():
            Tracer.instance().record(
                "render.ic.flush",
                "IC stale render flushed on show",
                {},
            )
    except Exception:
        pass
    try:
        return bool(presenter.update_comparison_if_needed())
    except Exception:
        try:
            presenter.schedule_update()
            return True
        except Exception:
            return False


def schedule_update(presenter):
    if (
        hasattr(presenter.main_window_app, "_closing")
        and presenter.main_window_app._closing
    ):
        _preview_log("schedule_update: ignored - app closing")
        return

    if _is_background_tab(presenter):
        _preview_log("schedule_update: hidden tab - render marked stale")
        _mark_render_stale(presenter)
        return

    is_interactive = presenter.store.viewport.interaction_state.is_interactive_mode

    if is_interactive:
        presenter._pending_interactive_mode = True

    if is_interactive:
        _preview_log("schedule_update: interactive mode - immediate update")
        presenter._update_scheduler_timer.stop()
        result = presenter.update_comparison_if_needed()
        if result:
            presenter._pending_interactive_mode = None
    else:
        if not presenter._update_scheduler_timer.isActive():
            _preview_log("schedule_update: non-interactive - fps timer armed")
            presenter._update_scheduler_timer.start()


_last_document_log_sig = None  # type: ignore
_last_one_side_log_sig = None  # type: ignore
_last_gap_geometry_sig = None  # type: ignore
_last_gap_pick_sig = None  # type: ignore
_last_gap_apply_sig = None  # type: ignore

def update_comparison_if_needed(presenter):
    if _is_background_tab(presenter):
        _preview_log("update: deferred - background tab (render marked stale)")
        _mark_render_stale(presenter)
        return False

    if (
        not getattr(presenter.main_window_app, "_is_ui_stable", False)
        or presenter.store.viewport.interaction_state.resize_in_progress
    ):
        _preview_log("update: deferred - ui not stable / resize in progress")
        return False

    if (
        not presenter.main_window_app.isVisible()
        or presenter.main_window_app.isMinimized()
    ):
        _preview_log("update: deferred - window hidden or minimized")
        return False

    label_width, label_height = presenter.get_current_label_dimensions()
    if label_width <= 2 or label_height <= 2:
        _preview_log(
            "update: deferred - label too small (%dx%d)", label_width, label_height
        )
        return False

    _document = presenter.store.get_session_state_slot("document")
    if _document is None:
        _preview_log("update: deferred - no document slot")
        return False
    # Throttle document state log: only when sig changes to avoid 40Hz spam
    # when one side is missing and fps timer re-arms every frame.
    global _last_document_log_sig
    _doc_sig = (
        image_uid(_document.full_res_image1) if _document.full_res_image1 is not None else None,
        image_uid(_document.full_res_image2) if _document.full_res_image2 is not None else None,
        image_uid(_document.preview_image1) if _document.preview_image1 is not None else None,
        image_uid(_document.preview_image2) if _document.preview_image2 is not None else None,
        image_uid(_document.original_image1) if _document.original_image1 is not None else None,
        image_uid(_document.original_image2) if _document.original_image2 is not None else None,
        image_uid(presenter.store.viewport.session_data.image_state.image1) if presenter.store.viewport.session_data.image_state.image1 is not None else None,
        image_uid(presenter.store.viewport.session_data.image_state.image2) if presenter.store.viewport.session_data.image_state.image2 is not None else None,
        getattr(_document, "image1_path", None),
        getattr(_document, "image2_path", None),
    )
    if _doc_sig != _last_document_log_sig:
        _last_document_log_sig = _doc_sig
        _preview_log(
            "document state: full_res uid1=%s uid2=%s preview uid1=%s uid2=%s original uid1=%s uid2=%s image_state uid1=%s uid2=%s paths=%s/%s",
            _doc_sig[0], _doc_sig[1], _doc_sig[2], _doc_sig[3], _doc_sig[4], _doc_sig[5], _doc_sig[6], _doc_sig[7], _doc_sig[8], _doc_sig[9],
        )
    # Phase 3 SlotSource: document no longer holds pixels — pipeline cache / image_state is source.
    # Fallback chain: legacy document fields (for compat) → PipelineView → pipeline peek (preview)
    _img_state = presenter.store.viewport.session_data.image_state
    _pl = None
    try:
        # Try to get pipeline via presenter->tab controller if available; else via global session cache
        _ctrl = getattr(presenter, "session_controller", None) or getattr(presenter, "controller", None)
        if _ctrl is None:
            try:
                from tabs.image_compare.pipeline.cache import PipelineCache as _PC

                # fallback: try presenter.main_window_app tab registry
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
                    return c
            except Exception:
                pass
        return None
    source1 = (
        _document.full_res_image1
        or _document.preview_image1
        or _document.original_image1
        or getattr(_img_state, "image1", None)
        or _peek(getattr(_document, "image1_path", None))
    )
    source2 = (
        _document.full_res_image2
        or _document.preview_image2
        or _document.original_image2
        or getattr(_img_state, "image2", None)
        or _peek(getattr(_document, "image2_path", None))
    )

    # Comparison letterbox geometry must track the preview arrival, not the
    # unified-store flip. The early returns below (unification deferral,
    # single-image mode, one-side missing) used to skip the geometry block,
    # leaving the canvas letterboxed at the *previous* comparison's rect
    # until the unified tiles landed -- a visible resize arriving "with the
    # tiles" instead of "with the preview". Computing the rect from the best
    # available sizes (unified stores > full-res > previews) as soon as any
    # side has content converges it to the final layout during the preview
    # phase: previews preserve the source aspect, so the pair-fit rect is
    # already the flip's rect and the store flip no longer resizes anything.
    _update_comparison_geometry(
        presenter, source1, source2, label_width, label_height
    )

    if getattr(
        presenter.store.viewport.session_data.render_cache,
        "unification_in_progress",
        False,
    ):
        if presenter.store.viewport.session_data.image_state.image1 is None:
            # During unification the unified stores are not yet ready, but the
            # document already holds the raw loads (full_res/preview). The
            # previous "always defer" kept the canvas on the stale duplicate
            # (left on both halves, 20:59 16-entry [1,1] promotion) for ~1s
            # until the unified pair arrived. If both document sides are
            # present we can already show the preview/full_res pair — the
            # geometry already converged via _update_comparison_geometry.
            if source1 is None or source2 is None:
                _preview_log(
                    "update: deferred - unification in progress, image1 not ready"
                )
                return False
            _preview_log(
                "update: unification in progress but both document sources ready - proceeding with preview/full_res (image_state not yet ready)"
            )

    if presenter.store.viewport.view_state.showing_single_image_mode != 0:
        _preview_log(
            "update: single-image mode %s - display_single_image_on_label",
            presenter.store.viewport.view_state.showing_single_image_mode,
        )
        image_to_show = (
            pick_display_image(
                presenter.store.viewport.session_data.image_state.image1,
                source1,
                _document.preview_image1,
                _document.original_image1,
            )
            if presenter.store.viewport.view_state.showing_single_image_mode == 1
            else pick_display_image(
                presenter.store.viewport.session_data.image_state.image2,
                source2,
                _document.preview_image2,
                _document.original_image2,
            )
        )
        presenter.view.display_single_image_on_label(image_to_show)
        try:
            slot = int(presenter.store.viewport.view_state.showing_single_image_mode)
            if image_to_show is not None:
                _update_preview_tracking(presenter, {slot: image_to_show})
        except Exception:
            pass
        return False

    have1 = bool(
        presenter.store.viewport.session_data.image_state.image1 or source1
    )
    have2 = bool(
        presenter.store.viewport.session_data.image_state.image2 or source2
    )
    if not have1 and not have2:
        _preview_log("update: no sources on either side - label cleared")
        presenter.widget.image_label.clear()
        presenter.current_displayed_pixmap = None
        return False
    if not have1 or not have2:
        # One side is mid-reload / empty.
        # For a brand-new comparison (other list empty) we wait for the
        # second side instead of painting the live half duplicated across
        # both halves (left-on-both via display_single_image_on_label →
        # stored_0/stored_1 is_same=True). That duplicate is what the
        # 02:05:58.415 log showed (uid [2,2] on both halves). Waiting makes
        # the first load "1 загрузка, он покорно ждет sample2" and the
        # pair appears simultaneously once both sides are ready.
        # If the other list already has content (user browsing / reload),
        # keep the old live-half behaviour.
        global _last_one_side_log_sig
        try:
            other_list_empty = (
                len(_document.image_list2) == 0 if have1 else len(_document.image_list1) == 0
            )
        except AttributeError:
            other_list_empty = False
        # Path exists but pixels not yet ready → second side is on its way
        # (02:37:44.236 paths=sample1/sample2 but source2 still None). Wait
        # instead of painting left-on-both.
        other_has_path = (
            (_document.image2_path is not None) if have1 else (_document.image1_path is not None)
        )
        # Also wait if the other slot has a decode pending (coalesced by
        # _pending_image_loads) — visible via controller pending set.
        try:
            _pending = getattr(presenter.store, "_pending_image_loads", None)  # type: ignore[attr-defined]
            # controller pending lives on the tab controller, not store; check
            # presenter side via controller if available
            _ctrl = getattr(presenter, "controller", None) or getattr(presenter, "_controller", None)
            # presenter.widget may hold controller ref in some builds
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
                    have1,
                    have2,
                    other_list_empty,
                    other_has_path,
                    has_pending_other,
                )
            return False
        # Throttle: same have1/have2 + same image uids would spam at 60Hz via fps timer.
        _one_side_sig = (have1, have2, image_uid(source1) if source1 else None, image_uid(source2) if source2 else None)
        if _one_side_sig != _last_one_side_log_sig:
            _last_one_side_log_sig = _one_side_sig
            _preview_log(
                "update: one side missing (have1=%s have2=%s) - display live half",
                have1,
                have2,
            )
        image_to_show = (
            pick_display_image(
                presenter.store.viewport.session_data.image_state.image1,
                source1,
                _document.preview_image1,
                _document.original_image1,
            )
            if have1
            else pick_display_image(
                presenter.store.viewport.session_data.image_state.image2,
                source2,
                _document.preview_image2,
                _document.original_image2,
            )
        )
        presenter.view.display_single_image_on_label(image_to_show)
        try:
            slot = 1 if have1 else 2
            if image_to_show is not None:
                _update_preview_tracking(presenter, {slot: image_to_show})
        except Exception:
            pass
        return False

    current_bg_sig = presenter.background.get_background_signature(source1, source2)
    # Background signature must also be dirty when the unified store appears:
    # ``get_background_signature`` is keyed only on ``document.full_res/preview``
    # (``source1/2``), so ``image_state`` 4/5 arriving never dirtied ``bg_is_dirty``
    # and the ``pick`` branch 682:886 was skipped -- the fresh preview before unify
    # was lost and the 1024px backing never showed.
    try:
        _is1 = presenter.store.viewport.session_data.image_state.image1
        _is2 = presenter.store.viewport.session_data.image_state.image2
    except Exception:
        _is1 = _is2 = None
    current_bg_sig = (
        current_bg_sig,
        image_uid(_is1) if _is1 is not None else None,
        image_uid(_is2) if _is2 is not None else None,
    )
    last_bg_sig = getattr(presenter, "_last_bg_signature", None)
    current_label_dims = (label_width, label_height)
    label_dims_changed = presenter._last_label_dims != current_label_dims

    bg_is_dirty = (
        (current_bg_sig != last_bg_sig)
        or label_dims_changed
        or (presenter._cached_base_pixmap is None)
    )

    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    if presenter.view.is_canvas_widget() and diff_mode == "ssim":
        # Called every frame diff_mode=="ssim", not just when
        # cached_diff_image is None -- request_cached_diff_image_async's own
        # cached_diff_source_key comparison is what actually decides whether
        # a recompute is needed, so the *previous* pair's diff stays cached
        # and visible across an image swap instead of being cleared upfront
        # and leaving a diff-vanishes/plain-image/diff-reappears flash while
        # the new one computes (docs/dev/KNOWN_BUGS.md same-slot-swap SSIM
        # follow-up).
        request_cached_diff = registry().get_feature_command_by_alias(
            "overlay.request_cached_diff",
        )
        if request_cached_diff is not None:
            request_cached_diff(
                presenter,
                source1,
                source2,
                diff_mode,
            )

    if presenter.view.is_canvas_widget():
        sync_diff_texture(presenter, diff_mode)

    if bg_is_dirty:
        if presenter.view.is_canvas_widget():
            image_label = get_canvas_widget(presenter.widget)
            _last_display_uids = getattr(presenter, "_last_display_uids", None) or {}
            _superseded_uids = (
                getattr(presenter, "_last_superseded_preview_uid", None) or {}
            )
            img1 = pick_display_with_preview_backing(
                presenter.store.viewport.session_data.image_state.image1,
                _document.preview_image1,
                _document.full_res_image1,
                _document.original_image1,
                last_applied_uid=_last_display_uids.get(1),
                superseded_preview_uid=_superseded_uids.get(1),
            )
            img2 = pick_display_with_preview_backing(
                presenter.store.viewport.session_data.image_state.image2,
                _document.preview_image2,
                _document.full_res_image2,
                _document.original_image2,
                last_applied_uid=_last_display_uids.get(2),
                superseded_preview_uid=_superseded_uids.get(2),
            )
            # Correlate picker decision with the fallback-LOD debug in renderer
            # (same [ic-preview] stream): why "store shown but placeholder
            # missing" — was the preview even considered fresh?
            for _slot_num, _picked, _cand_preview in (
                (1, img1, _document.preview_image1),
                (2, img2, _document.preview_image2),
            ):
                _cand_full = _document.full_res_image1 if _slot_num == 1 else _document.full_res_image2
                _tier = "full_res" if _picked is _cand_full and _picked is not None else _source_tier(
                    _picked,
                    _document.preview_image1 if _slot_num == 1 else _document.preview_image2,
                    _document.original_image1 if _slot_num == 1 else _document.original_image2,
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
            # Always remember what was picked (uid equality, not ``is``) even
            # when the GPU apply is skipped (scene-only) -- otherwise the
            # single-side preview never arms ``last_applied`` and the
            # ``superseded`` guard after unify never fires.
            try:
                _update_preview_tracking(
                    presenter, {1: render_img1, 2: render_img2}
                )
            except Exception:
                pass
            # Phase 5: single geometry pass — second batch_changes per frame removed.
            # The early _update_comparison_geometry(source1, source2) already
            # letterboxes from the best available sizes (unified → full_res →
            # preview) preserving aspect, so the rect converges during the preview
            # phase without a second picked-size pass. A transient mixed-tier
            # (store vs preview) now waits ~400ms for unify before the rect
            # re-converges — cheaper than 2 batch_changes per frame (60Hz).

            # [ic-gap] mixed-tier risk during unification: store vs preview on same frame -> letterbox mismatch
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
                        _t1_gap = "full_res" if render_img1 is _document.full_res_image1 and render_img1 is not None else _source_tier(render_img1, _document.preview_image1, _document.original_image1, presenter.store.viewport.session_data.image_state.image1)
                        _t2_gap = "full_res" if render_img2 is _document.full_res_image2 and render_img2 is not None else _source_tier(render_img2, _document.preview_image2, _document.original_image2, presenter.store.viewport.session_data.image_state.image2)
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
                _t1 = "full_res" if render_img1 is _document.full_res_image1 and render_img1 is not None else _source_tier(
                    render_img1,
                    _document.preview_image1,
                    _document.original_image1,
                    presenter.store.viewport.session_data.image_state.image1,
                )
                _t2 = "full_res" if render_img2 is _document.full_res_image2 and render_img2 is not None else _source_tier(
                    render_img2,
                    _document.preview_image2,
                    _document.original_image2,
                    presenter.store.viewport.session_data.image_state.image2,
                )
                _preview_log(
                    "update: apply_store_to_canvas - sig changed "
                    "(uid1=%s uid2=%s tier1=%s tier2=%s label=%dx%d diff=%s channel=%s)",
                    image_uid(render_img1),
                    image_uid(render_img2),
                    _t1,
                    _t2,
                    current_label_dims[0],
                    current_label_dims[1],
                    presenter.store.viewport.view_state.diff_mode,
                    presenter.store.viewport.view_state.channel_view_mode,
                )
                presenter._last_img_sig = img_sig
                # [ic-gap] apply correlation
                if _gap_enabled():
                    try:
                        global _last_gap_apply_sig
                        _geom2 = getattr(presenter.store.viewport.geometry_state, "image_display_rect_on_label", None)
                        _apply_sig = (image_uid(render_img1), image_uid(render_img2), _geom2, _t1, _t2)
                        if _apply_sig != _last_gap_apply_sig:
                            _last_gap_apply_sig = _apply_sig
                            _gap_log(
                                "apply gap_correlation gap_id=%s/%s tier=%s/%s size=%s/%s geom=%s pixmap=%sx%s label=%dx%d unified=%s",
                                image_uid(render_img1),
                                image_uid(render_img2),
                                _t1,
                                _t2,
                                _size_or_none(render_img1),
                                _size_or_none(render_img2),
                                _geom2,
                                getattr(presenter.store.viewport.geometry_state, "pixmap_width", None),
                                getattr(presenter.store.viewport.geometry_state, "pixmap_height", None),
                                current_label_dims[0],
                                current_label_dims[1],
                                getattr(presenter.store.viewport.session_data.render_cache, "unification_in_progress", False),
                            )
                    except Exception:
                        pass
                if render_img1 and render_img2:
                    apply_store_to_canvas(
                        image_label,
                        presenter.store,
                        render_img1,
                        render_img2,
                        fit_content=False,
                        source_image1=gui_source1,
                        source_image2=gui_source2,
                        source_key=source_key,
                        display_cache_key=_display_cache_key(render_img1, render_img2),
                        clip_overlays_to_image_bounds=False,
                    )
                    # ``_update_preview_tracking`` already updated
                    # ``_last_display_uids`` / ``_last_applied_preview_uid`` /
                    # ``_last_superseded_preview_uid`` via ``image_uid`` equality
                    # (not ``is``) before the ``img_sig`` guard -- keeps single-side
                    # and scene-only picks armed for the next ``pick``.
                    # pick log vs GPU: correlate tier log with actual _stored_pil_images after upload_pil_images/realize_tile_plan
                    try:
                        _stored_actual = getattr(image_label.runtime_state, "_stored_pil_images", [None, None])
                        _gpu_t1 = "full_res" if _stored_actual[0] is _document.full_res_image1 and _stored_actual[0] is not None else _source_tier(
                            _stored_actual[0],
                            _document.preview_image1,
                            _document.original_image1,
                            presenter.store.viewport.session_data.image_state.image1,
                        )
                        _gpu_t2 = "full_res" if _stored_actual[1] is _document.full_res_image2 and _stored_actual[1] is not None else _source_tier(
                            _stored_actual[1],
                            _document.preview_image2,
                            _document.original_image2,
                            presenter.store.viewport.session_data.image_state.image2,
                        )
                        _preview_log(
                            "pick->GPU applied: picked tier1=%s tier2=%s GPU tier1=%s tier2=%s picked_uids=%s/%s stored_uids=%s/%s match=%s",
                            _t1,
                            _t2,
                            _gpu_t1,
                            _gpu_t2,
                            image_uid(render_img1),
                            image_uid(render_img2),
                            image_uid(_stored_actual[0]) if _stored_actual[0] is not None else None,
                            image_uid(_stored_actual[1]) if _stored_actual[1] is not None else None,
                            _t1 == _gpu_t1 and _t2 == _gpu_t2,
                        )
                    except Exception:
                        pass
            else:
                # pick log vs GPU: handle scene-only skip — GPU still shows old _stored_pil_images, not the pick
                _t1_skip = "full_res" if render_img1 is _document.full_res_image1 and render_img1 is not None else _source_tier(
                    render_img1,
                    _document.preview_image1,
                    _document.original_image1,
                    presenter.store.viewport.session_data.image_state.image1,
                )
                _t2_skip = "full_res" if render_img2 is _document.full_res_image2 and render_img2 is not None else _source_tier(
                    render_img2,
                    _document.preview_image2,
                    _document.original_image2,
                    presenter.store.viewport.session_data.image_state.image2,
                )
                _preview_log(
                    "update: skip apply - img_sig unchanged (uid1=%s uid2=%s picked_tier=%s/%s) scene-only repaint",
                    image_uid(render_img1),
                    image_uid(render_img2),
                    _t1_skip,
                    _t2_skip,
                )
                runtime_state = getattr(image_label, "runtime_state", None)
                if runtime_state is not None:
                    runtime_state._store = presenter.store
                    image_label.set_render_scene(
                        build_render_scene(
                            presenter.store,
                            apply_channel_mode_in_shader=bool(
                                getattr(
                                    runtime_state, "_apply_channel_mode_in_shader", True
                                )
                            ),
                            clip_overlays_to_image_bounds=False,
                        )
                    )
                    # Correlate scene-only pick with actual GPU still holding old stored images
                    try:
                        _stored_skip = getattr(runtime_state, "_stored_pil_images", [None, None])
                        _gpu_skip_t1 = "full_res" if _stored_skip[0] is _document.full_res_image1 and _stored_skip[0] is not None else _source_tier(
                            _stored_skip[0],
                            _document.preview_image1,
                            _document.original_image1,
                            presenter.store.viewport.session_data.image_state.image1,
                        )
                        _gpu_skip_t2 = "full_res" if _stored_skip[1] is _document.full_res_image2 and _stored_skip[1] is not None else _source_tier(
                            _stored_skip[1],
                            _document.preview_image2,
                            _document.original_image2,
                            presenter.store.viewport.session_data.image_state.image2,
                        )
                        _preview_log(
                            "pick->GPU scene-only: picked tier=%s/%s GPU tier still %s/%s stored_uids=%s/%s scene_only=True",
                            _t1_skip,
                            _t2_skip,
                            _gpu_skip_t1,
                            _gpu_skip_t2,
                            image_uid(_stored_skip[0]) if _stored_skip[0] is not None else None,
                            image_uid(_stored_skip[1]) if _stored_skip[1] is not None else None,
                        )
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
    visible_models = [
        model
        for model in (_query_overlay(presenter.store, "overlay.all_states", ()) or ())
        if bool(model.get("visible", False))
    ]
    _should_render = bool(_query_overlay(presenter.store, "overlay.enabled", False))
    if _should_render and visible_models:
        current_mag_sig = presenter.overlay.get_signature()
        last_mag_sig = getattr(presenter, "_last_mag_signature", None)
        image_label = presenter.widget.image_label
        current_mag_state = (
            current_mag_sig,
            getattr(image_label, "_source_images_ready", False),
            tuple(getattr(image_label, "_source_image_ids", []) or []),
        )
        mag_is_dirty = current_mag_state != last_mag_sig

        if mag_is_dirty:
            presenter.overlay.rebuild_overlay()
            presenter._last_mag_signature = current_mag_state
            return True
    else:
        reset_canvas_overlays(presenter.widget.image_label)
        presenter._last_mag_signature = None
    return False


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
