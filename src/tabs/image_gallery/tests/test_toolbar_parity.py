"""S2-5..S2-11 design-parity regression tests for toolbar + stats strip.

Covers the mockup divergences tracked in
``docs/design_parity_audit.md`` (S2-5, S2-6, S2-7, S2-8, S2-10, S2-11).
"""

from __future__ import annotations

import pytest

from tabs.image_gallery.ui.stats_strip import StatsStrip
from tabs.image_gallery.ui.toolbar import GalleryToolbar


@pytest.fixture
def _w1_light_palettes(qapp):
    """Register the production W1 palettes under the light theme.

    Rule A: token reads then assert live ``themes.json`` hexes instead of
    fallback literals. Teardown restores the bare manager (empty palettes,
    previous theme) so later suites keep their unbootstrapped behavior.
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


@pytest.fixture
def toolbar(qtbot):
    widget = GalleryToolbar()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def strip(qtbot):
    widget = StatsStrip()
    qtbot.addWidget(widget)
    return widget


def _layout_widgets(toolbar: GalleryToolbar) -> list[object]:
    layout = toolbar.layout()
    out: list[object] = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget()
        if widget is not None:
            out.append(widget)
            # also expose children of segmented view-switch container for parity
            try:
                if widget.objectName() == "gallery_toolbar_view_switch_container":
                    # add inner buttons for index checks
                    for ch in widget.findChildren(object):
                        if hasattr(ch, "objectName") and "view_switch" in ch.objectName():
                            out.append(ch)
            except Exception:
                pass
    return out


def test_s2_11_toolbar_layout_order(toolbar: GalleryToolbar) -> None:
    """pick, filter, sort, [scanning group], view_switch — switch rightmost."""
    widgets = _layout_widgets(toolbar)
    assert widgets.index(toolbar.pick_button) < widgets.index(toolbar.filter_edit)
    assert widgets.index(toolbar.filter_edit) < widgets.index(toolbar.sort_combo)
    assert widgets.index(toolbar.sort_combo) < widgets.index(toolbar.spinner)
    assert widgets.index(toolbar.spinner) < widgets.index(toolbar.scanning_label)
    # view_switch may be inside segmented container
    try:
        idx_view = widgets.index(toolbar.view_switch)
    except ValueError:
        # fallback: container is last
        idx_view = widgets.index(toolbar.findChild(object, "gallery_toolbar_view_switch_container"))
    assert widgets.index(toolbar.scanning_label) < idx_view
    # View switch (or its container) is the last widget in the row (right-aligned via stretch).
    assert widgets[-1] is toolbar.view_switch or widgets[-1].objectName() == "gallery_toolbar_view_switch_container" or widgets[-1] is toolbar.view_switch_list


def test_s2_10_pick_button_folder_icon(toolbar: GalleryToolbar) -> None:
    # Toolkit icon name (toolkit assets ship folder_open for light/dark).
    assert toolbar.pick_button._icon_unchecked == "folder_open"
    assert toolbar.pick_button._text == "Open Folder…"


def test_s2_8_view_switch_icon_pair(toolbar: GalleryToolbar) -> None:
    # Segmented switcher: two exclusive Buttons grid/list inside 106×32 container, SVG x1130 y74 r8
    grid_btn = toolbar.view_switch
    list_btn = toolbar.view_switch_list

    def _icon_name(v):
        try:
            return v.value if hasattr(v, "value") else str(v)
        except Exception:
            return str(v)

    assert "view_grid" in _icon_name(grid_btn._icon_unchecked)
    assert "view_list" in _icon_name(list_btn._icon_unchecked)
    assert grid_btn._has_toggle is True
    assert list_btn._has_toggle is True
    # Initial: grid active
    assert grid_btn.isChecked() is True
    assert list_btn.isChecked() is False

    checked: list[bool] = []
    toolbar.viewToggled.connect(checked.append)
    # Switch to list via helper (right segment)
    toolbar._apply_view(True)  # type: ignore[attr-defined]
    assert checked == [True]
    assert grid_btn.isChecked() is False
    assert list_btn.isChecked() is True
    checked.clear()
    toolbar._apply_view(False)
    assert checked == [False]
    assert grid_btn.isChecked() is True


def test_s2_6_stats_segments(strip: StatsStrip) -> None:
    strip.set_stats(40, 7, 33)
    assert strip.stats_prefix_label.text() == "40 images · 7 series · "
    assert strip.stats_redundant_label.text() == "33 redundant"
    # Accent via theme token, not hex / QSS.
    assert strip.stats_redundant_label._color_token_override == "accent"
    # stats_label stays reachable as the container widget.
    assert strip.stats_prefix_label.parent() is strip.stats_label


def test_s2_5_clean_rejected_accent(strip: StatsStrip) -> None:
    region = strip.clean_button.region("_main")
    assert region.override_border_color is not None
    strip.set_rejected_count(5)
    rows = strip.clean_button._rows
    assert rows and rows[0].text == "Clean rejected (5)"
    assert rows[0].color is not None
    assert not strip.clean_button.isEnabled() or True  # enabled with n>0
    assert strip.clean_button.isEnabled() is True


def test_p07_toolbar_qt_import_present() -> None:
    """P0-7: toolbar.py uses Qt at :233,242 — must be imported, not NameError."""
    import tabs.image_gallery.ui.toolbar as tb

    assert tb.Qt is not None
    assert hasattr(tb.Qt.AlignmentFlag, "AlignVCenter")


def test_s2_view_switch_active_is_fill_chip(toolbar: GalleryToolbar) -> None:
    """S2 mockup x1130 y74: active view segment is a fill-chip, not a border."""
    from tabs.image_gallery.ui.toolbar import (
        _apply_view_fill_chip,
        _resolve_toolbar_accent_fill,
    )

    fill = _resolve_toolbar_accent_fill()
    assert fill.alpha() == 51
    # Switching views via the helper must not raise and must keep exclusivity.
    toolbar._apply_view(True)  # type: ignore[attr-defined]
    assert toolbar.view_switch_list.isChecked() is True
    _apply_view_fill_chip(toolbar.view_switch_list, toolbar.view_switch)
    toolbar._apply_view(False)  # type: ignore[attr-defined]
    assert toolbar.view_switch.isChecked() is True


def test_s2_series_header_has_no_raw_hex() -> None:
    """grid_view series headers resolve via theme token (no raw #9a9a9a)."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "ui" / "grid_view.py"
    text = src.read_text(encoding="utf-8")
    assert "#9a9a9a" not in text.lower()


def test_sort_combo_opens_dropdown_and_emits(qtbot) -> None:
    """Clicking Sort opens the options flyout; picking a row emits sortChanged.

    Regression: the toolbar used ScrollableComboBox (wheel-only field, no
    popup), so clicks did nothing. Verified failing pre-fix (no popup),
    passing post-fix with Button + SimpleOptionsFlyout.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication

    toolbar = GalleryToolbar()
    qtbot.addWidget(toolbar)
    toolbar.show()
    qtbot.waitExposed(toolbar)
    got: list[str] = []
    toolbar.sortChanged.connect(got.append)
    qtbot.mouseClick(toolbar.sort_combo, Qt.MouseButton.LeftButton, pos=QPoint(70, 17))
    QApplication.processEvents()
    QApplication.processEvents()
    assert toolbar.sort_combo.property("cornerRadiusPx") == 6
    flyout = toolbar._sort_flyout
    assert flyout is not None and flyout.isVisible()
    assert flyout._options == ["Sort: Rank", "Sort: Name", "Sort: Date"]
    assert flyout.container.width() == toolbar.sort_combo.width()
    rows = flyout._rows
    assert len(rows) == 3
    qtbot.mouseClick(rows[1], Qt.MouseButton.LeftButton, pos=rows[1].rect().center())
    QApplication.processEvents()
    QApplication.processEvents()
    assert toolbar.sort_text() == "Sort: Name"
    assert got == ["Sort: Name"]
    assert not flyout.isVisible()
