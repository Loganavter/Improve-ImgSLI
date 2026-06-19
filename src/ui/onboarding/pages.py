from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QColorDialog, QLabel, QHBoxLayout, QVBoxLayout, QWidget

from resources.translations import tr
from sli_ui_toolkit.widgets import Button
from ui.icon_manager import AppIcon
from ui.theming import polish_themed_dialog, resolve_theme_color


def build_modes(store) -> list[dict[str, str]]:
    current_lang = getattr(store.settings, "current_language", "en")
    return [
        {
            "key": "beginner",
            "name": tr("settings.ui_mode_beginner", current_lang),
            "desc": tr("onboarding.beginner_description", current_lang),
        },
        {
            "key": "advanced",
            "name": tr("settings.ui_mode_advanced", current_lang),
            "desc": tr("onboarding.advanced_description", current_lang),
        },
        {
            "key": "expert",
            "name": tr("settings.ui_mode_expert", current_lang),
            "desc": tr("onboarding.expert_description", current_lang),
        },
    ]


def create_slide_for_mode(overlay, mode_data):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.setSpacing(30)

    lbl_title = QLabel(mode_data["name"])
    title_font = QFont()
    title_font.setPointSize(24)
    title_font.setBold(True)
    lbl_title.setFont(title_font)
    lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl_title)

    demo_container = QWidget()
    demo_layout = QHBoxLayout(demo_container)
    demo_layout.setSpacing(35)
    demo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    current_lang = getattr(overlay.store.settings, "current_language", "en")
    key = mode_data["key"]

    if key == "beginner":
        _add_beginner_demo(overlay, demo_container, demo_layout, current_lang)
    elif key == "advanced":
        _add_advanced_demo(overlay, demo_container, demo_layout, current_lang)
    elif key == "expert":
        _add_expert_demo(overlay, demo_container, demo_layout, current_lang)

    layout.addWidget(demo_container)
    layout.addWidget(_create_description_label(overlay, mode_data.get("desc", "")))

    return page


def _add_beginner_demo(overlay, demo_container, demo_layout, current_lang: str) -> None:
    b1 = Button(
        icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT),
        toggle=True,
        parent=demo_container,
    )
    _style_demo_btn(b1, checked=True)
    b2 = Button(
        icon=(AppIcon.DIVIDER_VISIBLE, AppIcon.DIVIDER_HIDDEN),
        toggle=True,
        parent=demo_container,
    )
    _style_demo_btn(b2, checked=True)
    b3 = Button(AppIcon.DIVIDER_COLOR, show_underline=True, parent=demo_container)
    _style_demo_btn(b3)
    accent_color = resolve_theme_color(overlay.theme_manager, "accent")
    b3.setUnderlineColor(accent_color)

    def _on_beginner_color_clicked():
        _show_color_dialog(overlay, b3, b3._custom_color or accent_color, current_lang)

    b3.clicked.connect(_on_beginner_color_clicked)

    b4 = Button(
        AppIcon.DIVIDER_WIDTH,
        scrollable=(1, 10),
        show_underline=True,
        parent=demo_container,
    )
    _style_demo_btn(b4)
    b4.setUnderlineColor(accent_color)
    labels = [
        tr("onboarding.beginner.button.rotate", current_lang),
        tr("onboarding.beginner.button.view", current_lang),
        tr("onboarding.beginner.button.color", current_lang),
        tr("onboarding.beginner.button.width", current_lang),
    ]

    demo_layout.addLayout(_wrap_btn(overlay, b1, labels[0]))
    demo_layout.addLayout(_wrap_btn(overlay, b2, labels[1]))
    demo_layout.addLayout(_wrap_btn(overlay, b3, labels[2]))
    demo_layout.addLayout(_wrap_btn(overlay, b4, labels[3]))


def _add_advanced_demo(overlay, demo_container, demo_layout, current_lang: str) -> None:
    b_smart = Button(
        icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT),
        toggle=True,
        scrollable=(0, 20),
        show_underline=True,
        parent=demo_container,
    )
    _style_demo_btn(b_smart, checked=True)
    b_smart.set_value(3)
    b_smart.setUnderlineColor(resolve_theme_color(overlay.theme_manager, "accent"))

    b_color = Button(AppIcon.DIVIDER_COLOR, show_underline=True, parent=demo_container)
    _style_demo_btn(b_color)
    accent_color = resolve_theme_color(overlay.theme_manager, "accent")
    b_color.setUnderlineColor(accent_color)

    def _on_advanced_color_clicked():
        _show_color_dialog(
            overlay,
            b_color,
            b_color._custom_color or accent_color,
            current_lang,
        )

    b_color.clicked.connect(_on_advanced_color_clicked)
    txts = [
        tr("onboarding.advanced.button.rotate_width_hint", current_lang),
        tr("onboarding.advanced.button.color", current_lang),
    ]

    demo_layout.addLayout(_wrap_btn(overlay, b_smart, txts[0]))
    demo_layout.addLayout(_wrap_btn(overlay, b_color, txts[1]))


def _add_expert_demo(overlay, demo_container, demo_layout, current_lang: str) -> None:
    b_expert = Button(
        icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT),
        toggle=True,
        scrollable=(0, 20),
        show_underline=True,
        parent=demo_container,
    )
    _style_demo_btn(b_expert, checked=True)
    b_expert.set_value(3)

    accent_color = resolve_theme_color(overlay.theme_manager, "accent")
    b_expert.setUnderlineColor(accent_color)

    def _on_expert_right():
        _show_color_dialog(
            overlay,
            b_expert,
            b_expert._underline_color or accent_color,
            current_lang,
        )

    def _on_expert_middle():
        current_value = b_expert.get_value()

        if current_value == 0:
            saved_value = b_expert.restore_saved_value()
            if saved_value is not None and saved_value > 0:
                b_expert.set_value(saved_value)
            else:
                b_expert.set_value(3)
        else:
            b_expert.set_saved_value(current_value)
            b_expert.set_value(0)

    def _on_expert_val_changed(val):
        pass

    b_expert.rightClicked.connect(_on_expert_right)
    b_expert.middleClicked.connect(_on_expert_middle)
    b_expert.valueChanged.connect(_on_expert_val_changed)
    info_txt = tr("onboarding.expert.button.info", current_lang)

    demo_layout.addLayout(_wrap_btn(overlay, b_expert, info_txt))


def _show_color_dialog(overlay, button, current_color, current_lang: str) -> None:
    existing = getattr(button, "_color_dialog", None)
    if existing is not None and existing.isVisible():
        existing.raise_()
        existing.activateWindow()
        return

    color_dialog = QColorDialog(current_color, overlay)
    color_dialog.setWindowTitle(tr("ui.select_color", current_lang))
    polish_themed_dialog(overlay.theme_manager, color_dialog)

    def on_color_selected(color):
        if color.isValid():
            button.setUnderlineColor(color)

    color_dialog.colorSelected.connect(on_color_selected)
    color_dialog.finished.connect(lambda _r, b=button: setattr(b, "_color_dialog", None))
    color_dialog.show()
    button._color_dialog = color_dialog


def _create_description_label(overlay, text: str) -> QLabel:
    lbl_desc_main = QLabel(text)
    lbl_desc_main.setAlignment(Qt.AlignmentFlag.AlignCenter)
    text_col = resolve_theme_color(overlay.theme_manager, "dialog.text").name()
    desc_font = lbl_desc_main.font()
    desc_font.setPixelSize(16)
    lbl_desc_main.setFont(desc_font)
    desc_palette = lbl_desc_main.palette()
    desc_palette.setColor(lbl_desc_main.foregroundRole(), QColor(text_col))
    lbl_desc_main.setPalette(desc_palette)
    lbl_desc_main.setContentsMargins(0, 15, 0, 0)
    return lbl_desc_main


def _style_demo_btn(btn, checked=False):
    btn.setFixedSize(40, 40)

    has_scroll = getattr(btn, "_has_scroll", False)
    if has_scroll:
        btn.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
    else:
        btn.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    btn.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, False)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    if hasattr(btn, "set_value"):
        if checked:
            btn.set_value(1)
    elif hasattr(btn, "setChecked"):
        btn.setChecked(checked)

    if hasattr(btn, "update_styles"):
        btn.update_styles()

    if not has_scroll:
        btn.style().unpolish(btn)
        btn.style().polish(btn)
    btn.update()


def _wrap_btn(overlay, btn, text):
    layout = QVBoxLayout()
    layout.setSpacing(8)
    layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
    if text:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_col = resolve_theme_color(overlay.theme_manager, "list_item.text.rating").name()
        label_font = lbl.font()
        label_font.setPixelSize(13)
        label_font.setWeight(500)
        lbl.setFont(label_font)
        label_palette = lbl.palette()
        label_palette.setColor(lbl.foregroundRole(), QColor(text_col))
        lbl.setPalette(label_palette)
        layout.addWidget(lbl)
    return layout
