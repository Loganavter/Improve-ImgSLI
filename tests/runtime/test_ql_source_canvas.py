"""Quick Look SOURCE inset is the ENGINE canvas, view-synced to the preview.

The source inset used to be a toolkit ``Button`` whose ``thumb`` region held a
cover-scaled ``QPixmap``. It is now the same ``QuickLookCanvasWidget`` the
main preview uses (a real ``QRhiWidget`` engine canvas) fed by the SOURCE
item's bounded coarse store, bound to the preview canvas's ``ViewportState``
so both surfaces share ONE zoom/pan (a wheel on the preview moves the inset
too). The pixmap button stays only as the rounded plate / pre-first-frame
cover, which is why the plate contract below is unchanged.

Falsification story (pre-change tree, recorded RED in DONE.md):
- ``test_inset_is_the_engine_canvas_attached_after_show`` — on the pre-change
  tree ``_source_inset_host`` contains no ``QuickLookCanvasWidget`` (the inset
  is a pixmap label), so the ``isinstance`` + attachment assertions fail.
- ``test_inset_view_tracks_the_preview_zoom_and_pan`` — there is no second
  canvas, so ``current_view`` and the frame comparison cannot even be built
  (``_raster_frame`` is absent / the widget is not an engine canvas).
- ``test_inset_renders_the_current_source_after_a_step`` — the pixmap button
  has no store and no frame raster; the CURRENT-source payload assertion and
  the late/stale token guard fail.
- ``test_inset_keeps_the_pinned_plate_and_rounded_clip`` — the frame/cover
  surface widgets and the shared radius constants do not exist.

No GPU is needed: the engine canvas exposes the same ``_raster_frame`` seam
the main preview tests use (``test_ql_demand_pyramid``); readback is pure
``QImage`` bytes. The QRhiWidget itself is only instantiated/attached — it
never renders offscreen.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QImage,
    QMouseEvent,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from tabs.image_gallery.ui.quick_look import preview_canvas as pc
from tabs.image_gallery.ui.quick_look import preview_zoom

# The inset surface is 150x84 inside a 4px plate pad (build_overlay_ui).
_W, _H = 150, 84


def _png(tmp_path: Path, name: str, color: str, w: int = 800, h: int = 600) -> Path:
    pm = QPixmap(w, h)
    pm.fill(QColor(color))
    p = tmp_path / name
    assert pm.save(str(p), "PNG")
    return p


def _item(path: Path) -> GalleryItem:
    return GalleryItem(path=path, mtime_ns=1, metrics={})


def _make_overlay(qtbot) -> QuickLookOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent  # strong ref: keeps the C++ subtree alive
    return ov


def _show(overlay: QuickLookOverlay, item, series, source) -> None:
    owner = SimpleNamespace(
        _judgment_domain="algorithms",
        state=SimpleNamespace(
            mode=Mode.FIDELITY,
            source_path=source,
            series=[[m for m in series]],
            items=list(series),
            judgment_domain="algorithms",
        ),
    )
    overlay.show_for(item, owner)
    parent = getattr(overlay, "_parity_test_parent", None) or overlay.parentWidget()
    if parent is not None:
        parent.resize(1280, 800)
        parent.show()
    QApplication.processEvents()


def _target(w: int = _W, h: int = _H):
    return SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: w, height=lambda: h)
    )


def _frame_bytes(canvas, w: int = _W, h: int = _H):
    frame = canvas._raster_frame(_target(w, h))
    assert frame is not None, "engine canvas produced no frame"
    fw, fh, pixels = frame
    assert (fw, fh) == (w, h)
    return pixels


def _center_rgb(canvas, w: int = _W, h: int = _H) -> tuple[int, int, int]:
    fw, fh, pixels = canvas._raster_frame(_target(w, h))
    img = QImage(pixels, fw, fh, QImage.Format.Format_RGBA8888_Premultiplied).copy()
    col = img.pixelColor(fw // 2, fh // 2)
    return (col.red(), col.green(), col.blue())


def _is_red(rgb) -> bool:
    r, g, b = rgb
    return r > 120 and g < 90 and b < 90


def _is_green(rgb) -> bool:
    r, g, b = rgb
    return g > 110 and r < 100 and b < 100


def _is_blue(rgb) -> bool:
    r, g, b = rgb
    return b > 120 and r < 100 and g < 140


def _store_image(store) -> QImage:
    """Level-0 pixels of an open coarse store (what the canvas samples)."""
    from engine.store.pixel_source_adapters import pixel_source_size
    from engine.store.pyramid_pixel_store import PyramidPixelStore

    w, h = pixel_source_size(store)
    pyr = PyramidPixelStore(store)
    try:
        img = pyr.best_pixels((0, 0, int(w), int(h)), 1.0)
    finally:
        pyr.close()
    assert img is not None and not img.isNull()
    return img


# -- 1. the inset IS the engine canvas, attached after the overlay shows ------


def test_inset_is_the_engine_canvas_attached_after_show(qtbot, tmp_path):
    """The source inset image surface is a QuickLookCanvasWidget (not a label)."""
    src = _item(_png(tmp_path, "src.png", "#c0392b"))
    item = _item(_png(tmp_path, "view.png", "#3a6ea5"))
    ov = _make_overlay(qtbot)
    try:
        _show(ov, item, [src, item], src.path)
        inset = getattr(ov, "_source_inset_canvas", None)
        assert inset is not None, "no engine canvas was attached to the source inset"
        assert isinstance(inset, pc.QuickLookCanvasWidget), (
            f"inset is {type(inset).__name__}, not the engine canvas"
        )
        # Same implementation the main preview uses.
        main = getattr(ov, "_preview_canvas", None)
        assert main is not None
        assert type(inset) is type(main)
        # Attached: inside the inset plate, visible with the overlay, after show.
        assert ov._source_inset_pix.isAncestorOf(inset), (
            "inset canvas must live on the source plate"
        )
        assert inset.isVisibleTo(ov), "inset canvas is not attached/shown"
        # The old pixmap-only surface is no longer the image: the canvas owns it.
        assert inset.width() > 0 and inset.height() > 0
    finally:
        ov.hide()


# -- 2. one viewport, two views ----------------------------------------------


def test_inset_view_tracks_the_preview_zoom_and_pan(qtbot, tmp_path):
    """A wheel on the preview moves the inset's viewport identically."""
    src = _item(_png(tmp_path, "src2.png", "#c0392b"))
    item = _item(_png(tmp_path, "view2.png", "#3a6ea5"))
    ov = _make_overlay(qtbot)
    try:
        _show(ov, item, [src, item], src.path)
        main = ov._preview_canvas
        inset = ov._source_inset_canvas
        assert inset.current_view() == main.current_view() == (1.0, 0.0, 0.0)

        # Real interaction path: one wheel notch on the main preview.
        ev = QWheelEvent(
            QPointF(70.0, 42.0),
            QPointF(70.0, 42.0),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        main.wheelEvent(ev)
        zoom, pan_x, pan_y = main.current_view()
        assert zoom > 1.0 and (pan_x, pan_y) != (0.0, 0.0)
        assert inset.current_view() == (zoom, pan_x, pan_y), (
            "the inset must read the SAME viewport as the preview"
        )

        # ...and the inset's transform really is the shared one: its frame is
        # bit-identical to the shared fit/crop math on its own framebuffer.
        want = preview_zoom.zoomed_frame(
            _store_image(inset._store), _W, _H, zoom, pan_x, pan_y
        )
        assert want is not None
        assert _frame_bytes(inset) == want[2], (
            "inset frame does not use the main preview's viewport transform"
        )
        fit = preview_zoom.zoomed_frame(_store_image(inset._store), _W, _H, 1.0)
        assert _frame_bytes(inset) != fit[2], "inset still shows the 1.0 fit frame"

        # One state, both directions: a programmatic view change from the
        # inset side is the same state the preview reads.
        inset.set_view(3.0, -0.1, 0.25)
        assert main.current_view() == (3.0, -0.1, 0.25)
        assert inset.current_view() == main.current_view()
    finally:
        ov.hide()


# -- 3. content identity + stale guard ---------------------------------------


def test_inset_renders_the_current_source_after_a_step(qtbot, tmp_path):
    """Two pairs stepped: the inset shows the CURRENT source, never the old."""
    red = _png(tmp_path, "a_src.png", "#c0392b")
    red_view = _png(tmp_path, "a_view.png", "#3a6ea5")
    green = _png(tmp_path, "b_src.png", "#27ae60")
    green_view = _png(tmp_path, "b_view.png", "#f1c40f")

    ov = _make_overlay(qtbot)
    try:
        a_src, a_view = _item(red), _item(red_view)
        _show(ov, a_view, [a_src, a_view], a_src.path)
        inset = ov._source_inset_canvas
        store_a = inset._store
        assert store_a is not None
        assert _is_red(_center_rgb(inset)), "pair A: inset must show pair A's source"

        # Step to pair B: a full context switch (new source side, new owner
        # state) — the production "open another pair" path.
        token_a = ov._source_inset_token
        b_src, b_view = _item(green), _item(green_view)
        _show(ov, b_view, [b_src, b_view], green)
        QApplication.processEvents()

        inset = ov._source_inset_canvas
        store_b = inset._store
        assert store_b is not None and store_b is not store_a
        assert _is_green(_center_rgb(inset)), (
            "pair B: the inset still renders a neighbour/previous source"
        )
        assert not _is_red(_center_rgb(inset))

        # Late/stale apply: an old resolve (pair A) landing after pair B was
        # populated must be rejected, never replace the newer content.
        from tabs.image_gallery.ui.quick_look import source_canvas

        ok = source_canvas.apply_source_inset_source(
            ov, str(red), store_a, token=token_a
        )
        assert ok is False, "a stale inset source was accepted"
        assert inset._store is store_b
        assert _is_green(_center_rgb(inset)), "stale frame replaced the newer one"
    finally:
        ov.hide()


# -- 4. the pinned plate / rounded clip contract -----------------------------


def test_inset_keeps_the_pinned_plate_and_rounded_clip(qtbot, tmp_path):
    """Pinning, plate size and the rounding invariants survive the canvas."""
    from sli_ui_toolkit.managers import scaled_px

    from tabs.image_gallery.ui.quick_look import source_canvas

    src = _item(_png(tmp_path, "src4.png", "#c0392b"))
    item = _item(_png(tmp_path, "view4.png", "#3a6ea5"))
    ov = _make_overlay(qtbot)
    try:
        _show(ov, item, [src, item], src.path)
        host = ov._source_inset_host
        plate = ov._source_inset_pix
        inset = ov._source_inset_canvas

        # Pinned bottom-left inside the preview host (unchanged pinning).
        margin = scaled_px(12)
        assert host.parentWidget() is ov._preview_host
        assert host.x() == margin
        assert host.y() + host.height() == ov._preview_host.height() - margin

        # The canvas fills the plate's inner thumb rect (the 4px pad).
        pad = source_canvas.SOURCE_INSET_PAD
        outer = plate.rect().adjusted(pad, pad, -pad, -pad)
        assert inset.geometry() == outer, (
            f"inset canvas {inset.geometry()} != plate thumb rect {outer}"
        )

        # Rectangle + rounding invariants: the plate keeps its rounded regions
        # (outer bg 8, image 5) and the shared constants agree.
        regions = {r.id: r for r in plate.regions()}
        assert set(regions) == {"bg", "thumb"}
        assert regions["bg"].corner_radii == (source_canvas.SOURCE_INSET_FRAME_RADIUS,) * 4
        assert regions["thumb"].corner_radii == (source_canvas.SOURCE_INSET_THUMB_RADIUS,) * 4
        assert all(r.bg_locked for r in regions.values())

        # Rounded clip surface above the canvas: same thumb rect, radius 5,
        # and inert for the mouse (navigation/region-select routing unchanged).
        frame = ov._source_inset_frame
        assert frame.geometry() == outer
        assert frame.radius_px() == source_canvas.SOURCE_INSET_THUMB_RADIUS
        assert frame.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert frame.focusPolicy() == Qt.FocusPolicy.NoFocus

        # No new focus stop from the canvas itself.
        assert inset.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert plate.focusPolicy() == Qt.FocusPolicy.NoFocus
    finally:
        ov.hide()


# -- 5. hover / press on the plate swaps the MAIN preview to the SOURCE ------
#
# The inset shows the source on its own surface; the interaction shows the
# SAME source in the MAIN preview (the source is what a fidelity check has to
# look at closely) without touching the shared ``ViewportState``. The plate is
# the only non-transparent child of the inset block, so it is the hit target —
# the engine canvas/cover/frame stay ``WA_TransparentForMouseEvents`` and
# outside the section graph (docs/dev/KEYBOARD_NAVIGATION.md §9).


def _send_enter(widget) -> None:
    pos = QPointF(5.0, 5.0)
    ev = QEnterEvent(pos, pos, QPointF(widget.mapToGlobal(pos.toPoint())))
    QApplication.sendEvent(widget, ev)


def _send_leave(widget) -> None:
    QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))


def _send_lmb(widget, press: bool) -> None:
    pos = QPointF(widget.width() / 2.0, widget.height() / 2.0)
    kind = (
        QEvent.Type.MouseButtonPress if press else QEvent.Type.MouseButtonRelease
    )
    buttons = Qt.MouseButton.LeftButton if press else Qt.MouseButton.NoButton
    ev = QMouseEvent(
        kind,
        pos,
        QPointF(widget.mapToGlobal(pos.toPoint())),
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, ev)


def _main_rgb(main) -> tuple[int, int, int]:
    return _center_rgb(main, 160, 120)


def test_hover_on_the_inset_plate_shows_the_source_in_the_main_preview(
    qtbot, tmp_path
):
    """Enter → main preview shows the SOURCE at the SAME view; Leave → restore."""
    src = _item(_png(tmp_path, "sw_src.png", "#c0392b"))
    item = _item(_png(tmp_path, "sw_view.png", "#3a6ea5"))
    ov = _make_overlay(qtbot)
    try:
        _show(ov, item, [src, item], src.path)
        main = ov._preview_canvas
        plate = ov._source_inset_pix
        inset = ov._source_inset_canvas
        view = main.current_view()

        assert main._ql_source_path == str(item.path)
        assert _is_blue(_main_rgb(main)), "baseline: preview shows the viewed item"

        _send_enter(plate)
        assert main._ql_source_path == str(src.path), (
            "hover did not swap the main preview to the source"
        )
        assert _is_red(_main_rgb(main)), "main preview pixels are not the source"
        # SAME viewport state: the swap changes pixels, never zoom/pan, and the
        # main preview borrows the inset's already-open coarse store.
        assert main.current_view() == view
        assert inset.current_view() == view
        assert main._store is ov._source_inset_store

        # Zooming while swapped still drives the ONE shared viewport.
        ev = QWheelEvent(
            QPointF(70.0, 42.0),
            QPointF(70.0, 42.0),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        main.wheelEvent(ev)
        zoomed = main.current_view()
        assert zoomed[0] > view[0], "wheel while swapped did not zoom"
        assert inset.current_view() == zoomed, "shared viewport broke during the swap"
        assert main._ql_source_path == str(src.path), "zoom ended the swap"

        _send_leave(plate)
        assert main._ql_source_path == str(item.path), "leave did not restore"
        assert _is_blue(_main_rgb(main)), "restored preview is not the viewed item"
        assert main.current_view() == zoomed, "restore changed the viewport"
    finally:
        ov.hide()


def test_inset_lmb_swap_lasts_until_release_even_after_leaving(qtbot, tmp_path):
    """LMB press swaps; the swap survives Leave and ends on release."""
    red = _item(_png(tmp_path, "pr_src.png", "#c0392b"))
    item = _item(_png(tmp_path, "pr_view.png", "#3a6ea5"))
    ov = _make_overlay(qtbot)
    try:
        _show(ov, item, [red, item], red.path)
        main = ov._preview_canvas
        plate = ov._source_inset_pix
        assert main._ql_source_path == str(item.path)

        _send_lmb(plate, press=True)
        assert main._ql_source_path == str(red.path), "LMB press did not swap"
        assert _is_red(_main_rgb(main))

        # The pointer leaves the plate while the button is still down: the
        # press-owned swap must hold (temporary until release).
        _send_leave(plate)
        assert main._ql_source_path == str(red.path), (
            "a press-pending swap was ended by Leave"
        )
        assert _is_red(_main_rgb(main))

        _send_lmb(plate, press=False)
        assert main._ql_source_path == str(item.path), "release did not restore"
        assert _is_blue(_main_rgb(main))
    finally:
        ov.hide()


def test_hover_on_another_inset_region_does_nothing(qtbot, tmp_path):
    """Only the plate is a swap target: the caption/title region is inert."""
    src = _item(_png(tmp_path, "ot_src.png", "#c0392b"))
    item = _item(_png(tmp_path, "ot_view.png", "#3a6ea5"))
    ov = _make_overlay(qtbot)
    try:
        _show(ov, item, [src, item], src.path)
        main = ov._preview_canvas
        for other in (ov._source_inset_title, ov._source_inset_host):
            _send_enter(other)
            assert main._ql_source_path == str(item.path), (
                f"hover over {type(other).__name__} swapped the preview"
            )
            assert _is_blue(_main_rgb(main))
            _send_leave(other)
            assert main._ql_source_path == str(item.path)
    finally:
        ov.hide()


def test_hiding_while_swapped_clears_the_swap(qtbot, tmp_path):
    """Close/reopen never inherits a hover swap (the source stays retired)."""
    src = _item(_png(tmp_path, "hd_src.png", "#c0392b"))
    item = _item(_png(tmp_path, "hd_view.png", "#3a6ea5"))
    other = _item(_png(tmp_path, "hd_other.png", "#27ae60"))
    ov = _make_overlay(qtbot)
    try:
        _show(ov, item, [src, item], src.path)
        main = ov._preview_canvas
        _send_enter(ov._source_inset_pix)
        assert _is_red(_main_rgb(main))

        ov.hide()
        QApplication.processEvents()
        assert not getattr(ov, "_source_swap_active", False), (
            "closing the overlay kept the swap armed"
        )

        _show(ov, other, [src, other], src.path)
        assert main._ql_source_path == str(other.path)
        assert _is_green(_main_rgb(main)), "reopen shows a stale/pre-swap item"
    finally:
        ov.hide()
