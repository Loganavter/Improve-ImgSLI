"""App-side UI inspector wiring: toolkit inspector + app families + native
diagnostics. (The core inspection machinery lives in sli-ui-toolkit
``ui/inspector``; these tests cover the app's thin layer.)"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from devtools.ui_inspector.installer import install_ui_inspector
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.inspector import inspect_widget
from sli_ui_toolkit.widgets import Button, ButtonRegion


def _theme(app):
    tm = ThemeManager.get_instance()
    tm.register_palettes(
        {"accent": "#0078d4", "dialog.text": "#111111"},
        {"accent": "#0096ff", "dialog.text": "#dddddd"},
    )
    tm.set_theme("light", app)
    return tm


def _shift_click(widget) -> QMouseEvent:
    center = widget.mapToGlobal(widget.rect().center())
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        center,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
    )


def test_installer_wires_toolkit_inspector(qapp):
    from shared_toolkit.ui.decorate_dialog import install_application_dialog_decorations

    install_application_dialog_decorations(qapp)
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    install_ui_inspector(qapp, host, _theme(qapp))
    controller = host._ui_inspector_controller
    window = host._ui_inspector_window
    assert controller is not None
    assert window is not None
    # idempotent
    install_ui_inspector(qapp, host, _theme(qapp))
    assert host._ui_inspector_controller is controller

    assert controller._handle_mouse_press(_shift_click(button)) is True
    assert controller._committed_widget is button
    assert window.isVisible()
    assert host.window() in controller._overlays
    # the established CSD pipeline decorates the tool window (auto-Polish)
    assert getattr(window, "_csd_title_bar", None) is not None
    controller.shutdown()


def test_selection_populates_native_diagnostics(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    install_ui_inspector(qapp, host, _theme(qapp))
    controller = host._ui_inspector_controller
    window = host._ui_inspector_window
    controller._select_widget(button, global_pos=QPoint(0, 0))
    assert window._native_widget is button
    assert window._native_chain
    assert window._native_chain[0].selector == "Button"
    controller.shutdown()


def test_app_widget_families_self_describe(qapp):
    from ui.widgets.glass_hud import InfoHUD
    from ui.widgets.rating_item import RatingListItem
    from ui.widgets.scroll_value_button import ScrollValueButton

    assert RatingListItem.inspect_spec.family == "RatingListItem"
    assert RatingListItem.inspect_spec.regions is True
    assert ScrollValueButton.inspect_spec.family == "ScrollValueButton"
    assert InfoHUD.inspect_spec.family == "InfoHUD"


# Every app-side widget family carries a spec (family name) and a per-widget
# docs reference for the inspector's Docs page. Add new families here.
_APP_FAMILIES = (
    ("ui.widgets.color", "ColorPickerDialog", "docs/dev/widgets/color_picker_dialog.md"),
    ("ui.widgets.color", "ColorSwatch", "docs/dev/widgets/color_swatch.md"),
    ("ui.widgets.color", "RecentColorsRow", "docs/dev/widgets/recent_colors_row.md"),
    ("ui.widgets.drag_ghost_widget", "DragGhostWidget", "docs/dev/widgets/drag_ghost_widget.md"),
    ("ui.widgets.font_settings_flyout", "FontSettingsFlyout", "docs/dev/widgets/font_settings_flyout.md"),
    ("ui.widgets.form_controls", "DialogActionBar", "docs/dev/widgets/form_controls.md"),
    ("ui.widgets.form_controls", "OutputPathSection", "docs/dev/widgets/form_controls.md"),
    ("ui.widgets.glass_hud", "GlassHUD", "docs/dev/widgets/glass_hud.md"),
    ("ui.widgets.glass_hud", "InfoHUD", "docs/dev/widgets/glass_hud.md"),
    ("ui.widgets.glass_hud", "ZoomIndicator", "docs/dev/widgets/glass_hud.md"),
    ("ui.widgets.glass_hud", "GlassPanelDisplayWidgetCpu", "docs/dev/widgets/glass_panel_display.md"),
    ("ui.widgets.rating_item", "RatingListItem", "docs/dev/widgets/rating_item.md"),
    ("ui.widgets.scroll_value_button", "ScrollValueButton", "docs/dev/widgets/scroll_value_button.md"),
    ("ui.widgets.shelf", "ShelfWidget", "docs/dev/widgets/shelf.md"),
    ("ui.widgets.slider_hint", "ValueSlider", "docs/dev/widgets/value_slider.md"),
    ("ui.widgets.slider_hint", "ValueSliderRow", "docs/dev/widgets/value_slider.md"),
    ("ui.widgets.startup_placeholder", "StartupPlaceholder", "docs/dev/widgets/startup_placeholder.md"),
    ("ui.widgets.themed_surface", "ThemedSurface", "docs/dev/widgets/themed_surface.md"),
    ("ui.widgets.themed_surface", "ThemedBackgroundContainer", "docs/dev/widgets/themed_surface.md"),
    ("ui.widgets.unified_list_picker", "UnifiedListPicker", "docs/dev/widgets/unified_list_picker.md"),
    ("ui.widgets.workspace_tab_strip", "WorkspaceTabStrip", "docs/dev/widgets/workspace_tab_strip.md"),
)


@pytest.mark.parametrize(
    "module_path,family,docs_ref",
    _APP_FAMILIES,
    ids=[f"{mod}::{fam}" for mod, fam, _ in _APP_FAMILIES],
)
def test_app_families_carry_spec_and_docs(module_path, family, docs_ref):
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, family)
    spec = cls.inspect_spec
    assert spec.family == family
    assert spec.docs == docs_ref, (
        f"{family} docs must point at its per-widget page in docs/dev/widgets/"
    )
    repo_root = Path(__file__).resolve().parents[2]
    assert (repo_root / docs_ref).is_file(), f"docs ref {docs_ref} must exist"


def test_new_app_spec_state_resolves(qapp):
    from PySide6.QtGui import QColor

    from sli_ui_toolkit.ui.inspector import inspect_widget

    from ui.widgets.color import ColorSwatch
    from ui.widgets.shelf import ShelfWidget
    from ui.widgets.slider_hint import ValueSlider

    swatch = ColorSwatch(QColor("#ff8800"))
    inspection = inspect_widget(swatch)
    assert inspection.family == "ColorSwatch"
    state = {f.name: f for f in inspection.state}
    assert state["color"].value == QColor("#ff8800")

    slider = ValueSlider()
    slider.setRange(0, 100)
    slider.setValue(25)
    inspection = inspect_widget(slider)
    assert inspection.family == "ValueSlider"
    state = {f.name: f for f in inspection.state}
    assert state["value"].value == 25

    shelf = ShelfWidget()
    inspection = inspect_widget(shelf)
    assert inspection.family == "ShelfWidget"
    state = {f.name: f for f in inspection.state}
    assert state["content_well"].value is False


def test_output_path_section_state_resolves(qapp):
    from sli_ui_toolkit.ui.inspector import inspect_widget

    from ui.widgets.form_controls import OutputPathSection

    section = OutputPathSection(
        directory_label_text="Dir:",
        browse_text="Browse...",
        set_favorite_text="Set",
        use_favorite_text="Use",
        filename_label_text="File:",
        use_custom_line_edit=False,
    )
    section.edit_dir.setText("/tmp/out")
    inspection = inspect_widget(section)
    assert inspection.family == "OutputPathSection"
    state = {f.name: f for f in inspection.state}
    assert state["directory"].value == "/tmp/out"


def test_scroll_value_button_inspection(qapp):
    from ui.widgets.scroll_value_button import ScrollValueButton

    button = ScrollValueButton(min_value=0, max_value=10, start=4)
    inspection = inspect_widget(button)
    assert inspection.family == "ScrollValueButton"
    state = {f.name: f for f in inspection.state}
    assert state["value"].value == 4
    assert state["min_value"].value == 0
    assert state["max_value"].value == 10


def test_dump_layout_button_writes_json(qapp, tmp_path, monkeypatch):
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(regions=[ButtonRegion(id="main")])
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    import devtools.ui_inspector.app_controller as controller_module

    def fake_dump(root, registry):
        return {"windows": [{"class": "QWidget"}]}

    monkeypatch.setattr(controller_module, "dump_ui_layout", fake_dump)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    install_ui_inspector(qapp, host, _theme(qapp))
    controller = host._ui_inspector_controller
    controller._last_focused_window = host
    controller._dump_layout()
    files = list(tmp_path.glob("imgsli_ui_dump_*.json"))
    assert len(files) == 1
    assert '"QWidget"' in files[0].read_text(encoding="utf-8")
    controller.shutdown()


def test_dump_window_button_writes_whole_window_layout(qapp, tmp_path, monkeypatch):
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    import json

    import devtools.ui_inspector.app_controller as controller_module

    roots = []

    def fake_dump(root, registry):
        roots.append(root)
        return {"class": type(root).__name__}

    monkeypatch.setattr(controller_module, "dump_ui_layout", fake_dump)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    install_ui_inspector(qapp, host, _theme(qapp))
    controller = host._ui_inspector_controller
    controller._select_widget(button, global_pos=QPoint(0, 0))
    controller._dump_window_layout()
    files = list(tmp_path.glob("imgsli_ui_dump_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert roots == [host]
    assert data["class"] == "QWidget"
    assert "path" not in data
    controller.shutdown()


def test_dump_layout_with_selection_dumps_subtree_not_window(qapp, tmp_path, monkeypatch):
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    import json

    import devtools.ui_inspector.app_controller as controller_module

    roots = []

    def fake_dump(root, registry):
        roots.append(root)
        return {"class": type(root).__name__}

    monkeypatch.setattr(controller_module, "dump_ui_layout", fake_dump)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    install_ui_inspector(qapp, host, _theme(qapp))
    controller = host._ui_inspector_controller
    controller._select_widget(button, global_pos=QPoint(0, 0))
    controller._dump_layout()
    files = list(tmp_path.glob("imgsli_ui_dump_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert roots == [button]
    assert data["class"] == "Button"
    assert data["path"][-1] == {"class": "Button", "object_name": ""}
    assert data["path"][0]["class"] == "QWidget"
    controller.shutdown()