"""Every app window carries minimize / maximize-restore / close.

Owner requirement (2026-10-28): all windows expose the same three functional
window controls. The main window already did (``WindowControlsConfig`` without
``show_*`` -> the toolkit defaults). Dialogs did not, because the app wrapper
``shared_toolkit.ui.decorate_dialog.decorate_dialog`` defaulted to
``show_minimize=False, show_maximize=False``; the fix is one decision point in
that wrapper, not a per-dialog edit.

The exceptions are deliberate and asserted here as such:

* Qt's own ``QFileDialog`` / ``QMessageBox`` -> close only.
* ``_csd_opt_out`` dialogs (``AppMessageDialog`` / ``AppTextInputDialog``) ->
  close only; they own their chrome and are compact modal prompts whose window
  flags declare a close-button hint only.

Buttons are checked by *fact* — the widgets the toolkit actually built on the
title bar (``titlebarRole`` property) — not by re-reading the config flags,
which would restate the implementation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMessageBox,
    QWidget,
)

from shared_toolkit.ui.decorate_dialog import (
    _wants_window_controls,
    decorate_dialog,
    install_application_dialog_decorations,
)
from tests.helpers.drain_until_stable import drain_until_stable

ALL_CONTROLS = {"min", "max", "close"}
CLOSE_ONLY = {"close"}

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _roles(bar) -> set[str]:
    """The window-control roles the title bar actually built.

    ``CustomTitleBar`` only creates a button when its ``show_*`` flag is on
    (a hidden flag means no widget at all), so this reads existence, not
    visibility — it is the same thing the user sees.
    """
    container = bar.window_controls().container
    return {
        role
        for role in (
            widget.property("titlebarRole")
            for widget in container.findChildren(QWidget)
        )
        if role in ("min", "max", "close")
    }


def _flush(qapp) -> None:
    from PySide6.QtCore import QEvent

    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


# -- app dialogs: all three controls ---------------------------------------


def test_explicitly_decorated_app_dialog_gets_three_controls(qapp):
    dialog = QDialog()
    dialog.setWindowTitle("Export")
    bar = decorate_dialog(dialog, title="Export")

    assert bar is not None
    assert _roles(bar) == ALL_CONTROLS
    dialog.deleteLater()
    _flush(qapp)


def test_interceptor_gives_a_bare_dialog_three_controls(qapp):
    """The app-wide Polish filter is the path most ad-hoc dialogs take."""
    install_application_dialog_decorations(qapp)

    dialog = QDialog()
    dialog.setWindowTitle("Ad hoc")
    dialog.ensurePolished()
    drain_until_stable(
        qapp,
        lambda: getattr(dialog, "_csd_title_bar", None),
        timeout_ms=1000,
        stable_frames=2,
    )

    bar = getattr(dialog, "_csd_title_bar", None)
    assert bar is not None, "a bare app QDialog must still be auto-decorated"
    assert _roles(bar) == ALL_CONTROLS
    dialog.deleteLater()
    _flush(qapp)


def test_real_app_dialog_gets_three_controls(qapp):
    """Image Properties is one of the eight app dialogs; prove it end to end.

    The other seven rely on the same wrapper default (see the call-site scan
    below), so this is the representative runtime proof.
    """
    from plugins.image_properties.dialog import ImagePropertiesDialog
    from plugins.image_properties.service import (
        ImageProperties,
        ImagePropertyRow,
        ImagePropertySection,
    )

    properties = ImageProperties(
        title="Properties",
        sections=(
            ImagePropertySection(
                "file",
                "File",
                (ImagePropertyRow("name", "Name", "photo.png"),),
            ),
        ),
    )
    dialog = ImagePropertiesDialog(properties)
    # The dialog defers its layout finalize on QTimer.singleShot(0); run it
    # before tearing the dialog down so it cannot fire on a dead object.
    qapp.processEvents()
    bar = getattr(dialog, "_csd_title_bar", None)

    assert bar is not None
    assert _roles(bar) == ALL_CONTROLS
    dialog.close()
    dialog.deleteLater()
    _flush(qapp)


# -- deliberate exceptions -------------------------------------------------


def test_qmessagebox_stays_close_only(qapp):
    install_application_dialog_decorations(qapp)

    box = QMessageBox()
    box.setText("error")
    box.setWindowTitle("oops")
    box.ensurePolished()
    drain_until_stable(
        qapp,
        lambda: getattr(box, "_csd_title_bar", None),
        timeout_ms=1000,
        stable_frames=2,
    )

    bar = getattr(box, "_csd_title_bar", None)
    assert bar is not None, "QMessageBox keeps its CSD bar (close button)"
    assert _roles(bar) == CLOSE_ONLY
    box.deleteLater()
    _flush(qapp)


def test_qfiledialog_stays_close_only(qapp):
    dialog = QFileDialog()
    dialog.setWindowTitle("Open")
    bar = decorate_dialog(dialog, title="Open")

    assert bar is not None
    assert _roles(bar) == CLOSE_ONLY
    dialog.deleteLater()
    _flush(qapp)


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: _message_dialog(),
            id="app-message-dialog",
        ),
        pytest.param(
            lambda: _text_input_dialog(),
            id="app-text-input-dialog",
        ),
    ],
)
def test_compact_prompts_keep_close_only(qapp, factory):
    """Message / text-input are compact modal prompts: close is the decision.

    They set ``_csd_opt_out`` (they own their chrome) and declare
    ``WindowCloseButtonHint``-only window flags; maximizing a two-line prompt
    is not a workflow, so they keep the close button — consciously.
    """
    dialog = factory()
    bar = getattr(dialog, "_csd_title_bar", None)

    assert bar is not None, "compact prompts decorate themselves"
    assert _roles(bar) == CLOSE_ONLY
    dialog.deleteLater()
    _flush(qapp)


def _message_dialog():
    from shared_toolkit.ui.message_dialog import AppMessageDialog, MessageKind

    return AppMessageDialog(
        kind=MessageKind.INFORMATION,
        title="Info",
        text="compact prompt",
    )


def _text_input_dialog():
    from shared_toolkit.ui.text_input_dialog import AppTextInputDialog

    return AppTextInputDialog(title="Rename", prompt="Name")


def test_gate_is_a_default_not_a_ban(qapp):
    """A call site may still ask for the third button explicitly."""
    dialog = QDialog()
    dialog.setWindowTitle("Force")
    dialog._csd_opt_out = True  # type: ignore[attr-defined]  # dynamic attr

    assert _wants_window_controls(dialog) is False
    bar = decorate_dialog(dialog, title="Force", show_minimize=True, show_maximize=True)

    assert bar is not None
    assert _roles(bar) == ALL_CONTROLS
    dialog.deleteLater()
    _flush(qapp)


def test_gate_predicate():
    plain = QDialog()
    assert _wants_window_controls(plain) is True

    opted_out = QDialog()
    opted_out._csd_opt_out = True  # type: ignore[attr-defined]  # dynamic attr
    assert _wants_window_controls(opted_out) is False

    assert _wants_window_controls(QMessageBox()) is False
    assert _wants_window_controls(QFileDialog()) is False


# -- the single decision point is not bypassed at call sites ---------------

#: The eight app dialogs of the owner's list plus the two compact prompts.
#: A call site that opts out on its own would make "all windows" a lie again.
APP_DIALOG_CALL_SITES = frozenset(
    {
        "plugins/settings/dialog.py",
        "plugins/help/dialog.py",
        "plugins/image_properties/dialog.py",
        "plugins/export/dialog.py",
        "plugins/diagnostics/dialog.py",
        "plugins/diagnostics/offer.py",
        "ui/actions/palette/dialog.py",
        "tabs/image_compare/plugins/video_editor/dialog/shell.py",
    }
)


def _decorate_dialog_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "decorate_dialog":
            calls.append(node)
    return calls


def test_no_call_site_opts_out_of_window_controls():
    """Every app-owned dialog relies on the wrapper default (all three)."""
    found: dict[str, list[ast.Call]] = {}
    for path in sorted(SRC_ROOT.rglob("*.py")):
        calls = [
            call
            for call in _decorate_dialog_calls(path)
            # ``decorate_dialog.py`` holds the wrapper's own definition and its
            # delegation to the toolkit's same-named function.
            if path.name != "decorate_dialog.py" or path.parent.name != "ui"
        ]
        if calls:
            found[path.relative_to(SRC_ROOT).as_posix()] = calls

    missing = APP_DIALOG_CALL_SITES - set(found)
    assert not missing, f"expected decorate_dialog call sites missing: {sorted(missing)}"

    offenders = []
    for rel_path, calls in found.items():
        for call in calls:
            for kwarg in call.keywords:
                if kwarg.arg not in ("show_minimize", "show_maximize"):
                    continue
                if isinstance(kwarg.value, ast.Constant) and kwarg.value.value is False:
                    offenders.append(f"{rel_path}:{call.lineno} {kwarg.arg}=False")
    assert not offenders, (
        "window controls are decided in one place "
        "(shared_toolkit.ui.decorate_dialog._wants_window_controls); "
        f"call sites must not opt out on their own: {offenders}"
    )
