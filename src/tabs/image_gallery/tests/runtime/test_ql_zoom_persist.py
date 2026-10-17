"""Quick Look — keep the view when stepping within ONE series (ql-zoom-persist).

User report: zooming into an image and then switching to another image of the
SAME series reset the view to 1.0 / centre ("зум каждый раз сбрасывается").

Root cause (verified): the zoom/pan live on the canvas widget
(``QuickLookCanvasWidget._zoom / _pan_x / _pan_y``) and were reset
UNCONDITIONALLY inside ``set_source`` — and every item switch goes through
``set_source`` (``_walk`` -> ``_populate`` -> ``populate_preview`` ->
``preview_canvas_host._populate_preview_canvas`` -> ``canvas.set_source``).
Missing feature, not a regression (the reset lines predate the fill wave).

Falsification story (pre-fix):
- ``test_walk_keeps_zoom_and_binds_new_source`` is the discriminator. On the
  pre-change tree the walk reaches ``set_source`` without the flag and resets
  the view: with ``_walk`` reverted to the default call (``self._populate()``)
  the test fails on ``card._zoom == 1.0`` (recorded in DONE.md). With the fix
  the zoom/pan survive while ``card._store`` still changes (that is the
  "pixels change, view does not" contract) and the walk still re-populates.
- The ``set_source`` / ``set_tiled_source`` / ``populate_preview`` default
  cases pin the PRE-CHANGE contract (reset) so the new flag can never turn
  into an unconditional keep.

Not covered here (out of this lane's file set / owned elsewhere): the
``_walk`` release keeps memos (``tests/runtime/test_ql_walk_release.py``,
unchanged) and the strip re-populate pin (``test_quicklook_strip.py``,
unchanged).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from tabs.image_gallery.ui.quick_look import preview as _preview
from tabs.image_gallery.ui.quick_look import preview_canvas as _pc
from tabs.image_gallery.ui.quick_look import preview_canvas_host as host
from tabs.image_gallery.ui.quick_look.overlay_parts import populate as _populate_parts


def _png(tmp_path: Path, name: str, color: str = "#3a6ea5") -> Path:
    pm = QPixmap(800, 600)
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
    ov._parity_test_parent = parent
    return ov


def _make_canvas(qtbot, ov, monkeypatch):
    """Real canvas slotted into the overlay (mirrors the host's own ensure)."""
    card = _pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    ov._preview_canvas = card
    host._install_memo_probe(ov, card)
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: card, raising=False)
    # The zoom>1.0 path kicks the uncapped tiled decode eagerly; stub it so a
    # test never races a real background decode (the view contract is what is
    # under test, not the tiled install).
    monkeypatch.setattr(host, "_populate_tiled_source", lambda *_a, **_k: None)
    return card


def _zoom_of(card) -> tuple:
    return (card._zoom, card._pan_x, card._pan_y)


# -- canvas-level flag contract ---------------------------------------------


def test_set_source_preserve_view_keeps_zoom_else_resets(qtbot):
    """preserve_view=True keeps zoom/pan/drag; default False is the old reset."""
    card = _pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    st_a = SimpleNamespace(close=lambda: None, is_open=True)
    st_b = SimpleNamespace(close=lambda: None, is_open=True)

    card.set_source(st_a)
    card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2
    card._drag_last = (3, 4)
    card._frame_ok = True

    card.set_source(st_b, preserve_view=True)
    assert _zoom_of(card) == (2.5, 0.3, -0.2), "preserve_view must keep the view"
    assert card._drag_last == (3, 4)
    assert card._store is st_b, "the new source is still adopted"
    # Frame/plan/watchdog bookkeeping still runs on the preserved path.
    assert card._frame_ok is False
    assert card._frame_key is None

    card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2
    card._drag_last = (3, 4)
    card.set_source(st_a)  # default False — pre-change contract
    assert _zoom_of(card) == (1.0, 0.0, 0.0)
    assert card._drag_last is None


def test_set_tiled_source_never_owns_the_view(qtbot):
    """The tiled registration must not clobber a view the walk preserved.

    ``preserve_view`` is part of the populate-chain signature (uniform with
    ``set_source``), but this entry point never owned the view: resetting
    here would clobber a walk-preserved zoom whenever the dwell / zoom>1.0
    tiled install lands after the walk (the reset owner is ``set_source``).
    Both flag values therefore keep today's behavior — the view is untouched.
    """
    card = _pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    store = SimpleNamespace(close=lambda: None, is_open=True)
    card.set_source(store)
    card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2

    card.set_tiled_source("k", store, preserve_view=True)
    assert _zoom_of(card) == (2.5, 0.3, -0.2)
    assert card._tiled_source == ("k", store)

    # Dwell/zoom install landing after a walk (default flag): no reset.
    card.set_tiled_source("k", store)
    assert _zoom_of(card) == (2.5, 0.3, -0.2)
    card.set_tiled_source("k", store, preserve_view=False)
    assert _zoom_of(card) == (2.5, 0.3, -0.2)


# -- populate-chain forwarding ----------------------------------------------


def test_populate_preview_forwards_preserve_view(qtbot, tmp_path, monkeypatch):
    """populate_preview(..., preserve_view=...) reaches the canvas."""
    a = _item(_png(tmp_path, "pa.png"))
    ov = _make_overlay(qtbot)
    card = _make_canvas(qtbot, ov, monkeypatch)
    try:
        _preview.populate_preview(ov, a)
        assert card._store is not None, "baseline populate must bind a source"

        card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2
        _preview.populate_preview(ov, a)  # default False
        assert _zoom_of(card) == (1.0, 0.0, 0.0)

        card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2
        _preview.populate_preview(ov, a, preserve_view=True)
        assert _zoom_of(card) == (2.5, 0.3, -0.2)
    finally:
        ov.hide()


# -- the user-visible bug ---------------------------------------------------


def test_walk_keeps_zoom_and_binds_new_source(qtbot, tmp_path, monkeypatch):
    """A within-series walk re-binds the source but keeps the zoom (the bug)."""
    a = _item(_png(tmp_path, "wa.png", "#c0392b"))
    b = _item(_png(tmp_path, "wb.png"))
    ov = _make_overlay(qtbot)
    card = _make_canvas(qtbot, ov, monkeypatch)
    try:
        ov._series_items = [a, b]
        ov._current_idx = 0
        ov._current_item = a
        assert host._populate_preview_canvas(ov, a) is True
        store_a = card._store
        assert store_a is not None

        card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2
        ov._walk(1)
        QApplication.processEvents()

        assert ov._current_idx == 1
        assert card._store is not None and card._store is not store_a, (
            "a walk must still bind the new source — the pixels change"
        )
        assert _zoom_of(card) == (2.5, 0.3, -0.2), (
            "a within-series walk must keep the user's zoom/pan"
        )
    finally:
        ov.hide()


def test_walk_keeps_view_then_context_change_resets(qtbot, tmp_path, monkeypatch):
    """Walk keeps the view; opening / series change (show_for) resets it."""
    a = _item(_png(tmp_path, "ca.png"))
    b = _item(_png(tmp_path, "cb.png"))
    ov = _make_overlay(qtbot)
    card = _make_canvas(qtbot, ov, monkeypatch)
    try:
        ov._series_items = [a, b]
        ov._current_idx = 0
        ov._current_item = a
        assert host._populate_preview_canvas(ov, a) is True

        card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2
        ov._walk(1)
        QApplication.processEvents()
        assert _zoom_of(card) == (2.5, 0.3, -0.2)

        owner = SimpleNamespace(
            state=SimpleNamespace(
                mode=Mode.FIDELITY,
                source_path=None,
                series=[[a, b]],
                items=[a, b],
            )
        )
        ov.show_for(a, owner)
        QApplication.processEvents()
        assert _zoom_of(card) == (1.0, 0.0, 0.0), (
            "a context change (open / series change) must reset the view"
        )
    finally:
        ov.hide()


def test_strip_click_keeps_zoom_within_series(qtbot, tmp_path, monkeypatch):
    """Clicking ANOTHER thumb of the same series keeps the view (strip path).

    The strip's own click path bypasses ``_walk`` and re-populates directly
    (``strip/rebuild.py``); it must pass the same within-series intent.
    """
    from sli_ui_toolkit.widgets import Button

    paths = [_png(tmp_path, f"st{i}.png") for i in range(3)]
    items = [_item(p) for p in paths]
    ov = _make_overlay(qtbot)
    card = _make_canvas(qtbot, ov, monkeypatch)
    try:
        owner = SimpleNamespace(
            state=SimpleNamespace(
                mode=Mode.FIDELITY,
                source_path=None,
                series=[list(items)],
                items=list(items),
            )
        )
        ov.show_for(items[0], owner)
        parent = getattr(ov, "_parity_test_parent", None)
        if parent is not None:
            parent.resize(1280, 800)
            parent.show()
        QApplication.processEvents()
        assert ov._current_idx == 0

        card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2
        target = None
        for b in ov._strip_host.findChildren(Button):
            if b.property("gallery_path") == str(paths[1]):
                target = b
                break
        assert target is not None, "strip thumb for the second member missing"
        target.regionClicked.emit("thumb")
        qtbot.wait(450)  # defer_click (press ripple) then the switch
        QApplication.processEvents()

        assert ov._current_idx == 1
        assert _zoom_of(card) == (2.5, 0.3, -0.2), (
            "a strip click within one series keeps the view"
        )
    finally:
        ov.hide()


def test_plain_repopulate_default_resets(qtbot, tmp_path, monkeypatch):
    """Non-navigation re-populates (delete / set-as-source) keep the default.

    They call ``_populate()`` with no flag (the class delegator's default),
    so the pre-change reset still fires there.
    """
    a = _item(_png(tmp_path, "da.png"))
    b = _item(_png(tmp_path, "db.png"))
    ov = _make_overlay(qtbot)
    card = _make_canvas(qtbot, ov, monkeypatch)
    try:
        ov._series_items = [a, b]
        ov._current_idx = 0
        ov._current_item = a
        assert host._populate_preview_canvas(ov, a) is True

        card._zoom, card._pan_x, card._pan_y = 2.5, 0.3, -0.2
        _populate_parts._populate(ov)  # delete / set-as-source / re-analyze
        QApplication.processEvents()
        assert _zoom_of(card) == (1.0, 0.0, 0.0)
    finally:
        ov.hide()
