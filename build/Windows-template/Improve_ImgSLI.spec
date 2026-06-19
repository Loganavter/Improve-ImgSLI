# -*- mode: python ; coding: utf-8 -*-

import importlib
import importlib.util
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

SPEC_DIR = Path(SPEC).resolve().parent
REPO_ROOT = SPEC_DIR.parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
ICON_PATH = SPEC_DIR / "icons" / "icon.ico"
QT_RUNTIME_HOOK = SPEC_DIR / "pyi_rth_pyside6_windows.py"
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


def collect_resource_dirs(root_dir, dest_prefix):
    root_path = Path(root_dir)
    if not root_path.exists():
        return []

    collected = []
    for resource_dir in sorted(root_path.rglob("resources")):
        if not resource_dir.is_dir():
            continue
        relative_dir = resource_dir.relative_to(root_path)
        target_dir = str(Path(dest_prefix) / relative_dir).replace("\\", "/")
        collected.append((str(resource_dir), target_dir))
    return collected


def collect_project_submodules(package_names):
    collected = []
    for package_name in package_names:
        package_spec = importlib.util.find_spec(package_name)
        if package_spec is None or package_spec.submodule_search_locations is None:
            continue
        collected.extend(collect_submodules(package_name))
    return collected


def find_pyside6_root():
    try:
        pyside6 = importlib.import_module("PySide6")
        module_file = getattr(pyside6, "__file__", None)
        if module_file:
            return Path(module_file).resolve().parent
    except Exception:
        pass

    spec = importlib.util.find_spec("PySide6.QtCore")
    if spec and spec.origin:
        return Path(spec.origin).resolve().parent

    raise RuntimeError("Unable to locate installed PySide6 files for Windows packaging.")


PYSIDE6_ROOT = find_pyside6_root()
QT6_ROOT = PYSIDE6_ROOT / "Qt6" if (PYSIDE6_ROOT / "Qt6").exists() else PYSIDE6_ROOT

APP_DATAS = [
    (str(REPO_ROOT / "src" / "resources"), "resources"),
    (str(REPO_ROOT / "src" / "shared_toolkit" / "resources"), "shared_toolkit/resources"),
    (str(REPO_ROOT / "src" / "shared_toolkit" / "ui" / "resources"), "shared_toolkit/ui/resources"),
    (str(QT_CONF_PATH), "."),
]
APP_DATAS.extend(collect_resource_dirs(REPO_ROOT / "src" / "plugins", "plugins"))
APP_DATAS.extend(collect_resource_dirs(REPO_ROOT / "src" / "tabs", "tabs"))
APP_DATAS.extend(collect_resource_dirs(REPO_ROOT / "src" / "ui" / "canvas_features", "ui/canvas_features"))

PYSIDE6_DATAS = []
PYSIDE6_DATAS.extend(collect_tree(QT6_ROOT / "plugins", "PySide6/plugins"))
PYSIDE6_DATAS.extend(collect_tree(QT6_ROOT / "translations", "PySide6/translations"))

PYSIDE6_BINARIES = []
PYSIDE6_BINARIES.extend(collect_tree(PYSIDE6_ROOT, "PySide6", include_suffixes={".dll", ".pyd"}))
PYSIDE6_BINARIES.extend(collect_tree(QT6_ROOT / "bin", "PySide6", include_suffixes={".dll"}))

APP_HIDDENIMPORTS = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtWidgets",
    "shiboken6",
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
    "sli_ui_toolkit.ui.dialogs.dialog_helpers",
    "shared_toolkit.ui.gesture_resolver",
    "shared_toolkit.ui.icon_manager",
    "shared_toolkit.ui.managers.font_manager",
    "shared_toolkit.ui.overlay_layer",
    "sli_ui_toolkit.managers",
    "sli_ui_toolkit.ui.managers.flyout_timer_service",
    "sli_ui_toolkit.ui.widgets.atomic.tooltips",
    "sli_ui_toolkit.ui.widgets.composite.base_flyout",
    "sli_ui_toolkit.ui.widgets.composite.color_swatch",
    "sli_ui_toolkit.ui.widgets.composite.drag_ghost_widget",
    "sli_ui_toolkit.ui.widgets.composite.icon_action_flyout",
    "sli_ui_toolkit.ui.widgets.composite.simple_options_flyout",
    "sli_ui_toolkit.ui.widgets.composite.toast",
    "sli_ui_toolkit.ui.widgets.composite.unified_flyout",
    "sli_ui_toolkit.ui.widgets.composite.unified_flyout.delegate",
    "sli_ui_toolkit.ui.widgets.composite.unified_flyout.layout",
    "sli_ui_toolkit.ui.widgets.composite.unified_flyout.panel",
    "sli_ui_toolkit.ui.widgets.composite.unified_flyout.simple_adapter",
    "sli_ui_toolkit.ui.widgets.overlays.drag_drop_overlay",
    "sli_ui_toolkit.ui.widgets.list_items.rating_item",
    "sli_ui_toolkit.ui.widgets.overlays.paste_direction_overlay",
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

APP_HIDDENIMPORTS.extend(
    collect_project_submodules(
        (
            "core",
            "domain",
            "events",
            "plugins",
            "resources",
            "services",
            "shared",
            "tabs",
            "ui",
            "utils",
            "sli_ui_toolkit",
        )
    )
)

a = Analysis(
    [str(REPO_ROOT / "src" / "__main__.py")],
    pathex=[str(REPO_ROOT), str(REPO_ROOT / "src")],
    binaries=PYSIDE6_BINARIES,
    datas=APP_DATAS + PYSIDE6_DATAS,
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
