"""QuickLookOverlay input handlers — mouse/wheel/context/key events.

Moved verbatim from ``ui/quick_look.py`` (plan-gallery-split-2026-10-17,
Part C2). Plain functions taking the overlay as their first argument; the
class keeps same-named one-line delegators so Qt's virtual dispatch is
unchanged. ``super()`` becomes an explicit ``TopLevelInWindowOverlay`` call
(the sole base) — same resolution.
"""

from __future__ import annotations

from sli_ui_toolkit.widgets import TopLevelInWindowOverlay


# W10: the 8px ring OUTSIDE the card (on the veil) is probed here at
# overlay level. Card resize drags are enabled (QL_RESIZABLE=True):
# W11 ring/plate presses inside either nav-arrow rect walk the series
# via the helpers (arrows never start a drag); other ring presses fall
# through to the veil dismiss below. Plain veil clicks dismiss the
# overlay (reverses the W6/W11 background-click ban; Esc/deactivate
# stay pinned).
def mousePressEvent(self, event) -> None:  # noqa: N802
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled
        from tabs.image_gallery.ui.quick_look.helpers import handle_ring_press, ring_zone_at

        _press_dbg = _dbg_enabled()
        _press_pos = event.position().toPoint()
        _press_zone = ring_zone_at(self, _press_pos) if _press_dbg else None
        if handle_ring_press(self, event):
            return
        if _press_dbg:
            try:
                _receiver = self.childAt(_press_pos)
                _receiver_name = (
                    f"{type(_receiver).__name__}:{_receiver.objectName()}"
                    if _receiver is not None
                    else "veil"
                )
            except Exception:
                _receiver_name = "?"
            _dbg(
                "ql-resize veil press declined zone=%s pos=(%d,%d) receiver=%s",
                _press_zone,
                _press_pos.x(),
                _press_pos.y(),
                _receiver_name,
            )
    except Exception:
        pass
    try:
        if self._maybe_start_region(event):
            return
    except Exception:
        pass
    # Plain veil press (ring declined above, children eat their own
    # presses): dismiss the overlay. Reverses the W6/W11 background-click
    # ban; Esc/deactivate stay pinned (flags unchanged).
    # NOTE: non-interactive children (Labels, histograms, scroll
    # viewport gaps) do NOT accept presses — those bubble up here.
    # A press inside the card is content, not veil: swallow it instead
    # of dismissing, otherwise every click on metrics/headers/preview
    # closes the overlay.
    try:
        _pos = event.position().toPoint()
        _content = getattr(self, "_content", None)
        if _content is not None:
            try:
                import shiboken6 as _shib

                _valid = bool(_shib.isValid(_content))
            except Exception:
                _valid = True
            if _valid:
                try:
                    _geo = _content.geometry()
                except Exception:
                    _geo = None
                if _geo is not None and int(_geo.width()) > 0 and int(_geo.height()) > 0:
                    if _geo.contains(_pos):
                        try:
                            event.accept()
                        except Exception:
                            pass
                        return
    except Exception:
        pass
    try:
        self.dismiss()
    except Exception:
        pass
    # Modal: the dismissing press is handled here — never propagate to
    # the gallery beneath (one veil click must not also toggle/select).
    try:
        event.accept()
    except Exception:
        pass
    return


def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
    # Modal: swallow double-clicks landing while visible.
    try:
        event.accept()
    except Exception:
        pass
    return


def wheelEvent(self, event) -> None:  # noqa: N802
    # Modal: veil wheel must not scroll the gallery behind the overlay
    # (children viewports eat their own wheel first).
    try:
        event.accept()
    except Exception:
        pass
    return


def contextMenuEvent(self, event) -> None:  # noqa: N802
    # Modal: no card menu from under the overlay (Menu key or
    # right-release menu gesture while the overlay owns the window).
    try:
        event.accept()
    except Exception:
        pass
    return


def mouseMoveEvent(self, event) -> None:  # noqa: N802
    try:
        from tabs.image_gallery.ui.quick_look.helpers import trace_move

        try:
            _pos = event.position().toPoint()
            trace_move(self, "overlay-move", _pos, self.childAt(_pos))
        except Exception:
            pass
    except Exception:
        pass
    try:
        if getattr(self, "_region_active", False):
            self._update_region(event)
            return
    except Exception:
        pass
    try:
        if getattr(self, "_border_drag", None) is not None:
            from tabs.image_gallery.ui.quick_look.helpers import handle_border_move
            if handle_border_move(self, event):
                return
        else:
            from tabs.image_gallery.ui.quick_look.helpers import handle_ring_hover
            handle_ring_hover(self, event)
    except Exception:
        pass
    TopLevelInWindowOverlay.mouseMoveEvent(self, event)


def mouseReleaseEvent(self, event) -> None:  # noqa: N802
    try:
        if getattr(self, "_region_active", False):
            self._finish_region(event)
            return
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.quick_look.helpers import handle_ring_release
        if handle_ring_release(self, event):
            return
    except Exception:
        pass
    TopLevelInWindowOverlay.mouseReleaseEvent(self, event)


def leaveEvent(self, event) -> None:  # noqa: N802
    try:
        if getattr(self, "_border_drag", None) is None:
            from tabs.image_gallery.ui.quick_look.helpers import apply_resize_cursor

            apply_resize_cursor(self, self, "overlay", None)
    except Exception:
        pass
    TopLevelInWindowOverlay.leaveEvent(self, event)


def keyPressEvent(self, event) -> None:  # noqa: N802
    # Esc closes via the toolkit base (close_on_escape=True).
    #
    # Arrows and Enter are NOT handled here. While the panel is visible it is a
    # NavigationManager *section* (quick_look/nav_section.py) owning the strip
    # row and the action row, so ←/→ move the focus ring, ↓/↑ cross the rows and
    # the focused toolkit Button activates itself on Enter/Space — the panel
    # never reaches this handler with those keys (the manager consumes them
    # first). A private per-key branch here would be a second cursor, which is
    # exactly what the section replaced (2026-10-17).
    TopLevelInWindowOverlay.keyPressEvent(self, event)
