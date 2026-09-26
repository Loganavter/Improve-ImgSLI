"""S3 design-parity regression tests for CleanReviewOverlay (mockup v3).

Covers audit items S3-1..S3-4 against ``ui/clean_review.py``:

- S3-1: reassurance subtitle under the title —
  ``N files will be moved to <folder>/_rejected/ — nothing is deleted,
  Undo available for 10 s.`` (safety promise shown before the move);
- S3-2: filmstrip thumbs 150x100 (scaled) rendered by the toolkit ``Label``
  component (QLabel subclass) with a neutral ``!`` placeholder;
- S3-3: flat filmstrip capped at ``FILMSTRIP_MAX_CELLS`` cells total with
  a ``+N more`` / ``scrollable strip`` informational tile, inside ONE
  horizontally scrollable, frameless strip (mockup v3 "scrollable strip";
  no per-series boxes or headers);
- S3-4: per-item Restore button text ``↩ Restore``.
- S3-5 (close-out): provenance line below the filmstrip with a ``from: ``
  prefix (svg:100); move toast ``Moved N files`` with ``success=True``
  and no MB suffix (svg toast preview); app-side dim veil 0.45 (P0-10).

Runs headless (QT_QPA_PLATFORM=offscreen).
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from tabs.image_gallery.ui.clean_review import (
    DIM_VEIL_ALPHA,
    FILMSTRIP_MAX_CELLS,
    REVIEW_CARD_HEIGHT_PX,
    REVIEW_CARD_WIDTH_PX,
    THUMB_HEIGHT_PX,
    THUMB_WIDTH_PX,
    CleanReviewOverlay,
    _ReviewPlate,
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


def test_subtitle_falls_back_to_common_parent(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")], folder=None)
    overlay = _make_overlay(qtbot, owner)

    assert f"{tmp_path}/_rejected/" in overlay._subtitle.text()


def test_subtitle_folder_literal_last_resort(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [], folder=None)
    overlay = _make_overlay(qtbot, owner)

    assert "<folder>/_rejected/" in overlay._subtitle.text()


def test_title_is_mockup_copy(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    assert overlay._title.text() == "Review rejected files"


# -- Phase 2: header (mockup v3 svg:43-45: title 16 bold + 12 muted + rule) -


def test_header_title_16_bold(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    assert overlay._title.text() == "Review rejected files"
    assert overlay._title.font().pixelSize() == 16
    assert overlay._title.font().bold() is True


def test_header_subtitle_14_muted_wrap(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    assert overlay._subtitle.font().pixelSize() == 14
    assert overlay._subtitle.variant() == "caption"
    assert overlay._subtitle.wordWrap() is True


def test_header_divider_present_and_ordered(qtbot, tmp_path):
    from tabs.image_gallery.ui.quick_look.helpers import _RuleWidget

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    rule = overlay.findChild(QWidget, "clean_review_header_rule")
    assert rule is not None
    assert isinstance(rule, _RuleWidget)
    assert rule.isVisibleTo(overlay)
    layout = overlay._content.layout()
    # Header row (title + subtitle + ✕) precedes the divider rule precedes
    # the strip; title precedes subtitle inside the header's title column.
    header_pos = rule_pos = scroll_pos = None
    header = None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is rule:
            rule_pos = i
        elif item.widget() is overlay._scroll:
            scroll_pos = i
        elif item.layout() is not None and item.layout().indexOf(overlay._close_btn) >= 0:
            header_pos = i
            header = item.layout()
    assert header_pos is not None and rule_pos is not None and scroll_pos is not None
    assert header_pos < rule_pos < scroll_pos
    assert header is not None
    title_col = header.itemAt(0).layout()
    assert title_col is not None
    assert title_col.itemAt(0).widget() is overlay._title
    assert title_col.itemAt(1).widget() is overlay._subtitle


# -- S3-2 -----------------------------------------------------------


def test_thumbs_are_toolkit_labels_150x100(qtbot, tmp_path):
    from sli_ui_toolkit.widgets import Label as ToolkitLabel

    owner = _make_owner(tmp_path, [str(tmp_path / f"img_{i}.jpg") for i in range(3)])
    overlay = _make_overlay(qtbot, owner)

    filmstrip = overlay.findChild(QWidget, "clean_review_filmstrip")
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

    filmstrip = overlay.findChild(QWidget, "clean_review_filmstrip")
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


def _make_multi_series_owner(tmp_path):
    items = [
        SimpleNamespace(
            rejected=True,
            path=str(tmp_path / f"sunset_{i}.jpg"),
            name=f"sunset_{i}.jpg",
            thumbnail=None,
            provenance_series_id="series_1",
        )
        for i in range(2)
    ] + [
        SimpleNamespace(
            rejected=True,
            path=str(tmp_path / "city_0.png"),
            name="city_0.png",
            thumbnail=None,
            provenance_series_id="series_2",
        )
    ]
    return SimpleNamespace(state=SimpleNamespace(items=items, folder=str(tmp_path)))


# -- S3-5: provenance prefix + position --------------------------------


def test_provenance_has_from_prefix(qtbot, tmp_path):
    owner = _make_multi_series_owner(tmp_path)
    overlay = _make_overlay(qtbot, owner)

    text = overlay._provenance_label.text()
    assert re.match(r"^from:", text), text
    assert "SERIES 1" in text
    assert "SERIES 2" in text


def test_provenance_omits_count_for_singletons(qtbot, tmp_path):
    """A lone hub needs no `` (1)`` — filenames like ``pic(1)`` would
    stutter into ``(1) (1)``."""
    from types import SimpleNamespace

    items = [
        SimpleNamespace(
            rejected=True,
            path=str(tmp_path / "pic(1).jpg"),
            name="pic(1).jpg",
            thumbnail=None,
            provenance_series_id="series_1",
        ),
        SimpleNamespace(
            rejected=True,
            path=str(tmp_path / "other.jpg"),
            name="other.jpg",
            thumbnail=None,
            provenance_series_id="series_2",
        ),
    ]
    owner = SimpleNamespace(state=SimpleNamespace(items=items, folder=str(tmp_path)))
    overlay = _make_overlay(qtbot, owner)

    text = overlay._provenance_label.text()
    assert text == "from: SERIES 1 · pic(1) · SERIES 2 · other", text


def test_provenance_keeps_count_for_multiples(qtbot, tmp_path):
    from types import SimpleNamespace

    items = [
        SimpleNamespace(
            rejected=True,
            path=str(tmp_path / f"{name}.jpg"),
            name=f"{name}.jpg",
            thumbnail=None,
            provenance_series_id="series_1",
        )
        for name in ("a", "b", "c")
    ]
    owner = SimpleNamespace(state=SimpleNamespace(items=items, folder=str(tmp_path)))
    overlay = _make_overlay(qtbot, owner)

    assert overlay._provenance_label.text() == "from: SERIES 1 · a (3)", overlay._provenance_label.text()


def test_move_title_is_bare_count(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")], folder=str(tmp_path))
    overlay = _make_overlay(qtbot, owner)

    title = "".join(getattr(region, "text", "") or "" for region in overlay._move_btn.regions())
    assert title == "Move 2", title


def test_move_hover_stays_dark_accent(qtbot, tmp_path):
    """Hover must not stack the light surface wash over the accent."""
    from PySide6.QtGui import QColor

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    hover = overlay._move_btn.hover_color()
    assert isinstance(hover, QColor)
    accent = getattr(overlay._move_btn, "_override_bg_color", None)
    assert isinstance(accent, QColor)
    assert hover.lightness() < accent.lightness()


def test_provenance_below_filmstrip(qtbot, tmp_path):
    """Mockup v3 (svg:100) draws the provenance line under the thumbs."""
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    layout = overlay._content.layout()
    assert layout.indexOf(overlay._scroll) < layout.indexOf(overlay._provenance_label)


# -- S3-5: toast copy --------------------------------------------------


def test_move_toast_files_no_mb_suffix_success(qtbot, tmp_path, monkeypatch):
    """Toast matches ``Moved N files`` (svg toast preview): no ``file(s)``,
    no MB suffix, green-check ``success=True``."""
    import tabs.image_gallery.use_cases.triage as triage

    moves = [
        {"src": str(tmp_path / "a.jpg"), "dst": str(tmp_path / "_rejected" / "a.jpg")},
        {"src": str(tmp_path / "b.jpg"), "dst": str(tmp_path / "_rejected" / "b.jpg")},
    ]
    monkeypatch.setattr(triage, "clean_rejected", lambda owner: list(moves))

    seen: list[tuple[str, dict]] = []

    class _FakeToast:
        def show_toast(self, msg, **kwargs):
            seen.append((msg, kwargs))

    monkeypatch.setattr(
        CleanReviewOverlay, "_ensure_toast_manager", lambda self, window: _FakeToast()
    )

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")])
    overlay = _make_overlay(qtbot, owner)
    overlay._on_move()

    assert len(seen) == 1
    msg, kwargs = seen[0]
    assert re.fullmatch(r"Moved \d+ files to _rejected/", msg), msg
    assert "MB" not in msg
    assert kwargs.get("success") is True
    assert kwargs.get("duration") == 10000
    actions = kwargs.get("actions") or []
    assert any(getattr(a, "text", getattr(a, "label", "")) == "Undo" for a in actions)


# -- S3-3: horizontal scroll past cap ----------------------------------


def test_filmstrip_horizontally_scrollable(qtbot, tmp_path):
    total = FILMSTRIP_MAX_CELLS + 3
    owner = _make_owner(tmp_path, [str(tmp_path / f"img_{i}.jpg") for i in range(total)])
    overlay = _make_overlay(qtbot, owner)

    strip = overlay.findChild(QScrollArea, "clean_review_filmstrip")
    assert strip is not None
    assert strip.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert strip.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert strip.widget() is not None
    # Cap + tile still hold inside the scrollable strip.
    cells = [
        w for w in strip.findChildren(QWidget)
        if w.objectName() == "clean_review_filmstrip_cell"
    ]
    assert len(cells) == FILMSTRIP_MAX_CELLS
    assert strip.findChild(QWidget, "clean_review_filmstrip_more") is not None


# -- Phase 3: horizontal filmstrip (mockup v3: one thumb row, 150x100) --


def test_filmstrip_strip_direction_horizontal(qtbot, tmp_path):
    """The flat strip is HORIZONTAL: inner container uses QHBoxLayout
    (LTR) inside a Qt.Horizontal QScrollArea; cells share one row
    (equal y, strictly increasing x)."""
    from PySide6.QtWidgets import QHBoxLayout

    owner = _make_owner(tmp_path, [str(tmp_path / f"img_{i}.jpg") for i in range(3)])
    overlay = _make_overlay(qtbot, owner)

    strip = overlay.findChild(QScrollArea, "clean_review_filmstrip")
    assert strip is not None
    inner = overlay.findChild(QWidget, "clean_review_filmstrip_inner")
    assert inner is not None
    layout = inner.layout()
    assert isinstance(layout, QHBoxLayout)
    assert layout.direction() == QHBoxLayout.Direction.LeftToRight

    cells = [w for w in strip.findChildren(QWidget) if w.objectName() == "clean_review_filmstrip_cell"]
    assert len(cells) == 3
    cells.sort(key=lambda w: w.x())
    assert len({c.y() for c in cells}) == 1
    xs = [c.x() for c in cells]
    assert xs == sorted(xs) and len(set(xs)) == len(xs)


def test_filmstrip_thumb_row_top_aligned_with_more_tile(qtbot, tmp_path):
    """Over cap: cells + the +N tile share the thumb-row top edge (mockup
    v3 draws the dashed tile at the same y as the thumbs); tile geometry
    is 150x100 like the thumbs."""
    total = FILMSTRIP_MAX_CELLS + 3
    owner = _make_owner(tmp_path, [str(tmp_path / f"img_{i}.jpg") for i in range(total)])
    overlay = _make_overlay(qtbot, owner)
    overlay.show()
    qtbot.waitExposed(overlay)

    strip = overlay.findChild(QScrollArea, "clean_review_filmstrip")
    assert strip is not None
    cells = sorted(
        (w for w in strip.findChildren(QWidget) if w.objectName() == "clean_review_filmstrip_cell"),
        key=lambda w: w.x(),
    )
    assert len(cells) == FILMSTRIP_MAX_CELLS
    tile = strip.findChild(QWidget, "clean_review_filmstrip_more")
    assert tile is not None
    assert tile.width() == scaled_px(THUMB_WIDTH_PX)
    assert tile.height() == scaled_px(THUMB_HEIGHT_PX)
    # Tile sits in the same row, after the last cell ...
    assert tile.x() > cells[-1].x()
    # ... and top-aligned with the row (cell padding tolerance), not
    # vertically centered.
    assert abs(tile.y() - cells[0].y()) <= scaled_px(8)


# -- Phase 6: flat strip (mockup v3: ONE borderless strip, no sections) --


def test_no_per_series_sections_headers_or_series_restore(qtbot, tmp_path):
    """Phase 6: multi-series rejected build NO section boxes, NO header
    rows, NO per-series Restore buttons — only the flat strip, per-thumb
    Restore, and Restore all remain (series survive in the provenance
    line, asserted separately)."""
    owner = _make_multi_series_owner(tmp_path)
    overlay = _make_overlay(qtbot, owner)

    for prefix in (
        "clean_review_series_",
        "clean_review_series_header_",
        "clean_review_series_label_",
        "clean_review_restore_series_",
    ):
        assert [
            w.objectName()
            for w in overlay.findChildren(QWidget)
            if w.objectName().startswith(prefix)
        ] == []
    series_buttons = [
        b
        for b in overlay.findChildren(type(overlay._restore_all_btn))
        if "SERIES" in "".join(getattr(region, "text", "") for region in b.regions())
    ]
    assert series_buttons == []


def test_flat_strip_spans_all_series_in_stable_order(qtbot, tmp_path):
    """Phase 6: exactly ONE strip holds every rejected item across series
    (stable SERIES order, state order within a series); per-thumb filenames
    ride the Restore-button tooltips in the same order."""
    owner = _make_multi_series_owner(tmp_path)
    overlay = _make_overlay(qtbot, owner)

    strips = overlay.findChildren(QScrollArea, "clean_review_filmstrip")
    assert len(strips) == 1
    names = [
        b.toolTip()
        for b in strips[0].findChildren(type(overlay._restore_all_btn))
        if b.objectName() == "clean_review_restore"
    ]
    assert names == ["sunset_0.jpg", "sunset_1.jpg", "city_0.png"]
    restores = [
        b
        for b in strips[0].findChildren(type(overlay._restore_all_btn))
        if b.objectName() == "clean_review_restore"
    ]
    assert len(restores) == 3


def test_flat_cap_applies_across_series(qtbot, tmp_path):
    """Phase 6: FILMSTRIP_MAX_CELLS + the single +N tile apply to the
    COMBINED total across series (not per series)."""
    split = 5
    rest = FILMSTRIP_MAX_CELLS + 4 - split
    items = [
        SimpleNamespace(
            rejected=True,
            path=str(tmp_path / f"sunset_{i}.jpg"),
            name=f"sunset_{i}.jpg",
            thumbnail=None,
            provenance_series_id="series_1",
        )
        for i in range(split)
    ] + [
        SimpleNamespace(
            rejected=True,
            path=str(tmp_path / f"city_{i}.png"),
            name=f"city_{i}.png",
            thumbnail=None,
            provenance_series_id="series_2",
        )
        for i in range(rest)
    ]
    owner = SimpleNamespace(state=SimpleNamespace(items=items, folder=str(tmp_path)))
    overlay = _make_overlay(qtbot, owner)

    strip = overlay.findChild(QScrollArea, "clean_review_filmstrip")
    assert strip is not None
    cells = [
        w for w in strip.findChildren(QWidget)
        if w.objectName() == "clean_review_filmstrip_cell"
    ]
    assert len(cells) == FILMSTRIP_MAX_CELLS
    tiles = overlay.findChildren(QWidget, "clean_review_filmstrip_more")
    assert len(tiles) == 1
    row_texts = [
        getattr(row, "text", "")
        for region in tiles[0].regions()
        for row in (getattr(region, "rows", None) or [])
    ]
    assert "+4 more" in row_texts


def test_scroll_areas_frameless_horizontal_only(qtbot, tmp_path):
    """Phase 6: both scroll areas are NoFrame, vertical AlwaysOff,
    horizontal AsNeeded (borderless strip over the plate)."""
    from PySide6.QtWidgets import QFrame

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    strip = overlay.findChild(QScrollArea, "clean_review_filmstrip")
    assert strip is not None
    for scroll in (overlay._scroll, strip):
        assert scroll.frameShape() == QFrame.Shape.NoFrame
        assert scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


# -- P0-10: app-side dim veil ------------------------------------------


def test_veil_alpha_matches_mockup(qtbot):
    from sli_ui_toolkit.widgets import TopLevelInWindowOverlay

    assert CleanReviewOverlay.paintEvent is not TopLevelInWindowOverlay.paintEvent
    assert DIM_VEIL_ALPHA == round(0.45 * 255) == 115


def test_veil_dims_background(qtbot):
    """The overlay paints a fullscreen 0.45-black veil (offscreen ``grab``
    returns the raw translucent pixel, so assert alpha + blackness; the
    window system composites it over the parent ≈ 140 gray on white)."""
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.setAutoFillBackground(True)
    pal = parent.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor("white"))
    parent.setPalette(pal)
    parent.resize(800, 600)
    parent.show()

    overlay = CleanReviewOverlay(parent)
    qtbot.addWidget(overlay)
    overlay._content.hide()  # veil only — no content plate over the sample
    overlay.setGeometry(parent.rect())
    overlay.show()
    QApplication.processEvents()

    try:
        pixel = overlay.grab().toImage().pixelColor(5, 5)
    finally:
        overlay.hide()
    assert abs(pixel.alpha() - DIM_VEIL_ALPHA) <= 2, pixel.alpha()
    assert pixel.red() == pixel.green() == pixel.blue() == 0
    _KEEP_ALIVE.append(parent)


def test_show_for_sizes_overlay_to_parent(qtbot, tmp_path):
    """show_for must size the overlay to the parent (QuickLook idiom).

    Regression: show_for called bare show(), never show_overlay(), so the
    overlay kept stale geometry and painted ~nothing ("S3 barely renders").
    """
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")], folder=str(tmp_path))
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(800, 600)
    parent.show()
    overlay = CleanReviewOverlay(parent, owner=owner)
    qtbot.addWidget(overlay)
    _KEEP_ALIVE.append(parent)
    overlay.show_for(owner)
    assert overlay.geometry() == parent.rect()
    assert overlay._content.isVisibleTo(overlay)


# -- Phase 1: card plate (mockup v3: 900x440 white card, rx12) ----------


def test_review_plate_min_size_matches_mockup(qtbot, tmp_path):
    """_content is a _ReviewPlate with the mockup 900x440 floor (scaled);
    the overlay sizeHint mirrors it (QuickLook :848 idiom)."""
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    assert isinstance(overlay._content, _ReviewPlate)
    assert _ReviewPlate.paintEvent is not QWidget.paintEvent
    assert overlay._content.minimumWidth() == scaled_px(REVIEW_CARD_WIDTH_PX)
    assert overlay._content.minimumHeight() == scaled_px(REVIEW_CARD_HEIGHT_PX)
    assert REVIEW_CARD_WIDTH_PX == 900
    assert REVIEW_CARD_HEIGHT_PX == 440
    assert overlay.sizeHint().width() == scaled_px(REVIEW_CARD_WIDTH_PX)
    assert overlay.sizeHint().height() == scaled_px(REVIEW_CARD_HEIGHT_PX)


def test_review_plate_paints_fill_and_border(qtbot):
    """Bare-plate grab: center pixel == resolved bg fill, mid-left edge
    pixel == resolved 1px border (both theme tokens, no hardcoded QColor)."""
    plate = _ReviewPlate()
    qtbot.addWidget(plate)
    plate.resize(scaled_px(REVIEW_CARD_WIDTH_PX), scaled_px(REVIEW_CARD_HEIGHT_PX))
    plate.show()
    QApplication.processEvents()

    assert plate._bg is not None
    assert plate._border is not None
    img = plate.grab().toImage()
    center = img.pixelColor(img.width() // 2, img.height() // 2)
    assert (center.red(), center.green(), center.blue()) == (
        plate._bg.red(), plate._bg.green(), plate._bg.blue(),
    )
    # Border is a 1px pen inside rect.adjusted(1,1,-1,-1): sample the
    # mid-left edge; allow small AA blend toward the fill.
    edge = img.pixelColor(1, img.height() // 2)
    for got, want in (
        (edge.red(), plate._border.red()),
        (edge.green(), plate._border.green()),
        (edge.blue(), plate._border.blue()),
    ):
        assert abs(got - want) <= 16, (got, want)
    _KEEP_ALIVE.append(plate)


def test_review_plate_centered_on_veil(qtbot, tmp_path):
    """After show_for, the plate sits centered on the fullscreen veil
    (equal margins on each axis, ±2px rounding)."""
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")], folder=str(tmp_path))
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(1200, 800)
    parent.show()
    overlay = CleanReviewOverlay(parent, owner=owner)
    qtbot.addWidget(overlay)
    _KEEP_ALIVE.append(parent)
    overlay.show_for(owner)
    QApplication.processEvents()

    cg = overlay._content.geometry()
    left, top = cg.x(), cg.y()
    right = overlay.width() - (cg.x() + cg.width())
    bottom = overlay.height() - (cg.y() + cg.height())
    assert left > 0 and top > 0
    assert abs(left - right) <= 2, (left, right)
    assert abs(top - bottom) <= 2, (top, bottom)


# -- Phase 4: bottom bar on plate (mockup v3 svg:103-117) ----------------


def test_bottom_bar_order_restore_stats_cancel_move(qtbot, tmp_path):
    """Mockup v3 svg:105-117: Restore all | stats | Cancel | Move N."""
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    bar = overlay.findChild(QWidget, "clean_review_bar")
    assert bar is not None
    layout = bar.layout()
    order = [
        layout.indexOf(overlay._restore_all_btn),
        layout.indexOf(overlay._size_label),
        layout.indexOf(overlay._cancel_btn),
        layout.indexOf(overlay._move_btn),
    ]
    assert all(i >= 0 for i in order)
    assert order == sorted(order)


def test_bottom_bar_on_plate_with_footer_rule(qtbot, tmp_path):
    """Bar lives on the plate (_content) below provenance; footer divider
    (mockup v3 svg:104) sits between provenance and bar."""
    from tabs.image_gallery.ui.quick_look.helpers import _RuleWidget

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    bar = overlay.findChild(QWidget, "clean_review_bar")
    assert bar is not None
    assert bar.parentWidget() is overlay._content
    rule = overlay.findChild(QWidget, "clean_review_footer_rule")
    assert rule is not None
    assert isinstance(rule, _RuleWidget)
    outer = overlay._content.layout()
    assert outer.indexOf(overlay._provenance_label) < outer.indexOf(rule)
    assert outer.indexOf(rule) < outer.indexOf(bar)


def test_bottom_bar_stats_centered_text(qtbot, tmp_path):
    """Stats label is AlignCenter with ``N files · X MB`` copy."""
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")])
    overlay = _make_overlay(qtbot, owner)

    assert overlay._size_label.alignment() & Qt.AlignmentFlag.AlignCenter
    assert re.fullmatch(r"2 files · \d+\.\d+ MB", overlay._size_label.text()), (
        overlay._size_label.text()
    )


def test_bottom_bar_move_accent_background(qtbot, tmp_path):
    """Move is SOLID accent (override_bg exact) + white text.

    ``set_background_color`` on surface only yields a tint fill
    (derive_custom_palette) — the hollow light-blue look. Override paints
    exact; toolkit ``primary`` variant is deprecated. No bold API on
    Button — white non-bold is the accepted mockup deviation.
    """
    from PySide6.QtGui import QColor as _QC

    from tabs.image_gallery.ui.quick_look import _token_color

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    assert overlay._move_btn._custom_bg_color is None  # tint path unused
    override = getattr(overlay._move_btn, "_override_bg_color", None)
    assert override is not None
    assert _QC(override).name().lower() == _token_color("accent", "#0096FF").name().lower()
    assert overlay._move_btn.property("foregroundColor") == _QC("#ffffff")


# -- Phase 5: theme parity (mockup light + dark via tokens only) ---------


@pytest.fixture()
def _production_palettes(qapp):
    """Register production palettes; teardown restores the bare manager.

    Mirrors the ``_production_dark_palettes`` idiom in
    ``tests/runtime/test_card_parity.py``: bare-manager fallbacks are
    light-pinned, so theme-parity asserts boot the real palettes and
    compare hex-exact against the live ``themes.json``.
    """
    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from sli_ui_toolkit.managers import ThemeManager

    tm = ThemeManager.get_instance()
    prev_theme = tm.get_current_theme()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    yield tm
    try:
        tm.register_palettes({}, {})
        tm.set_theme(prev_theme, qapp, await_ripples=False)
        try:
            tm._flush_pending_theme()  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception:
        pass


def _set_theme(tm, qapp, name: str) -> None:
    tm.set_theme(name, qapp, await_ripples=False)
    try:
        tm._flush_pending_theme()  # type: ignore[attr-defined]
    except Exception:
        pass
    qapp.processEvents()


def _themes_data() -> dict:
    from utils.resource_loader import resource_path

    with open(resource_path("resources/themes.json"), encoding="utf-8") as f:
        return json.load(f)


def test_review_plate_bg_border_match_themes_json_in_both_themes(
    qtbot, qapp, _production_palettes
):
    """Plate bg/border resolve via token chains on BOTH themes, hex-exact
    against the live themes.json (never duplicated here, so no hardcoded
    literals in test code either)."""
    tm = _production_palettes
    data = _themes_data()

    for theme in ("light", "dark"):
        _set_theme(tm, qapp, theme)
        assert tm.get_current_theme() == theme

        plate = _ReviewPlate()
        qtbot.addWidget(plate)
        plate.resize(scaled_px(REVIEW_CARD_WIDTH_PX), scaled_px(REVIEW_CARD_HEIGHT_PX))
        plate.show()
        QApplication.processEvents()

        assert plate._bg is not None, f"bg unresolvable under {theme}"
        assert plate._border is not None, f"border unresolvable under {theme}"
        # QColor.name() drops alpha on both sides, so the dark 8-digit
        # border ("#1EFFFFFF") still compares exactly.
        assert plate._bg.name().lower() == QColor(data[theme]["gallery.card.background"]).name().lower(), theme
        assert plate._border.name().lower() == QColor(data[theme]["gallery.card.border"]).name().lower(), theme
        # Repaint path must not crash offscreen on either theme.
        assert not plate.grab().isNull()


def test_review_plate_tracks_light_dark_flip(qtbot, qapp, _production_palettes):
    """One plate across light → dark → light re-resolves and repaints;
    round-trip lands back on the light production values."""
    tm = _production_palettes
    data = _themes_data()

    plate = _ReviewPlate()
    qtbot.addWidget(plate)
    plate.resize(scaled_px(REVIEW_CARD_WIDTH_PX), scaled_px(REVIEW_CARD_HEIGHT_PX))
    plate.show()
    QApplication.processEvents()

    for theme in ("light", "dark", "light"):
        _set_theme(tm, qapp, theme)
        try:
            plate.on_theme_changed()
        except Exception:
            pass
        QApplication.processEvents()
        assert plate._bg.name().lower() == QColor(data[theme]["gallery.card.background"]).name().lower(), theme
        assert plate._border.name().lower() == QColor(data[theme]["gallery.card.border"]).name().lower(), theme
        assert not plate.grab().isNull()

    assert plate._bg.name().lower() == QColor(data["light"]["gallery.card.background"]).name().lower()
    assert plate._border.name().lower() == QColor(data["light"]["gallery.card.border"]).name().lower()


def test_move_accent_matches_theme_at_construction(qtbot, qapp, _production_palettes, tmp_path):
    """Move button accent is the construction theme's ``accent`` token
    (surface + set_override_bg_color exact-fill idiom), hex-exact per theme."""
    tm = _production_palettes
    data = _themes_data()

    for theme in ("light", "dark"):
        _set_theme(tm, qapp, theme)
        owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
        overlay = _make_overlay(qtbot, owner)
        expected = QColor(data[theme]["accent"]).name().lower()
        got = getattr(overlay._move_btn, "_override_bg_color", None)
        got = (got if isinstance(got, QColor) else QColor(got)).name().lower()
        assert got == expected, f"accent under {theme}: {got} != themes.json {expected}"


def test_move_button_paints_solid_accent(qtbot, tmp_path):
    """Pixel witness: Move fill is solid accent, not a hollow tint."""
    from tabs.image_gallery.ui.quick_look import _token_color

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)
    overlay.show_for(owner)
    qtbot.waitExposed(overlay)

    btn = overlay._move_btn
    img = btn.grab().toImage()
    # Left padding pixel: the (now longer, folder-naming) title is centered,
    # so the middle row's center may land on a white glyph — sample the fill
    # clear of the text.
    bg = img.pixelColor(6, img.height() // 2)
    accent = _token_color("accent", "#0096FF")
    assert abs(bg.red() - accent.red()) <= 12
    assert abs(bg.green() - accent.green()) <= 12
    assert abs(bg.blue() - accent.blue()) <= 12
    overlay.hide()


def test_thumb_cell_has_no_provenance_sublabel(qtbot, tmp_path):
    """Mockup v3 thumb cell: thumbnail + Restore only (recent-panel idiom).

    No per-thumb name label (the filename rides the Restore tooltip) and
    no per-thumb series sublabel (series live in the provenance line).
    """
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)
    overlay.show_for(owner)
    assert overlay.findChild(QWidget, "clean_review_row_provenance") is None
    assert overlay.findChild(QWidget, "clean_review_row_name") is None
    restore = overlay.findChild(QWidget, "clean_review_restore")
    assert restore is not None
    assert restore.toolTip() == "a.jpg"
    overlay.hide()


# -- Quick Look behavior parity -------------------------------------------
# Close paths (veil click, Esc, top-right ✕) close; minimize/focus loss
# stay pinned; the corner grip resizes the card.


def test_close_policy_matches_quick_look(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)
    assert overlay._close_on_background is True
    assert overlay._close_on_escape is True
    assert overlay._close_on_deactivate is False
    overlay.hide()


def test_close_button_hides_overlay(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)
    overlay.show_for(owner)
    qtbot.waitExposed(overlay)
    assert overlay.isVisible()
    qtbot.mouseClick(overlay._close_btn, Qt.MouseButton.LeftButton)
    assert not overlay.isVisible()


def test_veil_click_dismisses_overlay(qtbot, tmp_path):
    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)
    overlay.show_for(owner)
    qtbot.waitExposed(overlay)
    assert overlay.isVisible()
    from PySide6.QtCore import QPoint, QEvent
    from PySide6.QtGui import QMouseEvent

    pos = QPoint(4, 4)  # veil: outside the centered card
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        overlay.mapToGlobal(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press)
    assert press.isAccepted()
    assert not overlay.isVisible()


def test_minimize_hide_does_not_dismiss(qtbot, tmp_path):
    """Ancestor-driven hides (window minimize) are not a dismiss."""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)
    overlay.show_for(owner)
    qtbot.waitExposed(overlay)
    parent = overlay.parentWidget()
    assert parent is not None
    parent.hide()  # ancestor hide: overlay.isHidden() stays False
    assert not overlay.isHidden()
    parent.show()
    qtbot.waitExposed(overlay)
    assert overlay.isVisible()
    # A real WindowDeactivate (what minimize delivers) must not dismiss
    # either — close_on_deactivate stays False, Quick Look parity.
    app = QApplication.instance()
    assert app is not None
    app.sendEvent(parent, QEvent(QEvent.Type.WindowDeactivate))
    qtbot.wait(50)
    assert not overlay.isHidden()
    assert overlay.isVisible()
    overlay.hide()


def test_resize_grip_drags_card(qtbot, tmp_path):
    from PySide6.QtCore import QPoint, QEvent
    from PySide6.QtGui import QMouseEvent

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)
    parent = overlay.parentWidget()
    assert parent is not None
    parent.resize(1400, 900)
    overlay.show_for(owner)
    qtbot.waitExposed(overlay)
    content = overlay._content
    grip = overlay._resize_grip
    start_size = content.size()
    assert start_size.width() >= 1 and start_size.height() >= 1

    center = grip.rect().center()
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        center,
        grip.mapToGlobal(center),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    grip.mousePressEvent(press)
    assert press.isAccepted()
    moved = center + QPoint(120, 80)
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        moved,
        grip.mapToGlobal(moved),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    grip.mouseMoveEvent(move)
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        moved,
        grip.mapToGlobal(moved),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    grip.mouseReleaseEvent(release)
    grown = content.size()
    assert grown.width() == start_size.width() + 120
    assert grown.height() == start_size.height() + 80
    # Grip stays pinned to the card's bottom-right corner.
    assert grip.pos() == content.rect().bottomRight() - grip.rect().bottomRight()
    overlay.hide()


def _s3_mouse_event(kind, local, widget):
    from PySide6.QtCore import QPoint, QEvent
    from PySide6.QtGui import QMouseEvent

    global_pos = widget.mapToGlobal(local)
    if kind == "press":
        return QMouseEvent(
            QEvent.Type.MouseButtonPress,
            local,
            global_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    if kind == "release":
        return QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            local,
            global_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    buttons = (
        Qt.MouseButton.LeftButton
        if kind == "drag"
        else Qt.MouseButton.NoButton
    )
    return QMouseEvent(
        QEvent.Type.MouseMove,
        local,
        global_pos,
        Qt.MouseButton.NoButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def _s3_shown_overlay(qtbot, tmp_path):
    from PySide6.QtCore import QPoint

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)
    parent = overlay.parentWidget()
    assert parent is not None
    parent.resize(1400, 900)
    overlay.show_for(owner)
    qtbot.waitExposed(overlay)
    return overlay


def test_border_drag_right_edge_grows_card(qtbot, tmp_path):
    from PySide6.QtCore import QPoint

    overlay = _s3_shown_overlay(qtbot, tmp_path)
    content = overlay._content
    start_geom = content.geometry()
    assert overlay.eventFilter(
        content, _s3_mouse_event("press", QPoint(start_geom.width() - 4, start_geom.height() // 2), content)
    )
    assert overlay.eventFilter(
        content,
        _s3_mouse_event("drag", QPoint(start_geom.width() + 56, start_geom.height() // 2), content),
    )
    assert overlay.eventFilter(content, _s3_mouse_event("release", QPoint(0, 0), content))
    grown = content.geometry()
    assert grown.width() == start_geom.width() + 60
    assert grown.height() == start_geom.height()
    assert grown.x() == start_geom.x()  # right drags keep the left anchor
    assert overlay._border_drag is None
    overlay.hide()


def test_border_drag_left_edge_moves_anchor(qtbot, tmp_path):
    from PySide6.QtCore import QPoint

    overlay = _s3_shown_overlay(qtbot, tmp_path)
    content = overlay._content
    start_geom = content.geometry()
    assert overlay.eventFilter(content, _s3_mouse_event("press", QPoint(4, start_geom.height() // 2), content))
    assert overlay.eventFilter(
        content, _s3_mouse_event("drag", QPoint(4 - 40, start_geom.height() // 2), content)
    )
    assert overlay.eventFilter(content, _s3_mouse_event("release", QPoint(0, 0), content))
    grown = content.geometry()
    assert grown.width() == start_geom.width() + 40
    assert grown.x() == start_geom.x() - 40  # opposite edge tracks the cursor
    overlay.hide()


def test_border_drag_clamps_to_plate_floor(qtbot, tmp_path):
    from PySide6.QtCore import QPoint

    overlay = _s3_shown_overlay(qtbot, tmp_path)
    content = overlay._content
    start_geom = content.geometry()
    assert overlay.eventFilter(
        content, _s3_mouse_event("press", QPoint(start_geom.width() - 4, start_geom.height() // 2), content)
    )
    assert overlay.eventFilter(
        content,
        _s3_mouse_event("drag", QPoint(start_geom.width() - 4000, start_geom.height() // 2), content),
    )
    assert overlay.eventFilter(content, _s3_mouse_event("release", QPoint(0, 0), content))
    assert content.geometry().width() == content.minimumWidth()
    overlay.hide()


def test_border_hover_shows_resize_cursor(qtbot, tmp_path):
    from PySide6.QtCore import QPoint, Qt as _Qt

    overlay = _s3_shown_overlay(qtbot, tmp_path)
    content = overlay._content
    assert not overlay.eventFilter(
        content, _s3_mouse_event("hover", QPoint(content.width() - 4, content.height() // 2), content)
    )
    assert content.cursor().shape() == _Qt.CursorShape.SizeHorCursor
    assert not overlay.eventFilter(
        content, _s3_mouse_event("hover", QPoint(content.width() // 2, content.height() // 2), content)
    )
    assert content.cursor().shape() == _Qt.CursorShape.ArrowCursor
    overlay.hide()


def test_ring_press_starts_drag_without_dismiss(qtbot, tmp_path):
    from PySide6.QtCore import QPoint

    overlay = _s3_shown_overlay(qtbot, tmp_path)
    content = overlay._content
    # Overlay-local point 4px left of the card: outer ring, open veil beyond.
    ring_pos = content.pos() + QPoint(-4, content.height() // 2)
    press = _s3_mouse_event("press", ring_pos, overlay)
    overlay.mousePressEvent(press)
    assert press.isAccepted()
    assert overlay.isVisible()  # ring press drags, never dismisses
    assert overlay._border_drag is not None
    release = _s3_mouse_event("release", ring_pos, overlay)
    overlay.mouseReleaseEvent(release)
    assert overlay._border_drag is None
    assert overlay.isVisible()
    overlay.hide()


def test_filmstrip_cells_are_framed_cards(qtbot, tmp_path):
    """Recent-panel idiom: each filmstrip item is one framed card
    (picture on top, Restore button below), not floating parts."""
    from tabs.image_gallery.ui.clean_review import _ReviewPlate

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")])
    overlay = _make_overlay(qtbot, owner)

    cells = [
        w
        for w in overlay.findChildren(QWidget)
        if w.objectName() == "clean_review_filmstrip_cell"
    ]
    assert len(cells) == 2
    for cell in cells:
        assert isinstance(cell, _ReviewPlate)
        kinds = sorted(type(ch).__name__ for ch in cell.children())
        assert "Button" in kinds  # Restore below
        assert overlay.findChild(QWidget, "clean_review_restore") is not None


def test_thumb_pixmap_has_rounded_top_corners():
    """Card photo: top corners rounded like the other cards, bottom square."""
    from PySide6.QtGui import QColor, QPixmap

    from tabs.image_gallery.ui.clean_review import _rounded_top_pixmap

    src = QPixmap(150, 100)
    src.fill(QColor("#ff0000"))
    out = _rounded_top_pixmap(src, 150, 100)
    assert out.width() == 150 and out.height() == 100
    assert out.toImage().pixelColor(0, 0).alpha() == 0
    assert out.toImage().pixelColor(149, 0).alpha() == 0
    assert out.toImage().pixelColor(0, 99).alpha() == 255
    assert out.toImage().pixelColor(149, 99).alpha() == 255
    assert out.toImage().pixelColor(75, 50).alpha() == 255


def test_restore_button_centered_in_card(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    cell = overlay.findChild(QWidget, "clean_review_filmstrip_cell")
    assert cell is not None
    lay = cell.layout()
    btn_idx = next(
        i
        for i in range(lay.count())
        if lay.itemAt(i).widget() is not None
        and lay.itemAt(i).widget().objectName() == "clean_review_restore"
    )
    assert lay.itemAt(btn_idx).alignment() == Qt.AlignmentFlag.AlignHCenter


def test_card_click_opens_quick_look_not_restore(qtbot, tmp_path):
    """Press on the card photo opens Quick Look; press on Restore does not."""
    from PySide6.QtCore import QPoint

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)
    overlay.show_for(owner)
    qtbot.waitExposed(overlay)

    opened = []
    overlay._open_quick_look_for_item = opened.append  # type: ignore[method-assign]

    cell = overlay.findChild(QWidget, "clean_review_filmstrip_cell")
    assert cell is not None
    thumb = overlay.findChild(QWidget, "clean_review_thumb")
    assert thumb is not None
    pos = thumb.mapTo(cell, thumb.rect().center())
    press = _s3_mouse_event("press", pos, cell)
    assert overlay.eventFilter(cell, press) is True
    assert len(opened) == 1

    restore = overlay.findChild(QWidget, "clean_review_restore")
    assert restore is not None
    pos_btn = restore.mapTo(cell, restore.rect().center())
    assert overlay.eventFilter(cell, _s3_mouse_event("press", pos_btn, cell)) is False
    assert len(opened) == 1
    overlay.hide()


def test_quick_look_close_returns_to_s3(qtbot, tmp_path):
    """Card-click Quick Look hides S3; its Hide (any close path) re-shows S3."""
    from PySide6.QtGui import QHideEvent
    from PySide6.QtWidgets import QWidget

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    shown = []
    ql_stub = QWidget()

    class _StubWidget:
        _quick_look_overlay = ql_stub

        def show_quick_look(self, item):
            shown.append(item)

    stub_owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    stub_owner.widget = _StubWidget()
    overlay._owner = stub_owner
    item = stub_owner.state.items[0]
    overlay._open_quick_look_for_item(item)

    assert shown == [item]
    assert overlay._ql_return is ql_stub
    assert overlay.isHidden()  # S3 hides while Quick Look is up
    overlay.eventFilter(ql_stub, QHideEvent())
    assert overlay._ql_return is None
    assert overlay.isVisible()  # back to S3, repopulated
    overlay.hide()


def test_filmstrip_cards_have_hover_wash(qtbot, tmp_path):
    """Rejected cards tint on hover; the modal plate itself never does."""
    from PySide6.QtCore import QEvent

    from tabs.image_gallery.ui.clean_review import _ReviewPlate

    owner = _make_owner(tmp_path, [str(tmp_path / "a.jpg")])
    overlay = _make_overlay(qtbot, owner)

    cell = overlay.findChild(QWidget, "clean_review_filmstrip_cell")
    assert isinstance(cell, _ReviewPlate)
    assert cell._hover_wash_enabled is True
    assert cell._hovered is False
    cell.enterEvent(QEvent(QEvent.Type.Enter))
    assert cell._hovered is True
    cell.leaveEvent(QEvent(QEvent.Type.Leave))
    assert cell._hovered is False

    assert overlay._content._hover_wash_enabled is False
    overlay._content.enterEvent(QEvent(QEvent.Type.Enter))
    assert overlay._content._hovered is False
