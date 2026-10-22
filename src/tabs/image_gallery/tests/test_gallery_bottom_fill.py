"""The gallery well reaches the tab's bottom edge (owner report 2026-10-22).

Falsification story: the page root kept a 40 design-px BOTTOM margin after the
selection HUD it was written for was deleted ("bottom 40 to clear the selection
HUD"), so the grid's ``OpaqueFillHost`` — the scroll well that paints the
gallery background — stopped 40 px above the tab's bottom edge. The band under
it was painted by the page, which read as a dead strip under the grid.

The test measures real geometry offscreen at two window sizes, with a few cards
(no scrolling) and in both view modes, and asserts the well's bottom edge equals
the page's bottom edge. It fails on the pre-fix tree by exactly the margin.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sli_ui_toolkit.managers import UiScale
from tabs.image_gallery.widget import ImageGalleryWidget


def _well_and_page_geometry(widget: ImageGalleryWidget) -> tuple[int, int, int]:
    """(well bottom, page bottom, layout bottom margin) in page coordinates."""
    layout = widget.layout()
    margin = layout.contentsMargins().bottom() if layout is not None else -1
    grid = widget._grid_view
    host = grid.items_host
    well_bottom = host.mapTo(widget, host.rect().bottomLeft()).y()
    return well_bottom, widget.rect().bottom(), margin


@pytest.mark.parametrize("size", [(1200, 800), (900, 620)])
def test_the_grid_well_reaches_the_page_bottom(qapp, size) -> None:
    UiScale.get_instance().set_factor(1.0)
    widget = ImageGalleryWidget(context=None)
    try:
        widget.resize(*size)
        # The scroll well only exists in the grid/list page (not the empty state).
        widget.show()
        qapp.processEvents()
        widget.layout().activate()
        qapp.processEvents()
        widget._content_stack.setCurrentWidget(widget._grid_view)
        qapp.processEvents()
        widget.resize(*size)
        qapp.processEvents()
        widget.layout().activate()
        qapp.processEvents()

        well_bottom, page_bottom, margin = _well_and_page_geometry(widget)
        assert margin == 0, (
            f"page root still reserves {margin}px at the bottom: the well cannot "
            "reach the tab edge (the pre-fix 40px HUD band)"
        )
        assert well_bottom == page_bottom, (
            f"grid well ends at y={well_bottom}, page ends at y={page_bottom} "
            f"({page_bottom - well_bottom}px gap under the grid)"
        )
    finally:
        widget.hide()
        widget.deleteLater()


def test_the_well_reaches_the_bottom_in_list_mode(qapp) -> None:
    """Same rule for the list view — one well, two view modes."""
    UiScale.get_instance().set_factor(1.0)
    widget = ImageGalleryWidget(context=None)
    try:
        widget.resize(1100, 760)
        widget.show()
        qapp.processEvents()
        widget._content_stack.setCurrentWidget(widget._grid_view)
        widget._grid_view.set_view_mode("list")
        qapp.processEvents()
        widget.layout().activate()
        qapp.processEvents()

        well_bottom, page_bottom, margin = _well_and_page_geometry(widget)
        assert margin == 0
        assert well_bottom == page_bottom, (
            f"list well ends at y={well_bottom}, page at y={page_bottom}"
        )
    finally:
        widget.hide()
        widget.deleteLater()
