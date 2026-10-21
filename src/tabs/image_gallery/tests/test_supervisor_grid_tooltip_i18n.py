"""Regression: the GRID card tooltip must follow the tab translator.

``_refresh_tooltip`` rebuilds the grid card tooltip from
``analysis_tooltip_lines`` at five call sites (rebuild, pool recycle, selection,
update, sweep). It passed no translator, so every one of those paths rendered
``defects: …`` in English and overwrote the localized tooltip
``_set_card_tooltip`` had written. The list view was already localized — only
the grid was not.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _analysis():
    return SimpleNamespace(
        reason="too soft",
        defects=[SimpleNamespace(kind="over_smoothing"), SimpleNamespace(kind="chroma_fringing")],
    )


def _ru_tr(key: str, default: str) -> str:
    return {
        "image_gallery.card.tooltip.defects": "дефекты",
    }.get(key, default)


def test_grid_card_tooltip_is_the_file_name_only(qtbot) -> None:
    """The grid card tooltip is a SINGLE line — the full file name.

    Product decision: the analysis second line was removed, so the tooltip
    must never carry an assessment/defect line (in any language)."""
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

    w._context = SimpleNamespace(_tr=_ru_tr)
    w._refresh_tooltip(item)
    tip = card.toolTip()

    assert tip == "sup_tip.png", f"tooltip must be the file name only: {tip!r}"
    assert "\n" not in tip, f"tooltip must be single-line: {tip!r}"
    assert "ОТКЛОН" not in tip and "REJECT" not in tip and "дефекты" not in tip, tip

    # The sweep path writes the same single line.
    w._refresh_rebuilt_cards([item], sweep=True)
    assert card.toolTip() == tip
