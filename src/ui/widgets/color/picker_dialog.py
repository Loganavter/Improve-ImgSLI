"""Themed color picker — app-level replacement for the system ``QColorDialog``.
Non-modal, resizable ``QDialog`` (custom title bar via the app-wide CSD
auto-decorator, see ``shared_toolkit.ui.decorate_dialog``) built from toolkit
atoms so it matches the rest of the app instead of the OS-native picker: an
SV square (custom, not a linear control) + a hue ``Slider`` + an alpha
``Slider`` (vertical, filled with a spectrum/checkerboard ``track_painter``
instead of the default flat track), a color-value ``CustomLineEdit`` plus
a small format-cycle button that switches the value between ``HEX``
(``#RRGGBB`` / ``#RRGGBBAA`` when alpha editing is on), ``RGB`` and ``HSL``
representations (see ``value_format``), RGB ``SpinBox`` fields, a
before/after preview chip and a recent-colors chip row
(``RecentColorsRow``). Return/Enter accepts.

Keyboard navigation: ``declare_navigation_rows`` registers the dialog's
four interaction rows *by container* (``ToolbarRowsSection``), visual
top→bottom — the SV/hue/alpha picker row (``_picker_container``), the
value-fields row (``_fields_container``: field + format button + R/G/B/A
spin boxes), the recent-color chips row (``_recents_row``) and the action
buttons (``_actions_container``). Declared rows (not the zero-config
``AutoNavigationSection``) are deliberate: the auto section claims *any*
descendant (``owns`` is an ancestor fallback) and derives its rows from
on-screen pixel clustering rather than the layout containers — so "every
control is owned" was vacuous, and the walk was not tied to the dialog's
rows. A declared row is owned iff it is one of the four, and the walk
follows container order, not pixel clustering. The chips
themselves are ``StrongFocus`` + ``FocusLayer`` ring (so Left/Right steps
within the row); the SV square is ``StrongFocus`` too, but it stays a
navigation stop until ``Enter`` explicitly enters its value-edit mode.
While navigating, arrows belong to the section (the square does not consume
them); while editing (``is_editing()`` — the toolkit's value-edit contract),
arrows and WASD move the crosshair, ``Enter`` commits and ``Esc`` reverts to
the saturation/value captured on entry. Movement is *held-key* based, not
per-keypress: the square feeds the held arrows into
``ui.widgets.color.sv_movement.KeyHoldStepper``, so two directions at once
move diagonally at axis speed (each axis ``step/sqrt(2)``) and a held key
moves continuously on a 16 ms timer with a 1x->4x ramp; a tap still applies
one base step. Its keyboard-focus ring is the toolkit's shared
``paint_focus_ring`` (keyboard modality only — a mouse click focuses without
a ring), drawn on the outer widget boundary while the gradient/thumb live in
``content_rect()``, inset by ``_SV_RING_GUTTER_DP`` so the ring reads as
focus rather than as the square's border. Esc (or any close path) returns
the keyboard to the widget that opened the picker.

Kept API-compatible with the subset of ``QColorDialog`` the callers used
(``colorSelected``, ``finished``, ``show``/``raise_``/``activateWindow``,
``setWindowTitle``) so call sites only need to swap the constructor and
``setOption(ShowAlphaChannel, ...)`` -> ``set_show_alpha(...)``.
Audit-Meta: pattern=qdialog-wiring reason="one ColorPicker QDialog — picker + fields + preview wiring"
"""

from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import shiboken6

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from resources.translations import tr
from shared_toolkit.ui.layout_sizing import GeometryApplyPolicy, apply_dialog_geometry
from shared_toolkit.ui.themed_dialog import ThemedDialog
from sli_ui_toolkit.managers import declare_navigation_rows, scaled_px
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers import connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_FONT, AXIS_SCALE
from sli_ui_toolkit.ui.widgets.atomic.focus_ring import paint_focus_ring
from sli_ui_toolkit.widgets import Button, CustomLineEdit, Label, Slider, SpinBox

from ui.theming import try_resolve_theme_color
from ui.widgets.color.recents import (
    RecentColorsRow,
    RecentColorsStore,
    checkerboard_brush,
)
from ui.widgets.color.sv_movement import KeyHoldStepper
from ui.widgets.color.value_format import (
    ValueFormat,
    color_format_label,
    color_value_has_alpha,
    format_color_value,
    next_color_format,
    parse_color_value,
)

# Chrome geometry in DESIGN px (never scaled at module scope — the use-time
# ``scaled_px`` calls live in ``ColorPickerDialog._apply_metrics`` / the
# widget ``apply_metrics`` methods; the contract test
# ``tests/contracts/test_color_widgets_no_import_time_scaling.py`` guards it).
# ``scaled_px`` bakes the live ``UiScale`` factor into the value it returns,
# so evaluating it here would freeze the chrome at the launch factor and the
# dialog could never follow a later interface-scale change (L5 regression:
# the picker was destroyed after a scale change precisely because these were
# module-level constants).
_MIN_WIDTH_DP = 260
_MIN_HEIGHT_DP = 300
_MAX_WIDTH_DP = 640
_TITLE_EXTRA_WIDTH_DP = 88
_ROOT_MARGIN_H_DP = 16
_ROOT_MARGIN_TOP_DP = 14
_ROOT_MARGIN_BOTTOM_DP = 14
_ROOT_SPACING_DP = 12
_PICKER_SPACING_DP = 10
_FIELDS_SPACING_DP = 6
_ACTIONS_SPACING_DP = 8
_SV_MIN_W_DP = 160
_SV_MIN_H_DP = 120
_SV_THUMB_RADIUS_DP = 9.0
# Gap between the SV square's focus ring and its gradient/border. The ring is
# 2 px thick at factor 1.0 (``paint_focus_ring``), drawn on the outer widget
# boundary, so 4 design px leaves a visible 2 px gap — the ring reads as
# "this control has keyboard focus", not as the square's own border. Inset at
# USE time (``_SVSquare.apply_metrics``), never at import.
_SV_RING_GUTTER_DP = 4.0
_SLIDER_MIN_H_DP = 140
_PREVIEW_CHIP_DP = 34
_FORMAT_BTN_W_DP = 46
_FORMAT_BTN_H_DP = 26
_ACTION_BTN_W_DP = 72
_ACTION_BTN_H_DP = 30
# The toolkit ``CustomLineEdit``'s ``minimumSizeHint().width()`` is 0, so the
# stretch-pinned fields row collapsed the value field to 0 px and its digits
# landed under the ``HEX`` format button. A real (small) minimum keeps the
# field visible at every dialog width its own declared minimum allows.
_VALUE_FIELD_MIN_W_DP = 96


def _geometry_policy() -> GeometryApplyPolicy:
    """The dialog's geometry recipe, re-derived at use time (never cached).

    Size (not position — always centers on the parent window) is remembered
    across opens via QSettings, same mechanism as settings/export/help/
    image-properties. Message/alert dialogs intentionally do not opt into this.

    ``lock_minimum_to_computed`` is what makes the declared window minimum
    cover the content: without it the only minimum is ``minimum_floor``
    (260x300 design px), which is *below* the laid-out content (426x424 at
    factor 1.0) — so a remembered/restored small size crushed every row. Same
    recipe class as the export dialog (``plugins/export/layout_geometry.py``),
    the other non-scrollable dialog.
    """
    return GeometryApplyPolicy(
        resize_when_hidden=True,
        update_minimum=True,
        minimum_floor=(scaled_px(_MIN_WIDTH_DP), scaled_px(_MIN_HEIGHT_DP)),
        width_bounds=(scaled_px(_MIN_WIDTH_DP), scaled_px(_MAX_WIDTH_DP)),
        center_on_parent=True,
        lock_minimum_to_computed=True,
        remember_key="color_picker",
    )


def _themed_or_fallback(
    manager: ThemeManager | None, token: str, fallback: QColor | str
) -> QColor:
    """Theme token with hardcoded fallback to preserve visual when token missing.

    Keeps HSV-generated colors intact — only used for chrome / neutral fills
    that have a semantic token (dialog.background, surface.background, etc.).
    """
    try:
        if manager is not None:
            resolved = try_resolve_theme_color(manager, token)
            if resolved is not None and resolved.isValid():
                return QColor(resolved)
    except Exception:
        pass
    return QColor(fallback) if not isinstance(fallback, QColor) else QColor(fallback)


def _themed_border_color(manager: ThemeManager | None) -> QColor:
    """dialog.border with visual-preserving fallback (#c0c0c0 light / #555 dark)."""
    # dialog.border light #c0c0c0 dark #555 — fallback uses light value to keep
    # pre-token visual; dark theme resolves via token when available.
    return _themed_or_fallback(manager, "dialog.border", QColor("#c0c0c0"))


class _SVSquare(QWidget):
    """Saturation (x) / value (y) picking area for a fixed hue.

    The gradient fills ``content_rect()`` — the widget inset by
    ``_SV_RING_GUTTER_DP`` so the keyboard-focus ring has its own gutter —
    edge to edge (so clicking exactly at the field's border reaches the true
    0/1 extreme) and hit-testing maps 1:1 against that same rect. Only the
    drawn cursor position is clamped inward by the thumb radius so the ring
    never paints partway outside the field — at extreme values it hugs the
    inside of the edge instead of centering exactly on it.

    Keyboard: the square is a navigation stop (``StrongFocus``) but a
    two-dimensional surface has no single row/column axis, so bare arrows
    stay the picker row section's — they walk the row and never change the
    colour. ``Enter`` enters the explicit value-edit mode (the toolkit's
    ``is_editing()`` contract): arrows and W/A/S/D then move the crosshair,
    ``Enter`` commits, ``Esc`` restores the saturation/value captured on
    entry. Held keys are sampled by ``KeyHoldStepper`` (16 ms timer, held-key
    set), so simultaneous directions move diagonally at axis speed and a
    hold accelerates instead of stepping once per auto-repeat event. The
    keyboard ring is the toolkit's shared ``paint_focus_ring`` — keyboard
    modality only, so a mouse click focuses the square without painting it.
    """

    svChanged = Signal(float, float)

    #: Edit-mode keys → the axis direction they move (mirrors the toolkit
    #: Slider's ``_EDIT_ADJUST_KEYS``; «W/S = value, A/D = saturation»).
    _EDIT_ADJUST_KEYS = {
        Qt.Key.Key_Left: Qt.Key.Key_Left,
        Qt.Key.Key_Right: Qt.Key.Key_Right,
        Qt.Key.Key_Up: Qt.Key.Key_Up,
        Qt.Key.Key_Down: Qt.Key.Key_Down,
        Qt.Key.Key_A: Qt.Key.Key_Left,
        Qt.Key.Key_D: Qt.Key.Key_Right,
        Qt.Key.Key_W: Qt.Key.Key_Up,
        Qt.Key.Key_S: Qt.Key.Key_Down,
    }

    #: One base edit step in saturation/value units (0..1). A tap applies
    #: exactly this; a held key scales it by dt and the acceleration ramp.
    EDIT_STEP = 0.01

    #: Navigation arrows — handed to the section (never consumed) while the
    #: square is not editing. Kept as one tuple so the handler does not need a
    #: four-key inline test (the arrow-redirection ratchet reads those).
    _NAV_ARROW_KEYS = (
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        # A NoFocus child is invisible to the picker's row walk; StrongFocus
        # is what makes the section's ``_focusable`` (StrongFocus only) see it.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._hue = 0.0
        self._sat = 1.0
        self._val = 1.0
        # Keyboard ring modality comes from the last input device, not the
        # FocusReason (guide §7) — set in focusInEvent via resolve_keyboard_focus.
        self._keyboard_focus = False
        self._editing = False
        self._edit_entry_sv = (self._sat, self._val)
        # One held-key stepper for this surface: 16 ms timer, WASD mapped to
        # arrows by the key handler, deltas applied through ``_apply_sv``.
        self._stepper = KeyHoldStepper(self.EDIT_STEP, self)
        self._stepper.tick.connect(self._on_stepper_tick)
        self._ring_gutter_px = 0.0
        self.apply_metrics()
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

    def apply_metrics(self) -> None:
        """Re-resolve this widget's chrome px from design space at use time."""
        self._thumb_radius_px = float(scaled_px(_SV_THUMB_RADIUS_DP))
        self._ring_gutter_px = float(scaled_px(_SV_RING_GUTTER_DP))
        self.setMinimumSize(scaled_px(_SV_MIN_W_DP), scaled_px(_SV_MIN_H_DP))
        self.update()

    def set_hue(self, hue_deg: float) -> None:
        self._hue = hue_deg
        self.update()

    def set_sv(self, sat: float, val: float) -> None:
        self._sat = max(0.0, min(1.0, sat))
        self._val = max(0.0, min(1.0, val))
        self.update()

    def is_editing(self) -> bool:
        """Value-edit contract, duck-typed by the toolkit's navigation sections.

        The section hands arrows to a control only while this returns True;
        while False the picker row's section keeps them for the ring walk
        (Up/Down rows, Left/Right columns). Controls without the method keep
        the legacy always-open gate — this one deliberately closes it.
        """
        return self._editing

    def _enter_edit_mode(self) -> None:
        self._editing = True
        self._edit_entry_sv = (self._sat, self._val)
        self.update()

    def _leave_edit_mode(self, *, commit: bool) -> None:
        self._editing = False
        # Held keys must not outlive edit mode: Qt delivers the eventual
        # keyRelease to whatever has focus then, not to this square.
        self._stepper.clear()
        if not commit:
            # Re-emit so the dialog (colour, preview, hex/spin fields) follows
            # the revert — edit-mode keys already pushed the live colour out.
            self._apply_sv(*self._edit_entry_sv)
        self.update()

    def _apply_sv(self, sat: float, val: float) -> None:
        sat = max(0.0, min(1.0, sat))
        val = max(0.0, min(1.0, val))
        if sat == self._sat and val == self._val:
            return
        self._sat, self._val = sat, val
        self.update()
        self.svChanged.emit(sat, val)

    def _on_stepper_tick(self, dx: float, dy: float, _dt: float) -> None:
        """Apply one held-key tick (diagonal normalized in the stepper)."""
        if not self._editing:
            self._stepper.clear()
            return
        self._apply_sv(self._sat + dx, self._val + dy)

    def focusInEvent(self, event) -> None:  # noqa: N802
        # Same modality source as the toolkit Slider (and the sibling
        # ``_RecentColorChip``): the manager's last-input flag, so a mouse
        # click focuses without a ring. The fallback is the chip's (True, not
        # a reason formula) — ``tests/contracts/test_no_unlisted_app_filter``
        # allows no Popup/ActiveWindow reason outside its allowlist.
        reason = getattr(event, "reason", lambda: Qt.FocusReason.OtherFocusReason)()
        try:
            from sli_ui_toolkit.ui.managers.navigation_manager import (
                resolve_keyboard_focus,
            )

            self._keyboard_focus = resolve_keyboard_focus(reason)
        except Exception:
            self._keyboard_focus = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._keyboard_focus = False
        # Held keys die with the focus: the keyRelease will go to the new
        # focus widget, so without this clear the timer would run forever.
        self._stepper.clear()
        # Leaving the widget ends edit mode but keeps the live value (same as
        # the toolkit Slider's focus-out); only Esc reverts.
        self._editing = False
        self.update()
        super().focusOutEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        # The dialog closing/hiding is the other way focus can vanish without
        # a matching keyRelease.
        self._stepper.clear()
        super().hideEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._editing:
                self._leave_edit_mode(commit=True)
            else:
                self._enter_edit_mode()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            if self._editing:
                self._leave_edit_mode(commit=False)
                event.accept()
                return
            # Not editing: Esc propagates to the dialog's reject().
            super().keyPressEvent(event)
            return
        if self._editing:
            arrow = self._EDIT_ADJUST_KEYS.get(key)
            if arrow is not None:
                # Auto-repeat is redundant: the held-key set already has the
                # key, and restarting a tap here would double the step.
                if not event.isAutoRepeat():
                    self._stepper.press(arrow)
                event.accept()
                return
            super().keyPressEvent(event)
            return
        if key in self._NAV_ARROW_KEYS:
            # Not editing: arrows are the picker row section's (ring walk).
            # Ignore so the section's trial dispatch / event filter keeps them.
            event.ignore()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        """End the held-key movement; a tap still applies one base step."""
        if self._editing:
            arrow = self._EDIT_ADJUST_KEYS.get(event.key())
            if arrow is not None:
                # Qt emits release+press pairs for auto-repeat; only the real
                # release may drop the key (and only it may count as a tap).
                if not event.isAutoRepeat():
                    self._stepper.release(arrow)
                event.accept()
                return
        super().keyReleaseEvent(event)

    def content_rect(self) -> QRectF:
        """The gradient/hit-test rect: the widget inset by the ring gutter.

        The focus ring stays on the outer widget boundary; this inset is the
        visible gap that keeps the ring reading as focus instead of as the
        square's border. Gradient, border, hit-testing and the thumb all use
        this same rect, so click mapping stays 1:1 with what is drawn.
        """
        gutter = self._ring_gutter_px
        return QRectF(self.rect()).adjusted(gutter, gutter, -gutter, -gutter)

    def _thumb_center(self, rect: QRectF) -> QPointF:
        margin = self._thumb_radius_px + 1.6
        raw_x = rect.left() + self._sat * rect.width()
        raw_y = rect.top() + (1.0 - self._val) * rect.height()
        x = min(max(raw_x, rect.left() + margin), rect.right() - margin)
        y = min(max(raw_y, rect.top() + margin), rect.bottom() - margin)
        return QPointF(x, y)

    def _set_from_pos(self, pos: QPointF) -> None:
        rect = self.content_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        sat = max(0.0, min(1.0, (pos.x() - rect.left()) / rect.width()))
        val = max(0.0, min(1.0, 1.0 - (pos.y() - rect.top()) / rect.height()))
        self._apply_sv(sat, val)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._set_from_pos(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._set_from_pos(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        content = self.content_rect()
        if content.width() <= 1.0 or content.height() <= 1.0:
            # Too small for a gutter + field (e.g. a transient 0-size layout
            # pass): drawing would paint outside the field or invert the rect.
            return
        # Half-pixel inset keeps the 1 px border crisp; the field itself is
        # ``content_rect`` so the ring gutter stays free of gradient.
        rect = QRectF(content).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 8.0

        hue_color = QColor.fromHsvF(self._hue / 360.0, 1.0, 1.0)
        sat_gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        # Saturation endpoint: intrinsic white (HSV model) — keep visual white
        # but allow theme override via surface.background
        # with fallback to hardcoded white so HSV square stays correct if token missing.
        sat_white = _themed_or_fallback(
            self.theme_manager, "surface.background", QColor(255, 255, 255)
        )
        # Preserve pure white for the SV picker even on dark theme: the square's
        # left edge must be white (s=0) not surface dark gray. Use token only if
        # it resolves to near-white; otherwise keep hardcoded white.
        if sat_white.lightness() < 220:
            sat_white = QColor(255, 255, 255)
        sat_gradient.setColorAt(0.0, sat_white)
        sat_gradient.setColorAt(1.0, hue_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sat_gradient)
        painter.drawRoundedRect(rect, radius, radius)

        val_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        # Value overlay: transparent→opaque black — part of HSV model, not theme
        val_gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        val_gradient.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.setBrush(val_gradient)
        painter.drawRoundedRect(rect, radius, radius)

        border = _themed_border_color(self.theme_manager)
        painter.setPen(QPen(border, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        center = self._thumb_center(content)
        thumb_radius = self._thumb_radius_px
        # Thumb rings: high-contrast white + soft dark outline — tokenized via
        # slider.thumb.outer and shadow.color
        thumb_outer = _themed_or_fallback(
            self.theme_manager, "slider.thumb.outer", QColor("#ffffff")
        )
        # Keep pure white for contrast even on dark surface.background (#2b2b2b)
        if thumb_outer.lightness() < 220:
            thumb_outer = QColor("#ffffff")
        painter.setPen(QPen(thumb_outer, 3.2))
        painter.drawEllipse(center, thumb_radius, thumb_radius)
        thumb_shadow = _themed_or_fallback(
            self.theme_manager, "shadow.color", QColor(0, 0, 0, 90)
        )
        # shadow.color may be #50000000 / #64000000 — normalize to 90 alpha fallback
        # if token resolves to a different alpha, keep the resolved but ensure alpha
        if thumb_shadow.alpha() == 0:
            thumb_shadow = QColor(0, 0, 0, 90)
        elif thumb_shadow.alpha() not in (90, 100, 80):
            # Blend resolved shadow's RGB with desired 90 alpha to preserve theme hue
            tmp = QColor(thumb_shadow)
            tmp.setAlpha(90)
            thumb_shadow = tmp
        painter.setPen(QPen(thumb_shadow, 1.2))
        painter.drawEllipse(center, thumb_radius, thumb_radius)

        # Keyboard focus ring — the toolkit's shared helper (the same one
        # Switch/Slider use), drawn last so it sits over the gradient. Only
        # keyboard modality paints it; a mouse click focuses silently.
        if self._keyboard_focus and self.hasFocus():
            paint_focus_ring(
                self, painter, self.theme_manager, corner_radius=radius
            )


class _PreviewChip(QWidget):
    """Circular before/after color comparison, split down the middle.

    Each half is painted over its own checkerboard tile first, so partial
    alpha in either color is actually visible instead of blending into
    whatever the other half happened to be (which previously made low-alpha
    colors look fully opaque).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.apply_metrics()
        # Neutral preview defaults: themed dialog.background / surface.background
        _tm = ThemeManager.get_instance()
        self._before = _themed_or_fallback(_tm, "surface.background", QColor(255, 255, 255))
        self._after = _themed_or_fallback(_tm, "surface.background", QColor(255, 255, 255))
        self.theme_manager = _tm
        self.theme_manager.theme_changed.connect(self.update)

    def apply_metrics(self) -> None:
        """Re-resolve this widget's chrome px from design space at use time."""
        self.setFixedSize(scaled_px(_PREVIEW_CHIP_DP), scaled_px(_PREVIEW_CHIP_DP))
        self.update()

    def set_before(self, color: QColor) -> None:
        self._before = QColor(color)
        self.update()

    def set_after(self, color: QColor) -> None:
        self._after = QColor(color)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        path = QPainterPath()
        path.addEllipse(rect)
        painter.save()
        painter.setClipPath(path)

        checker = checkerboard_brush(self.theme_manager.is_dark())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(checker)
        painter.drawRect(rect)

        left_half = QRectF(rect.left(), rect.top(), rect.width() / 2.0, rect.height())
        right_half = QRectF(rect.center().x(), rect.top(), rect.width() / 2.0, rect.height())
        painter.setBrush(self._before)
        painter.drawRect(left_half)
        painter.setBrush(self._after)
        painter.drawRect(right_half)

        painter.restore()

        border = _themed_border_color(self.theme_manager)
        painter.setPen(QPen(border, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)


class ColorPickerDialog(ThemedDialog):
    """Themed color picker dialog — non-modal, ``QColorDialog``-style usage."""

    colorSelected = Signal(QColor)

    def __init__(
        self,
        initial: QColor,
        parent: QWidget | None = None,
        *,
        title: str = "",
        show_alpha: bool = False,
        ok_text: str | None = None,
        cancel_text: str | None = None,
        recents_store: RecentColorsStore | None = None,
        opener: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        # Who gets the keyboard back when the picker closes (Esc/OK/Cancel).
        # The explicit ``opener`` wins; otherwise the widget that held focus
        # when the picker was constructed (the toolbar button / swatch that
        # opened it) — captured before show() activates this dialog window and
        # steals focus.
        self._opener: QWidget | None = (
            opener if opener is not None else QApplication.focusWidget()
        )
        # Fallback initial white via theme token surface.background
        _fallback_init = _themed_or_fallback(
            self.theme_manager, "surface.background", QColor(255, 255, 255)
        )
        if _fallback_init.lightness() < 220:
            # HSV neutral must stay white, not dark surface gray
            _fallback_init = QColor(255, 255, 255)
        self._color = QColor(initial) if isinstance(initial, QColor) and initial.isValid() else QColor(_fallback_init)
        self._updating = False
        self._show_alpha = False
        self._value_format = ValueFormat.HEX
        self._recents_store = recents_store if recents_store is not None else RecentColorsStore()
        self._ok_text = ok_text if ok_text else tr("common.ok", default="OK")
        self._cancel_text = cancel_text if cancel_text else tr("common.cancel", default="Cancel")

        self.setObjectName("ColorPickerDialog")
        if title:
            self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(False)

        self._build_ui(ok_text=self._ok_text, cancel_text=self._cancel_text)
        # Keyboard navigation over the picker's four interaction rows, in
        # visual top→bottom order. Rows are the real band containers keyed to
        # the layout (``_fields_container`` wraps the otherwise-bare fields
        # QHBoxLayout), so the section's ownership is exact and the walk is
        # container order — never the auto section's y-cluster heuristic.
        # The SV square is StrongFocus (it joins this row's walk); its bare
        # arrows stay the section's until Enter enters its value-edit mode —
        # see ``_SVSquare.is_editing``. The chips are StrongFocus too
        # (recents.py). See the module docstring.
        declare_navigation_rows(
            self,
            [
                self._picker_container,
                self._fields_container,
                self._recents_row,
                self._actions_container,
            ],
            tag="color-picker",
        )
        self.set_show_alpha(show_alpha)
        self._preview.set_before(self._color)
        self._sync_from_color()
        self._apply_dialog_geometry()
        self.install_dialog_geometry(self._apply_dialog_geometry)
        # Font AND scale changes both move this dialog's chrome: the rows'
        # margins/spacing/fixed sizes and the declared minimum must be
        # re-derived, and the platform window minimum re-pinned (see
        # ``_on_metrics_changed``). ``connect_ui_metrics`` coalesces them into
        # one slot call per appearance change.
        connect_ui_metrics(
            self,
            self._on_metrics_changed,
            axes=frozenset({AXIS_FONT, AXIS_SCALE}),
        )

        self.mark_theme_ui_ready()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Return/Enter accept (QColorDialog-compatible), but deliberately NOT
        # via a window-level QShortcut: a shortcut swallows the key before the
        # focused row sees it, so Enter on a keyboard-focused recent-color chip
        # accepted the dialog instead of applying that colour (probed). Here
        # the key only reaches this handler when the focused widget (chip,
        # button, field) did not consume it — Enter keeps activating whatever
        # is focused, and accepts otherwise.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_accept()
            event.accept()
            return
        super().keyPressEvent(event)

    def done(self, result: int) -> None:  # noqa: N802
        # Every close path (Esc → reject, OK → accept, Cancel, window close)
        # funnels through QDialog.done — hand the keyboard back to the widget
        # that opened the picker instead of leaving focus nowhere.
        super().done(result)
        self._restore_opener_focus()

    def _restore_opener_focus(self) -> None:
        """Give the keyboard back to the widget that opened the picker.

        Widget-level ``setFocus`` only — never ``activateWindow``: on Wayland
        an activation request issued while the host is not the active window
        carries a stale xdg-activation token and gets denied (same rule the
        toolkit's flyout focus-restore follows). The parent usually regains
        activation right after the dialog hides; until then Qt simply records
        the window's focus widget, so the opener has the keyboard as soon as
        the window is active again.
        """
        opener = self._opener
        self._opener = None
        if opener is None:
            return
        try:
            if not shiboken6.isValid(opener) or not opener.isVisible():
                return
        except Exception:
            return
        try:
            from sli_ui_toolkit.managers import NavigationManager

            reason = NavigationManager.get_instance().current_focus_reason()
        except Exception:
            reason = Qt.FocusReason.OtherFocusReason
        try:
            opener.setFocus(reason)
        except Exception:
            pass

    def _on_metrics_changed(self, _axes: frozenset[str] | None = None) -> None:
        """Appearance bus (font / interface scale) changed — re-derive the dialog.

        Every chrome px is re-resolved from design space (``_apply_metrics``)
        and the declared minimum re-locked to the new content, then the
        platform window minimum re-pinned. Without the re-lock the *widget*
        minimum follows the layout while the *window* minimum stays at the
        previous factor, so a CSD/system resize can still crush the rows.
        """
        self._apply_metrics()
        self.layout().invalidate()
        self.layout().activate()
        self._apply_dialog_geometry()

    def _apply_metrics(self) -> None:
        """Re-resolve every chrome px from design space at USE time.

        Runs once the widget tree exists and again on each appearance change.
        Never cache a ``scaled_px`` result on a module/class attribute: that
        bakes the launch factor in and the dialog cannot follow a later
        interface-scale change (the L5 defect).
        """
        root = self.layout()
        if root is not None:
            root.setContentsMargins(
                scaled_px(_ROOT_MARGIN_H_DP),
                scaled_px(_ROOT_MARGIN_TOP_DP),
                scaled_px(_ROOT_MARGIN_H_DP),
                scaled_px(_ROOT_MARGIN_BOTTOM_DP),
            )
            root.setSpacing(scaled_px(_ROOT_SPACING_DP))
        self._picker_row.setSpacing(scaled_px(_PICKER_SPACING_DP))
        self._fields_row.setSpacing(scaled_px(_FIELDS_SPACING_DP))
        self._actions_row.setSpacing(scaled_px(_ACTIONS_SPACING_DP))
        self._sv.apply_metrics()
        for slider in (self._hue_slider, self._alpha_slider):
            slider.setMinimumHeight(scaled_px(_SLIDER_MIN_H_DP))
        self._preview.apply_metrics()
        self._format_btn.setFixedSize(
            scaled_px(_FORMAT_BTN_W_DP), scaled_px(_FORMAT_BTN_H_DP)
        )
        self._hex_edit.setMinimumWidth(scaled_px(_VALUE_FIELD_MIN_W_DP))
        for button in (self._cancel_btn, self._ok_btn):
            button.setMinimumSize(scaled_px(_ACTION_BTN_W_DP), scaled_px(_ACTION_BTN_H_DP))
        self._recents_row.apply_metrics()
        # The value-fields band is its own container widget (a declared
        # navigation row — see __init__): resizing its children invalidates
        # *its* cached layout, but the dialog's root layout keeps its cached
        # minimum/sizeHint until the container reports geometry back. Without
        # this the hidden-dialog metrics probe (and a real scale change before
        # the window is shown) keeps the previous width instead of re-deriving.
        fields_layout = self._fields_container.layout()
        if fields_layout is not None:
            fields_layout.invalidate()
        self._fields_container.updateGeometry()

    def _pin_window_minimum(self) -> None:
        """Re-pin the QWindow minimum to the widget minimum.

        ``apply_dialog_geometry`` only sets the *widget* minimum; the platform
        window keeps the stale value, so CSD/system resizes could still crush
        the rows after an appearance change (mirrors
        ``ui/managers/dialog_manager.py::_pin_dialog_minimum`` and
        ``SettingsDialog._pin_window_minimum``).
        """
        try:
            handle = self.windowHandle()
        except RuntimeError:
            return
        if handle is not None:
            handle.setMinimumSize(self.minimumSize())

    def _apply_dialog_geometry(self) -> None:
        # No ``self.adjustSize()`` here: this recipe re-runs on every deferred
        # geometry pass (including after the dialog is already visible, e.g.
        # theme/font changes) — adjustSize() on a visible widget unconditionally
        # shrinks it back to sizeHint(), which would silently undo both a
        # remembered-size restore and any live user resize. sizeHint() alone
        # already reflects the layout's natural size without touching the
        # widget's actual current geometry.
        content_hint = self.sizeHint()
        # The custom title bar has no elide margin of its own — widen the
        # window past content size when the (often long, translated) title
        # would otherwise get clipped against the close button.
        title_width = (
            QFontMetrics(self.font()).horizontalAdvance(self.windowTitle())
            + scaled_px(_TITLE_EXTRA_WIDTH_DP)
        )
        width = max(content_hint.width(), min(scaled_px(_MAX_WIDTH_DP), title_width))
        apply_dialog_geometry(
            self, width, content_hint.height(), policy=_geometry_policy()
        )
        self._pin_window_minimum()

    def _build_ui(self, *, ok_text: str, cancel_text: str) -> None:
        root = QVBoxLayout(self)
        # Margins/spacing/fixed sizes are applied in ``_apply_metrics``
        # (design px -> scaled at use time), not here.
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Row containers (not bare layouts) so each interaction band is one
        # widget: ``declare_navigation_rows`` in __init__ registers these four
        # containers as the picker's navigation rows, in this order.
        self._picker_container = QWidget(self)
        self._actions_container = QWidget(self)

        self._picker_row = QHBoxLayout(self._picker_container)
        self._picker_row.setContentsMargins(0, 0, 0, 0)
        self._picker_row.setSpacing(0)
        # The SV square is a navigation stop (StrongFocus) but its bare arrows
        # stay the row section's: the 2D surface has no row/column model, so
        # arrows would fight the ring walk. Enter enters its explicit edit
        # mode, where arrows + WASD mean one axis each (W/S = value, A/D =
        # saturation) — see ``_SVSquare.keyPressEvent``.
        self._sv = _SVSquare(self)
        self._sv.svChanged.connect(self._on_sv_changed)
        self._picker_row.addWidget(self._sv, 1)

        self._hue_slider = Slider(
            Qt.Orientation.Vertical,
            self,
            track_thickness=18,
            thumb_radius=9,
            track_painter=self._paint_hue_track,
            show_value_fill=False,
        )
        self._hue_slider.setRange(0, 359)
        self._hue_slider.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._hue_slider.valueChanged.connect(self._on_hue_changed)
        self._picker_row.addWidget(self._hue_slider)

        self._alpha_slider = Slider(
            Qt.Orientation.Vertical,
            self,
            track_thickness=18,
            thumb_radius=9,
            track_painter=self._paint_alpha_track,
            show_value_fill=False,
        )
        self._alpha_slider.setRange(0, 255)
        self._alpha_slider.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._alpha_slider.valueChanged.connect(self._on_alpha_changed)
        self._picker_row.addWidget(self._alpha_slider)

        root.addWidget(self._picker_container, 1)

        # The value-fields band is its own container widget (not a bare
        # QHBoxLayout): a declared navigation row must be a widget so the
        # section can own its descendants exactly (``_fields_container`` is
        # row 2 of the picker's section — see __init__). The container adds
        # no margins, so the fields' right-aligned geometry is unchanged.
        self._fields_container = QWidget(self)
        self._fields_row = QHBoxLayout(self._fields_container)
        self._fields_row.setContentsMargins(0, 0, 0, 0)
        self._fields_row.setSpacing(0)

        # Leading stretch pins the whole fields group (preview chip, labels,
        # inputs) to the right edge. It also absorbs the dialog slack so the
        # gaps between the fixed-size items never grow on relayout — without
        # it QBoxLayout redistributes extra width between the items and the
        # fields visibly drift while the dialog is being resized.
        # NOTE: the stretch takes all slack, so the value field below must
        # carry its own minimum width (``_apply_metrics``) or it collapses.
        self._fields_row.addStretch(1)

        self._preview = _PreviewChip(self)
        self._fields_row.addWidget(self._preview)

        self._field_labels: list[Label] = []

        def _field_label(text: str) -> Label:
            label = Label(text, self, variant="caption", pixel_size=18)
            label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            # QLabel defaults to Preferred/Preferred: in a wide dialog the
            # labels would absorb the slack and push the fields right with
            # every relayout pass (visible as jitter during interactive
            # resize). Pin the width to the text so field positions are
            # stable at any dialog width.
            label.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
            )
            self._field_labels.append(label)
            return label

        self._hex_edit = CustomLineEdit(self, alignment=Qt.AlignmentFlag.AlignCenter)
        self._hex_edit.editingFinished.connect(self._on_hex_edited)
        self._fields_row.addWidget(self._hex_edit)

        self._format_btn = Button(text="HEX", variant="surface", parent=self)
        self._format_btn.setToolTip(
            tr("ui.color_value_format_cycle_tooltip", default="Change color value format (HEX/RGB/HSL)")
        )
        self._format_btn.clicked.connect(self._on_format_btn_clicked)
        self._fields_row.addWidget(self._format_btn)

        self._r_spin = SpinBox(self)
        self._g_spin = SpinBox(self)
        self._b_spin = SpinBox(self)
        for text, spin in (
            ("R", self._r_spin),
            ("G", self._g_spin),
            ("B", self._b_spin),
        ):
            spin.setRange(0, 255)
            spin.valueChanged.connect(self._on_rgb_changed)
            self._fields_row.addWidget(_field_label(text))
            self._fields_row.addWidget(spin)

        self._alpha_label = _field_label("A")
        self._a_spin = SpinBox(self)
        self._a_spin.setRange(0, 255)
        self._a_spin.valueChanged.connect(self._on_alpha_spin_changed)
        self._fields_row.addWidget(self._alpha_label)
        self._fields_row.addWidget(self._a_spin)

        root.addWidget(self._fields_container)

        self._recents_row = RecentColorsRow(
            self,
            caption=tr("ui.recent_colors_caption", default="Recent"),
        )
        self._recents_row.recentPicked.connect(self._on_recent_picked)
        self._recents_row.set_colors(self._recents_store.load())
        root.addWidget(self._recents_row)

        self._actions_row = QHBoxLayout(self._actions_container)
        self._actions_row.setContentsMargins(0, 0, 0, 0)
        self._actions_row.setSpacing(0)
        self._actions_row.addStretch(1)
        self._cancel_btn = Button(text=cancel_text, variant="surface", parent=self)
        self._cancel_btn.clicked.connect(self.reject)
        self._actions_row.addWidget(self._cancel_btn)
        self._ok_btn = Button(text=ok_text, variant="surface", parent=self)
        self._ok_btn.setMinimumSize(scaled_px(72), scaled_px(30))
        self._ok_btn.clicked.connect(self._on_accept)
        self._actions_row.addWidget(self._ok_btn)
        root.addWidget(self._actions_container)

        # Resolve the hold-placed (unscaled) chrome above from design space in
        # one pass so the tree is coherent before the first geometry apply.
        self._apply_metrics()

    def set_show_alpha(self, enabled: bool) -> None:
        self._show_alpha = bool(enabled)
        self._alpha_slider.setVisible(self._show_alpha)
        self._alpha_label.setVisible(self._show_alpha)
        self._a_spin.setVisible(self._show_alpha)
        self._hex_edit.setText(
            format_color_value(self._color, self._value_format, include_alpha=self._show_alpha)
        )
        # Toggling the alpha row changes the fields row's minimum width: re-lock
        # the declared minimum (and the window minimum) so the dialog cannot be
        # left smaller than its own content.
        self._apply_dialog_geometry()

    def color(self) -> QColor:
        return QColor(self._color)

    def setCurrentColor(self, color: QColor) -> None:
        if not isinstance(color, QColor) or not color.isValid():
            return
        self._color = QColor(color)
        self._preview.set_before(self._color)
        self._sync_from_color()

    def _current_hue_deg(self) -> float:
        return float(self._hue_slider.value())

    def _paint_hue_track(self, painter: QPainter, rect: QRectF) -> None:
        """Full hue spectrum, top=359 (max) down to bottom=0 (min) per Slider's vertical convention."""
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        steps = 6
        for i in range(steps + 1):
            t = i / steps
            hue_frac = 1.0 - t
            gradient.setColorAt(t, QColor.fromHsvF(0.0 if hue_frac >= 1.0 else hue_frac, 1.0, 1.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRect(rect)

    def _paint_alpha_track(self, painter: QPainter, rect: QRectF) -> None:
        """Checkerboard + gradient of the current color, top=255 (opaque) to bottom=0 (transparent)."""
        opaque = QColor(self._color)
        opaque.setAlpha(255)
        transparent = QColor(self._color)
        transparent.setAlpha(0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(checkerboard_brush(self.theme_manager.is_dark()))
        painter.drawRect(rect)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, opaque)
        gradient.setColorAt(1.0, transparent)
        painter.setBrush(gradient)
        painter.drawRect(rect)

    def _sync_from_color(self) -> None:
        self._updating = True
        try:
            h, s, v, _a = self._color.getHsvF()
            hue_deg = self._current_hue_deg() if h < 0 else h * 360.0
            self._hue_slider.setValue(int(round(hue_deg)))
            self._sv.set_hue(hue_deg)
            self._sv.set_sv(s, v)
            self._alpha_slider.setValue(self._color.alpha())
            self._a_spin.setValue(self._color.alpha())
            self._alpha_slider.update()
            self._hex_edit.setText(
                format_color_value(self._color, self._value_format, include_alpha=self._show_alpha)
            )
            self._r_spin.setValue(self._color.red())
            self._g_spin.setValue(self._color.green())
            self._b_spin.setValue(self._color.blue())
        finally:
            self._updating = False
        self._preview.set_after(self._color)

    def _apply_new_color(
        self,
        color: QColor,
        *,
        resync_hue: bool = True,
        resync_alpha: bool = True,
        resync_rgb: bool = True,
    ) -> None:
        self._color = QColor(color)
        self._updating = True
        try:
            if resync_hue:
                h, s, v, _a = color.getHsvF()
                hue_deg = self._current_hue_deg() if h < 0 else h * 360.0
                self._hue_slider.setValue(int(round(hue_deg)))
                self._sv.set_hue(hue_deg)
                self._sv.set_sv(s, v)
            if resync_alpha:
                self._alpha_slider.setValue(color.alpha())
                self._a_spin.setValue(color.alpha())
            self._alpha_slider.update()
            if resync_rgb:
                self._r_spin.setValue(color.red())
                self._g_spin.setValue(color.green())
                self._b_spin.setValue(color.blue())
            self._hex_edit.setText(
                format_color_value(color, self._value_format, include_alpha=self._show_alpha)
            )
        finally:
            self._updating = False
        self._preview.set_after(color)

    def _on_sv_changed(self, sat: float, val: float) -> None:
        if self._updating:
            return
        hue = self._current_hue_deg() / 360.0
        color = QColor.fromHsvF(hue, sat, val, self._color.alphaF())
        self._apply_new_color(color, resync_hue=False)

    def _on_hue_changed(self, hue_deg: float) -> None:
        if self._updating:
            return
        self._sv.set_hue(hue_deg)
        color = QColor.fromHsvF(hue_deg / 360.0, self._sv._sat, self._sv._val, self._color.alphaF())
        self._apply_new_color(color, resync_hue=False)

    def _on_alpha_changed(self, value: int) -> None:
        if self._updating:
            return
        color = QColor(self._color)
        color.setAlpha(value)
        self._apply_new_color(color, resync_alpha=False)

    def _on_alpha_spin_changed(self, value: int) -> None:
        if self._updating:
            return
        color = QColor(self._color)
        color.setAlpha(value)
        self._apply_new_color(color, resync_alpha=False)

    def _on_hex_edited(self) -> None:
        text = self._hex_edit.text().strip()
        color = parse_color_value(text, self._value_format)
        if color is None:
            self._hex_edit.setText(
                format_color_value(self._color, self._value_format, include_alpha=self._show_alpha)
            )
            return
        if not (self._show_alpha and color_value_has_alpha(text, self._value_format)):
            color.setAlpha(self._color.alpha())
        self._apply_new_color(color)

    def _on_format_btn_clicked(self) -> None:
        self._value_format = next_color_format(self._value_format)
        self._format_btn.update_region("_main", text=color_format_label(self._value_format))
        self._hex_edit.setText(
            format_color_value(self._color, self._value_format, include_alpha=self._show_alpha)
        )

    def _on_recent_picked(self, color: QColor) -> None:
        if not color.isValid():
            return
        self._apply_new_color(color)

    def _on_rgb_changed(self, _value: int) -> None:
        if self._updating:
            return
        color = QColor(self._r_spin.value(), self._g_spin.value(), self._b_spin.value(), self._color.alpha())
        self._apply_new_color(color, resync_rgb=False)

    def _on_accept(self) -> None:
        # Recents are always stored as hex regardless of the field's format.
        self._recents_store.add(format_color_value(self._color, ValueFormat.HEX, include_alpha=True))
        self.colorSelected.emit(QColor(self._color))
        self.accept()


ColorPickerDialog.inspect_spec = InspectSpec(
    family="ColorPickerDialog",
    state=(
        SpecField("color", "color"),
        SpecField("show_alpha", "_show_alpha", private=True),
        SpecField("value_format", "_value_format", private=True),
    ),
    docs="docs/dev/widgets/color_picker_dialog.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
ColorPickerDialog.widget_descriptor = WidgetDescriptor(
    family=ColorPickerDialog.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ColorPickerDialog.inspect_spec, 'config', ()),
        state=ColorPickerDialog.inspect_spec.state,
        token_family=getattr(ColorPickerDialog.inspect_spec, 'token_family', ()),
        regions=getattr(ColorPickerDialog.inspect_spec, 'regions', False),
        layers=getattr(ColorPickerDialog.inspect_spec, 'layers', False),
        docs=getattr(ColorPickerDialog.inspect_spec, 'docs', ''),
        preview_seed=getattr(ColorPickerDialog.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ColorPickerDialog.inspect_spec, 'apply_config_refresh', None),
    ),
)
