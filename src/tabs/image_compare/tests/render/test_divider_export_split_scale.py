"""P2 canvas parity: export divider split_pos honors the export scale.

``command_build_export_overlay`` receives the export/display ratio but used
to drop it, so the export divider sat at the display-px position on an
export-sized canvas (up to ~1px off per HiDPI step from the live line).
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.image_compare.canvas.features.divider.commands.registry import (
    command_build_export_overlay,
)


def _store(*, split=0.37, horizontal=False):
    return SimpleNamespace(
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(
                is_horizontal=horizontal,
                split_position_visual=split,
                diff_mode="off",
                canvas_widget_state={},
            )
        )
    )


def _kw():
    return dict(
        content_offset_x=0.0,
        content_offset_y=0.0,
        content_width=1000.0,
        content_height=800.0,
    )


def test_vertical_split_scales_with_scale_x():
    at1 = command_build_export_overlay(_store(), scale_x=1.0, scale_y=1.0, **_kw())
    at2 = command_build_export_overlay(_store(), scale_x=2.0, scale_y=2.0, **_kw())
    assert at1["split_pos"] == 370
    assert at2["split_pos"] == 740


def test_horizontal_split_scales_with_scale_y_not_x():
    at1 = command_build_export_overlay(
        _store(split=0.25, horizontal=True), scale_x=1.0, scale_y=1.0, **_kw()
    )
    at2 = command_build_export_overlay(
        _store(split=0.25, horizontal=True), scale_x=3.0, scale_y=2.0, **_kw()
    )
    assert at1["split_pos"] == 200
    assert at2["split_pos"] == 400


def test_unit_scale_matches_unscaled_position():
    overlay = command_build_export_overlay(
        _store(split=0.5), scale_x=1.0, scale_y=1.0, **_kw()
    )
    assert overlay["split_pos"] == 500
    assert overlay["visible"] is True


def test_no_viewport_stays_hidden():
    overlay = command_build_export_overlay(
        SimpleNamespace(viewport=None), scale_x=2.0, scale_y=2.0, **_kw()
    )
    assert overlay["visible"] is False
