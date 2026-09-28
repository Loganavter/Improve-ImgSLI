"""Stats-strip action gates: Keep best / Compare finalists disable with nothing to do.

Regression: both buttons stayed enabled on empty/singleton/all-rejected
galleries, running no-op actions on click.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _item(name: str, rejected: bool = False) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    it.rejected = rejected
    return it


def _states(w: ImageGalleryWidget) -> tuple[bool, bool]:
    return (
        w.stats_strip._keep_btn.isEnabled(),
        w.stats_strip._compare_btn.isEnabled(),
    )


def test_empty_widget_disables_both(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    assert _states(w) == (False, False)


def test_series_enables_both(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    a, b = _item("a.png"), _item("b.png")
    w.rebuild_grid([a, b])
    w.set_triage([[a, b]], "camera", None)
    assert _states(w) == (True, True)


def test_all_rejected_disables_both(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    a, b = _item("a.png", rejected=True), _item("b.png", rejected=True)
    w.rebuild_grid([a, b])
    w.set_triage([[a, b]], "camera", None)
    assert _states(w) == (False, False)


def test_single_item_disables_both(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    a = _item("a.png")
    w.rebuild_grid([a])
    w.set_triage([], "camera", None)
    assert _states(w) == (False, False)


def test_reject_last_survivor_disables_compare(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    a, b = _item("a.png"), _item("b.png")
    w.rebuild_grid([a, b])
    w.set_triage([[a, b]], "camera", None)
    assert _states(w) == (True, True)
    a.rejected = True
    b.rejected = True
    w.rebuild_grid([a, b])
    assert _states(w) == (False, False)


def test_show_mode_keeps_button_enabled(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.stats_strip.set_keep_mode("show")
    w.rebuild_grid([])
    assert w.stats_strip._keep_btn.isEnabled() is True
