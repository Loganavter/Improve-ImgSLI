from __future__ import annotations

from typing import Any


def has_initial_canvas_content(store: Any) -> bool:
    document = getattr(store, "document", None)
    viewport = getattr(store, "viewport", None)
    if document is None:
        return False
    if getattr(document, "image1_path", None) and getattr(document, "image2_path", None):
        return True
    single_mode = int(
        getattr(
            getattr(viewport, "view_state", None),
            "showing_single_image_mode",
            0,
        )
        or 0
    )
    if single_mode == 1:
        return bool(
            getattr(document, "image1_path", None)
            or getattr(document, "original_image1", None)
        )
    if single_mode == 2:
        return bool(
            getattr(document, "image2_path", None)
            or getattr(document, "original_image2", None)
        )
    return False


def refresh_startup_button_visuals(ui: Any) -> None:
    for attr_name in (
        "btn_magnifier_color_settings",
        "btn_magnifier_color_settings_beginner",
    ):
        button = getattr(ui, attr_name, None)
        if button is not None and hasattr(button, "refresh_visual_state"):
            button.refresh_visual_state()
