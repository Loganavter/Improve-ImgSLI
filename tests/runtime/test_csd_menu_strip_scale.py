"""CSD menu trigger widths must cover the real painted content at any scale.

Regression: ``_estimate_menu_button_width`` divided the design constants
(icon size, gap, padding) by the UiScale factor together with the measured
text advance. The constants are design values — ``Button(size=...)`` scales
them exactly once — so at factor > 1.0 the trigger came out narrower than
its painted content (scaled icon + gap + text + padding), and the label
elided to "…" (visible on the File trigger, which carries the app icon).
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFontMetrics

from sli_ui_toolkit.managers import UiScale, scaled_px, ui_font
from ui.main_window.csd_menu_strip import _estimate_menu_button_width

_LABEL = "Файл"
_FACTORS = (1.0, 1.25, 1.5, 2.0)


@pytest.fixture(autouse=True)
def _restore_ui_scale():
    """Parametrized scale tests must not leave the process-wide factor changed
    for later tests in the same process."""
    yield
    UiScale.get_instance().set_factor(1.0)


def _painted_content_width(*, has_icon: bool, icon_size: int, gap: int, pad: int) -> int:
    text_w = QFontMetrics(ui_font()).horizontalAdvance(_LABEL)
    if not has_icon:
        return text_w
    return scaled_px(pad) + scaled_px(icon_size) + scaled_px(gap) + text_w + scaled_px(pad)


@pytest.mark.parametrize("factor", _FACTORS)
def test_icon_trigger_width_covers_painted_content(qapp, factor):
    """The File trigger (app icon + label) must never elide the label."""
    UiScale.get_instance().set_factor(factor)
    design_w = _estimate_menu_button_width(
        _LABEL,
        28,
        has_icon=True,
        icon_size=16,
        gap=8,
        content_pad=6,
    )
    button_w = scaled_px(design_w)
    painted = _painted_content_width(has_icon=True, icon_size=16, gap=8, pad=6)
    assert button_w >= painted, (
        f"factor {factor}: trigger {button_w}px < painted content {painted}px — "
        "the label will elide to '…'"
    )


@pytest.mark.parametrize("factor", _FACTORS)
def test_text_trigger_width_covers_painted_content(qapp, factor):
    """The Help-style trigger (label only) keeps its margin at any scale."""
    UiScale.get_instance().set_factor(factor)
    design_w = _estimate_menu_button_width(_LABEL, 28, has_icon=False)
    button_w = scaled_px(design_w)
    painted = _painted_content_width(has_icon=False, icon_size=0, gap=0, pad=0)
    assert button_w >= painted, (
        f"factor {factor}: trigger {button_w}px < painted content {painted}px"
    )