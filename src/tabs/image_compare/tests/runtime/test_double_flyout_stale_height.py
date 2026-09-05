"""DOUBLE-mode stale single-height guard (PLAN 1 fallback/protection).

Regression: ``showAsSingle(1)`` leaves each panel clamped to its own list's
natural height (panel min/max == natural). ``switchToDoubleMode`` computes
equal-height shared panel rects, but Qt silently clamps ``setGeometry`` to
the stale ``maximumHeight`` — the shorter panel never grows (e.g. 154 vs 82)
and, worse, the unchanged size emits no Resize event, so the virtual-list
controller never rebinds and rows stay frozen at the hidden-panel width,
huddled top-left.

Invariant under test: after ``showAsSingle(1) + switchToDoubleMode`` with
unequal lists, both panels synchronously take the shared height and both
row windows span the full content width (no event-loop pass required —
mid-drag there may be none before the user looks).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ui.widgets.unified_list_picker import UnifiedListPicker


def _make_picker(qapp):
    host = QWidget()
    host.resize(800, 600)
    left = QWidget(host)
    left.setGeometry(8, 200, 200, 34)
    right = QWidget(host)
    right.setGeometry(520, 200, 200, 34)
    host.show()
    qapp.processEvents()
    picker = UnifiedListPicker.create_double_list(
        host,
        left,
        right,
        left_items=["Alpha", "Beta", "Gamma", "Delta"],
        right_items=["One", "Two"],
    )
    picker.set_list_anchors(left, right)
    return host, left, right, picker


def _teardown(host, picker, qapp):
    picker.hide()
    picker.deleteLater()
    host.close()
    host.deleteLater()
    qapp.processEvents()


def test_switch_to_double_equalizes_stale_single_heights(qapp):
    host, left, right, picker = _make_picker(qapp)
    try:
        picker.showAsSingle(1, left)
        qapp.processEvents()
        assert (
            picker.panel_left._container_height
            != picker.panel_right._container_height
        ), "fixture needs unequal single-mode naturals"

        picker.switchToDoubleMode()

        # Synchronous: no processEvents between switch and assertions.
        left_geom = picker.panel_left.geometry()
        right_geom = picker.panel_right.geometry()
        assert left_geom.height() == right_geom.height()
        assert left_geom.height() == picker.panel_left._container_height
        assert right_geom.height() == picker.panel_right._container_height
        # Stale max clamps must have been relaxed to admit the shared height.
        # The scroll area admits the shared height minus the panel chrome
        # (own layout margins) — it must never overshoot the panel, or the
        # viewport stretches the content (dead band under the last row).
        assert picker.panel_left.maximumHeight() >= left_geom.height()
        assert picker.panel_right.maximumHeight() >= right_geom.height()
        for panel, geom in (
            (picker.panel_left, left_geom),
            (picker.panel_right, right_geom),
        ):
            margins = panel.layout_outer.contentsMargins()
            chrome = margins.top() + margins.bottom()
            assert panel.scroll_area.maximumHeight() >= geom.height() - chrome
    finally:
        _teardown(host, picker, qapp)


def test_switch_to_double_rows_take_full_width_synchronously(qapp):
    host, left, right, picker = _make_picker(qapp)
    try:
        picker.showAsSingle(1, left)
        qapp.processEvents()
        picker.switchToDoubleMode()

        # The hidden-while-single right panel bound its rows at the stale
        # narrow width; after the switch they must span the panel content
        # width immediately (x_margin on both sides), not huddle top-left.
        for panel in (picker.panel_left, picker.panel_right):
            x_margin = panel._controller._x_margin
            expected_width = panel.content_widget.width() - 2 * x_margin
            rows = panel._item_widgets()
            assert rows, "expected materialized rows"
            for row in rows:
                assert row.geometry().x() == x_margin
                assert row.geometry().width() == expected_width
    finally:
        _teardown(host, picker, qapp)
