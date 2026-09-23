"""Quick look resize re-layout (W12 W-B) regression tests.

Recompose like the image-save (export) window: the preview pane stretches
with the card while the image inside keeps its aspect, the right column
stays a fixed 296px, the footer reflows (actions left, hint right), and all
existing reposition hooks re-run on every resize. W8 min-only stays
(minimum 1040×620, no maximum); no new close paths.
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
    """W-B: the preview pixmap itself grows with the card, keeping aspect."""
    from sli_ui_toolkit.managers import scaled_px

    src_p = _real_png(tmp_path, "src.png")
    v_p = _real_png(tmp_path, "v.png")
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={"width": 800, "height": 600})
    item = GalleryItem(path=v_p, mtime_ns=2, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)

    before = ov._preview_label.pixmap()
    assert before is not None and not before.isNull()
    bw, bh = before.width(), before.height()

    _grow(qtbot, ov)
    after = ov._preview_label.pixmap()
    assert after is not None and not after.isNull()
    # Grows with the card...
    assert after.width() * after.height() > bw * bh
    # ...fits the (grown) label, keeps the 4:3 source aspect (letterbox).
    label = ov._preview_label.size()
    assert after.width() <= label.width() + 2
    assert after.height() <= label.height() + 2
    assert abs(after.width() / after.height() - 800 / 600) < 0.05
    # The full source is stashed for re-derivation, not re-decoded per step.
    assert getattr(ov, "_preview_full", None) is not None
    assert ov._preview_full.width() == 800
    ov.hide()


def test_right_column_stays_fixed_296_on_resize(qtbot, tmp_path):
    """W-B: the right column never takes resize space (fixed 296, no scroll)."""
    from sli_ui_toolkit.managers import scaled_px

    src_p = _real_png(tmp_path, "src.png")
    v_p = _real_png(tmp_path, "v.png")
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={})
    item = GalleryItem(path=v_p, mtime_ns=2, metrics={"ssim": 0.9})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)

    _grow(qtbot, ov)
    scroll = ov.findChild(QScrollArea, "quicklook_right_scroll")
    assert scroll.width() == scaled_px(296)
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    assert scroll.horizontalScrollBar().isVisible() is False
    assert scroll.verticalScrollBar().isVisible() is False
    # ...and still fixed after shrinking back to the minimum.
    ov._content.resize(scaled_px(1040), scaled_px(620))
    QApplication.processEvents()
    QApplication.processEvents()
    assert scroll.width() == scaled_px(296)
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    ov.hide()


def test_footer_reflows_hint_right_on_resize(qtbot, tmp_path):
    """W-B: footer actions stay left, the hint stays pinned right on resize."""
    src_p = _real_png(tmp_path, "src.png")
    v_p = _real_png(tmp_path, "v.png")
    src = GalleryItem(path=src_p, mtime_ns=1, metrics={})
    item = GalleryItem(path=v_p, mtime_ns=2, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)

    def _assert_bar():
        bar = ov._content.findChild(QWidget, "quicklook_bottom_bar")
        assert bar is not None
        hint = ov._hint_label
        compare = ov._compare_btn
        # Hint is the last bar item and hugs the bar's right edge.
        lay = bar.layout()
        assert lay.itemAt(lay.count() - 1).widget() is hint
        hint_right = hint.mapTo(ov._content, hint.rect().topRight()).x()
        bar_right = bar.mapTo(ov._content, bar.rect().topRight()).x()
        assert abs(hint_right - bar_right) <= 20
        # Actions stay left of the hint with no overlaps.
        cmp_left = compare.mapTo(ov._content, compare.rect().topLeft()).x()
        hint_left = hint.mapTo(ov._content, hint.rect().topLeft()).x()
        assert cmp_left < hint_left
        prev_right = -1
        for btn in (ov._compare_btn, ov._multi_btn, ov._reject_btn, ov._set_source_btn):
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
    """W-B: W8 min-only stays — minimum 1040×620, no maximum cap."""
    from sli_ui_toolkit.managers import scaled_px

    ov = _make_overlay(qtbot)
    assert ov._content.minimumSize() == QSize(scaled_px(1040), scaled_px(620))
    assert ov._content.maximumSize() == QSize(16777215, 16777215)
    assert ov.sizeHint() == QSize(scaled_px(1040), scaled_px(620))
    ov.hide()
