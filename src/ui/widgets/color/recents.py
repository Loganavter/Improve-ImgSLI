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
  (``_SVSquare``/``_PreviewChip`` pattern from ``color_picker_dialog``)
  because alpha < 255 colors must sit on a checkerboard, which the toolkit
  ``Button`` painter pipeline cannot do.

Hex storage format is ``#RRGGBB`` or ``#RRGGBBAA`` — the latter is parsed
manually because ``QColor`` parses 8-digit strings as ``#AARRGGBB``
(verified on PySide6 6.11; ``QColor.NameFormat.HexAarrgb`` does not exist
there either).
"""

from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from PySide6.QtCore import QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.theme import ThemeManager

from ui.theming import resolve_theme_color
from ui.widgets.shelf import ShelfWidget

RECENT_COLORS_CAP = 12

_SETTINGS_KEY = "color_picker/recents"

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
    """

    picked = Signal(QColor)

    SIZE = scaled_px(64)
    CORNER_RADIUS = scaled_px(10.0)
    SWATCH_RADIUS = scaled_px(6.0)
    SWATCH_PADDING = scaled_px(6.0)
    HOVER_RING_WIDTH = 2.0

    def __init__(self, hex_code: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        color = parse_hex_color(hex_code)
        self._color = color if color is not None else QColor("#000000")
        self._hovered = False
        self._pressed = False
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

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
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = self.CORNER_RADIUS

        swatch = rect.adjusted(
            self.SWATCH_PADDING, self.SWATCH_PADDING,
            -self.SWATCH_PADDING, -self.SWATCH_PADDING,
        )
        path = QPainterPath()
        path.addRoundedRect(swatch, self.SWATCH_RADIUS, self.SWATCH_RADIUS)
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
            painter.setPen(QPen(accent, self.HOVER_RING_WIDTH))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)


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
            surface_token="dialog.background",
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

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._chip_widgets:
            self._relayout_chips()

    def _relayout_chips(self) -> None:
        """Wrap chips onto rows that fit the current shelf width."""
        chips = self._chip_widgets
        if not chips:
            return
        size = _RecentColorChip.SIZE
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
