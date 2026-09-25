"""Stage 2 S4 quick look — TopLevelInWindowOverlay with two-panel layout.
Audit-Meta: pattern=thin-owner reason="thin owner delegating to ui/quick_look/* helpers,bars,histograms,source_inset,metrics,artifacts,strip"

Left: large preview (pixmap, source inset for fidelity mode, sharpness-crop inset)
     + prev/next walk the series (←→).
Right: metric bars per mode (SSIM/sharpness/exposure), artifact rows with
       mini-visualizations (stub), series strip (SOURCE/viewing/pending/rejected
       thumbs clickable), bottom bar buttons.
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
        _load_preview_pixmap,
        _set_colored_text,
        _source_dimensions,
        _theme_color,
        _thumb_pixmap,
        _token_color,
    )
except Exception:
    _load_preview_pixmap = _thumb_pixmap = _theme_color = _token_color = _set_colored_text = _source_dimensions = None  # type: ignore
try:
    from tabs.image_gallery.ui.quick_look.source_inset import _SourceInsetHost
except Exception:
    _SourceInsetHost = QWidget  # type: ignore
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
        # Close policy: veil click and the X button close; Esc/minimize/
        # focus loss stay pinned (W11 rationale kept for keyboard/focus —
        # only the W6/W11 background-click ban is reversed: a veil click no
        # longer traps the user, and no report state is lost — triage state
        # lives in the controller, reopen re-resolves it).
        # close_on_background stays False so the base class never dismisses
        # on its own: the veil dismiss below is explicit (ring presses
        # return earlier, children eat their own presses).
        super().__init__(parent, close_on_background=False, close_on_escape=False, close_on_deactivate=False)
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
        # W8: the resizable card plate is a plain child widget — its own
        # resizes never reach the overlay's resizeEvent, so watch it and
        # re-run the pin hooks (nav circles, source inset, resize grip).
        try:
            content = getattr(self, "_content", None)
            if content is not None:
                content.installEventFilter(self)
        except Exception:
            pass

    def _reposition_source_inset(self) -> None:
        try:
            from tabs.image_gallery.ui.quick_look.source_inset import reposition_source_inset
            reposition_source_inset(self)
        except Exception:
            pass
        # W4 item 6: nav circles are absolute card children — re-pin with
        # every resize (like the source inset).
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
        except Exception:
            pass
        return super().eventFilter(watched, event)

    # W10: the 8px ring OUTSIDE the card (on the veil) is owned here at
    # overlay level — the W9 plate filter only sees the inner edge. Ring
    # drags share the _border_drag tuple + clamp/cursor helpers with the
    # plate handlers. Plain veil clicks dismiss the overlay (reverses the
    # W6/W11 background-click ban; Esc/deactivate stay pinned). W11: ring
    # and plate presses inside either nav-arrow rect walk the series via
    # the helpers (arrows never start a drag).
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
        try:
            self.dismiss()
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
            self._owner = owner
        self._current_item = item
        owner = self._owner
        mode_val = source = series_raw = None
        try:
            st = getattr(owner, "state", None) if owner is not None else None
            if st is not None:
                mode_val = getattr(st, "mode", None)
                source = getattr(st, "source_path", None)
                series_raw = getattr(st, "series", None)
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
        self._series_items = self._resolve_series(item, series_raw)
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
                    populate_crop,
                    populate_filename_meta,
                )

                populate_crop(self, item, is_fidelity)
                populate_filename_meta(self, item, is_fidelity)
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
        super().paintEvent(event)

    def refresh_quick_look(self, item) -> None:
        self.refresh_artifacts(item)

    def _resolve_series(self, item, series_raw) -> list:
        if series_raw is None:
            try:
                series_raw = getattr(self._owner, "_series", None) if self._owner is not None else None
            except Exception:
                series_raw = None
        if not series_raw:
            return [item]
        normalized: list[list] = []
        for entry in list(series_raw):
            if hasattr(entry, "members"):
                members = list(getattr(entry, "members") or [])
            elif isinstance(entry, (list, tuple)):
                members = list(entry)
            else:
                members = [entry]
            if members:
                normalized.append(members)
        if not normalized:
            return [item]
        try:
            cur_path = Path(getattr(item, "path", ""))
        except Exception:
            return normalized[0] if normalized else [item]
        for cl in normalized:
            try:
                if any(Path(getattr(m, "path", "")) == cur_path for m in cl):
                    return list(cl)
            except Exception:
                continue
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
        try:
            self._mode_chip.setText(mode_str)
        except Exception:
            pass
        is_fidelity = "FIDELITY" in mode_str
        # Delegate populated sections
        if _dbg_on:
            _tp_sections = _time.perf_counter()
        try:
            from tabs.image_gallery.ui.quick_look.helpers import (
                populate_brief,
                populate_crop,
                populate_filename_meta,
                populate_preview,
                populate_report_header,
                populate_series_header,
                populate_source_inset,
            )
            if _dbg_on:
                _t = _time.perf_counter()
            populate_preview(self, item)
            if _dbg_on:
                _dbg("quick look populate preview=%.1fms path=%s", (_time.perf_counter() - _t) * 1000.0, getattr(item, "path", item))
                _t = _time.perf_counter()
            populate_source_inset(self, item, is_fidelity)
            if _dbg_on:
                _dbg("quick look populate source-inset=%.1fms", (_time.perf_counter() - _t) * 1000.0)
                _t = _time.perf_counter()
            populate_crop(self, item, is_fidelity)
            if _dbg_on:
                _dbg("quick look populate crop=%.1fms", (_time.perf_counter() - _t) * 1000.0)
                _t = _time.perf_counter()
            populate_filename_meta(self, item, is_fidelity)
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
            from tabs.image_gallery.ui.quick_look.helpers import populate_series_header as _psh, populate_brief as _pb
            _psh(self)
            _pb(self, item)
        except Exception:
            pass
        if _dbg_on:
            _dbg("quick look populate series+brief=%.1fms", (_time.perf_counter() - _t) * 1000.0)
            _t = _time.perf_counter()
        self._rebuild_strip()
        if _dbg_on:
            _dbg(
                "quick look populate strip=%.1fms n_series=%d total_populate=%.1fms",
                (_time.perf_counter() - _t) * 1000.0,
                len(self._series_items),
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
            self._compare_btn.setEnabled(True)
            self._multi_btn.setEnabled(True)
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
                    st = owner.state
                    if hasattr(st, "selected_paths"):
                        st.selected_paths = {Path(getattr(self._current_item, "path", ""))}
                        if hasattr(st, "selected_order"):
                            st.selected_order = [Path(getattr(self._current_item, "path", ""))]
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
                st = owner.state
                if hasattr(st, "selected_paths"):
                    st.selected_paths.add(p)
                    if hasattr(st, "selected_order") and p not in st.selected_order:
                        st.selected_order.append(p)
                try:
                    w = getattr(owner, "widget", None) or owner
                    if hasattr(w, "_grid_view"):
                        w._grid_view.apply_selection(st.selected_paths)
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
            self._populate()  # W12-A: Reject stays open — triage continues.
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
                        st.source_path = p
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
        # W11 pinned policy: Esc NEVER closes (the toolkit base also ignores
        # it with close_on_escape=False) — X is the only close path. ←→
        # still walk the series.
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            delta = -1 if k == Qt.Key.Key_Left else 1
            self._walk(delta)
            event.accept()
            return
        super().keyPressEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(scaled_px(1040), scaled_px(620))
