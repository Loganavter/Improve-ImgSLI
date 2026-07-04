"""Tab-owned semantic contributions for the generic video timeline widget.

Holds track ids, token translations, and is_track_active branches that only
make sense for image_compare (comparison/magnifier/splitter/filename_overlay).
Generic timeline callbacks defer to this contribution via the registry hook.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VideoTimelineSemantics:
    prominent_track_ids: frozenset[str] = field(default_factory=frozenset)
    token_translation_keys: dict[str, str] = field(default_factory=dict)

    def is_track_active(self, track, channel, value) -> bool | None:
        track_id = track.id
        if channel.kind == "enum":
            if track_id == "comparison.diff_mode":
                return str(value).lower() != "off"
            if track_id == "comparison.channel_view_mode":
                return str(value).upper() != "RGB"
        if track_id.startswith("magnifier.default.") and track_id != "magnifier.default.enabled":
            return True
        return None


IMAGE_COMPARE_TIMELINE_SEMANTICS = VideoTimelineSemantics(
    prominent_track_ids=frozenset({"splitter.main.position"}),
    token_translation_keys={
        "NEAREST": "magnifier.nearest_neighbor",
        "BILINEAR": "magnifier.bilinear",
        "BICUBIC": "magnifier.bicubic",
        "LANCZOS": "magnifier.lanczos",
        "EWA_LANCZOS": "magnifier.ewa_lanczos",
        "LEFT": "common.position.left",
        "CENTER": "common.position.center",
        "RIGHT": "common.position.right",
        "RGB": "video.rgb",
        "R": "video.red",
        "G": "video.green",
        "B": "video.blue",
        "L": "video.luminance",
        "HIGHLIGHT": "video.highlight",
        "GRAYSCALE": "video.grayscale",
        "EDGES": "video.edge_comparison",
        "SSIM": "video.ssim_map",
    },
)


def get_image_compare_timeline_semantics() -> VideoTimelineSemantics:
    return IMAGE_COMPARE_TIMELINE_SEMANTICS
