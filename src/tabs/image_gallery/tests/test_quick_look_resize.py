"""Quick look resize re-layout (W12 W-B + W13 stretch) regression tests.

Recompose like the image-save (export) window: the preview pane stretches
with the card while the image inside keeps its aspect. W13: the right
column is min 296px and STRETCHES with the card (scroll area + host
expanding, mid-layout stretch on both sides with the preview keeping
priority) — its bars/histograms fill the live column width while strip
thumbs keep their fixed size. The footer reflows (actions left, hint
right), and all existing reposition hooks re-run on every resize. W8
min-only stays (minimum 1040×680, no maximum); no new close paths.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.ui.quick_look import QuickLookOverlay


def _item(name: str, **kwargs) -> GalleryItem:
    return GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1, **kwargs)


def _real_png(tmp_path: Path, name: str, w: int = 800, h: int = 600) -> Path:
    from PySide6.QtGui import QColor, QPixmap

    pm = QPixmap(w, h)
    pm.fill(QColor("#3a6ea5"))
    p = tmp_path / name
    assert pm.save(str(p), "PNG")
    return p


def _make_overlay(qtbot) -> QuickLookOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent  # strong ref, keeps C++ tree alive
    return ov


def _show(overlay: QuickLookOverlay, item: GalleryItem, series, mode=Mode.FIDELITY, source=None):
    if series and not isinstance(series[0], (list, tuple)):
        series = [list(series)]
    owner = SimpleNamespace(
        state=SimpleNamespace(
            mode=mode,
            source_path=source,
            series=series,
            items=[m for cl in series for m in cl],
        )
    )
    overlay.show_for(item, owner)
    try:
        parent = getattr(overlay, "_parity_test_parent", None) or overlay.parentWidget()
        if parent is not None:
            parent.resize(1280, 800)
            parent.show()
    except Exception:
        pass
    QApplication.processEvents()
    QApplication.processEvents()


def _grow(qtbot, ov, dw: int = 160, dh: int = 80):
    from sli_ui_toolkit.managers import scaled_px

    content = ov._content
    content.resize(content.width() + scaled_px(dw), content.height() + scaled_px(dh))
    QApplication.processEvents()
    QApplication.processEvents()


def test_preview_stretches_with_aspect_on_resize(qtbot, tmp_path):
    """W-B: the preview canvas fills the grown slot; source keeps aspect.

    The GPU canvas is the only live surface — the card resize mirrors the
    host rect onto it (single geometry authority) while the stashed full
    source keeps its aspect inside the frame.
    """
    src_p = _real_png(tmp_path, "src.png")
    v_p = _real_png(tmp_path, "v.png")
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={"width": 800, "height": 600})
    item = GalleryItem(path=v_p, mtime_ns=2, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)

    host = ov._preview_host
    before = host.rect()
    assert getattr(ov, "_preview_full", None) is not None
    assert ov._preview_full.width() == 800
    assert ov._preview_canvas is not None

    _grow(qtbot, ov)
    after = host.rect()
    # Slot grows with the card; the canvas/cover mirror it exactly.
    assert after.width() > before.width()
    assert ov._preview_canvas.geometry() == after
    if ov._preview_cover is not None:
        assert ov._preview_cover.geometry() == after
    # The full source is stashed for re-derivation, not re-decoded per step.
    assert ov._preview_full is not None
    assert ov._preview_full.width() == 800
    ov.hide()


def test_right_column_stretches_with_min_296_on_resize(qtbot, tmp_path):
    """W13: the right column stretches with the card (floor 296, no scroll).

    The column never drops below the mockup 296px floor; a bigger card
    widens it (the preview still takes its priority share of the extra),
    and shrinking back restores the floor-honoring width. No scrollbars
    at any size.
    """
    from sli_ui_toolkit.managers import scaled_px

    src_p = _real_png(tmp_path, "src.png")
    v_p = _real_png(tmp_path, "v.png")
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={})
    item = GalleryItem(path=v_p, mtime_ns=2, metrics={"ssim": 0.9})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)

    scroll = ov.findChild(QScrollArea, "quicklook_right_scroll")
    # The 296 floor is a minimum, not a fixed width: the live width
    # follows the layout distribution (with an unloaded preview the
    # column takes more than the floor even at the minimum card).
    # Column floor is dynamic (296 + 35% of slack, pinned from live card
    # width) — never below the mockup 296px, exact value follows size.
    assert scroll.minimumWidth() >= scaled_px(296)
    width_before = scroll.width()
    assert width_before >= scaled_px(296)

    def _assert_no_scroll():
        assert scroll.horizontalScrollBar().maximum() == 0
        assert scroll.verticalScrollBar().maximum() == 0
        assert scroll.horizontalScrollBar().isVisible() is False
        assert scroll.verticalScrollBar().isVisible() is False

    _assert_no_scroll()
    preview_before = ov._preview_host.width()
    _grow(qtbot, ov)
    # Column stretched with the card...
    assert scroll.width() > width_before
    # ...while the preview kept priority (it grew too).
    assert ov._preview_host.width() > preview_before
    _assert_no_scroll()
    # ...and shrinking back restores the floor-honoring width, never below.
    # Settle loop: fixed-pixel fill segments transiently prop the host
    # minimum open for one layout pass after a shrink (production pumps
    # continuously so it self-corrects; the horizontal bar stays
    # AlwaysOff regardless).
    ov._content.resize(scaled_px(1040), scaled_px(620))
    for _ in range(10):
        QApplication.processEvents()
        QApplication.processEvents()
        if scroll.width() == width_before and scroll.horizontalScrollBar().maximum() == 0:
            break
    assert scroll.width() == width_before
    assert scroll.width() >= scaled_px(296)
    _assert_no_scroll()
    ov.hide()


def test_right_contents_fill_stretched_column(qtbot, tmp_path):
    """W13: bars (metric + artifact, both _BarWidget) fill the stretched
    column; strip thumbs do NOT grow.

    Bar widgets track the live column width (bar count and thumb sizes
    fixed, gaps absorb the extra). Artifacts are unified % bars now, so
    every report bar is a _BarWidget.
    """
    from sli_ui_toolkit.managers import scaled_px
    from sli_ui_toolkit.widgets import Button

    from tabs.image_gallery.models import Artifact, Severity
    from tabs.image_gallery.ui.quick_look.bars import _BarWidget

    src_p = _real_png(tmp_path, "src.png")
    mates = []
    for i in range(4):
        p = _real_png(tmp_path, f"v{i}.png")
        mates.append(
            GalleryItem(
                path=p,
                mtime_ns=i + 2,
                metrics={"ssim": 0.94, "hf_ratio": 0.18, "delta_e": 1.8},
                artifacts={Artifact.BANDING: Severity.MILD},
            )
        )
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], [[src], list(mates)], source=src.path)

    def _widths():
        scroll = ov.findChild(QScrollArea, "quicklook_right_scroll")
        bars = ov._report_host.findChildren(_BarWidget)
        thumbs = [
            b
            for b in ov._strip_host.findChildren(Button)
            if b.objectName().startswith("quicklook_strip_")
        ]
        return scroll, bars, thumbs

    scroll, bars, thumbs = _widths()
    assert bars, "expected bars"
    assert len(thumbs) == 4
    viewport_w = scroll.viewport().width()
    for bar in bars:
        assert abs(bar.width() - viewport_w) <= 4
    col_w_before = scroll.width()
    _grow(qtbot, ov)
    scroll, bars, thumbs = _widths()
    viewport_w = scroll.viewport().width()
    assert scroll.width() > col_w_before
    # Bars track the wider viewport; strip thumbs keep their fixed size.
    for bar in bars:
        assert abs(bar.width() - viewport_w) <= 4
    for b in thumbs:
        assert b.width() == scaled_px(66)
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    ov.hide()


def test_footer_reflows_hint_right_on_resize(qtbot, tmp_path):
    """W-B: footer actions stay left with no overlaps on resize (hint gone)."""
    src_p = _real_png(tmp_path, "src.png")
    v_p = _real_png(tmp_path, "v.png")
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={})
    item = GalleryItem(path=v_p, mtime_ns=2, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)

    def _assert_bar():
        bar = ov._content.findChild(QWidget, "quicklook_bottom_bar")
        assert bar is not None
        # No hint anywhere on the bar.
        assert getattr(ov, "_hint_label", None) is None
        assert bar.findChild(QWidget, "quicklook_hint") is None
        # Compare actions removed — only triage buttons remain.
        assert getattr(ov, "_compare_btn", None) is None
        assert getattr(ov, "_multi_btn", None) is None
        assert bar.findChild(QWidget, "quicklook_compare") is None
        assert bar.findChild(QWidget, "quicklook_multi") is None
        first = ov._reject_btn
        # Actions stay ordered left-to-right with no overlaps.
        cmp_left = first.mapTo(ov._content, first.rect().topLeft()).x()
        assert cmp_left >= 0
        prev_right = -1
        for btn in (ov._reject_btn, ov._delete_btn, ov._set_source_btn):
            left = btn.mapTo(ov._content, btn.rect().topLeft()).x()
            assert left >= prev_right
            prev_right = btn.mapTo(ov._content, btn.rect().bottomRight()).x()

    _assert_bar()
    _grow(qtbot, ov)
    _assert_bar()
    ov.hide()


def test_reposition_hooks_rerun_on_resize_no_new_close(qtbot, tmp_path, monkeypatch):
    """W-B: inset + nav + grip hooks re-run on resize; overlay stays open."""
    from tabs.image_gallery.ui.quick_look import helpers as _ql_helpers

    src_p = _real_png(tmp_path, "src.png")
    v_p = _real_png(tmp_path, "v.png")
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={"width": 800, "height": 600})
    item = GalleryItem(path=v_p, mtime_ns=2, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)

    calls: list = []
    orig_inset = ov._reposition_source_inset

    def _spy_inset():
        calls.append("inset")
        return orig_inset()

    monkeypatch.setattr(ov, "_reposition_source_inset", _spy_inset)
    orig_grip = _ql_helpers.reposition_grip

    def _spy_grip(overlay):
        calls.append("grip")
        return orig_grip(overlay)

    monkeypatch.setattr(_ql_helpers, "reposition_grip", _spy_grip)
    orig_nav = _ql_helpers.reposition_nav_buttons

    def _spy_nav(overlay):
        calls.append("nav")
        return orig_nav(overlay)

    monkeypatch.setattr(_ql_helpers, "reposition_nav_buttons", _spy_nav)

    _grow(qtbot, ov)
    assert "inset" in calls
    assert "grip" in calls
    # Nav circles re-pin through the inset hook on the same resize.
    assert "nav" in calls
    # No new close paths: a resize never hides the pinned overlay.
    assert ov.isVisible()
    ov.hide()


def test_resize_without_stash_is_noop(qtbot):
    """W-B: fake paths (nothing stashed) resize without crashing or pixmap."""
    ov = _make_overlay(qtbot)
    item = _item("ghost.png", metrics={})
    _show(ov, item, [item])
    assert getattr(ov, "_preview_full", None) is None
    _grow(qtbot, ov)
    assert ov.isVisible()
    ov.hide()


def test_min_only_no_max_regression(qtbot):
    """W-B: W8 min-only stays — minimum 1040×680, no maximum cap."""
    from sli_ui_toolkit.managers import scaled_px

    ov = _make_overlay(qtbot)
    assert ov._content.minimumSize() == QSize(scaled_px(1040), scaled_px(680))
    assert ov._content.maximumSize() == QSize(16777215, 16777215)
    assert ov.sizeHint() == QSize(scaled_px(1040), scaled_px(680))
    ov.hide()


def test_metric_row_gaps_grow_uniformly_on_vertical_stretch(qtbot, tmp_path):
    """Metric rows spread with uniform gaps when the card grows taller.

    The metrics block takes the column's extra height (stretch 1 in the
    AlignTop right column) and equal inter-row spacers split it evenly:
    every gap grows, all gaps stay equal. Short window → 4px floor.
    """
    from sli_ui_toolkit.managers import scaled_px

    src_p = _real_png(tmp_path, "src.png")
    v_p = _real_png(tmp_path, "v.png")
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={})
    item = GalleryItem(
        path=v_p, mtime_ns=2,
        metrics={"ssim": 0.93, "hf_ratio": -0.07, "delta_e": 8.3},
    )
    ov = _make_overlay(qtbot)
    _show(ov, item, [[src], [item]], source=src.path)

    def _gaps():
        # every gap in the report section in visual order: metric rows,
        # then artifact rows (flat right_lay children with uniform spacers).
        # Rows live in the shared report host, so map to its coordinates.
        from PySide6.QtCore import QPoint

        host = ov._report_host
        spans = []
        for row in list(ov._metric_rows) + list(ov._artifact_rows):
            top = row.mapTo(host, QPoint(0, 0)).y()
            spans.append((top, top + row.height()))
        assert len(spans) >= 4, f"expected >=4 report rows, got {len(spans)}"
        return [spans[i + 1][0] - spans[i][1] for i in range(len(spans) - 1)]

    gaps_before = _gaps()
    # Already uniform at the default card size (proportional stretches:
    # each gap in the section gets exactly one share of extra height).
    assert max(gaps_before) - min(gaps_before) <= 8

    content = ov._content
    content.resize(content.width(), content.height() + scaled_px(400))
    QApplication.processEvents()
    QApplication.processEvents()

    scroll = ov.findChild(QScrollArea, "quicklook_right_scroll")
    assert scroll.verticalScrollBar().maximum() == 0
    gaps_after = _gaps()
    # Every gap grew (inner and boundary seams alike)...
    for before, after in zip(gaps_before, gaps_after):
        assert after > before
    # ...and uniformly.
    assert max(gaps_after) - min(gaps_after) <= 8
    ov.hide()


def test_metric_block_outer_gaps_match_inter_row_gaps(qtbot, tmp_path):
    """The metric block breathes from the meta row above and the analysis
    divider below exactly like rows do between themselves.

    Falsification story: before the leading/trailing spacers, the top seam
    was a fixed ~6px ``meta_gap`` widget (+ layout spacing) and the bottom
    seam was only the 3px layout spacing — both far below the inter-row
    stretch gaps, so the first/last metric hugged the meta row / divider.
    """
    from PySide6.QtCore import QPoint

    src_p = _real_png(tmp_path, "src.png")
    v_p = _real_png(tmp_path, "v.png")
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={})
    item = GalleryItem(
        path=v_p, mtime_ns=2,
        metrics={"ssim": 0.93, "hf_ratio": -0.07, "delta_e": 8.3},
    )
    ov = _make_overlay(qtbot)
    _show(ov, item, [[src], [item]], source=src.path)

    host = ov._report_host
    rows = list(ov._metric_rows) + list(ov._artifact_rows)
    assert len(rows) >= 4

    def _top(w):
        return w.mapTo(host, QPoint(0, 0)).y()

    meta_bottom = _top(ov._meta_label) + ov._meta_label.height()
    spans = [(r, _top(r), _top(r) + r.height()) for r in rows]
    first_top = spans[0][1]
    last_bottom = spans[-1][2]
    div_top = _top(ov._div_analysis)
    inter = [spans[i + 1][1] - spans[i][2] for i in range(len(spans) - 1)]
    gap_top = first_top - meta_bottom
    gap_bottom = div_top - last_bottom

    # All seams — top, inter-row, bottom — share one uniform gap.
    assert max(inter + [gap_top, gap_bottom]) - min(inter + [gap_top, gap_bottom]) <= 8
    # And it is the stretch gap, not the old cramped fixed seam.
    assert gap_top > 12 and gap_bottom > 12
    ov.hide()


def test_grow_shrink_roundtrip_restores_proportions(qtbot, tmp_path):
    """Sticky-width regression: grow->shrink must settle back (no ratchet).

    Root causes fixed: bar fill segments baked grown widths into the layout
    minimum via setFixedWidth (now paint-only via _set_painted_width), and the
    preview label floor (320px) let the 1:1 stretch split strand ~496px on the
    scroll (now 640px mockup floor).
    """
    from sli_ui_toolkit.managers import scaled_px

    src = _item("src.png")
    item = _item(
        "view.png",
        metrics={"ssim": 0.93, "hf_ratio": 0.08, "delta_e": 8.3, "upscale_factor": 5},
        artifacts={"banding": "mild", "halo": "flagged"},
    )
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)
    content = ov._content
    scroll = ov.findChild(QScrollArea, "quicklook_right_scroll")
    _grow(qtbot, ov, dw=400, dh=200)
    assert content.width() == scaled_px(1040) + scaled_px(400)
    # Settled height fits three artifact rows (was two at 620px).
    content.resize(scaled_px(1040), scaled_px(700))
    QApplication.processEvents()
    QApplication.processEvents()
    QApplication.processEvents()
    assert content.width() == scaled_px(1040)
    assert ov._preview_host.width() >= scaled_px(640)
    assert scroll.width() < scaled_px(500)
    assert scroll.viewport().width() >= scaled_px(296)
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    assert sa_min_hint(scroll) <= scaled_px(296)
    ov.hide()


def sa_min_hint(scroll):
    return scroll.widget().minimumSizeHint().width()


# -- D1-D4 drag/cursor lifecycle guards (recon ql-resize-recon-01) --------------


def _synth_move(pos, buttons):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(float(pos.x()), float(pos.y())),
        Qt.MouseButton.NoButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def _synth_press(pos):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(float(pos.x()), float(pos.y())),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _synth_release(pos):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(float(pos.x()), float(pos.y())),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_interior_hover_clears_stale_plate_cursor(qtbot):
    """D1: a stale plate resize cursor must not leak over card content."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QCursor

    from tabs.image_gallery.ui.quick_look.resize import handle_ring_hover

    a = _item("a.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a])
    card = ov._content.geometry()
    # Simulate the leak: strip hover left SizeHor on the plate.
    ov._content.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
    assert ov._content.cursor().shape() == Qt.CursorShape.SizeHorCursor
    # Hover deep interior (moves over ignoring children propagate here).
    center = QPoint(card.x() + card.width() // 2, card.y() + card.height() // 2)
    assert handle_ring_hover(ov, _synth_move(center, Qt.MouseButton.NoButton)) is False
    assert ov._content.cursor().shape() == Qt.CursorShape.ArrowCursor
    ov.hide()


def test_button_free_move_cancels_live_drag(qtbot):
    """D2: a move with no buttons held ends a stranded drag (no grabMouse)."""
    from PySide6.QtCore import QPoint, Qt

    from tabs.image_gallery.ui.quick_look.resize import handle_border_move

    a = _item("a.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a])
    w0 = ov._content.width()
    ov._border_drag = ("left", QPoint(0, 0), ov._content.geometry())
    center = ov._content.geometry().center()
    assert handle_border_move(ov, _synth_move(center, Qt.MouseButton.NoButton)) is False
    assert ov._border_drag is None
    assert ov._content.width() == w0
    ov.hide()


def test_release_clears_both_cursor_slots(qtbot):
    """D3: releasing an outer-ring drag over the card clears plate+overlay."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QCursor

    from tabs.image_gallery.ui.quick_look.resize import handle_border_release

    a = _item("a.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a])
    ov.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
    ov._content.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
    ov._border_drag = ("bottom", ov._content.geometry().center(), ov._content.geometry())
    center = ov._content.geometry().center()
    assert handle_border_release(ov, _synth_release(center)) is True
    assert ov._border_drag is None
    assert ov.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert ov._content.cursor().shape() == Qt.CursorShape.ArrowCursor
    ov.hide()


def test_second_press_keeps_first_drag(qtbot):
    """D4: a second press during a live drag must not silently re-anchor."""
    from PySide6.QtCore import QPoint, Qt

    from tabs.image_gallery.ui.quick_look.resize import handle_border_press

    a = _item("a.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a])
    first = ("left", QPoint(10, 10), ov._content.geometry())
    ov._border_drag = first
    # Bottom-edge middle: inside the strip, far from nav circles (mid-height)
    # and the grip (corner) so the press reaches the zone path, not WALK.
    content = ov._content
    pt = QPoint(content.width() // 2, content.height() - 4)
    assert handle_border_press(ov, _synth_press(pt)) is True
    assert ov._border_drag == first
    ov._border_drag = None
    ov.hide()


def test_fast_jump_to_child_clears_plate_cursor(qtbot):
    """D5: resizable card — border hovers show the resize cursor.

    Resize affordance live (QL_RESIZABLE): hovering the edge strip shows
    SizeHor, and a stale plate cursor still clears on the next landing
    move over content children.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QApplication

    from sli_ui_toolkit.widgets import Button

    mates = [_item(f"up{i}.png", rank=i) for i in (1, 2, 3, 4, 5, 6)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    content = ov._content
    # Edge strip hover: resize cursor (affordance live).
    qtbot.mouseMove(content, QPoint(content.width() - 4, 100))
    QApplication.processEvents()
    assert content.cursor().shape() == Qt.CursorShape.SizeHorCursor
    # Stale-cursor clearing still works: a stranded SizeHor drops back
    # to the arrow on landing moves.
    content.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
    thumbs = [
        b for b in ov._strip_host.findChildren(Button)
        if b.objectName().startswith("quicklook_strip_")
    ]
    assert thumbs
    qtbot.mouseMove(thumbs[0], thumbs[0].rect().center())
    QApplication.processEvents()
    QApplication.processEvents()
    assert content.cursor().shape() == Qt.CursorShape.ArrowCursor
    ov.hide()


def test_ring_drag_resizes_card(qtbot):
    """W10 ring drag (QL_RESIZABLE): press outside-right + move grows the card."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from tabs.image_gallery.ui.quick_look.resize import ring_zone_at

    a = _item("a.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a])
    c0 = ov._content.geometry()
    # Bottom-right ring corner (clear of the mid-edge nav arrows).
    pt = QPoint(c0.x() + c0.width() - 1, c0.y() + c0.height() + 4)
    assert ring_zone_at(ov, pt) == "bottom_right"
    w0, h0 = ov._content.width(), ov._content.height()
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    QApplication.processEvents()
    assert ov._border_drag is not None
    QTest.mouseMove(ov, QPoint(pt.x() + 60, pt.y() + 40))
    QApplication.processEvents()
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                        QPoint(pt.x() + 60, pt.y() + 40))
    QApplication.processEvents()
    assert ov._border_drag is None
    assert ov._content.width() > w0 and ov._content.height() > h0
    assert ov.isVisible()  # a resize drag never dismisses the overlay
    ov.hide()


def test_strip_uses_overlay_area_with_autohiding_h_bar(qtbot):
    """Strip scrolls via toolkit OverlayScrollArea (thin bar, auto-hide).

    The strip rides the full-width bottom row (not the 296px sidebar), so
    overflow needs a long filmstrip: 16 thumbs (~1206px) exceed the row
    while 6 would fit without scrolling.
    """
    from PySide6.QtWidgets import QApplication

    from sli_ui_toolkit.widgets import MinimalistScrollBar, OverlayScrollArea

    mates = [_item(f"up{i}.png", rank=i) for i in range(1, 17)]
    ov = _make_overlay(qtbot)
    _show(ov, mates[0], mates)
    QApplication.processEvents()
    QApplication.processEvents()
    scroll = ov._strip_scroll
    assert isinstance(scroll, OverlayScrollArea)
    assert scroll.widgetResizable() is False
    hbar = scroll.custom_h_scrollbar
    assert isinstance(hbar, MinimalistScrollBar)
    assert hbar.maximum() > hbar.minimum()  # overflow: 16 thumbs
    assert hbar.isVisible()
    # Column containment holds (the original 446-vs-329 overflow fix).
    assert ov._report_host.minimumSizeHint().width() <= scroll.viewport().width()
    # Idle auto-hide + scroll re-show.
    hbar.set_auto_hide(0.15)
    qtbot.waitUntil(lambda: not hbar.isVisible(), timeout=2000)
    scroll.horizontalScrollBar().setValue(50)
    assert hbar.isVisible()
    ov.hide()
