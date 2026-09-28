"""Series header keeps its full title when the cluster is collapsed.

Regression: collapsing every series removed all cards from the
``QGridLayout``, so its columns shrank to zero width and the spanning
header ``Button`` elided its text (``ElideRight``) — e.g.
``SERIES 1 · HUB · 3 VARIANTS ▼`` degraded to ``SERIES 1 ·``.
Column minimums pinned to the card width in series mode keep the
header at the full grid width.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import GALLERY_CARD_W
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i) for i, n in enumerate(names)]


def _header_btn_text(btn) -> str:
    try:
        region = btn.region("_main")
        rows = getattr(region, "rows", None) or getattr(region, "_rows", None) or []
        if rows:
            return str(getattr(rows[0], "text", ""))
    except Exception:
        pass
    for attr in ("_text", "text", "_label"):
        try:
            val = getattr(btn, attr, None)
            text = val() if callable(val) else val
            if text:
                return str(text)
        except Exception:
            continue
    return ""


def test_collapsed_series_keeps_full_header_title(qtbot) -> None:
    """Collapse must pin columns and keep the full header text."""
    from sli_ui_toolkit.managers import scaled_px

    items = _items("a.png", "b.png", "c.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    gv = w._grid_view
    gv.set_series([items], hub_names=["HUB-A"], collapsed={})

    expected_w = int(scaled_px(GALLERY_CARD_W))
    for c in range(4):
        assert gv.items_layout.columnMinimumWidth(c) == expected_w

    gv._toggle_collapse(0)
    assert gv._collapsed.get(0) is True
    for c in range(4):
        assert gv.items_layout.columnMinimumWidth(c) == expected_w

    btn = gv.findChild(object, "GallerySeriesHeaderBtn_0")
    assert btn is not None
    text = _header_btn_text(btn)
    assert "HUB-A" in text
    assert "VARIANTS" in text
    assert text.strip().upper().endswith("▶")
    # Accent bar is the button's own painter layer (simple-flyout pattern),
    # not a sibling widget: it cannot drift from the label.
    from tabs.image_gallery.ui.grid_view import _SeriesHeaderAccentLayer

    layers = list(getattr(getattr(btn, "_painter", None), "layers", None) or [])
    accent = [layer for layer in layers if isinstance(layer, _SeriesHeaderAccentLayer)]
    assert len(accent) == 1
    assert accent[0]._collapsible is True


def test_flat_grid_resets_column_minimums(qtbot) -> None:
    """Flat (non-series) mode must not force card-width columns."""
    items = _items("a.png", "b.png", "c.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    gv = w._grid_view
    gv.set_series([items], hub_names=["HUB-A"], collapsed={})
    gv._toggle_collapse(0)
    assert gv._collapsed.get(0) is True
    gv.rebuild_grid(items)
    for c in range(4):
        assert gv.items_layout.columnMinimumWidth(c) == 0
