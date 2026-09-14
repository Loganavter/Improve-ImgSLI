"""S3 design-parity regression tests for CleanReviewOverlay (mockup v3).

Covers audit items S3-1..S3-4 against ``ui/clean_review.py``:

- S3-1: reassurance subtitle under the title —
  ``N files will be moved to <folder>/_rejected/ — nothing is deleted,
  Undo available for 10 s.`` (safety promise shown before the move);
- S3-2: filmstrip thumbs 150x100 (scaled) rendered by the toolkit ``Label``
  component (QLabel subclass) with a neutral ``!`` placeholder;
- S3-3: series filmstrip capped at ``FILMSTRIP_MAX_CELLS`` cells with a
  ``+N more`` / ``scrollable strip`` informational tile;
- S3-4: per-item Restore button text ``↩ Restore``.

Runs headless (QT_QPA_PLATFORM=offscreen).
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

from tabs.image_gallery.ui.clean_review import (
    FILMSTRIP_MAX_CELLS,
    THUMB_HEIGHT_PX,
    THUMB_WIDTH_PX,
    CleanReviewOverlay,
)
from sli_ui_toolkit.managers import scaled_px

_KEEP_ALIVE: list[QWidget] = []


def _make_owner(tmp_path, rejected_paths: list[str], folder: str | None = None):
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
    return SimpleNamespace(state=SimpleNamespace(items=items, folder=folder))


def _make_overlay(qtbot, owner) -> CleanReviewOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    overlay = CleanReviewOverlay(parent, owner=owner)
    qtbot.addWidget(overlay)
    overlay._populate(owner)
    # pytest-qt keeps only weakrefs; a top-level parent with no Python
    # reference would be GC-collected and destroy the overlay with it.
    _KEEP_ALIVE.append(parent)
    return overlay


# -- S3-1 -----------------------------------------------------------


def test_subtitle_reassurance_line(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")], folder=str(tmp_path))
    overlay = _make_overlay(qtbot, owner)

    subtitle = overlay._subtitle.text()
    assert "2 files will be moved to" in subtitle
    assert f"{tmp_path}/_rejected/" in subtitle
    assert "nothing is deleted" in subtitle
    assert "Undo available for 10 s" in subtitle


def test_subtitle_folder_literal_fallback(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")], folder=None)
    overlay = _make_overlay(qtbot, owner)

    assert "<folder>/_rejected/" in overlay._subtitle.text()


def test_title_is_mockup_copy(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    assert overlay._title.text() == "Review rejected files"


# -- S3-2 -----------------------------------------------------------


def test_thumbs_are_toolkit_labels_150x100(qtbot, tmp_path):
    from sli_ui_toolkit.widgets import Label as ToolkitLabel

    owner = _make_owner(tmp_path, [str(tmp_path / f"img_{i}.jpg") for i in range(3)])
    overlay = _make_overlay(qtbot, owner)

    filmstrip = overlay.findChild(QWidget, "clean_review_filmstrip_1")
    assert filmstrip is not None
    thumbs = [w for w in filmstrip.findChildren(ToolkitLabel) if w.objectName() == "clean_review_thumb"]
    assert len(thumbs) == 3
    for thumb in thumbs:
        assert thumb.width() == scaled_px(THUMB_WIDTH_PX)
        assert thumb.height() == scaled_px(THUMB_HEIGHT_PX)
        # No thumbnail loaded -> neutral placeholder text (not the old "IMG").
        assert thumb.text() == "!"


# -- S3-3 -----------------------------------------------------------


def test_filmstrip_capped_with_more_tile(qtbot, tmp_path):
    total = FILMSTRIP_MAX_CELLS + 3
    owner = _make_owner(tmp_path, [str(tmp_path / f"img_{i}.jpg") for i in range(total)])
    overlay = _make_overlay(qtbot, owner)

    filmstrip = overlay.findChild(QWidget, "clean_review_filmstrip_1")
    assert filmstrip is not None
    cells = [w for w in filmstrip.findChildren(QWidget) if w.objectName() == "clean_review_filmstrip_cell"]
    assert len(cells) == FILMSTRIP_MAX_CELLS

    tile = overlay.findChild(QWidget, "clean_review_filmstrip_more")
    assert tile is not None
    assert tile.isEnabled() is False
    row_texts = [
        getattr(row, "text", "")
        for region in tile.regions()
        for row in (getattr(region, "rows", None) or [])
    ]
    assert "+3 more" in row_texts
    assert "scrollable strip" in row_texts


def test_filmstrip_no_tile_under_cap(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / f"img_{i}.jpg") for i in range(FILMSTRIP_MAX_CELLS)])
    overlay = _make_overlay(qtbot, owner)

    assert overlay.findChild(QWidget, "clean_review_filmstrip_more") is None


# -- S3-4 -----------------------------------------------------------


def test_per_item_restore_button_text(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    restore_btns = [
        b for b in overlay.findChildren(type(overlay._restore_all_btn))
        if b.objectName() == "clean_review_restore"
    ]
    assert len(restore_btns) == 1
    assert all(region.text == "↩ Restore" for region in restore_btns[0].regions())
