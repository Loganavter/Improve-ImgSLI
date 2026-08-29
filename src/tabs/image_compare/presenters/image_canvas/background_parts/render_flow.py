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
    return candidate.size


def pick_display_with_preview_backing(*candidates, last_applied_uid=None):
    """Display-pair picker for the live canvas (stored role).

    ``pick_display_image`` only returns a ``TiledPixelStore`` once its
    pyramid is complete, so the first-load path naturally shows the 1024px
    preview as the backing until the pyramid catches up. On-the-fly content
    changes (swap, next image, auto-crop resizing the store, a fresh
    preview arriving while the previous unified store is still installed)
    can bypass that: the store's pyramid is already complete, so the canvas
    flips straight to store tiles whose fallback-LOD baseline is the
    *previous* content -- the new preview never appears underneath.

    Rule: while the slot's preview is *fresh* (its ``image_uid`` differs
    from the display pair last applied to the canvas), prefer the preview
    for the stored role regardless of pyramid state. The next apply cycle
    (unify result / pyramid-completion invalidation) then finds the preview
    no longer fresh, picks the store as usual, and the flip's fallback
    baseline is exactly the new preview tiles -- the backing survives every
    on-the-fly change instead of only the first load.
    """
    preview = candidates[1] if len(candidates) > 1 else None
    if preview is not None and image_uid(preview) != last_applied_uid:
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
        return

    if _is_background_tab(presenter):
        _mark_render_stale(presenter)
        return

    is_interactive = presenter.store.viewport.interaction_state.is_interactive_mode

    if is_interactive:
        presenter._pending_interactive_mode = True

    if is_interactive:
        presenter._update_scheduler_timer.stop()
        result = presenter.update_comparison_if_needed()
        if result:
            presenter._pending_interactive_mode = None
    else:
        if not presenter._update_scheduler_timer.isActive():
            presenter._update_scheduler_timer.start()


def update_comparison_if_needed(presenter):
    if _is_background_tab(presenter):
        _mark_render_stale(presenter)
        return False

    if (
        not getattr(presenter.main_window_app, "_is_ui_stable", False)
        or presenter.store.viewport.interaction_state.resize_in_progress
    ):
        return False

    if (
        not presenter.main_window_app.isVisible()
        or presenter.main_window_app.isMinimized()
    ):
        return False

    label_width, label_height = presenter.get_current_label_dimensions()
    if label_width <= 2 or label_height <= 2:
        return False

    if getattr(
        presenter.store.viewport.session_data.render_cache,
        "unification_in_progress",
        False,
    ):
        if presenter.store.viewport.session_data.image_state.image1 is None:
            return False

    _document = presenter.store.get_session_state_slot("document")
    if _document is None:
        return False
    source1 = (
        _document.full_res_image1
        or _document.preview_image1
        or _document.original_image1
    )
    source2 = (
        _document.full_res_image2
        or _document.preview_image2
        or _document.original_image2
    )

    if presenter.store.viewport.view_state.showing_single_image_mode != 0:
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
        return False

    have1 = bool(
        presenter.store.viewport.session_data.image_state.image1 or source1
    )
    have2 = bool(
        presenter.store.viewport.session_data.image_state.image2 or source2
    )
    if not have1 and not have2:
        presenter.widget.image_label.clear()
        presenter.current_displayed_pixmap = None
        return False
    if not have1 or not have2:
        # One side is mid-reload / empty. Keep showing the live half instead of
        # blanking the whole canvas (ClearImageSlotData + path-only load).
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
        return False

    src_resize1 = presenter.store.viewport.session_data.image_state.image1
    src_resize2 = presenter.store.viewport.session_data.image_state.image2
    size1 = _size_or_none(src_resize1) or _size_or_none(source1)
    size2 = _size_or_none(src_resize2) or _size_or_none(source2)
    if size1 and size2:
        img1_w, img1_h = size1
        img2_w, img2_h = size2
        scale1 = min(label_width / img1_w, label_height / img1_h)
        scale2 = min(label_width / img2_w, label_height / img2_h)
        scale = min(scale1, scale2)
        scaled_w = max(1, int(img1_w * scale))
        scaled_h = max(1, int(img1_h * scale))
    else:
        scaled_w, scaled_h = label_width, label_height

    presenter.store.viewport.geometry_state.pixmap_width = scaled_w
    presenter.store.viewport.geometry_state.pixmap_height = scaled_h
    img_x, img_y = (label_width - scaled_w) // 2, (label_height - scaled_h) // 2
    presenter.store.viewport.geometry_state.image_display_rect_on_label = Rect(
        img_x, img_y, scaled_w, scaled_h
    )

    current_bg_sig = presenter.background.get_background_signature(source1, source2)
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
            img1 = pick_display_with_preview_backing(
                presenter.store.viewport.session_data.image_state.image1,
                _document.preview_image1,
                _document.original_image1,
                last_applied_uid=_last_display_uids.get(1),
            )
            img2 = pick_display_with_preview_backing(
                presenter.store.viewport.session_data.image_state.image2,
                _document.preview_image2,
                _document.original_image2,
                last_applied_uid=_last_display_uids.get(2),
            )
            render_img1, render_img2 = img1, img2

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
                presenter._last_img_sig = img_sig
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
                    presenter._last_display_uids = {
                        1: image_uid(render_img1),
                        2: image_uid(render_img2),
                    }
            else:
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
            presenter._last_mag_signature = None
            presenter._last_bg_signature = current_bg_sig
            presenter._last_label_dims = current_label_dims
            if presenter._cached_base_pixmap is None:
                presenter._cached_base_pixmap = QPixmap(1, 1)
        else:
            return False
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
