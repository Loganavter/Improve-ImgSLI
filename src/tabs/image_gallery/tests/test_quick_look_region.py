"""Quick Look region inspection — pure mapping, prompt, band paint.

The live gesture needs a real canvas+overlay; the pure inverse mapping, the
region system prompt and the band widget are covered here. Falsification: with
the pre-feature build ``widget_rect_to_normalized`` and
``ASK_REGION_SYSTEM_PROMPT`` do not exist (ImportError).
"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QWidget

from tabs.image_gallery.services.ask_prompt import (
    ASK_REGION_SYSTEM_PROMPT,
    ASK_SYSTEM_PROMPT,
)
from tabs.image_gallery.ui.quick_look.preview_zoom import widget_rect_to_normalized
from tabs.image_gallery.ui.quick_look.region import RegionBand


def test_widget_rect_to_normalized_fit_identity() -> None:
    # Perfect fit at zoom 1: the framebuffer IS the image.
    assert widget_rect_to_normalized(
        (0, 0, 50, 50), 200, 200, 100, 100, 1.0, 0.0, 0.0
    ) == (0.0, 0.0, 0.5, 0.5)


def test_widget_rect_to_normalized_zoom_centered_quarter() -> None:
    # zoom 2, pan 0 → the visible fb window is the centered half of the image.
    box = widget_rect_to_normalized((0, 0, 100, 100), 200, 200, 100, 100, 2.0, 0.0, 0.0)
    assert box is not None
    left, top, right, bottom = box
    assert abs(left - 0.25) < 1e-6 and abs(top - 0.25) < 1e-6
    assert abs(right - 0.75) < 1e-6 and abs(bottom - 0.75) < 1e-6


def test_widget_rect_to_normalized_degenerate_is_none() -> None:
    assert (
        widget_rect_to_normalized((10, 10, 10, 10), 200, 200, 100, 100, 1.0, 0.0, 0.0)
        is None
    )
    assert (
        widget_rect_to_normalized((0, 0, 10, 10), 0, 0, 100, 100, 1.0, 0.0, 0.0)
        is None
    )


def test_widget_rect_to_normalized_clamps_out_of_bounds() -> None:
    assert widget_rect_to_normalized(
        (-50, -50, 500, 500), 100, 100, 100, 100, 1.0, 0.0, 0.0
    ) == (0.0, 0.0, 1.0, 1.0)


def test_region_prompt_is_distinct_and_mentions_region() -> None:
    assert ASK_REGION_SYSTEM_PROMPT
    assert ASK_REGION_SYSTEM_PROMPT != ASK_SYSTEM_PROMPT
    assert "region" in ASK_REGION_SYSTEM_PROMPT.lower()


def test_region_band_paints_and_clears(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(200, 200)
    band = RegionBand(host)
    qtbot.addWidget(band)
    band.setGeometry(host.rect())
    band.set_band(QRect(10, 10, 50, 40))
    band.show()
    band.grab()  # must not raise
    band.clear()
    band.grab()
