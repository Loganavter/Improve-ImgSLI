"""DOUBLE-mode flyout geometry — pure functions over the picker owner.

Split from ``layout.py`` per CODE_PATTERNS.md "thin owner + use_cases":
layout.py grew past the 500-line Audit-Meta limit after the Plan 1
double-geometry fix (BELOW = anchor.bottom + GAP when space suffices,
ABOVE otherwise; interrupted show animation snaps to end). The picker
mixin (``_UnifiedFlyoutBase``) keeps the instance state and exposes thin
delegators with the original method names — Plan 1 tests
(``test_double_flyout_geometry.py``) call them directly — while the
bodies live here as functions taking the picker as their first argument.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QRect

from ui.widgets.unified_list_picker.debug import double_geom_debug
from ui.widgets.unified_list_picker.common import (
    _UnifiedFlyoutBase,
    current_index_for_list,
    items_for_list,
)


def _r(rect: QRect) -> str:
    return f"({rect.x()},{rect.y()},{rect.width()}x{rect.height()})"


def sync_double_mode_button_state(
    picker: _UnifiedFlyoutBase, button1, button2
) -> None:
    list1 = items_for_list(picker._document(), 1)
    list2 = items_for_list(picker._document(), 2)
    idx1 = current_index_for_list(picker._document(), 1)
    idx2 = current_index_for_list(picker._document(), 2)

    def _label(items, idx: int) -> str:
        if not 0 <= idx < len(items):
            return ""
        item = items[idx]
        if isinstance(item, str):
            return item if item else "-----"
        name = getattr(item, "display_name", "") or ""
        if isinstance(name, str) and name.strip():
            return name
        path = getattr(item, "path", "") or ""
        stem = os.path.splitext(os.path.basename(path))[0] if path else ""
        return stem if stem and stem.strip(" .") else "-----"

    def _names(items) -> list:
        labels = []
        for item in items or []:
            if isinstance(item, str):
                labels.append(item if item else "-----")
                continue
            name = getattr(item, "display_name", "") or ""
            if isinstance(name, str) and name.strip():
                labels.append(name)
                continue
            path = getattr(item, "path", "") or ""
            stem = os.path.splitext(os.path.basename(path))[0] if path else ""
            labels.append(stem if stem and stem.strip(" .") else "-----")
        return labels

    items1 = _names(list1)
    items2 = _names(list2)
    text1 = _label(list1, idx1)
    text2 = _label(list2, idx2)
    if hasattr(button1, "updateState"):
        button1.updateState(len(list1), idx1, text=text1, items=items1)
    if hasattr(button2, "updateState"):
        button2.updateState(len(list2), idx2, text=text2, items=items2)


def resolve_double_mode_top(
    picker: _UnifiedFlyoutBase, button1, button2, geom1_content: QRect, geom2_content: QRect
) -> int:
    """Shared content height for DOUBLE mode, honoring the resolved top.

    Returns the shared height and shifts both content rects by the source
    delta so the united top lands on the resolved y (BELOW =
    anchor.bottom + GAP when space suffices, ABOVE otherwise) instead of
    sticking to the preferred below-y.
    """
    source_anchor = button1 if picker.source_list_num == 1 else button2
    source_panel = picker.panel_left if picker.source_list_num == 1 else picker.panel_right
    source_rect = geom1_content if picker.source_list_num == 1 else geom2_content
    resolved_y, shared_height = picker._resolve_content_y_and_height(
        source_anchor,
        source_rect.y(),
        max(geom1_content.height(), geom2_content.height()),
        source_panel,
    )
    dy = resolved_y - source_rect.y()
    if dy:
        geom1_content.translate(0, dy)
        geom2_content.translate(0, dy)
    return shared_height


def compute_double_mode_geometry(
    picker: _UnifiedFlyoutBase, button1, button2
) -> tuple[QRect, QRect, QRect]:
    left_size = picker._calc_panel_total_size(1)
    right_size = picker._calc_panel_total_size(2)
    double_geom_debug(
        "in anchors w1=%s w2=%s same=%s sizes l=%sx%s r=%sx%s "
        "cont_h l=%s r=%s n1=%s n2=%s",
        getattr(button1, "width", lambda: -1)(),
        getattr(button2, "width", lambda: -1)(),
        button1 is button2,
        left_size.width(),
        left_size.height(),
        right_size.width(),
        right_size.height(),
        picker.panel_left._container_height,
        picker.panel_right._container_height,
        len(picker.panel_left._items),
        len(picker.panel_right._items),
    )
    geom1_content = picker._calculate_ideal_geometry(
        button1, left_size, content_only=True
    )
    geom2_content = picker._calculate_ideal_geometry(
        button2, right_size, content_only=True
    )
    shared_height = resolve_double_mode_top(
        picker, button1, button2, geom1_content, geom2_content
    )
    if shared_height < max(
        picker.panel_left._container_height,
        picker.panel_right._container_height,
    ):
        picker.panel_left.recalculate_and_set_height(max_height=shared_height)
        picker.panel_right.recalculate_and_set_height(max_height=shared_height)
        left_size = picker._calc_panel_total_size(1)
        right_size = picker._calc_panel_total_size(2)
        geom1_content = picker._calculate_ideal_geometry(
            button1, left_size, content_only=True
        )
        geom2_content = picker._calculate_ideal_geometry(
            button2, right_size, content_only=True
        )
        shared_height = resolve_double_mode_top(
            picker, button1, button2, geom1_content, geom2_content
        )
    geom1_content.setHeight(shared_height)
    geom2_content.setHeight(shared_height)

    unified_content = geom1_content.united(geom2_content)
    final_unified_geom = picker._clamp_outer_rect(
        picker._outer_from_content_rect(unified_content),
        allow_resize=False,
    )
    double_geom_debug(
        "content g1=%s g2=%s united=%s shared_h=%s",
        _r(geom1_content),
        _r(geom2_content),
        _r(unified_content),
        shared_height,
    )
    clamped_content = final_unified_geom.adjusted(
        picker.SHADOW_RADIUS,
        picker.SHADOW_RADIUS,
        -picker.SHADOW_RADIUS,
        -picker.SHADOW_RADIUS,
    )
    delta = clamped_content.topLeft() - unified_content.topLeft()
    max_panel_height = max(1, clamped_content.height())
    if max_panel_height < max(
        picker.panel_left._container_height,
        picker.panel_right._container_height,
    ):
        picker.panel_left.recalculate_and_set_height(max_height=max_panel_height)
        picker.panel_right.recalculate_and_set_height(max_height=max_panel_height)
        geom1_content.setHeight(picker.panel_left._container_height)
        geom2_content.setHeight(picker.panel_right._container_height)
        unified_content = geom1_content.united(geom2_content)
        final_unified_geom = picker._clamp_outer_rect(
            picker._outer_from_content_rect(unified_content),
            allow_resize=True,
        )
        clamped_content = final_unified_geom.adjusted(
            picker.SHADOW_RADIUS,
            picker.SHADOW_RADIUS,
            -picker.SHADOW_RADIUS,
            -picker.SHADOW_RADIUS,
        )
        delta = clamped_content.topLeft() - unified_content.topLeft()
    geom1_content = QRect(
        geom1_content.x() + delta.x(),
        geom1_content.y() + delta.y(),
        geom1_content.width(),
        min(geom1_content.height(), max_panel_height),
    )
    geom2_content = QRect(
        geom2_content.x() + delta.x(),
        geom2_content.y() + delta.y(),
        geom2_content.width(),
        min(geom2_content.height(), max_panel_height),
    )
    panel1_local = QRect(
        geom1_content.x() - clamped_content.x(),
        geom1_content.y() - clamped_content.y(),
        geom1_content.width(),
        geom1_content.height(),
    )
    panel2_local = QRect(
        geom2_content.x() - clamped_content.x(),
        geom2_content.y() - clamped_content.y(),
        geom2_content.width(),
        geom2_content.height(),
    )
    double_geom_debug(
        "out final=%s cont=%s delta=(%s,%s) p1=%s p2=%s",
        _r(final_unified_geom),
        _r(clamped_content),
        delta.x(),
        delta.y(),
        _r(panel1_local),
        _r(panel2_local),
    )
    return panel1_local, panel2_local, final_unified_geom


def ensure_double_mode_scroll_behavior(picker: _UnifiedFlyoutBase) -> None:
    for panel in (picker.panel_left, picker.panel_right):
        if hasattr(panel, "scroll_area"):
            panel.scroll_area.setWidgetResizable(True)
