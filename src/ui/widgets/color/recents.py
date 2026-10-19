"""Recent-color persistence and the picker's recents chip row.

Two pieces, app-side (picker integration is a product concern, not a
toolkit widget):

- ``RecentColorsStore`` — QSettings-backed list of hex codes, capped and
  deduped, written only when the picker accepts a color.
- ``RecentColorsRow`` + ``_RecentColorChip`` — a shelf section built on the
  shared ``ShelfWidget`` (``ui.widgets.shelf``, same component as the Session
  Picker Recent shelf): the caption goes to the shelf header, a horizontal
  row of small card-style swatch chips to the content host; clicking a chip
  applies that color (does not close the dialog). Chips are custom-painted
  (``_SVSquare``/``_PreviewChip`` pattern from ``picker_dialog``)
  because alpha < 255 colors must sit on a checkerboard, which the toolkit
  ``Button`` painter pipeline cannot do.

Hex storage format is ``#RRGGBB`` or ``#RRGGBBAA`` — the latter is parsed
manually because ``QColor`` parses 8-digit strings as ``#AARRGGBB``
(verified on PySide6 6.11; ``QColor.NameFormat.HexAarrgb`` does not exist
there either).
"""

from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import shiboken6
from PySide6.QtCore import QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.layout_settle import settle_layout
from sli_ui_toolkit.ui.managers import connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_FONT, AXIS_SCALE
from sli_ui_toolkit.ui.widgets.buttons.context import DrawContext
from sli_ui_toolkit.ui.widgets.buttons.layers.focus import FocusLayer as _FocusLayer

from ui.theming import resolve_theme_color
from ui.widgets.shelf import ShelfWidget

RECENT_COLORS_CAP = 12

# One stateless toolkit layer instance shared by every chip (the layer reads
# the widget off the DrawContext, same as the painter pipeline).
_FOCUS_LAYER = _FocusLayer()

_SETTINGS_KEY = "color_picker/recents"

# Chip chrome in DESIGN px — resolved with ``scaled_px`` at use time (per
# instance, see ``_RecentColorChip.apply_metrics``), never at import time:
# a class-level ``scaled_px(...)`` bakes the launch scale factor in and the
# chips could never follow a later interface-scale change.
_CHIP_SIZE_DP = 64
_CHIP_CORNER_RADIUS_DP = 10.0
_CHIP_SWATCH_RADIUS_DP = 6.0
_CHIP_SWATCH_PADDING_DP = 6.0
# Gutter between the chip's outer edge and its content (swatch + chrome): the
# FocusLayer ring is painted inside the content rect, so without a gutter the
# ring sits flush against the widget border and reads as part of the swatch
# (owner report 2026-10-19). Design px; resolved per instance in
# ``apply_metrics`` because a class-level value would freeze at import.
_CHIP_FOCUS_GUTTER_DP = 2.0

# Assumed content-well width (design px) for the pre-layout chip wrap: the
# picker dialog's max width (640) minus its shelf root margins (32) minus
# the chips margins (16). Keeps the initial sizeHint to ~2 rows of chips.
_MAX_DIALOG_WELL_WIDTH = 592


def checkerboard_brush(is_dark: bool) -> QBrush:
    """Small tiled checkerboard used behind alpha-revealing paints."""
    tile = QPixmap(8, 8)
    base = QColor(74, 74, 74) if is_dark else QColor(255, 255, 255)
    alt = QColor(92, 92, 92) if is_dark else QColor(216, 220, 227)
    tile.fill(base)
    painter = QPainter(tile)
    painter.fillRect(0, 0, 4, 4, alt)
    painter.fillRect(4, 4, 4, 4, alt)
    painter.end()
    return QBrush(tile)


def parse_hex_color(text: str) -> QColor | None:
    """Parse ``#RRGGBB`` / ``#RRGGBBAA`` (leading ``#`` optional).

    8-digit input is read as RRGGBBAA, matching the format this module
    writes — NOT Qt's ``#AARRGGBB`` interpretation, which would silently
    swap alpha and the red channel.
    """
    body = str(text or "").strip().lstrip("#")
    if len(body) == 8:
        color = QColor(f"#{body[:6]}")
        if not color.isValid():
            return None
        try:
            color.setAlpha(int(body[6:8], 16))
        except ValueError:
            return None
        return color
    if len(body) != 6:
        return None
    color = QColor(f"#{body}")
    return color if color.isValid() else None


def color_to_hex_string(color: QColor, *, include_alpha: bool = False) -> str:
    """Canonical storage/display hex: ``#RRGGBB`` or, when alpha < 255 and
    ``include_alpha``, ``#RRGGBBAA``."""
    if include_alpha and color.alpha() < 255:
        return (
            f"#{color.red():02X}{color.green():02X}{color.blue():02X}{color.alpha():02X}"
        )
    return color.name(QColor.NameFormat.HexRgb).upper()


class RecentColorsStore:
    """QSettings-backed recent color list, most-recent-first, capped."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings if settings is not None else QSettings()

    def load(self) -> list[str]:
        raw = self._settings.value(_SETTINGS_KEY, [])
        codes: list[str] = []
        for item in raw if isinstance(raw, list) else []:
            color = parse_hex_color(str(item))
            if color is None:
                continue
            code = color_to_hex_string(color, include_alpha=True)
            if code in codes:
                continue
            codes.append(code)
            if len(codes) >= RECENT_COLORS_CAP:
                break
        return codes

    def add(self, hex_code: str) -> None:
        color = parse_hex_color(hex_code)
        if color is None:
            return
        code = color_to_hex_string(color, include_alpha=True)
        codes = [c for c in self.load() if c != code]
        codes.insert(0, code)
        self._settings.setValue(_SETTINGS_KEY, codes[:RECENT_COLORS_CAP])


class _RecentColorChip(QWidget):
    """Large card-style swatch chip with hover/pressed states.

    The color fills the card with an inset swatch over a checkerboard when
    the color is translucent. Resting state has no chrome (no outline, no
    accent backing); hover draws an accent ring, pressed dims the swatch —
    interactive feedback like a toolkit ``Button``, but custom-painted
    because the ``Button`` pipeline cannot checkerboard alpha < 255 colors.

    Keyboard-reachable: ``StrongFocus`` so the picker's row section
    (``ToolbarRowsSection``) can land on it, Enter/Space activate the same
    ``picked`` signal a click does, and the toolkit's own ``FocusLayer`` draws
    the ring (guide §12: a ``NoFocus`` child is invisible to navigation).
    """

    picked = Signal(QColor)

    HOVER_RING_WIDTH_DP = 2.0

    def __init__(self, hex_code: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.apply_metrics()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        color = parse_hex_color(hex_code)
        self._color = color if color is not None else QColor("#000000")
        self._hovered = False
        self._pressed = False
        # FocusLayer.applies() requires this exact attribute (Button/Flyout
        # convention) — modality from the last input device, not FocusReason.
        self._keyboard_focus = False
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

    def apply_metrics(self) -> None:
        """Re-resolve this chip's chrome px from design space at use time."""
        self._corner_radius = float(scaled_px(_CHIP_CORNER_RADIUS_DP))
        self._swatch_radius = float(scaled_px(_CHIP_SWATCH_RADIUS_DP))
        self._swatch_padding = float(scaled_px(_CHIP_SWATCH_PADDING_DP))
        self._focus_gutter = float(scaled_px(_CHIP_FOCUS_GUTTER_DP))
        size = scaled_px(_CHIP_SIZE_DP)
        self.setFixedSize(size, size)
        self.update()

    def content_rect(self) -> QRectF:
        """The chip's content box: the widget rect inset by the focus gutter.

        The swatch, hover ring and the FocusLayer focus ring all draw inside
        this box. The gutter is what visually separates the ring from the
        swatch instead of leaving the ring flush on the chip's outer edge.
        Kept as a method (not a cached rect) because the gutter and size are
        re-derived on scale changes.
        """
        gutter = self._focus_gutter
        return QRectF(self.rect()).adjusted(gutter, gutter, -gutter, -gutter)

    def focusInEvent(self, event) -> None:  # noqa: N802
        try:
            from sli_ui_toolkit.ui.managers.navigation_manager import (
                resolve_keyboard_focus,
            )

            self._keyboard_focus = resolve_keyboard_focus(event.reason())
        except Exception:
            self._keyboard_focus = True
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._keyboard_focus = False
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.picked.emit(QColor(self._color))
            event.accept()
            return
        # Everything else (incl. Esc) stays native: arrows are the picker row
        # section's, Esc propagates to the dialog's reject().
        super().keyPressEvent(event)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(event.position().toPoint()):
                self.picked.emit(QColor(self._color))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Every visible part lives inside the content rect: the focus gutter
        # keeps the FocusLayer ring off the widget edge (see content_rect).
        rect = self.content_rect().adjusted(0.5, 0.5, -0.5, -0.5)
        radius = self._corner_radius

        swatch = rect.adjusted(
            self._swatch_padding, self._swatch_padding,
            -self._swatch_padding, -self._swatch_padding,
        )
        path = QPainterPath()
        path.addRoundedRect(swatch, self._swatch_radius, self._swatch_radius)
        painter.save()
        painter.setClipPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._color.alpha() < 255:
            painter.setBrush(checkerboard_brush(self.theme_manager.is_dark()))
            painter.drawRect(swatch)
        painter.setBrush(self._color)
        painter.drawRect(swatch)
        painter.restore()

        if self._pressed:
            # Dim the swatch while pressed — simple, no tint over the color.
            painter.save()
            painter.setClipPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 45))
            painter.drawRect(swatch)
            painter.restore()

        if self._hovered or self._pressed:
            accent = resolve_theme_color(self.theme_manager, "button.default.border")
            painter.setPen(QPen(accent, scaled_px(self.HOVER_RING_WIDTH_DP)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

        # Keyboard focus ring — the toolkit's own FocusLayer (same layer every
        # Button uses), so the chip reads as focused exactly like the rest of
        # the app instead of a hand-rolled lookalike.
        focus_ctx = self._focus_ctx(painter)
        if _FOCUS_LAYER.applies(focus_ctx):
            _FOCUS_LAYER.draw(focus_ctx, self.theme_manager)

    def _focus_ctx(self, painter: QPainter) -> DrawContext:
        return DrawContext(
            widget=self,
            painter=painter,
            rect=self.content_rect(),
            states=frozenset(),
            variant="default",
            corner_radius=int(self._corner_radius),
        )


class RecentColorsRow(ShelfWidget):
    """Recent-colors shelf: shared shelf chrome + chips in the content host.

    Built on the same ``ShelfWidget`` as the Session Picker Recent shelf —
    only the contents differ: the title goes to the shelf header and the
    large card-style color chips to the content host, sitting on the
    surface-colored content well like the recent-project cards. Chips wrap
    onto extra rows when the shelf width runs out. The whole shelf (chrome
    included) hides while empty.
    """

    recentPicked = Signal(QColor)

    # Breathing room between the content well edges and the chip grid, matching
    # the session picker's card grid margins (ITEMS_MARGIN*).
    CHIPS_MARGIN_LEFT = 8
    CHIPS_MARGIN_TOP = 16
    CHIPS_MARGIN_RIGHT = 8
    CHIPS_MARGIN_BOTTOM = 16
    CHIPS_SPACING = 10

    def __init__(self, parent: QWidget | None = None, *, caption: str = "") -> None:
        super().__init__(
            parent,
            surface_token="surface.background",
            content_well=True,
        )
        self.set_title(caption)
        self._caption = self.title_label()

        self._chip_widgets: list[_RecentColorChip] = []
        # Chips are positioned manually (``_relayout_chips``) so the wrap is
        # exact; QGridLayout neither stretches inside the well nor
        # left-aligns its columns, and mutating it inside resizeEvent is
        # unreliable.
        self.setVisible(False)
        # Chip card size is scaled chrome: re-size the chips and re-wrap on a
        # live font/scale change (the dialog also calls ``apply_metrics`` before
        # it re-locks its own minimum, so the row works standalone too).
        connect_ui_metrics(
            self,
            self._on_metrics_changed,
            axes=frozenset({AXIS_FONT, AXIS_SCALE}),
        )

    def _on_metrics_changed(self, _axes: frozenset[str] | None = None) -> None:
        self.apply_metrics()

    def apply_metrics(self) -> None:
        """Re-resolve chip sizes + the wrap at the live scale factor."""
        for chip in self._chip_widgets:
            chip.apply_metrics()
        self._relayout_chips()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._chip_widgets:
            self._relayout_chips()

    def _relayout_chips(self) -> None:
        """Wrap chips onto rows that fit the current shelf width."""
        chips = self._chip_widgets
        if not chips:
            return
        size = scaled_px(_CHIP_SIZE_DP)
        spacing = scaled_px(self.CHIPS_SPACING)
        margin_left = scaled_px(self.CHIPS_MARGIN_LEFT)
        margin_top = scaled_px(self.CHIPS_MARGIN_TOP)
        margin_right = scaled_px(self.CHIPS_MARGIN_RIGHT)
        margin_bottom = scaled_px(self.CHIPS_MARGIN_BOTTOM)

        avail = self.width() - margin_left - margin_right
        step = size + spacing
        if avail < 2 * step - spacing:
            # Pre-layout width is garbage (the dialog hands the row ~100px
            # before the first real geometry pass), and a real dialog can
            # never be this narrow (min 260px -> >= 2 chips). Assume the
            # picker dialog's content width (max 640px minus root + chips
            # margins) so the initial sizeHint wraps into rows instead of
            # stacking one column and opening the dialog absurdly tall.
            avail = scaled_px(_MAX_DIALOG_WELL_WIDTH)
        columns = max(1, (avail + spacing) // step)
        for index, chip in enumerate(chips):
            chip.move(
                margin_left + (index % columns) * step,
                margin_top + (index // columns) * step,
            )
        rows = (len(chips) + columns - 1) // columns
        self.content_host().setFixedHeight(
            rows * size + (rows - 1) * spacing + margin_top + margin_bottom
        )

    def live_chips(self) -> list[_RecentColorChip]:
        """Chips still alive and owned by this row (deleted ones dropped)."""
        live: list[_RecentColorChip] = []
        for chip in self._chip_widgets:
            try:
                if shiboken6.isValid(chip):  # type: ignore[attr-defined]
                    live.append(chip)
            except Exception:
                continue
        return live

    def chip_rows(self) -> list[list[_RecentColorChip]]:
        """Live chips grouped into the visual rows the wrap actually produced.

        Derived from the laid-out geometry left by ``_relayout_chips`` (row =
        same top ``y``, ordered by ``x`` inside a row) instead of a recomputed
        column count: a resize or UI-scale change re-wraps the chips, and a
        stale column guess would send keyboard focus to the wrong chip
        (owner report 2026-10-19, the recents shelf is a 2D grid). Rescanned on
        every call — never cached.
        """
        chips = sorted(self.live_chips(), key=lambda chip: (chip.y(), chip.x()))
        rows: list[list[_RecentColorChip]] = []
        for chip in chips:
            if rows and chip.y() == rows[-1][0].y():
                rows[-1].append(chip)
            else:
                rows.append([chip])
        return rows

    def set_colors(self, hex_codes: list[str]) -> None:
        for chip in self._chip_widgets:
            chip.deleteLater()
        self._chip_widgets = []
        for code in hex_codes[:RECENT_COLORS_CAP]:
            chip = _RecentColorChip(code, self.content_host())
            chip.picked.connect(self.recentPicked)
            self._chip_widgets.append(chip)
        self._relayout_chips()
        self.setVisible(bool(self._chip_widgets))
        # The chip wrap derives the content host's fixed height from the
        # chip count while the shelf hosts a QLayout: re-run it now so the
        # header/content distribution agrees in the same frame instead of
        # overflowing for one turn while growing.
        settle_layout(self, self._header_host, self.content_host())


RecentColorsRow.inspect_spec = InspectSpec(
    family="RecentColorsRow",
    state=(
        SpecField("chip_count", lambda w: len(w._chip_widgets), private=True),
        SpecField(
            "caption",
            lambda w: w.title_label().text() if w.title_label() else "",
        ),
    ),
    docs="docs/dev/widgets/recent_colors_row.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
RecentColorsRow.widget_descriptor = WidgetDescriptor(
    family=RecentColorsRow.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(RecentColorsRow.inspect_spec, 'config', ()),
        state=RecentColorsRow.inspect_spec.state,
        token_family=getattr(RecentColorsRow.inspect_spec, 'token_family', ()),
        regions=getattr(RecentColorsRow.inspect_spec, 'regions', False),
        layers=getattr(RecentColorsRow.inspect_spec, 'layers', False),
        docs=getattr(RecentColorsRow.inspect_spec, 'docs', ''),
        preview_seed=getattr(RecentColorsRow.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(RecentColorsRow.inspect_spec, 'apply_config_refresh', None),
    ),
)
