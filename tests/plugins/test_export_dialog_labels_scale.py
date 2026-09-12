"""Export dialog text labels follow the UiScale factor (live + on reopen).

Regression: the export window built its text labels with plain ``QLabel``,
which never re-resolves on ``UiScale.scale_changed`` (the toolkit ``Label``
does). At 125%/150% interface scale the surrounding controls grew while the
labels stayed at the design-size app font.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import UiScale, scaled_px

from plugins.export.dialog_sections import build_format_row
from ui.widgets.form_controls import OutputPathSection
from sli_ui_toolkit.widgets import CustomLineEdit


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


class _Dialog:
    def __init__(self, parent: QWidget) -> None:
        self._parent = parent
        self.fmt_label = None

    def _tr(self, key: str, fallback: str) -> str:
        return fallback

    def _update_controls_visity_by_format(self, *_args) -> None:
        pass


def _label_size(label) -> int:
    return label.font().pixelSize()


def test_export_dialog_labels_scale_live(qapp: QApplication):
    host = QWidget()
    host.show()

    dialog = _Dialog(host)
    build_format_row(dialog)
    dialog.fmt_label.show()

    base = _label_size(dialog.fmt_label)
    assert base > 0

    UiScale.get_instance().set_factor(1.5)
    assert _label_size(dialog.fmt_label) == scaled_px(12) == 18

    UiScale.get_instance().set_factor(1.0)
    assert _label_size(dialog.fmt_label) == base

    host.close()


def test_output_path_section_labels_scale_live(qapp: QApplication):
    host = QWidget()
    host.show()

    section = OutputPathSection(
        directory_label_text="Dir:",
        browse_text="Browse...",
        set_favorite_text="Set as Favorite",
        use_favorite_text="Use Favorite",
        filename_label_text="File name:",
        use_custom_line_edit=False,
        parent=host,
    )
    section.show()

    base = _label_size(section.dir_label)
    assert base > 0

    UiScale.get_instance().set_factor(1.5)
    assert _label_size(section.dir_label) == scaled_px(12)
    assert _label_size(section.filename_label) == scaled_px(12)

    host.close()


def test_export_output_editors_are_custom_line_edits_and_scale_live(qapp: QApplication):
    """Export output path editors must be toolkit CustomLineEdit (like the
    video editor), not plain QLineEdit: a plain editor never re-resolves its
    font on ``UiScale.scale_changed`` and stays stuck at the old height when
    the interface scale increases.
    """
    from plugins.export.dialog_sections import build_output_path_section

    class _Dialog:
        def _tr(self, key: str, fallback: str) -> str:
            return fallback

        def _choose_directory(self) -> None:
            pass

        def _set_favorite_from_current(self) -> None:
            pass

        def _use_favorite_dir(self) -> None:
            pass

        def _harden_text_buttons(self, *buttons) -> None:
            pass

    dialog = _Dialog()
    build_output_path_section(dialog)
    host = QWidget()
    for widget in (dialog.edit_dir, dialog.edit_name):
        widget.setParent(host)
        widget.show()
    host.show()

    assert isinstance(dialog.edit_dir, CustomLineEdit)
    assert isinstance(dialog.edit_name, CustomLineEdit)

    base_dir_h = dialog.edit_dir.height()
    base_name_h = dialog.edit_name.height()
    assert base_dir_h > 0 and base_name_h > 0

    UiScale.get_instance().set_factor(2.0)
    assert dialog.edit_dir.height() > base_dir_h
    assert dialog.edit_name.height() > base_name_h

    host.close()