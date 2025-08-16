from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication
import logging

logger = logging.getLogger("ImproveImgSLI")

LIGHT_THEME_PALETTE = {
    "Window": QColor("#ffffff"),
    "WindowText": QColor("#1f1f1f"),
    "Base": QColor("#ffffff"),
    "AlternateBase": QColor("#e1e1e1"),
    "ToolTipBase": QColor("#ffffff"),
    "ToolTipText": QColor("#1f1f1f"),
    "Text": QColor("#1f1f1f"),
    "Button": QColor("#e1e1e1"),
    "ButtonText": QColor("#1f1f1f"),
    "BrightText": QColor("#ff0000"),
    "Highlight": QColor("#0078D4"),
    "HighlightedText": QColor("#ffffff"),

    "accent": QColor("#0078D4"),
    "button.default.background": QColor("#140078D7"),
    "button.default.background.hover": QColor("#2D0078D7"),
    "button.default.background.pressed": QColor("#2D0078D7"),
    "button.default.border": QColor("#1E000000"),
    "button.default.bottom.edge": QColor("#32000000"),
    "button.delete.background": QColor("#26D93025"),
    "button.delete.background.hover": QColor("#4CD93025"),
    "button.delete.background.pressed": QColor("#4CD93025"),
    "button.delete.border": QColor("#66D93025"),

    "button.primary.background": QColor("#ffffff"),
    "button.primary.background.hover": QColor("#f8f8f8"),
    "button.primary.background.pressed": QColor("#e9e9e9"),
    "button.primary.border": QColor("#1E000000"),
    "button.primary.bottom.edge": QColor("#32000000"),

    "button.primary.text": QColor("#000000"),

    "input.border.thin": QColor("#2D000000"),
    "flyout.background": QColor("#ffffff"),
    "flyout.border": QColor("#e0e0e0"),
    "list_item.background.normal": QColor("#ffffff"),
    "list_item.background.hover": QColor("#f5f5f5"),
    "list_item.text.normal": QColor("#000000"),
    "list_item.text.rating": QColor("#7f7f7f"),
    "separator.color": QColor("#e5e5e5"),
    "shadow.color": QColor("#64000000"),
    "dialog.background": QColor("#f0f0f0"),
    "dialog.text": QColor("#1f1f1f"),
    "dialog.border": QColor("#c0c0c0"),
    "dialog.input.background": QColor("#ffffff"),
    "dialog.button.background": QColor("#e1e1e1"),
    "dialog.button.hover": QColor("#d8d8d8"),
    "dialog.button.ok.background": QColor("#0078D4"),
    "label.image.background": QColor("#ffffff"),
    "help.separator": QColor("#e5e5e5"),
    "help.code.background": QColor("#0D000000"),
    "help.nav.background": QColor("#f0f0f0"),
    "help.nav.border": QColor("#e0e0e0"),
    "help.nav.hover": QColor("#f2f2f2"),
    "help.nav.selected": QColor("#0078D4"),
    "help.nav.selected.text": QColor("#ffffff"),

    "toast.background": QColor("#ffffff"),
    "toast.text": QColor("#000000"),
    "toast.border": QColor("#19000000"),

    "slider.track.background": QColor("#929292"),
    "slider.track.unfilled": QColor("#706f6f"),
    "slider.thumb.outer": QColor("#ffffff"),

    "switch.track.off.border": QColor("#6E000000"),
    "switch.knob.off": QColor("#646464"),
    "switch.knob.on": QColor("#ffffff"),
    "switch.knob.border": QColor("#23000000"),
    "switch.text": QColor("#1f1f1f"),

    "tooltip.background": QColor("#ffffff"),
    "tooltip.text": QColor("#1f1f1f"),
    "tooltip.border": QColor("#c0c0c0"),

    "color_dialog.background": QColor("#f0f0f0"),
    "color_dialog.text": QColor("#1f1f1f"),
    "color_dialog.input.background": QColor("#ffffff"),
    "color_dialog.input.border": QColor("#c0c0c0"),
}

DARK_THEME_PALETTE = {
    "Window": QColor("#2b2b2b"),
    "WindowText": QColor("#dfdfdf"),
    "Base": QColor("#3c3c3c"),
    "AlternateBase": QColor("#313131"),
    "ToolTipBase": QColor("#3c3c3c"),
    "ToolTipText": QColor("#dfdfdf"),
    "Text": QColor("#dfdfdf"),
    "Button": QColor("#3c3c3c"),
    "ButtonText": QColor("#dfdfdf"),
    "BrightText": QColor("#ff0000"),
    "Highlight": QColor("#0096FF"),
    "HighlightedText": QColor("#ffffff"),

    "accent": QColor("#0096FF"),
    "button.default.background": QColor("#1E0096FF"),
    "button.default.background.hover": QColor("#3C0096FF"),
    "button.default.background.pressed": QColor("#3C0096FF"),
    "button.default.border": QColor("#26FFFFFF"),
    "button.default.bottom.edge": QColor("#1EFFFFFF"),
    "button.delete.background": QColor("#33D93025"),
    "button.delete.background.hover": QColor("#66D93025"),
    "button.delete.background.pressed": QColor("#66D93025"),
    "button.delete.border": QColor("#80D93025"),

    "button.primary.background": QColor("#3c3c3c"),
    "button.primary.background.hover": QColor("#4a4a4a"),
    "button.primary.background.pressed": QColor("#555555"),
    "button.primary.border": QColor("#26FFFFFF"),
    "button.primary.bottom.edge": QColor("#1EFFFFFF"),

    "button.primary.text": QColor("#dfdfdf"),

    "input.border.thin": QColor("#3CFFFFFF"),
    "flyout.background": QColor("#383838"),
    "flyout.border": QColor("#4a4a4a"),
    "list_item.background.normal": QColor("#383838"),
    "list_item.background.hover": QColor("#424242"),
    "list_item.text.normal": QColor("#f0f0f0"),
    "list_item.text.rating": QColor("#9a9a9a"),
    "separator.color": QColor("#4f4f4f"),
    "shadow.color": QColor("#50000000"),
    "dialog.background": QColor("#2b2b2b"),
    "dialog.text": QColor("#dfdfdf"),
    "dialog.border": QColor("#555"),
    "dialog.input.background": QColor("#3c3c3c"),
    "dialog.button.background": QColor("#3c3c3c"),
    "dialog.button.hover": QColor("#4f4f4f"),
    "dialog.button.ok.background": QColor("#0096FF"),
    "label.image.background": QColor("#2b2b2b"),
    "help.separator": QColor("#4f4f4f"),
    "help.code.background": QColor("#1AFFFFFF"),
    "help.nav.background": QColor("#313131"),
    "help.nav.border": QColor("#444"),
    "help.nav.hover": QColor("#3c3c3c"),
    "help.nav.selected": QColor("#0096FF"),
    "help.nav.selected.text": QColor("#ffffff"),

    "toast.background": QColor("#F0323232"),
    "toast.text": QColor("#ffffff"),
    "toast.border": QColor("#19FFFFFF"),

    "slider.track.background": QColor("#5a5a5a"),
    "slider.track.unfilled": QColor("#9a9a9a"),
    "slider.thumb.outer": QColor("#454545"),

    "switch.track.off.border": QColor("#78FFFFFF"),
    "switch.knob.off": QColor("#B4B4B4"),
    "switch.knob.on": QColor("#ffffff"),
    "switch.knob.border": QColor("#5A000000"),
    "switch.text": QColor("#dfdfdf"),

    "tooltip.background": QColor("#3c3c3c"),
    "tooltip.text": QColor("#dfdfdf"),
    "tooltip.border": QColor("#555555"),

    "color_dialog.background": QColor("#2b2b2b"),
    "color_dialog.text": QColor("#e0e0e0"),
    "color_dialog.input.background": QColor("#3c3c3c"),
    "color_dialog.input.border": QColor("#555555"),
}

class ThemeManager(QObject):
    _instance = None
    theme_changed = pyqtSignal()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    def __init__(self):
        if ThemeManager._instance is not None:
            raise RuntimeError("ThemeManager is a singleton, use get_instance()")
        super().__init__()
        self._current_theme = None
        self._qss_template = ""
        self._load_qss_template()

    def force_apply_theme(self, theme_name: str, app):
        self._current_theme = "dark" if theme_name == "dark" else "light"
        if app and self._qss_template:
            self.apply_theme_to_app(app)

    def _load_qss_template(self):
        try:
            from utils.resource_loader import resource_path
            import os

            possible_paths = [
                resource_path("resources/styles/base.qss"),
                os.path.join(os.path.dirname(__file__), "..", "resources", "styles", "base.qss"),
                "resources/styles/base.qss"
            ]

            qss_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    qss_path = path
                    break

            if qss_path:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self._qss_template = f.read()
            else:
                self._qss_template = ""
        except Exception as e:
            self._qss_template = ""

    def set_theme(self, theme_name: str, app=None):
        new_theme = "dark" if theme_name == "dark" else "light"

        if self._current_theme != new_theme:
            self._current_theme = new_theme
            if app and self._qss_template:
                self.apply_theme_to_app(app)
            self.theme_changed.emit()

    def apply_theme_to_app(self, app):
        from PyQt6.QtGui import QPalette

        palette_data = DARK_THEME_PALETTE if self.is_dark() else LIGHT_THEME_PALETTE

        q_palette = QPalette()
        color_roles = {
            "Window": QPalette.ColorRole.Window,
            "WindowText": QPalette.ColorRole.WindowText,
            "Base": QPalette.ColorRole.Base,
            "AlternateBase": QPalette.ColorRole.AlternateBase,
            "ToolTipBase": QPalette.ColorRole.ToolTipBase,
            "ToolTipText": QPalette.ColorRole.ToolTipText,
            "Text": QPalette.ColorRole.Text,
            "Button": QPalette.ColorRole.Button,
            "ButtonText": QPalette.ColorRole.ButtonText,
            "BrightText": QPalette.ColorRole.BrightText,
            "Highlight": QPalette.ColorRole.Highlight,
            "HighlightedText": QPalette.ColorRole.HighlightedText,
        }

        for name, role in color_roles.items():
            if name in palette_data:
                q_palette.setColor(role, palette_data[name])

        app.setPalette(q_palette)

        processed_palette = palette_data.copy()
        if 'accent' in processed_palette:
            accent_color = QColor(processed_palette['accent'])
            hover_color = accent_color.lighter(115) if self.is_dark() else accent_color.darker(115)
            processed_palette['accent.hover'] = hover_color

        current_qss = self._qss_template
        sorted_keys = sorted(processed_palette.keys(), key=len, reverse=True)

        for key in sorted_keys:
            color = processed_palette[key]
            if isinstance(color, QColor):
                placeholder = f"@{key}"
                if placeholder in current_qss:
                    current_qss = current_qss.replace(placeholder, color.name(QColor.NameFormat.HexArgb))

        app.setStyleSheet("")
        QApplication.processEvents()

        app.setStyleSheet(current_qss)

        main_window = app.activeWindow()
        if main_window:
            main_window.style().unpolish(main_window)
            main_window.style().polish(main_window)
            main_window.update()

    def is_dark(self) -> bool:
        is_dark = self._current_theme == "dark"
        return is_dark

    def get_color(self, key: str) -> QColor:
        palette = DARK_THEME_PALETTE if self.is_dark() else LIGHT_THEME_PALETTE
        value = palette.get(key)

        if isinstance(value, QColor):
            return value

        return QColor("magenta")
