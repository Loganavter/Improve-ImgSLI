from __future__ import annotations

from core.constants import AppConstants
from tabs.registry import get_shared_tab_registry

class SettingsViewStateCoordinator:
    def __init__(self, store, tr_func):
        self.store = store
        self.tr = tr_func

    def update_interpolation_combo_box_ui(self):
        method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())

        interp_translation_map = {
            "NEAREST": "magnifier.nearest_neighbor",
            "BILINEAR": "magnifier.bilinear",
            "BICUBIC": "magnifier.bicubic",
            "LANCZOS": "magnifier.lanczos",
            "EWA_LANCZOS": "magnifier.ewa_lanczos",
        }

        target_method_key = self.store.viewport.render_config.interpolation_method
        if target_method_key not in method_keys:
            target_method_key = (
                AppConstants.DEFAULT_INTERPOLATION_METHOD
                if AppConstants.DEFAULT_INTERPOLATION_METHOD in method_keys
                else (
                    method_keys[0]
                    if method_keys
                    else AppConstants.DEFAULT_INTERPOLATION_METHOD
                )
            )
            self.store.viewport.render_config.interpolation_method = target_method_key

        try:
            current_index = method_keys.index(target_method_key)
        except ValueError:
            current_index = 0

        labels = [
            self.tr(
                interp_translation_map.get(
                    key,
                    f"magnifier.{AppConstants.INTERPOLATION_METHODS_MAP[key].lower().replace(' ', '_')}",
                )
            )
            for key in method_keys
        ]
        display_text = labels[current_index] if 0 <= current_index < len(labels) else ""

        tab = get_shared_tab_registry().get_active_tab()
        if tab is not None:
            tab.create_service(
                "sync_interpolation_combo_state",
                count=len(method_keys),
                current_index=current_index,
                text=display_text,
                items=labels,
            )

    def setup_view_buttons(self):
        diff_actions = [
            (self.tr("common.switch.off"), "off"),
            (self.tr("video.highlight"), "highlight"),
            (self.tr("video.grayscale"), "grayscale"),
            (self.tr("video.edge_comparison"), "edges"),
            (self.tr("video.ssim_map"), "ssim"),
        ]
        channel_actions = [
            (self.tr("video.rgb"), "RGB"),
            (self.tr("video.red"), "R"),
            (self.tr("video.green"), "G"),
            (self.tr("video.blue"), "B"),
            (self.tr("video.luminance"), "L"),
        ]

        tab = get_shared_tab_registry().get_active_tab()
        if tab is not None:
            tab.create_service(
                "setup_view_mode_buttons",
                diff_actions=diff_actions,
                diff_mode=self.store.viewport.view_state.diff_mode,
                channel_actions=channel_actions,
                channel_mode=self.store.viewport.view_state.channel_view_mode,
            )
