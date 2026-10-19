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
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication
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


def _walk_down_until(dialog: QWidget, target: QWidget, *, max_steps: int = 24) -> None:
    """Press Down until focus lands on *target*, asserting every hop is owned."""
    for _ in range(max_steps):
        current = QApplication.focusWidget()
        if current is target:
            return
        assert _owns(current), f"focus left the dialog: {type(current).__name__}"
        nxt = _press(current, Qt.Key.Key_Down)
        assert nxt is not None, "Down dropped focus to nothing"
    raise AssertionError(
        f"Down never reached {type(target).__name__} "
        f"(last={type(QApplication.focusWidget()).__name__})"
    )


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
        # The SV square stays a deliberate mouse-only service widget.
        assert dialog._sv.focusPolicy() == Qt.FocusPolicy.NoFocus
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
        # Down steps off the picker row onto a fields-row control …
        first_hop = _press(dialog._hue_slider, Qt.Key.Key_Down)
        assert first_hop is not dialog._hue_slider
        assert _owns(first_hop)
        # … and keeps walking the rows down to OK, activating it with Return.
        _walk_down_until(dialog, dialog._ok_btn)
        assert QApplication.focusWidget() is dialog._ok_btn
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


def test_settings_search_down_enters_list_and_ok_activates(qapp):
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
        # OK is reachable/owned and activates on a real key.
        _kbd_focus(dialog.ok_button)
        QTest.keyClick(dialog.ok_button, Qt.Key.Key_Space)
        qapp.processEvents()
        assert confirmed, "Space on the focused OK button must confirm settings"
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
        landed = _press(dialog.combo_format, Qt.Key.Key_Down)
        assert landed is not dialog.combo_format
        assert _owns(landed)
        _walk_down_until(dialog, dialog.btn_ok)
        QTest.keyClick(dialog.btn_ok, Qt.Key.Key_Return)
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
