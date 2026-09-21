"""image_uid content identity (engine identity task).

Falsification-first: ``image_uid`` used to (a) keep a stale counter tag
when a payload was mutated in place (same object, new pixels, same uid --
a false cache hit serving old content) and (b) fall back to ``id()`` for
objects rejecting setattr (numpy arrays), whose address CPython reuses
after GC -- a live unrelated object could inherit a dead one's uid and
serve wrong cached content. Both are cache-correctness bugs, not style.
"""

import pytest

from engine.cache import image_identity as identity_module
from engine.cache.image_identity import image_uid


def test_none_maps_to_zero():
    assert image_uid(None) == 0


def test_same_pil_object_is_stable_across_calls():
    from PIL import Image

    image = Image.new("RGBA", (8, 8), "blue")
    assert image_uid(image) == image_uid(image)


def test_pil_in_place_resize_retags():
    """Same object, new shape -> new uid (no stale-counter hit)."""
    from PIL import Image

    image = Image.new("RGBA", (8, 8), "blue")
    before = image_uid(image)
    assert before != 0
    # An in-place payload swap keeps the old tag store but changes shape:
    # emulate by grafting the old tag onto a differently-shaped image.
    # The uid must change (stale counter is a false hit otherwise).
    image2 = Image.new("RGBA", (16, 16), "blue")
    image2.info["_imgsli_uid"] = image.info["_imgsli_uid"]
    assert image_uid(image2) != before


def test_pil_mode_change_retags():
    from PIL import Image

    rgb = Image.new("RGB", (8, 8), "blue")
    uid_rgb = image_uid(rgb)
    rgba = Image.new("RGBA", (8, 8), "blue")
    rgba.info["_imgsli_uid"] = rgb.info["_imgsli_uid"]
    assert image_uid(rgba) != uid_rgb


def test_numpy_array_never_uses_id_and_always_misses():
    """ndarray rejects setattr: every call must miss (fresh counter), and
    the uid must never equal id() (GC-reusable address)."""
    numpy = pytest.importorskip("numpy")
    array = numpy.zeros((4, 4), dtype="uint8")
    first = image_uid(array)
    second = image_uid(array)
    assert first != second, "same array must miss, not hit a stale tag"
    assert first != id(array)
    assert second != id(array)
    other = numpy.zeros((4, 4), dtype="uint8")
    assert image_uid(other) not in (first, second)


def test_freed_object_address_cannot_collide():
    """A fresh counter never reuses a live tag; id() could (address
    reuse after GC). Two equal-content payloads that cannot carry tags
    must still get distinct uids."""
    numpy = pytest.importorskip("numpy")
    seen = set()
    for _ in range(8):
        arr = numpy.zeros((4, 4), dtype="uint8")
        uid = image_uid(arr)
        assert uid not in seen
        seen.add(uid)
        del arr


def test_qimage_uses_cache_key():
    PySide6 = pytest.importorskip("PySide6")
    from PySide6.QtGui import QImage

    image = QImage(8, 8, QImage.Format.Format_RGBA8888)
    image.fill(0)
    uid = image_uid(image)
    assert isinstance(uid, int)
    assert uid == image_uid(image)


def test_legacy_plain_int_tag_migrates():
    """Tags written before fingerprints existed (plain int in .info) are
    adopted when no shape is visible, retagged when shape disagrees."""
    from PIL import Image

    image = Image.new("RGBA", (8, 8), "blue")
    image.info["_imgsli_uid"] = 1234567
    # Shape disagrees with "no fingerprint" legacy tag -> retag.
    assert image_uid(image) != 1234567


def test_unreadable_shape_keeps_tag_for_sweep_after_close(tmp_path):
    """A closed TiledPixelStore (``size`` raises) must keep its uid: an
    unreadable fingerprint is no evidence of a content change. Retagging
    there broke identity-keyed sweeps running right after close
    (pyramid_registry sweep-on-access missed and leaked derived levels)."""
    from engine.store.tiled_pixel_store import TiledPixelStore
    from PIL import Image

    pil = Image.new("RGBA", (16, 16), "blue")
    store = TiledPixelStore.from_pil(pil, tmp_dir=str(tmp_path))
    uid_open = image_uid(store)
    store.close()
    assert image_uid(store) == uid_open


def test_no_id_fallback_in_source():
    import inspect

    source = inspect.getsource(identity_module)
    assert "return id(" not in source


def test_host_cache_counts_shared_image_once_and_evicts_both_directions():
    """The uid-cache canonical QImage aliased into the role cache must be
    charged once, and eviction must release exactly once per direction."""
    pytest.importorskip("PySide6")
    from PIL import Image

    from engine.gpu.host_texture_cache import HostTextureUploadCache

    cache = HostTextureUploadCache(budget_bytes=10**12)
    pil = Image.new("RGBA", (4, 4), "blue")
    image = cache.qimage_from_source(pil, "role_a")
    single = image.sizeInBytes()
    assert cache._total_bytes() == single

    cache.store("role_b", image)
    assert cache._total_bytes() == single, "aliased role must not double-charge"

    # Role-direction evict: drops the reference, keeps the canonical entry.
    cache.evict_over_budget(protected=set(), budget_bytes=single)
    assert cache._total_bytes() == single

    # Uid-direction evict to zero: releases everything, never negative.
    cache.evict_over_budget(protected=set(), budget_bytes=0)
    assert cache._total_bytes() == 0
    assert len(cache._cache) == 0
    assert len(cache._uid_cache) == 0
