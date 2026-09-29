"""Marquee update coalescing: repeated bands with the same membership apply once.

The gesture emits per mousemove (100+/s unthrottled); without coalescing
every move recomputes paths and repaints cards even when the hit set did
not change — the visible lag while band-selecting.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QRect

from tabs.image_gallery.ui import marquee as _marquee


def _card(geom: QRect):
    return SimpleNamespace(geometry=lambda: QRect(geom))


def _view():
    applied: list[set] = []
    cards = {
        "a.png": _card(QRect(10, 10, 100, 100)),
        "b.png": _card(QRect(200, 10, 100, 100)),
    }
    view = SimpleNamespace(
        _items=[SimpleNamespace(path=Path("a.png")), SimpleNamespace(path=Path("b.png"))],
        _marquee_additive=False,
        _marquee_base=set(),
        _owner=None,
        owner=None,
        _on_marquee_preview=None,
        apply_selection=lambda paths: applied.append(set(paths)),
    )
    view.card_for = lambda p: cards.get(str(p))
    return view, applied


def test_same_band_applies_once() -> None:
    view, applied = _view()
    band = QRect(0, 0, 150, 150)  # hits card A only
    _marquee.on_rect_update(view, band)
    _marquee.on_rect_update(view, band)
    _marquee.on_rect_update(view, QRect(band))  # equal copy, same membership
    assert len(applied) == 1
    assert {str(p) for p in applied[0]} == {"a.png"}


def test_changed_membership_applies_again() -> None:
    view, applied = _view()
    _marquee.on_rect_update(view, QRect(0, 0, 150, 150))
    _marquee.on_rect_update(view, QRect(0, 0, 350, 150))  # hits A+B now
    assert len(applied) == 2
    assert {str(p) for p in applied[-1]} == {"a.png", "b.png"}


def test_new_press_resets_coalescing() -> None:
    view, applied = _view()
    band = QRect(0, 0, 150, 150)
    _marquee.on_rect_update(view, band)
    assert len(applied) == 1
    # New gesture (fresh base): the same band must dispatch again.
    view._marquee_last_update_sig = None
    view._marquee_base = {"b.png"}
    _marquee.on_rect_update(view, band)
    assert len(applied) == 2
