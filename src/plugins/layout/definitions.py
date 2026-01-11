from typing import Dict, List

LAYOUT_DEFINITIONS: Dict[str, Dict[str, List[str]]] = {
    "beginner": {
        "line_group": [
            "btn_orientation_simple", "btn_divider_visible",
            "btn_divider_color", "btn_divider_width"
        ],
        "view_group": [
            "btn_diff_mode", "btn_channel_mode", "btn_file_names"
        ],
        "magnifier_group": [
            "btn_magnifier", "btn_freeze",
            "btn_magnifier_orientation_simple",
            "btn_magnifier_divider_visible",
            "btn_magnifier_color_settings_beginner",
            "btn_magnifier_divider_width",
            "btn_magnifier_guides_simple",
            "btn_magnifier_guides_width"
        ],
        "record_group": [
            "btn_record", "btn_pause", "btn_video_editor"
        ]
    },
    "expert": {
        "line_group": [
            "btn_orientation"
        ],
        "view_group": [
            "btn_diff_mode", "btn_channel_mode", "btn_file_names"
        ],
        "magnifier_group": [
            "btn_magnifier", "btn_freeze",
            "btn_magnifier_orientation",
            "btn_magnifier_color_settings",
            "btn_magnifier_guides"
        ],
        "record_group": [
            "btn_record", "btn_pause", "btn_video_editor"
        ]
    },
    "advanced": {
        "line_group": [
            "btn_orientation", "btn_divider_color"
        ],
        "view_group": [
            "btn_diff_mode", "btn_channel_mode", "btn_file_names"
        ],
        "magnifier_group": [
            "btn_magnifier", "btn_magnifier_orientation", "btn_freeze",
            "btn_magnifier_color_settings", "btn_magnifier_guides"
        ],
        "record_group": [
            "btn_record", "btn_pause", "btn_video_editor"
        ]
    },

    "minimal": {
        "line_group": ["btn_orientation_simple"],
        "view_group": [],
        "magnifier_group": ["btn_magnifier"],
        "record_group": []
    }
}

ALL_KNOWN_WIDGETS = {
    "btn_orientation", "btn_orientation_simple",
    "btn_divider_visible", "btn_divider_color", "btn_divider_width",
    "btn_magnifier_orientation", "btn_magnifier_orientation_simple",
    "btn_magnifier_divider_visible", "btn_magnifier_divider_width",
    "btn_magnifier_color_settings", "btn_magnifier_color_settings_beginner",
    "btn_magnifier_guides", "btn_magnifier_guides_simple", "btn_magnifier_guides_width",
    "btn_diff_mode", "btn_channel_mode", "btn_file_names",
    "btn_record", "btn_pause", "btn_video_editor"
}

