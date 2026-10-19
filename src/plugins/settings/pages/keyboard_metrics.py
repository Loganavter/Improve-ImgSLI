"""Keyboard page design px: resolved at use time, re-resolved on a scale change.

Split out of ``plugins/settings/pages/keyboard.py`` (file-size policy, see
``tests/contracts/test_file_size_policy.py``). The page is built once per
settings dialog and none of its spacings re-derived before this module
existed: a live ``UiScale`` change left every row pitch at the factor the page
was built with (plan ``plan-live-appearance-fixes-2026-10-19``).
"""

from __future__ import annotations

#: Design px of the page chrome. ``keyboard.build`` resolves them through
#: ``scaled_px`` at build; ``apply_design_metrics`` re-resolves them live.
GROUPS_SPACING_PX = 10
GROUP_BODY_MARGIN_V_PX = 4
GROUP_BODY_SPACING_PX = 4
ROW_SPACING_PX = 8


def apply_design_metrics(dialog) -> None:
    """Re-resolve the keyboard page's design px at the live scale factor."""
    from sli_ui_toolkit.managers import scaled_px

    groups_layout = getattr(dialog, "_keyboard_groups_layout", None)
    if groups_layout is not None:
        groups_layout.setSpacing(scaled_px(GROUPS_SPACING_PX))

    for group_layout in getattr(dialog, "_keyboard_group_layouts", ()) or ():
        group_layout.setContentsMargins(
            0,
            scaled_px(GROUP_BODY_MARGIN_V_PX),
            0,
            scaled_px(GROUP_BODY_MARGIN_V_PX),
        )
        group_layout.setSpacing(scaled_px(GROUP_BODY_SPACING_PX))

    for row, _group, _entry in getattr(dialog, "_keyboard_filter_rows", ()) or ():
        row_layout = row.layout()
        if row_layout is not None:
            row_layout.setSpacing(scaled_px(ROW_SPACING_PX))


def connect_design_metrics(dialog) -> None:
    """Own the page's design px on the unified metrics channel (scale axis)."""
    page = getattr(dialog, "page_keyboard", None)
    if page is None:
        return

    from sli_ui_toolkit.ui.managers import connect_ui_metrics
    from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE

    connect_ui_metrics(
        page,
        lambda *_args: apply_design_metrics(dialog),
        axes=frozenset({AXIS_SCALE}),
    )
