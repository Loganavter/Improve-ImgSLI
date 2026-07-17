"""Performance page.

Render backend is platform-owned and always visible. Tab-specific performance
groups are contributed through ``SettingsRegistry.add_section_extra``.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy
from sli_ui_toolkit.widgets import ComboBox

from plugins.settings.registry import SettingsSection
from plugins.settings.search import SearchIndex, group
from ui.icon_manager import AppIcon

RENDER_BACKEND = group(
    "settings.render_backend",
    "settings.render_backend_label",
    "settings.render_backend_default",
    "settings.render_backend_opengl",
    "settings.render_backend_vulkan",
    "settings.render_backend_d3d11",
    "settings.render_backend_d3d12",
    "settings.render_backend_metal",
    "settings.render_backend_restart_hint",
)
SEARCH = SearchIndex.of(RENDER_BACKEND)


def build(dialog, p):
    dialog.page_perf, layout = dialog._create_scrollable_page()
    dialog._perf_layout = layout
    from plugins.settings.registry import get_settings_registry

    for extra in get_settings_registry().extras_for(
        "builtin.performance",
        getattr(dialog, "active_tab", None),
    ):
        extra(dialog, p)
    _build_render_backend_group(dialog, layout, p)
    dialog.pages_stack.addWidget(dialog.page_perf)


def _build_render_backend_group(dialog, layout, p):
    dialog.render_backend_group = RENDER_BACKEND.widget(dialog)
    row = QHBoxLayout()
    row.setContentsMargins(5, 5, 5, 5)
    dialog.lbl_rhi_backend = QLabel(
        RENDER_BACKEND.text(dialog, "settings.render_backend_label") + ":"
    )
    RENDER_BACKEND.tag_member(
        dialog.lbl_rhi_backend, "settings.render_backend_label"
    )
    dialog.combo_rhi_backend = ComboBox()
    RENDER_BACKEND.tag_combo(dialog.combo_rhi_backend)
    dialog.combo_rhi_backend.setMinimumWidth(180)
    dialog.combo_rhi_backend.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )

    all_options = [
        ("default", "settings.render_backend_default"),
        ("opengl", "settings.render_backend_opengl"),
        ("vulkan", "settings.render_backend_vulkan"),
        ("d3d11", "settings.render_backend_d3d11"),
        ("d3d12", "settings.render_backend_d3d12"),
        ("metal", "settings.render_backend_metal"),
    ]
    if sys.platform == "darwin":
        keep = {"default", "opengl", "metal", "vulkan"}
    elif sys.platform.startswith("win"):
        keep = {"default", "opengl", "d3d11", "d3d12", "vulkan"}
    else:
        keep = {"default", "opengl", "vulkan"}

    for value, key in all_options:
        if value not in keep:
            continue
        dialog.combo_rhi_backend.addItem(
            RENDER_BACKEND.text(dialog, key),
            userData=value,
        )
        RENDER_BACKEND.note_combo_option(dialog.combo_rhi_backend, key)
    idx = dialog.combo_rhi_backend.findData(p.rhi_backend or "default")
    if idx != -1:
        dialog.combo_rhi_backend.setCurrentIndex(idx)
    row.addWidget(dialog.lbl_rhi_backend)
    row.addWidget(dialog.combo_rhi_backend, 1)
    dialog.render_backend_group.add_layout(row)

    dialog.lbl_rhi_backend_hint = QLabel(
        RENDER_BACKEND.text(dialog, "settings.render_backend_restart_hint")
    )
    RENDER_BACKEND.tag_member(
        dialog.lbl_rhi_backend_hint, "settings.render_backend_restart_hint"
    )
    dialog.lbl_rhi_backend_hint.setWordWrap(True)
    dialog.render_backend_group.add_widget(dialog.lbl_rhi_backend_hint)

    layout.addWidget(dialog.render_backend_group)


SECTION = SettingsSection(
    section_id="builtin.performance",
    title_key="settings.optimization",
    icon=AppIcon.PLAY,
    build=build,
    owner_tab=None,
    order=30,
    action_description_key="action.settings.optimization_desc",
    search=SEARCH,
)
