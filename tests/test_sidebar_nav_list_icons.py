import os
import sys

from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        "packages",
        "sli-ui-toolkit",
        "src",
    ),
)

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.sidebar_nav_list import SidebarNavList

def _solid_icon(color: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)

def test_sidebar_nav_list_builds_selected_icon_variant():
    app = QApplication.instance() or QApplication([])

    theme = ThemeManager.get_instance()
    theme.register_palettes(
        {
            "HighlightedText": QColor("#ff3366"),
        }
    )
    theme.set_theme("light", app)

    widget = SidebarNavList()
    widget.set_nav_items([("General", _solid_icon("#000000"))])

    icon = widget.item(0).icon()
    selected = icon.pixmap(widget.iconSize(), QIcon.Mode.Selected, QIcon.State.Off)
    normal = icon.pixmap(widget.iconSize(), QIcon.Mode.Normal, QIcon.State.Off)

    assert not selected.isNull()
    assert normal.toImage().pixelColor(8, 8) == QColor("#000000")
    assert selected.toImage().pixelColor(8, 8) == QColor("#ff3366")
