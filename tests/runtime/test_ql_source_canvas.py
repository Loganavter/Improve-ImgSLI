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

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPixmap, QWheelEvent
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
