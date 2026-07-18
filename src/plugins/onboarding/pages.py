from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QColorDialog, QLabel, QHBoxLayout, QVBoxLayout, QWidget

from plugins.onboarding.icons import DemoIcon
from resources.translations import tr
from sli_ui_toolkit.widgets import Button
from ui.theming import polish_themed_dialog, resolve_theme_color
from ui.widgets.scroll_value_button import ScrollValueButton

# Larger than live toolbar so the onboarding demos read clearly on slides.
_DEMO_BTN_BASE_PX = 56
_DEMO_ICON_BASE_PX = 28


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
    page._onboarding_root_layout = layout

    lbl_title = QLabel(mode_data["name"])
    lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl_title)
    page._onboarding_title = lbl_title

    demo_container = QWidget()
    demo_layout = QHBoxLayout(demo_container)
    demo_layout.setSpacing(35)
    demo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    page._onboarding_demo_layout = demo_layout
    page._onboarding_demo_buttons = []
    page._onboarding_captions = []
    page._onboarding_caption_layouts = []

    current_lang = getattr(overlay.store.settings, "current_language", "en")
    key = mode_data["key"]

    if key == "beginner":
        _add_beginner_demo(overlay, page, demo_container, demo_layout, current_lang)
    elif key == "advanced":
        _add_advanced_demo(overlay, page, demo_container, demo_layout, current_lang)
    elif key == "expert":
        _add_expert_demo(overlay, page, demo_container, demo_layout, current_lang)

    layout.addWidget(demo_container)
    desc = _create_description_label(overlay, mode_data.get("desc", ""))
    layout.addWidget(desc)
    page._onboarding_desc = desc

    # First paint must already use UiFont + scaled metrics (not bare QFont()).
    scale_slide(overlay, page, getattr(overlay, "_last_scale", 1.0) or 1.0)
    return page


def scale_slide(overlay, page, scale: float) -> None:
    """Re-apply UiFont + sizes for one mode slide (chrome is handled in overlay)."""
    base = overlay._ui_base_font()
    title = getattr(page, "_onboarding_title", None)
    if title is not None:
        font = QFont(base)
        # Historical look used pointSize 24 (~32px); keep pixel sizing consistent.
        font.setPixelSize(max(18, int(32 * scale)))
        font.setBold(True)
        title.setFont(font)

    desc = getattr(page, "_onboarding_desc", None)
    if desc is not None:
        font = QFont(base)
        font.setPixelSize(max(12, int(16 * scale)))
        desc.setFont(font)
        desc.setContentsMargins(0, max(8, int(15 * scale)), 0, 0)

    root = getattr(page, "_onboarding_root_layout", None)
    if root is not None:
        root.setSpacing(max(12, int(30 * scale)))

    demo_layout = getattr(page, "_onboarding_demo_layout", None)
    if demo_layout is not None:
        demo_layout.setSpacing(max(14, int(35 * scale)))

    btn_size = max(44, int(_DEMO_BTN_BASE_PX * scale))
    icon_px = max(20, int(_DEMO_ICON_BASE_PX * scale))
    for btn in getattr(page, "_onboarding_demo_buttons", []) or []:
        _style_demo_btn(btn, size=btn_size, icon_px=icon_px)

    caption_px = max(11, int(13 * scale))
    caption_font = QFont(base)
    caption_font.setPixelSize(caption_px)
    caption_font.setWeight(QFont.Weight.Medium)
    for lbl in getattr(page, "_onboarding_captions", []) or []:
        lbl.setFont(caption_font)

    for wrap in getattr(page, "_onboarding_caption_layouts", []) or []:
        wrap.setSpacing(max(4, int(8 * scale)))


def scale_all_slides(overlay, scale: float) -> None:
    for page in getattr(overlay, "_slide_widgets", []) or []:
        scale_slide(overlay, page, scale)


def _add_beginner_demo(overlay, page, demo_container, demo_layout, current_lang: str) -> None:
    # Mirrors image_compare primitives: orientation_simple, divider_visible,
    # divider_color, divider_width — default unchecked / no forced demo state.
    b1 = Button(
        icon=(DemoIcon.VERTICAL_SPLIT, DemoIcon.HORIZONTAL_SPLIT),
        toggle=True,
        parent=demo_container,
    )
    b2 = Button(
        icon=(DemoIcon.DIVIDER_VISIBLE, DemoIcon.DIVIDER_HIDDEN),
        toggle=True,
        parent=demo_container,
    )
    # Color keeps underline (IC btn_divider_color); width has none (IC btn_divider_width).
    b3 = Button(DemoIcon.DIVIDER_COLOR, show_underline=True, parent=demo_container)
    accent_color = resolve_theme_color(overlay.theme_manager, "accent")
    b3.setUnderlineColor(accent_color)

    def _on_beginner_color_clicked():
        _show_color_dialog(overlay, b3, b3._custom_color or accent_color, current_lang)

    b3.clicked.connect(_on_beginner_color_clicked)

    b4 = ScrollValueButton(
        icon=DemoIcon.DIVIDER_WIDTH,
        min_value=0,
        max_value=10,
        zero_icon=DemoIcon.DIVIDER_HIDDEN,
        parent=demo_container,
    )
    labels = [
        tr("onboarding.beginner.button.rotate", current_lang),
        tr("onboarding.beginner.button.view", current_lang),
        tr("onboarding.beginner.button.color", current_lang),
        tr("onboarding.beginner.button.width", current_lang),
    ]

    for btn, text in ((b1, labels[0]), (b2, labels[1]), (b3, labels[2]), (b4, labels[3])):
        page._onboarding_demo_buttons.append(btn)
        demo_layout.addLayout(_wrap_btn(overlay, page, btn, text))


def _add_advanced_demo(overlay, page, demo_container, demo_layout, current_lang: str) -> None:
    # Combined orientation+width; thickness via wheel — no underline strip on this demo.
    # Color button keeps the accent underline (the paint control).
    b_smart = ScrollValueButton(
        icon=(DemoIcon.VERTICAL_SPLIT, DemoIcon.HORIZONTAL_SPLIT),
        toggle=True,
        min_value=0,
        max_value=10,
        zero_icon=DemoIcon.DIVIDER_HIDDEN,
        parent=demo_container,
    )
    b_smart.set_value(3)

    b_color = Button(DemoIcon.DIVIDER_COLOR, show_underline=True, parent=demo_container)
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

    for btn, text in ((b_smart, txts[0]), (b_color, txts[1])):
        page._onboarding_demo_buttons.append(btn)
        demo_layout.addLayout(_wrap_btn(overlay, page, btn, text))


def _add_expert_demo(overlay, page, demo_container, demo_layout, current_lang: str) -> None:
    # Same combined control as advanced; expert adds RMB color / MMB reset.
    b_expert = ScrollValueButton(
        icon=(DemoIcon.VERTICAL_SPLIT, DemoIcon.HORIZONTAL_SPLIT),
        toggle=True,
        show_underline=True,
        min_value=0,
        max_value=10,
        zero_icon=DemoIcon.DIVIDER_HIDDEN,
        parent=demo_container,
    )
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

    b_expert.rightClicked.connect(_on_expert_right)
    b_expert.middleClicked.connect(_on_expert_middle)
    info_txt = tr("onboarding.expert.button.info", current_lang)

    page._onboarding_demo_buttons.append(b_expert)
    demo_layout.addLayout(_wrap_btn(overlay, page, b_expert, info_txt))


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
        if not color.isValid():
            return
        button._custom_color = color
        if getattr(button, "_show_underline", False):
            button.setUnderlineColor(color)

    color_dialog.colorSelected.connect(on_color_selected)
    color_dialog.finished.connect(lambda _r, b=button: setattr(b, "_color_dialog", None))
    color_dialog.show()
    button._color_dialog = color_dialog


def _create_description_label(overlay, text: str) -> QLabel:
    lbl_desc_main = QLabel(text)
    lbl_desc_main.setAlignment(Qt.AlignmentFlag.AlignCenter)
    text_col = resolve_theme_color(overlay.theme_manager, "dialog.text").name()
    desc_palette = lbl_desc_main.palette()
    desc_palette.setColor(lbl_desc_main.foregroundRole(), QColor(text_col))
    lbl_desc_main.setPalette(desc_palette)
    return lbl_desc_main


def _style_demo_btn(
    btn, size: int = _DEMO_BTN_BASE_PX, icon_px: int = _DEMO_ICON_BASE_PX
) -> None:
    """Size only — leave painter/checked state to the toolkit like image_compare."""
    btn.setFixedSize(size, size)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if hasattr(btn, "setIconSizePx"):
        btn.setIconSizePx(icon_px)
    if hasattr(btn, "update_styles"):
        btn.update_styles()
    btn.update()


def _wrap_btn(overlay, page, btn, text):
    layout = QVBoxLayout()
    layout.setSpacing(8)
    layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
    page._onboarding_caption_layouts.append(layout)
    if text:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_col = resolve_theme_color(overlay.theme_manager, "list_item.text.rating").name()
        label_palette = lbl.palette()
        label_palette.setColor(lbl.foregroundRole(), QColor(text_col))
        lbl.setPalette(label_palette)
        layout.addWidget(lbl)
        page._onboarding_captions.append(lbl)
    return layout
