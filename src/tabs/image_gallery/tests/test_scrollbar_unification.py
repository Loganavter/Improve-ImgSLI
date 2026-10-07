"""Scrollbar unification: no stock QScrollArea left in gallery overlays.

- The Quick Look right column, the CleanReview main scroll and the
  CleanReview filmstrip ride ``OverlayScrollArea`` (``corner_radius=0``
  keeps the current square look — only the scrollbar changes).
- ``install_scrollbar_policy()`` is the project-wide backstop: any stock
  area still constructed anywhere gets ``MinimalistScrollBar`` bars at
  polish time, so future call sites cannot silently reintroduce the
  native look.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from sli_ui_toolkit.widgets import MinimalistScrollBar, OverlayScrollArea

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.ui.clean_review import CleanReviewOverlay
from tabs.image_gallery.ui.quick_look import QuickLookOverlay

_KEEP_ALIVE: list[QWidget] = []


def _ql_item(name: str, **kwargs) -> GalleryItem:
    return GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1, **kwargs)


def _make_ql_overlay(qtbot) -> QuickLookOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._scrollbar_test_parent = parent  # strong ref, keeps C++ tree alive
    return ov


def _show_ql(overlay: QuickLookOverlay, item: GalleryItem, series, mode=Mode.FIDELITY):
    if series and not isinstance(series[0], (list, tuple)):
        series = [list(series)]
    owner = SimpleNamespace(
        state=SimpleNamespace(
            mode=mode,
            source_path=None,
            series=series,
            items=[m for cl in series for m in cl],
        )
    )
    overlay.show_for(item, owner)
    try:
        parent = getattr(overlay, "_scrollbar_test_parent", None) or overlay.parentWidget()
        if parent is not None:
            parent.resize(1280, 800)
            parent.show()
    except Exception:
        pass
    QApplication.processEvents()


def _make_cr_owner(tmp_path):
    items = [
        SimpleNamespace(
            rejected=True,
            path=str(tmp_path / name),
            name=name,
            thumbnail=None,
            provenance_series_id="series_1",
        )
        for name in ("a.jpg", "b.jpg")
    ]
    return SimpleNamespace(state=SimpleNamespace(items=items, folder=str(tmp_path)))


def _make_cr_overlay(qtbot, owner) -> CleanReviewOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    overlay = CleanReviewOverlay(parent, owner=owner)
    qtbot.addWidget(overlay)
    overlay._populate(owner)
    _KEEP_ALIVE.append(parent)
    return overlay


def test_quicklook_right_column_uses_overlay_scrollarea(qtbot):
    a = _ql_item("a.png")
    b = _ql_item("b.png")
    ov = _make_ql_overlay(qtbot)
    _show_ql(ov, a, [a, b])
    right = ov.findChild(QWidget, "quicklook_right_scroll")
    assert isinstance(right, OverlayScrollArea)
    ov.hide()


def test_clean_review_scrolls_use_overlay_scrollarea(qtbot, tmp_path):
    overlay = _make_cr_overlay(qtbot, _make_cr_owner(tmp_path))
    assert isinstance(overlay._scroll, OverlayScrollArea)
    filmstrip = overlay.findChild(QWidget, "clean_review_filmstrip")
    assert isinstance(filmstrip, OverlayScrollArea)
    overlay.hide()


def test_policy_backstop_swaps_remaining_stock_areas(qtbot):
    """install_scrollbar_policy covers stock areas at polish time."""
    from sli_ui_toolkit.widgets import install_scrollbar_policy

    assert install_scrollbar_policy() is True
    area = QScrollArea()
    qtbot.addWidget(area)
    area.resize(320, 240)
    area.show()
    QApplication.processEvents()
    assert isinstance(area.verticalScrollBar(), MinimalistScrollBar)
    assert isinstance(area.horizontalScrollBar(), MinimalistScrollBar)
    area.close()
