"""Target-canvas watching/wiring for ``GlassHUD`` -- split out per
docs/dev/CODE_PATTERNS.md's "thin owner + use_cases module" pattern (own
orthogonal concern: tracking the target canvas's geometry/frame signal and
(un)registering this HUD's backdrop from/to it, independent of the text-mask
rasterization concern in ``text_mask.py`` or the backdrop-style/registration
concern that stays on ``GlassHUD`` itself).

Functions here take the owning ``GlassHUD`` instance as their first
argument and read/write its instance state directly -- same shape as
``ui/drag_drop.py``'s split off ``MultiCompareWidget``, see that pattern's
reference table.
"""

from __future__ import annotations

import time

from ui.widgets.flyout_debug import flyout_debug, flyout_debug_enabled


def connect_zoom_refresh(hud, target_widget) -> None:
    """Recompute the registered panel rect shortly after
    ``target_widget.zoomChanged`` fires -- cheap (updates a dict entry, not
    a texture readback), so this can just run directly."""
    if hasattr(target_widget, "zoomChanged"):
        target_widget.zoomChanged.connect(lambda _zoom: hud._refresh_backdrop())


def watch_target(hud, target_widget) -> None:
    """Track ``target_widget``'s geometry directly instead of relying on
    the host to call ``reposition()``/``sync_position()`` from its own
    resize/move hooks.

    The target can resize or move from a purely internal layout change (a
    sibling row's height changing, a panel toggling) with no top-level
    window resize/move/show -- the events the host otherwise hooks this up
    to. Watching the target itself makes this self-contained instead of
    every host having to remember to wire it.

    Reads ``hud._target_widget`` as the *previous* target: callers
    (``InfoHUD.show_on``/``ZoomIndicator``) call this *before* assigning
    ``hud._target_widget = target_widget`` themselves -- don't reorder that
    without updating both call sites, this function relies on it to know
    what to disconnect."""
    previous = hud._target_widget
    if target_widget is previous:
        return
    if previous is not None:
        previous.removeEventFilter(hud)
        registry = getattr(previous, "glass_panels", None)
        if registry is not None:
            registry.unregister(id(hud))
        if hasattr(previous, "frameSubmitted"):
            try:
                previous.frameSubmitted.disconnect(hud._display.update)
            except (RuntimeError, TypeError):
                pass
            try:
                previous.frameSubmitted.disconnect(hud._maybe_update_text_mask)
            except (RuntimeError, TypeError):
                pass
            try:
                previous.frameSubmitted.disconnect(hud._debug_frame_submitted)
            except (RuntimeError, TypeError):
                pass
    if target_widget is not None:
        target_widget.installEventFilter(hud)
        if hasattr(target_widget, "frameSubmitted"):
            target_widget.frameSubmitted.connect(hud._display.update)
            target_widget.frameSubmitted.connect(hud._maybe_update_text_mask)
            if flyout_debug_enabled():
                target_widget.frameSubmitted.connect(hud._debug_frame_submitted)
    hud._display.set_source(target_widget, id(hud))


def debug_frame_submitted(hud) -> None:
    """IMGSLI_FLYOUT_DEBUG=1 only: reports how often the target canvas's
    own ``frameSubmitted`` fires -- answers "is the canvas rendering
    continuously even at idle, or is this HUD's own work
    (``maybe_update_text_mask`` etc.) the thing spinning". See
    docs/dev/rendering/glass-panel-text-vibrancy-plan.md Phase 3."""
    hud._debug_frame_count += 1
    now = time.monotonic()
    if now - hud._debug_frame_window_start >= 1.0:
        flyout_debug(
            "%s: target frameSubmitted rate self=%#x target=%r frames=%d over %.2fs",
            type(hud).__name__,
            id(hud),
            hud._target_widget,
            hud._debug_frame_count,
            now - hud._debug_frame_window_start,
        )
        hud._debug_frame_count = 0
        hud._debug_frame_window_start = now