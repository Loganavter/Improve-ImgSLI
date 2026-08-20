"""Startup placeholder / zoom indicator / focus-dim chrome for ``MultiCompareWidget``.

Split out of ``widget.py`` to keep that class down to composition/wiring --
mirrors the ``drag_drop`` split. Every function here takes the widget as its
first argument and reads/writes its instance state directly.

Qt calls ``resizeEvent``/``hideEvent``/``showEvent`` by name on the widget
itself, so those stay defined as thin methods on ``MultiCompareWidget`` that
delegate into this module.
"""

from __future__ import annotations


def sync_zoom_indicator(widget) -> None:
    indicator = getattr(widget, "zoom_indicator", None)
    if indicator is None:
        return
    st = widget.store.state
    from ui.widgets.flyout_debug import flyout_debug, flyout_debug_enabled

    if flyout_debug_enabled():
        flyout_debug(
            "mc-zoom-indicator: _sync_zoom_indicator() zoom=%.4f pan=(%.2f, %.2f) "
            "widget.size=%r canvas_container.size=%r canvas.size=%r",
            float(getattr(st, "zoom", 1.0)),
            float(getattr(st, "pan_x", 0.0)),
            float(getattr(st, "pan_y", 0.0)),
            widget.size(),
            widget._canvas_container.size(),
            widget.canvas.size(),
        )
    indicator.update_zoom(
        float(getattr(st, "zoom", 1.0)),
        float(getattr(st, "pan_x", 0.0)),
        float(getattr(st, "pan_y", 0.0)),
    )


def on_first_frame(widget) -> None:
    from tabs.multi_compare.first_frame_debug import mc_first_frame_debug

    placeholder = widget._startup_placeholder
    mc_first_frame_debug(
        widget.canvas,
        "first frame -> placeholder hidden (was_visible=%s was_covering=%s)",
        bool(placeholder is not None and placeholder.isVisible()),
        bool(
            placeholder is not None
            and placeholder.isVisible()
            and placeholder.geometry().intersects(widget.canvas.geometry())
        ),
    )
    if placeholder is not None:
        placeholder.hide()
    release_transition_mask(widget)


def release_transition_mask(widget) -> None:
    """Drop the workspace transition cover once an opaque frame is up.

    Mirrors image_compare's widget: without this the cover would stay for
    its whole ``max_duration`` (400 ms) on every tab enter, because the
    mask force-releases only on its deadline unless told otherwise.
    """
    context = widget._context
    services = getattr(context, "services", None) if context else None
    if not services:
        return
    mask = services.get("workspace.transition_mask")
    if mask is None:
        return
    try:
        mask.release()
    except Exception:
        import logging

        logging.getLogger("ImproveImgSLI").exception(
            "[workspace-transition] MC mask.release failed"
        )


def resize_event(widget, event) -> None:
    placeholder = getattr(widget, "_startup_placeholder", None)
    if placeholder is not None:
        # Always sync — during the first show/layout the placeholder is
        # still at its construction-time default size (100x30) and is not
        # "visible" yet, so an isVisible() guard would skip the resize and
        # leave the canvas uncovered (transparent) for its first frames.
        placeholder.sync_geometry()
    indicator = getattr(widget, "zoom_indicator", None)
    if indicator is not None and indicator.isVisible():
        indicator.sync_position()
    sync_focus_dim_overlays(widget)


def exit_focus(widget) -> None:
    from tabs.multi_compare.scene import actions

    if widget.state.is_focused:
        widget.store.dispatch(actions.set_focus(None))


def sync_focus_dim_overlays(widget) -> None:
    dim_toolbar = getattr(widget, "_focus_dim_toolbar", None)
    dim_footer = getattr(widget, "_focus_dim_footer", None)
    if dim_toolbar is None or dim_footer is None:
        return
    dim_toolbar.setGeometry(widget.toolbar.geometry())
    dim_footer.setGeometry(widget.footer.geometry())
    dim_toolbar.raise_()
    dim_footer.raise_()


def hide_event(widget, event) -> None:
    # ZoomIndicator is a `pinned` flyout reparented onto the app-wide
    # OverlayLayer host (see ui/flyout_policy.py), not a child of this
    # page -- Qt's own hideEvent on this page (fired when the workspace
    # switches to another tab/session) does not cascade to it, so
    # without this it kept rendering above whichever tab became active
    # next. show_event below resyncs it from current state when this tab
    # is shown again.
    indicator = getattr(widget, "zoom_indicator", None)
    if indicator is not None:
        indicator.hide()


def show_event(widget, event) -> None:
    placeholder = getattr(widget, "_startup_placeholder", None)
    if placeholder is not None:
        # Re-size/raise before the canvas's first paint: at construction
        # the placeholder tracked a 100x30 container, and leaving it there
        # exposes the unrendered (transparent) QRhi surface on the first
        # frames (see the placeholder probe in canvas_widget.py).
        placeholder.sync_geometry()
    sync_zoom_indicator(widget)
