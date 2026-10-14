"""The stats-strip keep button stays clickable when it reads "Show all".

Falsification (pre-fix): ``_refresh_owner_grid`` rebuilt the grid first (the
action gate ran with the STALE ``keep_mode="keep"`` — after keep-best a series
has a single survivor, so the gate disabled the button) and only then flipped
the mode to "show", relabelling the still-disabled button to "Show all". The
user could not click it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.stats_strip import StatsStrip
from tabs.image_gallery.use_cases import triage
from tabs.image_gallery.widget import ImageGalleryWidget


def test_set_keep_mode_show_enables_the_button(qtbot) -> None:
    strip = StatsStrip()
    qtbot.addWidget(strip)
    strip.set_action_states(keep_best=False, compare_finalists=False)
    assert not strip._keep_btn.isEnabled()
    strip.set_keep_mode("show")
    assert strip._keep_btn.isEnabled(), "Show all button left disabled"


def test_show_all_button_clickable_after_keep_best(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    a = GalleryItem(path=Path("/g/a.png"), mtime_ns=1)
    b = GalleryItem(path=Path("/g/b.png"), mtime_ns=2)
    a.rejected = False
    b.rejected = True
    owner = SimpleNamespace(
        widget=w, state=SimpleNamespace(items=[a, b], series=[[a, b]])
    )
    triage._refresh_owner_grid(owner)
    assert w.stats_strip._keep_mode == "show"
    assert w.stats_strip._keep_btn.isEnabled(), "Show all button is not clickable"
