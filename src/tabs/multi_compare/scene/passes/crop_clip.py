"""Parametric-crop render clip for Multi Compare's base-image pass.

Split out of ``tabs.multi_compare.scene.passes.residency`` (lane
mc-crop-render; docs/dev/CODE_MASS_REDUCTION.md Part D) -- the crop cluster
moved verbatim, and ``residency`` re-exports these names so its existing
``residency.<name>`` call sites keep working unchanged.
"""

from __future__ import annotations

#
# Decode stays full-frame forever; crop applies at sampling. The canvas
# resolves one effective box per slot (via the frozen
# ``tabs.multi_compare.use_cases.crop.effective_crop_box`` seam) and wraps
# cropped slots in :class:`CroppedSlotView` -- a translating view that
# reports the cropped size (``engine.store.crop_window.crop_view_size``)
# while sampling the full-frame parent with every read box intersected
# (``engine.store.crop_window.intersect_box``). Downstream code
# (tile-service grid registration, LOD scale, fit, composition extents)
# reads sizes through ``pixel_source_size`` and therefore picks up the
# cropped size with no engine changes; pyramid builds never see views
# (they stay on the controller's real stores), so cropped slots resolve
# native -- correct pixels, LOD scale still computed against the cropped
# size. An empty intersection yields ``None`` (gap) instead of a source,
# fail-closed, never neighbor bytes.


def controller_for_canvas(widget: object) -> object | None:
    """Nearest ``_controller`` above the canvas widget, or ``None``.

    Production chain is canvas -> container -> ``MultiCompareWidget``
    (which owns ``_controller`` -- see ``controller.py``); headless fakes
    without parents read ``None``. Never raises.
    """
    node = widget
    for _ in range(8):
        if node is None:
            return None
        try:
            ctrl = getattr(node, "_controller", None)
        except Exception:
            ctrl = None
        if ctrl is not None:
            return ctrl
        try:
            parent = node.parentWidget()
        except Exception:
            return None
        node = parent
    return None


def crop_box_for_slot(controller: object | None, slot: object | None) -> tuple[int, int, int, int] | None:
    """Effective crop box for ``slot`` in full-frame source px, or ``None``.

    Thin guarded wrapper over the frozen ``effective_crop_box`` seam --
    the ONLY box source on this path. Never raises (any failure reads as
    full frame, mirroring the seam's own never-raises contract).
    """
    try:
        if controller is None or slot is None:
            return None
        from tabs.multi_compare.use_cases.crop import effective_crop_box

        box = effective_crop_box(controller, slot)
        if box is None:
            return None
        return (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
    except Exception:
        return None


class CroppedSlotView:
    """Box-sized translating view over a full-frame pixel source.

    Reports ``crop_view_size`` while every read translates box-local rects
    back to full-frame parent coords and intersects them with the crop
    window -- the per-slot read-box clip. Satisfies the duck-typed pixel
    source shapes the render path already accepts:

    - ``.size`` / ``.width`` / ``.height`` (``pixel_source_size``,
      composition extents);
    - ``.crop(box)`` (``crop_apron_tile``'s generic branch, tile uploads);
    - ``.mode`` / ``.tobytes()`` (PIL emulation for the 1x1 whole-image
      swap path via ``HostTextureUploadCache.qimage_from_source`` -- only
      small single-tile views ever flow there).

    Read-only; the parent source is never mutated. Never raises out of
    ``crop``/``tobytes`` with an empty intersection -- those degrade to a
    1px fallback instead of sampling neighbor bytes.
    """

    mode = "RGBA"

    def __init__(self, parent: object, box: tuple[int, int, int, int]) -> None:
        from engine.store.crop_window import crop_view_size

        left, top, right, bottom = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
        self._parent = parent
        self._box = (left, top, right, bottom)
        try:
            from engine.store.tiled_pixel_store import pixel_source_size

            full = pixel_source_size(parent)
        except Exception:
            full = (0, 0)
        try:
            self._size = (int(crop_view_size(full, self._box)[0]), int(crop_view_size(full, self._box)[1]))
        except Exception:
            self._size = (0, 0)

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    @property
    def width(self) -> int:
        return int(self._size[0])

    @property
    def height(self) -> int:
        return int(self._size[1])

    @property
    def parent(self) -> object:
        return self._parent

    @property
    def crop_box(self) -> tuple[int, int, int, int]:
        return self._box

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"CroppedSlotView(box={self._box}, size={self._size})"

    def _translated(self, box: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
        """Box-local rect to full-frame parent coords, clipped to the crop.

        ``None`` when nothing usable remains (fail-closed -- callers fall
        back to a 1px sample, never neighbor bytes).
        """
        from engine.store.crop_window import intersect_box

        left, top, right, bottom = self._box
        try:
            w, h = self._size
            al, at, ar, ab = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
        except Exception:
            return None
        al = max(0, min(al, w))
        at = max(0, min(at, h))
        ar = max(0, min(ar, w))
        ab = max(0, min(ab, h))
        if ar <= al or ab <= at:
            return None
        try:
            return intersect_box((al + left, at + top, ar + left, ab + top), self._box)
        except Exception:
            return None

    def crop(self, box: tuple[int, int, int, int]):  # type: ignore[no-untyped-def]
        """Crop a box-local rect, translated to full-frame parent coords.

        Returns a ``QImage`` for store/QImage parents (same types
        ``crop_apron_tile`` yields for those today) and a PIL image for
        PIL-like parents -- whatever the tile-upload funnels already
        accept. Never raises on empty intersections (1px fallback).
        """
        translated = self._translated(box)
        if translated is None:
            return _one_px_fallback(self._parent)
        parent = self._parent
        try:
            from PySide6.QtGui import QImage

            from engine.store.tiled_pixel_store import TiledPixelStore

            if isinstance(parent, TiledPixelStore):
                from engine.store.tiled_pixel_store import qimage_from_pixel_source

                return qimage_from_pixel_source(parent, translated)
            if isinstance(parent, QImage):
                left, top, right, bottom = translated
                return parent.copy(left, top, right - left, bottom - top)
        except Exception:
            pass
        try:
            return parent.crop(translated)  # type: ignore[union-attr]  # PIL-like parent
        except Exception:
            return _one_px_fallback(self._parent)

    def tobytes(self, raw: str = "raw", kind: str = "RGBA") -> bytes:
        """PIL-emulation for the 1x1 whole-image swap path.

        Materializes the (clamped, single-tile-bounded) crop once per box
        change -- the resulting QImage is then uid-cached by the host
        cache, so this never runs per frame.
        """
        try:
            pil = _materialize_pil(self._parent, self._box)
            return pil.tobytes(raw, kind)
        except Exception:
            return b""


def _one_px_fallback(parent: object):  # type: ignore[no-untyped-def]
    """1px transparent sample -- the fail-closed degenerate read."""
    try:
        from PySide6.QtGui import QImage

        return QImage(1, 1, QImage.Format.Format_RGBA8888)
    except Exception:  # pragma: no cover - Qt always present in practice
        from PIL import Image as _PILImage

        return _PILImage.new("RGBA", (1, 1), (0, 0, 0, 0))


def _qimage_to_pil(qimage):  # type: ignore[no-untyped-def]
    """Lossless QImage -> PIL via a PNG round-trip (rare small-crop path)."""
    import io

    from PySide6.QtCore import QBuffer, QIODevice
    from PIL import Image as _PILImage

    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    try:
        qimage.save(buf, "PNG")
        data = bytes(buf.data())
    finally:
        buf.close()
    img = _PILImage.open(io.BytesIO(data))
    img.load()
    return img.convert("RGBA")


def _materialize_pil(parent: object, box: tuple[int, int, int, int]):  # type: ignore[no-untyped-def]
    """Cropped PIL copy of ``parent`` for ``tobytes`` (bounded caller)."""
    from engine.store.crop_window import intersect_box
    from engine.store.tiled_pixel_store import pixel_source_size

    full = pixel_source_size(parent)
    frame = (0, 0, int(full[0]), int(full[1]))
    clamped = intersect_box(box, frame)
    if clamped is None:
        from PIL import Image as _PILImage

        return _PILImage.new("RGBA", (1, 1), (0, 0, 0, 0))
    try:
        from PySide6.QtGui import QImage

        from engine.store.tiled_pixel_store import TiledPixelStore

        if isinstance(parent, TiledPixelStore):
            return parent.crop(clamped)
        if isinstance(parent, QImage):
            left, top, right, bottom = clamped
            return _qimage_to_pil(parent.copy(left, top, right - left, bottom - top))
    except Exception:
        pass
    return parent.crop(clamped)  # type: ignore[union-attr]  # PIL-like parent


def cropped_source_for_slot(
    real_source: object | None,
    controller: object | None,
    slot: object | None,
    *,
    cache: dict[int, tuple[object, tuple[int, int, int, int], object]] | None = None,
) -> object | None:
    """Render source for ``slot``: cropped view, full source, or ``None``.

    ``None`` box (no crop) returns ``real_source`` unchanged; a box whose
    cropped size covers the full frame does the same (keeps pyramid LOD
    and object identity for the no-op crop). A degenerate/empty cropped
    size returns ``None`` -- the slot renders gap (fail-closed). Views are
    cached per ``(source identity, box)`` in the caller-owned ``cache``
    (same explicit-dependency posture as ``slot_lod_keys``) so swap
    duplicate-detection (``is``) stays stable across frames. Never raises.
    """
    try:
        if real_source is None:
            return None
        box = crop_box_for_slot(controller, slot)
        if box is None:
            return real_source
        from engine.store.crop_window import crop_view_size
        from engine.store.tiled_pixel_store import pixel_source_size

        full = pixel_source_size(real_source)
        try:
            size = crop_view_size(full, box)
            size = (int(size[0]), int(size[1]))
        except Exception:
            return real_source
        if size[0] <= 0 or size[1] <= 0:
            return None
        try:
            if tuple(size) == (int(full[0]), int(full[1])):
                return real_source
        except Exception:
            pass
        if cache is not None:
            try:
                sid = int(getattr(slot, "id", -1))
                hit = cache.get(sid)
                if hit is not None and hit[0] is real_source and tuple(hit[1]) == tuple(box):
                    return hit[2]
                view = CroppedSlotView(real_source, box)
                cache[sid] = (real_source, box, view)
                return view
            except Exception:
                pass
        return CroppedSlotView(real_source, box)
    except Exception:
        return real_source
