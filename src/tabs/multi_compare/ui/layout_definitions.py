from __future__ import annotations

from typing import Dict, List

LAYOUT_DEFINITIONS: Dict[str, Dict[str, List[str]]] = {
    "beginner": {
        "line_group": [
            "btn_divider_visible",
            "btn_divider_color",
            "btn_divider_width",
        ],
        "label_group": ["btn_text_settings"],
        "action_group": ["btn_quick_save"],
    },
    "expert": {
        "line_group": ["btn_divider_width"],
        "label_group": ["btn_text_settings"],
        "action_group": ["btn_quick_save"],
    },
    "advanced": {
        "line_group": ["btn_divider_color", "btn_divider_width"],
        "label_group": ["btn_text_settings"],
        "action_group": ["btn_quick_save"],
    },
    "minimal": {
        "line_group": [],
        "label_group": ["btn_text_settings"],
        "action_group": [],
    },
}

ALL_KNOWN_WIDGETS = {
    "btn_divider_visible",
    "btn_divider_color",
    "btn_divider_width",
    "btn_text_settings",
    "btn_quick_save",
}
