\
\
\
\

import os
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from shared_toolkit.ui.widgets.atomic.custom_button import CustomButton
from shared_toolkit.utils.paths import resource_path
from shared_toolkit.ui.managers.theme_manager import ThemeManager

class BaseDialog(QDialog):
    """
    Base dialog class with standard setup.

    Provides common functionality for all dialogs:
    - Window flags setup
    - Icon setup
    - Theme manager connection
    - Standard sizing
    """

    def __init__(self, parent=None, title="", min_width=350, min_height=0):
        super().__init__(parent)
        self.setObjectName(f"{self.__class__.__name__}")
        self.theme_manager = ThemeManager.get_instance()

        self._setup_window(title, min_width, min_height)
        self._setup_icon()
        self._setup_theme()

    def _setup_window(self, title, min_width, min_height):
        """Sets up window properties."""
        if title:
            self.setWindowTitle(title)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)

        if min_width > 0:
            self.setMinimumWidth(min_width)
        if min_height > 0:
            self.setMinimumHeight(min_height)

    def _setup_icon(self):
        """Sets up window icon from resources."""
        setup_dialog_icon(self)

    def _setup_theme(self):
        """Connects to theme manager."""
        self.theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self):
        """Override this method to handle theme changes."""
        self.update()

def setup_dialog_scaffold(
    dialog: QDialog,
    main_layout: QVBoxLayout,
    ok_text: str,
    cancel_text: str = "Cancel",
    show_cancel_button: bool = True,
):
    """
    Creates standard OK/Cancel button layout for dialog.

    Args:
        dialog: Dialog to add buttons to
        main_layout: Main layout to add buttons layout to
        ok_text: Text for OK button
        cancel_text: Text for Cancel button
        show_cancel_button: Whether to show cancel button

    Creates:
        dialog.ok_button: CustomButton for OK action
        dialog.cancel_button: CustomButton for Cancel action
    """
    buttons_layout = QHBoxLayout()
    buttons_layout.addStretch()

    dialog.ok_button = CustomButton(None, ok_text)
    dialog.ok_button.setProperty("class", "primary")
    dialog.ok_button.setFixedSize(100, 30)
    dialog.cancel_button = CustomButton(None, cancel_text)
    dialog.cancel_button.setFixedSize(100, 30)

    dialog.ok_button.clicked.connect(dialog.accept)
    dialog.cancel_button.clicked.connect(dialog.reject)

    buttons_layout.addWidget(dialog.ok_button)
    if show_cancel_button:
        buttons_layout.addWidget(dialog.cancel_button)

    main_layout.addLayout(buttons_layout)

def setup_dialog_icon(dialog: QDialog, icon_path: str = None):
    """
    Sets icon for dialog window.

    Args:
        dialog: Dialog to set icon for
        icon_path: Optional custom icon path. If None, tries default from resources.
    """
    if icon_path is None:

        try:
            icon_path = resource_path("resources/icons/icon.png")
        except:
            return

    if icon_path and os.path.exists(icon_path):
        dialog.setWindowIcon(QIcon(icon_path))

def auto_size_dialog(dialog: QDialog, min_width: int = 300, min_height: int = 200):
    """
    Automatically calculates and sets dialog sizes based on content.

    This function schedules size calculation for the next event loop iteration
    to ensure all widgets are properly laid out first.

    Args:
        dialog: Dialog to update sizes for
        min_width: Minimum width
        min_height: Minimum height
    """

    def _recalculate_sizes():

        dialog.adjustSize()

        content_size = dialog.sizeHint()

        final_width = max(min_width, content_size.width() + 50)
        final_height = max(min_height, content_size.height() + 30)

        dialog.setMinimumSize(final_width, final_height)

        _update_group_sizes(dialog)

    QTimer.singleShot(0, _recalculate_sizes)

def _update_group_sizes(dialog: QDialog):
    """
    Updates sizes of styled groups in dialog.

    Searches for CustomGroupWidget instances and updates their minimum widths
    based on content and title sizes.
    """
    for child in dialog.findChildren(QWidget):
        if child.objectName() == "StyledGroupFrame":
            parent_group = child.parent()
            if parent_group:

                content_width = child.sizeHint().width()
                min_width = content_width + 30

                for title_child in parent_group.findChildren(QLabel):
                    if title_child.objectName() == "StyledGroupTitle":
                        title_width = title_child.width() + 40
                        min_width = max(min_width, title_width)
                        break

                parent_group.setMinimumWidth(min_width)

