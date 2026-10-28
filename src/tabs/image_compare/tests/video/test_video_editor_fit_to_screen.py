"""Fit-to-screen idiom + video editor 720p fit.

Owner report (2026-10-28): "the video editor's minimum size is so large that
even 1680x1080 may not be enough; introduce an idiom so every window opens
within a 720p screen".

Two layers are pinned here:

* ``GeometryApplyPolicy.fit_screen`` (shared_toolkit layout_sizing) caps BOTH
  window dimensions to the target screen's ``availableGeometry()`` — the
  generic idiom every dialog opts into with one flag. ``False`` must stay
  byte-identical, so the same call on a small screen without the flag keeps
  the oversized minimum.
* the video editor's own content budget. A minimum height cannot fix an
  over-tall content: Qt raises the window back to the layout minimum after
  ``show()``, so the panes themselves shrink (compact settings density,
  timeline/bottom floors). Measured offscreen before the fix: content minimum
  730 px at UiScale 1.0 and 873 px at 1.25 against 680 available on 1280x720.

The screen is faked (``available`` / patched resolver) because the offscreen
platform reports 800x800; the real-editor tests build the actual dialog and
assert the whole window plus the two interactive panes land inside
1280x680. A window-only proof belongs to the supervisor (see DONE.md
``LIVE-PROOF WANTED``).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget

from shared_toolkit.ui import layout_sizing
from tests.helpers.drain_until_stable import drain_until_stable
from sli_ui_toolkit.managers import UiScale, scaled_px
from tabs.host_helpers import GeometryApplyPolicy, apply_dialog_geometry
from tabs.image_compare.plugins.video_editor import layout_geometry as video_geometry
from tabs.image_compare.plugins.video_editor.dialog.shell import VideoEditorDialog
from tabs.image_compare.plugins.video_editor.layout_geometry import (
    MIN_VIDEO_EDITOR_BOTTOM_CONTAINER_HEIGHT_PX,
    MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX,
    MIN_VIDEO_EDITOR_FIT_TIMELINE_HEIGHT_PX,
    MIN_VIDEO_EDITOR_PREVIEW_HEIGHT_PX,
    MIN_VIDEO_EDITOR_TIMELINE_HEIGHT_PX,
    VIDEO_EDITOR_INITIAL_HEIGHT_PX,
    VIDEO_EDITOR_INITIAL_WIDTH_PX,
    VIDEO_EDITOR_SETTINGS_STATIC_COMPACT_SPACING_PX,
    VIDEO_EDITOR_SETTINGS_STATIC_SPACING_PX,
    VIDEO_EDITOR_TOOLBAR_HEIGHT_PX,
    apply_top_row_geometry,
    compute_video_editor_fit,
)

#: A 1280x720 screen after the window manager reserves its panels — the
#: owner's target: "every window opens within 720p".
SMALL_SCREEN = (1280, 680)
#: A spacious screen: nothing may shrink there.
BIG_SCREEN = (1920, 1080)


class _FakePresenter:
    main_controller = None


class _FakeExportController:
    store = None
    presenter = _FakePresenter()


@pytest.fixture(autouse=True)
def _scale_one(qapp):
    UiScale.get_instance().set_factor(1.0)
    yield
    UiScale.get_instance().set_factor(1.0)


def _fake_screen(monkeypatch, size: tuple[int, int] | None):
    """Point both resolvers at ``size`` (``None`` = no screen at all)."""
    monkeypatch.setattr(
        layout_sizing, "screen_available_size", lambda widget=None: size
    )
    monkeypatch.setattr(
        video_geometry, "available_screen_size", lambda dialog=None: size
    )


def _destroy(dialog) -> None:
    """One close per dialog: ``WA_DeleteOnClose`` deletes during processEvents."""
    try:
        if dialog.isVisible():
            dialog.close()
        QApplication.processEvents()
    except RuntimeError:
        pass
    QApplication.processEvents()


def _build_editor(monkeypatch, screen, *, factor: float = 1.0) -> VideoEditorDialog:
    UiScale.get_instance().set_factor(factor)
    _fake_screen(monkeypatch, screen)
    dialog = VideoEditorDialog([], _FakeExportController(), None)
    return dialog


def _show(dialog) -> None:
    dialog.show()
    QApplication.processEvents()
    QApplication.processEvents()


# ---------------------------------------------------------------------------
# Generic idiom: GeometryApplyPolicy.fit_screen
# ---------------------------------------------------------------------------


def _apply(dialog: QWidget, *, fit_screen: bool, floor: int = 700) -> None:
    apply_dialog_geometry(
        dialog,
        1400,
        900,
        policy=GeometryApplyPolicy(
            minimum_floor=(0, floor),
            fit_screen=fit_screen,
        ),
    )


def test_fit_screen_caps_both_dimensions(monkeypatch):
    _fake_screen(monkeypatch, SMALL_SCREEN)
    dialog = QWidget()
    try:
        _apply(dialog, fit_screen=True)
        assert dialog.minimumSize().height() <= SMALL_SCREEN[1], (
            "the minimum itself must fit the screen — clamp both dimensions "
            "before setMinimumSize"
        )
        assert dialog.width() <= SMALL_SCREEN[0]
        assert dialog.height() <= SMALL_SCREEN[1]
    finally:
        dialog.deleteLater()


def test_fit_screen_caps_width_too(monkeypatch):
    _fake_screen(monkeypatch, (1024, 720))
    dialog = QWidget()
    try:
        _apply(dialog, fit_screen=True, floor=300)
        assert dialog.width() <= 1024
        assert dialog.height() <= 720
    finally:
        dialog.deleteLater()


def test_fit_screen_off_keeps_oversized_minimum(monkeypatch):
    """The pre-existing behaviour has to stay: no flag, no clamping."""
    _fake_screen(monkeypatch, SMALL_SCREEN)
    dialog = QWidget()
    try:
        _apply(dialog, fit_screen=False)
        assert dialog.minimumSize().height() == 700
        assert dialog.height() == 900
    finally:
        dialog.deleteLater()


def test_fit_screen_does_not_change_a_spacious_screen(monkeypatch):
    _fake_screen(monkeypatch, BIG_SCREEN)
    capped = QWidget()
    plain = QWidget()
    try:
        _apply(capped, fit_screen=True)
        _apply(plain, fit_screen=False)
        assert capped.minimumSize() == plain.minimumSize()
        assert capped.size() == plain.size()
    finally:
        capped.deleteLater()
        plain.deleteLater()


# ---------------------------------------------------------------------------
# Video editor: the content budget itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factor", [1.0, 1.25])
def test_editor_fits_720p(monkeypatch, factor):
    dialog = _build_editor(monkeypatch, SMALL_SCREEN, factor=factor)
    try:
        # Hidden (opening) size already inside the screen.
        assert dialog.width() <= SMALL_SCREEN[0]
        assert dialog.height() <= SMALL_SCREEN[1]

        _show(dialog)
        assert dialog.width() <= SMALL_SCREEN[0], (
            f"shown width {dialog.width()} exceeds {SMALL_SCREEN[0]} at {factor}"
        )
        assert dialog.height() <= SMALL_SCREEN[1], (
            f"shown height {dialog.height()} exceeds {SMALL_SCREEN[1]} at {factor}"
        )
        assert dialog.minimumSizeHint().height() <= SMALL_SCREEN[1]

        # Both interactive panes remain reachable and non-degenerate.
        assert dialog.toolbar_frame.isVisible()
        assert dialog.scroll_area.isVisible()
        assert dialog.scroll_area.height() >= dialog.scroll_area.minimumHeight()
        timeline_bottom = dialog.scroll_area.mapTo(
            dialog, QPoint(0, dialog.scroll_area.height())
        ).y()
        assert timeline_bottom <= dialog.height(), (
            "the timeline's bottom edge must stay inside the dialog"
        )
        assert dialog.scroll_area.minimumHeight() >= scaled_px(
            MIN_VIDEO_EDITOR_FIT_TIMELINE_HEIGHT_PX
        )
        # The preview keeps its design minimum: the settings panel is the
        # taller pane, so preview shrink never buys vertical room.
        assert dialog.preview_label.minimumHeight() == scaled_px(
            MIN_VIDEO_EDITOR_PREVIEW_HEIGHT_PX
        )
        # Inspector (settings panel) keeps room for its rows + export button.
        assert dialog.settings_panel.minimumHeight() > 0
        assert dialog.settings_panel.height() >= scaled_px(300)
    finally:
        _destroy(dialog)


def test_editor_fit_plan_is_screen_bounded(monkeypatch):
    dialog = _build_editor(monkeypatch, SMALL_SCREEN)
    try:
        fit = compute_video_editor_fit(dialog, available=SMALL_SCREEN)
        assert fit.shrink is True
        assert fit.fits_screen is True
        assert fit.available_height == SMALL_SCREEN[1]
        assert fit.dialog_min_height <= SMALL_SCREEN[1]
        assert fit.initial_height + 2 * video_geometry.VIDEO_EDITOR_CSD_BAND_PX <= (
            SMALL_SCREEN[1]
        )
        assert fit.initial_width <= SMALL_SCREEN[0]
        # Bottom pane = toolbar + timeline, and the timeline never collapses.
        assert fit.bottom_min_height == scaled_px(VIDEO_EDITOR_TOOLBAR_HEIGHT_PX) + (
            fit.timeline_min_height
        )
        assert fit.timeline_min_height >= scaled_px(
            MIN_VIDEO_EDITOR_FIT_TIMELINE_HEIGHT_PX
        )
        assert fit.timeline_min_height < scaled_px(
            MIN_VIDEO_EDITOR_TIMELINE_HEIGHT_PX
        )
        assert fit.compact_settings is True
    finally:
        _destroy(dialog)


def test_editor_compact_density_is_applied_on_a_short_screen(monkeypatch):
    dialog = _build_editor(monkeypatch, SMALL_SCREEN)
    try:
        assert dialog.settings_static_layout.spacing() == scaled_px(
            VIDEO_EDITOR_SETTINGS_STATIC_COMPACT_SPACING_PX
        )
    finally:
        _destroy(dialog)


# ---------------------------------------------------------------------------
# Spacious screens: the design values, unchanged
# ---------------------------------------------------------------------------


def test_spacious_screen_keeps_design_geometry(monkeypatch):
    dialog = _build_editor(monkeypatch, BIG_SCREEN)
    band = 2 * video_geometry.VIDEO_EDITOR_CSD_BAND_PX
    try:
        # Same opening size as before the fit existed: design px + CSD band.
        assert dialog.size().width() == scaled_px(VIDEO_EDITOR_INITIAL_WIDTH_PX) + band
        assert (
            dialog.size().height() == scaled_px(VIDEO_EDITOR_INITIAL_HEIGHT_PX) + band
        )
        assert dialog.minimumSize().height() == scaled_px(
            MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX
        )
        assert dialog.settings_panel.minimumHeight() == 0
        assert dialog.settings_static_layout.spacing() == scaled_px(
            VIDEO_EDITOR_SETTINGS_STATIC_SPACING_PX
        )
        assert dialog.preview_label.minimumHeight() == scaled_px(
            MIN_VIDEO_EDITOR_PREVIEW_HEIGHT_PX
        )
        assert dialog.scroll_area.minimumHeight() == scaled_px(
            MIN_VIDEO_EDITOR_TIMELINE_HEIGHT_PX
        )
        assert dialog.bottom_container.minimumHeight() == scaled_px(
            MIN_VIDEO_EDITOR_BOTTOM_CONTAINER_HEIGHT_PX
        )
    finally:
        _destroy(dialog)


def test_spacious_screen_plan_does_not_shrink(monkeypatch):
    dialog = _build_editor(monkeypatch, BIG_SCREEN, factor=1.25)
    try:
        fit = compute_video_editor_fit(dialog, available=BIG_SCREEN)
        assert fit.shrink is False
        assert fit.timeline_min_height == scaled_px(
            MIN_VIDEO_EDITOR_TIMELINE_HEIGHT_PX
        )
        assert fit.initial_width == scaled_px(VIDEO_EDITOR_INITIAL_WIDTH_PX)
        assert fit.initial_height == scaled_px(VIDEO_EDITOR_INITIAL_HEIGHT_PX)
    finally:
        _destroy(dialog)


def test_plan_without_a_screen_keeps_design_values(monkeypatch):
    dialog = _build_editor(monkeypatch, BIG_SCREEN)
    try:
        monkeypatch.setattr(
            video_geometry, "available_screen_size", lambda dialog=None: None
        )
        fit = compute_video_editor_fit(dialog)
        assert fit.shrink is False
        assert fit.available_height is None
        assert fit.dialog_min_height == scaled_px(MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX)
    finally:
        _destroy(dialog)


# ---------------------------------------------------------------------------
# A geometry re-pass must not fight the user's window
# ---------------------------------------------------------------------------


def test_repass_on_a_visible_dialog_does_not_resize(monkeypatch):
    dialog = _build_editor(monkeypatch, SMALL_SCREEN)
    try:
        _show(dialog)
        before = dialog.size()
        apply_top_row_geometry(dialog)
        QApplication.processEvents()
        assert dialog.size() == before
    finally:
        _destroy(dialog)


# ---------------------------------------------------------------------------
# The doctrine path: a dialog-shaped stub has no panes to fit
# ---------------------------------------------------------------------------


def test_stub_dialog_keeps_design_space_floor(monkeypatch):
    """No editor panes ⇒ no fit plan ⇒ the unscaled-by-screen design floor.

    This is the shape ``test_ic_chrome_px_follows_ui_scale`` pins at factor
    1.5 (900 px design floor): the fit must not silently retune a content
    minimum it did not measure.
    """
    _fake_screen(monkeypatch, (800, 800))
    UiScale.get_instance().set_factor(1.5)
    dialog = QWidget()
    dialog.settings_panel = QWidget(dialog)
    dialog.settings_static_container = None
    dialog.tabs = None
    dialog.btn_export = None
    try:
        apply_top_row_geometry(dialog)
        # The scale change above rides the coalesced UiMetrics channel; drain
        # it before reading geometry (tests/contracts drain guard).
        drain_until_stable(getter=lambda: dialog.minimumHeight())
        assert dialog.minimumHeight() == scaled_px(MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX)
    finally:
        dialog.deleteLater()


def test_fit_policy_only_enabled_when_the_plan_is_screen_bounded(monkeypatch):
    dialog = _build_editor(monkeypatch, BIG_SCREEN)
    try:
        spacious = compute_video_editor_fit(dialog, available=BIG_SCREEN)
        small = compute_video_editor_fit(dialog, available=SMALL_SCREEN)
        assert video_geometry.video_editor_geometry_policy(spacious).fit_screen is False
        assert video_geometry.video_editor_geometry_policy(small).fit_screen is True
    finally:
        _destroy(dialog)
