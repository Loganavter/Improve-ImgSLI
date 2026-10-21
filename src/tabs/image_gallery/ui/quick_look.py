"""Stage 2 S4 quick look — TopLevelInWindowOverlay with two-panel layout.
Audit-Meta: pattern=thin-owner reason="thin owner delegating to ui/quick_look/* helpers,bars,histograms,metrics,artifacts,strip"

Left: large preview (pixmap, source inset for fidelity mode)
     + the ‹/› circles walk the series (prev/next); the keyboard moves the
       strip's ring with ←→ and shows the focused item on Enter
       (quick_look/nav_section.py).
Right: metric bars per mode (SSIM/sharpness/exposure), artifact rows with
       mini-visualizations (stub), filename meta + brief (series note, no
       counts); bottom: full-width series strip (SOURCE/viewing/pending/
       rejected thumbs clickable), bottom bar buttons.
Public toolkit only: TopLevelInWindowOverlay, Button variant="surface",
scaled_px. No setStyleSheet — painter pipeline owns visuals.

Thin-owner split (plan-gallery-split-2026-10-17, Part C2): every method body
lives in ``ui/quick_look/overlay_parts/*.py`` as a plain function taking this
overlay as its first argument (``CODE_PATTERNS.md`` "thin owner + ui/ parts").
The class below keeps same-named one-line delegators so Qt virtual dispatch,
call sites and tests are untouched; module-level names (``DIM_VEIL_ALPHA``,
the helpers/bars/histograms re-exports) stay here for the package shim.
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

from PySide6.QtCore import Qt, Signal, QSize, QPoint, QRect
from PySide6.QtGui import QBrush, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import TopLevelInWindowOverlay

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

# Concern modules: the actual bodies. Imported here so the delegators are a
# single attribute call (no per-event import); each module only defines plain
# functions over the overlay and never imports this file back (no cycle).
from tabs.image_gallery.ui.quick_look.overlay_parts import (
    dispatch as _dispatch,
    filters as _filters,
    input_events as _input_events,
    lifecycle as _lifecycle,
    pinning as _pinning,
    populate as _populate_parts,
    region_select as _region_select,
    show as _show,
    theming as _theming,
)


class QuickLookOverlay(TopLevelInWindowOverlay):
    """S4 quick look overlay — two-panel layout. Thin owner."""

    compareRequested = Signal(object)
    rejectToggled = Signal(object)
    setSource = Signal(object)
    #: LMB region selection finished: (image path, normalized box (l,t,r,b)).
    regionAskRequested = Signal(str, object)

    def __init__(self, parent: QWidget | None = None, owner=None, *, translate=None) -> None:
        # Close policy: veil click, Esc, and the X button close;
        # minimize/focus loss stay pinned. Reverses W6 (background ban) and
        # the W11 Esc ban; no report state is lost — triage state lives in
        # the controller, reopen re-resolves it. close_on_background stays
        # False so the base class never dismisses on its own: the veil
        # dismiss is explicit (ring presses return earlier, children eat
        # their own presses); Esc flows through the base keyPressEvent.
        super().__init__(parent, close_on_background=False, close_on_escape=True, close_on_deactivate=False)
        # Translator seam: ``translate(key, default) -> str`` (or None for the
        # EN defaults). Captured once; ``retranslate()`` refreshes it on a live
        # language switch. Set BEFORE build_overlay_ui so the chrome buttons
        # (Set as source / Reject / Delete) can resolve their keys.
        self._tr = translate
        # G3 dispatch-only: the triage owner (controller) arrives explicitly
        # via __init__/show_for and is stored here. Assigned ONLY from those
        # explicit arguments — never poked from outside, never re-scanned.
        self._owner = owner
        self._current_item = None
        self._series_items: list = []
        self._current_idx: int = 0
        self._mode = None
        self._source_path: Path | None = None
        try:
            from tabs.image_gallery.ui.quick_look.helpers import build_overlay_ui
            build_overlay_ui(self)
        except Exception:
            # Fallback inline minimal if builder fails
            pass
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
        # Region selection (LMB drag over the preview → Ask AI region scope).
        self._region_active = False
        self._region_start_host: QPoint | None = None
        self._region_band = None
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

    # -- child-hover watch + event filters (overlay_parts/filters.py) --------

    def _install_subtree_hover_watch(self, root) -> None:
        _filters._install_subtree_hover_watch(self, root)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        return _filters.eventFilter(self, watched, event)

    # -- pinning: resize re-pins (insets/nav/grip) + size floor --------------

    def _reposition_source_inset(self) -> None:
        _pinning._reposition_source_inset(self)

    def resizeEvent(self, event):  # noqa: N802
        _pinning.resizeEvent(self, event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return _pinning.sizeHint(self)

    # -- region selection (LMB drag over the preview → Ask AI region scope) --
    #       (overlay_parts/region_select.py)

    def _preview_rect_in_overlay(self):
        return _region_select._preview_rect_in_overlay(self)

    def _ensure_region_band(self):
        return _region_select._ensure_region_band(self)

    def _maybe_start_region(self, event) -> bool:
        return _region_select._maybe_start_region(self, event)

    def _update_region(self, event) -> None:
        _region_select._update_region(self, event)

    def _finish_region(self, event) -> None:
        _region_select._finish_region(self, event)

    def region_selection_anchor(self):
        return _region_select.region_selection_anchor(self)

    def hide_region_band(self) -> None:
        _region_select.hide_region_band(self)

    # -- input events (overlay_parts/input_events.py) ------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        _input_events.mousePressEvent(self, event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        _input_events.mouseDoubleClickEvent(self, event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        _input_events.wheelEvent(self, event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        _input_events.contextMenuEvent(self, event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        _input_events.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        _input_events.mouseReleaseEvent(self, event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        _input_events.leaveEvent(self, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        _input_events.keyPressEvent(self, event)

    # -- lifecycle: canvas release + close cover + hide/close ----------------
    #       (overlay_parts/lifecycle.py)

    def _release_preview_resources(self, *, for_walk: bool = False) -> None:
        _lifecycle._release_preview_resources(self, for_walk=for_walk)

    def _grab_close_frame(self):
        return _lifecycle._grab_close_frame(self)

    def _plant_close_cover(self, shot) -> None:
        _lifecycle._plant_close_cover(self, shot)

    def hide(self) -> None:  # noqa: N802
        _lifecycle.hide(self)

    def hideEvent(self, event) -> None:  # noqa: N802
        _lifecycle.hideEvent(self, event)

    def closeEvent(self, event) -> None:  # noqa: N802
        _lifecycle.closeEvent(self, event)

    # -- theming / translation: veil paint + retranslate ---------------------
    #       (overlay_parts/theming.py)

    def _t(self, key: str, default: str) -> str:
        return _theming._t(self, key, default)

    def _mode_str_and_fidelity(self) -> tuple[str, bool]:
        return _theming._mode_str_and_fidelity(self)

    def retranslate(self, translate=None) -> None:
        _theming.retranslate(self, translate)

    def paintEvent(self, event) -> None:  # noqa: N802
        _theming.paintEvent(self, event)

    # -- show / refresh (overlay_parts/show.py) ------------------------------

    def show_for(self, item, owner=None) -> None:
        _show.show_for(self, item, owner)

    def show_quick_look(self, item, owner=None) -> None:
        _show.show_quick_look(self, item, owner)

    def refresh_artifacts(self, item) -> None:
        _show.refresh_artifacts(self, item)

    def refresh_metrics(self, item) -> None:
        _show.refresh_metrics(self, item)

    def refresh_quick_look(self, item) -> None:
        _show.refresh_quick_look(self, item)

    def _rebuild_metrics(self, item, is_fidelity: bool, mode_str: str) -> None:
        _show._rebuild_metrics(self, item, is_fidelity, mode_str)

    def _rebuild_artifacts(self, item) -> None:
        _show._rebuild_artifacts(self, item)

    def _ssim_subline(self, item) -> str:
        return _show._ssim_subline(self, item)

    def _rebuild_strip(self) -> None:
        _show._rebuild_strip(self)

    # -- populate / series resolve / walk (overlay_parts/populate.py) --------

    def _resolve_series(self, item, series_raw, all_items=None) -> list:
        return _populate_parts._resolve_series(self, item, series_raw, all_items)

    def _populate(self) -> None:
        _populate_parts._populate(self)

    def _walk(self, delta: int) -> None:
        _populate_parts._walk(self, delta)

    # -- strip navigation (toolkit rows section; quick_look/nav_section.py) --
    # The section is a plain ToolbarRowsSection over [strip_row, action_bar]:
    # no cursor index, no zone memory, no painted marker, no keyPressEvent
    # fallback here (the focused Button activates itself).

    # -- triage dispatch: bottom-bar buttons (overlay_parts/dispatch.py) -----

    def _on_compare(self) -> None:
        _dispatch._on_compare(self)

    def _on_multi(self) -> None:
        _dispatch._on_multi(self)

    def _on_reject(self) -> None:
        _dispatch._on_reject(self)

    def _refresh_triage_state(self) -> None:
        _dispatch._refresh_triage_state(self)

    def _on_delete(self) -> None:
        _dispatch._on_delete(self)

    def _on_set_source(self) -> None:
        _dispatch._on_set_source(self)
