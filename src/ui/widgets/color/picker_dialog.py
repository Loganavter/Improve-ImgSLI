"""Themed color picker — app-level replacement for the system ``QColorDialog``.
Non-modal, resizable ``QDialog`` (custom title bar via the app-wide CSD
auto-decorator, see ``shared_toolkit.ui.decorate_dialog``) built from toolkit
atoms so it matches the rest of the app instead of the OS-native picker: an
SV square (custom, not a linear control) + a hue ``Slider`` + an alpha
``Slider`` (vertical, filled with a spectrum/checkerboard ``track_painter``
instead of the default flat track), a color-value ``CustomLineEdit`` plus
a small format-cycle button that switches the value between ``HEX``
(``#RRGGBB`` / ``#RRGGBBAA`` when alpha editing is on), ``RGB`` and ``HSL``
representations (see ``color_value_format``), RGB ``SpinBox`` fields, a
before/after preview chip and a recent-colors chip row
(``color_picker_recents``). Return/Enter accepts.

Kept API-compatible with the subset of ``QColorDialog`` the callers used
(``colorSelected``, ``finished``, ``show``/``raise_``/``activateWindow``,
``setWindowTitle``) so call sites only need to swap the constructor and
``setOption(ShowAlphaChannel, ...)`` -> ``set_show_alpha(...)``.
Audit-Meta: pattern=qdialog-wiring reason="one ColorPicker QDialog — picker + fields + preview wiring"
"""

from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontMetrics,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from resources.translations import tr
from shared_toolkit.ui.layout_sizing import GeometryApplyPolicy, apply_dialog_geometry
from shared_toolkit.ui.themed_dialog import ThemedDialog
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button, CustomLineEdit, Label, Slider, SpinBox

from ui.theming import try_resolve_theme_color
from ui.widgets.color.recents import (
    RecentColorsRow,
    RecentColorsStore,
    checkerboard_brush,
)
from ui.widgets.color.value_format import (
    ValueFormat,
    color_format_label,
    color_value_has_alpha,
    format_color_value,
    next_color_format,
    parse_color_value,
)

_MIN_WIDTH = scaled_px(260)
_MIN_HEIGHT = scaled_px(300)
_MAX_WIDTH = scaled_px(640)

# Size (not position — always centers on the parent window) is remembered
# across opens via QSettings, same mechanism as settings/export/help/
# image-properties. Message/alert dialogs intentionally do not opt into this.
_GEOMETRY_POLICY = GeometryApplyPolicy(
    resize_when_hidden=True,
    update_minimum=True,
    minimum_floor=(_MIN_WIDTH, _MIN_HEIGHT),
    width_bounds=(_MIN_WIDTH, _MAX_WIDTH),
    center_on_parent=True,
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

    The gradient fills the full widget edge-to-edge (so clicking exactly at
    a border reaches the true 0/1 extreme) and hit-testing maps 1:1 against
    that same full rect. Only the drawn cursor position is clamped inward by
    ``THUMB_RADIUS`` so the ring never paints partway outside the field —
    at extreme values it hugs the inside of the edge instead of centering
    exactly on it.
    """

    svChanged = Signal(float, float)

    THUMB_RADIUS = scaled_px(9.0)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(scaled_px(160), scaled_px(120))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._hue = 0.0
        self._sat = 1.0
        self._val = 1.0
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

    def set_hue(self, hue_deg: float) -> None:
        self._hue = hue_deg
        self.update()

    def set_sv(self, sat: float, val: float) -> None:
        self._sat = max(0.0, min(1.0, sat))
        self._val = max(0.0, min(1.0, val))
        self.update()

    def _thumb_center(self, rect: QRectF) -> QPointF:
        margin = self.THUMB_RADIUS + 1.6
        raw_x = rect.left() + self._sat * rect.width()
        raw_y = rect.top() + (1.0 - self._val) * rect.height()
        x = min(max(raw_x, rect.left() + margin), rect.right() - margin)
        y = min(max(raw_y, rect.top() + margin), rect.bottom() - margin)
        return QPointF(x, y)

    def _set_from_pos(self, pos: QPointF) -> None:
        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        sat = max(0.0, min(1.0, (pos.x() - rect.left()) / rect.width()))
        val = max(0.0, min(1.0, 1.0 - (pos.y() - rect.top()) / rect.height()))
        if sat != self._sat or val != self._val:
            self._sat, self._val = sat, val
            self.update()
            self.svChanged.emit(sat, val)

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
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 8.0

        hue_color = QColor.fromHsvF(self._hue / 360.0, 1.0, 1.0)
        sat_gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        # Saturation endpoint: intrinsic white (HSV model) — keep visual white
        # but allow theme override via surface.background alias (dialog.background)
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

        center = self._thumb_center(rect)
        thumb_radius = self.THUMB_RADIUS
        # Thumb rings: high-contrast white + soft dark outline — tokenized via
        # slider.thumb.outer (alias surface.background) and shadow.color
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


class _PreviewChip(QWidget):
    """Circular before/after color comparison, split down the middle.

    Each half is painted over its own checkerboard tile first, so partial
    alpha in either color is actually visible instead of blending into
    whatever the other half happened to be (which previously made low-alpha
    colors look fully opaque).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(scaled_px(34), scaled_px(34))
        # Neutral preview defaults: themed dialog.background / surface.background
        _tm = ThemeManager.get_instance()
        self._before = _themed_or_fallback(_tm, "dialog.background", QColor(255, 255, 255))
        self._after = _themed_or_fallback(_tm, "dialog.background", QColor(255, 255, 255))
        self.theme_manager = _tm
        self.theme_manager.theme_changed.connect(self.update)

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
    ) -> None:
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        # Fallback initial white via theme token (surface.background alias dialog.background)
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
        self.set_show_alpha(show_alpha)
        self._preview.set_before(self._color)
        self._sync_from_color()
        self._apply_dialog_geometry()
        self.install_dialog_geometry(self._apply_dialog_geometry)

        return_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        return_shortcut.activated.connect(self._on_accept)
        enter_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Enter), self)
        enter_shortcut.activated.connect(self._on_accept)

        self.mark_theme_ui_ready()

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
        title_width = QFontMetrics(self.font()).horizontalAdvance(self.windowTitle()) + scaled_px(88)
        width = max(content_hint.width(), min(_MAX_WIDTH, title_width))
        apply_dialog_geometry(self, width, content_hint.height(), policy=_GEOMETRY_POLICY)

    def _build_ui(self, *, ok_text: str, cancel_text: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            scaled_px(16), scaled_px(14), scaled_px(16), scaled_px(14)
        )
        root.setSpacing(scaled_px(12))

        picker_row = QHBoxLayout()
        picker_row.setSpacing(scaled_px(10))
        self._sv = _SVSquare(self)
        self._sv.svChanged.connect(self._on_sv_changed)
        picker_row.addWidget(self._sv, 1)

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
        self._hue_slider.setMinimumHeight(scaled_px(140))
        self._hue_slider.valueChanged.connect(self._on_hue_changed)
        picker_row.addWidget(self._hue_slider)

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
        self._alpha_slider.setMinimumHeight(scaled_px(140))
        self._alpha_slider.valueChanged.connect(self._on_alpha_changed)
        picker_row.addWidget(self._alpha_slider)

        root.addLayout(picker_row, 1)

        fields_row = QHBoxLayout()
        fields_row.setSpacing(scaled_px(6))

        # Leading stretch pins the whole fields group (preview chip, labels,
        # inputs) to the right edge. It also absorbs the dialog slack so the
        # gaps between the fixed-size items never grow on relayout — without
        # it QBoxLayout redistributes extra width between the items and the
        # fields visibly drift while the dialog is being resized.
        fields_row.addStretch(1)

        self._preview = _PreviewChip(self)
        fields_row.addWidget(self._preview)

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
        fields_row.addWidget(self._hex_edit)

        self._format_btn = Button(text="HEX", variant="surface", parent=self)
        self._format_btn.setFixedSize(scaled_px(46), scaled_px(26))
        self._format_btn.setToolTip(
            tr("ui.color_value_format_cycle_tooltip", default="Change color value format (HEX/RGB/HSL)")
        )
        self._format_btn.clicked.connect(self._on_format_btn_clicked)
        fields_row.addWidget(self._format_btn)

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
            fields_row.addWidget(_field_label(text))
            fields_row.addWidget(spin)

        self._alpha_label = _field_label("A")
        self._a_spin = SpinBox(self)
        self._a_spin.setRange(0, 255)
        self._a_spin.valueChanged.connect(self._on_alpha_spin_changed)
        fields_row.addWidget(self._alpha_label)
        fields_row.addWidget(self._a_spin)

        root.addLayout(fields_row)

        self._recents_row = RecentColorsRow(
            self,
            caption=tr("ui.recent_colors_caption", default="Recent"),
        )
        self._recents_row.recentPicked.connect(self._on_recent_picked)
        self._recents_row.set_colors(self._recents_store.load())
        root.addWidget(self._recents_row)

        actions = QHBoxLayout()
        actions.setSpacing(scaled_px(8))
        actions.addStretch(1)
        self._cancel_btn = Button(text=cancel_text, variant="surface", parent=self)
        self._cancel_btn.setMinimumSize(scaled_px(72), scaled_px(30))
        self._cancel_btn.clicked.connect(self.reject)
        actions.addWidget(self._cancel_btn)
        self._ok_btn = Button(text=ok_text, variant="surface", parent=self)
        self._ok_btn.setMinimumSize(scaled_px(72), scaled_px(30))
        self._ok_btn.clicked.connect(self._on_accept)
        actions.addWidget(self._ok_btn)
        root.addLayout(actions)

    def set_show_alpha(self, enabled: bool) -> None:
        self._show_alpha = bool(enabled)
        self._alpha_slider.setVisible(self._show_alpha)
        self._alpha_label.setVisible(self._show_alpha)
        self._a_spin.setVisible(self._show_alpha)
        self._hex_edit.setText(
            format_color_value(self._color, self._value_format, include_alpha=self._show_alpha)
        )

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
