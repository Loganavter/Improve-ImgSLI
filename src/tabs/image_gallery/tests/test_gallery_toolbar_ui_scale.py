"""UI-scale geometry for the gallery toolbar row + status/actions row.

Owner report 2026-10-19 (plan-live-appearance-fixes-2026-10-19): on the gallery
page the two top rows scaled inconsistently — one control scaled its inner text
but not itself, another never scaled at all, and a segmented group's outline
scaled while the children doubled. ``GalleryToolbar`` and ``StatsStrip``
resolved their cached design-px chrome (fixed row heights, filter width,
segmented container sizes, margins/spacing, the scanning spinner) once at build
with ``scaled_px()`` and never re-ran it on a live ``UiScale`` change.

Measured misfits (supervisor sweep, empty toolbar, factor 1.0 -> 1.5):
  - ``LoadingSpinner gallery_toolbar_spinner``: 16x16 -> 60x60 = 3.75x (DOUBLE);
  - ``Label gallery_toolbar_scanning``: 100x30 -> 100x30 = 1.00x (STALE).

Root cause (measured, not assumed): ``LoadingSpinner`` scales its own design-px
``SIZE_PX`` internally, so the toolbar's ``setFixedSize(scaled_px(16)...)``
double-resolved it (and lost to the spinner's own re-derive on the metrics bus).
The scanning ``Label`` was hidden, and a hidden widget is never laid out — its
``size()`` stayed Qt's 100x30 default instead of following the factor.

These tests build the REAL populated gallery widget offscreen. At factor 1.0
every assertion is a no-op, so the suite is green before and after on the
default factor — it is red only at factor > 1.0 pre-fix. Each snapshot is read
at the factor it was built with and destroyed before the next factor is set: an
ALIVE toolkit ``Button`` re-derives its ``size=`` live on a factor change, so
keeping two widgets around would compare stale snapshots.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from sli_ui_toolkit.managers import UiScale, scaled_px

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget

#: Design px of the toolbar / stats rows.
_ROW_H = 34
#: Design px of the folder picker and the tag-filter field.
_PICK = (132, 34)
_FILTER = (280, 34)
#: Design px of one segmented-switch segment and its pill.
_SEGMENT = (48, 28)
_CONTAINER = (106, 32)
#: Design px of the scanning spinner square.
_SPINNER = 16
#: Design px of the stats-strip action buttons (width is text-derived).
_ACTION_H = 24


@pytest.fixture(autouse=True)
def _restore_ui_scale():
    """Never leak a parametrized factor into later suites (process singleton)."""
    yield
    UiScale.get_instance().set_factor(1.0)


def _drain(qapp, frames: int = 6) -> None:
    """Spin real event-loop turns (``connect_ui_metrics`` coalesces on a zero-timer)."""
    for _ in range(frames):
        qapp.processEvents()
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()


def _items(n: int = 6) -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/img-{i:02d}.png"), mtime_ns=i + 1)
        for i in range(n)
    ]


def _build(factor: float, qapp, *, populate: bool = True) -> ImageGalleryWidget:
    """Build the real populated gallery widget at *factor*."""
    UiScale.get_instance().set_factor(factor)
    w = ImageGalleryWidget()
    w.resize(1400, 900)
    w.show()
    if populate:
        its = _items()
        w.rebuild_grid(its)
        w.set_triage([[its[0], its[1]], [its[2], its[3]]], "camera", None)
        w.stats_strip.set_rank_provenance("jev")
    _drain(qapp)
    return w


def _size(obj) -> tuple[int, int]:
    return (obj.width(), obj.height())


def _read(w: ImageGalleryWidget) -> dict[str, tuple[int, int] | int]:
    """Every number of the two rows, keyed by control."""
    tb = w.toolbar
    st = w.stats_strip
    return {
        "toolbar_h": tb.height(),
        "pick": _size(tb._pick_button),
        "filter": _size(tb._filter_edit),
        "sort_h": tb._sort_combo.height(),
        "domain_seg": _size(tb._domain_switch),
        "domain_seg_ai": _size(tb._domain_switch_ai),
        "domain_container": _size(tb._domain_switch_container),
        "view_seg": _size(tb._view_switch),
        "view_seg_list": _size(tb._view_switch_list),
        "view_container": _size(tb._view_switch_container),
        "spinner": _size(tb._spinner),
        "scanning_size": _size(tb._scanning_label),
        "scanning_hint": (
            tb._scanning_label.sizeHint().width(),
            tb._scanning_label.sizeHint().height(),
        ),
        "strip_h": st.height(),
        "keep": _size(st._keep_btn),
        "clean": _size(st._clean_btn),
        "compare": _size(st._compare_btn),
        "prefix": _size(st._stats_prefix_label),
        "redundant": _size(st._stats_redundant_label),
        "rank_prov": _size(st._rank_provenance_label),
    }


def _snapshot(factor: float, qapp, *, populate: bool = True) -> dict:
    w = _build(factor, qapp, populate=populate)
    try:
        return _read(w)
    finally:
        w.deleteLater()
        _drain(qapp, 2)


def _expected(design: tuple[int, int], factor: float) -> tuple[int, int]:
    return (int(scaled_px(design[0])), int(scaled_px(design[1])))


def _assert_scaled_once(
    name: str, base: tuple[int, int], scaled: tuple[int, int], factor: float
) -> None:
    """Require ``scaled`` == ``base`` * factor, never * factor**2 and never * 1."""
    for i, axis in enumerate(("x", "y")):
        b, s = base[i], scaled[i]
        if not b:
            continue
        ratio = s / b
        assert ratio != pytest.approx(1.0, abs=0.05), (
            f"{name}.{axis} did not scale: {b} -> {s} (ratio {ratio:.3f})"
        )
        assert abs(ratio - factor) < 0.09, (
            f"{name}.{axis} scaled wrong: {b} -> {s} (ratio {ratio:.3f}, "
            f"expected ~{factor:.2f}; factor^2 would be ~{factor ** 2:.2f})"
        )


# ---------------------------------------------------------------------------
# Build-time: every control follows the factor exactly once.
# ---------------------------------------------------------------------------

_TB_FIXED = (
    ("pick_button", "pick", _PICK),
    ("filter_edit", "filter", _FILTER),
    ("domain_container", "domain_container", _CONTAINER),
    ("view_container", "view_container", _CONTAINER),
    ("domain_segment", "domain_seg", _SEGMENT),
    ("domain_segment_ai", "domain_seg_ai", _SEGMENT),
    ("view_segment", "view_seg", _SEGMENT),
    ("view_segment_list", "view_seg_list", _SEGMENT),
)


def test_toolbar_fixed_controls_are_design_px_at_1_0(qapp) -> None:
    snap = _snapshot(1.0, qapp)
    for name, key, design in _TB_FIXED:
        assert snap[key] == design, (
            f"{name} at 1.0 is {snap[key]}, expected design {design}"
        )
    assert snap["toolbar_h"] == _ROW_H
    assert snap["sort_h"] == _ROW_H
    assert snap["spinner"] == (_SPINNER, _SPINNER)
    assert snap["scanning_size"] == snap["scanning_hint"], (
        "the scanning label is not participating in the layout"
    )


def test_toolbar_fixed_controls_scale_once_at_build(qapp) -> None:
    base = _snapshot(1.0, qapp)
    scaled = _snapshot(1.5, qapp)
    assert _expected(_PICK, 1.5) == (198, 51)  # sanity, not the assertion
    for name, key, design in _TB_FIXED:
        assert scaled[key] == _expected(design, 1.5), (
            f"{name} at 1.5 is {scaled[key]}, expected design*factor "
            f"{_expected(design, 1.5)} (design {design}; factor^2 would be "
            f"{(design[0] * 2, design[1] * 2)})"
        )
        _assert_scaled_once(name, base[key], scaled[key], 1.5)
    assert scaled["toolbar_h"] == int(scaled_px(_ROW_H)) == 51
    assert scaled["sort_h"] == 51


def test_spinner_is_design_px_scaled_once_at_build(qapp) -> None:
    """The measured misfit: 16x16 -> 60x60 (3.75x) instead of 16 -> 24.

    Pre-fix red: ``LoadingSpinner`` scales its own ``SIZE_PX`` internally, the
    toolbar pre-scaled a ``setFixedSize`` on top, and the two resolutions
    fought — ending at the spinner's default 40 design px (60 at 1.5).
    """
    base = _snapshot(1.0, qapp)["spinner"]
    scaled = _snapshot(1.5, qapp)["spinner"]
    assert base == (_SPINNER, _SPINNER)
    assert scaled == (24, 24), (
        f"spinner at 1.5 is {scaled}; double-plus drift measured pre-fix as 60x60"
    )


def test_scanning_label_is_laid_out_at_its_scaled_size(qapp) -> None:
    """The measured misfit: 100x30 -> 100x30 (stale).

    Pre-fix red: the label was hidden, so it was never laid out and kept Qt's
    100x30 default at every factor. Post-fix it stays in the layout (empty text
    is invisible) and reports its scaled size hint.
    """
    base = _snapshot(1.0, qapp)
    scaled = _snapshot(1.5, qapp)
    assert scaled["scanning_size"] != (100, 30), (
        "the scanning label kept Qt's un-laid-out default 100x30 — it is not "
        "participating in the layout"
    )
    assert scaled["scanning_size"] == scaled["scanning_hint"]
    _assert_scaled_once(
        "scanning_label", base["scanning_hint"], scaled["scanning_hint"], 1.5
    )


def test_status_row_controls_scale_once_at_build(qapp) -> None:
    base = _snapshot(1.0, qapp)
    scaled = _snapshot(1.5, qapp)
    assert scaled["strip_h"] == int(scaled_px(_ROW_H)) == 51
    for name in ("keep", "clean", "compare"):
        assert base[name][1] == _ACTION_H
        assert scaled[name][1] == int(scaled_px(_ACTION_H)) == 36
        _assert_scaled_once(name, base[name], scaled[name], 1.5)
    for name in ("prefix", "redundant", "rank_prov"):
        _assert_scaled_once(name, base[name], scaled[name], 1.5)


# ---------------------------------------------------------------------------
# Live: cached chrome re-derives on a UiScale change (no rebuild, no restart).
# ---------------------------------------------------------------------------


def test_toolbar_refollows_a_live_scale_change(qapp) -> None:
    """Pre-fix red: the row's cached design geometry stayed at the 1.0 px."""
    w = _build(1.0, qapp)
    try:
        before = _read(w)
        assert before["filter"] == _FILTER
        assert before["domain_container"] == _CONTAINER

        UiScale.get_instance().set_factor(1.5)
        _drain(qapp)
        after = _read(w)

        assert after["toolbar_h"] == 51
        assert after["filter"] == _expected(_FILTER, 1.5) == (420, 51)
        assert (
            after["domain_container"]
            == after["view_container"]
            == _expected(_CONTAINER, 1.5)
            == (159, 48)
        )
        assert after["spinner"] == (24, 24)
        _assert_scaled_once("filter", before["filter"], after["filter"], 1.5)
    finally:
        w.deleteLater()


def test_status_row_refollows_a_live_scale_change(qapp) -> None:
    """Pre-fix red: the strip stayed 34px and clipped its (scaled) labels."""
    w = _build(1.0, qapp)
    try:
        before = _read(w)
        assert before["strip_h"] == _ROW_H
        assert before["prefix"][1] == 20

        UiScale.get_instance().set_factor(1.5)
        _drain(qapp)
        after = _read(w)

        assert after["strip_h"] == 51
        assert after["prefix"][1] >= 29
        assert after["clean"][1] == 36
    finally:
        w.deleteLater()


def test_scanning_label_scales_live_once_text_is_set(qapp) -> None:
    """The user-visible scanning path: text resolves at use time on a live flip.

    (An *empty* toolkit ``Label``'s ``sizeHint`` does not re-derive on a live
    font change — a toolkit-internal quirk — but it draws nothing, so the
    visible path is ``set_scanning``, which must scale.)
    """
    w = _build(1.0, qapp)
    try:
        label = w.toolbar._scanning_label
        base_hint = label.sizeHint()

        UiScale.get_instance().set_factor(1.5)
        _drain(qapp)
        w.toolbar.set_scanning(3, 10)
        _drain(qapp)

        hint = label.sizeHint()
        assert hint.height() >= int(0.9 * scaled_px(base_hint.height()))
        assert hint.height() > base_hint.height()
    finally:
        w.deleteLater()

