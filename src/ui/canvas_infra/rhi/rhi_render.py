from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette

from engine.gpu.mip_cascade import MipCascadeNotReady

from shared.debug_flags import env_flag as _env_flag
from core.log_names import APP_LOGGER_NAME


def resolve_clear_color(widget) -> QColor:
    plan = getattr(widget, "_active_render_plan", None)
    fill_rgba = getattr(plan, "fill_rgba", None)
    if bool(getattr(widget, "_use_plan_fill_clear", False)):
        # Export offscreen: plan fill paints the virtual-canvas chrome. When
        # fill is off, clear must stay transparent so pad pixels remain
        # alpha=0 (theme clear would bake an opaque wrong color that
        # ``apply_background_fill`` cannot replace).
        if plan is not None:
            if fill_rgba is not None and len(fill_rgba) >= 4:
                return QColor(
                    int(fill_rgba[0]),
                    int(fill_rgba[1]),
                    int(fill_rgba[2]),
                    int(fill_rgba[3]),
                )
            return QColor(0, 0, 0, 0)
        # No plan yet (GPU-export warm-up canvas, before any export applies a
        # plan): fall through to the opaque theme clear. A transparent clear
        # here makes the shown offscreen widget render as a see-through hole
        # on compositors that don't honor WA_DontShowOnScreen for parentless
        # QRhiWidgets (flashes the window behind through).

    # Live QRhiWidget sits under a WA_TranslucentBackground CSD shell. Any
    # clear alpha < 255 punches through to the desktop on Windows/D3D
    # (see docs/dev/rendering/render-pass-contract.md + qrhi-gotchas).
    # Match Multi Compare's ``_theme_or_palette_bg`` opaque rule.
    color = getattr(widget, "_theme_background_color", None)
    if isinstance(color, QColor) and color.isValid():
        out = QColor(color)
        out.setAlpha(255)
        _log_clear_color(widget, out, source="_theme_background_color")
        return out

    palette = widget.palette()
    color = palette.color(QPalette.ColorRole.Window)
    if not color.isValid():
        color = palette.color(QPalette.ColorRole.Base)
    if not color.isValid():
        color = QColor(245, 245, 245)
    color.setAlpha(255)
    _log_clear_color(widget, color, source="palette.Window")
    return color


def _log_clear_color(widget, color: QColor, *, source: str) -> None:
    try:
        # Same gate as the canvas tab's own first-frame wrapper
        # (IMGSLI_IC_FIRST_FRAME_DEBUG via shared.debug_flags.env_flag) —
        # routed through the shared predicate so this inline check can't
        # drift from the wrapper's own gate.
        if not _env_flag("IMGSLI_IC_FIRST_FRAME_DEBUG"):
            return
        import logging

        logging.getLogger(APP_LOGGER_NAME).info(
            "[ic-first-frame] clear color %s rgba(%d,%d,%d,%d) widget=%s",
            source,
            color.red(),
            color.green(),
            color.blue(),
            color.alpha(),
            type(widget).__name__,
        )
    except Exception:
        pass


#: A typed "not ready yet" render failure is deferred, never raised: an
#: exception escaping a ``QRhiWidget`` render override is printed by PySide as
#: ``Error calling Python override of QRhiWidget::render()`` and, on the
#: default OpenGL backend (llvmpipe), killed the app in the 2026-10-21 audit.
_NOT_READY_INITIAL_MS = 50
_NOT_READY_MAX_MS = 1000


def defer_not_ready_render(widget, label: str, error: BaseException) -> None:
    """Keep the last frame up and retry a typed not-ready render shortly.

    The condition is transient by definition (a probe render target cannot be
    created on this driver stack *yet*), so the only correct reaction is to
    draw nothing, say so once, and try again on a timer. Backoff doubles per
    consecutive failure up to ``_NOT_READY_MAX_MS`` and resets on the first
    successful frame.
    """
    retries = int(getattr(widget, "_not_ready_retries", 0)) + 1
    delay = int(getattr(widget, "_not_ready_delay_ms", _NOT_READY_INITIAL_MS))
    widget._not_ready_retries = retries
    widget._not_ready_delay_ms = min(max(delay, _NOT_READY_INITIAL_MS) * 2, _NOT_READY_MAX_MS)
    if retries == 1:
        logging.getLogger(APP_LOGGER_NAME).info(
            "[render-not-ready] %s: %s; keeping the last frame, retrying in %d ms",
            label,
            error,
            delay,
        )
    QTimer.singleShot(delay, widget.update)


def render_or_defer(widget, label: str, render) -> bool:
    """Run one render; a typed not-ready condition defers instead of escaping.

    Returns the render's own truth value (``True`` only for a completed pass),
    ``False`` when the render was deferred. Any other exception propagates: only
    the typed, transient condition is absorbed.
    """
    try:
        painted = render()
    except MipCascadeNotReady as error:
        defer_not_ready_render(widget, label, error)
        return False
    if painted:
        widget._not_ready_retries = 0
        widget._not_ready_delay_ms = _NOT_READY_INITIAL_MS
    return bool(painted)


def render_clear_frame(widget, command_buffer) -> bool:
    """Run the tab RHI renderer; return whether a pass was actually recorded.

    A typed ``MipCascadeNotReady`` (the canvas probe mip target is not
    creatable on this backend *yet*) is deferred, not raised: the last frame
    stays on screen and a retry is scheduled (``render_or_defer``).
    """
    return render_or_defer(
        widget,
        "ic-canvas",
        lambda: widget._rhi_renderer.render(
            widget, command_buffer, resolve_clear_color(widget)
        ),
    )