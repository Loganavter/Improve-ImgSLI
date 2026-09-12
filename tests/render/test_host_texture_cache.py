"""Shared host-side texture upload cache tests."""

from collections import OrderedDict
from types import SimpleNamespace

from PIL import Image
from PySide6.QtGui import QImage

from shared.rendering.host_texture_cache import cache_for_widget
from tabs.image_compare.canvas.rhi_renderer.resources import (
    _pil_image_for_texture_key,
)
from tabs.image_compare.canvas.state import CanvasRuntimeState
from tabs.image_compare.canvas.texture_parts.upload_queue import (
    cache_texture_upload,
    evict_texture_upload_cache_over_budget,
    qimage_from_pil,
    queue_prepared_texture_upload,
    queue_texture_upload,
    touch_texture_upload_cache,
)


def _widget():
    state = SimpleNamespace(
        _pending_texture_uploads=[],
        _images_uploaded=[False, False],
        _texture_upload_cache=OrderedDict(),
        _qimage_by_uid_cache=OrderedDict(),
        _stored_pil_images=[None, None],
        _source_pil_images=[None, None],
        _diff_source_pil_image=None,
    )
    widget = SimpleNamespace(
        runtime_state=state,
        texture_ids=["stored_0", "stored_1"],
        _source_texture_ids=["source_0", "source_1"],
        _diff_source_texture_id="diff",
    )
    return widget


def _solid_qimage(w=8, h=8):
    image = QImage(w, h, QImage.Format.Format_RGBA8888)
    image.fill(0)
    return image


def test_queue_prepared_texture_upload_skips_redundant_copy_when_already_rgba8888():
    widget = _widget()
    image = _solid_qimage()

    queue_prepared_texture_upload(widget, "stored_0", image, 0)

    cached = widget.runtime_state._texture_upload_cache["stored_0"]
    assert cached is image


def test_queue_texture_upload_dedupes_decode_for_same_pil_image_identity():
    widget = _widget()
    pil_image = Image.new("RGBA", (8, 8), "red")

    queue_texture_upload(widget, pil_image, "stored_0")
    queue_texture_upload(widget, pil_image, "source_0")

    cache = widget.runtime_state._texture_upload_cache
    assert cache["stored_0"] is cache["source_0"]


def test_evict_over_budget_keeps_protected_and_drops_unused():
    widget = _widget()
    for key in ("stored_0", "stored_1", "source_0", "source_1", "diff"):
        cache_texture_upload(widget, key, _solid_qimage(100, 100))
    touch_texture_upload_cache(widget, "stored_0")
    touch_texture_upload_cache(widget, "stored_1")

    per_image_bytes = _solid_qimage(100, 100).sizeInBytes()
    evict_texture_upload_cache_over_budget(
        widget, {"stored_0", "stored_1"}, per_image_bytes * 2
    )

    cache = widget.runtime_state._texture_upload_cache
    assert "stored_0" in cache
    assert "stored_1" in cache
    assert "source_0" not in cache
    assert "source_1" not in cache


def test_evict_over_budget_noop_under_budget():
    widget = _widget()
    cache_texture_upload(widget, "stored_0", _solid_qimage())

    evict_texture_upload_cache_over_budget(widget, set(), 10**9)

    assert "stored_0" in widget.runtime_state._texture_upload_cache


def test_cache_for_widget_works_with_slotted_canvas_runtime_state():
    """Regression: slotted CanvasRuntimeState must accept the host LRU cache."""
    state = CanvasRuntimeState()
    widget = SimpleNamespace(runtime_state=state)
    cache = cache_for_widget(widget)
    assert cache is state._host_texture_upload_cache
    assert state._texture_upload_cache is cache.entries


def test_pil_image_for_texture_key_resolves_every_role():
    widget = _widget()
    img1, img2 = Image.new("RGBA", (2, 2)), Image.new("RGBA", (2, 2))
    src1, src2 = Image.new("RGBA", (3, 3)), Image.new("RGBA", (3, 3))
    diff = Image.new("RGBA", (4, 4))
    widget.runtime_state._stored_pil_images = [img1, img2]
    widget.runtime_state._source_pil_images = [src1, src2]
    widget.runtime_state._diff_source_pil_image = diff

    assert _pil_image_for_texture_key(widget, "stored_0") is img1
    assert _pil_image_for_texture_key(widget, "stored_1") is img2
    assert _pil_image_for_texture_key(widget, "source_0") is src1
    assert _pil_image_for_texture_key(widget, "source_1") is src2
    assert _pil_image_for_texture_key(widget, "diff") is diff
    assert _pil_image_for_texture_key(widget, "unknown") is None


def test_cache_texture_upload_survives_evicted_entry_rebuild_roundtrip():
    widget = _widget()
    pil_image = Image.new("RGBA", (5, 5), "blue")
    widget.runtime_state._stored_pil_images[0] = pil_image
    cache_texture_upload(widget, "stored_0", qimage_from_pil(pil_image))

    evict_texture_upload_cache_over_budget(widget, set(), 0)
    assert touch_texture_upload_cache(widget, "stored_0") is None

    rebuilt = qimage_from_pil(_pil_image_for_texture_key(widget, "stored_0"))
    cache_texture_upload(widget, "stored_0", rebuilt)

    assert widget.runtime_state._texture_upload_cache["stored_0"] is rebuilt
    assert rebuilt.pixelColor(0, 0) == qimage_from_pil(pil_image).pixelColor(0, 0)
