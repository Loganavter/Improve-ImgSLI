from typing import Dict, List

LAYOUT_DEFINITIONS: Dict[str, List[str]] = {

    "theme_selector": [
        "settings.auto",
        "settings.light",
        "settings.dark"
    ],
    "resolution_selector": [
        "settings.original",
        "settings.resolution_8k",
        "settings.resolution_4k",
        "settings.resolution_2k",
        "settings.resolution_full_hd"
    ],
    "interpolation_selector": [
        "magnifier.nearest_neighbor",
        "magnifier.bilinear",
        "magnifier.bicubic",
        "magnifier.lanczos",
        "magnifier.ewa_lanczos"
    ],

    "settings_sidebar": [
        "settings.appearance",
        "label.view",
        "settings.optimization",
        "label.details"
    ],
    "help_sidebar": [
        "help.help_section_introduction",
        "help.help_section_file_management",
        "help.help_section_basic_comparison",
        "magnifier.help_section_magnifier_tool",
        "help.help_section_exporting_results",
        "help.help_section_settings",
        "help.help_section_hotkeys"
    ],

    "video_editor_tabs": [
        "video.standard",
        "video.manual_cli",
        "label.output"
    ]
}

LAYOUT_CONFIG = {
    "theme_selector":         {"strategy": "max", "padding": 50},
    "resolution_selector":    {"strategy": "max", "padding": 50},
    "interpolation_selector": {"strategy": "max", "padding": 50},

    "settings_sidebar":       {"strategy": "max", "padding": 85},
    "help_sidebar":           {"strategy": "max", "padding": 70},

    "video_editor_tabs":      {"strategy": "sum", "item_padding": 40}
}
