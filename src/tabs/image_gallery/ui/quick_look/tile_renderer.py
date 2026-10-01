"""Quick Look tiled single-source renderer (task-ql-tiles-w1).
Audit-Meta: pattern=thin-owner-target size=exempt reason="one tile-array renderer: service/residency/upload/mip/instance/draw share one source lifecycle"

A thin, gallery-owned consumer of the shared engine tile-array stack
(``engine.gpu.array_draw`` + ``engine.cache.tile_texture_service`` +
``engine.cache.draw_plans`` + ``engine.gpu.array_resources`` +
``engine.gpu.mip_cascade``). It draws the *full* ``TiledPixelStore`` of the
displayed item from its texture-array tiles, with no source-size cap — the
transient cover raster keeps its own bound; this path is the one that can
show any resolution.

Deliberately canvas-light: one source, no pairing, no letterbox, no feature
passes. Geometry (contain-fit + zoom + pan) mirrors ``preview_zoom``'s
single-quad math so the tiled frame agrees with the raster/cover path by
construction:

    uv = (screen_fraction - 0.5) / (fit * zoom) + 0.5 - pan

``engine.cache.draw_plans.slot_visible_rect`` mirrors that same chain, so
visible-tile enumeration and the shader can never disagree.

Content identity fails CLOSED: a visible tile with no array slot yet is
skipped (never substituted by a neighbor), and every instance samples its own
``(row, col)``'s layer. Geometry derives solely from ``store.size`` and the
framebuffer size — never from first-arrived tile or arrival order.
"""

from __future__ import annotations

import struct
import time
from pathlib import Path

from PySide6.QtGui import (
    QRhi,
    QRhiBuffer,
    QShader,
)

from engine.cache.draw_plans import build_slot_plan_tiles, content_scale_for
from engine.cache.tile_constants import (
    LIVE_TILE_EXTENT,
    MIPS_CASCADE_TIME_BUDGET_MS,
    TILE_UPLOAD_BUDGET_PER_CALL,
    TILE_UPLOAD_TIME_BUDGET_MS,
)
from engine.cache.tile_geometry import _TILE_APRON_PX, crop_apron_tile
from engine.cache.tile_texture_service import (
    DEFAULT_MAX_ARRAY_SIZE,
    TileTextureService,
)
from engine.gpu.array_draw import (
    ARRAY_INSTANCE_ATTRIBUTES,
    ARRAY_INSTANCE_STRIDE,
    ArrayInstance,
    array_layer_px,
    record_array_draw,
)
from engine.gpu.array_resources import TileArrayResourcesBase
from engine.gpu.mip_cascade import MipCascadeGenerator
from engine.cache.uniform_layout import assert_uniform_size

# One texture-array layer's pixel size: LQ tile content (at most
# LIVE_TILE_EXTENT + 2*apron) uploaded 1:1 into the top-left corner.
_LIVE_TILE_EXTENT = LIVE_TILE_EXTENT
_ARRAY_LAYER_PX = array_layer_px(_LIVE_TILE_EXTENT, _TILE_APRON_PX)

# Clamp the array to the measured cross-backend TextureArraySizeMax
# (TileTextureService opens further arrays past it anyway).
_ARRAY_CAPACITY = DEFAULT_MAX_ARRAY_SIZE

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"

# Quad: 4 vertices of (vec2 position, vec2 texcoord) — texcoord is a 0/1
# corner selector within each instance's bounding box. Binding 0 stride 16.
_VERTICES = struct.pack(
    "<16f",
    -1.0, 1.0, 0.0, 0.0,
    -1.0, -1.0, 0.0, 1.0,
    1.0, 1.0, 1.0, 0.0,
    1.0, -1.0, 1.0, 1.0,
)

# std140 UBuf (ql_array.vert/frag): mat4 mvp(64) + vec2 pan(8) + vec2 zoom(8)
# + vec2 fit(8) + vec2 _pad(8) = 96.
_QL_UNIFORM_FMT = "<16f4f4f"
_QL_UNIFORM_BLOCK_SIZE = 96
assert_uniform_size(
    _QL_UNIFORM_FMT, _QL_UNIFORM_BLOCK_SIZE, label="pack_ql_array_uniforms"
)


def load_shader(name: str) -> QShader:
    """Load one of QL's own baked ``ql_array.*.qsb`` shaders."""
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {name}")
    return shader


def pack_ql_array_uniforms(
    rhi: QRhi,
    *,
    pan: tuple[float, float],
    zoom: float,
    fit: tuple[float, float],
) -> bytes:
    """Uniform bytes for one tiled frame (see the GLSL UBuf layout)."""
    matrix = tuple(float(value) for value in rhi.clipSpaceCorrMatrix().data())
    return struct.pack(
        _QL_UNIFORM_FMT,
        *matrix,
        float(pan[0]),
        float(pan[1]),
        float(zoom),
        float(zoom),
        float(fit[0]),
        float(fit[1]),
        0.0,
        0.0,
    )


def contain_fit_scale(
    store_size: tuple[int, int], fb_w: int, fb_h: int
) -> tuple[float, float]:
    """Contain-fit scale of the image inside the framebuffer, as the fraction
    of each framebuffer axis the image spans at zoom 1 (MC ``layer_fit_scale``
    for a full-canvas slot). Never raises; degenerate inputs give (1, 1)."""
    try:
        src_w, src_h = int(store_size[0]), int(store_size[1])
        fb_w, fb_h = int(fb_w), int(fb_h)
        if src_w <= 0 or src_h <= 0 or fb_w <= 0 or fb_h <= 0:
            return (1.0, 1.0)
        img_ar = src_w / src_h
        cell_ar = fb_w / fb_h
        if img_ar > cell_ar:
            return (1.0, cell_ar / img_ar)
        return (img_ar / cell_ar, 1.0)
    except Exception:
        return (1.0, 1.0)


def _axis_screen_span(
    tile_origin: float,
    tile_size: float,
    pan: float,
    fit: float,
    zoom: float,
) -> tuple[float, float]:
    """One axis of a tile's on-screen (framebuffer-fraction) span.

    Inverts the frag chain ``uv = (screen-0.5)/(fit*zoom)+0.5-pan`` for a
    tile rect stage clamped to [0,1], mirroring MC's ``_axis_bbox`` with the
    slot/letterbox stages collapsed to identity (single full-canvas slot).
    """
    e0 = max(0.0, min(1.0, tile_origin))
    e1 = max(0.0, min(1.0, tile_origin + tile_size))
    inv = 1.0 / max(1e-9, fit * zoom)
    c0 = 0.5 + (e0 - 0.5 + pan) / inv
    c1 = 0.5 + (e1 - 0.5 + pan) / inv
    if c0 > c1:
        c0, c1 = c1, c0
    return (max(0.0, min(1.0, c0)), max(0.0, min(1.0, c1)))


def tile_screen_bbox(
    tile_rect: tuple[float, float, float, float],
    *,
    pan: tuple[float, float],
    fit: tuple[float, float],
    zoom: float,
) -> tuple[float, float, float, float]:
    """A tile's framebuffer-fraction bounding box (x, y, w, h) for iBBox."""
    x0, x1 = _axis_screen_span(tile_rect[0], tile_rect[2], pan[0], fit[0], zoom)
    y0, y1 = _axis_screen_span(tile_rect[1], tile_rect[3], pan[1], fit[1], zoom)
    return (x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0))


class _QuickLookArrayResources(TileArrayResourcesBase):
    """QL's tile-array resource owner: shared instance layout, QL shader,
    QL array layer size."""

    def __init__(self, *, rhi_getter, sampler_getter, load_shader, name_prefix):
        super().__init__(
            rhi_getter=rhi_getter,
            sampler_getter=sampler_getter,
            load_shader=load_shader,
            layer_px=_ARRAY_LAYER_PX,
            array_capacity=_ARRAY_CAPACITY,
            name_prefix=name_prefix,
            instance_stride=ARRAY_INSTANCE_STRIDE,
            uniform_block_size=_QL_UNIFORM_BLOCK_SIZE,
            instance_attributes=ARRAY_INSTANCE_ATTRIBUTES,
            vertex_shader_name="ql_array.vert.qsb",
            fragment_shader_name="ql_array.frag.qsb",
            default_sampler_name="linear",
        )


class QuickLookTileRenderer:
    """Draws one full ``TiledPixelStore`` from its texture-array tiles.

    Owned by ``QuickLookCanvasWidget`` alongside the single-quad shell. This
    is additive: the canvas keeps the raster/cover path for the pre-first-
    frame and fail-open surface; this renderer only takes over once a tiled
    source is registered and the RHI is ready.
    """

    def __init__(self, *, rhi_getter, sampler_getter, load_shader, name_prefix="ql") -> None:
        self._rhi_getter = rhi_getter
        self._sampler_getter = sampler_getter
        self._name_prefix = name_prefix
        self.resources = _QuickLookArrayResources(
            rhi_getter=rhi_getter,
            sampler_getter=sampler_getter,
            load_shader=load_shader,
            name_prefix=name_prefix,
        )
        self._mip_cascade = MipCascadeGenerator(
            rhi_getter=rhi_getter,
            tile_arrays=self.resources.tile_arrays,
            ensure_tile_array=self.resources._ensure_tile_array,
            sampler_getter=lambda: sampler_getter("linear"),
            layer_px=_ARRAY_LAYER_PX,
            name_prefix=name_prefix,
        )
        self.tile_service: TileTextureService | None = None
        self._key: object | None = None
        self._store = None
        self._vertex_buffer: QRhiBuffer | None = None
        self._dirty_layers: dict[int, set[int]] = {}
        self._pending_mips: dict[int, set[int]] = {}

    # -- lifecycle -------------------------------------------------------------

    @property
    def _rhi(self) -> QRhi:
        rhi = self._rhi_getter()
        assert rhi is not None
        return rhi

    def _ensure_vertex_buffer(self) -> None:
        if self._vertex_buffer is not None:
            return
        buffer = self._rhi.newBuffer(
            QRhiBuffer.Type.Immutable,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(_VERTICES),
        )
        buffer.setName(f"{self._name_prefix}-array-quad".encode())
        if not buffer.create():
            raise RuntimeError("Failed to create Quick Look array vertex buffer")
        self._vertex_buffer = buffer

    def set_source(self, key: object, store) -> None:
        """Adopt the full store under ``key`` and register its tile grid.

        ``store`` is a ``TiledPixelStore`` (full resolution, uncapped). Any
        previous source's GPU tiles are dropped first (a fresh service is
        built) so no stale layer can ever be sampled for the new content.
        """
        self._release_gpu()
        self._key = key
        self._store = store
        service = TileTextureService(
            max_tile_extent=_LIVE_TILE_EXTENT,
            max_array_size=_ARRAY_CAPACITY,
        )
        try:
            width, height = store.size
        except Exception:
            try:
                width, height = store.size
            except Exception:
                width, height = (1, 1)
        service.register_source(key, (int(width), int(height)))
        self.tile_service = service

    def clear_source(self) -> None:
        """Drop the current source + its GPU tiles. Idempotent."""
        self._release_gpu()
        self._key = None
        self._store = None
        self.tile_service = None

    def _release_gpu(self) -> None:
        self._dirty_layers = {}
        self._pending_mips = {}
        self._mip_cascade.release()

    def release(self) -> None:
        """Destroy every GPU resource this renderer owns."""
        try:
            self._mip_cascade.release()
        except Exception:
            pass
        try:
            self.resources.release()
        except Exception:
            pass
        if self._vertex_buffer is not None:
            try:
                self._vertex_buffer.destroy()
            except RuntimeError:
                pass
            self._vertex_buffer = None
        self.tile_service = None
        self._key = None
        self._store = None

    # -- grid geometry ---------------------------------------------------------

    def grid(self):
        if self.tile_service is None or self._key is None:
            return None
        return self.tile_service.grid_for(self._key)

    def store_size(self) -> tuple[int, int]:
        try:
            width, height = self._store.size
            return (int(width), int(height))
        except Exception:
            return (0, 0)

    def has_source(self) -> bool:
        return self.tile_service is not None and self._key is not None

    # -- residency + draw ------------------------------------------------------

    def render(
        self,
        command_buffer,
        *,
        updates,
        target,
        clear_color,
        zoom: float,
        pan_x: float,
        pan_y: float,
        fb_w: int,
        fb_h: int,
    ) -> bool:
        """Upload this frame's visible tiles and record one instanced draw.

        Returns ``True`` iff at least one tile instance was drawn. Geometry
        derives from ``store.size`` and ``(fb_w, fb_h)`` only.
        """
        if self.tile_service is None or self._key is None:
            return False
        if target is None or command_buffer is None:
            return False
        fb_w = max(1, int(fb_w))
        fb_h = max(1, int(fb_h))
        store_w, store_h = self.store_size()
        if store_w <= 0 or store_h <= 0:
            return False

        fit = contain_fit_scale((store_w, store_h), fb_w, fb_h)
        pan = (float(pan_x), float(pan_y))
        try:
            zoom = float(zoom) or 1.0
        except Exception:
            zoom = 1.0

        plan = build_slot_plan_tiles(
            self.tile_service,
            self._key,
            pan,
            fit,
            zoom,
            apron_px=_TILE_APRON_PX,
        )
        self._ensure_vertex_buffer()

        self._upload_visible_tiles(plan, pan, fit, zoom, updates)

        # Submit the tile uploads BEFORE the mip cascade reads them back: the
        # cascade samples the just-uploaded level-0 content, which a
        # same-batch (unsubmitted) write does not guarantee visibility for.
        # The draw then gets a fresh batch (mirrors IC render(): submit
        # uploads -> generate_all_dirty_mips -> new batch -> draw).
        command_buffer.resourceUpdate(updates)

        dirty_layers = self._dirty_layers
        self._dirty_layers = {}
        if dirty_layers:
            deferred = self._mip_cascade.generate_all_dirty_mips(
                command_buffer,
                self._vertex_buffer,
                dirty_layers,
                MIPS_CASCADE_TIME_BUDGET_MS,
            )
            if deferred:
                self._dirty_layers = deferred

        instances = self._build_instances(plan, pan, fit, zoom)
        if not instances:
            # Nothing resident yet (fail closed): uploads stay queued/submitted
            # for the next frame, but no pass is recorded so the caller can
            # keep its own raster/cover batch untouched.
            return False
        uniform_bytes = pack_ql_array_uniforms(
            self._rhi, pan=pan, zoom=zoom, fit=fit
        )
        draw_updates = self._rhi.nextResourceUpdateBatch()

        record_array_draw(
            command_buffer,
            resources=self.resources,
            vertex_buffer=self._vertex_buffer,
            instances=instances,
            uniform_bytes=uniform_bytes,
            target=target,
            clear_color=clear_color,
            updates=draw_updates,
        )
        return True

    def _upload_visible_tiles(self, plan, pan, fit, zoom, updates) -> None:
        """Upload missing tiles among this frame's visible set (bounded).

        A tile with no slot yet is simply not resident this frame; it is
        skipped downstream (fail closed), never substituted by a neighbor.
        """
        service = self.tile_service
        key = self._key
        grid = service.grid_for(key)
        if grid is None:
            return
        desired = {tile.index for tile in plan}
        missing = {index for index in desired if not service.is_resident(key, index)}
        if not missing:
            return
        visible_rect = _visible_image_rect(pan, fit, zoom, grid)
        batch = service.select_upload_batch(
            key, missing, visible_rect, TILE_UPLOAD_BUDGET_PER_CALL
        )
        if not batch:
            return
        # Bound the wall clock like the compare tabs: one tile is a real
        # memmap read + crop.
        deadline = time.monotonic() + TILE_UPLOAD_TIME_BUDGET_MS / 1000.0
        dirty = self._dirty_layers
        for position, index in enumerate(batch):
            if position > 0 and time.monotonic() >= deadline:
                break
            row, col = index
            if row < 0 or row >= grid.rows or col < 0 or col >= grid.columns:
                continue
            region = grid.region_for(row, col)
            tile_image = crop_apron_tile(
                self._store,
                region.left,
                region.top,
                region.right,
                region.bottom,
                _TILE_APRON_PX,
            )
            self.resources.upload_tile_to_array(
                service, key, index, tile_image, updates, dirty
            )

    def _build_instances(self, plan, pan, fit, zoom) -> list[ArrayInstance]:
        service = self.tile_service
        key = self._key
        layer_px = float(_ARRAY_LAYER_PX)
        instances: list[ArrayInstance] = []
        for tile in plan:
            slot = service.slot_for(key, tile.index)
            if slot is None:
                # Fail closed: no array slot yet -> skip this tile entirely.
                continue
            _array_index, layer = slot
            scale = content_scale_for(
                service.content_size_for(key, tile.index), layer_px
            )
            content_scale = (scale[0], scale[1], scale[0], scale[1])
            bbox = tile_screen_bbox(tile.rect, pan=pan, fit=fit, zoom=zoom)
            instances.append(
                ArrayInstance(
                    rect1=tile.rect,
                    rect2=tile.rect,
                    content_scale=content_scale,
                    content_scale_diff=(1.0, 1.0),
                    layer1=layer,
                    layer2=layer,
                    layer_diff=0,
                    bbox=bbox,
                    rect_diff=(0.0, 0.0, 1.0, 1.0),
                    sampler_name="linear",
                )
            )
        return instances


def _visible_image_rect(pan, fit, zoom, grid):
    """Image-fraction visible window (left, top, right, bottom) in source
    pixels — the same ``slot_visible_rect`` derivation ``build_slot_plan_tiles``
    uses, reused here so upload selection and draw enumeration agree."""
    from engine.cache.draw_plans import slot_visible_rect

    return slot_visible_rect(pan, fit, zoom, grid)
