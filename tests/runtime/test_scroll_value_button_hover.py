"""ScrollValueButton hover must cover the full grouped capsule after split."""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtGui import QEnterEvent

from ui.widgets.scroll_value_button import ScrollValueButton


def _enter(button: ScrollValueButton, pos: QPoint) -> None:
    local = QPoint(pos).toPointF()
    event = QEnterEvent(local, local, button.mapToGlobal(pos))
    button.enterEvent(event)


def test_hover_split_covers_both_grouped_regions(qtbot):
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=4)
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    _enter(button, button.rect().center())

    assert button._hovered_split is True
    assert {r.id for r in button.regions()} == {"icon", "value"}
    assert button.region("icon").hovered
    assert button.region("value").hovered


def test_hover_split_toggle_button_covers_main_and_value(qtbot):
    button = ScrollValueButton(
        icon=None,
        toggle=True,
        min_value=0,
        max_value=10,
        start=3,
    )
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    _enter(button, button.rect().center())

    assert {r.id for r in button.regions()} == {"_main", "value"}
    assert button.region("_main").hovered
    assert button.region("value").hovered


def test_value_change_while_hovered_keeps_group_wash(qtbot):
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=2)
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    _enter(button, button.rect().center())
    button.set_value(5)

    assert button.region("icon").hovered
    assert button.region("value").hovered


def test_split_regions_clip_their_own_content(qtbot):
    """Icon and value regions must clip content to their own rects.

    Regression: the regions carry ``group=`` (needed for the shared hover
    wash), which disables the toolkit's default per-region content clip —
    so the digit capsule of the bottom "value" region (taller than the
    region for multi-digit values) bled up into the icon region, and the
    icon itself was not contained either. ``clip_content=True`` on both
    regions restores the clip.
    """
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=4)
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    button._set_hover_split(True)
    assert {r.id for r in button.regions()} == {"icon", "value"}
    for region in button.regions():
        assert region.clip_content is True


def test_digit_capsule_stays_inside_value_region(qtbot):
    """The digit backdrop never pokes into the icon region above it.

    The capsule is sized to the digit + padding, which is taller than the
    bottom split region for multi-digit values; the layer clamps it to the
    region rect (``intersected``) so it cannot overlap the icon region.
    """
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFontMetrics

    from sli_ui_toolkit.managers import scaled_px
    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    from ui.widgets.scroll_value_button import (
        _CAPSULE_PAD_X,
        _CAPSULE_PAD_Y,
        _ValueOverUnderlineLayer,
    )

    button = ScrollValueButton(icon=None, min_value=0, max_value=20, start=10)
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)
    button._set_hover_split(True)

    from sli_ui_toolkit.ui.widgets.buttons.context import DrawContext
    from sli_ui_toolkit.ui.widgets.buttons.painter import Painter

    ctx = DrawContext(
        widget=button,
        painter=None,
        rect=QRectF(button.rect()),
        states=frozenset(),
        variant="default",
        corner_radius=6,
    )
    value_rect = None
    for scoped in button.iter_regions(ctx):
        if scoped.region_id == "value":
            value_rect = scoped.effective_rect
            break
    assert value_rect is not None

    font = ui_font(pixel_size=12)
    fm = QFontMetrics(font)
    width = fm.horizontalAdvance("10") + 2 * scaled_px(_CAPSULE_PAD_X)
    height = fm.height() + 2 * scaled_px(_CAPSULE_PAD_Y)
    center = value_rect.center()
    capsule = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)

    # The unclamped capsule is taller than the value region (the bleed).
    assert capsule.height() > value_rect.height()

    clamped = capsule.intersected(QRectF(value_rect))
    assert clamped.top() >= value_rect.top()
    assert clamped.bottom() <= value_rect.bottom()
    assert clamped.width() == capsule.width()  # horizontal never overflows
    assert clamped == _ValueOverUnderlineLayer._clamp_capsule(
        capsule, QRectF(value_rect)
    )


def test_value_flyout_label_reflows_after_live_scale_change(qtbot):
    """The cached value flyout must grow its label with the UI scale.

    Regression: ``_ScrollValueFlyout`` pinned the digit label with
    ``setFixedSize(scaled_px(22), scaled_px(20))`` computed once at
    construction, and the flyout is cached per button across UiScale
    changes — after raising the factor the digit's font re-resolves live
    while the label stayed at the old design size, so the text overflowed
    and clipped against the panel's rounded corners. A minimum size (not a
    fixed one) lets ``show_aligned``'s ``adjustSize`` reflow it.
    """
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.managers import UiScale

    from ui.widgets.scroll_value_button import _ScrollValueFlyout

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 300)
    host.show()

    UiScale.get_instance().set_factor(1.0)
    flyout = _ScrollValueFlyout(host)  # created/cached at scale 1.0
    flyout.show_value("10", anchor=host)
    qtbot.waitExposed(host)

    assert flyout._label.width() == 22  # design minimum while the digit fits

    try:
        UiScale.get_instance().set_factor(2.0)
        flyout.show_value("10", anchor=host)  # re-show -> reflows
        qtbot.wait(10)

        digit_w = QFontMetrics(flyout._label.font()).horizontalAdvance("10")
        assert flyout._label.width() >= digit_w, (
            f"label {flyout._label.width()}px too narrow for the scaled "
            f"digit ({digit_w}px) — text clips against the panel corners"
        )
        assert flyout._label.width() > 22  # grew past the stale fixed size
        assert flyout.sizeHint().width() > flyout._label.width()
    finally:
        UiScale.get_instance().set_factor(1.0)