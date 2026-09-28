"""Quick-look RHI canvas must not present before the overlay chrome.

``QRhiWidget`` composites on its own render-thread clock and could show the
image ahead of the veil/bars on a warm open. Populate stages a cold-open
canvas for the first ``paintEvent``; warm walks show immediately.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
    release_preview_canvas,
    reveal_pending_preview_canvas,
    reveal_preview_canvas,
)


def _canvas():
    shown: list[bool] = []
    hidden: list[bool] = []
    return (
        SimpleNamespace(
            show=lambda: shown.append(True),
            hide=lambda: hidden.append(True),
        ),
        shown,
        hidden,
    )


def _overlay(*, visible: bool, painted: bool = False):
    ov = SimpleNamespace(isVisible=lambda: visible)
    if painted:
        ov._ql_chrome_painted = True
    return ov


def test_cold_open_stages_canvas_for_first_paint() -> None:
    canvas, shown, hidden = _canvas()
    ov = _overlay(visible=False)
    reveal_preview_canvas(ov, canvas)
    assert shown == []
    assert hidden == [True]
    assert getattr(ov, "_preview_canvas_pending", None) is canvas


def test_warm_walk_shows_immediately() -> None:
    canvas, shown, hidden = _canvas()
    ov = _overlay(visible=True, painted=True)
    reveal_preview_canvas(ov, canvas)
    assert shown == [True]
    assert getattr(ov, "_preview_canvas_pending", None) is None


def test_first_paint_reveals_staged_canvas() -> None:
    canvas, shown, _hidden = _canvas()
    ov = _overlay(visible=True)
    ov._preview_canvas_pending = canvas
    reveal_pending_preview_canvas(ov)
    assert shown == [True]
    assert getattr(ov, "_preview_canvas_pending", None) is None


def test_hidden_overlay_restages_instead_of_showing() -> None:
    canvas, shown, _hidden = _canvas()
    ov = _overlay(visible=False)
    ov._preview_canvas_pending = canvas
    reveal_pending_preview_canvas(ov)
    assert shown == []
    assert getattr(ov, "_preview_canvas_pending", None) is canvas


def test_release_drops_staged_canvas() -> None:
    canvas, _shown, _hidden = _canvas()
    ov = _overlay(visible=False)
    ov._preview_canvas_pending = canvas
    ov._preview_canvas = None
    ov._preview_store = None
    ov._preview_label = None
    release_preview_canvas(ov)
    assert getattr(ov, "_preview_canvas_pending", None) is None
