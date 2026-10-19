"""Allowlist for the live-appearance drain guard.

``tests/contracts/test_live_appearance_drain_guard.py`` requires every
live-appearance test (one that moves the coalesced metrics channel and then
asserts widget geometry / label metrics) to drain that channel before the
assertion. This module is the escape hatch for the cases the static predicate
cannot separate from a real trap.

Entry shape — ``"<repo-relative path>"`` (whole file) or
``"<repo-relative path>::<test function name>"`` (one test): a non-empty
reason string. Both halves are verified by the guard: the file must exist,
a ``::test`` suffix must name a real function in it, and an entry that no
longer suppresses a finding fails the gate so the list cannot rot (ratchet).
"""

from __future__ import annotations

#: ``entry -> why this is not an undrained live-appearance assertion``.
ALLOWLIST: dict[str, str] = {
    "tests/test_context_menu.py::test_popup_at_offsets_from_cursor": (
        "the context menu is CONSTRUCTED after set_factor(1.5); the asserted "
        "offsets are computed from that construction-time metric, so there is "
        "no deferrable re-derivation to wait for"
    ),
    "tests/runtime/test_scroll_value_button_hover.py::test_value_flyout_label_reflows_after_live_scale_change": (
        "the first geometry assert reads the flyout built at the baseline "
        "factor; the post-change read follows a pytest-qt wait() event-loop "
        "turn (kept as-is: the test asserts growth, not an exact stale value)"
    ),
    "src/tabs/image_gallery/tests/test_gallery_switch_ui_scale.py::test_ask_ai_images_toggle_scales_once_at_build": (
        "build-time factor^2 guard: it reads 1.0 geometry BEFORE constructing "
        "at 1.5 and compares two separately built widgets; nothing is asserted "
        "on a live widget after a factor change"
    ),
    "tests/test_context_menu.py::test_submenu_rows_get_the_scaled_ui_font": (
        "the menu and its submenu are CONSTRUCTED after set_factor(2.0); the "
        "toolkit rows resolve the scale-resolved font at build time, so the "
        "assertion reads no deferred re-derivation"
    ),
    "src/tabs/image_compare/tests/runtime/test_interp_flyout_design_metrics.py::test_live_combo_metrics_convert_to_design_values": (
        "pure model test: no widget; converts the combo's live metrics into "
        "design values with a font object built at the current factor"
    ),
    "src/tabs/image_compare/tests/runtime/test_interp_flyout_design_metrics.py::test_pixel_size_fonts_convert_proportionally": (
        "pure model test: no live widget; asserts the design-value conversion "
        "helpers with a font object built at the current factor"
    ),
    "src/tabs/image_compare/tests/runtime/test_interp_flyout_design_metrics.py::test_design_metrics_roundtrip_stays_single_scaled": (
        "pure model test: row height/font are passed explicitly to the flyout "
        "and read back synchronously; the metrics bus is not involved"
    ),
    "src/tabs/image_compare/tests/runtime/test_magnifier_settings_flyout_icons_scale.py::test_icon_label_renders_at_current_scale": (
        "the label is CONSTRUCTED at 1.5; its size is resolved synchronously "
        "from the live factor in the constructor (no coalesced re-derivation)"
    ),
    "src/tabs/image_compare/tests/runtime/test_magnifier_settings_flyout_position.py::test_flyout_left_edge_tracks_group_border_box": (
        "every widget (group, window, flyout) is constructed after the "
        "parametrized factor is applied; the asserted edges are laid out at "
        "that same factor, not re-derived by a later change"
    ),
    "src/tabs/image_compare/tests/video/test_video_editor_output_tab_scale.py::test_output_tab_buttons_scale_live": (
        "pre-existing offender: a live factor change followed by a single "
        "qapp.processEvents(); quarantined pending migration to "
        "drain_until_stable (assertions are growth, so it cannot pass on the "
        "pre-flush value by accident)"
    ),
    "src/tabs/image_compare/tests/video/test_video_editor_output_tab_scale.py::test_output_path_section_repapplies_explicit_sizes_on_scale": (
        "pre-existing offender: a live factor change followed by a single "
        "qapp.processEvents(); quarantined pending migration to "
        "drain_until_stable"
    ),
    "src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py::test_scale_above_1_bare_panel_cap_is_scaled": (
        "the panel is CONSTRUCTED and refreshed at 1.5; the scroll-area height "
        "is read from that build, not from a deferred re-derivation"
    ),
}
