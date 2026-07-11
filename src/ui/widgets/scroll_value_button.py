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

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QWidget
from sli_ui_toolkit.widgets import (
    BaseFlyout,
    Button,
    ButtonRegion,
    ButtonRow,
    VerticalSplit,
)

from ui.icon_manager import get_app_icon

logger = logging.getLogger("ImproveImgSLI")

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
            self._svb_icon_normal = icon[0]
            self._svb_icon_checked = icon[1] if len(icon) >= 2 else icon[0]
        else:
            self._svb_icon_normal = icon
            self._svb_icon_checked = icon
        self._toggle_enabled = bool(toggle)
        # Mirrors isChecked(), tracked by hand: _build_regions() (and thus
        # _icon_region_icon()) runs once before super().__init__() below,
        # when Button's own internal state (isChecked() reads
        # self._region_states, set up by Button.__init__) doesn't exist yet.
        self._is_checked = False
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
        if self._toggle_enabled:
            self.regionClicked.connect(self._on_region_clicked)
            # A click landing directly on the icon region ("_main") is
            # handled entirely inside the toolkit's own click path — it flips
            # "_main"'s checked state and emits toggled() without ever going
            # through our setChecked() override below, so the "value" region
            # would be left out of sync in that one case. Catch it here too.
            self.toggled.connect(self._on_native_toggled)
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

    # ---------- checked state (kept in sync with both regions, even when the
    # caller suppresses the toggled signal) ----------

    def setChecked(self, checked: bool, emit_signal: bool = True) -> None:
        # External state sync (e.g. divider/toolbar.py's sync_toolbar_state,
        # presenter.py's viewport-change handler) always calls this with
        # emit_signal=False to avoid a feedback loop, which means the
        # `toggled` signal never fires for that path — so the rebuild below
        # is done unconditionally here rather than from a toggled.connect.
        # A full _sync_regions() (not just setRegionChecked) is required:
        # the icon region's static icon= field itself needs to switch to
        # _icon_checked/_icon_normal (see _icon_region_icon), and only
        # _sync_regions() -> _build_regions() recomputes that.
        self._is_checked = bool(checked)
        super().setChecked(checked, emit_signal=emit_signal)
        self._sync_regions()

    def _on_native_toggled(self, checked: bool) -> None:
        # A click landing directly on the icon region ("_main") is handled
        # entirely inside the toolkit's own click path (see the comment at
        # the toggled.connect above) — it never goes through our
        # setChecked() override, so _is_checked needs updating here too.
        self._is_checked = bool(checked)
        self._sync_regions()

    def _sync_region_checked_state(self, checked: bool) -> None:
        if not self._toggle_enabled:
            return
        # `group=` (see _build_regions) only mirrors hover/press across
        # regions, not the toggle/CHECKED state, so both the icon region
        # (whose icon= tuple depends on it) and the split "value" region
        # (whose darkened background depends on it) are asserted explicitly
        # rather than trusting that they already picked it up.
        self.setRegionChecked(self._icon_region_id(), checked)
        if self._hovered_split:
            self.setRegionChecked("value", checked)

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

    # ---------- click: value region (hover split) also toggles orientation ----------

    def _on_region_clicked(self, region_id: str) -> None:
        # When hovered, the button splits into an "icon" region (toggle=True,
        # named "_main") and a non-toggle "value" region showing the digit.
        # A left click landing on the value region would otherwise do
        # nothing, unlike the plain single-region toggle button used in
        # beginner mode. Mirror that behavior here.
        if region_id == "value":
            self.setChecked(not self.isChecked())

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
        # set_regions() rebuilds region runtime state from scratch too (new
        # ButtonRegion objects), so re-assert checked here as well — this is
        # what makes the "value" region already show as checked/darkened the
        # moment it first appears on hover, instead of only from the next
        # setChecked() call.
        self._sync_region_checked_state(self.isChecked())

    def _is_at_zero(self) -> bool:
        return self._zero_icon is not None and self._value <= self._min_value

    def _icon_region_id(self) -> str:
        # A toggle=True region must be named "_main" — the toolkit's click
        # handler (events.py) only updates isChecked()/emits toggled() and
        # the base Button._checked state for the region literally named
        # "_main", regardless of which region the split layout renders it in.
        return "_main" if self._toggle_enabled else "icon"

    def _icon_region_icon(self):
        # The (unchecked, checked) icon-tuple convenience documented for
        # Button's own icon= constructor kwarg is Button-level sugar around
        # its single implicit "_main" region — it is not implemented for
        # ButtonRegion.icon when regions= is passed directly (as we always
        # do here), so a tuple placed there is never unpacked/switched by
        # the toolkit itself. Do the checked -> icon selection by hand,
        # baked into whichever single icon we hand to the region.
        #
        # These are stored as self._svb_icon_normal/_svb_icon_checked (not
        # self._icon_normal/_icon_checked) because Button.__init__ parses
        # its own icon= kwarg into attributes of that exact name for its
        # built-in tuple convenience; since we never forward icon= to
        # super().__init__() (we consume it ourselves), Button.__init__
        # still runs with icon=None and was clobbering ours right after
        # __init__ set them, making every rebuild after construction use a
        # None checked-icon.
        if not self._toggle_enabled:
            return self._svb_icon_normal
        # isChecked() itself isn't used here: it reads Button's internal
        # _region_states, which doesn't exist yet the first time this runs
        # (from _build_regions() in __init__, before super().__init__()).
        return self._svb_icon_checked if self._is_checked else self._svb_icon_normal

    def _build_regions(self) -> tuple[list[ButtonRegion], VerticalSplit]:
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
        )
        if self._is_at_zero():
            value_region = ButtonRegion(
                id="value",
                icon=self._zero_icon,
                icon_size_px=13,
                weight=0.9,
                variant="default",
                group=self._GROUP,
            )
        else:
            value_region = ButtonRegion(
                id="value",
                rows=[ButtonRow(text=str(self._value), size=12)],
                weight=0.9,
                variant="default",
                group=self._GROUP,
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
