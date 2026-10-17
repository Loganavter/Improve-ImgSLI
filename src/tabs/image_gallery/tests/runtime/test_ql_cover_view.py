"""Quick Look — the pre-first-frame cover plate follows the canvas view.

User report (live): *"zoom preservation is crooked — in one or several
intermediate frames the zoom resets, and only after that is it restored."*

Root cause (verified, not a guess): on a within-series walk the Quick Look
canvas is hidden and the host shows the cover plate until the new frame
settles (``release_preview_canvas_for_walk`` hides it; the plate is built by
``_cover_pixmap_from_full``). The canvas view itself IS preserved
(``preserve_view=True``), but the plate was built with a hardcoded zoom of
1.0 — so the plate shows the fit frame while the canvas that arrives a moment
later shows the preserved zoom: one or more fit frames, then the zoom
reappears. Before the zoom-persist feature this was invisible by construction
(the view was 1.0 after every walk, so plate 1.0 == canvas 1.0).

Falsification story (pre-fix):
- ``test_plate_follows_canvas_view`` is the discriminator. Against the
  unfixed ``cover.py`` the plate equals the 1.0 fit frame and the test FAILS
  on the pixel comparison (recorded in DONE.md). With the fix the plate
  equals ``preview_zoom.zoomed_frame(src.toImage(), w, h, 2.5, 0.3, -0.2)``.
- ``test_plate_defaults_without_canvas`` /
  ``test_plate_defaults_without_current_view`` pin backward compatibility
  (a 1.0 plate when no view is known) so the new accessor can never turn
  into a hard requirement for the host.
- ``test_cover_until_first_frame_plate_is_the_zoomed_one`` pins that the
  re-cover / reveal path shows the plate ``_fit_cover`` built (it does not
  rebuild a 1.0 plate over it).

No GPU, no real window: pure ``QPixmap`` / ``QLabel``/``SimpleNamespace``
doubles.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from tabs.image_gallery.ui.quick_look import preview_canvas as _pc
from tabs.image_gallery.ui.quick_look import preview_canvas_host as host
from tabs.image_gallery.ui.quick_look.preview_canvas_host import cover as _cover_mod
from tabs.image_gallery.ui.quick_look.preview_zoom import zoomed_frame

# Slot 4:3 vs source 2:1 → the 1.0 plate is letterboxed while a zoomed plate
# crops, so the two can never coincide byte-for-byte (the source is
# non-uniform too, so pan alone already changes the pixels).
_W, _H = 160, 120
_SRC_W, _SRC_H = 200, 100
# The view a within-series walk preserves: (zoom, pan_x, pan_y).
_VIEW = (2.5, 0.3, -0.2)


def _source_pixmap(w: int = _SRC_W, h: int = _SRC_H) -> QPixmap:
    """Non-uniform source (four quadrants) so zoom/pan change the pixels."""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    painter = QPainter(img)
    try:
        painter.fillRect(0, 0, w // 2, h // 2, QColor("#c0392b"))
        painter.fillRect(w // 2, 0, w - w // 2, h // 2, QColor("#27ae60"))
        painter.fillRect(0, h // 2, w // 2, h - h // 2, QColor("#2980b9"))
        painter.fillRect(w // 2, h // 2, w - w // 2, h - h // 2, QColor("#f1c40f"))
    finally:
        painter.end()
    return QPixmap.fromImage(img)


def _frame_image(
    pixmap: QPixmap, w: int, h: int, zoom: float, pan_x: float = 0.0, pan_y: float = 0.0
) -> QImage:
    """The exact frame the live canvas draws for this view (shared fit math)."""
    frame = zoomed_frame(pixmap.toImage(), w, h, zoom, pan_x, pan_y)
    assert frame is not None, "zoomed_frame returned None"
    fw, fh, px = frame
    return QImage(px, fw, fh, QImage.Format.Format_RGBA8888_Premultiplied).copy()


def _canon(img: QImage) -> QImage:
    """Canonical format so a QPixmap (ARGB32) compares with a frame (RGBA8888)."""
    return img.convertToFormat(QImage.Format.Format_RGBA8888)


def _pixels(img: QImage) -> bytes:
    return bytes(img.constBits())


def _view_double(view=_VIEW):
    """A canvas double exposing only the declared accessor."""
    return SimpleNamespace(current_view=lambda _v=view: _v)


def _plate(overlay) -> QImage:
    cover = overlay._preview_cover
    assert cover is not None, "no cover plate was built"
    shown = cover.pixmap()
    assert shown is not None and not shown.isNull(), "plate pixmap missing"
    return shown.toImage()


def _overlay_for(qtbot, *, canvas, src=None):
    host_w = QWidget()
    qtbot.addWidget(host_w)
    host_w.resize(_W, _H)
    cover = QLabel(host_w)
    qtbot.addWidget(cover)
    return SimpleNamespace(
        _preview_host=host_w,
        _preview_cover=cover,
        _preview_full=src if src is not None else _source_pixmap(),
        _preview_canvas=canvas,
    )


# -- the fix: the plate rides the canvas view ---------------------------------


def test_plate_follows_canvas_view(qtbot):
    """The plate is the view frame, not the fit frame (the flicker)."""
    ov = _overlay_for(qtbot, canvas=_view_double())
    host._fit_cover(ov)

    face = _canon(_plate(ov))
    want = _canon(_frame_image(ov._preview_full, _W, _H, *_VIEW))
    assert (face.width(), face.height()) == (want.width(), want.height()) == (_W, _H)
    assert _pixels(face) == _pixels(want), "the plate must equal the preserved-view frame"
    # And it is NOT the fit frame the unfixed plate showed.
    fit = _canon(_frame_image(ov._preview_full, _W, _H, 1.0))
    assert _pixels(face) != _pixels(fit), "the plate must not be the 1.0 fit frame"


def test_plate_rebuilds_when_the_view_changes(qtbot):
    """A later view change re-fits the plate (the ``_ql_fit_for`` cache is size-only)."""
    ov = _overlay_for(qtbot, canvas=_view_double())
    host._fit_cover(ov)
    # Same slot size, new view: the cache key does not change, so only an
    # explicit drop (production: the walk drops the cover) re-fits. Assert the
    # production sequence: drop + rebuild yields the new view frame.
    host._drop_cover(ov, "release-walk")
    ov._preview_cover = QLabel(ov._preview_host)
    ov._preview_canvas = _view_double((4.0, -0.1, 0.25))
    host._fit_cover(ov)
    want = _canon(_frame_image(ov._preview_full, _W, _H, 4.0, -0.1, 0.25))
    assert _pixels(_canon(_plate(ov))) == _pixels(want)


# -- backward compatibility ---------------------------------------------------


def test_plate_defaults_without_canvas(qtbot):
    """No canvas (a cold open) → the historical 1.0 fit plate."""
    host_w = QWidget()
    qtbot.addWidget(host_w)
    host_w.resize(_W, _H)
    cover = QLabel(host_w)
    qtbot.addWidget(cover)
    ov = SimpleNamespace(
        _preview_host=host_w,
        _preview_cover=cover,
        _preview_full=_source_pixmap(),
    )
    host._fit_cover(ov)
    want = _canon(_frame_image(ov._preview_full, _W, _H, 1.0))
    assert _pixels(_canon(_plate(ov))) == _pixels(want)


def test_plate_defaults_without_current_view(qtbot):
    """A foreign/old canvas double without the accessor → the 1.0 fit plate."""
    ov = _overlay_for(qtbot, canvas=SimpleNamespace())
    host._fit_cover(ov)
    want = _canon(_frame_image(ov._preview_full, _W, _H, 1.0))
    assert _pixels(_canon(_plate(ov))) == _pixels(want)


def test_plate_defaults_when_accessor_raises(qtbot):
    """A raising accessor fails open to the 1.0 fit plate (never propagates)."""

    def _boom():
        raise RuntimeError("degenerate canvas")

    ov = _overlay_for(qtbot, canvas=SimpleNamespace(current_view=_boom))
    host._fit_cover(ov)
    want = _canon(_frame_image(ov._preview_full, _W, _H, 1.0))
    assert _pixels(_canon(_plate(ov))) == _pixels(want)


# -- the shown plate is the one we built --------------------------------------


def test_cover_until_first_frame_plate_is_the_zoomed_one(qtbot):
    """The re-cover path (walk -> reveal) shows the preserved-view plate.

    ``_cover_until_first_frame`` builds its label and derives the plate through
    ``_fit_cover`` — it must be the zoomed plate, and the reveal that follows
    must not repaint it back to the fit frame.
    """
    ov = _overlay_for(qtbot, canvas=_view_double())
    canvas = SimpleNamespace()
    host._cover_until_first_frame(ov, canvas)

    want = _canon(_frame_image(ov._preview_full, _W, _H, *_VIEW))
    assert _pixels(_canon(_plate(ov))) == _pixels(want)
    assert ov._preview_cover.objectName() == "quicklook_preview_cover"

    # The reveal is warm here (the overlay is open): it shows the canvas and
    # must leave the built plate alone.
    ov._ql_chrome_painted = True
    ov.isVisible = lambda: True
    canvas.show = lambda: None
    canvas.update = lambda: None
    host.reveal_preview_canvas(ov, canvas)
    assert _pixels(_canon(_plate(ov))) == _pixels(want)


# -- the accessor contract ----------------------------------------------------


def test_current_view_returns_the_live_zoom_pan(qtbot):
    card = _pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    assert card.current_view() == (1.0, 0.0, 0.0)
    card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2
    assert card.current_view() == (2.5, 0.3, -0.2)


def test_current_view_never_raises_on_degenerate_state():
    """The accessor is total: bad stored values fall back to the identity view."""
    bad = SimpleNamespace(_zoom="nope", _pan_x=None, _pan_y=object())
    assert _pc.QuickLookCanvasWidget.current_view(bad) == (1.0, 0.0, 0.0)
    missing = SimpleNamespace()
    assert _pc.QuickLookCanvasWidget.current_view(missing) == (1.0, 0.0, 0.0)


def test_cover_uses_the_accessor_not_raw_view_fields():
    """The host resolves the view through ``current_view``, never the privates."""
    src = (
        inspect.getsource(_cover_mod._fit_cover)
        + inspect.getsource(_cover_mod._live_view_kwargs)
        + inspect.getsource(_cover_mod._cover_pixmap_from_full)
    )
    assert "current_view" in src
    for field in ("_zoom", "_pan_x", "_pan_y"):
        assert f".{field}" not in src, f"cover must not poke {field} directly"
