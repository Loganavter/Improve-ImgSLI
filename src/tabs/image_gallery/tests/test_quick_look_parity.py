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


# -- S4-4: clean rows are hidden, empty section collapses --------------------


def test_clean_artifacts_hidden_section_collapsed(qtbot):
    item = _item("c.png", artifacts={}, metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    assert ov._artifact_rows == []
    assert not ov._artifacts_host.isVisibleTo(ov._artifacts_host.parentWidget())
    ov.hide()


def test_non_clean_artifact_rows_shown(qtbot):
    item = _item(
        "d.png",
        artifacts={
            Artifact.BANDING: Severity.MILD,
            Artifact.BLOCKING: Severity.CLEAN,
            Artifact.HALO: Severity.FLAGGED,
        },
        metrics={},
    )
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    assert len(ov._artifact_rows) == 2
    assert ov._artifacts_host.isVisibleTo(ov._artifacts_host.parentWidget())
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
    text = ov._source_inset_label.text()
    assert text.startswith("SOURCE · src.png")
    assert "960×540" in text
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


def test_card_geometry_1040x620(qtbot):
    """S4 mockup panel is 1040x620 (svg:31) — floor, not a suggestion."""
    from sli_ui_toolkit.managers import scaled_px

    ov = _make_overlay(qtbot)
    assert ov._content.minimumSize() == QSize(scaled_px(1040), scaled_px(620))
    assert ov._content.maximumSize() == QSize(scaled_px(1040), scaled_px(620))
    assert ov.sizeHint() == QSize(scaled_px(1040), scaled_px(620))


def test_prev_next_36px_circular_at_preview_edges(qtbot):
    """Prev/next: 36px circular buttons flanking the preview host (svg:67-70)."""
    from sli_ui_toolkit.managers import scaled_px

    item = _item("v.png", metrics={})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
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
    # Outer edges: prev left of the preview host, next right of it.
    assert ov._prev_btn.x() + ov._prev_btn.width() <= host.x()
    assert ov._next_btn.x() >= host.x() + host.width()
    # Vertically centered on the preview band.
    for btn in (ov._prev_btn, ov._next_btn):
        cy = btn.y() + btn.height() // 2
        assert host.y() <= cy <= host.y() + host.height()
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
