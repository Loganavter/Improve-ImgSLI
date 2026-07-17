"""Settings member resolve — tagged controls and combo reveal."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from plugins.settings.member_resolve import resolve_member_in_subtree
from plugins.settings.search import group
from sli_ui_toolkit.widgets import ComboBox


def test_resolve_member_finds_tagged_control(qtbot):
    root = QWidget()
    qtbot.addWidget(root)
    layout = QVBoxLayout(root)
    radio = QWidget(root)
    lang = group("label.language", "settings.language_en")
    lang.tag_member(radio, "settings.language_en")
    layout.addWidget(radio)

    found = resolve_member_in_subtree(root, "settings.language_en", scroll=False)
    assert found is radio


def test_resolve_member_opens_combo_for_option_member(qtbot):
    root = QWidget()
    qtbot.addWidget(root)
    layout = QVBoxLayout(root)
    backend = group(
        "settings.render_backend",
        "settings.render_backend_opengl",
        "settings.render_backend_vulkan",
    )
    combo = ComboBox(parent=root)
    backend.tag_combo(combo)
    combo.addItem("OpenGL", "opengl")
    backend.note_combo_option(combo, "settings.render_backend_opengl")
    combo.addItem("Vulkan", "vulkan")
    backend.note_combo_option(combo, "settings.render_backend_vulkan")
    combo.setCurrentIndex(0)
    layout.addWidget(combo)
    root.show()
    qtbot.waitExposed(root)

    found = resolve_member_in_subtree(
        root, "settings.render_backend_vulkan", scroll=False
    )
    assert combo.currentIndex() == 0
    qtbot.waitUntil(lambda: combo._expanded is True, timeout=2000)
    assert combo._dropdown_focus_index == 1
    # Pulse target is the dropdown row, not the closed field.
    row = combo.dropdown_row_widget(1)
    assert found is row
    assert row is not None


def test_pulse_widget_tolerates_deleted_overlay(qtbot):
    from PySide6.QtWidgets import QWidget

    from ui.actions import widget_pulse

    host = QWidget()
    qtbot.addWidget(host)
    target = QWidget(host)
    host.show()
    qtbot.waitExposed(host)

    widget_pulse.pulse_widget(target, duration_ms=200, pulses=2)
    overlay = widget_pulse._ACTIVE
    assert overlay is not None
    overlay.deleteLater()
    qtbot.wait(50)
    # Stale ticks must not raise RuntimeError.
    qtbot.wait(300)
    assert widget_pulse._ACTIVE is None


def test_pulse_covers_full_custom_group(qtbot):
    """Settings groups pulse the full fieldset after scroll-into-view."""
    from PySide6.QtWidgets import QLabel, QVBoxLayout

    from sli_ui_toolkit.widgets import CustomGroupWidget
    from ui.actions import widget_pulse

    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    group = CustomGroupWidget("Appearance")
    for _ in range(8):
        group.add_widget(QLabel("row"))
    layout.addWidget(group)
    host.resize(400, 500)
    host.show()
    qtbot.waitExposed(host)
    qtbot.waitUntil(lambda: group.height() > 120, timeout=2000)

    widget_pulse.pulse_widget(group, host=host, duration_ms=200, pulses=1)
    overlay = widget_pulse._ACTIVE
    assert overlay is not None
    pulsed = overlay._target_rect
    # Full group (with outset pad), not a title-only band.
    assert pulsed.height() >= group.height() - 4
    assert pulsed.width() >= group.width() - 4
    widget_pulse._dispose_overlay(overlay)


def test_pulse_contrast_halo_on_accent_fill():
    """Selected sidebar rows fill with accent — halo must not match accent."""
    from PySide6.QtGui import QColor

    from ui.actions.widget_pulse import _contrast_for_accent

    accent = QColor("#0078D4")
    halo = _contrast_for_accent(accent)
    assert halo != accent
    assert halo.lightness() > 200


def test_pulse_rect_outsets_sidebar_sized_button(qtbot):
    from PySide6.QtWidgets import QWidget

    from ui.actions.widget_pulse import _PULSE_OUTSET, _pulse_rect

    host = QWidget()
    qtbot.addWidget(host)
    target = QWidget(host)
    target.setGeometry(10, 20, 180, 44)
    host.resize(400, 200)
    host.show()
    qtbot.waitExposed(host)

    rect = _pulse_rect(target, host)
    assert rect.width() == 180 + 2 * _PULSE_OUTSET
    assert rect.height() == 44 + 2 * _PULSE_OUTSET


def test_activate_member_control_sets_combo_index(qtbot):
    from plugins.settings.member_resolve import activate_member_control
    from sli_ui_toolkit.widgets import ComboBox

    combo = ComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    assert activate_member_control(combo, 2) is True
    assert combo.currentIndex() == 2
    assert getattr(combo, "_expanded", False) is False


def test_settings_member_run_uses_run_hook_not_ensure():
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    runs: list[tuple[str, str, str]] = []
    shown: list[str] = []

    register_platform_actions(
        show_settings=lambda: None,
        show_help=lambda: None,
        new_session=lambda: None,
        show_find_action=lambda: None,
        quit_app=lambda: None,
        show_settings_section=lambda sid: shown.append(sid),
        run_settings_member=lambda sid, gkey, mkey: runs.append((sid, gkey, mkey)),
        registry=registry,
    )
    vulkan_id = (
        "settings.group.builtin.performance.settings.render_backend"
        ".settings.render_backend_vulkan"
    )
    action = registry.get(vulkan_id)
    assert action is not None and action.run is not None
    action.run()
    assert runs == [
        ("builtin.performance", "settings.render_backend", "settings.render_backend_vulkan")
    ]
    assert shown == []


def test_settings_member_actions_use_distinct_resolve_from_group():
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    calls: list[tuple[str, ...]] = []

    register_platform_actions(
        show_settings=lambda: None,
        show_help=lambda: None,
        new_session=lambda: None,
        show_find_action=lambda: None,
        quit_app=lambda: None,
        show_settings_section=lambda _sid: None,
        resolve_settings_group=lambda sid, gkey: calls.append(("group", sid, gkey)) or "group",
        resolve_settings_member=lambda sid, gkey, mkey: (
            calls.append(("member", sid, gkey, mkey)) or f"member:{mkey}"
        ),
        registry=registry,
    )
    group_id = "settings.group.builtin.performance.settings.render_backend"
    group_action = registry.get(group_id)
    vulkan_id = f"{group_id}.settings.render_backend_vulkan"
    vulkan_action = registry.get(vulkan_id)
    assert group_action is not None and vulkan_action is not None
    assert group_action.target is not vulkan_action.target
    assert group_action.target.resolve_widget() == "group"
    assert vulkan_action.target.resolve_widget() == "member:settings.render_backend_vulkan"
    assert ("group", "builtin.performance", "settings.render_backend") in calls
    assert (
        "member",
        "builtin.performance",
        "settings.render_backend",
        "settings.render_backend_vulkan",
    ) in calls
