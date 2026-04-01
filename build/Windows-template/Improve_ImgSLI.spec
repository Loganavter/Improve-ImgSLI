# -*- mode: python ; coding: utf-8 -*-

import importlib
import importlib.util
import os
from pathlib import Path

block_cipher = None

SPEC_DIR = Path(SPEC).resolve().parent
REPO_ROOT = SPEC_DIR.parents[1]
ICON_PATH = SPEC_DIR / "icons" / "icon.ico"
QT_RUNTIME_HOOK = SPEC_DIR / "pyi_rth_pyqt6_windows.py"
QT_CONF_PATH = SPEC_DIR / "qt.conf"
APP_NAME = "Improve_ImgSLI"


def collect_tree(source_dir, dest_dir, *, include_suffixes=None):
    source_path = Path(source_dir)
    if not source_path.exists():
        return []

    include_suffixes = None if include_suffixes is None else {suffix.lower() for suffix in include_suffixes}
    collected = []
    for file_path in source_path.rglob("*"):
        if not file_path.is_file():
            continue
        if include_suffixes is not None and file_path.suffix.lower() not in include_suffixes:
            continue
        relative_parent = file_path.relative_to(source_path).parent
        target_dir = Path(dest_dir) / relative_parent
        collected.append((str(file_path), str(target_dir).replace("\\", "/")))
    return collected


def find_pyqt6_root():
    try:
        pyqt6 = importlib.import_module("PyQt6")
        module_file = getattr(pyqt6, "__file__", None)
        if module_file:
            return Path(module_file).resolve().parent
    except Exception:
        pass

    spec = importlib.util.find_spec("PyQt6.QtCore")
    if spec and spec.origin:
        return Path(spec.origin).resolve().parent

    raise RuntimeError("Unable to locate installed PyQt6 files for Windows packaging.")


PYQT6_ROOT = find_pyqt6_root()
QT6_ROOT = PYQT6_ROOT / "Qt6"

APP_DATAS = [
    (str(REPO_ROOT / "src" / "resources"), "resources"),
    (str(REPO_ROOT / "src" / "shared_toolkit" / "resources"), "shared_toolkit/resources"),
    (str(REPO_ROOT / "src" / "shared_toolkit" / "ui" / "resources"), "shared_toolkit/ui/resources"),
    (str(REPO_ROOT / "src" / "plugins" / "export" / "resources"), "plugins/export/resources"),
    (str(REPO_ROOT / "src" / "plugins" / "settings" / "resources"), "plugins/settings/resources"),
    (str(REPO_ROOT / "src" / "plugins" / "video_editor" / "resources"), "plugins/video_editor/resources"),
    (str(REPO_ROOT / "src" / "plugins" / "help" / "resources"), "plugins/help/resources"),
    (str(QT_CONF_PATH), "."),
]

PYQT6_DATAS = []
PYQT6_DATAS.extend(collect_tree(QT6_ROOT / "plugins", "PyQt6/Qt6/plugins"))
PYQT6_DATAS.extend(collect_tree(QT6_ROOT / "translations", "PyQt6/Qt6/translations"))

PYQT6_BINARIES = []
PYQT6_BINARIES.extend(collect_tree(PYQT6_ROOT, "PyQt6", include_suffixes={".dll", ".pyd"}))
PYQT6_BINARIES.extend(collect_tree(QT6_ROOT / "bin", "PyQt6/Qt6/bin", include_suffixes={".dll"}))

APP_HIDDENIMPORTS = [
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtOpenGL",
    "PyQt6.QtOpenGLWidgets",
    "PyQt6.QtWidgets",
    "darkdetect",
    "desktop_notifier",
    "numpy",
    "markdown",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageChops",
    "PIL.ImageOps",
    "PIL.ImageStat",
    "PIL.PngImagePlugin",
    "skimage",
    "skimage.metrics",
    "skimage.feature",
    "skimage.util",
    "imagecodecs",
    "OpenGL",
    "OpenGL.GL",
    "core.bootstrap",
    "core.constants",
    "core.events",
    "core.main_controller",
    "core.plugin_coordinator",
    "core.theme",
    "core.store",
    "core.store_document",
    "core.store_operations",
    "core.store_settings",
    "core.store_viewport",
    "core.store_workspace",
    "core.session_blueprints",
    "core.session_manager",
    "core.plugin_system",
    "core.plugin_system.decorators",
    "core.plugin_system.event_bus",
    "core.plugin_system.interfaces",
    "core.plugin_system.lifecycle",
    "core.plugin_system.plugin",
    "core.plugin_system.registry",
    "core.plugin_system.settings",
    "core.plugin_system.ui_integration",
    "core.state_management",
    "core.state_management.actions",
    "core.state_management.dispatcher",
    "core.state_management.reducers",
    "domain.qt_adapters",
    "domain.types",
    "domain.workspace",
    "events.app_event_handler",
    "events.drag_drop_handler",
    "events.image_label_event_handler",
    "events.window_event_handler",
    "plugins.analysis",
    "plugins.analysis.controller",
    "plugins.analysis.plugin",
    "plugins.analysis.processing.channel_analyzer",
    "plugins.analysis.processing.differ",
    "plugins.analysis.processing.edge_detector",
    "plugins.analysis.processing.metrics",
    "plugins.analysis.services.metrics",
    "plugins.analysis.settings",
    "plugins.analysis.state",
    "plugins.comparison",
    "plugins.comparison.plugin",
    "plugins.comparison.session_controller",
    "plugins.comparison.use_cases.list_ops",
    "plugins.comparison.use_cases.loading",
    "plugins.comparison.use_cases.navigation",
    "plugins.export",
    "plugins.export.controller",
    "plugins.export.dialog",
    "plugins.export.models",
    "plugins.export.plugin",
    "plugins.export.presenter",
    "plugins.export.services.image_export",
    "plugins.export.settings",
    "plugins.export.state",
    "plugins.help",
    "plugins.help.dialog",
    "plugins.help.plugin",
    "plugins.layout",
    "plugins.layout.definitions",
    "plugins.layout.manager",
    "plugins.layout.plugin",
    "plugins.magnifier",
    "plugins.magnifier.plugin",
    "plugins.magnifier.settings",
    "plugins.magnifier.state",
    "plugins.settings",
    "plugins.settings.application_service",
    "plugins.settings.controller",
    "plugins.settings.dialog",
    "plugins.settings.manager",
    "plugins.settings.models",
    "plugins.settings.plugin",
    "plugins.settings.presenter",
    "plugins.video_editor",
    "plugins.video_editor.dialog",
    "plugins.video_editor.dialog_sections",
    "plugins.video_editor.model",
    "plugins.video_editor.plugin",
    "plugins.video_editor.presenter",
    "plugins.video_editor.preview_gl",
    "plugins.video_editor.services.editor",
    "plugins.video_editor.services.export",
    "plugins.video_editor.services.export_config",
    "plugins.video_editor.services.keyframes",
    "plugins.video_editor.services.playback",
    "plugins.video_editor.services.recorder",
    "plugins.video_editor.services.thumbnails",
    "plugins.video_editor.services.timeline",
    "plugins.video_editor.services.track_defs",
    "plugins.video_editor.widgets.timeline",
    "plugins.video_editor.widgets.timeline.interaction",
    "plugins.video_editor.widgets.timeline.layout",
    "plugins.video_editor.widgets.timeline.primitives",
    "plugins.video_editor.widgets.timeline.render",
    "plugins.video_editor.widgets.timeline.theme",
    "plugins.video_editor.widgets.timeline.viewport",
    "plugins.video_editor.widgets.timeline.widget",
    "plugins.viewport",
    "plugins.viewport.controller",
    "plugins.viewport.plugin",
    "plugins.viewport.state",
    "shared.image_processing",
    "shared.image_processing.drawing.magnifier_diff",
    "shared.image_processing.drawing.magnifier_drawer",
    "shared.image_processing.drawing.magnifier_layout",
    "shared.image_processing.drawing.magnifier_masks",
    "shared.image_processing.drawing.magnifier_strategies",
    "shared.image_processing.drawing.text_drawer",
    "shared.image_processing.pipeline",
    "shared.image_processing.progressive_loader",
    "shared.image_processing.qt_conversion",
    "shared.image_processing.rendering.base_frame",
    "shared.image_processing.rendering.context_factory",
    "shared.image_processing.rendering.geometry",
    "shared.image_processing.rendering.magnifier_renderer",
    "shared.image_processing.rendering.models",
    "shared.image_processing.rendering.overlays",
    "shared.image_processing.rendering.text_renderer",
    "shared.image_processing.resize",
    "shared_toolkit.core.logging",
    "shared_toolkit.ui.dialogs.dialog_helpers",
    "shared_toolkit.ui.gesture_resolver",
    "shared_toolkit.ui.icon_manager",
    "shared_toolkit.ui.managers.flyout_manager",
    "shared_toolkit.ui.managers.font_manager",
    "shared_toolkit.ui.managers.icon_manager",
    "shared_toolkit.ui.managers.theme_manager",
    "shared_toolkit.ui.overlay_layer",
    "shared_toolkit.ui.services.icon_service",
    "shared_toolkit.ui.widgets.atomic.button_group_container",
    "shared_toolkit.ui.widgets.atomic.button_painter",
    "shared_toolkit.ui.widgets.atomic.buttons",
    "shared_toolkit.ui.widgets.atomic.clickable_label",
    "shared_toolkit.ui.widgets.atomic.comboboxes",
    "shared_toolkit.ui.widgets.atomic.custom_button",
    "shared_toolkit.ui.widgets.atomic.custom_group_widget",
    "shared_toolkit.ui.widgets.atomic.custom_line_edit",
    "shared_toolkit.ui.widgets.atomic.fluent_checkbox",
    "shared_toolkit.ui.widgets.atomic.fluent_combobox",
    "shared_toolkit.ui.widgets.atomic.fluent_radio",
    "shared_toolkit.ui.widgets.atomic.fluent_slider",
    "shared_toolkit.ui.widgets.atomic.fluent_spinbox",
    "shared_toolkit.ui.widgets.atomic.fluent_switch",
    "shared_toolkit.ui.widgets.atomic.minimalist_scrollbar",
    "shared_toolkit.ui.widgets.atomic.numbered_toggle_icon_button",
    "shared_toolkit.ui.widgets.atomic.scrollable_icon_button",
    "shared_toolkit.ui.widgets.atomic.simple_icon_button",
    "shared_toolkit.ui.widgets.atomic.text_labels",
    "shared_toolkit.ui.widgets.atomic.toggle_icon_button",
    "shared_toolkit.ui.widgets.atomic.toggle_scrollable_icon_button",
    "shared_toolkit.ui.widgets.atomic.tool_button",
    "shared_toolkit.ui.widgets.atomic.tool_button_with_menu",
    "shared_toolkit.ui.widgets.atomic.tooltips",
    "shared_toolkit.ui.widgets.atomic.unified_icon_button",
    "shared_toolkit.ui.widgets.composite.base_flyout",
    "shared_toolkit.ui.widgets.composite.color_options_flyout",
    "shared_toolkit.ui.widgets.composite.color_settings_button",
    "shared_toolkit.ui.widgets.composite.drag_ghost_widget",
    "shared_toolkit.ui.widgets.composite.magnifier_visibility_flyout",
    "shared_toolkit.ui.widgets.composite.simple_options_flyout",
    "shared_toolkit.ui.widgets.composite.text_settings_flyout",
    "shared_toolkit.ui.widgets.composite.toast",
    "shared_toolkit.ui.widgets.composite.unified_flyout",
    "shared_toolkit.ui.widgets.composite.unified_flyout.delegate",
    "shared_toolkit.ui.widgets.composite.unified_flyout.model",
    "shared_toolkit.ui.widgets.composite.unified_flyout.overlay_list_view",
    "shared_toolkit.ui.widgets.composite.unified_flyout.panel",
    "shared_toolkit.ui.widgets.drag_drop_overlay",
    "shared_toolkit.ui.widgets.helpers.overlay_geometry",
    "shared_toolkit.ui.widgets.helpers.shadow_painter",
    "shared_toolkit.ui.widgets.helpers.underline_painter",
    "shared_toolkit.ui.widgets.list_items.rating_item",
    "shared_toolkit.ui.widgets.paste_direction_overlay",
    "shared_toolkit.utils.file_utils",
    "shared_toolkit.utils.paths",
    "shared_toolkit.workers.generic_worker",
    "services.io.image_loader",
    "services.system.clipboard",
    "services.system.notifications",
    "services.workflow.playlist",
    "ui.gesture_resolver",
    "ui.icon_manager",
    "ui.main_window",
    "ui.main_window_ui",
    "ui.managers.dialog_manager",
    "ui.managers.message_manager",
    "ui.managers.transient_ui_manager",
    "ui.managers.tray_manager",
    "ui.managers.ui_manager",
    "ui.onboarding",
    "ui.presenters.image_canvas.background",
    "ui.presenters.image_canvas.magnifier",
    "ui.presenters.image_canvas.results",
    "ui.presenters.image_canvas.signatures",
    "ui.presenters.image_canvas.view",
    "ui.presenters.main_window.connections",
    "ui.presenters.main_window.state",
    "ui.presenters.toolbar.connections",
    "ui.presenters.toolbar.orientation",
    "ui.presenters.toolbar.state",
    "ui.presenters.ui_update_batcher",
    "ui.store_bridge",
    "ui.widgets.gl_canvas",
    "ui.widgets.gl_canvas.render",
    "ui.widgets.gl_canvas.shaders",
    "ui.widgets.gl_canvas.state",
    "ui.widgets.gl_canvas.textures",
    "ui.widgets.gl_canvas.widget",
    "ui.widgets.video_session_widget",
    "utils.geometry",
    "utils.resource_loader",
    "workers.image_rendering_worker",
    "resources.translations",
]

a = Analysis(
    [str(REPO_ROOT / "src" / "__main__.py")],
    pathex=[str(REPO_ROOT), str(REPO_ROOT / "src")],
    binaries=PYQT6_BINARIES,
    datas=APP_DATAS + PYQT6_DATAS,
    hiddenimports=sorted(set(APP_HIDDENIMPORTS)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(QT_RUNTIME_HOOK)] if QT_RUNTIME_HOOK.exists() else [],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
