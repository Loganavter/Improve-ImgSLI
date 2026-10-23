"""Two owner-reported ScrollValueButton defects (2026-10-23):

1. At value 0 — the control's own "hidden" state (``zero_icon``) — the always-
   visible colour underline was still painted (the 1 px minimum of the ramp).
   Nothing on canvas corresponds to that line, so it must not be drawn.
2. On hover the digit's capsule resolved the IDLE background family while the
   button body was hovered: the value region is created *while* the pointer is
   already inside (the HoverCoordinator's app filter sees Enter before the
   widget's own ``enterEvent`` builds the split), and a region added to an
   already-hovered group used to start idle. The toolkit now restores the
   group's state on rebuild; the capsule then matches the body exactly.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QColor, QEnterEvent
from PySide6.QtWidgets import QApplication

from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from sli_ui_toolkit.managers import ThemeManager
from ui.widgets.scroll_value_button import ScrollValueButton

LINE = QColor(229, 57, 53)


def _themed(qapp):
    # Palette only, no QSS: the pixel assertions describe the toolkit painter
    # output (the capsule is a painter mask), not whatever a stylesheet adds.
    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme("light")
    return tm


def _button(qtbot, *, value: int, show_underline: bool = True) -> ScrollValueButton:
    button = ScrollValueButton(
        icon=None,
        show_underline=show_underline,
        min_value=0,
        max_value=10,
        zero_icon="divider_hidden",
    )
    button.setUnderlineColor(LINE)
    button.set_value(value, emit=False)
    button.resize(36, 36)
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)
    return button


def _line_rows(button: ScrollValueButton) -> list[int]:
    """Rows at the bottom that carry the red indicator (>= 1/3 of the width)."""
    img = button.grab().toImage()
    width, height = img.width(), img.height()
    rows = []
    for y in range(max(0, height - 8), height):
        hits = sum(
            1
            for x in range(width)
            if (lambda c: c.red() > 150 and c.green() < 120)(img.pixelColor(x, y))
        )
        if hits > width // 3:
            rows.append(y)
    return rows


def _enter_through_app(button: ScrollValueButton) -> None:
    """Dispatch a real Enter so the HoverCoordinator filter runs first."""
    pos = QPoint(button.rect().center())
    local = QPointF(pos)
    QApplication.sendEvent(
        button, QEnterEvent(local, local, button.mapToGlobal(pos))
    )
    QApplication.processEvents()


def test_zero_state_paints_no_underline(qtbot, qapp):
    _themed(qapp)
    button = _button(qtbot, value=0)

    assert button._underline_visible is True  # the host asked for it
    assert button._show_underline is False  # …but the zero state has nothing to show
    assert _line_rows(button) == []


def test_nonzero_state_paints_the_underline(qtbot, qapp):
    _themed(qapp)
    button = _button(qtbot, value=4)

    assert _line_rows(button), "expected the divider-colour underline at value 4"


def test_crossing_zero_toggles_the_line(qtbot, qapp):
    _themed(qapp)
    button = _button(qtbot, value=3)
    assert _line_rows(button)

    button.set_value(0)
    QApplication.processEvents()
    assert _line_rows(button) == []

    button.set_value(6)
    QApplication.processEvents()
    assert _line_rows(button)


def test_hovered_value_region_resolves_the_hover_wash(qtbot, qapp):
    """The digit's capsule is resolved from the value region: it must carry
    the hover wash, not only the idle base (owner: "the digit looks painted
    outside the hover family")."""
    from PySide6.QtGui import QImage, QPainter

    from sli_ui_toolkit.ui.widgets.buttons.layers.background import BackgroundLayer
    from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState

    tm = _themed(qapp)
    button = _button(qtbot, value=5)

    _enter_through_app(button)

    assert button._hovered_split is True
    assert button.region("value").hovered

    image = QImage(button.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        ctx = button._make_context(painter)
        scoped = next(c for c in button.iter_regions(ctx) if c.region_id == "value")
        layers, _border = BackgroundLayer._resolve(scoped, tm)
    finally:
        painter.end()

    assert ButtonState.HOVERED in scoped.effective_states
    assert len(layers) >= 2, (
        "value region resolved base only — the capsule would be the idle "
        f"colour on a hovered body: {[c.name() for c in layers]}"
    )
