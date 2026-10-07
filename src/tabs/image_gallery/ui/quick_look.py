"""Stage 2 S4 quick look — TopLevelInWindowOverlay with two-panel layout.
Audit-Meta: pattern=thin-owner reason="thin owner delegating to ui/quick_look/* helpers,bars,histograms,metrics,artifacts,strip"

Left: large preview (pixmap, source inset for fidelity mode)
     + prev/next walk the series (←→).
Right: metric bars per mode (SSIM/sharpness/exposure), artifact rows with
       mini-visualizations (stub), filename meta + brief (series note, no
       counts); bottom: full-width series strip (SOURCE/viewing/pending/
       rejected thumbs clickable), bottom bar buttons.
Public toolkit only: TopLevelInWindowOverlay, Button variant="surface", Label,
scaled_px. No setStyleSheet — painter pipeline owns visuals.
"""

from __future__ import annotations

import pathlib as _ql_path
import sys as _ql_sys
try:
    __path__ = [str(_ql_path.Path(__file__).with_suffix(""))]  # type: ignore[attr-defined]
    _pkg = _ql_sys.modules.get(__name__)
    if _pkg is not None and not hasattr(_pkg, "__path__"):
        setattr(_pkg, "__path__", __path__)  # type: ignore[attr-defined]
except Exception:
    pass

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QBrush, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Label, TopLevelInWindowOverlay

# S4 v2 LIGHT (svg:27): modal dim-veil alpha, mirroring
# ui/clean_review.py DIM_VEIL_ALPHA (mockup "modal veil" fill-opacity 0.45).
# TopLevelInWindowOverlay has no paintEvent (transparent background), so the
# overlay paints this veil itself in gallery scope — never in the toolkit.
DIM_VEIL_ALPHA = round(0.45 * 255)  # 115

# Re-export for tests
try:
    from tabs.image_gallery.ui.quick_look.helpers import (
        _set_colored_text,
        _source_dimensions,
        _theme_color,
        _thumb_pixmap,
        _token_color,
    )
except Exception:
    _thumb_pixmap = _theme_color = _token_color = _set_colored_text = _source_dimensions = None  # type: ignore
try:
    from tabs.image_gallery.ui.quick_look.bars import _BarWidget, _DualRestoredInventedBar
    from tabs.image_gallery.ui.quick_look.histograms import _BandingCombHistogram, _GenericHistogram, _HistogramStub
except Exception:
    pass


class QuickLookOverlay(TopLevelInWindowOverlay):
    """S4 quick look overlay — two-panel layout. Thin owner."""

    compareRequested = Signal(object)
    rejectToggled = Signal(object)
    setSource = Signal(object)

    def __init__(self, parent: QWidget, owner=None) -> None:
        # Close policy: veil click, Esc, and the X button close;
        # minimize/focus loss stay pinned. Reverses W6 (background ban) and
        # the W11 Esc ban; no report state is lost — triage state lives in
        # the controller, reopen re-resolves it. close_on_background stays
        # False so the base class never dismisses on its own: the veil
        # dismiss is explicit (ring presses return earlier, children eat
        # their own presses); Esc flows through the base keyPressEvent.
        super().__init__(parent, close_on_background=False, close_on_escape=True, close_on_deactivate=False)
        # G3 dispatch-only: the triage owner (controller) arrives explicitly
        # via __init__/show_for and is stored here. Assigned ONLY from those
        # explicit arguments — never poked from outside, never re-scanned.
        self._owner = owner
        self._current_item = None
        self._series_items: list = []
        self._current_idx: int = 0
        self._mode = None
        self._source_path: Path | None = None
        # Build UI via helpers
        try:
            from tabs.image_gallery.ui.quick_look.helpers import build_overlay_ui
            build_overlay_ui(self)
        except Exception:
            # Fallback inline minimal if builder fails
            pass
        # Ensure tracking lists exist
        if not hasattr(self, "_strip_buttons"):
            self._strip_buttons: list = []
        if not hasattr(self, "_metric_rows"):
            self._metric_rows: list = []
        if not hasattr(self, "_artifact_rows"):
            self._artifact_rows: list = []
        if not hasattr(self, "_strip_caption_labels"):
            self._strip_caption_labels: list = []
        # Canvas preview slot defaults (build_overlay_ui sets them too; the
        # inline-minimal fallback above does not).
        if not hasattr(self, "_preview_canvas"):
            self._preview_canvas = None
        if not hasattr(self, "_preview_store"):
            self._preview_store = None
        # W8: the resizable card plate is a plain child widget — its own
        # resizes never reach the overlay's resizeEvent, so watch it and
        # re-run the pin hooks (nav circles, source inset, resize grip).
        try:
            content = getattr(self, "_content", None)
            if content is not None:
                content.installEventFilter(self)
                # D5: fast border→child jumps can skip content-Leave delivery,
                # stranding a set plate cursor over inheriting children
                # (proven live: qtbot jump border→thumb/label keeps SizeHor).
                # One filter over the whole subtree recomputes the slot on
                # every landing move, so staleness heals on arrival.
                self._install_subtree_hover_watch(content)
        except Exception:
            pass

    def _install_subtree_hover_watch(self, root) -> None:
        """Install this overlay as MouseMove observer on a content subtree.

        Idempotent (remove-then-install): ChildAdded storms must never stack
        duplicate filter entries on the same widget.
        """
        try:
            from PySide6.QtWidgets import QWidget as _QW

            stack = [root]
            seen = set()
            while stack:
                w = stack.pop()
                try:
                    if w is None or id(w) in seen:
                        continue
                    seen.add(id(w))
                    if w is not self:
                        try:
                            w.removeEventFilter(self)
                        except Exception:
                            pass
                        try:
                            w.installEventFilter(self)
                        except Exception:
                            pass
                    try:
                        stack.extend(w.findChildren(_QW))
                    except Exception:
                        pass
                except Exception:
                    continue
        except Exception:
            pass

    def _reposition_source_inset(self) -> None:
        # Source/crop inset blocks are absolute children of the preview
        # (bottom-left over the image) — re-pin with every resize, then nav.
        try:
            from tabs.image_gallery.ui.quick_look.insets import reposition_preview_insets
            reposition_preview_insets(self)
        except Exception:
            pass
        # W4 item 6: nav circles are absolute card children — re-pin with
        # every resize.
        try:
            from tabs.image_gallery.ui.quick_look.helpers import reposition_nav_buttons
            reposition_nav_buttons(self)
        except Exception:
            pass

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        try:
            self._reposition_source_inset()
        except Exception:
            pass
        # W8: keep the drag handle pinned on overlay (window) resizes.
        try:
            from tabs.image_gallery.ui.quick_look.helpers import reposition_grip
            reposition_grip(self)
        except Exception:
            pass

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # W8: card-plate resizes (user drag via the corner grip or direct
        # resizes) re-run the same pin hooks as resizeEvent.
        # W9: the whole card border is an 8px resize strip (8 directions) —
        # press/move/release on the plate drive the border drag, plain
        # moves update the hover cursor. Same clamp + re-pin idiom as W8.
        try:
            from PySide6.QtCore import QEvent

            _watched_content = getattr(self, "_content", None)
            if event.type() == QEvent.Type.ChildAdded and (
                watched is _watched_content
                or (_watched_content is not None and _watched_content.isAncestorOf(watched))
            ):
                # D5: rows/strip/buttons are rebuilt per populate — watch
                # newcomers the same way as the initial subtree.
                try:
                    child = event.child()
                    if child is not None:
                        self._install_subtree_hover_watch(child)
                except Exception:
                    pass
            if watched is getattr(self, "_content", None):
                t = event.type()
                if t == QEvent.Type.Resize:
                    try:
                        self._reposition_source_inset()
                    except Exception:
                        pass
                    try:
                        from tabs.image_gallery.ui.quick_look.helpers import reposition_grip
                        reposition_grip(self)
                    except Exception:
                        pass
                elif t == QEvent.Type.MouseButtonPress:
                    try:
                        from tabs.image_gallery.ui.quick_look.helpers import handle_border_press
                        if handle_border_press(self, event):
                            return True
                    except Exception:
                        pass
                elif t == QEvent.Type.MouseMove:
                    try:
                        from tabs.image_gallery.ui.quick_look.helpers import handle_border_move
                        from tabs.image_gallery.ui.quick_look.helpers import trace_move

                        try:
                            trace_move(self, "plate-move", event.position().toPoint(), watched)
                        except Exception:
                            pass
                        if handle_border_move(self, event):
                            return True
                    except Exception:
                        pass
                elif t == QEvent.Type.MouseButtonRelease:
                    try:
                        from tabs.image_gallery.ui.quick_look.helpers import handle_border_release
                        if handle_border_release(self, event):
                            return True
                    except Exception:
                        pass
                elif t == QEvent.Type.Leave:
                    try:
                        if getattr(self, "_border_drag", None) is None:
                            from tabs.image_gallery.ui.quick_look.helpers import apply_resize_cursor

                            apply_resize_cursor(self, self._content, "plate", None)
                    except Exception:
                        pass
            # D5: landing moves on content descendants (buttons, labels,
            # viewports, bars) never reach the plate filter above, so a
            # border→child jump strands a set plate cursor with no clear
            # path. Recompute the slot from the landing position; hover-only,
            # never consumed (drags keep the existing plate/ring paths).
            try:
                from PySide6.QtCore import QEvent as _QE2

                _content = getattr(self, "_content", None)
                _in_content = (
                    _content is not None
                    and watched is not _content
                    and _content.isAncestorOf(watched)
                )
                if event.type() == _QE2.Type.MouseMove and _in_content:
                    try:
                        from PySide6.QtCore import Qt as _Qt2

                        from tabs.image_gallery.ui.quick_look.helpers import (
                            apply_resize_cursor as _arc2,
                        )
                        from tabs.image_gallery.ui.quick_look.helpers import (
                            nav_button_at as _nba2,
                        )
                        from tabs.image_gallery.ui.quick_look.helpers import (
                            resize_zone_at as _rza2,
                        )

                        if getattr(self, "_border_drag", None) is None:
                            try:
                                _held = event.buttons()
                            except Exception:
                                _held = _Qt2.MouseButton.NoButton
                            if _held == _Qt2.MouseButton.NoButton:
                                try:
                                    _global = event.globalPosition().toPoint()
                                except Exception:
                                    _global = None
                                if _global is not None:
                                    try:
                                        _ov_local = self.mapFromGlobal(_global)
                                    except Exception:
                                        _ov_local = None
                                    try:
                                        _c_local = _content.mapFromGlobal(_global)
                                    except Exception:
                                        _c_local = None
                                    if _ov_local is not None and _c_local is not None:
                                        # W11: nav-arrow rects never show resize.
                                        try:
                                            _nav = _nba2(self, _ov_local)
                                        except Exception:
                                            _nav = None
                                        if _nav is not None:
                                            _arc2(self, _content, "plate", None)
                                        else:
                                            from tabs.image_gallery.ui.quick_look.helpers import (
                                                resize_cursor_for as _rcf2,
                                            )

                                            _arc2(self, _content, "plate", _rcf2(_rza2(_content, _c_local)))
                    except Exception:
                        pass
            except Exception:
                pass
            # Slot frame (IC parity): the preview host is the single
            # laid-out geometry authority; on its Resize mirror the rect
            # onto every layout-external child (GPU canvas, first-frame
            # cover) so the active surface never desyncs. Layout passes
            # that settle the host without a card resize also re-pin the
            # insets anchored to it.
            try:
                from PySide6.QtCore import QEvent as _QE

                if watched is getattr(self, "_preview_host", None) and event.type() == _QE.Type.Resize:
                    try:
                        from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
                            _fit_preview_slot,
                        )
                        _fit_preview_slot(self)
                    except Exception:
                        pass
                    try:
                        self._reposition_source_inset()
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
        return super().eventFilter(watched, event)

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
            if getattr(self, "_border_drag", None) is not None:
                from tabs.image_gallery.ui.quick_look.helpers import handle_border_move
                if handle_border_move(self, event):
                    return
            else:
                from tabs.image_gallery.ui.quick_look.helpers import handle_ring_hover
                handle_ring_hover(self, event)
        except Exception:
            pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        try:
            from tabs.image_gallery.ui.quick_look.helpers import handle_ring_release
            if handle_ring_release(self, event):
                return
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        try:
            if getattr(self, "_border_drag", None) is None:
                from tabs.image_gallery.ui.quick_look.helpers import apply_resize_cursor

                apply_resize_cursor(self, self, "overlay", None)
        except Exception:
            pass
        super().leaveEvent(event)

    def _release_preview_resources(self, *, for_walk: bool = False) -> None:
        """Canvas lifecycle: clear_source() + close store + drop the cover.

        Walk steps (``_populate``) keep both memo dicts so revisits reuse
        the memoized store; hide/close drop everything. Idempotent; no-op
        when the canvas path was never taken.
        """
        try:
            if for_walk:
                from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
                    release_preview_canvas_for_walk,
                )

                release_preview_canvas_for_walk(self)
                return
            from tabs.image_gallery.ui.quick_look.preview_canvas_host import release_preview_canvas

            release_preview_canvas(self)
        except Exception:
            pass

    def _grab_close_frame(self):
        """Grab the last canvas frame for the close cover (None on miss)."""
        try:
            canvas = getattr(self, "_preview_canvas", None)
            if canvas is None:
                return None
            try:
                if not canvas.isVisible():
                    return None
            except Exception:
                pass
            try:
                shot = canvas.grab()
            except Exception:
                return None
            try:
                if shot is None or shot.isNull():
                    return None
            except Exception:
                return None
            return shot
        except Exception:
            return None

    def _plant_close_cover(self, shot) -> None:
        """Freeze *shot* as an opaque raster cover (call while visible).

        The canvas is a NATIVE window: when it unmaps, the compositor has
        nothing for that rect for 1-2 frames (black flash) — no amount of
        backing-store repainting fixes a compositor-level hole (proven:
        synchronous grid pre-paint changed nothing). The cover is a plain
        non-native QLabel: shown + repaint()ed synchronously while the
        overlay is still up, it rides out the unmap and hides with the
        overlay in the same stack. Next show_for drops it via the existing
        "re-cover" path (release drops covers too, so plant AFTER release,
        from a frame grabbed BEFORE it). Fail-open: no frame → no cover.
        """
        try:
            if shot is None:
                return
            try:
                if shot.isNull():
                    return
            except Exception:
                return
            try:
                host = getattr(self, "_preview_host", None)
                if host is None:
                    return
                from PySide6.QtCore import Qt as _Qt
                from PySide6.QtWidgets import QLabel as _QLabel

                cover = _QLabel(host)
                try:
                    cover.setObjectName("quicklook_preview_close_cover")
                except Exception:
                    pass
                try:
                    cover.setAlignment(_Qt.AlignmentFlag.AlignCenter)
                except Exception:
                    pass
                try:
                    cover.setPixmap(shot)
                except Exception:
                    return
                try:
                    cover.setAutoFillBackground(True)
                except Exception:
                    pass
                try:
                    cover.setGeometry(host.rect())
                except Exception:
                    pass
                try:
                    cover.show()
                    cover.raise_()
                    cover.repaint()
                except Exception:
                    pass
                try:
                    self._preview_cover = cover
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass

    def hide(self) -> None:  # noqa: N802
        # Cover-then-release-then-hide, all while still visible: planting in
        # hideEvent would be too late (hidden parent never paints). Covers
        # every path — direct hide(), close() (via its internal hide) and
        # toolkit dismiss() — since all funnel through here.
        try:
            if self.isVisible():
                shot = self._grab_close_frame()
                try:
                    self._release_preview_resources()
                except Exception:
                    pass
                if shot is not None:
                    self._plant_close_cover(shot)
        except Exception:
            pass
        try:
            super().hide()
        except Exception:
            pass

    def hideEvent(self, event) -> None:  # noqa: N802
        try:
            self._release_preview_resources()
        except Exception:
            pass
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Same cover-then-release order as hide(): the default closeEvent
        # hides only at its end, but our release runs first — grab the
        # frame here while the canvas still presents. The internal hide()
        # below finds the canvas already released (grab misses, idempotent
        # release) and keeps the planted cover.
        try:
            if self.isVisible():
                shot = self._grab_close_frame()
                try:
                    self._release_preview_resources()
                except Exception:
                    pass
                if shot is not None:
                    self._plant_close_cover(shot)
        except Exception:
            pass
        try:
            super().closeEvent(event)
        except Exception:
            pass

    def show_for(self, item, owner=None) -> None:
        import time as _time

        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

        _dbg_on = _dbg_enabled()
        _t0 = _time.perf_counter() if _dbg_on else 0.0
        if _dbg_on:
            try:
                _dbg("quick look show_for begin path=%s", getattr(item, "path", item))
            except Exception:
                pass
        if owner is not None:
            # Explicit owner from the caller (see __init__ note): the only
            # re-assignment point besides construction.
            self._owner = owner
        try:
            self._ql_chrome_painted = False
        except Exception:
            pass
        self._current_item = item
        # Modal input grab: never disabled, never mouse-transparent — while
        # visible every press lands here (veil dismiss or card swallow),
        # never in the gallery beneath.
        try:
            self.setEnabled(True)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        except Exception:
            pass
        owner = self._owner
        mode_val = source = series_raw = None
        all_items = None
        try:
            st = getattr(owner, "state", None) if owner is not None else None
            if st is not None:
                mode_val = getattr(st, "mode", None)
                source = getattr(st, "source_path", None)
                series_raw = getattr(st, "series", None)
                all_items = getattr(st, "items", None)
            else:
                mode_val = getattr(owner, "_mode", None) if owner is not None else None
                source = getattr(owner, "_source_path", None) if owner is not None else None
                series_raw = getattr(owner, "_series", None) if owner is not None else None
        except Exception:
            pass
        self._mode = mode_val
        self._source_path = Path(source) if source is not None else None
        if _dbg_on:
            _t_state = _time.perf_counter()
        self._series_items = self._resolve_series(item, series_raw, all_items)
        self._current_idx = 0
        try:
            for i, m in enumerate(self._series_items):
                if Path(getattr(m, "path", "")) == Path(getattr(item, "path", "")):
                    self._current_idx = i
                    break
        except Exception:
            pass
        if _dbg_on:
            _t_series = _time.perf_counter()
            _dbg(
                "quick look show_for phase state-resolve=%.1fms series-resolve=%.1fms n_series=%d",
                (_t_state - _t0) * 1000.0,
                (_t_series - _t_state) * 1000.0,
                len(self._series_items),
            )
            _t_pop = _time.perf_counter()
        self._populate()
        if _dbg_on:
            _t_pop_done = _time.perf_counter()
            _dbg(
                "quick look show_for phase populate=%.1fms total=%.1fms",
                (_t_pop_done - _t_pop) * 1000.0,
                (_t_pop_done - _t0) * 1000.0,
            )
        self.show()
        try:
            self.raise_()
            self.setFocus(Qt.FocusReason.PopupFocusReason)
        except Exception:
            pass
        # Re-assert the modal input grab AFTER show: populate-time rebuilds
        # must never leave the overlay disabled/transparent (a visible but
        # hit-test-invisible veil passes every press to the gallery beneath
        # while looking modal — clicks select behind it, X/veil go dead).
        try:
            self.setEnabled(True)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        except Exception:
            pass
        if _dbg_on:
            try:
                from PySide6.QtWidgets import QApplication as _QA2

                _app2 = _QA2.instance()
                _grab = None
                try:
                    from PySide6.QtWidgets import QWidget as _QW2

                    _grab = _QW2.mouseGrabber()
                except Exception:
                    pass
                _dbg(
                    "quick look show input grabber=%s focus=%s active=%s",
                    type(_grab).__name__ if _grab is not None else None,
                    type(_app2.focusWidget()).__name__ if _app2 is not None and _app2.focusWidget() is not None else None,
                    type(_app2.activeWindow()).__name__ if _app2 is not None and _app2.activeWindow() is not None else None,
                )
            except Exception:
                pass
        if _dbg_on:
            _t_show = _time.perf_counter()
        try:
            self.show_overlay()
        except Exception:
            pass
        if _dbg_on:
            _t_overlay = _time.perf_counter()
            _dbg(
                "quick look show_for phase show=%.1fms show_overlay=%.1fms",
                (_t_show - _t_pop_done) * 1000.0,
                (_t_overlay - _t_show) * 1000.0,
            )
        # Post-show re-pin: base reposition() recenters the card AFTER
        # _populate ran on stale pre-show geometry, and overlay-child nav
        # circles are unknown to it — re-run the pin hooks on live geometry
        # (same idiom as resizeEvent/eventFilter), or arrows/inset/grip keep
        # the previous opening's coordinates on reopen.
        try:
            self._reposition_source_inset()
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.quick_look.helpers import reposition_grip

            reposition_grip(self)
        except Exception:
            pass
        if _dbg_on:
            _dbg(
                "quick look show_for done total=%.1fms repin=%.1fms path=%s",
                (_time.perf_counter() - _t0) * 1000.0,
                (_time.perf_counter() - _t_overlay) * 1000.0,
                getattr(item, "path", item),
            )

    def show_quick_look(self, item, owner=None) -> None:
        self.show_for(item, owner)

    def refresh_artifacts(self, item) -> None:
        try:
            cur = getattr(self, "_current_item", None)
            if cur is None:
                return
            try:
                if Path(getattr(cur, "path", "")) != Path(getattr(item, "path", "")):
                    return
            except Exception:
                if cur is not item:
                    return
            if not self.isVisible():
                return
            self._rebuild_artifacts(item)
        except Exception:
            pass

    def refresh_analysis(self, item) -> None:
        """Rebuild the sidebar AI-analysis block for the open overlay.

        Mirrors ``refresh_artifacts``: no-op when hidden or for another
        item (path-guarded, never copied between items). Called when the
        analysis worker lands so the block needs no reopen. Never raises.
        """
        try:
            cur = getattr(self, "_current_item", None)
            if cur is None:
                return
            try:
                if Path(getattr(cur, "path", "")) != Path(getattr(item, "path", "")):
                    return
            except Exception:
                if cur is not item:
                    return
            if not self.isVisible():
                return
            try:
                from tabs.image_gallery.ui.quick_look.helpers import populate_analysis as _pa_r
                _pa_r(self, item)
            except Exception:
                pass
        except Exception:
            pass

    def refresh_metrics(self, item) -> None:
        """W1 seam — W2 calls this from ``_on_fidelity_ready`` / set-source paths.

        Mirrors ``refresh_artifacts``: rebuilds metrics + meta + brief for the
        open overlay (no reopen needed when fidelity numbers land); no-op when
        hidden or for another item. Never copied between items (path-guarded).
        """
        try:
            cur = getattr(self, "_current_item", None)
            if cur is None:
                return
            try:
                if Path(getattr(cur, "path", "")) != Path(getattr(item, "path", "")):
                    return
            except Exception:
                if cur is not item:
                    return
            if not self.isVisible():
                return
            try:
                self._current_item = item
            except Exception:
                pass
            # Re-read mode from owner state (W2 may have flipped it, e.g.
            # set-as-source → FIDELITY) before rebuilding.
            try:
                owner = getattr(self, "_owner", None)
                st = getattr(owner, "state", None) if owner is not None else None
                if st is not None and getattr(st, "mode", None) is not None:
                    self._mode = st.mode
            except Exception:
                pass
            mode_str = "FIDELITY MODE"
            try:
                mode = getattr(self, "_mode", None)
                if mode is not None:
                    mode_str = str(mode.value) if hasattr(mode, "value") else str(mode)
                mode_str = mode_str.upper()
                if not mode_str.endswith(" MODE"):
                    mode_str = f"{mode_str} MODE"
            except Exception:
                pass
            is_fidelity = "FIDELITY" in mode_str
            try:
                from tabs.image_gallery.ui.quick_look.helpers import (
                    populate_brief,
                    populate_filename_meta,
                )

                populate_filename_meta(self, item, is_fidelity, getattr(self, "_owner", None))
            except Exception:
                pass
            self._rebuild_metrics(item, is_fidelity, mode_str)
            try:
                from tabs.image_gallery.ui.quick_look.helpers import populate_brief as _pb

                _pb(self, item)
            except Exception:
                pass
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802
        """S4 modal dim veil (mockup fill-opacity 0.45), mirroring clean_review.

        ``TopLevelInWindowOverlay`` paints nothing (transparent background),
        so the veil lives here in gallery scope.
        """
        try:
            painter = QPainter(self)
            # No hardcoded QColor (contracts/test_no_hardcoded_qcolor.py):
            # the veil is mockup-specified plain black at an opacity, not
            # a theme color — Qt global black + painter opacity.
            painter.setOpacity(DIM_VEIL_ALPHA / 255.0)
            painter.fillRect(self.rect(), QBrush(Qt.GlobalColor.black))
            painter.end()
        except Exception:
            pass
        try:
            # Chrome painted: a cold-open canvas staged in populate may show.
            if getattr(self, "_preview_canvas_pending", None) is not None:
                try:
                    from tabs.image_gallery.debug import ql_cover as _qlc
                    from tabs.image_gallery.debug import ql_cover_enabled as _qlc_on

                    if _qlc_on():
                        _qlc("overlay paintEvent pending canvas -> reveal")
                except Exception:
                    pass
                from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
                    reveal_pending_preview_canvas,
                )

                reveal_pending_preview_canvas(self)
            self._ql_chrome_painted = True
        except Exception:
            pass
        super().paintEvent(event)

    def refresh_quick_look(self, item) -> None:
        self.refresh_artifacts(item)

    def _resolve_series(self, item, series_raw, all_items=None) -> list:
        """Cluster for *item*: its series, or the ungrouped group.

        Multi-member cluster wins. A singleton cluster (or no cluster at
        all) falls back to the ungrouped group — every item outside a
        multi-member cluster, in folder order — so the strip and the nav
        arrows keep working instead of stranding one lonely thumb. The
        grid shows singles under its UNGROUPED tail the same way.
        """
        if series_raw is None:
            try:
                series_raw = getattr(self._owner, "_series", None) if self._owner is not None else None
            except Exception:
                series_raw = None
        normalized: list[list] = []
        if series_raw:
            for entry in list(series_raw):
                if hasattr(entry, "members"):
                    members = list(getattr(entry, "members") or [])
                elif isinstance(entry, (list, tuple)):
                    members = list(entry)
                else:
                    members = [entry]
                if members:
                    normalized.append(members)
        try:
            cur_path = Path(getattr(item, "path", ""))
        except Exception:
            cur_path = None
            if normalized:
                return normalized[0] if normalized else [item]
            return [item]
        for cl in normalized:
            try:
                if any(Path(getattr(m, "path", "")) == cur_path for m in cl):
                    if len(cl) > 1:
                        return list(cl)
                    break  # singleton cluster → ungrouped group below
            except Exception:
                continue
        try:
            grouped = set()
            for cl in normalized:
                if len(cl) <= 1:
                    continue
                for m in cl:
                    try:
                        grouped.add(Path(getattr(m, "path", "")))
                    except Exception:
                        continue
            pool = list(all_items) if all_items else [item]
            ungrouped = []
            for m in pool:
                try:
                    if Path(getattr(m, "path", "")) not in grouped:
                        ungrouped.append(m)
                except Exception:
                    continue
            if len(ungrouped) > 1:
                return ungrouped
        except Exception:
            pass
        return [item]

    def _populate(self) -> None:
        import time as _time

        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

        _dbg_on = _dbg_enabled()
        _tp0 = _time.perf_counter() if _dbg_on else 0.0
        item = self._current_item
        if item is None:
            return
        # Hydrate the cached analysis BEFORE metrics/artifacts rebuild: their
        # row headers carry the AI axis_notes, so the analysis must be on the
        # item by then (otherwise a cached analysis opens without notes).
        try:
            if getattr(item, "analysis", None) is None:
                _owner = getattr(self, "_owner", None)
                _hydrate = getattr(_owner, "hydrate_cached_analysis", None)
                if callable(_hydrate):
                    _hydrate(item)
        except Exception:
            pass
        # Explicit triage owner for the populate helpers (G3: helpers take
        # owner instead of reading the private attr).
        try:
            _populate_owner = self._owner
        except Exception:
            _populate_owner = None
        # Populate-next lifecycle: walk-step release (memos survive the walk;
        # hide/close take the full release). No fd/memmap leaks across walks;
        # no-op label-only.
        try:
            self._release_preview_resources(for_walk=True)
        except Exception:
            pass
        mode_str = ""
        try:
            if self._mode is not None:
                mode_str = str(self._mode.value) if hasattr(self._mode, "value") else str(self._mode)
            else:
                mode_str = "fidelity"
            mode_str = mode_str.upper()
            if not mode_str.endswith(" MODE"):
                mode_str = f"{mode_str} MODE"
        except Exception:
            mode_str = "FIDELITY MODE"
        is_fidelity = "FIDELITY" in mode_str
        # Delegate populated sections
        if _dbg_on:
            _tp_sections = _time.perf_counter()
        try:
            from tabs.image_gallery.ui.quick_look.helpers import (
                populate_brief,
                populate_filename_meta,
                populate_preview,
                populate_report_header,
                populate_source_inset,
            )
            if _dbg_on:
                _t = _time.perf_counter()
            populate_preview(self, item)
            if _dbg_on:
                _dbg("quick look populate preview=%.1fms path=%s", (_time.perf_counter() - _t) * 1000.0, getattr(item, "path", item))
                _t = _time.perf_counter()
            populate_source_inset(self, item, is_fidelity, _populate_owner)
            if _dbg_on:
                _dbg("quick look populate source-inset=%.1fms", (_time.perf_counter() - _t) * 1000.0)
                _t = _time.perf_counter()
            populate_filename_meta(self, item, is_fidelity, _populate_owner)
            if _dbg_on:
                _dbg("quick look populate filename-meta=%.1fms", (_time.perf_counter() - _t) * 1000.0)
                _t = _time.perf_counter()
            populate_report_header(self, is_fidelity, mode_str)
            if _dbg_on:
                _dbg("quick look populate report-header=%.1fms", (_time.perf_counter() - _t) * 1000.0)
        except Exception:
            pass
        if _dbg_on:
            _t = _time.perf_counter()
        self._rebuild_metrics(item, is_fidelity, mode_str)
        if _dbg_on:
            _dbg("quick look populate metrics=%.1fms", (_time.perf_counter() - _t) * 1000.0)
            _t = _time.perf_counter()
        self._rebuild_artifacts(item)
        if _dbg_on:
            _dbg("quick look populate artifacts=%.1fms", (_time.perf_counter() - _t) * 1000.0)
            _t = _time.perf_counter()
        try:
            from tabs.image_gallery.ui.quick_look.helpers import populate_brief as _pb
            _pb(self, item)
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.quick_look.helpers import populate_analysis as _pa
            _pa(self, item)
        except Exception:
            pass
        if _dbg_on:
            _dbg("quick look populate brief=%.1fms", (_time.perf_counter() - _t) * 1000.0)
            _t = _time.perf_counter()
        self._rebuild_strip()
        if _dbg_on:
            _dbg(
                "quick look populate strip=%.1fms n_series=%d n_thumbs=%d total_populate=%.1fms",
                (_time.perf_counter() - _t) * 1000.0,
                len(self._series_items),
                len(getattr(self, "_strip_buttons", [])),
                (_time.perf_counter() - _tp0) * 1000.0,
            )
        try:
            has_series = len(self._series_items) > 1
            self._prev_btn.setEnabled(bool(has_series))
            self._next_btn.setEnabled(bool(has_series))
        except Exception:
            pass
        try:
            self._set_source_btn.setVisible(bool(is_fidelity))
        except Exception:
            pass
        try:
            rejected = bool(getattr(item, "rejected", False))
            if callable(_set_colored_text):
                _set_colored_text(self._reject_btn, "Restore" if rejected else "✕ Reject", getattr(self, "_reject_text_color", None))
        except Exception:
            pass
        try:
            _cmp = getattr(self, "_compare_btn", None)
            if _cmp is not None:
                _cmp.setEnabled(True)
            _mlt = getattr(self, "_multi_btn", None)
            if _mlt is not None:
                _mlt.setEnabled(True)
        except Exception:
            pass
        # W4 item 6: best-effort nav pin after populate (resizeEvent re-pins
        # once live geometry lands).
        try:
            from tabs.image_gallery.ui.quick_look.helpers import reposition_nav_buttons
            reposition_nav_buttons(self)
        except Exception:
            pass
        # W8: pin the resize grip with the other absolute card children
        # (the _content Resize filter re-pins on every later resize).
        try:
            from tabs.image_gallery.ui.quick_look.helpers import reposition_grip
            reposition_grip(self)
        except Exception:
            pass
        # Modal stacking: stay above window siblings (toasts/flyouts) while
        # visible — a popup grab (card menu) still wins, by Qt design.
        try:
            if self.isVisible():
                self.raise_()
        except Exception:
            pass

    def _rebuild_metrics(self, item, is_fidelity: bool, mode_str: str) -> None:
        try:
            from tabs.image_gallery.ui.quick_look.metrics import rebuild_metrics
            rebuild_metrics(self, item, is_fidelity, mode_str)
        except Exception:
            pass

    def _rebuild_artifacts(self, item) -> None:
        try:
            from tabs.image_gallery.ui.quick_look.artifacts import rebuild_artifacts
            rebuild_artifacts(self, item)
        except Exception:
            pass

    def _ssim_subline(self, item) -> str:
        try:
            from tabs.image_gallery.ui.quick_look.metrics import ssim_subline
            return ssim_subline(self, item)
        except Exception:
            return ""

    def _rebuild_strip(self) -> None:
        try:
            from tabs.image_gallery.ui.quick_look.strip import rebuild_strip
            rebuild_strip(self)
        except Exception:
            pass

    def _walk(self, delta: int) -> None:
        if not self._series_items or len(self._series_items) <= 1:
            return
        n = len(self._series_items)
        self._current_idx = (self._current_idx + delta) % n
        try:
            self._current_item = self._series_items[self._current_idx]
        except Exception:
            return
        self._populate()

    def _on_compare(self) -> None:
        if self._current_item is None:
            return
        # No compareRequested.emit here: the direct path below already sets
        # selection {p} and runs carry_selected, and the only subscriber
        # (on_quick_compare) would run carry_selected a SECOND time
        # (double ImageCarryService.begin). on_quick_compare stays for the
        # _on_multi path, which relies on it for the carry step.
        try:
            owner = self._owner
            if owner is not None and hasattr(owner, "state"):
                try:
                    # G3 dispatch-only: narrow to {p} via controller dispatch
                    # when available; storeless fallback mirrors via setattr.
                    p = Path(getattr(self._current_item, "path", ""))
                    setter = getattr(owner, "set_selection", None)
                    if callable(setter):
                        setter([p])
                    else:
                        st = owner.state
                        if hasattr(st, "selected_paths"):
                            setattr(st, "selected_paths", {p})
                            if hasattr(st, "selected_order"):
                                setattr(st, "selected_order", [p])
                except Exception:
                    pass
                from tabs.image_gallery.use_cases import carry as _carry
                _carry.carry_selected(owner)
        except Exception:
            pass
        # W12-A: Compare navigates away (carry flow) — dismiss the overlay.
        # Reject / Set as source stay open (triage continues); X still closes.
        try:
            self.hide()
        except Exception:
            pass

    def _on_multi(self) -> None:
        if self._current_item is None:
            return
        try:
            owner = self._owner
            p = Path(getattr(self._current_item, "path", ""))
            if owner is not None and hasattr(owner, "state"):
                # G3 dispatch-only: merge-add via controller dispatch when
                # available; storeless fallback keeps the verbatim merge.
                setter = getattr(owner, "set_selection", None)
                if callable(setter):
                    try:
                        cur = list(getattr(owner.state, "selected_paths", None) or [])
                        merged: list = []
                        seen: set = set()
                        for cand in list(cur) + [p]:
                            try:
                                key = str(cand)
                            except Exception:
                                continue
                            if key not in seen:
                                seen.add(key)
                                merged.append(cand)
                        setter(merged)
                    except Exception:
                        pass
                else:
                    st = owner.state
                    if hasattr(st, "selected_paths"):
                        try:
                            st.selected_paths.add(p)
                        except Exception:
                            try:
                                setattr(st, "selected_paths", {p})
                            except Exception:
                                pass
                        try:
                            if hasattr(st, "selected_order") and p not in st.selected_order:
                                st.selected_order.append(p)
                        except Exception:
                            pass
                try:
                    w = getattr(owner, "widget", None) or owner
                    if hasattr(w, "_grid_view"):
                        w._grid_view.apply_selection(getattr(owner.state, "selected_paths", {p}))
                except Exception:
                    pass
            self.compareRequested.emit(p)
        except Exception:
            pass
        # W12-A: verified in code that _on_multi enters the compare flow
        # (compareRequested -> on_quick_compare -> carry_selected ->
        # ImageCarryService.begin), so it dismisses like Compare. Reject /
        # Set as source stay open (triage continues); X still closes.
        try:
            self.hide()
        except Exception:
            pass

    def _on_analyze(self) -> None:
        """Trigger AI analysis for the currently viewed item (sidebar button).

        A finished analysis re-runs forced (``reanalyze_item_by_path``,
        cache bypassed); otherwise delegates to ``analyze_item_by_path``.
        The block shows the PENDING line immediately and refresh_analysis
        fills it in when the worker lands. Owners without the hook (bare
        test doubles) are a silent no-op. Never raises.
        """
        try:
            item = getattr(self, "_current_item", None)
            if item is None:
                return
            owner = getattr(self, "_owner", None)
            try:
                _st = getattr(item, "analysis_status", None)
                _st_val = str(getattr(_st, "value", _st) or "")
            except Exception:
                _st_val = ""
            fn = None
            if _st_val == "done" and getattr(item, "analysis", None) is not None:
                fn = getattr(owner, "reanalyze_item_by_path", None)
            if not callable(fn):
                fn = getattr(owner, "analyze_item_by_path", None)
            if not callable(fn):
                return
            fn(Path(getattr(item, "path", "")))
        except Exception:
            return
        try:
            from tabs.image_gallery.ui.quick_look.helpers import populate_analysis as _pa_a
            _pa_a(self, item)
        except Exception:
            pass

    def _on_reject(self) -> None:
        if self._current_item is None:
            return
        try:
            p = Path(getattr(self._current_item, "path", ""))
            owner = self._owner
            if owner is not None:
                try:
                    from tabs.image_gallery.use_cases import triage as _triage
                    _triage.toggle_reject(owner, p)
                except Exception:
                    try:
                        cur = bool(getattr(self._current_item, "rejected", False))
                        self._current_item.rejected = not cur
                    except Exception:
                        pass
                try:
                    w = getattr(owner, "widget", None) or owner
                    if hasattr(w, "refresh_card"):
                        w.refresh_card(self._current_item)
                    if hasattr(w, "set_triage"):
                        st = getattr(owner, "state", None)
                        if st is not None:
                            rejected_n = sum(1 for it in getattr(st, "items", []) if bool(getattr(it, "rejected", False)))
                            try:
                                w.stats_strip.set_rejected_count(rejected_n)
                            except Exception:
                                pass
                except Exception:
                    pass
            # No rejectToggled.emit here: _on_reject already flipped the flag
            # above, and the only subscriber (on_quick_reject, wired in
            # quick_look_hooks.show_quick_look) would flip it BACK plus run a
            # second full show_for (~300ms of redundant re-populate). External
            # reject triggers (card menu, hover capsule) still reach the open
            # overlay via on_quick_reject — that path is untouched.
            self._refresh_triage_state()  # W12-A: Reject stays open — triage continues.
        except Exception:
            pass

    def _refresh_triage_state(self) -> None:
        """Light refresh after a triage flag flip (reject/unreject).

        A full ``_populate()`` rebuilds the preview pipeline (TileStore
        stream + pyramid, ~1s per 5K file) — pure waste when only the
        rejected flag changed. Refresh just the flag-dependent chrome:
        reject label, brief and strip dim. Preview, metrics, artifacts
        and report stay untouched.
        """
        item = self._current_item
        if item is None:
            return
        try:
            rejected = bool(getattr(item, "rejected", False))
            if callable(_set_colored_text):
                _set_colored_text(self._reject_btn, "Restore" if rejected else "✕ Reject", getattr(self, "_reject_text_color", None))
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.quick_look.helpers import populate_brief as _pb

            _pb(self, item)
        except Exception:
            pass
        try:
            self._rebuild_strip()
        except Exception:
            pass

    def _on_delete(self) -> None:
        """Remove the current item from the grid (file on disk stays).

        Same semantics as the card menu "Remove from view"
        (``triage.remove_from_grid``). After removal the overlay advances
        to the next series item; the last item dismisses the overlay.
        """
        if self._current_item is None:
            return
        try:
            p = Path(getattr(self._current_item, "path", ""))
            owner = self._owner
            if owner is not None:
                try:
                    from tabs.image_gallery.use_cases import triage as _triage

                    _triage.remove_from_grid(owner, p)
                except Exception:
                    pass
            try:
                self._series_items = [
                    m
                    for m in (self._series_items or [])
                    if Path(getattr(m, "path", "")) != p
                ]
            except Exception:
                self._series_items = []
            if not self._series_items:
                try:
                    self.hide()
                except Exception:
                    pass
                return
            try:
                self._current_idx = min(self._current_idx, len(self._series_items) - 1)
                self._current_item = self._series_items[self._current_idx]
            except Exception:
                return
            self._populate()
        except Exception:
            pass

    def _on_set_source(self) -> None:
        if self._current_item is None:
            return
        try:
            p = Path(getattr(self._current_item, "path", ""))
            owner = self._owner
            new_mode = None
            if owner is not None:
                try:
                    st = getattr(owner, "state", None)
                    if st is not None:
                        # G3 dispatch-only seam: prefer controller.set_source
                        # (added by G1) when available; absent on this base,
                        # so mirror locally until the seam lands.
                        # TODO(G1): route via controller.set_source(p).
                        set_source = getattr(owner, "set_source", None)
                        if callable(set_source):
                            try:
                                set_source(p)
                            except Exception:
                                pass
                        else:
                            setattr(st, "source_path", p)
                        # P0-6: re-run mode selection so the chip flips to
                        # FIDELITY (a source hub implies fidelity mode).
                        try:
                            from tabs.image_gallery.services.mode import select_mode

                            new_mode = select_mode(
                                getattr(st, "series", None),
                                getattr(st, "items", None),
                                p,
                            )
                            st.mode = new_mode
                        except Exception:
                            new_mode = None
                    w = getattr(owner, "widget", None) or owner
                    if hasattr(w, "_source_path"):
                        w._source_path = p
                    if hasattr(w, "stats_strip"):
                        try:
                            mode = new_mode
                            if mode is None:
                                mode = getattr(st, "mode", None) if st is not None else getattr(w, "_mode", None)
                            mode_name = getattr(mode, "value", mode) or "fidelity"
                            w.stats_strip.set_mode(str(mode_name), p)
                        except Exception:
                            pass
                except Exception:
                    pass
            self._source_path = p
            if new_mode is not None:
                self._mode = new_mode
            self.setSource.emit(p)
            self._populate()  # W12-A: Set as source stays open — triage continues.
        except Exception:
            pass

    def keyPressEvent(self, event) -> None:  # noqa: N802
        k = event.key()
        # Esc closes via the toolkit base (close_on_escape=True); ←→ still
        # walk the series here.
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            delta = -1 if k == Qt.Key.Key_Left else 1
            self._walk(delta)
            event.accept()
            return
        super().keyPressEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        # Matches the content floor (1040x680 for three artifact rows).
        return QSize(scaled_px(1040), scaled_px(680))
