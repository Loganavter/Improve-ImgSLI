"""No ``id()`` in identity / cache / throttle keys (scoped dogmas).

``id()`` values are memory addresses: they are reused after garbage
collection, so any key built from them can collide with a dead object and
return stale data. The three sites below keep a documented last-resort or
mitigated use; these dogmas pin the mitigations so a refactor cannot
silently widen the ``id()`` surface:

- grab key (export throttle): the key must always carry a non-identity
  component, the throttle window must stay bounded, and the cached image
  must be returned as a copy.
- image_uid (content identity): stable tags are tried before ``id()``, and
  ``id()`` appears at most once, in the final fallback.
- dedup key (clipboard): dedup keys are content/path-derived, never ``id()``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"


def _read(relative: str) -> tuple[str, ast.Module]:
    text = (_SRC / relative).read_text(encoding="utf-8")
    return text, ast.parse(text)


def _id_calls(tree: ast.Module) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "id"
    ]


def test_grab_key_always_carries_non_identity_component():
    """Export grab throttle: ``id()`` never stands alone as the key."""
    text, tree = _read("plugins/export/services/gpu_export_proxy.py")
    assert "grab_key" in text
    # The key tuple keeps its size (content-derived) component.
    assert "target_widget_size" in text
    # Throttle window stays a bounded sub-second literal (< 1.0), so even an
    # id-reuse collision can only serve a stale image for milliseconds.
    windows = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, float)
        and node.value < 1.0
    ]
    assert windows, "expected a bounded sub-second throttle window literal"
    # Cached image is handed out as a copy — callers can never mutate the
    # cached entry through the returned reference.
    assert "_last_grab_image.copy()" in text


def test_image_uid_stable_tags_before_id_fallback():
    """Content identity prefers stable tags; ``id()`` is the last resort."""
    text, tree = _read("engine/cache/image_identity.py")
    id_calls = _id_calls(tree)
    assert len(id_calls) <= 1, "image_uid must keep a single id() fallback"
    # Stable mechanisms exist ahead of the fallback.
    assert "_UID_INFO_KEY" in text
    assert "cacheKey" in text
    # Behavioral: stable, distinct, None-safe.
    from engine.cache.image_identity import image_uid

    try:
        from PIL import Image
    except ImportError:
        return
    first = Image.new("RGB", (8, 8), (1, 2, 3))
    assert image_uid(None) == 0
    assert image_uid(first) == image_uid(first)
    assert image_uid(first) != image_uid(Image.new("RGB", (8, 8), (1, 2, 3)))


def test_dedup_keys_content_derived_never_id():
    """Clipboard dedup keys come from content/paths, never ``id()``."""
    text, tree = _read("shared/clipboard_images.py")
    assert not _id_calls(tree), "dedup path must not key on id()"
    from shared.clipboard_images import _dedupe_clipboard_items

    items = ["https://x/y.png", "https://x/y.png", "/tmp/a.png", "/tmp/a.png"]
    assert _dedupe_clipboard_items(items) == ["https://x/y.png", "/tmp/a.png"]


def test_owned_store_files_use_no_id_keys():
    """Lane-owned store files: no ``id()`` in any identity/cache key."""
    owned = [
        "core/state_management/dispatcher.py",
        "core/state_management/reducers.py",
        "core/state_management/extension_reducers.py",
    ]
    for relative in owned:
        _, tree = _read(relative)
        assert not _id_calls(tree), f"{relative} must not use id()"
