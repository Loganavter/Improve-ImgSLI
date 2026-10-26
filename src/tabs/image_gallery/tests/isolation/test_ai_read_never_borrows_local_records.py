"""GUARD: the AI-domain read never borrows local detector numbers.

``analysis.read.read_axes(item, domain="ai")`` answers "what did the model
measure". An item that carries ONLY local engine records or legacy
``item.metrics`` has never been seen by the model: every requested axis must be
a ``gap`` (``value is None``), never a local number relabelled as AI.

This already holds on ``int/backend-isolation`` (the engine branch filters by
producer and the legacy AI branch reads only ``item.analysis``); it is kept as
the seam's guard so a future "single read path" refactor cannot quietly widen
the AI branch to the local columns.
"""

from __future__ import annotations

from pathlib import Path

from engine.analysis.contracts import AxisValue
from tabs.image_gallery.analysis.read import read_axes
from tabs.image_gallery.models import GalleryItem

_AXES = ("sharpness", "noise")


def _item_with_engine_records() -> GalleryItem:
    item = GalleryItem(path=Path("/gallery/engine.png"), mtime_ns=1)
    item.metrics.update({"sharpness": 200.0, "noise": 0.2})
    item.analysis_records = (
        AxisValue(axis="sharpness", value=50, producer="local", status="ok"),
        AxisValue(axis="noise", value=80, producer="local", status="ok"),
    )
    return item


def _item_with_legacy_metrics_only() -> GalleryItem:
    item = GalleryItem(path=Path("/gallery/legacy.png"), mtime_ns=1)
    item.metrics.update({"sharpness": 200.0, "noise": 0.2})
    return item


def test_ai_read_never_borrows_local_records() -> None:
    for item in (_item_with_engine_records(), _item_with_legacy_metrics_only()):
        records = read_axes(item, domain="ai", axes=_AXES)
        assert [record.axis for record in records] == list(_AXES)
        for record in records:
            assert record.status == "gap", (
                f"{type(item).__name__} {item.path.name}: local measurement "
                f"{record.axis!r} leaked into the AI-domain read ({record!r})"
            )
            assert record.value is None, (
                f"{record.axis!r} under domain='ai' returned a number for an "
                f"item the model never analyzed ({record!r})"
            )
