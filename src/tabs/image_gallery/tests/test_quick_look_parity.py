"""Quick look (S4) design-parity regression tests.

Covers audit items S4-1, S4-2, S4-4, S4-5, S4-6, S4-7, S4-8, S4-9 against
design.md "Quick look report" + ui-mockup-v4-quicklook.svg.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget

from tabs.image_gallery.models import Artifact, GalleryItem, Mode, Severity
from tabs.image_gallery.ui.quick_look import (
    DIM_VEIL_ALPHA,
    QuickLookOverlay,
    _SourceInsetHost,
    _source_dimensions,
)


def _item(name: str, **kwargs) -> GalleryItem:
    return GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1, **kwargs)


@pytest.fixture()
def _w1_light_palettes(qapp):
    """Register the production W1 palettes under the light theme.

    Rule A: strip borders then resolve live ``themes.json`` hexes
    (``gallery.status.warn`` / ``accent``) instead of fallback literals.
    Teardown restores the bare manager so later suites keep their
    unbootstrapped behavior.
    """
    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from sli_ui_toolkit.managers import ThemeManager

    tm = ThemeManager.get_instance()
    prev_theme = tm.get_current_theme()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme("light", qapp, await_ripples=False)
    try:
        tm._flush_pending_theme()  # type: ignore[attr-defined]
    except Exception:
        pass
    yield tm
    try:
        tm.register_palettes({}, {})
        tm.set_theme(prev_theme, qapp, await_ripples=False)
        tm._flush_pending_theme()  # type: ignore[attr-defined]
    except Exception:
        pass


@pytest.fixture()
def overlay(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    yield ov
    try:
        ov.hide()
    except Exception:
        pass


def _make_overlay(qtbot) -> QuickLookOverlay:
    # NB: qtbot.addWidget tracks widgets via weakref, so the parent must be
    # kept referenced for the whole test or the overlay subtree is destroyed.
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent  # strong ref, keeps C++ tree alive
    return ov


def _show(overlay: QuickLookOverlay, item: GalleryItem, series, mode=Mode.FIDELITY, source=None):
    # state.series is list[Series] | list[list[GalleryItem]] — wrap a flat
    # list of items into one cluster the way the widget stores it.
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
    # Real visibility + layout: the overlay only counts as visible over a
    # shown window (production state). Needed for isVisible()/geometry and
    # for refresh_* which no-op while hidden.
    try:
        parent = getattr(overlay, "_parity_test_parent", None) or overlay.parentWidget()
        if parent is not None:
            parent.resize(1280, 800)
            parent.show()
    except Exception:
        pass
    QApplication.processEvents()


# -- P0-8: no region claims without region analysis ----------------------------


def test_no_region_suffix_on_any_artifact(qtbot):
    banding = _item("b.png", artifacts={Artifact.BANDING: Severity.MILD}, metrics={})
    halo = _item("h.png", artifacts={Artifact.HALO: Severity.MILD}, metrics={})
    for item in (banding, halo):
        ov = _make_overlay(qtbot)
        _show(ov, item, [item])
        texts = [
            lbl.text()
            for w in ov._artifact_rows
            for lbl in w.findChildren(type(ov._mode_chip))
        ]
        assert "mild" in texts
        assert all("sky region" not in t for t in texts)
        ov.hide()


# -- S4-4: mockup artifact rows (Banding + Halo) incl. clean ---------------
# (W4 item 8: hiding clean rows hid the banding base on all-clean items.
# W5: the overlay shows the mockup set only — Banding + Halo. The full
# 7-key catalog stays in the card dots/tooltip, untouched.)


def test_all_artifact_rows_shown_including_clean(qtbot):
    item = _item("c.png", artifacts={}, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    assert len(ov._artifact_rows) == 2
    assert ov._artifacts_host.isVisibleTo(ov._artifacts_host.parentWidget())
    texts = [
        lbl.text()
        for w in ov._artifact_rows
        for lbl in w.findChildren(type(ov._mode_chip))
    ]
    titles = [lbl.text() for w in ov._artifact_rows for lbl in w.findChildren(type(ov._mode_chip))]
    assert any("Banding" in t for t in titles)
    assert any("Halo" in t for t in titles)
    assert "clean" in texts
    ov.hide()


def test_non_clean_artifact_rows_shown(qtbot):
    item = _item(
        "d.png",
        artifacts={
            Artifact.BANDING: Severity.MILD,
            Artifact.HALO: Severity.FLAGGED,
        },
        metrics={},
    )
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    # Mockup set only (Banding + Halo); severities read severity-only.
    assert len(ov._artifact_rows) == 2
    assert ov._artifacts_host.isVisibleTo(ov._artifacts_host.parentWidget())
    texts = [
        lbl.text()
        for w in ov._artifact_rows
        for lbl in w.findChildren(type(ov._mode_chip))
    ]
    assert "mild" in texts and "flagged" in texts
    ov.hide()


def test_halo_renders_as_bar_widget(qtbot):
    """W4 item 8: halo is a horizontal _BarWidget like the metric rows."""
    from tabs.image_gallery.ui.quick_look.bars import _BarWidget

    item = _item("h.png", artifacts={Artifact.HALO: Severity.MILD}, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    halo_rows = [
        w for w in ov._artifact_rows
        if any("Halo" in lbl.text() for lbl in w.findChildren(type(ov._mode_chip)))
    ]
    assert len(halo_rows) == 1
    assert halo_rows[0].findChild(_BarWidget) is not None
    ov.hide()


# -- S4-1: source inset border host + caption dimensions ---------------------


def test_source_inset_host_paints_border(qtbot):
    host = _SourceInsetHost()
    host.resize(100, 80)
    qtbot.addWidget(host)
    pm = host.grab()  # paintEvent smoke — border painter must not raise
    assert not pm.isNull()


def test_source_dimensions_prefers_metrics(monkeypatch):
    item = _item("s.png", metrics={"width": 960, "height": 540})
    assert _source_dimensions(item, Path("/gallery/s.png")) == (960, 540)


def test_source_caption_includes_dimensions(qtbot):
    src = _item("src.png", metrics={"width": 960, "height": 540})
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)
    # Caption is an overlaid strip elided to width (W4 item 5): the full
    # caption lives in _original_text even when the strip elides the tail.
    full = ov._source_inset_label._original_text
    assert full.startswith("SOURCE · src.png")
    assert "960×540" in full
    ov.hide()


# -- S4-5: SSIM muted subline -------------------------------------------------


def test_ssim_subline_next_rank_and_rejected_tail(qtbot):
    src = _item("src.png", rank=0, metrics={})
    viewing = _item("v.png", rank=1, metrics={"ssim": 0.95})
    second = _item("b.png", rank=2, metrics={"ssim": 0.91})
    rejected = _item("r.png", rank=3, rejected=True, metrics={"ssim": 0.83})
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [src, viewing, second, rejected])
    subline = ov._ssim_subline(viewing)
    assert "#2 scores 0.91" in subline
    assert "rejected tail ≤ 0.83" in subline
    ov.hide()


def test_ssim_subline_empty_without_data(qtbot):
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    assert ov._ssim_subline(item) == ""
    ov.hide()


# -- S4-6: camera noise + WB shift rows ---------------------------------------


def test_camera_noise_and_wb_rows_present_when_metrics_exist(qtbot):
    item = _item(
        "cam.png",
        metrics={"sharpness": 150.0, "exposure": 0.5, "clipping": 0.4, "noise": 0.2, "wb_shift": 0.12},
    )
    ov = _make_overlay(qtbot)
    _show(ov, item, [item], mode=Mode.CAMERA)
    texts = [
        lbl.text()
        for row in ov._metric_rows
        for lbl in row.findChildren(type(ov._mode_chip))
    ]
    assert "Noise" in texts
    assert any("warm" in t for t in texts)
    ov.hide()


def test_camera_noise_and_wb_rows_skipped_when_missing(qtbot):
    item = _item("cam.png", metrics={"sharpness": 150.0, "exposure": 0.5, "clipping": 0.4})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item], mode=Mode.CAMERA)
    texts = [
        lbl.text()
        for row in ov._metric_rows
        for lbl in row.findChildren(type(ov._mode_chip))
    ]
    assert "Noise" not in texts
    assert "WB shift" not in texts
    ov.hide()


# -- S4-7: strip borders + rejected dim ----------------------------------------


def test_strip_source_and_viewing_border_colors(qtbot, _w1_light_palettes):
    from PySide6.QtGui import QColor

    from sli_ui_toolkit.widgets import Button

    src = _item("src.png")
    viewing = _item("v.png")
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [src, viewing], source=src.path)
    buttons = [
        b for b in ov._strip_host.findChildren(Button) if b.objectName().startswith("quicklook_strip_")
    ]
    assert len(buttons) == 2
    by_path = {b.property("gallery_path"): b for b in buttons}
    # Light production palettes registered → borders resolve the live
    # gallery.status.warn / accent hexes via the real painter border API
    # (not the old setProperty no-op). White-cards norm: warn #e8b64c; the
    # viewing border follows the global accent token (untouched #0078D4).
    assert by_path["/gallery/src.png"].borderColor() == QColor("#e8b64c")
    assert by_path["/gallery/v.png"].borderColor() == QColor("#0078D4")
    ov.hide()


def test_strip_rejected_thumb_dimmed_but_clickable(qtbot):
    viewing = _item("v.png")
    rejected = _item("r.png", rejected=True)
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, rejected])
    from sli_ui_toolkit.widgets import Button

    for b in ov._strip_host.findChildren(Button):
        if b.property("gallery_path") == "/gallery/r.png":
            assert b.isEnabled()
            eff = b.graphicsEffect()
            assert isinstance(eff, QGraphicsOpacityEffect)
            assert eff.opacity() == pytest.approx(0.4)
    ov.hide()


# -- S4-8: bottom bar button colors ---------------------------------------------


def test_bottom_bar_button_colors(qtbot):
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    # Compare: accent tint via set_background_color (real Button API).
    assert ov._compare_btn.getBackgroundColor() is not None
    # Reject: red stroke via setBorderColor override.
    assert ov._reject_btn.borderColor() is not None
    # Set as source: amber stroke.
    assert ov._set_source_btn.borderColor() is not None
    ov.hide()


# -- S4-9: FIDELITY MODE chip accent color ---------------------------------------


def test_mode_chip_uses_accent_token(qtbot):
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    assert ov._mode_chip._color_token_override == "accent"
    ov.hide()


# -- Wave B parity close-out regressions (P0-3/4/5/6) ---------------------------


def _noise_png(path, size, seed: int):
    from PIL import Image

    import numpy as np

    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(arr, "RGB").save(path)


def test_fidelity_writers_produce_four_keys(tmp_path):
    from tabs.image_gallery.services.fidelity_metrics import (
        apply_fidelity_metrics,
        compute_fidelity_metrics,
    )

    src = tmp_path / "src.png"
    up = tmp_path / "up.png"
    _noise_png(src, (64, 64), seed=7)
    _noise_png(up, (128, 128), seed=8)
    measured = compute_fidelity_metrics(up, src)
    for key in ("ssim", "hf_ratio", "delta_e", "upscale_factor"):
        assert key in measured, f"missing fidelity key {key}"
    assert 0.0 <= measured["ssim"] <= 1.0
    assert measured["delta_e"] >= 0
    assert isinstance(measured["upscale_factor"], int)
    assert measured["upscale_factor"] == 2


def test_fidelity_apply_is_identity_fail_closed(tmp_path):
    from tabs.image_gallery.services.fidelity_metrics import apply_fidelity_metrics

    src = tmp_path / "src.png"
    up = tmp_path / "up.png"
    _noise_png(src, (64, 64), seed=7)
    _noise_png(up, (128, 128), seed=8)
    item = GalleryItem(path=up, mtime_ns=1, metrics={})
    other = GalleryItem(path=tmp_path / "other.png", mtime_ns=1, metrics={})
    assert apply_fidelity_metrics(item, src) is True
    for key in ("ssim", "hf_ratio", "delta_e", "upscale_factor"):
        assert key in item.metrics
    # Nothing is ever copied between items: the untouched item stays empty,
    # and a missing file writes nothing (fail-closed).
    assert other.metrics == {}
    missing = GalleryItem(path=tmp_path / "gone.png", mtime_ns=1, metrics={})
    assert apply_fidelity_metrics(missing, src) is False
    assert missing.metrics == {}


def test_dual_marker_frac_restored_side():
    from tabs.image_gallery.ui.quick_look.bars import dual_marker_frac

    assert dual_marker_frac(0.18) == pytest.approx(0.41)
    assert dual_marker_frac(0.0) == pytest.approx(0.5)
    assert dual_marker_frac(-1.0) == pytest.approx(1.0)
    assert dual_marker_frac(5.0) == pytest.approx(0.0)


def test_multi_compare_keeps_two_after_two_adds(qtbot):
    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    ov._owner.state.selected_paths = set()
    ov._owner.state.selected_order = []
    ov._on_multi()
    ov.show_for(b, ov._owner)
    ov._on_multi()
    assert len(ov._owner.state.selected_paths) >= 2
    ov.hide()


def test_quick_compare_hook_merges_instead_of_clobbering():
    from tabs.image_gallery.ui import quick_look_hooks as _hooks

    owner = SimpleNamespace(state=SimpleNamespace(selected_paths=set(), selected_order=[]))
    _hooks.on_quick_compare(owner, Path("/gallery/a.png"))
    _hooks.on_quick_compare(owner, Path("/gallery/b.png"))
    assert len(owner.state.selected_paths) >= 2


def test_set_source_flips_chip_to_fidelity(qtbot):
    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, b, [a, b], mode=Mode.CAMERA)
    assert "CAMERA" in ov._mode_chip.text()
    ov._on_set_source()
    assert "FIDELITY" in ov._mode_chip.text()
    assert ov._owner.state.mode == Mode.FIDELITY
    assert ov._owner.state.source_path == b.path
    ov.hide()


def test_series_header_shows_index_and_hub(qtbot):
    src = _item("src.png")
    viewing = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [src, viewing], source=src.path)
    assert ov._series_header.text() == "Series 1 · src"
    ov.hide()


def test_local_brief_fallback_without_vlm(qtbot):
    viewing = _item("v.png", rank=1, metrics={"ssim": 0.95, "hf_ratio": 0.18})
    second = _item("b.png", rank=2, metrics={"ssim": 0.91, "hf_ratio": -0.31})
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, second])
    text = ov._brief_label.text()
    assert text.startswith("vs #2:")
    assert "0.95" in text and "0.91" in text
    ov.hide()


def test_meta_order_dims_format_size(qtbot, tmp_path):
    from PIL import Image as _PIL

    p = tmp_path / "m.png"
    _PIL.new("RGB", (64, 32), (10, 20, 30)).save(p)
    item = GalleryItem(path=p, mtime_ns=1, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    assert ov._meta_label.text().startswith("64 × 32 · PNG · ")
    ov.hide()


# -- W1 chrome: veil / plate / geometry / crop gate / refresh_metrics --------


def test_veil_alpha_matches_mockup():
    """Veil override assert (mirrors test_clean_review_parity.py:274)."""
    from sli_ui_toolkit.widgets import TopLevelInWindowOverlay

    assert QuickLookOverlay.paintEvent is not TopLevelInWindowOverlay.paintEvent
    assert DIM_VEIL_ALPHA == round(0.45 * 255) == 115


def test_veil_dims_background(qtbot):
    """The overlay paints a fullscreen 0.45-black veil (offscreen ``grab``
    returns the raw translucent pixel, so assert alpha + blackness)."""
    from PySide6.QtGui import QColor, QPalette

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.setAutoFillBackground(True)
    pal = parent.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor("white"))
    parent.setPalette(pal)
    parent.resize(800, 600)
    parent.show()

    ov = QuickLookOverlay(parent)
    qtbot.addWidget(ov)
    ov._parity_test_parent = parent
    ov._content.hide()  # veil only — no content plate over the sample
    ov.setGeometry(parent.rect())
    ov.show()
    QApplication.processEvents()

    try:
        pixel = ov.grab().toImage().pixelColor(5, 5)
    finally:
        ov.hide()
    assert abs(pixel.alpha() - DIM_VEIL_ALPHA) <= 2, pixel.alpha()
    assert pixel.red() == pixel.green() == pixel.blue() == 0


def test_card_plate_fill_border_radius(qtbot, _w1_light_palettes):
    """Card plate: ``gallery.card.background`` fill + border + rx 12, no QSS."""
    from PySide6.QtGui import QColor

    from tabs.image_gallery.ui.quick_look.helpers import (
        QUICK_LOOK_CARD_RADIUS_PX,
        _CardPlate,
    )

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    plate = ov._content
    assert isinstance(plate, _CardPlate)
    assert _CardPlate.paintEvent is not QWidget.paintEvent
    assert QUICK_LOOK_CARD_RADIUS_PX == 12
    # Light production palettes registered → live token hexes (design.md
    # light-theme norm: white card + #e2e4e8 hairline, never fill contrast).
    assert plate._bg == QColor("#ffffff")
    assert plate._border == QColor("#e2e4e8")
    # Painter pipeline owns visuals — no ad-hoc QSS on the plate.
    assert plate.styleSheet() == ""
    ov.hide()


def test_card_plate_paints_fill(qtbot, _w1_light_palettes):
    """Bare plate grab: interior pixel is the card fill (paintEvent smoke)."""
    from tabs.image_gallery.ui.quick_look.helpers import _CardPlate

    plate = _CardPlate()
    qtbot.addWidget(plate)
    plate.resize(400, 200)
    plate.show()
    QApplication.processEvents()
    pixel = plate.grab().toImage().pixelColor(200, 100)
    assert (pixel.red(), pixel.green(), pixel.blue()) == (255, 255, 255)
    assert pixel.alpha() == 255


def test_card_geometry_min_1040x620_no_max(qtbot):
    """W8: S4 mockup panel 1040x620 (svg:31) is the card MINIMUM — the card
    is user-resizable, so there is no maximum (was: fixed min == max)."""
    from sli_ui_toolkit.managers import scaled_px

    ov = _make_overlay(qtbot)
    assert ov._content.minimumSize() == QSize(scaled_px(1040), scaled_px(620))
    assert ov._content.maximumSize() == QSize(16777215, 16777215)
    assert ov.sizeHint() == QSize(scaled_px(1040), scaled_px(620))


def test_card_resize_smoke_preview_grows_column_stretches(qtbot, monkeypatch):
    """W13 resize smoke: a bigger card grows the preview pane AND stretches
    the right column (floor 296px) with no scrollbars, and the pin hooks
    (nav circles, source inset, resize grip) re-ran for the new size."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QScrollArea, QWidget

    from sli_ui_toolkit.managers import scaled_px
    from tabs.image_gallery.ui.quick_look import helpers as _ql_helpers

    src = _item("src.png", metrics={"width": 960, "height": 540})
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)
    QApplication.processEvents()
    QApplication.processEvents()
    content = ov._content
    # Spy the reposition hooks: the _content Resize filter must re-run them.
    hook_calls: list = []
    orig_inset = ov._reposition_source_inset

    def _spy_inset():
        hook_calls.append("inset")
        return orig_inset()

    monkeypatch.setattr(ov, "_reposition_source_inset", _spy_inset)
    orig_grip = _ql_helpers.reposition_grip

    def _spy_grip(overlay):
        hook_calls.append("grip")
        return orig_grip(overlay)

    monkeypatch.setattr(_ql_helpers, "reposition_grip", _spy_grip)
    preview_before = ov._preview_host.size()
    base_w, base_h = content.width(), content.height()
    assert (base_w, base_h) == (scaled_px(1040), scaled_px(620))
    # W13: column floor 296px, stretches with the card (never fixed width).
    scroll_before = ov.findChild(QScrollArea, "quicklook_right_scroll")
    assert scroll_before.minimumWidth() == scaled_px(296)
    col_before = scroll_before.width()
    assert col_before >= scaled_px(296)
    content.resize(base_w + scaled_px(160), base_h + scaled_px(80))
    QApplication.processEvents()
    QApplication.processEvents()
    # Hooks re-ran for the resize.
    assert "inset" in hook_calls
    assert "grip" in hook_calls
    # Preview pane took its priority share of the extra space; the right
    # column stretched too (never below the 296px floor).
    assert ov._preview_host.width() > preview_before.width()
    assert ov._preview_host.height() > preview_before.height()
    # Right column stretched with the card, scrollbars still hidden.
    scroll = ov.findChild(QScrollArea, "quicklook_right_scroll")
    assert scroll.width() > col_before
    assert scroll.width() >= scaled_px(296)
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    assert scroll.horizontalScrollBar().isVisible() is False
    assert scroll.verticalScrollBar().isVisible() is False
    # Nav circles re-pinned to the new card edges (W10: overlay coords —
    # buttons are overlay children, centers on the card left/right edges).
    card = content.geometry()
    assert abs(ov._prev_btn.geometry().center().x() - card.x()) <= 2
    assert abs(ov._next_btn.geometry().center().x() - (card.x() + card.width())) <= 2
    # Grip re-pinned to the new bottom-right corner.
    grip = ov._resize_grip
    assert grip.parentWidget() is content
    assert grip.geometry().topLeft() == QPoint(
        content.width() - grip.width(), content.height() - grip.height()
    )
    ov.hide()


def test_resize_grip_drag_clamp_floor_and_paint(qtbot):
    """W8 drag handle: painter-painted (no QSS), bottom-right child of the
    card; dragging clamps to the overlay minus margin and floors at the
    1040x620 minimum; nothing is persisted (session-only size)."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.managers import scaled_px
    from tabs.image_gallery.ui.quick_look.helpers import _ResizeGrip

    src = _item("src.png", metrics={"width": 960, "height": 540})
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)
    QApplication.processEvents()
    QApplication.processEvents()
    grip = ov._resize_grip
    assert isinstance(grip, _ResizeGrip)
    assert _ResizeGrip.paintEvent is not QWidget.paintEvent
    assert grip.styleSheet() == ""
    assert grip.objectName() == "quicklook_resize_grip"
    assert not grip.grab().isNull()  # paintEvent smoke — must not raise

    def _press_move_release(dx: int, dy: int):
        from PySide6.QtCore import QPoint

        start_global = grip.mapToGlobal(grip.rect().center())
        end_global = start_global + QPoint(dx, dy)
        local = QPointF(grip.rect().center())
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            local,
            QPointF(start_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        grip.mousePressEvent(press)
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            local,
            QPointF(end_global),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        grip.mouseMoveEvent(move)
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            local,
            QPointF(end_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        grip.mouseReleaseEvent(release)
        QApplication.processEvents()

    content = ov._content
    # Drag far past the window: clamped to overlay minus the 16px margin.
    _press_move_release(1000, 1000)
    margin = scaled_px(16)
    assert content.width() == ov.width() - margin * 2
    assert content.height() == ov.height() - margin * 2
    # Drag far the other way: floored at the 1040x620 minimum.
    _press_move_release(-2000, -2000)
    assert content.size() == QSize(scaled_px(1040), scaled_px(620))
    # Grip followed the card back to the minimum corner.
    from PySide6.QtCore import QPoint

    assert grip.geometry().topLeft() == QPoint(
        content.width() - grip.width(), content.height() - grip.height()
    )
    ov.hide()


def test_card_size_is_session_only():
    """W8: the resized card size lives on the widget only — no settings /
    persistence writes in the quick look scope."""
    import inspect

    from tabs.image_gallery.ui import quick_look as _ql_mod
    from tabs.image_gallery.ui.quick_look import helpers as _ql_helpers

    for mod in (_ql_mod, _ql_helpers):
        src = inspect.getsource(mod)
        assert "QSettings" not in src
        assert "setValue" not in src


def test_prev_next_36px_circular_at_preview_edges(qtbot):
    """Prev/next: 36px circles overlapping the card edge half-outside (svg:67-70).

    W4 item 6: each circle's center sits on the card edge, vertically
    centered on the preview band. W10: overlay children (siblings above
    the plate) in overlay coords — the plate clips children to its rect,
    which erased the outside half when parented to the card.
    """
    from PySide6.QtCore import QPoint

    from sli_ui_toolkit.managers import scaled_px

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    QApplication.processEvents()
    content = ov._content
    host = ov._preview_host
    assert (ov._prev_btn.width(), ov._prev_btn.height()) == (scaled_px(36), scaled_px(36))
    assert (ov._next_btn.width(), ov._next_btn.height()) == (scaled_px(36), scaled_px(36))
    for btn, glyph in ((ov._prev_btn, "‹"), (ov._next_btn, "›")):
        # Circular via the painter pipeline (Button corner_radius, design px
        # — Button scales it internally); glyph via rows (text= buttons stay
        # content-sized); no QSS.
        assert btn._corner_radius_px == 18
        assert btn.styleSheet() == ""
        glyphs = [
            row.text for region in btn.regions() for row in (getattr(region, "rows", None) or [])
        ]
        assert glyph in glyphs
        # Overlay children above the card plate (W10: card-parent clipping
        # erased the outside half), no QSS.
        assert btn.parentWidget() is ov
        try:
            btn.raise_()
        except Exception:
            pass
    # Half-outside: prev center on the left card edge, next on the right
    # (overlay coords — geometry is overlay-local since W10).
    card = content.geometry()
    prev_c = ov._prev_btn.geometry().center()
    next_c = ov._next_btn.geometry().center()
    assert abs(prev_c.x() - card.x()) <= 2
    assert abs(next_c.x() - (card.x() + card.width())) <= 2
    # Vertically centered on the preview band (mapped to overlay coords).
    host_top = host.mapTo(ov, QPoint(0, 0)).y()
    for c in (prev_c, next_c):
        assert host_top <= c.y() <= host_top + host.height()
    ov.hide()


def test_prev_next_keep_border_when_disabled(qtbot):
    """W4 item 6: the nav border is explicit, so it survives disable."""
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    for btn in (ov._prev_btn, ov._next_btn):
        btn.setEnabled(False)
        assert btn.borderColor() is not None
    ov.hide()


def test_crop_hidden_in_fidelity(qtbot):
    """S4 v2 LIGHT draws no SHARPNESS CROP inset in fidelity mode."""
    src = _item("src.png", metrics={"width": 960, "height": 540})
    viewing = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [src, viewing], source=src.path)
    assert "FIDELITY" in ov._mode_chip.text()
    assert ov._crop_host.isVisible() is False
    ov.hide()


def test_crop_visible_in_camera(qtbot):
    item = _item("cam.png", metrics={"sharpness": 150.0})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item], mode=Mode.CAMERA)
    assert ov._crop_host.isVisible() is True
    ov.hide()


def test_refresh_metrics_signature():
    """Seam shape W2 codes against: ``refresh_metrics(self, item) -> None``."""
    assert list(inspect.signature(QuickLookOverlay.refresh_metrics).parameters) == [
        "self",
        "item",
    ]


def test_refresh_metrics_rebuilds_without_reopen(qtbot):
    """Fidelity delivery (W2) refreshes the open overlay: numbers, meta, brief."""
    src = _item("src.png", rank=0, metrics={})
    viewing = _item("v.png", rank=1, metrics={})
    second = _item("b.png", rank=2, metrics={"ssim": 0.91, "hf_ratio": -0.31})
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [src, viewing, second], source=src.path)
    before = [
        lbl.text()
        for row in ov._metric_rows
        for lbl in row.findChildren(type(ov._mode_chip))
    ]
    assert any("not measured" in t for t in before)
    # Fidelity delivery mutates metrics in place (service contract), then W2
    # calls refresh_metrics — the overlay shows numbers without reopening.
    viewing.metrics = {"ssim": 0.94, "hf_ratio": 0.18, "delta_e": 1.8, "upscale_factor": 4}
    ov.refresh_metrics(viewing)
    after = [
        lbl.text()
        for row in ov._metric_rows
        for lbl in row.findChildren(type(ov._mode_chip))
    ]
    assert any("0.94" in t for t in after)
    assert not any("not measured" in t for t in after)
    assert "upscale ×4" in ov._meta_label.text()
    assert ov._brief_label.text().startswith("vs #2:")
    assert ov._brief_label.isVisible()
    assert ov._crop_host.isVisible() is False
    ov.hide()


def test_refresh_metrics_noop_when_hidden(qtbot):
    viewing = _item("v.png", rank=1, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing])
    ov.hide()
    QApplication.processEvents()
    n_before = len(ov._metric_rows)
    viewing.metrics = {"ssim": 0.94, "hf_ratio": 0.18, "delta_e": 1.8, "upscale_factor": 4}
    ov.refresh_metrics(viewing)  # must not raise, must not rebuild
    assert len(ov._metric_rows) == n_before
    # The service wrote through to the item; the hidden overlay kept its rows.
    assert ov._current_item.metrics["ssim"] == 0.94


def test_refresh_metrics_ignores_other_item(qtbot):
    viewing = _item("v.png", rank=1, metrics={})
    other = _item("o.png", rank=2, metrics={"ssim": 0.5})
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, other])
    before = [
        lbl.text()
        for row in ov._metric_rows
        for lbl in row.findChildren(type(ov._mode_chip))
    ]
    ov.refresh_metrics(other)
    after = [
        lbl.text()
        for row in ov._metric_rows
        for lbl in row.findChildren(type(ov._mode_chip))
    ]
    # Path-guarded: another item's delivery changes nothing on the open card.
    assert after == before
    assert ov._current_item is viewing
    ov.hide()


# -- W3: strip regions / banding base / Find-Action set-source --------------


def _w3_png(path, color=(200, 30, 30)):
    from PIL import Image as _PIL

    _PIL.new("RGB", (64, 44), color).save(path)


def test_strip_thumbs_use_button_regions(qtbot, tmp_path):
    """Strip thumbs ride on ButtonRegion(pixmap, cover) — Button has no pixmap param."""
    p1 = tmp_path / "s1.png"
    p2 = tmp_path / "s2.png"
    _w3_png(p1)
    _w3_png(p2, (30, 200, 30))
    src = _item("s1.png")
    src.path = p1
    viewing = _item("s2.png")
    viewing.path = p2
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [src, viewing], source=src.path)
    from sli_ui_toolkit.widgets import Button

    buttons = [
        b for b in ov._strip_host.findChildren(Button) if b.objectName().startswith("quicklook_strip_")
    ]
    assert len(buttons) == 2
    for b in buttons:
        regions = b.regions()
        assert len(regions) == 1
        assert regions[0].pixmap is not None and not regions[0].pixmap.isNull()
        assert regions[0].image_fill == "cover"
    # Badge text preserved as badge overlays (W4 item 9): SOURCE on source,
    # #N on viewing — not Button text.
    by_path = {b.property("gallery_path"): b for b in buttons}
    assert by_path[str(p1)]._badge == "SOURCE"
    assert by_path[str(p2)]._badge == "#2"
    assert by_path[str(p1)]._text == ""
    ov.hide()


def test_strip_region_click_switches_preview(qtbot, tmp_path):
    p1 = tmp_path / "c1.png"
    p2 = tmp_path / "c2.png"
    _w3_png(p1)
    _w3_png(p2, (30, 30, 200))
    src = _item("c1.png")
    src.path = p1
    viewing = _item("c2.png")
    viewing.path = p2
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [src, viewing], source=src.path)
    assert ov._current_item.path == p2
    from sli_ui_toolkit.widgets import Button

    for b in ov._strip_host.findChildren(Button):
        if b.property("gallery_path") == str(p1):
            b.click()
            break
    QApplication.processEvents()
    assert ov._current_item.path == p1
    ov.hide()


def test_banding_base_visible_on_light(qtbot, _w1_light_palettes):
    """Banding base is a local mid-gray on light — not the #e1e1e1 token wash."""
    from PySide6.QtGui import QColor

    from tabs.image_gallery.ui.quick_look.histograms import (
        _BandingCombHistogram,
        _GenericHistogram,
        _base_fill,
        _container_bg,
    )

    base = _base_fill()
    bg = _container_bg()
    assert base == QColor("#8a8a8a")
    assert base != bg

    def _luma(c):
        return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()

    assert abs(_luma(base) - _luma(bg)) > 60
    comb = _BandingCombHistogram(severity="clean")
    qtbot.addWidget(comb)
    base_bars = [bar for bar, kind in comb._bars if kind == "base"]
    assert base_bars
    assert all(bar._color == base for bar in base_bars)
    gen = _GenericHistogram(severity="clean")
    qtbot.addWidget(gen)
    assert gen._bars
    assert all(bar._color == base for bar, _kind in gen._bars)


def test_find_action_set_as_source_reruns_fidelity(tmp_path):
    """Find-Action set-as-source routes through the hooks stale-keys + re-run path."""
    from tabs.image_gallery.actions import GALLERY_SET_AS_SOURCE
    from tabs.image_gallery.tab import ImageGalleryTab

    old_src = tmp_path / "old.png"
    new_src = tmp_path / "new.png"
    _w3_png(old_src)
    _w3_png(new_src, (30, 30, 200))
    fid = {"ssim": 0.9, "hf_ratio": 0.1, "delta_e": 0.5, "upscale_factor": 1}
    a = GalleryItem(path=old_src, mtime_ns=1, metrics=dict(fid))
    b = GalleryItem(path=new_src, mtime_ns=2, metrics=dict(fid))

    class _Ctrl:
        def __init__(self):
            self.state = SimpleNamespace(
                selected_paths={Path(new_src)},
                items=[a, b],
                source_path=Path(old_src),
                series=None,
                mode=None,
            )
            self.runs: list = []

        def _start_fidelity_analysis(self, items, source_path):
            self.runs.append((list(items), source_path))

    class _StripStub:
        def __init__(self):
            self.modes: list = []

        def set_mode(self, name, source):
            self.modes.append((name, source))

    class _OverlayStub:
        def __init__(self):
            self.refreshed: list = []

        def refresh_metrics(self, item):
            self.refreshed.append(item)

    ctrl = _Ctrl()
    overlay_stub = _OverlayStub()
    wid = SimpleNamespace(
        _controller=ctrl,
        _source_path=Path(old_src),
        _mode=None,
        stats_strip=_StripStub(),
        _quick_look_overlay=overlay_stub,
    )

    class _Registry:
        def __init__(self):
            self.items: list = []

        def register(self, descriptor):
            self.items.append(descriptor)
            return True

    tab = ImageGalleryTab()
    tab._controller = ctrl
    tab._widget = wid
    registry = _Registry()
    assert tab.create_service("contribute_actions", registry) is True
    descs = [d for d in registry.items if d.action_id == GALLERY_SET_AS_SOURCE]
    assert len(descs) == 1
    # Action id and UX identical — only the run path changed.
    assert descs[0].label_key == "image_gallery.action.set_as_source"
    descs[0].run()
    assert ctrl.state.source_path == Path(new_src)
    for it in (a, b):
        assert all(k not in it.metrics for k in ("ssim", "hf_ratio", "delta_e", "upscale_factor"))
    assert ctrl.runs == [([a, b], Path(new_src))]
    assert overlay_stub.refreshed == [a, b]


# -- W4 render fidelity -------------------------------------------------------


def test_right_column_scroll_frameless(qtbot):
    """W4 item 2: the right-column QScrollArea is frameless (no bogus box)."""
    from PySide6.QtWidgets import QFrame, QScrollArea

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    scroll = ov.findChild(QScrollArea, "quicklook_right_scroll")
    assert scroll is not None
    assert scroll.frameShape() == QFrame.Shape.NoFrame
    ov.hide()


def test_hint_at_right_end_of_button_bar(qtbot):
    """W4 item 4: the Esc hint is the last widget of the bottom bar row."""
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    bar = ov.findChild(QWidget, "quicklook_bottom_bar")
    assert bar is not None
    assert ov._hint_label.parentWidget() is bar
    lay = bar.layout()
    assert lay.itemAt(lay.count() - 1).widget() is ov._hint_label
    # Out of the left column.
    left = ov.findChild(QWidget, "QuickLookLeft")
    assert ov._hint_label not in left.findChildren(type(ov._hint_label))
    ov.hide()


def test_dividers_are_painted_widgets(qtbot):
    """W4 item 3: section dividers are real 1px painted widgets, no QSS."""
    from tabs.image_gallery.ui.quick_look.helpers import _RuleWidget

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    for name in ("quicklook_div_series", "quicklook_div_brief", "quicklook_div_bar"):
        div = ov.findChild(QWidget, name)
        assert isinstance(div, _RuleWidget), name
        assert div.styleSheet() == ""
        pm = div.grab()
        assert not pm.isNull()
    ov.hide()


def test_labels_render_at_mockup_point_sizes(qtbot):
    """W4 item 1: Labels render the mockup number as points (UiFont path)."""
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    assert ov._report_title.font().pointSizeF() == pytest.approx(13)
    assert ov._filename_label.font().pointSizeF() == pytest.approx(12)
    assert ov._mode_chip.font().pointSizeF() == pytest.approx(10)
    assert ov._hint_label.font().pointSizeF() == pytest.approx(10)
    assert ov._brief_label.font().pointSizeF() == pytest.approx(11.5)
    ov.hide()


def test_inset_caption_is_bottom_overlay_strip(qtbot):
    """W4 item 5: caption is an overlaid strip at the inset bottom, not a
    VBox label — full width, bottom edge, eliding."""
    src = _item("src.png", metrics={"width": 960, "height": 540})
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)
    QApplication.processEvents()
    host = ov._source_inset_host
    cap = ov._source_inset_caption
    assert cap.parentWidget() is host
    # Not managed by the host VBox layout.
    assert host.layout().indexOf(cap) == -1
    # Pinned to the inset bottom, full inset width.
    assert cap.y() + cap.height() == host.height()
    assert cap.width() == host.width()
    ov.hide()


def test_meta_same_size_when_factor_one(qtbot):
    """W4 item 7: fidelity meta reads an explicit same-size text when ×1."""
    src = _item("src.png", metrics={})
    item = _item("v.png", metrics={"upscale_factor": 1})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)
    assert "same size as source" in ov._meta_label.text()
    assert "upscale ×" not in ov._meta_label.text()
    ov.hide()


def test_upscale_factor_uses_long_side(tmp_path):
    """W4 item 7: portrait-safe — factor by LONG side, not width."""
    from tabs.image_gallery.services.fidelity_metrics import compute_fidelity_metrics

    src = tmp_path / "psrc.png"
    up = tmp_path / "pup.png"
    _noise_png(src, (32, 64), seed=11)
    _noise_png(up, (64, 128), seed=12)
    measured = compute_fidelity_metrics(up, src)
    assert measured["upscale_factor"] == 2
    # Square control still exact.
    s2 = tmp_path / "ssrc.png"
    u2 = tmp_path / "sup.png"
    _noise_png(s2, (64, 64), seed=13)
    _noise_png(u2, (64, 64), seed=14)
    assert compute_fidelity_metrics(u2, s2)["upscale_factor"] == 1


def test_strip_rejected_badge_is_x(qtbot, tmp_path):
    """W4 item 9: rejected thumbs carry the ✕ badge overlay, no text."""
    from sli_ui_toolkit.widgets import Button

    p1 = tmp_path / "r1.png"
    p2 = tmp_path / "r2.png"
    _w3_png(p1)
    _w3_png(p2, (30, 200, 30))
    viewing = _item("r1.png")
    viewing.path = p1
    rejected = _item("r2.png", rejected=True)
    rejected.path = p2
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [viewing, rejected])
    by_path = {
        b.property("gallery_path"): b
        for b in ov._strip_host.findChildren(Button)
        if b.objectName().startswith("quicklook_strip_")
    }
    assert by_path[str(p2)]._badge == "✕"
    assert by_path[str(p2)]._text == ""
    ov.hide()


# -- W5 fit + live xN --------------------------------------------------------


def _w5_solid_png(path, size, color=(10, 20, 30)):
    from PIL import Image as _PIL

    _PIL.new("RGB", size, color).save(path)


def test_upscale_factor_precap_long_side(tmp_path):
    """W5 item 1: factor divides PRE-CAP original long sides — the live ×1
    class (5760×4320 vs ~1100×432 reading 1) stays 5, plus a portrait pair."""
    from tabs.image_gallery.services.fidelity_metrics import compute_fidelity_metrics

    big = tmp_path / "big.png"
    small = tmp_path / "small.png"
    _w5_solid_png(big, (5760, 4320))
    _w5_solid_png(small, (1100, 432), (40, 50, 60))
    measured = compute_fidelity_metrics(big, small)
    assert measured["upscale_factor"] == 5
    # Portrait pair: long-side ratio, not width-only.
    psrc = tmp_path / "psrc.png"
    pup = tmp_path / "pup.png"
    _w5_solid_png(psrc, (540, 960))
    _w5_solid_png(pup, (1080, 1920), (40, 50, 60))
    assert compute_fidelity_metrics(pup, psrc)["upscale_factor"] == 2


def test_meta_smaller_than_source(tmp_path, qtbot):
    """W5 item 1b: factor 1 with a genuinely smaller item must not claim
    'same size as source' (the max(1, …) clamp hid downscales)."""
    small = tmp_path / "small.png"
    big = tmp_path / "big.png"
    _w5_solid_png(small, (64, 32))
    _w5_solid_png(big, (128, 128), (40, 50, 60))
    src = GalleryItem(path=big, mtime_ns=1, metrics={})
    item = GalleryItem(path=small, mtime_ns=2, metrics={"upscale_factor": 1})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)
    assert "smaller than source" in ov._meta_label.text()
    assert "same size as source" not in ov._meta_label.text()
    ov.hide()


def test_right_column_stretches_with_full_content(qtbot):
    """W5 item 3 + W7 + W13: full right column (metrics + 2 artifact rows +
    series + brief) fits the 1040×620 card with both scrollbars hidden
    (mockup: none). Value/subline labels elide to the live column width
    (floor 296px) instead of forcing width; the full copy stays in
    _original_text.

    W7 extends this with LIVE-like long content (supervisor offscreen
    repro: layout totalHint 379px vs 296px viewport — report_sub,
    series_sub and the banding caption hints forced h-scroll; elide
    paints truncated text but does NOT shrink QLabel.sizeHint, and
    minimum_width=40 only sets minimumSize). One-line elided labels now
    carry horizontal QSizePolicy.Ignored (layout reserves the minimum,
    not the hint), the right scroll is AlwaysOff horizontally, and the
    word-wrap brief pins its minimum width to the column so its
    minimumSizeHint is the height AT that width instead of the height
    at longest-word width (a 4px phantom v-scroll)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QScrollArea

    from sli_ui_toolkit.managers import scaled_px
    from sli_ui_toolkit.widgets import Button, Label

    src = _item("2x-Futsuu-Anime(1).png", metrics={})
    viewing = _item(
        "up1.png",
        rank=1,
        metrics={"ssim": 0.94, "hf_ratio": 0.18, "delta_e": 1.8, "upscale_factor": 2},
        artifacts={Artifact.BANDING: Severity.MILD},
    )
    second = _item("up2.png", rank=2, metrics={"ssim": 0.91})
    third = _item("up3.png", rank=3, metrics={"ssim": 0.83})
    third.rejected = True
    fourth = _item("up4.png", rank=4, metrics={"ssim": 0.80})
    mates = [viewing, second, third, fourth]
    ov = _make_overlay(qtbot)
    _show(ov, viewing, [[src], list(mates)], source=src.path)
    QApplication.processEvents()
    QApplication.processEvents()
    # Full content is really there.
    assert len(ov._metric_rows) >= 3
    assert len(ov._artifact_rows) == 2
    thumbs = [
        b for b in ov._strip_host.findChildren(Button) if b.objectName().startswith("quicklook_strip_")
    ]
    assert len(thumbs) == 4
    assert ov._brief_label.isVisible() and ov._brief_label.text()
    # W7 LIVE-long texts (verbatim full copies, painting elides them).
    assert ov._report_sub._original_text == "vs SOURCE 2x-Futsuu-Anime(1).png · shared/analysis engine"
    assert ov._series_sub._original_text == "4 upscales of one source · rank by fidelity · 1 rejected"
    sublines = [
        lbl._original_text
        for w in ov._metric_rows
        for lbl in w.findChildren(Label)
        if "rejected tail" in getattr(lbl, "_original_text", "")
    ]
    assert sublines == ["#2 scores 0.91 · rejected tail ≤ 0.83"]
    captions = [
        lbl._original_text
        for w in ov._artifact_rows
        for lbl in w.findChildren(Label)
        if "gradient histogram" in getattr(lbl, "_original_text", "")
    ]
    assert captions == ["gradient histogram — comb spikes = banding steps (sky)"]
    # W13: the column honors the mockup 296px floor and stretches with
    # the card (never a fixed width); the layout hint fits it, and both
    # scrollbars stay hidden with zero range.
    scroll = ov.findChild(QScrollArea, "quicklook_right_scroll")
    assert scroll.minimumWidth() == scaled_px(296)
    assert scroll.width() >= scaled_px(296)
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    host = ov.findChild(QWidget, "quicklook_right_host")
    # W13: under the stretched column the W7 invariant tracks the LIVE
    # width (wide bars report wide hints once laid out) — the hint must
    # still fit the column it is laid out in, never force it wider.
    assert host.layout().totalSizeHint().width() <= scroll.width()
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    assert scroll.horizontalScrollBar().isVisible() is False
    assert scroll.verticalScrollBar().isVisible() is False
    # Elide, not truncate: the full sub copy survives in _original_text.
    assert "shared/analysis engine" in ov._report_sub._original_text
    ov.hide()


# -- W6 strip fit + background-close -------------------------------------------


def test_strip_hint_below_thumbs_not_in_row(qtbot):
    """W6 item 1: the hint sits BELOW the thumb row (svg:170, y=588 under
    the 516..560 thumbs), not inside the strip HBox."""
    from sli_ui_toolkit.widgets import Label

    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    hint = ov.findChild(QWidget, "quicklook_strip_hint")
    assert hint is not None
    # Out of the strip HBox.
    assert ov._strip_layout.indexOf(hint) == -1
    assert hint.parentWidget() is not ov._strip_host
    # In the right column, directly after the strip host.
    assert hint.parentWidget() is ov._strip_host.parentWidget()
    parent_lay = hint.parentWidget().layout()
    assert parent_lay.indexOf(hint) == parent_lay.indexOf(ov._strip_host) + 1
    # Below the thumbs (same parent coords as the strip host).
    assert hint.y() >= ov._strip_host.y() + ov._strip_host.height()
    assert isinstance(hint, Label)
    assert hint.text() == "click thumb = switch preview"
    ov.hide()


def test_strip_four_thumbs_fit_296px_column(qtbot):
    """W6 item 2: 4 svg-pitch thumbs (4x66 + 3x10 = 294) fit the 296px
    column — no h-scroll, badge/click/dim behavior intact."""
    from PySide6.QtWidgets import QScrollArea

    from sli_ui_toolkit.managers import scaled_px
    from sli_ui_toolkit.widgets import Button

    items = [_item(f"{c}.png") for c in "abcd"]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    QApplication.processEvents()
    QApplication.processEvents()
    buttons = [
        b for b in ov._strip_host.findChildren(Button) if b.objectName().startswith("quicklook_strip_")
    ]
    assert len(buttons) == 4
    for b in buttons:
        assert b.width() == scaled_px(66)
    row = sum(b.width() for b in buttons) + 3 * scaled_px(10)
    assert row <= scaled_px(296)
    scroll = ov.findChild(QScrollArea, "quicklook_right_scroll")
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.horizontalScrollBar().isVisible() is False
    assert scroll.verticalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().isVisible() is False
    # Badge contract still holds at the new size.
    by_path = {b.property("gallery_path"): b for b in buttons}
    assert by_path["/gallery/a.png"]._badge == "#1"
    ov.hide()


def test_pinned_close_policy_x_only(qtbot):
    """W11 pinned policy (InfoHUD analog): X is the ONLY close path.

    Replaces the W6 Esc-close assertion — Esc, window deactivate/focus
    loss, and minimize/restore must all leave the card open.
    """
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    assert ov._close_on_background is False
    assert ov._close_on_escape is False
    assert ov._close_on_deactivate is False
    assert ov._hint_label.text() == "X closes · ←→ walk series"
    assert ov.isVisible() is True
    # Esc must NOT close.
    ov.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()
    assert ov.isVisible() is True
    # Window/focus loss must NOT close (deactivation filter is inert, and
    # no deferred dismiss is queued — flush the singleShot queue to prove it).
    window = ov.window()
    assert ov.eventFilter(window, QEvent(QEvent.Type.WindowDeactivate)) is False
    assert ov.eventFilter(window, QEvent(QEvent.Type.ApplicationDeactivate)) is False
    QApplication.processEvents()
    QApplication.processEvents()
    assert ov.isVisible() is True
    assert getattr(ov, "_dismissing", False) is False
    # Minimize/restore keeps the card (geometry follows the parent resize;
    # no hide path fires).
    parent = ov.parentWidget()
    parent.showMinimized()
    QApplication.processEvents()
    parent.showNormal()
    QApplication.processEvents()
    QApplication.processEvents()
    assert ov.isVisible() is True
    # X button path still closes.
    assert ov._close_btn is not None
    ov._close_btn.click()
    QApplication.processEvents()
    assert ov.isVisible() is False


def test_dblclick_open_survives_no_background_close(qtbot):
    """W6 item 3: grid dbl-click still opens quick look — the open path
    never depended on background-close (no test asserted a veil click)."""
    from PySide6.QtCore import QEvent

    from tabs.image_gallery.ui import quick_look_hooks as _hooks

    item = _item("d.png")
    ov = _make_overlay(qtbot)
    owner = SimpleNamespace(_items=[item], _quick_look_overlay=ov)
    watched = SimpleNamespace(_gallery_item=item)
    event = SimpleNamespace(type=lambda: QEvent.Type.MouseButtonDblClick)
    assert _hooks.event_filter(owner, watched, event) is True
    try:
        parent = ov.parentWidget()
        if parent is not None:
            parent.resize(1280, 800)
            parent.show()
    except Exception:
        pass
    QApplication.processEvents()
    assert ov.isVisible() is True
    assert ov._current_item is item
    ov.hide()


# -- W9 full-border resize + nav mockup paint ----------------------------------


def _w9_grab_stats(btn):
    """Offscreen grab census: fill samples, ring count, glyph dark core."""
    from PySide6.QtGui import QColor

    img = btn.grab().toImage()
    w, h = img.width(), img.height()

    def _px(x, y):
        c = img.pixelColor(x, y)
        return (c.red(), c.green(), c.blue(), c.alpha())

    ring = QColor("#d7dade")
    ring_n = sum(
        1
        for y in range(h)
        for x in range(w)
        if abs(img.pixelColor(x, y).red() - ring.red()) <= 8
        and abs(img.pixelColor(x, y).green() - ring.green()) <= 8
        and abs(img.pixelColor(x, y).blue() - ring.blue()) <= 8
    )
    # Glyph dark core (subpixel fringes excluded: strict luma floor).
    darks = [
        (x, y)
        for y in range(h)
        for x in range(w)
        if (lambda p: (p.red() + p.green() + p.blue()) // 3 < 100 and p.alpha() > 10)(
            img.pixelColor(x, y)
        )
    ]
    return _px, ring_n, darks, (w, h)


def test_nav_circles_mockup_fill_ring_centered_glyph(qtbot, _w1_light_palettes):
    """W9 arrows: mockup paint — #f1f2f4 disc, #d7dade ring, chevron on center.

    Execution diagnosis (offscreen grabs, light palettes): the W8 buttons
    rendered a #ffffff disc (surface default) with a ~#fdfdfd ring, and the
    glyph parked in the top half (dark rows y 8..13 of 36 — ButtonRow
    defaults to ratio=0.5). The veil hypothesis was REFUTED (nav buttons
    are _content children painted above the veil; fills grabbed pure).
    Fill now goes through set_override_bg_color (exact layer) with
    ratio=1.0 rows; the ring is the mockup #d7dade."""
    from PySide6.QtGui import QColor

    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    for btn in (ov._prev_btn, ov._next_btn):
        assert btn.isEnabled()
        # Exact override fill + explicit mockup ring (API values).
        assert btn._override_bg_color == QColor("#f1f2f4")
        assert btn.borderColor() == QColor("#d7dade")
        # Glyph row fills the button (ratio=1.0 centers it vertically).
        glyph_rows = [
            row.text
            for region in btn.regions()
            for row in (getattr(region, "rows", None) or [])
        ]
        assert glyph_rows
        for region in btn.regions():
            for row in (getattr(region, "rows", None) or []):
                assert row.ratio == pytest.approx(1.0)
        # Rendered pixels: mockup fill, visible ring, centered dark core.
        px, ring_n, darks, (w, h) = _w9_grab_stats(btn)
        assert px(18, 6)[:3] == (0xF1, 0xF2, 0xF4), px(18, 6)
        assert px(6, 18)[:3] == (0xF1, 0xF2, 0xF4), px(6, 18)
        assert ring_n > 30, ring_n
        assert len(darks) >= 5, len(darks)
        cx = sum(x for x, _y in darks) / len(darks)
        cy = sum(y for _x, y in darks) / len(darks)
        assert abs(cx - w / 2) <= 3, (cx, w)
        assert abs(cy - h / 2) <= 3, (cy, h)
    ov.hide()


def test_nav_circles_keep_ring_and_glyph_when_disabled(qtbot, _w1_light_palettes):
    """W9 arrows disabled: the ring survives (override-bg path keeps the
    explicit border in DISABLED — the derived-palette path early-returns
    with border=None and rendered a flat #e0e0e0 disc with no ring)."""
    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    for btn in (ov._prev_btn, ov._next_btn):
        btn.setEnabled(False)
        assert btn.borderColor() is not None
        px, ring_n, darks, _size = _w9_grab_stats(btn)
        assert px(18, 6)[:3] == (0xF1, 0xF2, 0xF4), px(18, 6)
        assert ring_n > 30, ring_n
        assert len(darks) >= 5, len(darks)
    ov.hide()


def test_resize_border_zones_and_cursors(qtbot):
    """W9 item 1: 8px strip on all 4 edges + 4 corners, 8 directions."""
    from PySide6.QtCore import QPoint, Qt

    from sli_ui_toolkit.managers import scaled_px
    from tabs.image_gallery.ui.quick_look import helpers as _ql_helpers

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    QApplication.processEvents()
    content = ov._content
    w, h = content.width(), content.height()
    assert (w, h) == (scaled_px(1040), scaled_px(620))
    assert _ql_helpers.RESIZE_BORDER_PX == 8
    strip = scaled_px(8)
    cases = {
        (strip // 2, h // 2): ("left", Qt.CursorShape.SizeHorCursor),
        (w - strip // 2 - 1, h // 2): ("right", Qt.CursorShape.SizeHorCursor),
        (w // 2, strip // 2): ("top", Qt.CursorShape.SizeVerCursor),
        (w // 2, h - strip // 2 - 1): ("bottom", Qt.CursorShape.SizeVerCursor),
        (strip // 2, strip // 2): ("top_left", Qt.CursorShape.SizeFDiagCursor),
        (w - strip // 2 - 1, strip // 2): ("top_right", Qt.CursorShape.SizeBDiagCursor),
        (strip // 2, h - strip // 2 - 1): ("bottom_left", Qt.CursorShape.SizeBDiagCursor),
        (w - strip // 2 - 1, h - strip // 2 - 1): ("bottom_right", Qt.CursorShape.SizeFDiagCursor),
        (w // 2, h // 2): (None, None),
    }
    for (x, y), (zone_exp, cursor_exp) in cases.items():
        zone = _ql_helpers.resize_zone_at(content, QPoint(x, y))
        assert zone == zone_exp, ((x, y), zone)
        assert _ql_helpers.resize_cursor_for(zone) == cursor_exp, zone
    # Hover affordance is cursor-only over a tracking plate — no QSS.
    assert content.hasMouseTracking() is True
    assert content.styleSheet() == ""
    ov.hide()


def _w9_mouse_event(kind, local, glob, button, buttons):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    return QMouseEvent(
        kind,
        QPointF(QPoint(*local)),
        QPointF(QPoint(*glob)),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def test_resize_border_hover_cursor_through_filter(qtbot):
    """W9 item 1: plain moves over the strip set the hover cursor via the
    overlay eventFilter; interior moves restore the arrow."""
    from PySide6.QtCore import QEvent, QPoint, Qt

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    QApplication.processEvents()
    content = ov._content
    w, h = content.width(), content.height()
    # W11: mid-height strip points can sit inside the nav circles (their
    # preview-band offset varies with layout) — ride the edge at a
    # proven nav-clear height instead.
    _ly = content.mapFrom(ov, QPoint(0, _ring_y_clear_of_nav(ov, content.geometry()))).y()

    def _move(x, y):
        glob = content.mapToGlobal(QPoint(x, y))
        assert (
            ov.eventFilter(
                content,
                _w9_mouse_event(
                    QEvent.Type.MouseMove, (x, y), (glob.x(), glob.y()),
                    Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                ),
            )
            is False
        )  # hover never consumes
        QApplication.processEvents()

    _move(4, _ly)
    assert content.cursor().shape() == Qt.CursorShape.SizeHorCursor
    _move(w // 2, 4)
    assert content.cursor().shape() == Qt.CursorShape.SizeVerCursor
    _move(4, 4)
    assert content.cursor().shape() == Qt.CursorShape.SizeFDiagCursor
    _move(w // 2, h // 2)
    assert content.cursor().shape() == Qt.CursorShape.ArrowCursor
    ov.hide()


def test_resize_border_drag_clamps_and_repins(qtbot):
    """W9 item 1: border drags clamp like the W8 grip (min 1040×620,
    overlay minus 16px margin), re-pin grip + nav, stay session-only."""
    from PySide6.QtCore import QEvent, QPoint, QSize, Qt

    from sli_ui_toolkit.managers import scaled_px

    src = _item("src.png", metrics={"width": 960, "height": 540})
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)
    QApplication.processEvents()
    QApplication.processEvents()
    content = ov._content
    base_geom = content.geometry()
    # W11: mid-height strip points can sit inside the nav circles (their
    # preview-band offset varies with layout) — drag from a proven
    # nav-clear height on the same edges instead.
    _ly = content.mapFrom(ov, QPoint(0, _ring_y_clear_of_nav(ov, content.geometry()))).y()

    def _press_move_release(lx, ly, dx, dy):
        start = content.mapToGlobal(QPoint(lx, ly))
        end = start + QPoint(dx, dy)
        press = _w9_mouse_event(
            QEvent.Type.MouseButtonPress, (lx, ly), (start.x(), start.y()),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        )
        consumed = ov.eventFilter(content, press)
        move = _w9_mouse_event(
            QEvent.Type.MouseMove, (lx + dx, ly + dy), (end.x(), end.y()),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
        )
        ov.eventFilter(content, move)
        release = _w9_mouse_event(
            QEvent.Type.MouseButtonRelease, (lx + dx, ly + dy), (end.x(), end.y()),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        )
        ov.eventFilter(content, release)
        QApplication.processEvents()
        return consumed

    w, h = content.width(), content.height()
    # Interior press is ignored (not consumed, no drag).
    assert _press_move_release(w // 2, h // 2, 100, 100) is False
    assert content.geometry() == base_geom
    assert getattr(ov, "_border_drag", None) is None
    # Right edge far past the window: clamped to overlay minus margin.
    # (W11: the strip point sits clear of the nav-circle band — presses
    # inside either arrow rect walk the series instead of dragging.)
    assert _press_move_release(w - 4, _ly, 1000, 0) is True
    margin = scaled_px(16)
    assert content.width() == ov.width() - margin * 2
    assert getattr(ov, "_border_drag", None) is None
    # Left edge drag rightwards shrinks with the opposite edge anchored.
    w2, right2 = content.width(), content.geometry().right()
    assert _press_move_release(4, _ly, 200, 0) is True
    assert content.width() < w2
    assert content.geometry().right() == right2
    # Far corner drag floors at the 1040×620 minimum.
    _press_move_release(4, 4, 3000, 3000)
    assert content.size() == QSize(scaled_px(1040), scaled_px(620))
    # Absolute children re-pinned: grip at the corner, nav on the edges
    # (W10 overlay coords — centers on the card left/right edges).
    assert ov._resize_grip.geometry().topLeft() == QPoint(
        content.width() - ov._resize_grip.width(),
        content.height() - ov._resize_grip.height(),
    )
    card = content.geometry()
    assert abs(ov._prev_btn.geometry().center().x() - card.x()) <= 2
    assert abs(ov._next_btn.geometry().center().x() - (card.x() + card.width())) <= 2
    ov.hide()


# -- W10 outer resize ring + arrows live --------------------------------------


def _w10_overlay_event(overlay, kind, local, button, buttons):
    """QMouseEvent in overlay-local coords with matching global pos."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    glob = overlay.mapToGlobal(QPoint(*local))
    return QMouseEvent(
        kind,
        QPointF(QPoint(*local)),
        QPointF(QPoint(glob.x(), glob.y())),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def _ring_y_clear_of_nav(overlay, card) -> int:
    """Overlay-y on the left/right ring bands, clear of both nav circles.

    W11: the 36px circles sit on the card edges at the preview-band
    center, whose offset varies with layout — fixed offsets are fragile,
    so scan candidates and prove the pick hits the ring, not an arrow.
    """
    from PySide6.QtCore import QPoint

    from tabs.image_gallery.ui.quick_look import helpers as _ql_helpers

    for y in (card.y() + 40, card.y() + card.height() - 40, card.y() + card.height() // 2):
        pts = (QPoint(card.x() - 4, y), QPoint(card.x() + card.width() + 4, y))
        if any(_ql_helpers.nav_button_at(overlay, p) is not None for p in pts):
            continue
        if _ql_helpers.ring_zone_at(overlay, pts[0]) != "left":
            continue
        if _ql_helpers.ring_zone_at(overlay, pts[1]) != "right":
            continue
        return y
    raise AssertionError("no nav-clear ring y")


def test_outer_ring_zones_and_cursors(qtbot):
    """W10 item 1: the 8px ring OUTSIDE the card hits all 8 zones; the
    interior, card children, and open veil hit nothing."""
    from PySide6.QtCore import QPoint, Qt

    from sli_ui_toolkit.managers import scaled_px
    from tabs.image_gallery.ui.quick_look import helpers as _ql_helpers

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    QApplication.processEvents()
    card = ov._content.geometry()
    assert _ql_helpers.RESIZE_BORDER_PX == 8
    strip = scaled_px(8)
    cx = card.x() + card.width() // 2
    cy = card.y() + card.height() // 2
    cases = {
        (card.x() - strip // 2, cy): ("left", Qt.CursorShape.SizeHorCursor),
        (card.x() + card.width() + strip // 2, cy): ("right", Qt.CursorShape.SizeHorCursor),
        (cx, card.y() - strip // 2): ("top", Qt.CursorShape.SizeVerCursor),
        (cx, card.y() + card.height() + strip // 2): ("bottom", Qt.CursorShape.SizeVerCursor),
        (card.x() - strip // 2, card.y() - strip // 2): ("top_left", Qt.CursorShape.SizeFDiagCursor),
        (card.x() + card.width() + strip // 2, card.y() - strip // 2): ("top_right", Qt.CursorShape.SizeBDiagCursor),
        (card.x() - strip // 2, card.y() + card.height() + strip // 2): ("bottom_left", Qt.CursorShape.SizeBDiagCursor),
        (card.x() + card.width() + strip // 2, card.y() + card.height() + strip // 2): ("bottom_right", Qt.CursorShape.SizeFDiagCursor),
        # Interior / card edge / open veil: no ring zone (W6 veil stays inert).
        (cx, cy): (None, None),
        (card.x() + 2, cy): (None, None),
        (max(0, card.x() - strip - 60), cy): (None, None),
        (5, 5): (None, None),
    }
    for (x, y), (zone_exp, cursor_exp) in cases.items():
        zone = _ql_helpers.ring_zone_at(ov, QPoint(x, y))
        assert zone == zone_exp, ((x, y), zone)
        assert _ql_helpers.resize_cursor_for(zone) == cursor_exp, zone
    ov.hide()


def test_outer_ring_hover_cursor_through_overlay(qtbot):
    """W10 item 1: plain moves over the outer ring set the hover cursor via
    the overlay mouseMove; open-veil moves restore the arrow."""
    from PySide6.QtCore import QEvent, Qt

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    QApplication.processEvents()
    card = ov._content.geometry()

    def _move(x, y):
        ov.mouseMoveEvent(
            _w10_overlay_event(
                ov, QEvent.Type.MouseMove, (x, y),
                Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            )
        )
        QApplication.processEvents()

    # W11: the mid-edge ring point at card center sits inside the prev
    # circle (arrows show the plain cursor) — hover rides the same edge
    # above the arrow band.
    _move(card.x() - 4, _ring_y_clear_of_nav(ov, card))
    assert ov.cursor().shape() == Qt.CursorShape.SizeHorCursor
    _move(card.x() + card.width() // 2, card.y() - 4)
    assert ov.cursor().shape() == Qt.CursorShape.SizeVerCursor
    _move(card.x() - 4, card.y() - 4)
    assert ov.cursor().shape() == Qt.CursorShape.SizeFDiagCursor
    _move(5, 5)
    assert ov.cursor().shape() == Qt.CursorShape.ArrowCursor
    ov.hide()


def test_outer_ring_drag_clamps_and_repins(qtbot):
    """W10 item 1: outer-ring drags clamp like the W9 plate drags (min
    1040×620, overlay minus 16px margin), re-pin grip + nav, stay
    session-only."""
    from PySide6.QtCore import QEvent, QPoint, QSize, Qt

    from sli_ui_toolkit.managers import scaled_px

    src = _item("src.png", metrics={"width": 960, "height": 540})
    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [src, item], source=src.path)
    QApplication.processEvents()
    QApplication.processEvents()

    def _press_move_release(lx, ly, dx, dy):
        from PySide6.QtCore import QPoint as _QPoint

        card = ov._content.geometry()
        base_right = card.right()
        press = _w10_overlay_event(
            ov, QEvent.Type.MouseButtonPress, (lx, ly),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        )
        ov.mousePressEvent(press)
        started = getattr(ov, "_border_drag", None) is not None
        move = _w10_overlay_event(
            ov, QEvent.Type.MouseMove, (lx + dx, ly + dy),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
        )
        ov.mouseMoveEvent(move)
        release = _w10_overlay_event(
            ov, QEvent.Type.MouseButtonRelease, (lx + dx, ly + dy),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        )
        ov.mouseReleaseEvent(release)
        QApplication.processEvents()
        return started, base_right

    content = ov._content
    card = content.geometry()
    # W11: the mid-edge ring points at card vertical center sit inside the
    # 36px nav circles — presses there walk the series (see W11 tests), so
    # the drag points ride the same edges clear of the arrow band.
    ring_y = _ring_y_clear_of_nav(ov, card)
    # Right ring far past the window: clamped to overlay minus margin.
    started, _ = _press_move_release(card.x() + card.width() + 4, ring_y, 1000, 0)
    assert started is True
    margin = scaled_px(16)
    assert content.width() == ov.width() - margin * 2
    assert getattr(ov, "_border_drag", None) is None
    # Left ring drag rightwards shrinks with the opposite edge anchored.
    card = content.geometry()
    w2 = content.width()
    started, right2 = _press_move_release(card.x() - 4, ring_y, 200, 0)
    assert started is True
    assert content.width() < w2
    assert content.geometry().right() == right2
    # Far corner drag floors at the 1040×620 minimum.
    card = content.geometry()
    _press_move_release(card.x() - 4, card.y() - 4, 3000, 3000)
    assert content.size() == QSize(scaled_px(1040), scaled_px(620))
    assert getattr(ov, "_border_drag", None) is None
    # Absolute children re-pinned: grip at the corner, nav on the edges.
    assert ov._resize_grip.geometry().topLeft() == QPoint(
        content.width() - ov._resize_grip.width(),
        content.height() - ov._resize_grip.height(),
    )
    card = content.geometry()
    assert abs(ov._prev_btn.geometry().center().x() - card.x()) <= 2
    assert abs(ov._next_btn.geometry().center().x() - (card.x() + card.width())) <= 2
    ov.hide()


def test_veil_plain_click_still_does_nothing(qtbot):
    """W10 item 1 / W6: owning the outer ring must NOT resurrect
    background-click close — a plain veil press (outside the ring) starts
    no drag, moves nothing, and leaves the overlay open."""
    from PySide6.QtCore import QEvent, Qt

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    QApplication.processEvents()
    assert ov.isVisible() is True
    card_before = ov._content.geometry()
    # Far veil (well outside the 8px ring).
    ov.mousePressEvent(
        _w10_overlay_event(
            ov, QEvent.Type.MouseButtonPress, (5, 5),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        )
    )
    QApplication.processEvents()
    assert getattr(ov, "_border_drag", None) is None
    assert ov._content.geometry() == card_before
    assert ov.isVisible() is True
    # Open veil beside the card (beyond the ring band).
    card = ov._content.geometry()
    cy = card.y() + card.height() // 2
    ov.mousePressEvent(
        _w10_overlay_event(
            ov, QEvent.Type.MouseButtonPress, (max(0, card.x() - 60), cy),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        )
    )
    QApplication.processEvents()
    assert getattr(ov, "_border_drag", None) is None
    assert ov._content.geometry() == card_before
    assert ov.isVisible() is True
    # A release with no drag is a no-op (not consumed).
    from tabs.image_gallery.ui.quick_look import helpers as _ql_helpers

    assert (
        _ql_helpers.handle_ring_release(
            ov,
            _w10_overlay_event(
                ov, QEvent.Type.MouseButtonRelease, (5, 5),
                Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
            ),
        )
        is False
    )
    ov.hide()


def _w10_live_nav_stats(overlay, btn):
    """Overlay-grab census inside the nav circle (r≤16): mockup fill, ring,
    glyph dark core. Circle corners are excluded — they show the veil
    through the round button's transparent corners."""
    img = overlay.grab().toImage()
    cc = btn.geometry().center()
    fills = ring = 0
    darks = []
    for y in range(cc.y() - 18, cc.y() + 19):
        for x in range(cc.x() - 18, cc.x() + 19):
            dist2 = (x - cc.x()) ** 2 + (y - cc.y()) ** 2
            if dist2 > 18 * 18:
                continue
            c = img.pixelColor(x, y)
            if dist2 <= 16 * 16:
                if abs(c.red() - 0xF1) <= 8 and abs(c.green() - 0xF2) <= 8 and abs(c.blue() - 0xF4) <= 8:
                    fills += 1
                if (c.red() + c.green() + c.blue()) // 3 < 100 and c.alpha() > 10:
                    darks.append((x, y))
            if abs(c.red() - 0xD7) <= 10 and abs(c.green() - 0xDA) <= 10 and abs(c.blue() - 0xDE) <= 10:
                ring += 1
    return fills, ring, darks, (cc.x(), cc.y())


def test_nav_circles_live_full_disc_centered_glyph(qtbot, _w1_light_palettes):
    """W10 item 2: at REAL geometry the circles paint whole — the outside
    half is mockup fill (was: pure veil, parent-clipped), the ring is
    visible, and the chevron dark core sits on center, enabled AND
    disabled (mockup: solid 36px, centered chevron, half-outside edge,
    visible ring in both states)."""
    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    QApplication.processEvents()
    card = ov._content.geometry()
    for enabled in (True, False):
        ov._prev_btn.setEnabled(enabled)
        ov._next_btn.setEnabled(enabled)
        QApplication.processEvents()
        for btn in (ov._prev_btn, ov._next_btn):
            fills, ring, darks, (ccx, ccy) = _w10_live_nav_stats(ov, btn)
            # Outside half paints the mockup disc (spot-check 9px outside
            # the card edge — the pixel that grabbed pure veil pre-W10).
            img = ov.grab().toImage()
            outside_x = card.x() - 9 if btn is ov._prev_btn else card.x() + card.width() + 9
            spot = img.pixelColor(
                max(0, min(img.width() - 1, outside_x)),
                max(0, min(img.height() - 1, ccy)),
            )
            assert (spot.red(), spot.green(), spot.blue()) == (0xF1, 0xF2, 0xF4), (
                enabled, btn.objectName(), (spot.red(), spot.green(), spot.blue()),
            )
            assert fills > 400, (enabled, btn.objectName(), fills)
            assert ring > 30, (enabled, btn.objectName(), ring)
            assert len(darks) >= 5, (enabled, btn.objectName(), len(darks))
            cx = sum(x for x, _y in darks) / len(darks)
            cy = sum(y for _x, y in darks) / len(darks)
            assert abs(cx - ccx) <= 4, (enabled, btn.objectName(), cx, ccx)
            assert abs(cy - ccy) <= 4, (enabled, btn.objectName(), cy, ccy)
    ov.hide()


# -- W11 arrows exempt + pinned policy + enlarged glyphs -----------------------


def test_nav_arrow_ring_press_walks_and_consumes_no_drag(qtbot):
    """W11 item 1: a press starting inside either arrow rect walks the
    series and is consumed — no border drag starts (arrows never drag)."""
    from PySide6.QtCore import QEvent, Qt

    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    assert ov._current_item.path == a.path
    nxt_c = ov._next_btn.geometry().center()
    ov.mousePressEvent(
        _w10_overlay_event(
            ov, QEvent.Type.MouseButtonPress, (nxt_c.x(), nxt_c.y()),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        )
    )
    QApplication.processEvents()
    assert ov._current_item.path == b.path
    assert getattr(ov, "_border_drag", None) is None
    assert ov.isVisible() is True
    # Prev walks back; the outer half of the circle (ring band) too.
    prev_c = ov._prev_btn.geometry().center()
    ov.mousePressEvent(
        _w10_overlay_event(
            ov, QEvent.Type.MouseButtonPress, (prev_c.x() - 12, prev_c.y()),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        )
    )
    QApplication.processEvents()
    assert ov._current_item.path == a.path
    assert getattr(ov, "_border_drag", None) is None
    assert ov.isVisible() is True
    ov.hide()


def test_nav_arrow_press_disabled_consumes_no_drag(qtbot):
    """W11 item 1: single-item series (disabled arrows) — the fall-through
    press inside the circle is still consumed, never a drag."""
    from PySide6.QtCore import QEvent, Qt

    from tabs.image_gallery.ui.quick_look import helpers as _ql_helpers

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    QApplication.processEvents()
    assert ov._prev_btn.isEnabled() is False
    assert ov._next_btn.isEnabled() is False
    prev_c = ov._prev_btn.geometry().center()
    assert (
        _ql_helpers.handle_ring_press(
            ov,
            _w10_overlay_event(
                ov, QEvent.Type.MouseButtonPress, (prev_c.x(), prev_c.y()),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            ),
        )
        is True
    )
    assert getattr(ov, "_border_drag", None) is None
    assert ov.isVisible() is True
    ov.hide()


def test_nav_arrow_plate_press_walks_and_consumes(qtbot):
    """W11 item 1: the plate filter excludes the arrow rects too — a
    content-local press mapping into the next circle walks + consumes."""
    from PySide6.QtCore import QEvent, QPoint, Qt

    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    content = ov._content
    nxt_c = ov._next_btn.geometry().center()
    local = content.mapFrom(ov, nxt_c)
    assert content.rect().contains(local)  # inner half overlaps the plate
    glob = content.mapToGlobal(QPoint(local.x(), local.y()))
    assert (
        ov.eventFilter(
            content,
            _w9_mouse_event(
                QEvent.Type.MouseButtonPress, (local.x(), local.y()), (glob.x(), glob.y()),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            ),
        )
        is True
    )
    QApplication.processEvents()
    assert ov._current_item.path == b.path
    assert getattr(ov, "_border_drag", None) is None
    ov.hide()


def test_nav_arrow_hover_shows_plain_cursor(qtbot):
    """W11 item 1: hovering either arrow shows the plain cursor, never a
    resize cursor (ring and plate paths)."""
    from PySide6.QtCore import QEvent, QPoint, Qt

    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    nxt_c = ov._next_btn.geometry().center()
    ov.mouseMoveEvent(
        _w10_overlay_event(
            ov, QEvent.Type.MouseMove, (nxt_c.x(), nxt_c.y()),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
        )
    )
    QApplication.processEvents()
    assert ov.cursor().shape() == Qt.CursorShape.ArrowCursor
    # Plate hover over the inner half: no resize cursor either.
    content = ov._content
    local = content.mapFrom(ov, nxt_c)
    glob = content.mapToGlobal(QPoint(local.x(), local.y()))
    assert (
        ov.eventFilter(
            content,
            _w9_mouse_event(
                QEvent.Type.MouseMove, (local.x(), local.y()), (glob.x(), glob.y()),
                Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            ),
        )
        is False
    )  # hover never consumes
    QApplication.processEvents()
    assert content.cursor().shape() == Qt.CursorShape.ArrowCursor
    ov.hide()


def test_nav_glyphs_enlarged_centered_both_states(qtbot, _w1_light_palettes):
    """W11 item 1: ‹ › rows size up (24pt), still centered, ring intact in
    both states; circles stay 36px."""
    from PySide6.QtGui import QColor

    from sli_ui_toolkit.managers import scaled_px
    from tabs.image_gallery.ui.quick_look.helpers import QUICK_LOOK_NAV_GLYPH_PT

    assert QUICK_LOOK_NAV_GLYPH_PT == 24
    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    QApplication.processEvents()
    for btn, glyph in ((ov._prev_btn, "‹"), (ov._next_btn, "›")):
        assert (btn.width(), btn.height()) == (scaled_px(36), scaled_px(36))
        assert btn._corner_radius_px == 18
        assert btn.styleSheet() == ""
        glyph_rows = [
            row for region in btn.regions() for row in (getattr(region, "rows", None) or [])
        ]
        assert [row.text for row in glyph_rows] == [glyph]
        assert all(row.ratio == pytest.approx(1.0) for row in glyph_rows)
        assert all(row.size == QUICK_LOOK_NAV_GLYPH_PT for row in glyph_rows)
    for enabled in (True, False):
        ov._prev_btn.setEnabled(enabled)
        ov._next_btn.setEnabled(enabled)
        QApplication.processEvents()
        for btn in (ov._prev_btn, ov._next_btn):
            assert btn.borderColor() == QColor("#d7dade")
            assert btn._override_bg_color == QColor("#f1f2f4")
            _px, ring_n, darks, (w, h) = _w9_grab_stats(btn)
            assert ring_n > 30, (enabled, ring_n)
            assert len(darks) >= 5, (enabled, len(darks))
            cx = sum(x for x, _y in darks) / len(darks)
            cy = sum(y for _x, y in darks) / len(darks)
            assert abs(cx - w / 2) <= 3, (enabled, cx, w)
            assert abs(cy - h / 2) <= 3, (enabled, cy, h)
    ov.hide()


# -- W12-A close semantics: navigating buttons dismiss, triage stays ---------


def test_compare_button_closes_overlay(qtbot):
    """W12-A: `Compare →` leaves for the compare flow — overlay dismisses."""
    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    assert ov.isVisible()
    ov._on_compare()
    QApplication.processEvents()
    assert ov.isHidden()


def test_multi_compare_button_closes_overlay(qtbot):
    """W12-A: `Add to Multi Compare` enters the compare flow (verified:
    compareRequested -> on_quick_compare -> carry_selected ->
    ImageCarryService.begin) — overlay dismisses."""
    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b])
    assert ov.isVisible()
    ov._on_multi()
    QApplication.processEvents()
    assert ov.isHidden()


def test_reject_button_stays_open(qtbot):
    """W12-A: `Reject` keeps triaging — overlay stays open."""
    a = _item("a.png")
    ov = _make_overlay(qtbot)
    _show(ov, a, [a])
    assert ov.isVisible()
    ov._on_reject()
    QApplication.processEvents()
    assert ov.isVisible()
    ov.hide()


def test_set_source_button_stays_open(qtbot):
    """W12-A: `Set as source` keeps triaging — overlay stays open."""
    a = _item("a.png")
    b = _item("b.png")
    ov = _make_overlay(qtbot)
    _show(ov, b, [a, b], mode=Mode.CAMERA)
    assert ov.isVisible()
    ov._on_set_source()
    QApplication.processEvents()
    assert ov.isVisible()
    ov.hide()
