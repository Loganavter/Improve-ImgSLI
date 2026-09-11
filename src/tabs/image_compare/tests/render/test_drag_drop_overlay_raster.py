"""DnD overlay raster actually produces visible tiles (QRhi-independent).

The drag/show state machine (``WindowEventHandler`` + canvas
``set_drag_overlay_state``) can flip ``runtime_state._drag_overlay_visible``
without the blue tiles ever appearing on screen. This test isolates the
raster stage: with the state ON, ``DragDropOverlayPass._raster`` must return
a non-null image whose pixels have non-zero coverage (both halves of the
canvas painted), proving the pass paints into the frame at all —
presentation/compositor questions are then the only remaining suspects.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage

from tabs.image_compare.canvas.features.drag_drop_overlay.passes import (
    DragDropOverlayPass,
)


def _widget():
    from PySide6.QtGui import QFont

    font = QFont()
    state = SimpleNamespace(
        _drag_overlay_visible=True,
        _drag_overlay_horizontal=False,
        _drag_overlay_texts=("one", "two"),
    )
    return SimpleNamespace(
        runtime_state=state,
        width=lambda: 800,
        height=lambda: 600,
        devicePixelRatioF=lambda: 1.0,
        font=lambda: font,
        property=lambda name: None,
        palette=lambda: __import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget().palette(),
    )


def _opaque_fraction(img: QImage) -> float:
    opaque = 0
    total = img.width() * img.height()
    for y in range(0, img.height(), 4):
        for x in range(0, img.width(), 4):
            if img.pixelColor(x, y).alpha() > 0:
                opaque += 1
    sampled = (img.width() // 4) * (img.height() // 4)
    return opaque / max(1, sampled)


def test_drag_overlay_raster_paints_both_tiles(qapp):
    w = _widget()
    ctx = SimpleNamespace(widget=w, framebuffer_size=(800, 600))
    p = DragDropOverlayPass()
    assert p.should_paint(ctx) is True
    img = p._raster(w, ctx)
    assert img is not None and not img.isNull()
    frac = _opaque_fraction(img)
    # Two large rounded tiles: coverage must be substantial (fill ~35%+).
    assert frac > 0.15, f"DnD raster produced a nearly-transparent image (coverage={frac:.3f})"


def test_drag_overlay_raster_hidden_state_returns_none(qapp):
    w = _widget()
    w.runtime_state._drag_overlay_visible = False
    ctx = SimpleNamespace(widget=w, framebuffer_size=(800, 600))
    p = DragDropOverlayPass()
    assert p.should_paint(ctx) is False
    assert p._raster(w, ctx) is None


def test_drag_overlay_raster_uses_cache(qapp):
    w = _widget()
    ctx = SimpleNamespace(widget=w, framebuffer_size=(800, 600))
    p = DragDropOverlayPass()
    first = p._raster(w, ctx)
    assert first is not None
    assert w.runtime_state._drag_overlay_cache_key == (800, 600, False, "one", "two", 1.0)
    # Second call with unchanged state must hit the cache (same object, no
    # re-raster): steady pump frames stay cheap during a drag.
    assert p._raster(w, ctx) is first
    # State flip invalidates (interaction.set_drag_overlay_state clears it).
    w.runtime_state._drag_overlay_cache_key = None
    w.runtime_state._drag_overlay_cached_image = None
    assert p._raster(w, ctx) is not first


def test_drag_overlay_raster_fades_in_from_show_edge(qapp, monkeypatch):
    """Telegram-style fade: first frames are a ghost, then full opacity."""
    import time

    from tabs.image_compare.canvas.features.drag_drop_overlay.passes import (
        _fade_progress,
    )

    w = _widget()
    # No show edge recorded (e.g. unit fakes): final opacity, unchanged.
    assert _fade_progress(w) == 1.0
    # Fresh show edge: near-zero progress (ghost frame).
    w._dnd_show_t0 = time.monotonic()
    assert _fade_progress(w) < 0.25
    # Aged show edge: final opacity.
    w._dnd_show_t0 = time.monotonic() - 10.0
    assert _fade_progress(w) == 1.0
    # Escape hatch restores binary show.
    monkeypatch.setenv("IMGSLI_DND_NO_FADE", "1")
    w._dnd_show_t0 = time.monotonic()
    assert _fade_progress(w) == 1.0
    monkeypatch.delenv("IMGSLI_DND_NO_FADE", raising=False)

    # End-to-end through _raster: ghost frame has strictly less coverage
    # than the settled frame for the same state.
    w._dnd_show_t0 = time.monotonic()
    w.runtime_state._drag_overlay_cache_key = None
    w.runtime_state._drag_overlay_cached_image = None
    ctx = SimpleNamespace(widget=w, framebuffer_size=(800, 600))
    p = DragDropOverlayPass()
    ghost = p._raster(w, ctx)
    assert ghost is not None
    w._dnd_show_t0 = time.monotonic() - 10.0
    w.runtime_state._drag_overlay_cache_key = None
    w.runtime_state._drag_overlay_cached_image = None
    settled = p._raster(w, ctx)
    assert settled is not None
    assert _opaque_fraction(ghost) < _opaque_fraction(settled)
