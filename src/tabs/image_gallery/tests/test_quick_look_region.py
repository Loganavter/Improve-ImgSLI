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


def test_region_band_flyout_anchor_rect(qtbot) -> None:
    """The band narrows flyout anchoring to the selection (toolkit hook).

    Falsification: pre-change ``RegionBand`` has no ``flyoutAnchorRect``.
    """
    host = QWidget()
    qtbot.addWidget(host)
    band = RegionBand(host)
    qtbot.addWidget(band)
    assert band.flyoutAnchorRect() is None
    band.set_band(QRect(10, 20, 50, 40))
    assert band.flyoutAnchorRect() == QRect(10, 20, 50, 40)
    band.clear()
    assert band.flyoutAnchorRect() is None


def test_finish_region_keeps_band_visible(qtbot) -> None:
    """A valid selection keeps the band: the flyout anchors to it.

    Falsification: the pre-change ``_finish_region`` hid the band on every
    release — ``isHidden()`` is True on that build.
    """
    from tabs.image_gallery.ui.quick_look import QuickLookOverlay

    host = QWidget()
    qtbot.addWidget(host)
    band = RegionBand(host)
    qtbot.addWidget(band)
    band.setGeometry(host.rect())

    overlay = QuickLookOverlay.__new__(QuickLookOverlay)
    overlay._region_active = True
    overlay._region_band = band
    overlay._preview_canvas = None
    overlay._current_item = None

    band.set_band(QRect(10, 10, 50, 40))
    band.show()
    overlay._finish_region(None)
    assert overlay._region_active is False
    assert not band.isHidden(), "valid selection must keep the band for the flyout"

    # Too small to ask about: still dropped.
    overlay._region_active = True
    band.set_band(QRect(10, 10, 2, 2))
    band.show()
    overlay._finish_region(None)
    assert band.isHidden()


def test_on_quick_ask_region_uses_selection_anchor() -> None:
    """The region flyout anchors to the held band, not the preview corner.

    Falsification: pre-change the anchor was ``_preview_host``/overlay.
    """
    from types import SimpleNamespace

    from tabs.image_gallery.ui.quick_look_hooks import on_quick_ask_region

    calls: list[tuple] = []
    sentinel = object()

    class _Ctrl:
        def open_ask_ai_region(self, path, box, anchor=None):
            calls.append((path, box, anchor))

    overlay = SimpleNamespace(
        region_selection_anchor=lambda: sentinel,
        _preview_host=None,
    )
    owner = SimpleNamespace(
        _owner_for_triage=lambda: _Ctrl(),
        _quick_look_overlay=overlay,
    )
    box = (0.1, 0.2, 0.3, 0.4)
    on_quick_ask_region(owner, "/img/a.png", box)
    assert len(calls) == 1
    path, got_box, anchor = calls[0]
    assert path == "/img/a.png"
    assert got_box == box
    assert anchor is sentinel


def test_maybe_start_region_bumps_selection_id(qtbot) -> None:
    """A new marquee supersedes the armed dismissal at start, not at close.

    Falsification: pre-change there is no selection generation to bump.
    """
    from types import SimpleNamespace

    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtWidgets import QWidget

    from tabs.image_gallery.ui.quick_look import QuickLookOverlay

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(400, 400)
    parent.show()
    overlay = QuickLookOverlay(parent)
    qtbot.addWidget(overlay)
    host = QWidget(overlay)
    host.setGeometry(50, 50, 200, 200)
    host.show()
    overlay._preview_host = host

    pos = host.mapTo(overlay, QPoint(100, 100))
    event = SimpleNamespace(
        button=lambda: Qt.MouseButton.LeftButton,
        position=lambda: QPointF(pos),
    )
    assert overlay._maybe_start_region(event) is True
    band = overlay._region_band
    assert band is not None
    assert band.selection_id == 1
    # A second marquee bumps again (slots armed to 1 must skip).
    assert overlay._maybe_start_region(event) is True
    assert band.selection_id == 2
