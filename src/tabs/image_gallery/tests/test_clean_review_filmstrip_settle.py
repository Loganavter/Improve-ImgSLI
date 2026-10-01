"""Clean-review filmstrip settle regression (qt-selfsizing A1).

``CleanReviewOverlay._populate`` sizes the filmstrip scroller from the
filmstrip's own hint
(``strip_scroll.setFixedHeight(filmstrip.sizeHint().height() + 16)``) while
both live under layouts. Two one-frame hazards lived here:

1. A child added while the host is already visible stays hidden (no
   implicit show) — excluded from layout hints, so the host collapses and
   the strip paints a frame late (same trap as ``ui/quick_look/strip.py``
   documents).
2. The fixed height is read from the filmstrip hint and the host layout is
   left to re-run on the next event-loop turn, so the strip keeps its old
   width until then (measured: 100px wide for one frame, then 868px).

Contract: repopulating while visible — with NO event-loop turn in between —
must already show the strip at its settled geometry, in both the grow and
the shrink direction.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from sli_ui_toolkit.managers import scaled_px
from tabs.image_gallery.ui.clean_review import CleanReviewOverlay

_KEEP_ALIVE: list[QWidget] = []


def _make_owner(rejected_paths: list[str]):
    items = [
        SimpleNamespace(
            rejected=True,
            path=p,
            name=p.rsplit("/", 1)[-1],
            thumbnail=None,
            provenance_series_id="series_1",
        )
        for p in rejected_paths
    ]
    return SimpleNamespace(state=SimpleNamespace(items=items, folder=None))


def _make_shown_overlay(qtbot, owner) -> CleanReviewOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(1280, 800)
    parent.show()
    overlay = CleanReviewOverlay(parent, owner=owner)
    qtbot.addWidget(overlay)
    overlay._populate(owner)
    overlay.show()
    QApplication.processEvents()
    QApplication.processEvents()
    _KEEP_ALIVE.append(parent)
    return overlay


def _snapshot(overlay: CleanReviewOverlay):
    strip = overlay._list_host.findChild(QScrollArea, "clean_review_filmstrip")
    assert strip is not None, "filmstrip scroller missing after _populate"
    film = strip.widget()
    assert film is not None, "filmstrip content missing after _populate"
    return (
        strip.isVisible(),
        strip.geometry().getRect(),
        film.sizeHint().height(),
    )


def _assert_repopulate_settles(qtbot, overlay, paths: list[str]) -> None:
    overlay._populate(_make_owner(paths))
    # NO processEvents here: immediate geometry must already be settled.
    immediate = _snapshot(overlay)
    QApplication.processEvents()
    QApplication.processEvents()
    settled = _snapshot(overlay)

    visible, rect, hint_h = immediate
    assert visible, "repopulated strip hidden until the next event-loop turn"
    assert hint_h > 0, "filmstrip hint collapsed to zero"
    assert immediate == settled, (
        f"strip geometry settled a turn late:\n immediate={immediate}\n settled={settled}"
    )
    strip = overlay._list_host.findChild(QScrollArea, "clean_review_filmstrip")
    assert strip is not None
    assert strip.height() == hint_h + scaled_px(16), (
        f"strip height {strip.height()} != filmstrip hint {hint_h} + padding"
    )


def test_filmstrip_repopulate_settles_on_grow(qtbot) -> None:
    overlay = _make_shown_overlay(
        qtbot, _make_owner(["/gallery/a.png", "/gallery/b.png"])
    )
    _assert_repopulate_settles(
        qtbot, overlay, [f"/gallery/n{i}.png" for i in range(8)]
    )


def test_filmstrip_repopulate_settles_on_shrink(qtbot) -> None:
    overlay = _make_shown_overlay(
        qtbot, _make_owner([f"/gallery/n{i}.png" for i in range(8)])
    )
    _assert_repopulate_settles(qtbot, overlay, ["/gallery/a.png"])
