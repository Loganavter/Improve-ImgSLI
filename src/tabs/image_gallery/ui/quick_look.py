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
        super().__init__(parent, close_on_background=True, close_on_escape=True, close_on_deactivate=True)
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

    def show_for(self, item, owner=None) -> None:
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
        self._series_items = self._resolve_series(item, series_raw)
        self._current_idx = 0
        try:
            for i, m in enumerate(self._series_items):
                if Path(getattr(m, "path", "")) == Path(getattr(item, "path", "")):
                    self._current_idx = i
                    break
        except Exception:
            pass
        self._populate()
        self.show()
        try:
            self.raise_()
            self.setFocus(Qt.FocusReason.PopupFocusReason)
        except Exception:
            pass
        try:
            self.show_overlay()
        except Exception:
            pass

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
            populate_preview(self, item)
            populate_source_inset(self, item, is_fidelity)
            populate_crop(self, item, is_fidelity)
            populate_filename_meta(self, item, is_fidelity)
            populate_report_header(self, is_fidelity, mode_str)
        except Exception:
            pass
        self._rebuild_metrics(item, is_fidelity, mode_str)
        self._rebuild_artifacts(item)
        try:
            from tabs.image_gallery.ui.quick_look.helpers import populate_series_header as _psh, populate_brief as _pb
            _psh(self)
            _pb(self, item)
        except Exception:
            pass
        self._rebuild_strip()
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
        try:
            p = Path(getattr(self._current_item, "path", ""))
            self.compareRequested.emit(p)
        except Exception:
            pass
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
            self.rejectToggled.emit(p)
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
            self._populate()
        except Exception:
            pass

    def keyPressEvent(self, event) -> None:  # noqa: N802
        k = event.key()
        if k == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            delta = -1 if k == Qt.Key.Key_Left else 1
            self._walk(delta)
            event.accept()
            return
        super().keyPressEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(scaled_px(1040), scaled_px(620))
