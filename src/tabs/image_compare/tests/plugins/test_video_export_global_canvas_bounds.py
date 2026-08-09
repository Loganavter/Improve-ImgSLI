"""GlobalCanvasBounds is owned by image_compare's video-export pipeline."""

from __future__ import annotations

from tabs.image_compare.plugins.video_editor.services.video_export.models import (
    GlobalCanvasBounds,
)


def test_global_canvas_bounds_extends_beyond_unit():
    unit = GlobalCanvasBounds(0, 0, 0, 0, 100, 100)
    assert unit.extends_beyond_unit() is False
    padded = GlobalCanvasBounds(10, 0, 0, 0, 100, 100, canvas_x_min=-0.1)
    assert padded.extends_beyond_unit() is True
