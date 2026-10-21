"""V11: a failed crop must drop the upload, never substitute the unclipped image.

Dogma (plan-canvas-hardening-2026-10-21, V11): ``queue_texture_upload`` clips a
whole image to the tile's box before staging it. Both crop paths used to swallow
the exception and fall through to the *unclipped* upload, which the apply path
then marked as a finished tile -- the frame showed content from outside the
tile's slot as if it were the tile (silent-wrong, S1). Now a failed crop (or an
unparseable box) drops the upload, increments ``widget._crop_failure_count`` and
warns once per key.

Falsification story: on the pre-fix source every ``crop fails`` test below sees
a queued upload (the unclipped image) and no counter, so it fails; the control
test passes on both sides and guards against "drop everything" implementations.
"""

from __future__ import annotations

from collections import OrderedDict
from types import SimpleNamespace

import pytest
from PIL import Image

from tabs.image_compare.canvas.texture_parts import crop_clip, upload_queue


def _widget() -> SimpleNamespace:
    state = SimpleNamespace(
        _pending_texture_uploads=[],
        _images_uploaded=[False, False],
        _qimage_by_uid_cache=OrderedDict(),
    )
    return SimpleNamespace(runtime_state=state)


def _image() -> Image.Image:
    return Image.new("RGB", (20, 20), (10, 20, 30))


def test_failed_pil_crop_drops_the_upload_and_counts(monkeypatch):
    widget = _widget()

    def _boom(_image, _box):
        raise RuntimeError("clip blew up")

    monkeypatch.setattr(crop_clip, "clip_image_for_upload", _boom)

    upload_queue.queue_texture_upload(
        widget, _image(), "stored_0", 0, crop_box=(0, 0, 8, 8)
    )

    assert widget.runtime_state._pending_texture_uploads == [], (
        "the unclipped image was queued after a failed crop"
    )
    assert widget._crop_failure_count == 1
    assert widget._crop_failure_keys == {"stored_0"}


def test_failed_store_crop_drops_the_upload_and_counts(monkeypatch):
    from engine.store import tiled_pixel_store as store_mod

    class _FakeStore:
        pass

    def _boom(_store, _box):
        raise RuntimeError("memmap crop blew up")

    monkeypatch.setattr(store_mod, "TiledPixelStore", _FakeStore)
    monkeypatch.setattr(store_mod, "qimage_from_pixel_source", _boom)

    widget = _widget()
    upload_queue.queue_texture_upload(
        widget, _FakeStore(), "stored_1", 1, crop_box=(0, 0, 8, 8)
    )

    assert widget.runtime_state._pending_texture_uploads == []
    assert widget._crop_failure_count == 1


def test_unparseable_crop_box_drops_the_upload():
    widget = _widget()

    upload_queue.queue_texture_upload(
        widget, _image(), "diff", None, crop_box="not-a-box"
    )

    assert widget.runtime_state._pending_texture_uploads == [], (
        "an unparseable crop box must not fall through to a whole-image upload"
    )
    assert widget._crop_failure_count == 1


def test_successful_crop_still_queues_one_upload():
    """Control: the happy path is unchanged (nothing dropped, no counter)."""
    widget = _widget()

    upload_queue.queue_texture_upload(
        widget, _image(), "stored_0", 0, crop_box=(0, 0, 8, 8)
    )

    assert len(widget.runtime_state._pending_texture_uploads) == 1
    key, prepared, slot = widget.runtime_state._pending_texture_uploads[0]
    assert (key, slot) == ("stored_0", 0)
    assert prepared.width() == 8 and prepared.height() == 8, "the upload was not clipped"
    assert getattr(widget, "_crop_failure_count", 0) == 0
