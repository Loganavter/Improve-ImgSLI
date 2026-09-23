"""Quick look (S4) design-parity regression tests.

Covers audit items S4-1, S4-2, S4-4, S4-5, S4-6, S4-7, S4-8, S4-9 against
design.md "Quick look report" + ui-mockup-v4-quicklook.svg.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from tabs.image_gallery.models import Artifact, GalleryItem, Mode, Severity
from tabs.image_gallery.ui.quick_look import (
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
