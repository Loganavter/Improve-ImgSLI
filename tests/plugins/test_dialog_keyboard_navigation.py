"""Every interactive control in the four host dialogs is owned by a section.

Plan ``plan-nav-coverage-2026-10-19`` (card N3b). The supervisor's live+code
audit found keyboard navigation missing or partial in four host windows:

* **Colour picker** — only the recent-chips row and the action row were
  declared; the hue/alpha sliders, the value field + format button and the
  R/G/B/A spin boxes (8 controls) were orphans.
* **Settings shell** — the search field and the OK/Cancel action bar were
  owned by no section (each settings *page* and the sidebar had their own).
* **Export dialog** — no navigation section at all.
* **Image-properties dialog** — no navigation section at all.

These are the *red* assertions: with the pre-fix tree the orphan lists are
non-empty and :func:`_owns` returns ``False`` for them (recorded in DONE.md).
The fix registers the missing rows/sections; ownership + one real key drive
per surface is the green gate.

Offscreen, real widgets + the real process-wide ``NavigationManager``; keys
are delivered through ``QTest.keyClick`` so the manager → section → widget
path (including its QApplication event filter) is what actually runs.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from resources.translations import add_i18n_root
from sli_ui_toolkit.managers import NavigationManager


def _manager() -> NavigationManager:
    return NavigationManager.get_instance()


def _owns(widget: QWidget) -> bool:
    """True when some registered section claims *widget* (live registry)."""
    for _owner, spec in list(_manager()._sections):
        try:
            if spec.owns(widget):
                return True
        except Exception:
            continue
    return False


def _interactive(root: QWidget) -> list[QWidget]:
    """Visible + enabled + keyboard-reachable descendants (the audit's set)."""
    out: list[QWidget] = []
    for widget in root.findChildren(QWidget):
        if widget.focusPolicy() == Qt.FocusPolicy.NoFocus:
            continue
        if not (widget.isVisible() and widget.isEnabled()):
            continue
        out.append(widget)
    return out


def _assert_all_owned(dialog: QWidget) -> list[QWidget]:
    orphans = [w for w in _interactive(dialog) if not _owns(w)]
    assert not orphans, "\n".join(
        f"  orphan: {type(w).__name__}({w.objectName()!r})" for w in orphans
    )
    return _interactive(dialog)


def _focus_reason() -> Qt.FocusReason:
    return _manager().current_focus_reason()


def _kbd_focus(widget: QWidget) -> None:
    """Grant keyboard focus with the manager's own modality (never a literal)."""
    widget.setFocus(_focus_reason())
    QApplication.processEvents()


def _press(widget: QWidget, key: Qt.Key) -> QWidget | None:
    focused = QApplication.focusWidget()
    assert focused is not None, "nothing focused — cannot drive the dialog"
    QTest.keyClick(focused, key)
    QApplication.processEvents()
    return QApplication.focusWidget()


def _walk_down_to_bottom(*, max_steps: int = 24) -> QWidget:
    """Press Down until focus stops moving; every hop must stay owned."""
    current = QApplication.focusWidget()
    for _ in range(max_steps):
        assert _owns(current), f"focus left the dialog: {type(current).__name__}"
        nxt = _press(current, Qt.Key.Key_Down)
        assert nxt is not None, "Down dropped focus to nothing"
        assert _owns(nxt), f"Down moved onto an orphan: {type(nxt).__name__}"
        if nxt is current:
            return current
        current = nxt
    raise AssertionError("Down never settled — navigation may be looping")


# ---------------------------------------------------------------------------
# Colour picker
# ---------------------------------------------------------------------------


def _color_picker(tmp_path):
    from ui.widgets.color import ColorPickerDialog, RecentColorsStore

    store = RecentColorsStore(
        QSettings(str(tmp_path / "cfg.ini"), QSettings.Format.IniFormat)
    )
    for code in ("#FF8800", "#224466"):
        store.add(code)
    return ColorPickerDialog(QColor("#101010"), show_alpha=True, recents_store=store)


def test_color_picker_every_interactive_control_is_owned(qapp, tmp_path):
    dialog = _color_picker(tmp_path)
    dialog.show()
    qapp.processEvents()
    try:
        # The 8 controls the audit named as orphans, made explicit here.
        for control in (
            dialog._hue_slider,
            dialog._alpha_slider,
            dialog._hex_edit,
            dialog._format_btn,
            dialog._r_spin,
            dialog._g_spin,
            dialog._b_spin,
            dialog._a_spin,
        ):
            assert _owns(control), (
                f"{type(control).__name__} is an orphan — no section owns it"
            )
        _assert_all_owned(dialog)
        # The SV square is a keyboard stop like every other value control
        # (its own Enter-gated edit contract, see the picker docs).
        assert dialog._sv.focusPolicy() == Qt.FocusPolicy.StrongFocus
    finally:
        dialog.close()


def test_color_picker_down_walks_to_ok_and_activates(qapp, tmp_path):
    dialog = _color_picker(tmp_path)
    dialog.show()
    qapp.processEvents()
    accepted: list[int] = []
    dialog.accepted.connect(lambda: accepted.append(1))
    try:
        _kbd_focus(dialog._hue_slider)
        assert QApplication.focusWidget() is dialog._hue_slider
        # Down steps off the picker row onto an owned fields-row control …
        moved = _press(dialog._hue_slider, Qt.Key.Key_Down)
        assert moved is not dialog._hue_slider
        assert _owns(moved)
        # … and the action row is reachable: cancel (leftmost) → Right → OK,
        # activated by a real Return.
        _kbd_focus(dialog._cancel_btn)
        assert _press(dialog._cancel_btn, Qt.Key.Key_Right) is dialog._ok_btn
        QTest.keyClick(dialog._ok_btn, Qt.Key.Key_Return)
        qapp.processEvents()
        assert accepted, "Return on the focused OK button must accept the picker"
    finally:
        dialog.close()


# ---------------------------------------------------------------------------
# Settings shell
# ---------------------------------------------------------------------------


def _settings_dialog():
    add_i18n_root(Path("src/plugins/settings/resources/i18n"))
    from plugins.settings.dialog import SettingsDialog

    return SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        active_tab="image_compare",
    )


def test_settings_shell_every_interactive_control_is_owned(qapp):
    dialog = _settings_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        for control in (dialog.search_field, dialog.ok_button, dialog.cancel_button):
            assert _owns(control), (
                f"{type(control).__name__} is an orphan — no section owns it"
            )
        _assert_all_owned(dialog)
    finally:
        dialog.close()


def test_settings_search_down_enters_list_and_ok_activates(qapp, qtbot):
    dialog = _settings_dialog()
    dialog.show()
    qapp.processEvents()
    confirmed: list[int] = []
    dialog.settings_confirmed.connect(lambda: confirmed.append(1))
    try:
        _kbd_focus(dialog.search_field)
        assert QApplication.focusWidget() is dialog.search_field
        landed = _press(dialog.search_field, Qt.Key.Key_Down)
        assert landed is not dialog.search_field, "Down must leave the search field"
        assert _owns(landed)
        # OK is owned and activates on a real key (the click lands after the
        # button's deferred ripple — wait for it).
        _kbd_focus(dialog.ok_button)
        QTest.keyClick(dialog.ok_button, Qt.Key.Key_Space)
        qtbot.waitUntil(lambda: bool(confirmed), timeout=4000)
    finally:
        dialog.close()


# ---------------------------------------------------------------------------
# Export dialog
# ---------------------------------------------------------------------------


def _export_dialog():
    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    from domain.types import Color
    from plugins.export.dialog import ExportDialog
    from plugins.export.models import ExportDialogState

    state = ExportDialogState(
        current_language="en",
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=True,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
        virtual_canvas_active=True,
    )
    return ExportDialog(dialog_state=state, suggested_filename="out")


def test_export_dialog_every_interactive_control_is_owned(qapp):
    dialog = _export_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        owned = _assert_all_owned(dialog)
        assert len(owned) >= 8, "export dialog should expose its form controls"
    finally:
        dialog.close()


def test_export_dialog_down_moves_focus_and_ok_activates(qapp):
    dialog = _export_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        _kbd_focus(dialog.combo_format)
        assert QApplication.focusWidget() is dialog.combo_format
        landed = _walk_down_to_bottom()
        assert landed is not dialog.combo_format
        assert _owns(landed)
        # OK is owned and activates on a real key.
        _kbd_focus(dialog.btn_ok)
        QTest.keyClick(dialog.btn_ok, Qt.Key.Key_Space)
        qapp.processEvents()
        assert dialog.result() == dialog.DialogCode.Accepted
    finally:
        dialog.close()


# ---------------------------------------------------------------------------
# Image properties dialog
# ---------------------------------------------------------------------------


def _image_properties_dialog():
    from plugins.image_properties.dialog import ImagePropertiesDialog
    from plugins.image_properties.service import (
        ImageProperties,
        ImagePropertyRow,
        ImagePropertySection,
    )

    properties = ImageProperties(
        title="Properties",
        sections=tuple(
            ImagePropertySection(
                f"section_{i}",
                f"Section {i}",
                (ImagePropertyRow(f"row_{i}", "Name", f"value_{i}.png"),),
            )
            for i in range(2)
        ),
    )
    return ImagePropertiesDialog(properties, current_language="en")


def test_image_properties_every_interactive_control_is_owned(qapp):
    dialog = _image_properties_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        for control in (dialog.copy_all_button, dialog.close_button):
            assert _owns(control), (
                f"{type(control).__name__} is an orphan — no section owns it"
            )
        _assert_all_owned(dialog)
    finally:
        dialog.close()


def test_image_properties_copy_activates_on_key(qapp):
    dialog = _image_properties_dialog()
    dialog.show()
    qapp.processEvents()
    clipboard = QGuiApplication.clipboard()
    clipboard.setText("")
    try:
        _kbd_focus(dialog.copy_all_button)
        QTest.keyClick(dialog.copy_all_button, Qt.Key.Key_Space)
        qapp.processEvents()
        assert clipboard.text().strip(), "Space on Copy all must copy the properties"
    finally:
        dialog.close()


# ---------------------------------------------------------------------------
# AppMessageDialog / AppTextInputDialog / DiagnosticsDialog
#
# The third audit (F3) found these three windows had NO navigation section at
# all: they decorated a CSD title bar and declared no rows, so every arrow key
# was dropped and the only path to the buttons was the mouse. The fix is
# ``register_dialog_auto_navigation`` (src/shared_toolkit/ui/decorate_dialog.py)
# plus ``register_dialog_title_bar_navigation``. The window-level allowlist
# exemptions were removed, so the app-wide contract audits these controls.
# ---------------------------------------------------------------------------


def _message_dialog() -> QWidget:
    from shared_toolkit.ui.message_dialog import AppMessageDialog, MessageKind

    return AppMessageDialog(
        None,
        kind=MessageKind.WARNING,
        title="Watch out",
        text="Something happened.",
        checkbox_text="Remember",
        dont_ask_text="Do not ask again",
        cancel_text="Cancel",
    )


def test_message_dialog_every_interactive_control_is_owned(qapp):
    dialog = _message_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        for control in (
            dialog._message_label,
            dialog._checkbox,
            dialog._cancel_button,
            dialog._dont_ask_button,
            dialog._ok_button,
        ):
            assert _owns(control), (
                f"{type(control).__name__} is an orphan — no section owns it"
            )
        _assert_all_owned(dialog)
    finally:
        dialog.close()


def test_message_dialog_down_up_walk_and_enter_accepts(qapp):
    dialog = _message_dialog()
    dialog.show()
    qapp.processEvents()
    accepted: list[int] = []
    dialog.accepted.connect(lambda: accepted.append(1))
    try:
        _kbd_focus(dialog._message_label)
        # Body → checkbox → action row, in visual order.
        assert _press(dialog._message_label, Qt.Key.Key_Down) is dialog._checkbox
        landed = _press(dialog._checkbox, Qt.Key.Key_Down)
        assert landed in (
            dialog._cancel_button,
            dialog._dont_ask_button,
            dialog._ok_button,
        ), f"Down from the checkbox must enter the action row, got {landed}"
        # Up walks back the same way.
        assert _press(landed, Qt.Key.Key_Up) is dialog._checkbox
        # Enter activates the focused button (OK accepts the dialog).
        _kbd_focus(dialog._ok_button)
        QTest.keyClick(dialog._ok_button, Qt.Key.Key_Return)
        qapp.processEvents()
        assert accepted, "Return on the focused OK button must accept the dialog"
    finally:
        dialog.close()


def _text_input_dialog() -> QWidget:
    from shared_toolkit.ui.text_input_dialog import AppTextInputDialog

    return AppTextInputDialog(None, title="Rename", prompt="New name", text="old")


def test_text_input_dialog_every_interactive_control_is_owned(qapp):
    dialog = _text_input_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        for control in (dialog._line_edit, dialog._cancel_button, dialog._ok_button):
            assert _owns(control), (
                f"{type(control).__name__} is an orphan — no section owns it"
            )
        _assert_all_owned(dialog)
    finally:
        dialog.close()


def test_text_input_dialog_down_walks_field_to_actions_and_enter_cancels(qapp):
    dialog = _text_input_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        _kbd_focus(dialog._line_edit)
        landed = _press(dialog._line_edit, Qt.Key.Key_Down)
        assert landed in (dialog._cancel_button, dialog._ok_button), (
            f"Down from the field must enter the action row, got {landed}"
        )
        assert _press(landed, Qt.Key.Key_Up) is dialog._line_edit
        # Enter activates the focused button (Cancel rejects the dialog).
        _kbd_focus(dialog._cancel_button)
        QTest.keyClick(dialog._cancel_button, Qt.Key.Key_Return)
        qapp.processEvents()
        assert dialog.result() == dialog.DialogCode.Rejected
    finally:
        dialog.close()


def _diagnostics_dialog() -> QWidget:
    from plugins.diagnostics.dialog import DiagnosticsDialog
    from plugins.diagnostics.report import DiagnosticsReport

    report = DiagnosticsReport(
        payload={"app": {"version": "test"}}, text="diagnostics line\n" * 5
    )
    return DiagnosticsDialog(report, current_language="en")


def test_diagnostics_dialog_every_interactive_control_is_owned(qapp):
    dialog = _diagnostics_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        for control in (
            dialog.preview,
            dialog.open_issue_button,
            dialog.copy_button,
            dialog.save_button,
            dialog.close_button,
        ):
            assert _owns(control), (
                f"{type(control).__name__} is an orphan — no section owns it"
            )
        _assert_all_owned(dialog)
    finally:
        dialog.close()


def test_diagnostics_dialog_down_walks_report_to_actions_and_enter_accepts(qapp):
    dialog = _diagnostics_dialog()
    dialog.show()
    qapp.processEvents()
    actions = (
        dialog.open_issue_button,
        dialog.copy_button,
        dialog.save_button,
        dialog.close_button,
    )
    try:
        _kbd_focus(dialog.preview)
        landed = _press(dialog.preview, Qt.Key.Key_Down)
        assert landed in actions, (
            f"Down from the report must enter the action row, got {landed}"
        )
        # Left/Right walk the action row in visual order.
        first = actions[0]
        _kbd_focus(first)
        assert _press(first, Qt.Key.Key_Right) is actions[1]
        # Up returns to the report view.
        assert _press(actions[1], Qt.Key.Key_Up) is dialog.preview
        # Enter activates the focused button (Close accepts the dialog).
        _kbd_focus(dialog.close_button)
        QTest.keyClick(dialog.close_button, Qt.Key.Key_Return)
        qapp.processEvents()
        assert dialog.result() == dialog.DialogCode.Accepted
    finally:
        dialog.close()


# ---------------------------------------------------------------------------
# Onboarding overlay
#
# The overlay swallowed every key (blanket ``event.accept()`` in
# ``keyPressEvent``) and registered no section: arrows and Tab dead-ended and
# typed characters never reached the focused control. It now registers the
# mode chips + Start as one section and owns only Escape.
# ---------------------------------------------------------------------------


class _OnboardingSettings:
    """Minimal settings double for the overlay's finish path."""

    def __init__(self) -> None:
        self.saved: dict[str, object] = {}
        self.first_run_completed = False

    def _save_setting(self, key: str, value: object) -> None:
        self.saved[key] = value

    def set_first_run_completed(self) -> None:
        self.first_run_completed = True

    def schedule_persist(self, store) -> None:
        return None


def _onboarding_overlay():
    from core.store import Store
    from plugins.onboarding.overlay import OnboardingOverlay

    settings = _OnboardingSettings()
    overlay = OnboardingOverlay(settings, Store())
    overlay.show()
    QApplication.processEvents()
    return overlay, settings


def test_onboarding_overlay_owns_chips_and_start(qapp):
    overlay, _settings = _onboarding_overlay()
    try:
        for control in (*overlay.mode_buttons, overlay.btn_start):
            assert _owns(control), (
                f"{control.objectName()} is an orphan — no section owns it"
            )
        assert [chip.isVisible() for chip in overlay.mode_buttons] == [True] * len(
            overlay.mode_buttons
        )
    finally:
        overlay.close()


def test_onboarding_overlay_arrows_walk_chips_and_start(qapp):
    overlay, _settings = _onboarding_overlay()
    try:
        first, second = overlay.mode_buttons[0], overlay.mode_buttons[1]
        _kbd_focus(first)
        assert _press(first, Qt.Key.Key_Right) is second
        # Down enters the Start row; Up returns to a chip.
        landed = _walk_down_to_bottom()
        assert landed is overlay.btn_start, (
            f"Down from the chips must reach Start, got {landed}"
        )
        back = _press(landed, Qt.Key.Key_Up)
        assert back in overlay.mode_buttons, (
            f"Up from Start must return to a chip, got {back}"
        )
    finally:
        overlay.close()


def test_onboarding_overlay_does_not_swallow_unrelated_keys(qapp):
    """A typed character is no longer eaten by the overlay (the old bug)."""
    overlay, _settings = _onboarding_overlay()
    try:
        _kbd_focus(overlay.mode_buttons[0])
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_P, Qt.KeyboardModifier.NoModifier, "p"
        )
        # Delivered to the focused chip; the chip ignores it and Qt propagates
        # to the overlay. The blanket accept() used to swallow it here.
        QApplication.sendEvent(overlay.mode_buttons[0], event)
        assert not event.isAccepted(), (
            "the onboarding overlay swallowed an unrelated key — it must only "
            "own Escape and the section graph's arrows/Tab"
        )
    finally:
        overlay.close()


def test_onboarding_overlay_escape_finishes_and_closes(qapp):
    overlay, settings = _onboarding_overlay()
    completed: list[str] = []
    overlay.completed.connect(completed.append)
    try:
        QTest.keyClick(overlay, Qt.Key.Key_Escape)
        qapp.processEvents()
        assert completed == [overlay.modes[overlay._current_index]["key"]], (
            "Escape must finish onboarding with the current mode"
        )
        assert settings.first_run_completed
    finally:
        overlay.close()
