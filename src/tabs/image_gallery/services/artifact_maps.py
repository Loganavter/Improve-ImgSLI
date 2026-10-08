"""Coarse artifact localization — *where* an artifact is, not just its severity.

SalArt-VQA's core recommendation is that an artifact claim must be tied to
local visual evidence ("where"), not just "present". The severity detectors
return a single call; this tiles the image and re-runs the detector per tile to
produce a coarse heatmap of the artifact's strength across the frame, which the
quick-look report renders as a mini map next to the row.

Pure PIL/numpy, no Qt (worker-safe). Cost is bounded by the tile count
(default 5x5 = 25 detector calls per artifact). Fail-open: unreadable input or
an unknown artifact returns ``None`` (callers show no map).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

#: clean / mild / flagged -> heat value.
_SEV_HEAT = {"clean": 0.0, "mild": 0.5, "flagged": 1.0}


def _heat_of(sev) -> float:
    try:
        value = getattr(sev, "value", sev)
        return _SEV_HEAT.get(str(value).lower(), 0.0)
    except Exception:
        return 0.0


def localize(image: "Image | None", artifact, source_image: "Image | None" = None, grid: int = 5):
    """Coarse ``grid x grid`` heatmap (0..1) of *artifact* strength, or None.

    Tiles the image, runs the artifact's detector per tile (anchored vs the
    matching source tile for the absolute detectors), and maps
    clean/mild/flagged to 0/0.5/1. Approximate by construction — it is a
    "where to look" hint, not a pixel mask.
    """
    if image is None:
        return None
    try:
        from tabs.image_gallery.services.artifacts import (
            _ANCHORED,
            _DETECTORS,
            _anchor_severity,
        )

        fn = _DETECTORS.get(artifact)
        if fn is None:
            return None
        anchored = artifact in _ANCHORED and source_image is not None
        w, h = image.size
        if w < grid or h < grid:
            return None
        rows = []
        for gy in range(grid):
            y0, y1 = int(gy * h / grid), int((gy + 1) * h / grid)
            row = []
            for gx in range(grid):
                x0, x1 = int(gx * w / grid), int((gx + 1) * w / grid)
                box = (x0, y0, max(x1, x0 + 1), max(y1, y0 + 1))
                try:
                    tile = image.crop(box)
                    if anchored:
                        src_tile = source_image.crop(box)
                        sev = _anchor_severity(fn(tile, None), fn(src_tile, None))
                    else:
                        sev = fn(tile, source_image.crop(box) if source_image is not None else None)
                    row.append(_heat_of(sev))
                except Exception:
                    row.append(0.0)
            rows.append(row)
        return rows
    except Exception:
        return None
