"""Keep best ↔ Show all toggle + rejected capsule state (Stage 2 triage).

- ``should_show_all`` flips only when every series (≥2 members) keeps
  exactly one non-rejected item.
- ``keep_best_of_series`` → strip shows "Show all"; ``show_all`` restores
  flags and the strip flips back to "Keep best".
- Rejected card capsule: pale ✕ (disabled alpha, still clickable) +
  "↩ Return" tooltip; normal card keeps "✕ Reject".
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.models import GalleryItem


def _item(name: str, series: str | None = None, rejected: bool = False) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    if series is not None:
        it.series_id = series
        try:
            it.provenance_series_id = series
        except Exception:
            pass
    it.rejected = rejected
    try:
        it.triage_rejected = rejected
    except Exception:
        pass
    return it


def test_should_show_all_predicate() -> None:
    from tabs.image_gallery.use_cases.triage import should_show_all

    # Untouched gallery: 2 survivors per series → keep mode.
    items = [_item("a1.png", "s1"), _item("a2.png", "s1"), _item("b1.png", "s2"), _item("b2.png", "s2")]
    groups = [items[0:2], items[2:4]]
    assert should_show_all(items, groups) is False
    # One series narrowed, other untouched → still keep mode.
    items[1].rejected = True
    assert should_show_all(items, groups) is False
    # Every series down to one survivor → show mode.
    items[3].rejected = True
    assert should_show_all(items, groups) is True
    # No series at all → never show mode.
    assert should_show_all(items, []) is False


def test_keep_best_then_show_all_roundtrip() -> None:
    from tabs.image_gallery.use_cases import triage as _triage

    items = [_item("a1.png", "s1"), _item("a2.png", "s1"), _item("b1.png", "s2"), _item("b2.png", "s2")]

    class _StripStub:
        def __init__(self) -> None:
            self.modes: list[str] = []
            self.counts: list[int] = []

        def set_rejected_count(self, n: int) -> None:
            self.counts.append(int(n))

        def set_keep_mode(self, mode: str) -> None:
            self.modes.append(str(mode))

    class _WidgetStub:
        def __init__(self, strip: _StripStub) -> None:
            self.stats_strip = strip
            self.rebuilt: list[int] = []

        def rebuild_grid(self, items) -> None:
            self.rebuilt.append(len(list(items)))

        def refresh_card(self, _item) -> None:
            pass

    class _Owner:
        def __init__(self, items, widget) -> None:
            self.state = type("S", (), {"items": items})()
            self.widget = widget

    strip = _StripStub()
    owner = _Owner(items, _WidgetStub(strip))

    _triage.keep_best_of_series(owner)
    assert _triage.is_keep_best_done(owner) is True
    assert strip.modes and strip.modes[-1] == "show"

    restored = _triage.show_all(owner)
    assert restored == 2
    assert all(not bool(getattr(it, "rejected", False)) for it in items)
    assert _triage.is_keep_best_done(owner) is False
    assert strip.modes and strip.modes[-1] == "keep"


def test_strip_keep_button_routes_by_mode(qtbot) -> None:
    from tabs.image_gallery.ui.stats_strip import StatsStrip

    strip = StatsStrip()
    qtbot.addWidget(strip)
    seen: list[str] = []
    strip.keepBestClicked.connect(lambda: seen.append("keep"))
    strip.showAllClicked.connect(lambda: seen.append("show"))

    strip.set_keep_mode("keep")
    strip._keep_btn.clicked.emit()
    assert seen == ["keep"]

    strip.set_keep_mode("show")
    assert strip._keep_btn._text == "Show all"
    strip._keep_btn.clicked.emit()
    assert seen == ["keep", "show"]

    strip.set_keep_mode("keep")
    assert strip._keep_btn._text == "Keep best"


def test_rejected_capsule_pale_return_tooltip(qtbot) -> None:
    from tabs.image_gallery.ui.card import build_gallery_card
    from tabs.image_gallery.ui.card.hover import show_gallery_card_flyout

    card = build_gallery_card(_item("a.png"), parent=None)
    qtbot.addWidget(card)
    card.resize(250, 170)
    qtbot.waitExposed(card) if False else None

    show_gallery_card_flyout(card)
    flyout = getattr(card, "_gallery_card_flyout", None)
    assert flyout is not None
    btn = flyout.action_button("reject")
    assert btn is not None
    assert btn.toolTip() == "✕ Reject"

    from tabs.image_gallery.ui.card import update_gallery_card

    bad = _item("a.png", rejected=True)
    update_gallery_card(card, bad)
    show_gallery_card_flyout(card)
    flyout = getattr(card, "_gallery_card_flyout", None)
    btn = flyout.action_button("reject")
    assert btn is not None
    assert btn.toolTip() == "↩ Return"
    # Pale = danger hue at the toolkit disabled alpha, button stays enabled.
    assert btn.isEnabled()
    try:
        fg = btn.getForegroundColor()
    except Exception:
        fg = None
    assert fg is not None and int(fg.alpha()) == 110
    card.deleteLater()
