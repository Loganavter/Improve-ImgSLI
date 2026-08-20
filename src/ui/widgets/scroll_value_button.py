"""Generic scroll-driven numeric control button.

A single icon region when idle, an icon+numeric-value split while hovered,
a transient flyout mirroring the value during scroll, and an always-visible
bottom underline (via the toolkit's built-in ``show_underline``/
``setUnderlineColor`` API) showing an associated color (e.g. divider/guide
color).

Used for divider width, magnifier-divider width, and magnifier-guides width
controls across multi_compare and image_compare toolbars.
Audit-Meta: pattern=state-machine reason="single custom-painted control — painter pipeline owns visuals"
"""

from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import logging

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QLabel, QWidget
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.managers.ui_font import apply_ui_font
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.widgets import (
    BackgroundLayer,
    BadgeLayer,
    BaseFlyout,
    Button,
    ButtonRegion,
    ButtonRow,
    ContentLayer,
    DividerLayer,
    Layer,
    RippleLayer,
    StrikethroughLayer,
    UnderlineLayer,
    VerticalSplit,
)

from ui.icon_manager import get_app_icon

logger = logging.getLogger("ImproveImgSLI")

_FLYOUT_HIDE_MS = 700
_WIDTH = 36
_HEIGHT = 36
_RADIUS = 6

# Padding around the digit inside the small capsule backdrop (see
# _ValueOverUnderlineLayer) — deliberately tight, not the full split region.
_CAPSULE_PAD_X = 5.0
_CAPSULE_PAD_Y = 3.0


class _ValueOverUnderlineLayer(Layer):
    """Repaints the "value" region's digit on top of UnderlineLayer, behind
    a small themed capsule sized to the digit (not the whole split region).

    Reuses the toolkit's own BackgroundLayer color resolution (so the
    capsule fill tracks the button's current state/theme for free) and
    ContentLayer for the digit itself, but draws the capsule shape by hand
    since BackgroundLayer only knows how to fill its full region rect.
    Stateless like the toolkit's own layers — reads the button instance off
    ``ctx.widget`` rather than holding any state itself, so one instance is
    shared across all ScrollValueButtons (see _LAYERS).
    """

    scope = "widget"

    def __init__(self) -> None:
        self._content_layer = ContentLayer()

    def applies(self, ctx) -> bool:
        widget = ctx.widget
        return bool(getattr(widget, "_hovered_split", False)) and not getattr(
            widget, "_is_scrolling", False
        )

    def draw(self, ctx, tm) -> None:
        iter_regions = getattr(ctx.widget, "iter_regions", None)
        if iter_regions is None:
            return
        for scoped_ctx in iter_regions(ctx):
            if scoped_ctx.region_id == "value":
                if not ctx.widget._is_at_zero():
                    self._draw_capsule(scoped_ctx, tm, str(ctx.widget._value))
                self._content_layer.draw(scoped_ctx, tm)
                return

    @staticmethod
    def _clamp_capsule(capsule: QRectF, region_rect: QRectF) -> QRectF:
        """Keep the capsule inside the value region (never over the icon)."""
        return capsule.intersected(region_rect)

    @staticmethod
    def _draw_capsule(scoped_ctx, tm, text: str) -> None:
        backgrounds, _border = BackgroundLayer._resolve(scoped_ctx, tm)
        if not backgrounds:
            return
        font = ui_font(pixel_size=12)
        fm = QFontMetrics(font)
        pad_x = scaled_px(_CAPSULE_PAD_X)
        pad_y = scaled_px(_CAPSULE_PAD_Y)
        width = fm.horizontalAdvance(text) + 2 * pad_x
        height = fm.height() + 2 * pad_y
        center = scoped_ctx.effective_rect.center()
        rect = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)
        # The value split region is narrower/shorter than the digit +
        # padding for multi-digit values; clamp the capsule to the region
        # so it never bleeds into the icon region (ContentLayer clips the
        # digit itself to the same rect — clip_content=True).
        rect = _ValueOverUnderlineLayer._clamp_capsule(
            rect, QRectF(scoped_ctx.effective_rect)
        )

        p = scoped_ctx.painter
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(backgrounds[-1])
        p.drawRoundedRect(rect, height / 2, height / 2)
        p.restore()


# The toolkit's Painter (buttons/painter.py) always runs every region-scoped
# layer (ContentLayer among them) before any widget-scoped layer
# (UnderlineLayer is scope="widget"), regardless of where each sits in this
# list — so simply listing ContentLayer after UnderlineLayer does NOT make
# the digit paint on top; the underline (esp. the thick end of the
# thickness ramp below) still ends up covering it. _ValueOverUnderlineLayer
# below is itself widget-scoped, so its list position *does* control paint
# order relative to UnderlineLayer: it repaints just the "value" region's
# content a second time, after the underline, whenever hover-without-scroll
# should show the digit sitting on top of the line.
_LAYERS = (
    BackgroundLayer(),
    RippleLayer(),
    ContentLayer(),
    BadgeLayer(),
    UnderlineLayer(),
    _ValueOverUnderlineLayer(),
    DividerLayer(),
    StrikethroughLayer(),
)

# The underline's thickness tracks the button's own value (e.g. divider/line
# width), so a thicker configured line reads visually as a thicker indicator
# too: value=1 -> _UNDERLINE_THICKNESS_MIN, value=max_value -> _MAX. value=0
# is the separate "hidden" state (zero_icon) and isn't part of this ramp.
_UNDERLINE_THICKNESS_MIN = 1.0
_UNDERLINE_THICKNESS_MAX = 5.0


class _ScrollValueFlyout(BaseFlyout):
    """Transient popup mirroring the current value above the button."""

    # Without an explicit group this falls into flyout_policy.py's
    # unconfigured "default" bucket, which resolves to the fallback
    # DISMISS_ALL policy -- every wheel-nudge on a ScrollValueButton was
    # closing every other visible flyout, including "pinned" ones like the
    # zoom-percent/info HUD chips (pinned only exempts a flyout from being
    # dismissed by *its own* passive-dismiss paths -- outside click/wheel/
    # deactivate -- not from another flyout's GroupShowPolicy dismiss set
    # naming it, or DISMISS_ALL). Same shape as "slider_hint" below.
    flyout_group = "scroll_value"

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._label = QLabel(self)
        # apply_ui_font (not a bare setFont) so the digit follows font and
        # UiScale changes live — see SliderHintFlyout for the same pattern.
        apply_ui_font(self._label)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Minimum, NOT fixed size: the flyout is cached per button and lives
        # across UiScale changes — a fixed design size computed once at
        # construction stays stale when the factor rises (digit re-resolves
        # its scaled font live, so the text overflows and clips against the
        # panel's rounded corners). A minimum keeps the compact pill for a
        # single digit while letting the sizeHint (scaled text) grow it on
        # every show (show_aligned -> adjustSize), same as SliderHintFlyout.
        self._label.setMinimumSize(scaled_px(22), scaled_px(20))
        self.add_widget(self._label)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._keyboard_focus = False

    def focusInEvent(self, event) -> None:
        reason = event.reason()
        is_kbd = reason not in (Qt.FocusReason.MouseFocusReason, Qt.FocusReason.MenuBarFocusReason)
        # NavigationManager preserve уже форсит, но дублируем для BaseFlyout без Button-логики
        try:
            from sli_ui_toolkit.managers import NavigationManager

            if not is_kbd and NavigationManager.get_instance().last_input_was_keyboard():
                is_kbd = True
        except Exception:
            pass
        self._keyboard_focus = bool(is_kbd)
        self._last_focus_reason = reason
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        self._keyboard_focus = False
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event) -> None:
        # В edit-mode кольцо на флайауте — Esc/Left/Right возвращают на якорь
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def show_value(self, text: str, icon=None, anchor: QWidget | None = None, grab_focus: bool | None = None) -> None:
        if icon is not None:
            self._label.setPixmap(icon.pixmap(scaled_px(16), scaled_px(16)))
            self._label.setText("")
        else:
            self._label.clear()
            self._label.setText(text)
        if anchor is not None:
            # Edit-mode (Enter) → кольцо наверх, wheel-preview → без кражи фокуса
            _grab = grab_focus if grab_focus is not None else False
            # Декларативный side для навигации — flyout визуально выше кнопки
            try:
                self._nav_side = "above"  # type: ignore[attr-defined]
            except Exception:
                pass
            self.show_aligned(
                anchor,
                anchor_point="top-center",
                flyout_point="bottom-center",
                offset=6,
                grab_focus=_grab,
                register_nav_section=_grab,
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
        self._is_scrolling = False
        self._underline_visible = False
        self._underline_qcolor = None
        self._underline_thickness_value: float | None = None
        self._flyout: _ScrollValueFlyout | None = None
        self._flyout_hide_timer = QTimer()
        self._flyout_hide_timer.setSingleShot(True)
        self._flyout_hide_timer.timeout.connect(self._hide_flyout)
        self._keyboard_edit_active = False

        regions, split = self._build_regions()
        super().__init__(
            regions=regions,
            split=split,
            toggle=self._toggle_enabled,
            size=(_WIDTH, _HEIGHT),
            corner_radius=_RADIUS,
            content_padding=(0.0, float(scaled_px(2)), 0.0, float(scaled_px(2))),
            variant="default",
            layers=list(_LAYERS),
            parent=parent,
            **kwargs,
        )
        # Button.__init__ sets self._show_underline directly (bypassing our
        # setShowUnderline override), so a show_underline=True kwarg would
        # otherwise be silently lost the first time _sync_regions() reasserts
        # our (still-False) shadow copy on the first hover/scroll.
        self._underline_visible = bool(getattr(self, "_show_underline", False))
        super().setShowUnderline(self._underline_visible and not self._is_at_zero())
        self.setUnderlineThickness(self._underline_thickness_for_value(self._value))
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

    def setUnderlineThickness(self, thickness: float) -> None:
        self._underline_thickness_value = float(thickness)
        super().setUnderlineThickness(thickness)

    def _underline_thickness_for_value(self, value: int) -> float:
        span = max(1, self._max_value - 1)
        t = (max(1, value) - 1) / span
        t = max(0.0, min(1.0, t))
        return _UNDERLINE_THICKNESS_MIN + t * (_UNDERLINE_THICKNESS_MAX - _UNDERLINE_THICKNESS_MIN)

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
        self.setUnderlineThickness(self._underline_thickness_for_value(clamped))
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
        # Public Button hover seeding (enterEvent → group= mirror) only sees
        # the regions that already exist. Expand to the icon+value capsule
        # first so both siblings share group= when HOVERED is applied.
        self._set_hover_split(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._set_hover_split(False)
        self._hide_flyout()

    def _set_hover_split(self, active: bool) -> None:
        if active == self._hovered_split:
            return
        self._hovered_split = active
        self._sync_regions()

    # ---------- wheel/key-driven value stepping ----------

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if not delta:
            super().wheelEvent(event)
            return
        event.accept()
        self._step_value(1 if delta > 0 else -1)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        # Enter toggles keyboard edit mode — arrows only adjust value after
        # explicit activation, otherwise they navigate (Left/Right → next
        # button, Up/Down → next row). This prevents swallowing navigation
        # without user intent and keeps flyouts open.
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._keyboard_edit_active = not self._keyboard_edit_active
            # Show flyout when entering edit mode so value is visible
            if self._keyboard_edit_active:
                self._show_flyout()
                # Ring only on the button itself — preview flyout is read-only, no ring
                self.setProperty("editActive", True)
                self.style().polish(self)
            else:
                self._hide_flyout()
                self.setProperty("editActive", False)
                self.style().polish(self)
            event.accept()
            self.update()
            return
        if key == Qt.Key.Key_Escape:
            if self._keyboard_edit_active:
                self._keyboard_edit_active = False
                self._hide_flyout()
                self.setProperty("editActive", False)
                self.style().polish(self)
                self.update()
                event.accept()
                return
            # Even when not in edit mode, Escape should hide the preview flyout
            # (e.g. after wheel) and not propagate to close unrelated flyouts
            if self._flyout is not None and self._flyout.isVisible():
                self._hide_flyout()
                event.accept()
                return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
            if not self._keyboard_edit_active:
                # Not in edit mode — let navigation handle it (move focus)
                super().keyPressEvent(event)
                return
            # In edit mode — Up/Right increment, Down/Left decrement
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Right):
                self._step_value(1)
            else:
                self._step_value(-1)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._keyboard_edit_active = False
        super().focusOutEvent(event)

    def _step_value(self, step: int) -> None:
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
        # can't silently erase the divider-color indicator. At the "hidden"
        # value (zero_icon shown instead of a width digit), force it off
        # regardless of the caller's requested state — there's no line to
        # show a color for once it's hidden.
        super().setShowUnderline(self._underline_visible and not self._is_at_zero())
        if self._underline_qcolor is not None:
            super().setUnderlineColor(self._underline_qcolor)
        if self._underline_thickness_value is not None:
            super().setUnderlineThickness(self._underline_thickness_value)
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
                    # group= disables the toolkit's default content clipping;
                    # re-enable so the icon stays inside its own region.
                    clip_content=True,
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
            clip_content=True,
        )
        if self._is_at_zero():
            value_region = ButtonRegion(
                id="value",
                icon=self._zero_icon,
                icon_size_px=13,
                weight=0.9,
                variant="default",
                group=self._GROUP,
                clip_content=True,
            )
        else:
            # While the scroll flyout is showing the value above the button,
            # the digit inside the button itself is suppressed (blank region)
            # so the two aren't both flashing the number at once; it reappears
            # here, drawn over the underline (see _LAYERS ordering above),
            # once hover lingers past the flyout's hide delay with no scroll.
            rows = [] if self._is_scrolling else [ButtonRow(text=str(self._value), size=12)]
            value_region = ButtonRegion(
                id="value",
                rows=rows,
                weight=0.9,
                variant="default",
                group=self._GROUP,
                clip_content=True,
            )
        # Bottom breathing room from the underline is reserved via the
        # button-level bottom-only content_padding (see __init__) rather
        # than a spacer region.
        return [icon_region, value_region], VerticalSplit()

    # ---------- flyout ----------

    def _show_flyout(self) -> None:
        try:
            from ui.canvas_infra.rhi.rhi_focus import park_keyboard_focus_off_qrhi

            park_keyboard_focus_off_qrhi()
        except Exception:
            pass
        if self._flyout is None:
            self._flyout = _ScrollValueFlyout(self.window())
            # Навигация: Up входит в флайаут сверху, Left/Right выходят обратно
            try:
                from sli_ui_toolkit.managers import bind_flyout

                bind_flyout(self, self._flyout, side="above")
            except Exception:
                pass
        # Edit-mode (Enter) → кольцо наверх и без автоскрытия, wheel-preview → кольцо на кнопке с таймером
        _grab = bool(self._keyboard_edit_active)
        if self._is_at_zero():
            self._flyout.show_value("", icon=get_app_icon(self._zero_icon), anchor=self, grab_focus=_grab)
        else:
            self._flyout.show_value(str(self._value), anchor=self, grab_focus=_grab)
        if _grab:
            self._flyout_hide_timer.stop()
            # show_aligned с grab=True уже вызвал _grab_focus, но для
            # _ScrollValueFlyout без StrongFocus детей фокус может упасть на
            # ButtonGroup — форсируем на сам флайаут (StrongFocus) c кольцом
            # через singleShot, чтобы пережить NavigationManager bootstrap.
            try:
                from PySide6.QtCore import Qt as _Qt, QTimer as _QTimer

                _QTimer.singleShot(0, lambda f=self._flyout: f.setFocus(_Qt.FocusReason.OtherFocusReason))
            except Exception:
                try:
                    from PySide6.QtCore import Qt as _Qt2

                    self._flyout.setFocus(_Qt2.FocusReason.OtherFocusReason)
                except Exception:
                    pass
        else:
            self._flyout_hide_timer.start(_FLYOUT_HIDE_MS)
        if not self._is_scrolling:
            self._is_scrolling = True
            self._sync_regions()
        # Preview (wheel) не регистрирует секцию — Up/Down остаются у тулбара;
        # edit-mode регистрирует и крадёт фокус наверх.
        if not _grab:
            try:
                from sli_ui_toolkit.managers import NavigationManager

                NavigationManager.get_instance().unregister(self._flyout)
            except Exception:
                pass

    def _hide_flyout(self) -> None:
        self._flyout_hide_timer.stop()
        if self._flyout is not None:
            self._flyout.hide()
        if self._is_scrolling:
            self._is_scrolling = False
            self._sync_regions()

ScrollValueButton.inspect_spec = InspectSpec(
    family="ScrollValueButton",
    state=(
        SpecField("value", "get_value"),
        SpecField("min_value", "_min_value", private=True),
        SpecField("max_value", "_max_value", private=True),
        SpecField("saved_value", "get_saved_value"),
        SpecField("checked", "isChecked"),
    ),
    regions=True,
    docs="docs/dev/widgets/scroll_value_button.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
ScrollValueButton.widget_descriptor = WidgetDescriptor(
    family=ScrollValueButton.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ScrollValueButton.inspect_spec, 'config', ()),
        state=ScrollValueButton.inspect_spec.state,
        token_family=getattr(ScrollValueButton.inspect_spec, 'token_family', ()),
        regions=getattr(ScrollValueButton.inspect_spec, 'regions', False),
        layers=getattr(ScrollValueButton.inspect_spec, 'layers', False),
        docs=getattr(ScrollValueButton.inspect_spec, 'docs', ''),
        preview_seed=getattr(ScrollValueButton.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ScrollValueButton.inspect_spec, 'apply_config_refresh', None),
    ),
)