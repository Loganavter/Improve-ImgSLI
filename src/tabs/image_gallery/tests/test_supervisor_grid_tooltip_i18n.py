"""Regression: the GRID card tooltip must follow the tab translator.

``_refresh_tooltip`` rebuilds the grid card tooltip from
``analysis_tooltip_lines`` at five call sites (rebuild, pool recycle, selection,
update, sweep). It passed no translator, so every one of those paths rendered
``KEEP — …`` / ``defects: …`` in English and overwrote the localized tooltip
``_set_card_tooltip`` had written. The list view was already localized — only
the grid was not.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _analysis():
    return SimpleNamespace(
        verdict="reject",
        verdict_reason="too soft",
        defects=[SimpleNamespace(kind="over_smoothing"), SimpleNamespace(kind="chroma_fringing")],
    )


def _ru_tr(key: str, default: str) -> str:
    return {
        "image_gallery.card.tooltip.reject": "ОТКЛОН",
        "image_gallery.card.tooltip.defects": "дефекты",
    }.get(key, default)


def test_grid_card_tooltip_follows_the_translator(qtbot) -> None:
    """A rebuilt grid card must show the RU verdict/defect wording, not EN."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w.show()
    qtbot.waitExposed(w)

    item = GalleryItem(path=__import__("pathlib").Path("/gallery/sup_tip.png"), mtime_ns=1)
    item.analysis = _analysis()
    item.analysis_error = None
    w.rebuild_grid([item])

    card = w._grid_view.card_for(item.path)
    assert card is not None, "grid card was not built"

    # The widget-level translator seam is what the fix plumbs through.
    w._context = SimpleNamespace(_tr=_ru_tr)

    w._refresh_tooltip(item)
    tip = card.toolTip()

    assert "ОТКЛОН" in tip, f"grid tooltip did not localise the verdict: {tip!r}"
    assert "дефекты" in tip, f"grid tooltip did not localise the defects label: {tip!r}"
    assert "REJECT" not in tip, f"grid tooltip still shows the English verdict: {tip!r}"
    assert "defects: " not in tip, f"grid tooltip still shows the English defects prefix: {tip!r}"

    # And it must survive the sweep path, which calls the same helper in bulk.
    w._refresh_rebuilt_cards([item], sweep=True)
    assert card.toolTip() == tip, "sweep path rewrote the tooltip with a different wording"
