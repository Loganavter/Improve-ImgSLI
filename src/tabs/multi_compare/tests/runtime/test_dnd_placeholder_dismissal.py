"""Drop preview must not stay hidden under the startup placeholder.

Empty canvas rarely accumulates the 10 presents the first-frame gate needs
(on-demand repaints), so the opaque ``StartupPlaceholder`` would otherwise
cover the drop-zone overlay for the whole first drag — RASTER+COMMIT happen
underneath it, invisibly. ``chrome.dismiss_placeholder_for_dnd`` lifts it
once a live preview is dispatched and the surface proven alive.
"""

from types import SimpleNamespace

import logging

from tabs.multi_compare.ui import chrome


def _widget(*, placeholder_visible: bool, presents: int, dismissed: bool = False):
    placeholder = SimpleNamespace(
        _visible=placeholder_visible,
        _dismissed=dismissed,
        isVisible=lambda: placeholder._visible and not placeholder._dismissed,
        hide=lambda: setattr(placeholder, "_dismissed", True),
    )
    canvas = SimpleNamespace(_rhi_presents_completed=presents)
    return SimpleNamespace(_startup_placeholder=placeholder, canvas=canvas)


def test_dismisses_covering_placeholder_once_surface_alive():
    widget = _widget(placeholder_visible=True, presents=3)
    assert chrome.dismiss_placeholder_for_dnd(widget) is True
    assert widget._startup_placeholder._dismissed is True


def test_keeps_placeholder_when_surface_never_presented():
    widget = _widget(placeholder_visible=True, presents=0)
    assert chrome.dismiss_placeholder_for_dnd(widget) is False
    assert widget._startup_placeholder._dismissed is False


def test_noop_when_placeholder_already_gone():
    widget = _widget(placeholder_visible=False, presents=5)
    assert chrome.dismiss_placeholder_for_dnd(widget) is False


def test_noop_without_placeholder_or_canvas():
    assert chrome.dismiss_placeholder_for_dnd(SimpleNamespace()) is False
    widget = SimpleNamespace(_startup_placeholder=None, canvas=None)
    assert chrome.dismiss_placeholder_for_dnd(widget) is False


def test_decision_logged_with_reasons(monkeypatch, caplog):
    monkeypatch.setenv("IMGSLI_MC_DEBUG", "1")
    widget = _widget(placeholder_visible=True, presents=0)
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        assert chrome.dismiss_placeholder_for_dnd(widget) is False
    assert "placeholder check" in caplog.text
    assert "presents=0" in caplog.text
    assert "KEPT" in caplog.text
