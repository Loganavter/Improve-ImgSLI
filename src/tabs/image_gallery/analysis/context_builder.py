"""Build an ``AnalysisContext`` from an already-decoded gallery item.

The engine's context (``engine.analysis.context``) is the one input of a
producer, and producers never decode (plan trap 1 / gate G11). Something has to
translate "a gallery item plus the images someone already decoded" into that
context, and this module is that translation — and nothing else:

- no file I/O, no decoding, no ``Image.open``, no ``TiledPixelStore``: the
  caller owns the decode (``services/proxy.py`` passes the shared bounded proxy
  it already built), so "how many decodes did this folder cost?" stays
  answerable;
- no store, no controller, no Qt: a context is a value, not a view;
- no policy decision: which producers run is the resolver's answer, not this
  module's.

Capability convention (deliberate, because the resolver narrows on it): the
capability set describes what the item's inputs ACTUALLY provide, and this
constructor adds the two it can see —

- ``"images"`` whenever ``proxy_image`` is not ``None``;
- ``"reference"`` whenever ``source_image`` is not ``None``.

Everything else (``"backend"``, ``"camera_scalars"``, …) is the caller's to
declare through ``capabilities``: this module must not claim an input it was not
handed. A capability that is absent is what a producer turns into an explicit
``status="gap"`` through ``ctx.require(...)``, never a substituted number.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from engine.analysis.context import AnalysisContext

#: Capability added when a decoded proxy image is present.
IMAGES_CAPABILITY = "images"
#: Capability added when a decoded source (reference) image is present.
REFERENCE_CAPABILITY = "reference"


def build_context(
    item,
    *,
    mode=None,
    proxy_image=None,
    source_image=None,
    capabilities: Iterable[str] = frozenset(),
    backend=None,
    call=None,
    image_bytes: bytes | None = None,
) -> AnalysisContext:
    """One item's analysis context, from inputs the caller already owns.

    *item* is a gallery item (``.path`` / ``.mtime_ns``), a mapping with those
    keys, or a path-like. The proxy/source images are passed through untouched —
    a producer must never mutate or close them (they are shared proxy cache
    entries).

    *mode* accepts the gallery's ``Mode`` enum or its string value; the context
    stores the plain string (or ``None``) so the engine never imports the tab's
    enums.
    """
    item_path, mtime_ns = _item_identity(item)
    caps = {
        name for name in (str(value).strip() for value in (capabilities or ())) if name
    }
    if proxy_image is not None:
        caps.add(IMAGES_CAPABILITY)
    if source_image is not None:
        caps.add(REFERENCE_CAPABILITY)
    return AnalysisContext(
        item_path=item_path,
        mtime_ns=mtime_ns,
        mode=_mode_value(mode),
        proxy_image=proxy_image,
        source_image=source_image,
        capabilities=frozenset(caps),
        backend=backend,
        call=call,
        image_bytes=image_bytes,
    )


def _item_identity(item) -> tuple[str, int]:
    """``(path, mtime_ns)`` from a gallery item / mapping / path-like.

    The mtime defaults to ``0`` for a bare path (a path has no mtime fact without
    a stat, and statting would be I/O): the cache-identity work that needs a real
    mtime passes the item, not its path.
    """
    if item is None:
        raise ValueError("build_context() needs an item (path, mapping or GalleryItem)")

    if isinstance(item, Mapping):
        path = item.get("path")
        mtime = item.get("mtime_ns")
    else:
        path = getattr(item, "path", None)
        mtime = getattr(item, "mtime_ns", None)
        if path is None:
            path = item

    text = str(path).strip() if path is not None else ""
    if not text:
        raise ValueError(f"build_context() got an item with no path: {item!r}")
    try:
        mtime_ns = int(mtime or 0)
    except (TypeError, ValueError):
        mtime_ns = 0
    return text, mtime_ns


def _mode_value(mode) -> str | None:
    """A ``Mode`` enum or string → its plain value; ``None`` stays ``None``."""
    if mode is None:
        return None
    text = str(getattr(mode, "value", mode) or "").strip()
    return text or None


__all__ = [
    "IMAGES_CAPABILITY",
    "REFERENCE_CAPABILITY",
    "build_context",
]
