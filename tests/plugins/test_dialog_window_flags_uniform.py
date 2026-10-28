"""Every app window declares the same window flags (owner rule 2026-10-28).

"The export dialog should carry the same flags as the video editor — and ideally
every window that is not the main one." Eight dialog classes each declared their
own subset: Export/Settings/Help/Properties used ``Window|TitleHint|CloseHint``,
the video editor additionally declared maximize/minimize hints. Platform code
that reads the hints (Windows native frames, Qt state bookkeeping) therefore saw
eight different answers for one product.

The normalisation lives in the single choke point every app dialog passes
through — the ``decorate_dialog`` wrapper — and skips Qt's own QFileDialog /
QMessageBox, whose frame may be platform-native.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from shared_toolkit.ui.decorate_dialog import decorate_dialog

_HINTS = (
    Qt.WindowType.WindowTitleHint,
    Qt.WindowType.WindowCloseButtonHint,
    Qt.WindowType.WindowMaximizeButtonHint,
    Qt.WindowType.WindowMinimizeButtonHint,
)


def _assert_uniform_flags(dialog) -> None:
    flags = dialog.windowFlags()
    missing = [hint.name for hint in _HINTS if not (flags & hint)]
    assert not missing, f"dialog is missing window hints: {missing} (flags={flags})"
    assert flags & Qt.WindowType.Window, "an app dialog must be a top-level Window"


def test_plain_dialog_gets_the_uniform_flags(qapp):
    dialog = QDialog()
    dialog.setWindowFlags(
        Qt.WindowType.Window
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
    )
    decorate_dialog(dialog, title="Probe")
    _assert_uniform_flags(dialog)


def test_export_shaped_dialog_matches_the_video_editor(qapp):
    """The reported pair: Export declared close-only, the editor all four."""
    export_like = QDialog()
    export_like.setWindowFlags(
        Qt.WindowType.Window
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
    )
    decorate_dialog(export_like, title="Export")

    editor_like = QDialog()
    editor_like.setWindowFlags(
        Qt.WindowType.Window
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
        | Qt.WindowType.WindowMaximizeButtonHint
        | Qt.WindowType.WindowMinimizeButtonHint
    )
    decorate_dialog(editor_like, title="Video Editor")

    assert export_like.windowFlags() == editor_like.windowFlags(), (
        "Export and the video editor still declare different window flags "
        f"({export_like.windowFlags()} vs {editor_like.windowFlags()})"
    )


def test_qt_standard_dialogs_do_not_gain_the_hints(qapp):
    """QFileDialog/QMessageBox may be platform-native — no hints forced on them.

    (Decorating them already adds ``FramelessWindowHint`` through the toolkit's
    ``apply_frameless``; that is pre-existing and not what this change is about.
    The assertion is therefore about the four capability hints, not the raw
    flag word.)
    """
    for dialog in (QFileDialog(), QMessageBox()):
        decorate_dialog(dialog, title="Qt standard")
        flags = dialog.windowFlags()
        for hint in (
            Qt.WindowType.WindowMaximizeButtonHint,
            Qt.WindowType.WindowMinimizeButtonHint,
        ):
            assert not (flags & hint), (
                f"{type(dialog).__name__} gained {hint.name} from the "
                "normalisation"
            )


def test_normalisation_is_idempotent(qapp):
    dialog = QDialog()
    decorate_dialog(dialog, title="Probe")
    first = dialog.windowFlags()
    decorate_dialog(dialog, title="Probe")  # re-entry must not churn
    assert dialog.windowFlags() == first
