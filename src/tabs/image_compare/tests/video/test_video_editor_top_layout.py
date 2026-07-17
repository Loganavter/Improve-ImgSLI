"""Video editor top-row layout: preview vs settings panel."""

from __future__ import annotations

from types import SimpleNamespace

from tabs.image_compare.plugins.video_editor.layout_geometry import (
    MIN_VIDEO_EDITOR_PREVIEW_WIDTH,
    MIN_VIDEO_EDITOR_SETTINGS_WIDTH,
    VIDEO_EDITOR_TOP_HORIZONTAL_SPACING_PX,
    VIDEO_EDITOR_TOP_MARGIN_PX,
    compute_minimum_dialog_width,
    compute_settings_panel_width,
)


def test_minimum_dialog_width_tracks_settings_width():
    settings_width = 430
    required = compute_minimum_dialog_width(settings_width)
    assert required == (
        VIDEO_EDITOR_TOP_MARGIN_PX
        + MIN_VIDEO_EDITOR_PREVIEW_WIDTH
        + VIDEO_EDITOR_TOP_HORIZONTAL_SPACING_PX
        + settings_width
    )


def test_compute_settings_panel_width_uses_widest_section():
    dialog = SimpleNamespace(
        settings_static_container=SimpleNamespace(
            ensurePolished=lambda: None,
            adjustSize=lambda: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: 360),
        ),
        tabs=SimpleNamespace(
            ensurePolished=lambda: None,
            count=lambda: 1,
            widget=lambda _index: SimpleNamespace(
                ensurePolished=lambda: None,
                adjustSize=lambda: None,
                sizeHint=lambda: SimpleNamespace(width=lambda: 510),
                findChild=lambda *_a, **_k: None,
            ),
            tabBar=lambda: SimpleNamespace(
                ensurePolished=lambda: None,
                sizeHint=lambda: SimpleNamespace(width=lambda: 320),
            ),
            parentWidget=lambda: None,
        ),
        btn_export=SimpleNamespace(
            ensurePolished=lambda: None,
            adjustSize=lambda: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: 280),
        ),
    )

    # Page content 510 + content_layout margins (12+12); tab strip 320+24 loses.
    assert compute_settings_panel_width(dialog) == 534
    assert compute_minimum_dialog_width(534) >= MIN_VIDEO_EDITOR_SETTINGS_WIDTH

def test_compute_settings_panel_width_includes_tab_parent_margins():
    from tabs.image_compare.plugins.video_editor.layout_geometry import (
        VIDEO_EDITOR_TABS_CONTENT_H_MARGINS_PX,
    )

    dialog = SimpleNamespace(
        settings_static_container=SimpleNamespace(
            ensurePolished=lambda: None,
            adjustSize=lambda: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: 200),
        ),
        tabs=SimpleNamespace(
            ensurePolished=lambda: None,
            count=lambda: 0,
            widget=lambda _index: None,
            tabBar=lambda: SimpleNamespace(
                ensurePolished=lambda: None,
                sizeHint=lambda: SimpleNamespace(width=lambda: 400),
            ),
            parentWidget=lambda: None,
        ),
        btn_export=SimpleNamespace(
            ensurePolished=lambda: None,
            adjustSize=lambda: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: 100),
        ),
    )

    assert compute_settings_panel_width(dialog) == (
        400 + VIDEO_EDITOR_TABS_CONTENT_H_MARGINS_PX
    )