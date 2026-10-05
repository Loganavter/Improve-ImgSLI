"""Tiled pump backoff: full rate only on forward progress.

The residency loop used to pump a full-rate frame whenever a frame had
any drawn/resident tile — but a held level draws every frame, so a
plateaued stream (coverage never completing) spun ``update()`` at GUI-loop
rate forever: per-pump log spam plus an event loop too saturated for
resize drags. Pinned here:
- growing ``resident`` → immediate full-rate pump (streaming stays fast);
- plateaued ``resident`` → single throttled pump with backoff (no spin);
- per-pump logging is cover-timeline only (silent by default).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace


def _make_canvas(qtbot):
    from tabs.image_gallery.ui.quick_look import preview_canvas as pc

    card = pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    card._tiled_source = ("k", object())
    return card


def _fake_renderer(result):
    calls: list = []

    class _R:
        def has_source(self):
            return True

        def render(self, *a, **k):
            calls.append(1)
            return result

        def store_size(self):
            return (64, 64)

    return _R(), calls


def _drive(canvas, monkeypatch, result, full_calls, slow_calls):
    from tabs.image_gallery.ui.quick_look import preview_canvas as pc

    renderer, _ = _fake_renderer(result)
    monkeypatch.setattr(canvas, "_ensure_tile_renderer", lambda: renderer)
    monkeypatch.setattr(
        pc.QuickLookCanvasWidget, "_pump_next_frame",
        lambda self: full_calls.append(1),
    )
    monkeypatch.setattr(
        pc.QuickLookCanvasWidget, "_pump_throttled",
        lambda self, stall: slow_calls.append(stall),
    )
    return canvas._render_tiled(object(), None, None, None, 64, 64)


def _result(drawn=True, covered=False, instances=3, resident=5):
    return SimpleNamespace(drawn=drawn, covered=covered, instances=instances, resident=resident)


def test_growing_resident_pumps_full_rate(qtbot, monkeypatch) -> None:
    card = _make_canvas(qtbot)
    full, slow = [], []
    assert _drive(card, monkeypatch, _result(resident=3), full, slow) is False
    assert _drive(card, monkeypatch, _result(resident=5), full, slow) is False
    assert len(full) == 2 and slow == []


def test_plateau_throttles_instead_of_spinning(qtbot, monkeypatch) -> None:
    card = _make_canvas(qtbot)
    full, slow = [], []
    assert _drive(card, monkeypatch, _result(resident=5), full, slow) is False
    assert len(full) == 1 and slow == []
    # Same tiles redrawn, coverage never completing: no more full-rate pumps.
    for _ in range(5):
        assert _drive(card, monkeypatch, _result(resident=5), full, slow) is False
    assert len(full) == 1
    assert len(slow) == 5


def test_idle_frame_pumps_nothing(qtbot, monkeypatch) -> None:
    card = _make_canvas(qtbot)
    full, slow = [], []
    assert _drive(card, monkeypatch, _result(drawn=False, resident=0), full, slow) is False
    assert full == [] and slow == []


def test_pump_log_silent_by_default(qtbot, monkeypatch, caplog) -> None:
    from tabs.image_gallery.ui.quick_look import preview_canvas as pc

    monkeypatch.delenv("IMGSLI_QL_COVER_DEBUG", raising=False)
    card = _make_canvas(qtbot)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        card._pump_next_frame()
    assert not [r for r in caplog.records if "pump posted" in r.getMessage()]


def test_pump_log_enabled_with_cover_flag(qtbot, monkeypatch, caplog) -> None:
    monkeypatch.setenv("IMGSLI_QL_COVER_DEBUG", "1")
    card = _make_canvas(qtbot)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        card._pump_next_frame()
    assert [r for r in caplog.records if "pump posted" in r.getMessage()]
