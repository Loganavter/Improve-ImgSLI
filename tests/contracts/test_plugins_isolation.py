"""Plugin isolation dogma.

  * a plugin must NOT import a canvas feature directly
  * a plugin must NOT reach into another plugin's internals
    (controller / presenter / state / dialog) — cross-plugin communication
    goes via events / services / plugin_coordinator

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md (no feature imports in plugins/)
and docs/dev/ARCHITECTURE.md (plugin decoupling).
"""

from __future__ import annotations

import re

import pytest

from ._framework import PLUGINS as PLUGINS_ROOT
from ._framework import iter_py, list_plugins, module_imports, read, rel

PLUGINS = list_plugins()
PLUGIN_IDS = [p.name for p in PLUGINS]

_CANVAS_FEATURE_RE = re.compile(
    r"(?:src\.)?tabs\.image_compare\.canvas\.features\.([a-zA-Z_]\w*)"
)
_CROSS_PLUGIN_RE = re.compile(r"plugins\.([^.]+)\.(.+)")
_FORBIDDEN_INTERNALS = ("controller", "presenter", "state", "dialog")

@pytest.mark.parametrize("plugin", PLUGINS, ids=PLUGIN_IDS)
def test_plugin_does_not_import_canvas_features_directly(plugin):
    leaks: list[str] = []
    for py in iter_py(plugin):
        for module, lineno in module_imports(py):
            m = _CANVAS_FEATURE_RE.match(module)
            if m and not m.group(1).startswith("_"):
                leaks.append(
                    f"{rel(py)}:{lineno} imports canvas feature "
                    f"'{m.group(1)}' (use capability aliases)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)

@pytest.mark.parametrize("plugin", PLUGINS, ids=PLUGIN_IDS)
def test_plugin_does_not_import_other_plugins_internals(plugin):
    leaks: list[str] = []
    for py in iter_py(plugin):
        for module, lineno in module_imports(py):
            m = _CROSS_PLUGIN_RE.match(module)
            if not m:
                continue
            other, tail = m.group(1), m.group(2)
            if other == plugin.name:
                continue
            head = tail.split(".")[0]
            if head in _FORBIDDEN_INTERNALS:
                leaks.append(
                    f"{rel(py)}:{lineno} imports '{head}' of plugin "
                    f"'{other}' (use events/services/coordinator)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_export_plugin_does_not_call_canvas_feature_registry_directly():
    """Image-compare export feature queries belong behind tab-owned services."""
    export_root = PLUGINS_ROOT / "export"
    leaks: list[str] = []
    for py in iter_py(export_root):
        text = read(py)
        if "get_canvas_feature_command" not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "get_canvas_feature_command" in line:
                leaks.append(
                    f"{rel(py)}:{lineno} calls canvas feature registry "
                    "(use a tab-owned export/snapshot service)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_export_plugin_does_not_publish_legacy_image_export_command():
    """Root export plugin is a dispatcher, not the owner of image-pair export."""
    path = PLUGINS_ROOT / "export" / "plugin.py"
    text = read(path)
    forbidden = (
        "from plugins.export.services.image_export import ExportService",
        "self.export_service",
        "def export_image(",
        'command == "export_image"',
        '"export_image":',
    )
    leaks = [token for token in forbidden if token in text]
    assert not leaks, (
        "plugins.export.plugin must not expose the old image-pair export command; "
        f"still-image export belongs behind presenter/tab-owned services: {leaks}"
    )


def test_export_plugin_does_not_own_image_pair_export_service():
    """Image-pair still export implementation belongs to the active tab."""
    export_root = PLUGINS_ROOT / "export"
    legacy_path = export_root / "services" / "image_export.py"
    assert not legacy_path.exists(), (
        f"{rel(legacy_path)} is image-pair export logic; use a tab-owned export service"
    )

    leaks: list[str] = []
    for py in iter_py(export_root):
        for module, lineno in module_imports(py):
            if module == "plugins.export.services.image_export":
                leaks.append(
                    f"{rel(py)}:{lineno} imports legacy image-pair export service "
                    "(use TabRegistry image_export_service)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_export_plugin_does_not_import_legacy_clipboard_service():
    """Clipboard paste is tab-specific because it loads into image slots."""
    legacy_path = PLUGINS_ROOT.parent / "services" / "system" / "clipboard.py"
    assert not legacy_path.exists(), (
        f"{rel(legacy_path)} is image-compare paste logic; use a tab service"
    )

    export_root = PLUGINS_ROOT / "export"
    leaks: list[str] = []
    for py in iter_py(export_root):
        for module, lineno in module_imports(py):
            if module == "services.system.clipboard":
                leaks.append(
                    f"{rel(py)}:{lineno} imports legacy clipboard service "
                    "(use TabRegistry clipboard_paste_service)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_export_plugin_does_not_publish_dead_recorded_video_event():
    """Video export is initiated by the video editor, not a dead root event."""
    export_root = PLUGINS_ROOT / "export"
    forbidden = (
        "ExportExportRecordedVideoEvent",
        "EXPORT_EXPORT_RECORDED_VIDEO",
        "def export_recorded_video(",
        "on_export_recorded_video",
    )
    leaks: list[str] = []
    for py in iter_py(export_root):
        text = read(py)
        for token in forbidden:
            if token in text:
                leaks.append(f"{rel(py)} contains legacy recorded-video token {token!r}")
    constants = PLUGINS_ROOT.parent / "core" / "constants.py"
    constants_text = read(constants)
    for token in forbidden:
        if token in constants_text:
            leaks.append(f"{rel(constants)} contains legacy recorded-video token {token!r}")
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_export_plugin_does_not_publish_dead_quick_save_event():
    """Quick save is wired through the presenter/tab path, not a root event."""
    export_root = PLUGINS_ROOT / "export"
    forbidden = (
        "ExportQuickSaveComparisonEvent",
        "EXPORT_QUICK_SAVE_COMPARISON",
        "quick_save_comparison",
        "on_quick_save_comparison",
    )
    leaks: list[str] = []
    for py in iter_py(export_root):
        text = read(py)
        for token in forbidden:
            if token in text:
                leaks.append(f"{rel(py)} contains legacy quick-save token {token!r}")
    constants = PLUGINS_ROOT.parent / "core" / "constants.py"
    constants_text = read(constants)
    for token in forbidden:
        if token in constants_text:
            leaks.append(f"{rel(constants)} contains legacy quick-save token {token!r}")
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_export_plugin_does_not_construct_video_editor_services_directly():
    """Recorder/video exporter construction is owned by the video editor plugin."""
    path = PLUGINS_ROOT / "export" / "plugin.py"
    leaks: list[str] = []
    for module, lineno in module_imports(path):
        if module in {
            "tabs.image_compare.plugins.video_editor.services.recorder",
            "tabs.image_compare.plugins.video_editor.services.export",
        }:
            leaks.append(
                f"{rel(path)}:{lineno} imports {module!r} "
                "(ask video_editor plugin for recording services)"
            )
    text = read(path)
    for token in ("Recorder(", "VideoExporterService("):
        if token in text:
            leaks.append(f"{rel(path)} constructs video-editor service via {token!r}")
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_export_plugin_does_not_own_video_editor_flow_modules():
    """Recording and video export flow orchestration belongs to video_editor."""
    export_root = PLUGINS_ROOT / "export"
    legacy_paths = (
        export_root / "services" / "recording_flow.py",
        export_root / "services" / "video_export_flow.py",
    )
    for path in legacy_paths:
        assert not path.exists(), (
            f"{rel(path)} is video-editor orchestration; use video_editor services"
        )

    leaks: list[str] = []
    forbidden_modules = {
        "plugins.export.services.recording_flow",
        "plugins.export.services.video_export_flow",
    }
    for py in iter_py(export_root):
        for module, lineno in module_imports(py):
            if module in forbidden_modules:
                leaks.append(f"{rel(py)}:{lineno} imports {module!r}")
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_export_plugin_does_not_own_image_pair_presenter_parts():
    """Image-pair export state/save flow belong to the image_compare tab."""
    export_root = PLUGINS_ROOT / "export"
    legacy_paths = (
        export_root / "presenter_parts" / "context_builder.py",
        export_root / "presenter_parts" / "save_flow.py",
        export_root / "presenter_parts" / "state.py",
    )
    for path in legacy_paths:
        assert not path.exists(), (
            f"{rel(path)} is image-pair export orchestration; use tab services"
        )

    models_text = read(export_root / "models.py")
    assert "ExportSaveContext" not in models_text, (
        "plugins.export.models must not own image-pair ExportSaveContext; "
        "use tabs.image_compare.services.export_models"
    )

    leaks: list[str] = []
    for py in iter_py(export_root):
        for module, lineno in module_imports(py):
            if module.startswith("plugins.export.presenter_parts"):
                leaks.append(f"{rel(py)}:{lineno} imports {module!r}")
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_layout_plugin_does_not_own_image_compare_toolbar_layout():
    """Root layout plugin is a bridge; tab toolbar definitions live in tabs."""
    layout_root = PLUGINS_ROOT / "layout"
    legacy_paths = (
        layout_root / "definitions.py",
        layout_root / "manager.py",
    )
    for path in legacy_paths:
        assert not path.exists(), (
            f"{rel(path)} is image-compare toolbar layout; use tab layout services"
        )

    forbidden_tokens = (
        "btn_diff_mode",
        "btn_channel_mode",
        "btn_file_names",
        "btn_magnifier",
        "btn_divider",
        "btn_record",
        "btn_pause",
        "btn_video_editor",
        "magnifier_group",
        "record_group",
    )
    leaks: list[str] = []
    for py in iter_py(layout_root):
        text = read(py)
        for token in forbidden_tokens:
            if token in text:
                leaks.append(f"{rel(py)} contains tab toolbar token {token!r}")
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_settings_plugin_does_not_own_canvas_feature_color_pickers():
    """Canvas feature color picker UI belongs to the image_compare tab."""
    settings_root = PLUGINS_ROOT / "settings"
    legacy_path = settings_root / "presenter_parts" / "color_pickers.py"
    assert not legacy_path.exists(), (
        f"{rel(legacy_path)} is canvas-feature UI; use tab settings services"
    )

    leaks: list[str] = []
    forbidden_tokens = (
        "SettingsColorPickerCoordinator",
        "read_canvas_feature_color_by_setting_key",
        "show_magnifier_divider_color_picker",
        "show_magnifier_border_color_picker",
        "show_laser_color_picker",
        "show_capture_ring_color_picker",
        "apply_smart_magnifier_colors",
    )
    for py in iter_py(settings_root):
        text = read(py)
        for token in forbidden_tokens:
            if token in text and py.name != "presenter.py":
                leaks.append(f"{rel(py)} contains canvas color picker token {token!r}")
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_settings_controller_does_not_expose_image_compare_feature_wrappers():
    """Root settings controller exposes generic tab gateways, not feature methods."""
    path = PLUGINS_ROOT / "settings" / "controller.py"
    text = read(path)
    forbidden_tokens = (
        "toggle_include_filenames_in_saved",
        "toggle_magnifier_divider_visibility",
        "set_magnifier_divider_color",
        "set_magnifier_divider_thickness",
        "set_magnifier_border_color",
        "set_magnifier_laser_color",
        "set_guides_color",
        "toggle_guides_visibility",
        "set_guides_thickness",
        "set_capture_color",
        "toggle_capture_visibility",
        "set_capture_ring_color",
    )
    leaks = [token for token in forbidden_tokens if token in text]
    assert not leaks, (
        "plugins.settings.controller must not own image_compare canvas feature "
        f"wrappers; use execute_canvas_feature_alias: {leaks}"
    )


def test_settings_application_service_does_not_own_image_compare_feature_settings():
    """Root settings application applies generic settings, not tab feature state."""
    path = PLUGINS_ROOT / "settings" / "application_service.py"
    text = read(path)
    forbidden_tokens = (
        "overlay.settings.",
        "guides.",
        "capture.",
        "magnifier.",
        "execute_canvas_feature_alias",
        "get_canvas_feature_command",
    )
    leaks = [token for token in forbidden_tokens if token in text]
    assert not leaks, (
        "plugins.settings.application_service must not own image_compare canvas "
        f"feature application; use a tab service: {leaks}"
    )


def test_settings_manager_does_not_own_image_compare_feature_bootstrap():
    """Root settings manager delegates tab feature startup/persist to tabs."""
    path = PLUGINS_ROOT / "settings" / "manager.py"
    text = read(path)
    forbidden_tokens = (
        "overlay.settings",
        "guides.set_smoothing",
        "optimize_magnifier_movement",
        "magnifier_movement_interpolation_method",
        "execute_canvas_feature_alias",
    )
    leaks = [token for token in forbidden_tokens if token in text]
    assert not leaks, (
        "plugins.settings.manager must not own image_compare feature bootstrap; "
        f"use tab settings services: {leaks}"
    )


def test_video_export_bounds_does_not_call_canvas_feature_registry_directly():
    """Video export bounds asks tabs for layout instead of querying features."""
    path = PLUGINS_ROOT / "video_editor" / "services" / "video_export_bounds.py"
    leaks: list[str] = []
    for lineno, line in enumerate(read(path).splitlines(), 1):
        if "get_canvas_feature_command" in line:
            leaks.append(
                f"{rel(path)}:{lineno} calls canvas feature registry "
                "(use a tab-owned bounds service)"
            )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_settings_plugin_does_not_call_canvas_feature_command_registry_directly():
    """Settings may use its tab-service gateway, not feature command registries."""
    settings_root = PLUGINS_ROOT / "settings"
    leaks: list[str] = []
    allowed = {settings_root / "canvas_feature_gateway.py"}
    for py in iter_py(settings_root):
        if py in allowed:
            continue
        for lineno, line in enumerate(read(py).splitlines(), 1):
            if "get_canvas_feature_command" in line:
                leaks.append(
                    f"{rel(py)}:{lineno} calls canvas feature registry "
                    "(use plugins.settings.canvas_feature_gateway)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_plugins_do_not_call_canvas_feature_command_registry_directly():
    """Generic plugins must consume tab services, not canvas feature registries."""
    leaks: list[str] = []
    for py in iter_py(PLUGINS_ROOT):
        for lineno, line in enumerate(read(py).splitlines(), 1):
            if "get_canvas_feature_command" in line:
                leaks.append(
                    f"{rel(py)}:{lineno} calls canvas feature registry "
                    "(use a tab-owned service boundary)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)
