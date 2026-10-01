"""Engine single-image tiled view: the composed texture-array canvas renderer.

The tile stack is already engine-owned (draw-plan math, ``TileTextureService``,
GPU array resources, mip cascade, ``record_array_draw``), but every surface
used to re-assemble residency + instance build + uniforms + draw + coverage in
its own tab code. ``SingleImageTiledView`` composes those primitives into one
per-frame call; anything genuinely surface-specific (letterbox/slot rect,
feature/diff uniforms, feature passes, LOD policy) is a declared hook. One
source, no pairing/diff logic; the compare tabs stay on their own paths until
they migrate onto the hooks.

Multi-level sources (E2) register every pyramid level through the one
``TileTextureService`` under a level-scoped key, pick the target level with
``engine.cache.lod.select_level`` (``LodPolicy`` immediate/settle), and keep
the last fully-drawable level drawable underneath a not-yet-complete target
via the shared ``resolve_fallback_lod`` + ``drop_covered_fallback_tiles`` --
never a neighbour tile. ``covered`` is honest: it is true only when the target
level's visible set is resident and the mip cascade has drained, and false
whenever fallback content is being drawn. ``TiledViewResult.drawn`` stays
true whenever any target *or* fallback instance is recorded.

Composition order per ``render`` (mirrors the compare tabs' established
sequence, which the mip cascade requires): visible-rect -> residency
(``TileResidencyRealizerBase.realize_specs``, never a private upload loop) ->
submit ``updates`` -> ``MipCascadeGenerator.generate_all_dirty_mips`` ->
instance build (shared ``ArrayInstance`` layout) -> one uniform pack ->
``record_array_draw`` (with the caller's feature hooks) -> ``TiledViewResult``.

Content identity fails CLOSED: a visible tile with no array slot yet is
skipped (never substituted by a neighbour); each instance samples the layer
resolved from its own ``(row, col)``. Geometry derives solely from the store
size and the framebuffer size -- never from arrival order.

Uniform block ``UBuf`` (std140, binding 0) for the ``tiled_image_array``
shaders -- header is 112 bytes, followed by ``_UNIFORM_EXTRA_CAPACITY``
reserved bytes for tab feature/diff uniforms (E2+), so the block size is
constant regardless of these extras::

    mat4 mvp          @0    64   clip-space correction (rhi.clipSpaceCorrMatrix)
    vec4 letterbox    @64   16   (x, y, w, h) framebuffer-fraction image slot
    vec2 pan          @80    8
    vec2 zoom         @88    8
    vec2 fit          @96    8   contain-fit fraction per axis at zoom 1
    vec2 _pad         @104   8
    = 112-byte header + _UNIFORM_EXTRA_CAPACITY reserved extra bytes

The frag chain (also mirrored by ``slot_visible_rect``)::

    contentUV = (screen - letterbox.xy) / letterbox.zw
    uv        = (contentUV - 0.5) / (fit * zoom) + 0.5 - pan
    tileUV    = (uv - tileRect.xy) / tileRect.zw

Audit-Meta: pattern=state-machine size=exempt reason="one tile-array render lifecycle: residency/instance/uniform/draw share one source; splitting threads the source/grid/dirty state through every helper"
"""

from __future__ import annotations

import struct
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtGui import QRhiBuffer, QShader

from engine.cache.draw_plans import (
    build_slot_plan_tiles,
    content_scale_for,
    drop_covered_fallback_tiles,
    slot_visible_rect,
)
from engine.cache.fallback_lod import resolve_fallback_lod
from engine.cache.lod import select_level
from engine.cache.residency import ResidencySpec, TileResidencyRealizerBase
from engine.cache.tile_constants import (
    LIVE_TILE_EXTENT,
    MIPS_CASCADE_TIME_BUDGET_MS,
)
from engine.cache.tile_geometry import _TILE_APRON_PX
from engine.cache.tile_texture_service import (
    DEFAULT_MAX_ARRAY_SIZE,
    TileTextureService,
)
from engine.cache.uniform_layout import assert_uniform_size
from engine.gpu.array_draw import (
    ARRAY_INSTANCE_ATTRIBUTES,
    ARRAY_INSTANCE_STRIDE,
    ArrayInstance,
    array_layer_px,
    record_array_draw,
)
from engine.gpu.array_resources import TileArrayResourcesBase
from engine.gpu.mip_cascade import MipCascadeGenerator

Rect = tuple[float, float, float, float]
TileIndex = tuple[int, int]

#: GPU live-tile grid extent and the texture-array layer the tile content is
#: uploaded 1:1 into (see ``array_layer_px``). One array for one source.
_LIVE_TILE_EXTENT = LIVE_TILE_EXTENT
_ARRAY_LAYER_PX = array_layer_px(_LIVE_TILE_EXTENT, _TILE_APRON_PX)
_ARRAY_CAPACITY = DEFAULT_MAX_ARRAY_SIZE

#: GPU tile byte budget for the shared eviction pass (mirrors the compare
#: tabs; at 512px tiles even a worst-case multi-ring working set stays well
#: under it, so eviction only reclaims genuinely unused tiles).
_TILE_CACHE_BUDGET_BYTES = 2 * 1024 * 1024 * 1024

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"

#: Quad: 4 vertices of (vec2 position, vec2 texcoord); texcoord is a 0/1
#: corner selector within each instance's bounding box. Binding 0 stride 16.
_VERTICES = struct.pack(
    "<16f",
    -1.0, 1.0, 0.0, 0.0,
    -1.0, -1.0, 0.0, 1.0,
    1.0, 1.0, 1.0, 0.0,
    1.0, -1.0, 1.0, 1.0,
)

_IDENTITY_MATRIX16 = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)
_IDENTITY_LETTERBOX: Rect = (0.0, 0.0, 1.0, 1.0)

# std140 header format: mat4(16f) + vec4 letterbox(4f) + vec2 pan(2f) +
# vec2 zoom(2f) + vec2 fit(2f) + vec2 _pad(2f) = 28 floats = 112 bytes.
_UNIFORM_HEADER_FMT = "<16f4f2f2f2f2f"
_UNIFORM_HEADER_SIZE = 112
#: Reserved trailing bytes for tab feature/diff uniforms; the block size is
#: constant (header + capacity) so a caller never has to resize the GPU
#: buffer when it starts passing ``TiledViewHooks.uniform_extra``.
_UNIFORM_EXTRA_CAPACITY = 64
_UNIFORM_BLOCK_SIZE = _UNIFORM_HEADER_SIZE + _UNIFORM_EXTRA_CAPACITY
assert_uniform_size(
    _UNIFORM_HEADER_FMT,
    _UNIFORM_HEADER_SIZE,
    label="pack_tiled_image_view_uniforms",
)


def load_tiled_image_shader(name: str) -> QShader:
    """Load one of the engine's baked ``tiled_image_array.*.qsb`` shaders.

    Consumers may pass this as ``load_shader`` when constructing the view;
    tests can pass a fake because no shader is built without a live target.
    """
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {name}")
    return shader


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def contain_fit_scale(
    store_size: tuple[int, int], fb_w: int, fb_h: int
) -> tuple[float, float]:
    """Contain-fit scale of the image inside the framebuffer, as the fraction
    of each framebuffer axis the image spans at zoom 1. Never raises;
    degenerate inputs give ``(1, 1)``.

    The single engine home for this math; surfaces migrating onto the view
    delete their own copies.
    """
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
    lb_origin: float,
    lb_size: float,
) -> tuple[float, float]:
    """One axis of a tile's framebuffer-fraction span.

    Inverts the frag chain ``uv = (contentUV - 0.5) / (fit*zoom) + 0.5 - pan``
    for a tile rect stage, clamped to [0, 1] in content space, then mapped
    through the letterbox slot. With ``letterbox = (0,0,1,1)`` this reduces to
    the Quick Look single-slot form.
    """
    e0 = max(0.0, min(1.0, tile_origin))
    e1 = max(0.0, min(1.0, tile_origin + tile_size))
    inv = 1.0 / max(1e-9, fit * zoom)
    c0 = 0.5 + (e0 - 0.5 + pan) / inv
    c1 = 0.5 + (e1 - 0.5 + pan) / inv
    if c0 > c1:
        c0, c1 = c1, c0
    c0 = max(0.0, min(1.0, c0))
    c1 = max(0.0, min(1.0, c1))
    return (lb_origin + c0 * lb_size, lb_origin + c1 * lb_size)


def tile_screen_bbox(
    tile_rect: Rect,
    *,
    pan: tuple[float, float],
    fit: tuple[float, float],
    zoom: float,
    letterbox: Rect = _IDENTITY_LETTERBOX,
) -> Rect:
    """A tile's framebuffer-fraction bounding box ``(x, y, w, h)`` for iBBox."""
    x0, x1 = _axis_screen_span(
        tile_rect[0], tile_rect[2], pan[0], fit[0], zoom, letterbox[0], letterbox[2]
    )
    y0, y1 = _axis_screen_span(
        tile_rect[1], tile_rect[3], pan[1], fit[1], zoom, letterbox[1], letterbox[3]
    )
    return (x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0))


# ---------------------------------------------------------------------------
# Uniform packing
# ---------------------------------------------------------------------------


def pack_tiled_image_view_uniforms(
    view: TiledImageView,
    *,
    letterbox: Rect | None = None,
    extra: bytes = b"",
    clip_matrix: Sequence[float] | None = None,
) -> bytes:
    """Bytes for one tiled frame's ``UBuf`` (see the module docstring layout).

    ``clip_matrix`` is the backend clip-space correction
    (``rhi.clipSpaceCorrMatrix()``); the view has no RHI of its own, so the
    render path supplies it and the default is identity. ``extra`` (tab
    feature/diff uniforms) is zero-padded to ``_UNIFORM_EXTRA_CAPACITY`` so
    the returned block is always ``_UNIFORM_BLOCK_SIZE`` bytes.
    """
    matrix = tuple(
        float(value)
        for value in (
            clip_matrix if clip_matrix is not None else _IDENTITY_MATRIX16
        )
    )
    if len(matrix) != 16:
        raise ValueError(
            f"clip_matrix must have 16 floats, got {len(matrix)}"
        )
    lb = letterbox if letterbox is not None else _IDENTITY_LETTERBOX
    if len(lb) != 4:
        raise ValueError(f"letterbox must have 4 floats, got {len(lb)}")
    zoom = float(view.zoom)
    pan_x, pan_y = float(view.pan[0]), float(view.pan[1])
    fit = view.fit if view.fit is not None else (1.0, 1.0)
    header = struct.pack(
        _UNIFORM_HEADER_FMT,
        *matrix,
        float(lb[0]), float(lb[1]), float(lb[2]), float(lb[3]),
        pan_x, pan_y,
        zoom, zoom,
        float(fit[0]), float(fit[1]),
        0.0, 0.0,
    )
    if len(extra) > _UNIFORM_EXTRA_CAPACITY:
        raise ValueError(
            f"extra uniform bytes {len(extra)} exceed reserved capacity "
            f"{_UNIFORM_EXTRA_CAPACITY}"
        )
    return header + bytes(extra) + b"\x00" * (_UNIFORM_EXTRA_CAPACITY - len(extra))


# ---------------------------------------------------------------------------
# Declared data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LodPolicy:
    """How the view picks among a multi-level source's pyramid levels.

    ``mode``:

    - ``"immediate"``: the selected level is drawn every frame. Falls back
      under its own still-resident previous level while it fills in.
    - ``"settle"``: the currently drawn level is held until the newly
      selected target level's visible tiles are all resident (and its mip
      cascade has drained); the held level keeps being drawn meanwhile.

    ``settle_ms`` is a minimum hold, in milliseconds, before a resident
    target is promoted to drawn (a debounce against level flapping). ``0``
    promotes as soon as the target is resident; it is measured with
    ``time.perf_counter`` (never used for any residency/budget decision --
    that stays on the shared ``realize_specs`` loop).
    """

    mode: str = "immediate"
    settle_ms: int = 0

    def __post_init__(self) -> None:
        if self.mode not in ("immediate", "settle"):
            raise ValueError(
                f"LodPolicy.mode must be 'immediate' or 'settle', got {self.mode!r}"
            )
        if int(self.settle_ms) < 0:
            raise ValueError("LodPolicy.settle_ms must be >= 0")


@dataclass(frozen=True)
class TiledImageSource:
    """The source a view draws, optionally as a pyramid of levels.

    ``store`` is any pixel source ``crop_apron_tile`` accepts (a
    ``TiledPixelStore`` or a PIL-like ``.size``/``.crop()`` object) and is
    the single-level/level-0 form. ``levels`` (E2) is an optional complete,
    ordered pyramid description -- a mapping or sequence of
    ``(level_key, store)`` pairs, **coarsest first, finest last**, so the
    last entry is level 0. Position in that sequence fixes the level number
    (``level_count - 1 - index``); a ``None`` ``level_key`` defaults to
    ``key`` for level 0 and ``(key, level)`` for coarser levels. When
    ``levels`` is ``None`` the view is byte-identical to E1 (one level).
    """

    key: object
    store: object
    level_key: object | None = None
    levels: (
        tuple[tuple[object, object], ...] | Mapping[object, object] | None
    ) = None


@dataclass(frozen=True)
class _LevelTile:
    """One drawable tile of a specific pyramid level (needed so fallback and
    target instances can share one draw call while each resolves its own
    level-scoped array layer)."""

    level: int
    key: object
    rect: Rect
    index: TileIndex


def _normalize_levels(
    source: TiledImageSource,
) -> list[tuple[int, object, object]]:
    """``[(level, source_key, store), ...]`` ascending by level (0 = base).

    ``None``/empty ``levels`` is the E1 single-level form. Otherwise the
    sequence/mapping is read coarsest-first/finest-last and indexed from the
    end, so the finest entry is level 0.
    """
    raw = source.levels
    if raw:
        if isinstance(raw, Mapping):
            pairs = list(raw.items())
        else:
            pairs = [tuple(pair) for pair in raw]
    else:
        pairs = [(source.key, source.store)]
    count = len(pairs)
    normalized: list[tuple[int, object, object]] = []
    for position, (level_key, store) in enumerate(pairs):
        level = count - 1 - position
        if level_key is None:
            level_key = source.key if level == 0 else (source.key, level)
        normalized.append((level, level_key, store))
    normalized.sort(key=lambda entry: entry[0])
    return normalized


@dataclass(frozen=True)
class TiledImageView:
    """Per-frame view transform. ``fit`` is derived from the store size when
    ``None`` (see ``contain_fit_scale``)."""

    zoom: float
    pan: tuple[float, float]
    fb_size: tuple[int, int]
    fit: tuple[float, float] | None = None


@dataclass
class TiledViewHooks:
    """Optional per-surface hooks. ``None`` = single-image / no extras."""

    #: Multi-level LOD policy (see ``LodPolicy``); ``None`` = immediate.
    lods: LodPolicy | None = None
    #: Per-source letterbox/slot rect in framebuffer fractions.
    letterbox: Callable[[], Rect] | None = None
    #: Tab feature/diff uniforms appended after the view header.
    uniform_extra: Callable[[], bytes] | None = None
    #: Runs before the pass opens (``record_array_draw`` pre_begin).
    feature_prepare: Callable[[], None] | None = None
    #: Runs inside the pass after the draw (``record_array_draw`` in_pass).
    feature_record: Callable[[], None] | None = None
    #: Called with the set of tile indices uploaded this frame.
    on_uploaded: Callable[[set], None] | None = None


@dataclass(frozen=True)
class TiledViewResult:
    drawn: bool
    covered: bool
    instances: int
    resident: int


# ---------------------------------------------------------------------------
# GPU resource + residency owners
# ---------------------------------------------------------------------------


class _TiledImageArrayResources(TileArrayResourcesBase):
    """The engine view's tile-array resource owner (one array, one shader,
    the shared instance layout)."""

    def __init__(self, *, rhi_getter, sampler_getter, load_shader, name_prefix):
        super().__init__(
            rhi_getter=rhi_getter,
            sampler_getter=sampler_getter,
            load_shader=load_shader,
            layer_px=_ARRAY_LAYER_PX,
            array_capacity=_ARRAY_CAPACITY,
            name_prefix=name_prefix,
            instance_stride=ARRAY_INSTANCE_STRIDE,
            uniform_block_size=_UNIFORM_BLOCK_SIZE,
            instance_attributes=ARRAY_INSTANCE_ATTRIBUTES,
            vertex_shader_name="tiled_image_array.vert.qsb",
            fragment_shader_name="tiled_image_array.frag.qsb",
            default_sampler_name="linear",
        )


class _TiledImageResidencyRealizer(TileResidencyRealizerBase):
    """Single-source residency: uploads each cropped tile into the shared
    texture array via the shared realizer loop (no private budget loop)."""

    def __init__(self, *, array_resources, tile_cache_budget_bytes=_TILE_CACHE_BUDGET_BYTES):
        super().__init__(tile_cache_budget_bytes=tile_cache_budget_bytes)
        self._array_resources = array_resources
        #: Tile indices uploaded by the most recent ``realize_specs`` call.
        self.last_uploaded: set[TileIndex] = set()

    def _upload_tile(
        self, tile_service, key, index, tile_image, updates, dirty_layers, region
    ) -> None:
        self._array_resources.upload_tile_to_array(
            tile_service, key, index, tile_image, updates, dirty_layers
        )
        self.last_uploaded.add(index)


# ---------------------------------------------------------------------------
# The view
# ---------------------------------------------------------------------------


class SingleImageTiledView:
    """Draws one tiled source from its shared texture-array tiles.

    Additive and fail-closed: before a source is set (or with no resident
    tile yet) ``render`` records nothing, so the caller keeps its own
    raster/cover batch. The caller's present policy keys off
    ``TiledViewResult.covered``, never off "at least one tile drawn".
    """

    def __init__(self, *, rhi_getter, sampler_getter, load_shader, name_prefix):
        self._rhi_getter = rhi_getter
        self._sampler_getter = sampler_getter
        self._load_shader = load_shader
        self._name_prefix = name_prefix
        self.resources = _TiledImageArrayResources(
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
        self._realizer = _TiledImageResidencyRealizer(array_resources=self.resources)
        self.tile_service: TileTextureService | None = None
        self._source: TiledImageSource | None = None
        self._vertex_buffer = None
        self._dirty_layers: dict[int, set[int]] = {}
        # Multi-level (E2) state. ``_level_count <= 1`` keeps the E1 path.
        self._level_count: int = 0
        self._level_keys: dict[int, object] = {}
        self._level_stores: dict[int, object] = {}
        self._key_levels: dict[object, int] = {}
        #: Last level whose visible set was fully drawable (fallback baseline).
        self._fallback_level: int | None = None
        #: Level currently drawn (settle mode holds it until the target lands).
        self._render_level: int | None = None
        #: Settle debounce bookkeeping (level + perf_counter seconds).
        self._settle_target_level: int | None = None
        self._settle_since: float = 0.0

    # -- lifecycle -----------------------------------------------------------

    @property
    def _rhi(self):
        rhi = self._rhi_getter()
        assert rhi is not None
        return rhi

    def _clip_matrix(self) -> tuple[float, ...] | None:
        try:
            rhi = self._rhi_getter()
        except Exception:
            return None
        if rhi is None:
            return None
        try:
            return tuple(float(v) for v in rhi.clipSpaceCorrMatrix().data())
        except Exception:
            return None

    @staticmethod
    def _store_size(store) -> tuple[int, int]:
        try:
            width, height = store.size
            return (int(width), int(height))
        except Exception:
            return (0, 0)

    def set_source(self, source: TiledImageSource) -> None:
        """Adopt a source (single- or multi-level) and register every level's
        tile grid through one ``TileTextureService``. Any previous source's
        residency is dropped first (a fresh service), so no stale layer can be
        sampled for the new content."""
        self._release_gpu()
        self._source = source
        service = TileTextureService(
            max_tile_extent=_LIVE_TILE_EXTENT,
            max_array_size=_ARRAY_CAPACITY,
        )
        self._level_keys = {}
        self._level_stores = {}
        self._key_levels = {}
        levels = _normalize_levels(source)
        for level, level_key, store in levels:
            width, height = self._store_size(store)
            service.register_source(level_key, (max(1, width), max(1, height)))
            self._level_keys[level] = level_key
            self._level_stores[level] = store
            self._key_levels[level_key] = level
        self._level_count = len(levels)
        self.tile_service = service
        self._render_level = None
        self._fallback_level = None
        self._settle_target_level = None
        self._settle_since = 0.0

    def clear_source(self) -> None:
        """Drop the current source + its GPU-side dirty bookkeeping. Idempotent."""
        self._release_gpu()
        self._source = None
        self.tile_service = None
        self._level_count = 0
        self._level_keys = {}
        self._level_stores = {}
        self._key_levels = {}

    def _release_gpu(self) -> None:
        self._dirty_layers = {}
        self._realizer.last_uploaded = set()
        self._render_level = None
        self._fallback_level = None
        self._settle_target_level = None
        self._settle_since = 0.0
        try:
            self._mip_cascade.release()
        except Exception:
            pass

    def release(self) -> None:
        """Destroy every GPU resource this view owns."""
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
        self._source = None

    def has_source(self) -> bool:
        return self._source is not None and self.tile_service is not None

    def store_size(self) -> tuple[int, int]:
        if self._source is None:
            return (0, 0)
        store = self._level_stores.get(0)
        if store is None:
            store = self._source.store
        return self._store_size(store)

    def _level_key(self, level: int) -> object:
        return self._level_keys[level]

    def _level_store(self, level: int) -> object:
        return self._level_stores[level]

    def _level_for_key(self, key: object) -> int | None:
        try:
            return self._key_levels.get(key)
        except TypeError:
            return None

    def _now_ms(self) -> float:
        return float(time.perf_counter()) * 1000.0

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
            raise RuntimeError("Failed to create tiled image view vertex buffer")
        self._vertex_buffer = buffer

    # -- draw ----------------------------------------------------------------

    def render(
        self,
        command_buffer,
        *,
        updates,
        target,
        clear_color,
        view: TiledImageView,
        hooks: TiledViewHooks | None = None,
    ) -> TiledViewResult:
        """Upload this frame's visible tiles and record one instanced draw.

        An empty visible set or a not-yet-resident one records nothing and
        returns ``drawn=False``; the caller keeps its own raster/cover batch.
        Multi-level sources (``TiledImageSource.levels``) route through the
        LOD/fallback path; a single level keeps E1's exact behaviour.
        """
        if self._source is None or self.tile_service is None:
            return TiledViewResult(False, False, 0, 0)
        if target is None or command_buffer is None:
            return TiledViewResult(False, False, 0, 0)
        hooks = hooks or TiledViewHooks()
        store_w, store_h = self.store_size()
        if store_w <= 0 or store_h <= 0:
            return TiledViewResult(False, False, 0, 0)

        fb_w = max(1, int(view.fb_size[0]))
        fb_h = max(1, int(view.fb_size[1]))
        try:
            zoom = float(view.zoom) or 1.0
        except Exception:
            zoom = 1.0
        pan = (float(view.pan[0]), float(view.pan[1]))
        fit = view.fit
        if fit is None:
            fit = contain_fit_scale((store_w, store_h), fb_w, fb_h)
        fit = (float(fit[0]), float(fit[1]))
        effective_view = replace(view, fit=fit)

        letterbox: Rect = _IDENTITY_LETTERBOX
        if hooks.letterbox is not None:
            hook_letterbox = hooks.letterbox()
            if hook_letterbox is not None:
                letterbox = tuple(float(v) for v in hook_letterbox)
        if len(letterbox) != 4:
            letterbox = _IDENTITY_LETTERBOX

        if self._level_count > 1:
            return self._render_multi_level(
                command_buffer,
                updates=updates,
                target=target,
                clear_color=clear_color,
                view=view,
                hooks=hooks,
                effective_view=effective_view,
                pan=pan,
                fit=fit,
                zoom=zoom,
                letterbox=letterbox,
            )
        return self._render_single_level(
            command_buffer,
            updates=updates,
            target=target,
            clear_color=clear_color,
            view=view,
            hooks=hooks,
            effective_view=effective_view,
            pan=pan,
            fit=fit,
            zoom=zoom,
            letterbox=letterbox,
        )

    def _render_single_level(
        self,
        command_buffer,
        *,
        updates,
        target,
        clear_color,
        view: TiledImageView,
        hooks: TiledViewHooks,
        effective_view: TiledImageView,
        pan: tuple[float, float],
        fit: tuple[float, float],
        zoom: float,
        letterbox: Rect,
    ) -> TiledViewResult:
        """E1 single-level path: one source key, ``covered`` = every visible
        tile resident (mip-cascade state is not part of ``covered`` here)."""
        key = self._source.key
        service = self.tile_service
        grid = service.grid_for(key)
        plan = build_slot_plan_tiles(service, key, pan, fit, zoom)
        self._ensure_vertex_buffer()

        if updates is not None and grid is not None:
            visible_rect = slot_visible_rect(pan, fit, zoom, grid)
            spec = ResidencySpec(
                key=key,
                grid=grid,
                visible_rect=visible_rect,
                crop_source=self._source.store,
            )
            self._realizer.last_uploaded = set()
            self._realizer.realize_specs(
                service, [spec], updates, dirty_layers=self._dirty_layers
            )
            if hooks.on_uploaded is not None:
                hooks.on_uploaded(set(self._realizer.last_uploaded))

        # Submit tile uploads BEFORE the mip cascade reads them back: the
        # cascade samples just-uploaded level-0 content, which a same-batch
        # (unsubmitted) write does not guarantee visibility for.
        if updates is not None:
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

        instances = self._build_instances(plan, pan, fit, zoom, letterbox)
        covered = bool(plan) and all(
            service.is_resident(key, tile.index) for tile in plan
        )
        resident = len(service.resident_tiles(key))
        if not instances:
            return TiledViewResult(
                drawn=False, covered=covered, instances=0, resident=resident
            )

        self._draw_instances(
            command_buffer,
            instances,
            target=target,
            clear_color=clear_color,
            hooks=hooks,
            effective_view=effective_view,
            letterbox=letterbox,
        )
        return TiledViewResult(
            drawn=True,
            covered=covered,
            instances=len(instances),
            resident=resident,
        )

    def _render_multi_level(
        self,
        command_buffer,
        *,
        updates,
        target,
        clear_color,
        view: TiledImageView,
        hooks: TiledViewHooks,
        effective_view: TiledImageView,
        pan: tuple[float, float],
        fit: tuple[float, float],
        zoom: float,
        letterbox: Rect,
    ) -> TiledViewResult:
        """E2 path: pick a pyramid level, realize the target *and* the
        fallback baseline in one ``realize_specs`` call, then draw the target
        (or its held level) with the previous fully-drawable level underneath
        wherever the target does not already cover it."""
        service = self.tile_service
        self._ensure_vertex_buffer()
        store_w, store_h = self._store_size(self._level_store(0))
        fb_w = max(1, int(view.fb_size[0]))
        fb_h = max(1, int(view.fb_size[1]))
        disp_w = fb_w * letterbox[2] * fit[0] * zoom
        disp_h = fb_h * letterbox[3] * fit[1] * zoom
        dest_scale = max(
            disp_w / float(max(1, store_w)), disp_h / float(max(1, store_h))
        )
        target_level = select_level(dest_scale, self._level_count)
        policy = hooks.lods if isinstance(hooks.lods, LodPolicy) else LodPolicy()

        # Settle debounce: the clock only gates *when* an already-resident
        # target is promoted to drawn; it never drives residency/budget.
        if policy.mode == "settle":
            if target_level != self._settle_target_level:
                self._settle_target_level = target_level
                self._settle_since = self._now_ms()
            if int(policy.settle_ms) > 0:
                debounce_ok = (self._now_ms() - self._settle_since) >= float(
                    policy.settle_ms
                )
            else:
                debounce_ok = True
        else:
            self._settle_target_level = target_level
            debounce_ok = True

        # One realize call for the target level plus the fallback baseline
        # (deduplicated), never a second service or upload loop.
        spec_levels: list[int] = []
        for level in (target_level, self._fallback_level):
            if level is None or level in spec_levels or level not in self._level_keys:
                continue
            spec_levels.append(level)
        specs: list[ResidencySpec] = []
        for level in spec_levels:
            level_key = self._level_key(level)
            grid = service.grid_for(level_key)
            if grid is None:
                continue
            specs.append(
                ResidencySpec(
                    key=level_key,
                    grid=grid,
                    visible_rect=slot_visible_rect(pan, fit, zoom, grid),
                    crop_source=self._level_store(level),
                )
            )
        if updates is not None and specs:
            self._realizer.last_uploaded = set()
            self._realizer.realize_specs(
                service, specs, updates, dirty_layers=self._dirty_layers
            )
            if hooks.on_uploaded is not None:
                hooks.on_uploaded(set(self._realizer.last_uploaded))

        # Submit tile uploads BEFORE the mip cascade reads them back (same
        # ordering contract as the single-level path).
        if updates is not None:
            command_buffer.resourceUpdate(updates)

        dirty_layers = self._dirty_layers
        self._dirty_layers = {}
        cascade_pending = False
        if dirty_layers:
            deferred = self._mip_cascade.generate_all_dirty_mips(
                command_buffer,
                self._vertex_buffer,
                dirty_layers,
                MIPS_CASCADE_TIME_BUDGET_MS,
            )
            if deferred:
                self._dirty_layers = deferred
                cascade_pending = True

        _, target_fully_resident = self._plan_residency(
            target_level, pan, fit, zoom
        )
        target_tiles = self._resident_items(target_level, pan, fit, zoom)

        # Settle hold: keep drawing the current level until the target is
        # fully resident, cascade-drained, and the debounce has elapsed.
        if policy.mode == "settle":
            if self._render_level is None:
                self._render_level = target_level
            elif (
                target_level != self._render_level
                and target_fully_resident
                and not cascade_pending
                and debounce_ok
            ):
                self._render_level = target_level
        else:
            self._render_level = target_level
        render_level = self._render_level

        if render_level == target_level:
            render_fully_resident = target_fully_resident
        else:
            _, render_fully_resident = self._plan_residency(
                render_level, pan, fit, zoom
            )
        render_tiles = self._resident_items(render_level, pan, fit, zoom)
        render_key = self._level_key(render_level)
        baseline_level = self._fallback_level
        baseline_key = (
            self._level_key(baseline_level)
            if baseline_level in self._level_keys
            else None
        )

        def build_fallback_items(prior_key):
            prior_level = self._level_for_key(prior_key)
            if prior_level is None:
                return []
            return self._resident_items(prior_level, pan, fit, zoom)

        def drop_covered(fallback_items, current_items):
            keep = drop_covered_fallback_tiles(
                [item.rect for item in fallback_items],
                [item.rect for item in current_items],
            )
            return [fallback_items[i] for i in keep]

        new_baseline_key, draw_plan = resolve_fallback_lod(
            key=render_key,
            current_items=render_tiles,
            more_pending=not render_fully_resident,
            last_good_key=baseline_key,
            build_fallback_items=build_fallback_items,
            drop_covered=drop_covered,
            cascade_pending=cascade_pending,
        )
        self._fallback_level = (
            self._level_for_key(new_baseline_key)
            if new_baseline_key is not None
            else None
        )

        instances = self._build_level_instances(
            draw_plan, pan=pan, fit=fit, zoom=zoom, letterbox=letterbox
        )
        fallback_drawn = any(item.level != render_level for item in draw_plan)
        # Honest coverage: only the selected target, only when fully resident
        # and the cascade has drained, and never while fallback is drawn.
        covered = (
            render_level == target_level
            and bool(target_tiles)
            and target_fully_resident
            and not cascade_pending
            and not fallback_drawn
        )
        resident = sum(
            len(service.resident_tiles(level_key))
            for level_key in self._key_levels
        )
        if not instances:
            return TiledViewResult(
                drawn=False, covered=covered, instances=0, resident=resident
            )

        drawn, count = self._draw_instances(
            command_buffer,
            instances,
            target=target,
            clear_color=clear_color,
            hooks=hooks,
            effective_view=effective_view,
            letterbox=letterbox,
        )
        return TiledViewResult(
            drawn=drawn,
            covered=covered,
            instances=count,
            resident=resident,
        )

    def _plan_residency(
        self, level: int, pan, fit, zoom
    ) -> tuple[list, bool]:
        """This level's visible tile plan and whether every tile is resident."""
        service = self.tile_service
        level_key = self._level_key(level)
        plan = build_slot_plan_tiles(service, level_key, pan, fit, zoom)
        fully_resident = bool(plan) and all(
            service.is_resident(level_key, tile.index) for tile in plan
        )
        return plan, fully_resident

    def _resident_items(
        self, level: int, pan, fit, zoom
    ) -> list[_LevelTile]:
        """The drawable (slot-resolved) subset of ``level``'s visible tiles."""
        service = self.tile_service
        level_key = self._level_key(level)
        plan = build_slot_plan_tiles(service, level_key, pan, fit, zoom)
        return [
            _LevelTile(
                level=level, key=level_key, rect=tile.rect, index=tile.index
            )
            for tile in plan
            if service.is_resident(level_key, tile.index)
            and service.slot_for(level_key, tile.index) is not None
        ]

    def _build_level_instances(
        self,
        items,
        *,
        pan,
        fit,
        zoom,
        letterbox: Rect,
    ) -> list[ArrayInstance]:
        """Instances for a mixed fallback/target plan; each item resolves its
        own ``(level, index)`` array layer (fail-closed, no substitution)."""
        service = self.tile_service
        layer_px = float(_ARRAY_LAYER_PX)
        instances: list[ArrayInstance] = []
        for item in items:
            slot = service.slot_for(item.key, item.index)
            if slot is None:
                continue
            _array_index, layer = slot
            scale = content_scale_for(
                service.content_size_for(item.key, item.index), layer_px
            )
            content_scale = (scale[0], scale[1], scale[0], scale[1])
            bbox = tile_screen_bbox(
                item.rect, pan=pan, fit=fit, zoom=zoom, letterbox=letterbox
            )
            instances.append(
                ArrayInstance(
                    rect1=item.rect,
                    rect2=item.rect,
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

    def _draw_instances(
        self,
        command_buffer,
        instances,
        *,
        target,
        clear_color,
        hooks,
        effective_view,
        letterbox,
    ) -> tuple[bool, int]:
        """One uniform pack + one ``record_array_draw`` for a frame."""
        extra = b""
        if hooks.uniform_extra is not None:
            hook_extra = hooks.uniform_extra()
            if hook_extra is not None:
                extra = bytes(hook_extra)
        uniform_bytes = pack_tiled_image_view_uniforms(
            effective_view,
            letterbox=letterbox,
            extra=extra,
            clip_matrix=self._clip_matrix(),
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
            pre_begin=hooks.feature_prepare,
            in_pass=hooks.feature_record,
        )
        return True, len(instances)

    def _build_instances(
        self,
        plan,
        pan,
        fit,
        zoom,
        letterbox: Rect,
    ) -> list[ArrayInstance]:
        service = self.tile_service
        key = self._source.key
        layer_px = float(_ARRAY_LAYER_PX)
        instances: list[ArrayInstance] = []
        for tile in plan:
            slot = service.slot_for(key, tile.index)
            if slot is None:
                # Fail closed: no array slot yet -> skip this tile entirely,
                # never substitute a neighbour's layer.
                continue
            _array_index, layer = slot
            scale = content_scale_for(
                service.content_size_for(key, tile.index), layer_px
            )
            content_scale = (scale[0], scale[1], scale[0], scale[1])
            bbox = tile_screen_bbox(
                tile.rect, pan=pan, fit=fit, zoom=zoom, letterbox=letterbox
            )
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
