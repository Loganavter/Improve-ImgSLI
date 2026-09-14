"""Generic plain per-key texture + dynamic-buffer resource owner (docs/dev/
rendering/renderer-unification-plan.md Phase 2).

Promoted out of a tab-side per-slot ``SlotResources`` class (Phase D4
plain-path decision): every canvas tab draws its still-1x1 tiles the same
way -- one ``QRhiTexture`` per tile key, per-slot dynamic vertex/uniform
buffers grown to a stride, recreated on resize -- with only the shader
pair, binding layout, and uniform block size differing. This class owns
the GPU-memory lifetime half (texture dict, buffer lists, upload,
destroy, release); shader/pipeline specifics (graphics pipeline creation,
SRB binding layout, which keys belong to which slot) stay with the
tab-side consumer, which subclasses this base exactly like the array
path subclasses ``engine.gpu.array_resources.TileArrayResourcesBase``.

Tile *residency decisions* (which tiles should be resident, cropping,
marking resident) stay in each tab's own residency code; this class only
owns the GPU resources those decisions get realized against.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QRhiBuffer


class PlainTextureResourcesBase:
    """Owns one plain ``QRhiTexture`` per tile key plus the per-slot
    dynamic vertex/uniform buffers backing the non-array draw path --
    one instance per renderer/pass."""

    def __init__(self, *, uniform_stride: int) -> None:
        self.slot_textures: dict = {}
        self.slot_texture_sizes: dict = {}
        self.slot_vertex_buffers: list = []
        self.slot_uniform_buffers: list = []
        self._slot_uniform_capacity: list[int] = []
        self._slot_uniform_stride = uniform_stride

    def set_uniform_stride(self, stride: int) -> None:
        self._slot_uniform_stride = stride

    def release_textures(self) -> None:
        for texture in self.slot_textures.values():
            if texture is not None:
                try:
                    texture.destroy()
                except RuntimeError:
                    pass
        self.slot_textures = {}
        self.slot_texture_sizes = {}

    def release_buffers(self) -> None:
        for res in (*self.slot_vertex_buffers, *self.slot_uniform_buffers):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.slot_vertex_buffers = []
        self.slot_uniform_buffers = []
        self._slot_uniform_capacity = []

    def release(self) -> None:
        self.release_buffers()
        self.release_textures()

    def upload_texture(
        self,
        tile_key: object,
        image,
        updates,
        *,
        allocate: Callable[[tuple[int, int]], object],
    ) -> object:
        """Uploads ``image`` under ``tile_key``, (re)creating the texture
        via ``allocate(size)`` when missing or resized. Allocation itself
        stays caller-supplied -- the caller mints the ``QRhiTexture``
        against its own renderer (format, sampler scope, and creation
        quirks differ per consumer) while this base owns the lifetime
        bookkeeping every consumer shares. Returns the live texture."""
        size = (image.width(), image.height())
        existing = self.slot_textures.get(tile_key)
        if existing is None or self.slot_texture_sizes.get(tile_key) != size:
            if existing is not None:
                try:
                    existing.destroy()
                except RuntimeError:
                    pass
            tex = allocate(size)
            self.slot_textures[tile_key] = tex
            self.slot_texture_sizes[tile_key] = size
        updates.uploadTexture(self.slot_textures[tile_key], image)
        return self.slot_textures[tile_key]

    def discard_textures(self, keys) -> None:
        """Destroys and forgets whichever of ``keys`` are currently held.
        Key selection (which keys belong to a slot, what to keep) stays
        with the caller -- this only performs the destruction."""
        for key in keys:
            texture = self.slot_textures.pop(key, None)
            if texture is not None:
                try:
                    texture.destroy()
                except RuntimeError:
                    pass
            self.slot_texture_sizes.pop(key, None)

    def ensure_buffer_count(self, rhi, count: int, *, vertex_bytes: int) -> None:
        """Grows the vertex/uniform buffer lists to ``count`` slots. The
        vertex payload size is caller-supplied (fullscreen quad bytes for
        the plain path); uniform buffers start at one stride block."""
        while len(self.slot_vertex_buffers) < count:
            buf = rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.VertexBuffer,
                vertex_bytes,
            )
            buf.create()
            self.slot_vertex_buffers.append(buf)
        while len(self.slot_uniform_buffers) < count:
            buf = rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                self._slot_uniform_stride,
            )
            buf.create()
            self.slot_uniform_buffers.append(buf)
            self._slot_uniform_capacity.append(1)

    def ensure_uniform_capacity(self, rhi, index: int, slot_count: int):
        """Grows ``slot_uniform_buffers[index]`` to hold ``slot_count``
        per-tile uniform blocks at stride-spaced offsets, so every tile
        item gets its own uniform slot written into the single pre-pass
        ``updates`` batch instead of a mid-pass ``resourceUpdate()`` per
        draw call. Must be called before beginPass: growing recreates the
        buffer object, which invalidates every cached tile SRB bound to
        it -- the caller purges those itself.

        Returns the replaced old buffer when growth happened (the caller
        destroys it after purging its SRBs), else ``None``."""
        slot_count = max(1, slot_count)
        if index >= len(self._slot_uniform_capacity):
            return None
        if slot_count <= self._slot_uniform_capacity[index]:
            return None
        new_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            self._slot_uniform_stride * slot_count,
        )
        if not new_buffer.create():
            raise RuntimeError("Failed to grow plain-path slot uniform buffer")
        old_buffer = self.slot_uniform_buffers[index]
        self.slot_uniform_buffers[index] = new_buffer
        self._slot_uniform_capacity[index] = slot_count
        return old_buffer
