"""Marquee update coalescing: repeated bands with the same membership apply once.

The gesture emits per mousemove (100+/s unthrottled); without coalescing
every move recomputes paths and repaints cards even when the hit set did
not change — the visible lag while band-selecting.

Counts alone are only perf bounds: a tick that "applies once" but applies the
WRONG cells passes every count assertion. The coalescing tests therefore
carry a per-card colour payload (the cell's content) and assert the applied
band holds exactly the in-band cells' payloads — including across suppressed
ticks (audit `audit-blind-test-inventory-2026-10-20`, blind pocket #2).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QRect

from tabs.image_gallery.ui import marquee as _marquee


def _card(geom: QRect, swatch=(0, 0, 0)):
    """Card double: geometry (hit-test) + colour payload (visible content)."""
    return SimpleNamespace(geometry=lambda: QRect(geom), swatch=tuple(swatch))


def _view(cards=None):
    """View double; ``_applied_payloads`` records what each apply painted.

    ``apply_selection`` resolves every applied path back to its card payload,
    so the assertion is about the cells the band actually selected — not just
    the strings the hit test happened to return.
    """
    applied: list[set] = []
    applied_payload: list[tuple] = []
    cards = cards or {
        "a.png": _card(QRect(10, 10, 100, 100), (200, 30, 30)),
        "b.png": _card(QRect(200, 10, 100, 100), (30, 200, 30)),
    }

    def _apply(paths):
        applied.append(set(paths))
        applied_payload.append(
            tuple(sorted((str(p), tuple(cards[str(p)].swatch)) for p in paths))
        )

    view = SimpleNamespace(
        _items=[SimpleNamespace(path=Path(p)) for p in cards],
        _marquee_additive=False,
        _marquee_base=set(),
        _owner=None,
        owner=None,
        _on_marquee_preview=None,
        apply_selection=_apply,
    )
    view.card_for = lambda p: cards.get(str(p))
    view._applied_payloads = applied_payload
    return view, applied


def _payload_hash(payload: tuple) -> str:
    return hashlib.sha1(repr(payload).encode()).hexdigest()


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


def test_suppressed_tick_keeps_the_applied_band_and_its_colours() -> None:
    """A coalesced tick repaints nothing: same cells, same payloads, no churn."""
    view, applied = _view()
    band = QRect(0, 0, 150, 150)  # card A only
    _marquee.on_rect_update(view, band)
    assert len(applied) == 1
    first = view._applied_payloads[-1]
    assert first == (("a.png", (200, 30, 30)),), first
    frozen = _payload_hash(first)
    for _ in range(6):
        _marquee.on_rect_update(view, QRect(band))
    # Count is the perf bound; the payload hash is the correctness assertion.
    assert len(applied) == 1, "a suppressed tick re-applied the same membership"
    assert _payload_hash(view._applied_payloads[-1]) == frozen
    assert {colour for _p, colour in view._applied_payloads[-1]} == {(200, 30, 30)}
    assert {str(p) for p in applied[-1]} == {"a.png"}


def test_applied_band_holds_the_selected_cells_colours() -> None:
    """The applied band is the in-band cells' content — never a neighbour's.

    Three distinct cells are walked through band shapes that add, slide and
    shrink membership. Each step must apply exactly the intersecting cells
    (path AND payload), and the suppressed repeats between steps must leave
    that applied band byte-identical.
    """
    cells = {
        "a.png": _card(QRect(10, 10, 100, 100), (200, 30, 30)),
        "b.png": _card(QRect(200, 10, 100, 100), (30, 200, 30)),
        "c.png": _card(QRect(400, 10, 100, 100), (30, 30, 200)),
    }
    view, applied = _view(cells)
    steps = (
        (QRect(0, 0, 150, 150), {"a.png"}),
        (QRect(0, 0, 350, 150), {"a.png", "b.png"}),
        (QRect(190, 0, 350, 150), {"b.png", "c.png"}),
        (QRect(390, 0, 200, 150), {"c.png"}),
    )
    for step, (rect, want_paths) in enumerate(steps, start=1):
        _marquee.on_rect_update(view, QRect(rect))
        assert len(applied) == step, f"step {step}: applied {len(applied)} times"
        payload = view._applied_payloads[-1]
        assert {p for p, _c in payload} == want_paths
        want_colours = {cells[p].swatch for p in want_paths}
        assert {c for _p, c in payload} == want_colours, (
            f"step {step}: band holds {payload}, expected {want_colours}"
        )
        assert dict(payload) == {p: cells[p].swatch for p in want_paths}
        frozen = _payload_hash(payload)
        for _ in range(3):
            _marquee.on_rect_update(view, QRect(rect))
        assert len(applied) == step, f"step {step}: suppressed tick re-applied"
        assert _payload_hash(view._applied_payloads[-1]) == frozen
