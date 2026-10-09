"""Content identity for the video-editor thumbnail pipeline.

Regression for the timeline-class bug (see
improve-imgsli-internal-docs inv-test-suite-state-2026-10-09): a thumbnail for
frame index ``i`` must be rendered from frame ``i``'s snapshot, never a
neighbor's. The wave/generation suites asserted counts and windows only, so an
index -> content swap passed them.

The seam exercised here is the real worker body
``_generate_single_thumbnail``: it resolves ``recording.evaluate_at(i / fps)``
and renders it. We inject a recording whose snapshot encodes the timestamp and
a renderer that paints that timestamp's distinct colour, then require the
emitted thumbnail to carry frame ``i``'s own colour.
"""

from __future__ import annotations

from PIL import Image

from tabs.image_compare.plugins.video_editor.services.thumbnails import (
    ThumbnailService,
)

_FPS = 10
_THUMB = (160, 90)


def _color_for_index(index: int) -> tuple[int, int, int, int]:
    """Distinct, index-derived colour so a neighbor bind cannot match."""
    return ((index * 37) % 256, (index * 91) % 256, (index * 53) % 256, 255)


class _TimestampRecording:
    """``evaluate_at(t)`` returns ``t``; the frame colour follows from ``t``."""

    def get_duration(self) -> float:
        return 30.0

    def evaluate_at(self, timestamp: float):
        return float(timestamp)


def _render_snapshot(snap, target_w, target_h, *, auto_crop=False):
    # snap is the frame timestamp; recover the frame index and paint its colour.
    index = int(round(float(snap) * _FPS))
    return Image.new("RGBA", (target_w * 2, target_h * 2), _color_for_index(index))


def test_thumbnail_renders_its_own_frame_not_a_neighbor(qapp):
    service = ThumbnailService()
    service.set_thumbnail_disk_cache(None)
    recording = _TimestampRecording()

    for index in (0, 3, 7, 11, 25):
        rendered = service._generate_single_thumbnail(
            index,
            _THUMB,
            False,
            1.0,
            _FPS,
            None,
            recording=recording,
            render_snapshot=_render_snapshot,
        )
        assert rendered is not None, f"index {index} produced no thumbnail"
        got = rendered.convert("RGBA").getpixel(
            (rendered.size[0] // 2, rendered.size[1] // 2)
        )
        assert got == _color_for_index(index), (
            f"index {index} rendered a neighbor's frame: {got}"
        )


def test_missing_render_capture_fails_closed(qapp):
    """No queue-time capture -> miss, never a render from live params."""
    service = ThumbnailService()
    service.set_thumbnail_disk_cache(None)
    assert (
        service._generate_single_thumbnail(3, _THUMB, False, 1.0, _FPS, None)
        is None
    )
