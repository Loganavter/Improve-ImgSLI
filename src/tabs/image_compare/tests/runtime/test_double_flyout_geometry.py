"""DOUBLE-mode flyout geometry (PLAN 1B — geometry).

Invariant under test:
- content top == anchor.bottom + SINGLE_PANEL_GAP_Y when space below suffices
  (the panel must not drift upward);
- outer top == content top - SHADOW_RADIUS, symmetric with
  ``_apply_container_geometry`` (inverse ``adjusted(±SHADOW_RADIUS)``);
- interrupting the show animation via ``switchToDoubleMode`` lands the widget
  on the final end geometry synchronously, never on
  ``start_pos = end_pos - _drop_offset_px``.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ui.widgets.unified_list_picker import UnifiedListPicker
from ui.widgets.unified_list_picker.common import FlyoutMode


def _make_picker(qapp):
    host = QWidget()
    host.resize(800, 600)
    left = QWidget(host)
    left.setGeometry(50, 200, 200, 34)
    right = QWidget(host)
    right.setGeometry(350, 200, 200, 34)
    host.show()
    qapp.processEvents()
    picker = UnifiedListPicker.create_double_list(
        host,
        left,
        right,
        left_items=["Alpha", "Beta", "Gamma"],
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


def test_double_content_top_matches_anchor_gap(qapp):
    host, left, right, picker = _make_picker(qapp)
    try:
        picker.source_list_num = 1
        picker._is_simple_mode = False
        picker.mode = FlyoutMode.SINGLE_LEFT

        panel1_local, panel2_local, final = picker._compute_double_mode_geometry(
            left, right
        )
        gap = picker.SINGLE_PANEL_GAP_Y
        shadow = picker.SHADOW_RADIUS
        expected_content_top = left.geometry().bottom() + 1 + gap

        content = final.adjusted(shadow, shadow, -shadow, -shadow)
        assert content.top() == expected_content_top
        assert final.top() == expected_content_top - shadow
        # Panels sit at the top of the content area (no upward drift).
        assert panel1_local.y() == 0
        assert panel2_local.y() == 0
    finally:
        _teardown(host, picker, qapp)


def test_outer_container_shadow_inverse(qapp):
    host, left, right, picker = _make_picker(qapp)
    try:
        picker.source_list_num = 1
        picker._is_simple_mode = False
        picker.mode = FlyoutMode.SINGLE_LEFT

        _, _, final = picker._compute_double_mode_geometry(left, right)
        picker.setGeometry(final)
        picker._apply_container_geometry()

        shadow = picker.SHADOW_RADIUS
        assert picker.container_widget.geometry() == picker.rect().adjusted(
            shadow, shadow, -shadow, -shadow
        )
        # Round-trip: outer(content) then container(outer) restores content.
        content = final.adjusted(shadow, shadow, -shadow, -shadow)
        assert picker._outer_from_content_rect(content) == final
    finally:
        _teardown(host, picker, qapp)


def test_resolve_prefers_below_when_space_suffices(qapp):
    host, left, right, picker = _make_picker(qapp)
    try:
        picker.source_list_num = 1
        picker._is_simple_mode = False
        picker.mode = FlyoutMode.SINGLE_LEFT

        preferred_y = (
            left.geometry().y() + left.geometry().height() + picker.SINGLE_PANEL_GAP_Y
        )
        y, _height = picker._resolve_content_y_and_height(
            left, preferred_y, 120, picker.panel_left
        )
        assert y == preferred_y
    finally:
        _teardown(host, picker, qapp)


def test_switch_to_double_snaps_to_end_during_animation(qapp):
    host, left, right, picker = _make_picker(qapp)
    try:
        picker.showAsSingle(1, left)
        qapp.processEvents()
        assert picker._anim is not None

        start_pos = picker.pos()
        picker.switchToDoubleMode()
        qapp.processEvents()

        assert picker.mode == FlyoutMode.DOUBLE
        # In-flight animation is torn down, not left stopped mid-flight.
        assert picker._anim is None

        gap = picker.SINGLE_PANEL_GAP_Y
        shadow = picker.SHADOW_RADIUS
        expected_content_top = left.geometry().bottom() + 1 + gap
        content = picker.geometry().adjusted(shadow, shadow, -shadow, -shadow)
        assert content.top() == expected_content_top
        assert picker.geometry().top() == expected_content_top - shadow
        # Must not be stranded at the animation start (above the end).
        assert picker.geometry().top() == start_pos.y() + picker._drop_offset_px
    finally:
        _teardown(host, picker, qapp)
