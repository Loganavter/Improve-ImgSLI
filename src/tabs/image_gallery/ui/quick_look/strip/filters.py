"""Quick Look series-strip event filters (wheel / lasso / repin).

Split out of the former ``ui/quick_look/strip.py`` (plan-gallery-split-2026-10-17,
Part C2). Bodies moved verbatim; names/signatures unchanged.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt

from .helpers import _repin_strip_rank_buttons
from .paint import (
    _strip_apply_lasso_selection,
    _strip_lasso_pick,
    _strip_refresh_selection,
    _strip_scroll_wheel,
)


class _StripWheelFilter(QObject):
    """Viewport wheel filter: plain wheel over the strip scrolls it.

    The toolkit OverlayScrollArea glides only the vertical bar, which the
    strip never overflows — without this filter a wheel over the strip
    does nothing (the native bars are AlwaysOff). Consumes the event only
    when the strip actually moved (at an edge it returns False so the
    wheel propagates to the outer vertical column scroll). Installed once
    per overlay; parented to the viewport. Never raises.
    """

    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self._overlay = overlay

    def eventFilter(self, watched, event):  # noqa: N802
        try:
            if event.type() == QEvent.Type.Wheel and _strip_scroll_wheel(
                self._overlay, event
            ):
                return True
        except Exception:
            pass
        return False
class _StripLassoFilter(QObject):
    """Rubber-band multi-select (marquee selection) on the strip.

    Left-press + drag past the drag threshold opens a QRubberBand over
    the host; on release every thumb container intersecting the rect joins
    Quick Look's OWN selection (``overlay._strip_selected_paths`` — local
    to the strip, the owner/grid selection is never touched). A release
    that never passed the threshold is an ordinary click: the strip's own
    selection (if any) is dropped, then the filter returns False and the
    thumb's own switch path runs.

    When the press started on a thumb and a lasso DID show, the trailing
    release would still fire the thumb click (same widget press+release)
    and walk the preview — that click is swallowed via
    ``overlay._strip_lasso_ate_click`` (checked first in ``_make_switch``).

    Installed on the host, the scroll viewport (full strip width —
    viewport gaps past the host edge must start a lasso too) and every
    thumb container, thumb button and rank pill (presses on children
    never reach the host filter); positions map to host coordinates.

    Two guards keep coordinates honest. First, dedup: one physical event
    reaches this filter once per ancestor (receiver, then each parent it
    propagates to) with IDENTICAL raw type/buttons/pos, and a second
    mapping would use the wrong widget's coordinates — repeats are
    skipped so exactly the first delivery (watched == receiver, correct
    coords) takes effect. Second, plain containers (host/viewport/thumb
    container) swallow handled Left press/move/release so nothing
    propagates further; buttons/pills are never swallowed (clicks,
    ripple, hover stay intact — and buttons accept presses/releases
    themselves, so those never propagate anyway). Never raises.
    """

    def __init__(self, overlay, host):
        super().__init__(host)
        self._overlay = overlay
        self._host = host
        # All lasso geometry lives in SCROLL-VIEWPORT coordinates, not host
        # coordinates: the host sizes to its contents and can be much
        # narrower than the viewport, so a host-parented band clips to a
        # sliver near the cards and host-space rects miss. The viewport
        # spans the full visible strip width (live-proven: picked=0 with a
        # 590px rect while the host held 2 thumbs).
        try:
            _scroll = getattr(overlay, "_strip_scroll", None)
            _view = _scroll.viewport() if _scroll is not None else None
        except Exception:
            _view = None
        self._view = _view if _view is not None else host
        self._origin = None
        self._band = None
        # Dedup key of the last processed press/move/release: one physical
        # event reaches this filter once per ancestor (receiver, then each
        # parent it propagates to) with IDENTICAL type/buttons/pos, and the
        # second mapping would use the wrong widget's coordinates. Skip
        # repeats so exactly one handling (the first, with watched ==
        # receiver and correct coords) takes effect.
        self._seen = None
        # Coalescing signature of the last live selection applied mid-drag:
        # a move that does not change membership only shifts the band, never
        # re-paints every thumb (grid parity, ``_marquee_last_update_sig``).
        self._pick_sig = None

    def _to_strip(self, widget, pos):
        # Viewport-space mapping (see __init__ for why not host-space):
        # mapTo(widget -> viewport) is valid for the viewport itself and
        # everything inside it (host, containers, buttons, pills); above
        # the viewport the direction flips to mapFrom; anything else goes
        # through the global round-trip. A wrong direction logs
        # "mapTo(): parent must be in parent hierarchy" and yields
        # garbage rects (live-proven).
        try:
            view = self._view
            if widget is None or widget is view:
                return pos
            try:
                if view.isAncestorOf(widget):
                    return widget.mapTo(view, pos)
            except Exception:
                pass
            try:
                if widget.isAncestorOf(view):
                    return view.mapFrom(widget, pos)
            except Exception:
                pass
            try:
                return view.mapFromGlobal(widget.mapToGlobal(pos))
            except Exception:
                return pos
        except Exception:
            return pos

    def _to_host(self, widget, pos):
        # Kept for compatibility; new code uses _to_strip (viewport space).
        return self._to_strip(widget, pos)

    def _threshold(self) -> int:
        try:
            from PySide6.QtWidgets import QApplication as _QA

            return max(4, int(_QA.startDragDistance()))
        except Exception:
            return 8

    def _hide_band(self):
        band, self._band = self._band, None
        if band is not None:
            try:
                band.hide()
            except Exception:
                pass

    def _apply_live_selection(self, rect):
        """Preview the strip selection mid-drag (grid marquee parity).

        The main grid applies its preview on every band update; the strip
        used to commit only on release, so the accent only appeared once the
        drag ended. Coalesce on membership so an unchanged hit set repaints
        nothing (only the band geometry moves).
        """
        try:
            picked = _strip_lasso_pick(self._overlay, rect)
        except Exception:
            return
        sig = frozenset(picked)
        if sig == self._pick_sig:
            return
        self._pick_sig = sig
        try:
            self._overlay._strip_selected_paths = set(picked)
        except Exception:
            pass
        try:
            _strip_refresh_selection(self._overlay)
        except Exception:
            pass

    def eventFilter(self, watched, event):  # noqa: N802
        # Return policy (kills double-delivery: a press handled on the host
        # must never ALSO be processed on the viewport — propagated events
        # keep the original receiver's coordinates, so the second mapping
        # produces garbage rects):
        # - plain containers (host/viewport/thumb container): swallow
        #   handled Left press/move/release (nothing else needs them; no
        #   grab is set, so later moves hit-test fresh with watched ==
        #   receiver and every mapping stays correct);
        # - buttons/pills: never swallow (clicks, ripple, hover stay
        #   intact; buttons accept presses/releases themselves, so nothing
        #   propagates further anyway).
        try:
            from PySide6.QtCore import QPoint as _QP
            from PySide6.QtCore import QRect as _QR

            try:
                from sli_ui_toolkit.widgets import Button as _BL

                _is_button = isinstance(watched, _BL)
            except Exception:
                _is_button = False
            t = event.type()
            if t == QEvent.Type.MouseButtonPress:
                try:
                    if event.button() == Qt.MouseButton.LeftButton:
                        try:
                            _pos = event.position().toPoint()
                            _key = (t, event.button(), _pos.x(), _pos.y())
                        except Exception:
                            self._origin = None
                            return False
                        if _key == self._seen:
                            return False
                        self._seen = _key
                        self._hide_band()
                        # New gesture: drop the coalescing signature so the
                        # first move always previews, even at equal membership.
                        self._pick_sig = None
                        self._origin = self._to_strip(watched, _pos)
                        try:
                            from tabs.image_gallery.debug import gallery_debug as _dbg

                            _dbg(
                                "strip lasso press on=%s pos=%s",
                                type(watched).__name__,
                                self._origin,
                            )
                        except Exception:
                            pass
                        if not _is_button:
                            return True
                except Exception:
                    self._origin = None
            elif t == QEvent.Type.MouseMove:
                if self._origin is not None:
                    try:
                        if not (event.buttons() & Qt.MouseButton.LeftButton):
                            self._origin = None
                            self._hide_band()
                        else:
                            _raw = event.position().toPoint()
                            _mkey = (t, event.buttons(), _raw.x(), _raw.y())
                            if _mkey == self._seen:
                                return False
                            self._seen = _mkey
                            cur = self._to_strip(watched, _raw)
                            dx = cur.x() - self._origin.x()
                            dy = cur.y() - self._origin.y()
                            if self._band is None and (abs(dx) + abs(dy)) >= self._threshold():
                                from PySide6.QtWidgets import QRubberBand as _QRB

                                self._band = _QRB(_QRB.Shape.Rectangle, self._view)
                                try:
                                    self._band.show()
                                except Exception:
                                    pass
                                try:
                                    from tabs.image_gallery.debug import gallery_debug as _dbg2

                                    _dbg2("strip lasso band shown origin=%s", self._origin)
                                except Exception:
                                    pass
                            if self._band is not None:
                                _rect = _QR(_QP(self._origin), _QP(cur)).normalized()
                                self._band.setGeometry(_rect)
                                # Live accent while dragging (grid parity):
                                # thumbs in the band light up on every move,
                                # not only after release.
                                self._apply_live_selection(_rect)
                                if not _is_button:
                                    return True
                    except Exception:
                        pass
            elif t == QEvent.Type.MouseButtonRelease:
                try:
                    if event.button() == Qt.MouseButton.LeftButton and self._origin is not None:
                        _rpos = event.position().toPoint()
                        _rkey = (t, event.button(), _rpos.x(), _rpos.y())
                        if _rkey == self._seen:
                            return False
                        self._seen = _rkey
                        _had_band = self._band is not None and self._band.isVisible()
                        if _had_band:
                            rect = self._band.geometry().normalized()
                            try:
                                from tabs.image_gallery.debug import gallery_debug as _dbg3

                                _dbg3("strip lasso release rect=%s", rect)
                            except Exception:
                                pass
                            if rect.width() >= 4 or rect.height() >= 4:
                                try:
                                    self._overlay._strip_lasso_ate_click = True
                                except Exception:
                                    pass
                                try:
                                    _strip_apply_lasso_selection(self._overlay, rect)
                                except Exception:
                                    pass
                        else:
                            # Plain click (no marquee ever showed): the
                            # strip's OWN selection goes away. On a thumb
                            # the trailing button click still walks the
                            # preview afterwards (the swallow flag is only
                            # set for the lasso path above); on a viewport
                            # gap there is nothing else to do.
                            try:
                                _ov = self._overlay
                                if _ov is not None and getattr(
                                    _ov, "_strip_selected_paths", None
                                ):
                                    _ov._strip_selected_paths = set()
                                    try:
                                        _strip_refresh_selection(_ov)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        self._origin = None
                        self._hide_band()
                        if _had_band and not _is_button:
                            return True
                except Exception:
                    pass
        except Exception:
            pass
        return False
class _StripRepinFilter(QObject):
    """Host-resize filter: re-pin rank pills when the strip settles.

    Installed once per overlay (parented to the host); layout settling
    after a rebuild is async, so the end-of-rebuild repin alone can pin
    from stale geometry. Never raises.
    """

    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self._overlay = overlay

    def eventFilter(self, watched, event):  # noqa: N802
        try:
            if event.type() == QEvent.Type.Resize:
                _repin_strip_rank_buttons(self._overlay)
        except Exception:
            pass
        return False
