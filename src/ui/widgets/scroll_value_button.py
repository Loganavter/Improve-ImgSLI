"""Generic scroll-driven numeric control button.

A single icon region when idle, an icon+numeric-value split while hovered,
a transient flyout mirroring the value during scroll, and an always-visible
bottom underline (via the toolkit's built-in ``show_underline``/
``setUnderlineColor`` API) showing an associated color (e.g. divider/guide
color).

Used for divider width, magnifier-divider width, and magnifier-guides width
controls across multi_compare and image_compare toolbars.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QWidget
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import (
    BaseFlyout,
    Button,
    ButtonRegion,
    ButtonRow,
    VerticalSplit,
)

from ui.icon_manager import get_app_icon
from ui.theming import resolve_theme_color

_FLYOUT_HIDE_MS = 700
_WIDTH = 36
_HEIGHT = 36
_RADIUS = 6


class _ScrollValueFlyout(BaseFlyout):
    """Transient popup mirroring the current value above the button."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFixedSize(22, 20)
        self.add_widget(self._label)

    def show_value(self, text: str, icon=None, anchor: QWidget | None = None) -> None:
        if icon is not None:
            self._label.setPixmap(icon.pixmap(16, 16))
            self._label.setText("")
        else:
            self._label.clear()
            self._label.setText(text)
        if anchor is not None:
            self.show_aligned(
                anchor,
                anchor_point="top-center",
                flyout_point="bottom-center",
                offset=6,
            )
        else:
            self.show()


class ScrollValueButton(Button):
    """Scroll-driven numeric control (min_value-max_value) with hover split & flyout.

    Optionally treats ``min_value`` as a "hidden" state, shown with
    ``zero_icon`` instead of the digit "0" (e.g. divider width 0 == divider
    hidden). Pass ``zero_icon=None`` (the default) to just display "0".
    """

    valueChanged = Signal(int)

    _GROUP = "scroll_value"

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        icon=None,
        toggle: bool = False,
        min_value: int = 0,
        max_value: int = 10,
        start: int = 0,
        zero_icon=None,
        **kwargs,
    ) -> None:
        self._min_value = int(min_value)
        self._max_value = int(max_value)
        self._value = max(self._min_value, min(self._max_value, int(start)))
        if isinstance(icon, (tuple, list)):
            self._icon_normal = icon[0]
            self._icon_checked = icon[1] if len(icon) >= 2 else icon[0]
        else:
            self._icon_normal = icon
            self._icon_checked = icon
        self._toggle_enabled = bool(toggle)
        self._zero_icon = zero_icon
        self._saved_value: int | None = None
        self._hovered_split = False
        self._underline_visible = False
        self._underline_qcolor = None
        self._flyout: _ScrollValueFlyout | None = None
        self._flyout_hide_timer = QTimer()
        self._flyout_hide_timer.setSingleShot(True)
        self._flyout_hide_timer.timeout.connect(self._hide_flyout)

        regions, split = self._build_regions()
        super().__init__(
            regions=regions,
            split=split,
            toggle=self._toggle_enabled,
            size=(_WIDTH, _HEIGHT),
            corner_radius=_RADIUS,
            content_padding=(0.0, 2.0, 0.0, 2.0),
            variant="default",
            parent=parent,
            **kwargs,
        )
        # Button.__init__ sets self._show_underline directly (bypassing our
        # setShowUnderline override), so a show_underline=True kwarg would
        # otherwise be silently lost the first time _sync_regions() reasserts
        # our (still-False) shadow copy on the first hover/scroll.
        self._underline_visible = bool(getattr(self, "_show_underline", False))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # RowsContent (used for the "value" region's digit) defaults to
        # splitting the region rect by row.ratio and top-aligning each row;
        # with a single row that leaves it stuck in the top half of the
        # region. compact=True instead centers the single row vertically
        # across the whole region rect, like plain text= used to.
        self._rows_compact = True

    # ---------- underline (re-applied after every region rebuild, see _sync_regions) ----------

    def setShowUnderline(self, value: bool) -> None:
        self._underline_visible = bool(value)
        super().setShowUnderline(value)

    def setUnderlineColor(self, color) -> None:
        self._underline_qcolor = color
        super().setUnderlineColor(color)

    # ---------- backward-compat value API ----------

    def get_value(self) -> int:
        return self._value

    def set_value(self, value: int, emit: bool = True) -> None:
        clamped = max(self._min_value, min(self._max_value, int(value)))
        if clamped == self._value:
            return
        self._value = clamped
        self._sync_regions()
        if emit:
            self.valueChanged.emit(clamped)

    # ---------- saved-value memory (restore previous width after hide/show) ----------

    def get_saved_value(self) -> int | None:
        return self._saved_value

    def set_saved_value(self, value: int | None) -> None:
        self._saved_value = None if value is None else int(value)

    def restore_saved_value(self) -> int | None:
        value = self._saved_value
        self._saved_value = None
        return value

    # ---------- hover: single region idle, icon+value split on hover ----------

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._set_hover_split(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._set_hover_split(False)
        self._hide_flyout()

    def _set_hover_split(self, active: bool) -> None:
        if active == self._hovered_split:
            return
        self._hovered_split = active
        self._sync_regions()

    # ---------- wheel-driven value stepping ----------

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if not delta:
            super().wheelEvent(event)
            return
        event.accept()
        step = 1 if delta > 0 else -1
        new_value = max(self._min_value, min(self._max_value, self._value + step))
        self.set_value(new_value)
        self._show_flyout()

    # ---------- regions ----------

    def _sync_regions(self) -> None:
        regions, split = self._build_regions()
        self.set_regions(regions, split=split)
        # set_regions() rebuilds the button's internal region/paint state from
        # scratch, which drops any previously applied underline visibility/color.
        # Re-assert our last known desired state so hover/scroll/value changes
        # can't silently erase the divider-color indicator.
        super().setShowUnderline(self._underline_visible)
        if self._underline_qcolor is not None:
            super().setUnderlineColor(self._underline_qcolor)

    def _is_at_zero(self) -> bool:
        return self._zero_icon is not None and self._value <= self._min_value

    def _toggle_bg_kwargs(self) -> dict:
        theme_manager = ThemeManager.get_instance()
        return {
            "override_bg_color": resolve_theme_color(
                theme_manager, "button.toggle.background.normal"
            ),
        }

    def _icon_region_id(self) -> str:
        # A toggle=True region must be named "_main" — the toolkit's click
        # handler (events.py) only updates isChecked()/emits toggled() and
        # the base Button._checked state for the region literally named
        # "_main", regardless of which region the split layout renders it in.
        return "_main" if self._toggle_enabled else "icon"

    def _icon_region_icon(self):
        return (
            (self._icon_normal, self._icon_checked)
            if self._toggle_enabled
            else self._icon_normal
        )

    def _build_regions(self) -> tuple[list[ButtonRegion], VerticalSplit]:
        toggle_kwargs = self._toggle_bg_kwargs()
        icon_region_id = self._icon_region_id()
        if not self._hovered_split:
            regions = [
                ButtonRegion(
                    id=icon_region_id,
                    icon=self._icon_region_icon(),
                    icon_size_px=20,
                    variant="default",
                    group=self._GROUP,
                    toggle=self._toggle_enabled,
                    **toggle_kwargs,
                ),
            ]
            return regions, VerticalSplit()

        # Per-region corner_radii is intentionally omitted: the button-level
        # corner_radius=_RADIUS (see __init__) already produces a seamless
        # capsule automatically (rounded outer ends, square inner seam) via
        # the toolkit's outer-clip contract, and stays in sync with the
        # underline arc radius, which reads the same button-level radius.
        icon_region = ButtonRegion(
            id=icon_region_id,
            icon=self._icon_region_icon(),
            icon_size_px=20,
            weight=1.1,
            variant="default",
            group=self._GROUP,
            toggle=self._toggle_enabled,
            **toggle_kwargs,
        )
        if self._is_at_zero():
            value_region = ButtonRegion(
                id="value",
                icon=self._zero_icon,
                icon_size_px=13,
                weight=0.9,
                variant="default",
                group=self._GROUP,
                **toggle_kwargs,
            )
        else:
            value_region = ButtonRegion(
                id="value",
                rows=[ButtonRow(text=str(self._value), size=12)],
                weight=0.9,
                variant="default",
                group=self._GROUP,
                **toggle_kwargs,
            )
        # Bottom breathing room from the underline is reserved via the
        # button-level bottom-only content_padding (see __init__) rather
        # than a spacer region.
        return [icon_region, value_region], VerticalSplit()

    # ---------- flyout ----------

    def _show_flyout(self) -> None:
        if self._flyout is None:
            self._flyout = _ScrollValueFlyout(self.window())
        if self._is_at_zero():
            self._flyout.show_value("", icon=get_app_icon(self._zero_icon), anchor=self)
        else:
            self._flyout.show_value(str(self._value), anchor=self)
        self._flyout_hide_timer.start(_FLYOUT_HIDE_MS)

    def _hide_flyout(self) -> None:
        self._flyout_hide_timer.stop()
        if self._flyout is not None:
            self._flyout.hide()
