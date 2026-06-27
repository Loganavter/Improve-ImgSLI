"""Performance page.

Render backend is platform-owned and always visible. Tab-specific performance
groups are contributed through ``SettingsRegistry.add_section_extra``.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy
from sli_ui_toolkit.widgets import ComboBox, CustomGroupWidget

from plugins.settings.registry import SettingsSection
from ui.icon_manager import AppIcon


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
    dialog.render_backend_group = CustomGroupWidget(
        dialog.tr("settings.render_backend", dialog.current_language)
    )
    row = QHBoxLayout()
    row.setContentsMargins(5, 5, 5, 5)
    dialog.lbl_rhi_backend = QLabel(
        dialog.tr("settings.render_backend_label", dialog.current_language) + ":"
    )
    dialog.combo_rhi_backend = ComboBox()
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
            dialog.tr(key, dialog.current_language),
            userData=value,
        )
    idx = dialog.combo_rhi_backend.findData(p.rhi_backend or "default")
    if idx != -1:
        dialog.combo_rhi_backend.setCurrentIndex(idx)
    row.addWidget(dialog.lbl_rhi_backend)
    row.addWidget(dialog.combo_rhi_backend, 1)
    dialog.render_backend_group.add_layout(row)

    dialog.lbl_rhi_backend_hint = QLabel(
        dialog.tr("settings.render_backend_restart_hint", dialog.current_language)
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
)
