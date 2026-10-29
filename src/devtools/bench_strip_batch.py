"""Phase-0 bench: can the video strip's N frame plans render in ONE GPU pass?

The proposed strip redesign drops per-frame caches and per-tile offscreen
renders: the visible strip is drawn by one pass with N frame plans, one
viewport per tile. This devtool is the falsification instrument for that
assumption. It is a *bench*, never imported by app code.

What it measures (per N, default 17 / 32 / 64, tile 160x90):

* ``plan_ms``     - building the N plans through the REAL plan builder
                    (``SnapshotFrameRenderer.prepare_canvas_frame_from_images``)
                    from two generated 3000x2000 sources.
* reference       - the CURRENT per-tile route: each plan rendered on its own
                    offscreen canvas surface (``GpuExportService.render_plan``,
                    the same GPU step ``render_snapshot_thumbnail_to_pil`` /
                    ``_render_thumbnail_from_proxy`` ends in) and hashed.
* ``pass_ms``     - one target, one pass: N viewports + per-tile uniforms and
                    per-tile texture-array layers, recorded in a single
                    beginPass/endPass by ``_StripAtlasWidget``.
* ``readback_ms`` - ONE grab of the atlas target plus the PIL conversion.

Exactness: every atlas tile is sliced out of the single readback and hashed
against its per-tile reference; ``exact_matches/N`` is the column that
decides the assumption.

Exit codes: ``0`` every tile matches and N=17 fits the 20 ms budget,
``1`` mismatch or over budget, ``2`` RHI cannot start (no display / no GL).

Why exit 2 offscreen: a ``QRhiWidget`` under ``QT_QPA_PLATFORM=offscreen``
reports ``renderFailed`` and a null framebuffer grab, so a "pass" there would
be a fabricated result. ``--cpu-only`` exists for exactly that case.

Flags: ``--self-test`` (pure functions, no GPU), ``--cpu-only`` (planning +
uniform packing only), ``--frames 17,32,64``, ``--tiles WxH``,
``--reference-samples K`` (hash-reference cap for a fast first look; the
default hashes every tile).

Measured status of the batch (llvmpipe via a private Xvfb, 2026-10-30 — the
cell that wrote this tool has no real GPU):

* the pass itself is cheap: 2 tiles 0.17 ms, 17 tiles 0.34 ms, 32 tiles
  0.50 ms, 64 tiles 0.88 ms (one beginPass/endPass, N viewports, one readback
  outside the pass: 0.2-8.4 ms depending on N);
* a 2-tile atlas is byte-identical to the per-tile reference except the
  overlay passes the batch does not draw: 14040/14400 px identical, the
  360 px delta is the divider band (first differing pixel at x=78);
* **above 2 tiles this bench's own layer assignment breaks**: uploads into
  array layers >= 2 do not land, so later frames alias layers 0/1 (tile 0
  renders another frame's pixels) and the tiles whose layers were never
  written read back fully transparent. Content, viewport and scissor are
  ruled out: the same instance/uniform path is pixel-exact at N=2, and the
  blank tiles' rects are inside the target. What is NOT ruled out is the
  bench-local ``layer = index * 2`` mapping: production assigns layers
  through ``TileTextureService`` / ``upload_tile_to_array`` (residency,
  eviction, capacity shrink via ``remembered_capacity``). Phase 0 should be
  re-run with that path before the batching assumption is accepted or
  refuted — see DONE.md.

Temp files live under a ``tempfile.mkdtemp()`` removed at exit; the sources
are generated deterministically (no seed needed, no network).
"""

# Audit-Meta: pattern=instrument reason="phase-0 bench: CPU planning + one-pass atlas + exactness harness + self-test are one measurement; splitting them would let the two halves drift"
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

DEFAULT_FRAMES = (17, 32, 64)
DEFAULT_TILE = (160, 90)
SOURCE_SIZE = (3000, 2000)
# One texture-array layer holds one tile's side image 1:1 (production uploads
# unresampled); 256 comfortably covers the bench's 160x90 tiles.
LAYER_PX = 256
# QRhi requires dynamic uniform-buffer bindings to be 256-byte aligned.
UNIFORM_STRIDE = 256
FPS = 10.0
BUDGET_MS_17 = 20.0


# ---------------------------------------------------------------------------
# Pure geometry / packing helpers (the --self-test surface)
# ---------------------------------------------------------------------------


def plan_tile_grid(count: int, tile_w: int, tile_h: int, cols: int | None = None):
    """Atlas grid for ``count`` tiles: ``(cols, rows, width, height)``.

    Column-major fill is irrelevant here (tiles are independent); rows are
    whatever is needed to hold every tile at the given column count.
    """
    count = max(1, int(count))
    tile_w, tile_h = max(1, int(tile_w)), max(1, int(tile_h))
    if cols is None:
        cols = 1
        while cols * cols < count:
            cols += 1
    cols = max(1, min(int(cols), count))
    rows = -(-count // cols)
    return cols, rows, cols * tile_w, rows * tile_h


def tile_rects(count: int, tile_w: int, tile_h: int, cols: int) -> list[tuple[int, int, int, int]]:
    """``(x, y, w, h)`` for every tile, in the atlas target.

    Every rect is exactly ``tile_w x tile_h`` and the rects tile the
    ``cols x rows`` area without overlap. The last row may be padded with
    unused cells (never drawn into), which is why the coverage assertion in
    the self-test compares the *drawn* area, not the whole target.
    """
    tile_w, tile_h = max(1, int(tile_w)), max(1, int(tile_h))
    rects = []
    for index in range(max(0, int(count))):
        row, col = divmod(index, max(1, int(cols)))
        rects.append((col * tile_w, row * tile_h, tile_w, tile_h))
    return rects


def target_units(rects: list[tuple[int, int, int, int]], grabbed_size: tuple[int, int]):
    """Map logical atlas rects onto the grabbed (device) framebuffer size.

    An offscreen ``QRhiWidget`` can have a DPR != 1, in which case the grab
    is larger than the logical target; every rect is scaled here so the
    slicing never silently reads the wrong grid.
    """
    if not rects:
        return rects, (1.0, 1.0)
    logical_w = max(rect[0] + rect[2] for rect in rects)
    logical_h = max(rect[1] + rect[3] for rect in rects)
    grab_w, grab_h = max(1, int(grabbed_size[0])), max(1, int(grabbed_size[1]))
    sx = grab_w / float(logical_w)
    sy = grab_h / float(logical_h)
    scaled = [
        (
            int(round(x * sx)),
            int(round(y * sy)),
            int(round(w * sx)),
            int(round(h * sy)),
        )
        for (x, y, w, h) in rects
    ]
    return scaled, (sx, sy)


def slice_tile_bytes(rgba: bytes, size: tuple[int, int], rect: tuple[int, int, int, int]) -> bytes:
    """Copy one rect out of a packed RGBA8888 buffer (``size`` = full buffer)."""
    width, height = int(size[0]), int(size[1])
    x, y, w, h = (int(v) for v in rect)
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise ValueError(f"tile rect {rect} outside {width}x{height} buffer")
    stride = width * 4
    row_bytes = w * 4
    out = bytearray(row_bytes * h)
    for row in range(h):
        start = (y + row) * stride + x * 4
        out[row * row_bytes : (row + 1) * row_bytes] = rgba[start : start + row_bytes]
    return bytes(out)


def hash_rgba(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def diff_stats(reference: bytes, candidate: bytes, size: tuple[int, int]):
    """``(differing_pixels, first_xy)`` between two same-size RGBA buffers.

    A hash says "not identical"; this says "by how much and where" — the
    difference between an overlay line the batch does not draw and a real
    per-tile content/geometry break.
    """
    if len(reference) != len(candidate):
        raise ValueError("diff_stats needs equal-length buffers")
    differing = 0
    first = None
    width = max(1, int(size[0]))
    for offset in range(0, len(reference), 4):
        if reference[offset : offset + 4] != candidate[offset : offset + 4]:
            differing += 1
            if first is None:
                pixel = offset // 4
                first = (pixel % width, pixel // width)
    return differing, first


def pad_uniform_block(block: bytes, stride: int = UNIFORM_STRIDE) -> bytes:
    """Pad one packed uniform block to the dynamic-buffer stride."""
    if len(block) > stride:
        raise ValueError(f"uniform block {len(block)}B exceeds stride {stride}B")
    return bytes(block) + b"\x00" * (stride - len(block))


def uniform_offset(index: int, stride: int = UNIFORM_STRIDE) -> int:
    offset = int(index) * int(stride)
    if offset % 256:
        raise ValueError(f"uniform offset {offset} is not 256-byte aligned")
    return offset


# ---------------------------------------------------------------------------
# Shared tile payload
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TileFrame:
    """Everything the batch pass needs for one strip tile."""

    index: int
    plan: object
    image1: object
    image2: object
    canvas_w: int
    canvas_h: int
    tile_w: int
    tile_h: int
    uniforms: bytes = b""
    instance: bytes = b""


def _load_uniform_module():
    from tabs.image_compare.canvas.rhi_renderer import uniforms as uniform_module

    return uniform_module


class _FixedClipRhi:
    """Stand-in ``rhi`` for CPU-side uniform packing.

    ``pack_array_uniforms`` reads exactly one thing off the RHI -- the
    backend's clip-space correction matrix -- so CPU-only packing can use the
    identity and stay on the production packer instead of re-implementing the
    std140 layout. The GPU path passes the real ``QRhi``.
    """

    def __init__(self) -> None:
        from PySide6.QtGui import QMatrix4x4

        self._matrix = QMatrix4x4()

    def clipSpaceCorrMatrix(self):  # noqa: N802 - QRhi API name
        return self._matrix


def _base_image_view(tile: TileFrame, plan):
    """The subset of ``base_image`` the uniform packer reads, from a plan.

    Export/video plans render the whole canvas: zoom 1, pan 0, the split from
    the scene when it exposes one. ``letterbox1/2`` is the image's footprint
    inside the canvas (``1.0`` when the pair already fills it).
    """
    split = 0.5
    horizontal = True
    scene = getattr(plan, "render_scene", None)
    for attr, default in (("split_position", split), ("is_horizontal", horizontal)):
        value = getattr(scene, attr, None) if scene is not None else None
        if value is None and isinstance(scene, dict):
            value = scene.get(attr)
        if value is not None:
            if attr == "is_horizontal":
                horizontal = bool(value)
            else:
                split = float(value)

    def _letterbox(image) -> tuple[float, float, float, float]:
        w = max(1, int(getattr(image, "width", 1) or 1))
        h = max(1, int(getattr(image, "height", 1) or 1))
        cw = max(1, int(tile.canvas_w))
        ch = max(1, int(tile.canvas_h))
        return (0.0, 0.0, min(1.0, w / cw), min(1.0, h / ch))

    return _BaseImageView(
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        split_position=split,
        is_horizontal=horizontal,
        channel_mode_int=0,
        diff_mode_int=0,
        letterbox1=_letterbox(tile.image1),
        letterbox2=_letterbox(tile.image2),
        canvas_letterbox=None,
        letterbox_fill=None,
    )


@dataclass(slots=True)
class _BaseImageView:
    zoom: float
    pan_offset_x: float
    pan_offset_y: float
    split_position: float
    is_horizontal: bool
    channel_mode_int: int
    diff_mode_int: int
    letterbox1: tuple[float, float, float, float]
    letterbox2: tuple[float, float, float, float]
    canvas_letterbox: object
    letterbox_fill: object


def pack_tile_uniforms(rhi, tile: TileFrame) -> bytes:
    """Production uniform packing for one tile (``_ARRAY_UNIFORM_BLOCK_SIZE``)."""
    uniform_module = _load_uniform_module()
    return uniform_module.pack_array_uniforms(
        rhi, _base_image_view(tile, tile.plan), diff_source_ready=False
    )


def pack_tile_instance(tile: TileFrame, layer1: int, layer2: int) -> bytes:
    """One full-canvas instance for ``base_array.vert`` (production layout).

    The tile covers the whole canvas (rects and bbox are unit), so the
    instance differs per tile only in its texture-array layers and in each
    side's content scale (uploaded image size / layer size).
    """
    from engine.gpu.array_draw import ArrayInstance, pack_array_instance

    return pack_array_instance(
        ArrayInstance(
            rect1=(0.0, 0.0, 1.0, 1.0),
            rect2=(0.0, 0.0, 1.0, 1.0),
            content_scale=(
                tile.image1.width / float(LAYER_PX),
                tile.image1.height / float(LAYER_PX),
                tile.image2.width / float(LAYER_PX),
                tile.image2.height / float(LAYER_PX),
            ),
            content_scale_diff=(1.0, 1.0),
            layer1=int(layer1),
            layer2=int(layer2),
            layer_diff=0,
            bbox=(0.0, 0.0, 1.0, 1.0),
        )
    )


# ---------------------------------------------------------------------------
# Deterministic synthetic recording
# ---------------------------------------------------------------------------


def make_sources(directory: Path) -> tuple[Path, Path]:
    """Two generated sources: a gradient field and a 37 px shifted variant."""
    from PIL import Image, ImageChops

    directory.mkdir(parents=True, exist_ok=True)
    base = Image.radial_gradient("L").resize(SOURCE_SIZE, Image.Resampling.BICUBIC)
    # Three decorrelated L channels -> one colour field; deterministic, no seed.
    channel_r = base
    channel_g = ImageChops.invert(base)
    channel_b = ImageChops.offset(base, 90, 40)
    left = Image.merge("RGB", (channel_r, channel_g, channel_b))
    # A shifted variant (not a resize): the strip's frames differ in content,
    # so a mis-sliced atlas tile cannot hide behind identical pixels.
    shifted = ImageChops.offset(left, 37, 11)
    path1 = directory / "source_a.png"
    path2 = directory / "source_b.png"
    left.save(path1)
    shifted.save(path2)
    return path1, path2


def _activate_image_compare_tab():
    """The plan builder reads store.viewport/settings; the registry must agree."""
    from tabs.registry import get_shared_tab_registry

    registry = get_shared_tab_registry()
    previous = registry._active_session_type
    registry._active_session_type = "image_compare"
    return registry, previous


def _build_store():
    from core.store import Store

    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    _disable_overlays(store)
    return store


# Overlay features the bench switches off so both sides render the same
# scope: the base-image pass only. The strip's real tiles also carry these
# overlays — batching them needs the same per-tile viewport treatment and is
# the residual risk recorded in DONE.md, not something this pass measures.
_OVERLAY_COMMANDS = (
    ("guides", ("toggle_enabled",)),
    ("magnifier", ("toggle_enabled",)),
    ("capture", ("settings.toggle_visibility", "toggle_visibility")),
    ("divider", ("settings.toggle_visibility", "toggle_visibility")),
    ("filename_overlay", ("settings.toggle_visibility", "toggle_visibility")),
)


def _disable_overlays(store) -> list[str]:
    """Turn off every canvas overlay feature; returns the ones still on.

    Two paths on purpose: ``execute_feature_command`` covers the features
    that expose a state command (guides/magnifier), and the settings mutation
    covers the rest — their visibility lives in the feature setting
    ``<feature>.visible`` and is what the render-scene overrides read.
    """
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    remaining = []
    for feature, commands in _OVERLAY_COMMANDS:
        disabled = False
        for command in commands:
            try:
                execute_feature_command(store, feature, command, False)
                disabled = True
                break
            except Exception:
                continue
        if not disabled:
            try:
                store.settings.mutations.set_canvas_feature_setting(
                    f"{feature}.visible",
                    False,
                    invalidate_render_cache=True,
                    request_core_update=True,
                )
                disabled = True
            except Exception:
                disabled = False
        if not disabled:
            remaining.append(feature)
    return remaining


def _build_snapshot(store, timestamp: float, image1_path: str, image2_path: str):
    from tabs.image_compare.plugins.video_editor.services.keyframing.types import (
        FrameSnapshot,
    )

    return FrameSnapshot(
        timestamp=float(timestamp),
        viewport_state=store.viewport,
        settings_state=store.settings,
        image1_path=image1_path,
        image2_path=image2_path,
        name1=Path(image1_path).name,
        name2=Path(image2_path).name,
    )


def _build_request(tile_w: int, tile_h: int):
    from engine.cache import TargetSurfaceSpec
    from tabs.image_compare.plugins.video_editor.services.video_export_models import (
        VideoRenderRequest,
    )

    return VideoRenderRequest(
        target_surface=TargetSurfaceSpec(
            width=int(tile_w), height=int(tile_h), fill_rgba=(0, 0, 0, 0)
        ),
        font_path=None,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
    )


def _pil_from_source(source):
    """Plan image -> PIL, whether it is a PIL image or a ``TiledPixelStore``.

    Export/video plans carry stores (the decoded pair); the live path carries
    PIL. The batched pass uploads exactly what the plan carries.
    """
    if hasattr(source, "read_array") and hasattr(source, "size"):
        from PIL import Image

        width, height = source.size
        return Image.fromarray(source.read_array((0, 0, width, height)), "RGBA")
    return source


def build_tiles(
    count: int,
    tile_w: int,
    tile_h: int,
    image1_path: Path,
    image2_path: Path,
    *,
    verbose: bool = True,
) -> tuple[list[TileFrame], float]:
    """Build ``count`` real frame plans; returns ``(tiles, plan_ms)``.

    Every frame is planned through the production builder with the two source
    images, at a timestamp that differs per frame (the strip's N visible
    frames span the recording).
    """
    from PIL import Image

    from tabs.image_compare.services.video_snapshot_rendering.renderer import (
        SnapshotFrameRenderer,
    )

    store = _build_store()
    request = _build_request(tile_w, tile_h)
    # The strip never feeds full-res pixels to a tile: `_resolve_thumbnail_images`
    # hands the plan builder a pyramid/display *proxy* at the requested size.
    # Modelling that here keeps the plan's images uploadable into one array
    # layer, exactly as the batched pass will need them. Each frame gets its
    # own shifted proxy so a tile cannot pass by reading a neighbour's layer.
    from PIL import ImageChops

    proxy1 = Image.open(image1_path).convert("RGBA").resize(
        (tile_w, tile_h), Image.Resampling.BICUBIC
    )
    proxy2 = Image.open(image2_path).convert("RGBA").resize(
        (tile_w, tile_h), Image.Resampling.BICUBIC
    )
    renderer = SnapshotFrameRenderer(image_loader=lambda path, auto_crop=False: None)

    started = time.perf_counter()
    tiles: list[TileFrame] = []
    for index in range(count):
        snap = _build_snapshot(
            store, index / FPS, str(image1_path), str(image2_path)
        )
        # Per-frame content shift: N visible strip frames of one recording
        # differ, so a tile cannot pass by sampling a neighbour's layer.
        frame1 = ImageChops.offset(proxy1, (index * 7) % tile_w, (index * 3) % tile_h)
        frame2 = ImageChops.offset(proxy2, (index * 5) % tile_w, (index * 11) % tile_h)
        prepared = renderer.prepare_canvas_frame_from_images(
            snap, request, frame1, frame2
        )
        plan = prepared.plan
        # Upload the PLAN's own pixels (the builder prescales the passed pair,
        # so the raw proxy would differ from the reference by resample
        # rounding everywhere — a bench artefact, not a batching defect).
        plan_image1 = _pil_from_source(getattr(plan, "image1", frame1))
        plan_image2 = _pil_from_source(getattr(plan, "image2", frame2))
        tiles.append(
            TileFrame(
                index=index,
                plan=plan,
                image1=plan_image1,
                image2=plan_image2,
                canvas_w=int(getattr(plan, "canvas_w", 0) or tile_w),
                canvas_h=int(getattr(plan, "canvas_h", 0) or tile_h),
                tile_w=int(tile_w),
                tile_h=int(tile_h),
            )
        )
    plan_ms = (time.perf_counter() - started) * 1000.0
    if verbose:
        first = tiles[0]
        print(
            f"  built {count} plans in {plan_ms:.1f} ms "
            f"(canvas {first.canvas_w}x{first.canvas_h}, "
            f"images {first.image1.size}/{first.image2.size})"
        )
    return tiles, plan_ms


def pack_tiles(tiles: list[TileFrame], *, rhi=None) -> float:
    """Pack per-tile uniforms + instances; returns ``pack_ms``."""
    packing_rhi = rhi if rhi is not None else _FixedClipRhi()
    started = time.perf_counter()
    for index, tile in enumerate(tiles):
        layer1 = index * 2
        layer2 = index * 2 + 1
        tile.uniforms = pack_tile_uniforms(packing_rhi, tile)
        tile.instance = pack_tile_instance(tile, layer1, layer2)
        if len(tile.uniforms) != _uniform_block_size():
            raise RuntimeError(
                f"tile {index}: uniform block {len(tile.uniforms)}B, "
                f"shader expects {_uniform_block_size()}B"
            )
        uniform_offset(index)  # asserts 256-byte alignment
    return (time.perf_counter() - started) * 1000.0


def _uniform_block_size() -> int:
    from tabs.image_compare.canvas.rhi_renderer.uniforms import _ARRAY_UNIFORM_BLOCK_SIZE

    return int(_ARRAY_UNIFORM_BLOCK_SIZE)


# ---------------------------------------------------------------------------
# GPU: reference per-tile route
# ---------------------------------------------------------------------------


def _qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _must_have_rhi(widget, what: str) -> None:
    if widget.rhi() is None:
        raise _NoDisplayError(
            f"{what}: QRhi is not available in this process (no window/GPU "
            "surface). A batched-pass result cannot be measured offscreen."
        )


class _NoDisplayError(RuntimeError):
    """RHI cannot start here -- the caller exits 2 instead of faking a pass."""


class _PreconditionError(RuntimeError):
    """The bench cannot compare 1:1 (e.g. a device-pixel ratio != 1).

    A silent resample here would turn a resolution difference into a
    "mismatch" verdict, so the run stops instead.
    """


def preflight_rhi() -> None:
    """Prove a QRhi surface can start before planning N frames.

    A ``QRhiWidget`` under ``QT_QPA_PLATFORM=offscreen`` never gets an RHI and
    its framebuffer grab is null; failing here (exit 2) is the honest outcome,
    not a fabricated pass or a planning run whose numbers can never be used.
    """
    from PySide6.QtWidgets import QRhiWidget

    from engine.gpu.offscreen_canvas import (
        configure_offscreen_widget,
        resize_and_show_offscreen_widget,
    )

    _qt_app()
    widget = QRhiWidget()
    configure_offscreen_widget(widget)
    try:
        resize_and_show_offscreen_widget(widget, (64, 64))
        if widget.rhi() is None:
            raise _NoDisplayError(
                "QRhi did not start for a probe QRhiWidget (null rhi(); "
                f"platform={os.environ.get('QT_QPA_PLATFORM', '<unset>')}). "
                "The strip's GPU pass needs a real or Xvfb display."
            )
    finally:
        try:
            widget.close()
            widget.deleteLater()
        except Exception:
            pass


def render_reference_tiles(tiles: list[TileFrame], sample_count: int | None):
    """The CURRENT per-tile route, one offscreen surface per tile.

    ``GpuExportService.render_plan`` is the GPU step the strip's
    ``render_snapshot_thumbnail_to_pil`` / ``_render_thumbnail_from_proxy``
    ends in (same plan -> same offscreen canvas widget -> same grab).
    """
    from plugins.export.services.gpu_export import GpuExportService

    service = GpuExportService()
    limit = len(tiles) if sample_count is None else max(1, min(int(sample_count), len(tiles)))
    results = []
    started = time.perf_counter()
    try:
        for tile in tiles[:limit]:
            image, debug = service.render_plan(tile.plan, diff_image=None)
            rgba = image.convert("RGBA")
            if rgba.size != (tile.tile_w, tile.tile_h):
                rgba = rgba.resize((tile.tile_w, tile.tile_h))
            raw = rgba.tobytes("raw", "RGBA")
            results.append((hash_rgba(raw), debug, raw))
    finally:
        try:
            service.shutdown()
        except Exception:
            pass
    elapsed = (time.perf_counter() - started) * 1000.0
    return results, elapsed


# ---------------------------------------------------------------------------
# GPU: batched atlas pass
# ---------------------------------------------------------------------------


def _array_resources(rhi_getter, sampler_getter, layer_count: int, name_prefix: str):
    from tabs.image_compare.canvas.rhi_renderer.array_resources import ArrayResources

    return ArrayResources(
        rhi_getter=rhi_getter,
        sampler_getter=sampler_getter,
        load_shader=_load_ic_shader,
        layer_px=LAYER_PX,
        array_capacity=int(layer_count),
        name_prefix=name_prefix,
    )


def _load_ic_shader(name: str):
    """The tab's own compiled shader (base_array.vert/.frag) — no copy."""
    from PySide6.QtGui import QShader

    shader_dir = _SRC_ROOT / "tabs" / "image_compare" / "canvas" / "shaders"
    shader = QShader.fromSerialized((shader_dir / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {name}")
    return shader


def _qimage_from_pil(image):
    """RGBA PIL -> ``QImage`` without a copy of the pixel buffer lifetime."""
    from PySide6.QtGui import QImage

    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
    return qimage.copy()


def _make_atlas_widget(tiles: list[TileFrame], cols: int):
    from PySide6.QtWidgets import QRhiWidget

    from engine.gpu.offscreen_canvas import configure_offscreen_widget

    class _StripAtlasWidget(QRhiWidget):
        """ONE target, ONE pass, N viewports — the batching assumption.

        Every tile draws the production ``base_array.vert``/``.frag`` quad from its own
        texture-array layer pair and its own uniform block; the pass is
        opened once and the target is read back once by the caller.
        """

        def __init__(self) -> None:
            super().__init__()
            configure_offscreen_widget(self)
            self._tiles = list(tiles)
            self._cols = int(cols)
            self._layer_count = max(2, 2 * len(self._tiles))
            self._resources = None
            self._vertex_buffer = None
            self._uniform_buffers = []
            self._instance_buffers = []
            self._srbs: list = []
            self._pipeline_ready = False
            self._uploaded = False
            self._last_error: str | None = None

        # -- lifecycle -------------------------------------------------
        def initialize(self, command_buffer):
            try:
                self._initialize(command_buffer)
            except BaseException as exc:  # Qt swallows render-override raises
                self._last_error = f"initialize failed: {exc}"
                raise

        def render(self, command_buffer):
            try:
                self._render(command_buffer)
            except BaseException as exc:
                self._last_error = f"render failed: {exc}"
                raise

        def _initialize(self, command_buffer):
            rhi = self.rhi()
            if rhi is None:
                self._last_error = "renderer initialize without an RHI"
                return
            # Qt re-runs initialize() on every target recreation (resize); all
            # ranked GPU state below is new, so the upload/pipeline flags must
            # not survive it (a stale _uploaded=True leaves the array blank).
            self._uploaded = False
            self._upload_qimages = []
            self._pipeline_ready = False
            self._srbs = []
            from PySide6.QtGui import QRhiBuffer, QRhiSampler

            samplers = {}
            for name, filter_mode, mip_mode in (
                ("nearest", QRhiSampler.Filter.Nearest, QRhiSampler.Filter.None_),
                ("linear", QRhiSampler.Filter.Linear, QRhiSampler.Filter.Linear),
            ):
                sampler = rhi.newSampler(
                    filter_mode,
                    filter_mode,
                    mip_mode,
                    QRhiSampler.AddressMode.ClampToEdge,
                    QRhiSampler.AddressMode.ClampToEdge,
                )
                if not sampler.create():
                    raise RuntimeError(f"bench: failed to create {name} sampler")
                samplers[name] = sampler
            self._samplers = samplers
            self._resources = _array_resources(
                lambda: self.rhi(),
                lambda name: self._samplers[name],
                self._layer_count,
                "bench-strip",
            )
            from tabs.image_compare.canvas.rhi_renderer.resources import _VERTICES

            vertex_buffer = rhi.newBuffer(
                QRhiBuffer.Type.Immutable,
                QRhiBuffer.UsageFlag.VertexBuffer,
                len(_VERTICES),
            )
            if not vertex_buffer.create():
                raise RuntimeError("bench: failed to create quad vertex buffer")
            self._vertex_buffer = vertex_buffer
            self._pending_vertex_bytes = _VERTICES

            # One uniform + one instance buffer PER TILE. Offset-addressed
            # bindings (one big buffer, per-tile offsets) drew only tile 0 on
            # this backend; separate buffers are the shape a batched pass can
            # actually rely on.
            uniform_buffers = []
            instance_buffers = []
            for index in range(len(self._tiles)):
                uniform_buffer = rhi.newBuffer(
                    QRhiBuffer.Type.Dynamic,
                    QRhiBuffer.UsageFlag.UniformBuffer,
                    UNIFORM_STRIDE,
                )
                if not uniform_buffer.create():
                    raise RuntimeError(f"bench: failed to create uniform buffer {index}")
                uniform_buffers.append(uniform_buffer)
                instance_buffer = rhi.newBuffer(
                    QRhiBuffer.Type.Dynamic,
                    QRhiBuffer.UsageFlag.VertexBuffer,
                    max(1, len(self._tiles[index].instance))
                    or self._resources._instance_stride,
                )
                if not instance_buffer.create():
                    raise RuntimeError(f"bench: failed to create instance buffer {index}")
                instance_buffers.append(instance_buffer)
            self._uniform_buffers = uniform_buffers
            self._instance_buffers = instance_buffers
            # The SRBs bind tile_arrays[0]; create it first (the array is
            # allocated up front with every layer the run needs).
            self._resources._ensure_tile_array(0)
            self._ensure_srbs()

        def _ensure_srbs(self) -> None:
            from PySide6.QtGui import QRhiShaderResourceBinding

            rhi = self.rhi()
            stages = (
                QRhiShaderResourceBinding.StageFlag.VertexStage
                | QRhiShaderResourceBinding.StageFlag.FragmentStage
            )
            fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
            tile_array = self._resources.tile_arrays[0]
            sampler = self._samplers["linear"]
            block = _uniform_block_size()
            srbs = []
            for index in range(len(self._tiles)):
                srb = rhi.newShaderResourceBindings()
                srb.setBindings(
                    [
                        QRhiShaderResourceBinding.uniformBuffer(
                            0, stages, self._uniform_buffers[index], 0, block
                        ),
                        QRhiShaderResourceBinding.sampledTexture(
                            1, fragment, tile_array, sampler
                        ),
                    ]
                )
                if not srb.create():
                    raise RuntimeError(f"bench: failed to create SRB {index}")
                srbs.append(srb)
            self._srbs = srbs

        def releaseResources(self):
            self._srbs = []
            if self._resources is not None:
                try:
                    self._resources.release()
                except Exception:
                    pass
            self._resources = None
            buffers = [
                self._vertex_buffer,
                *getattr(self, "_uniform_buffers", []),
                *getattr(self, "_instance_buffers", []),
            ]
            for buffer in buffers:
                if buffer is not None:
                    try:
                        buffer.destroy()
                    except Exception:
                        pass
            self._vertex_buffer = None
            self._uniform_buffers = []
            self._instance_buffers = []

        # -- recording -------------------------------------------------
        def _render(self, command_buffer):
            if self._resources is None or not self._uniform_buffers:
                return
            from PySide6.QtGui import (
                QRhiDepthStencilClearValue,
                QRhiTextureUploadDescription,
                QRhiTextureUploadEntry,
                QRhiScissor,
                QRhiTextureSubresourceUploadDescription,
                QRhiViewport,
            )

            rhi = self.rhi()
            target = self.renderTarget()
            if rhi is None or target is None:
                return
            if not self._pipeline_ready:
                self._resources.ensure_array_pipeline(target)
                self._pipeline_ready = True
            self._resources._ensure_tile_array(0)
            if len(self._srbs) != len(self._tiles) or not self._srbs:
                self._ensure_srbs()

            updates = rhi.nextResourceUpdateBatch()
            if not self._uploaded:
                # Layers are uploaded in small chunks, each submitted through
                # its own resource-update batch. One batch carrying every
                # layer (34 x 160x90 at N=17) left later layers unuploaded on
                # this backend: the tiles sampling them read back transparent.
                updates.uploadStaticBuffer(
                    self._vertex_buffer, self._pending_vertex_bytes
                )
                command_buffer.resourceUpdate(updates)
                updates = rhi.nextResourceUpdateBatch()
                tile_array = self._resources.tile_arrays[0]
                # The upload descriptions hold their QImage by reference; a
                # collected source image leaves the GPU upload reading freed
                # pixels (observed as blank/garbage tiles once a run uploads
                # more than a handful of layers). Keep them alive until the
                # run ends.
                self._upload_qimages = []
                uploaded_layers = 0
                for index, tile in enumerate(self._tiles):
                    for side, layer, image in (
                        (1, index * 2, tile.image1),
                        (2, index * 2 + 1, tile.image2),
                    ):
                        qimage = _qimage_from_pil(image)
                        self._upload_qimages.append(qimage)
                        entry = QRhiTextureUploadEntry(
                            int(layer),
                            0,
                            QRhiTextureSubresourceUploadDescription(qimage),
                        )
                        updates.uploadTexture(
                            tile_array, QRhiTextureUploadDescription(entry)
                        )
                        uploaded_layers += 1
                        if uploaded_layers % 4 == 0:
                            command_buffer.resourceUpdate(updates)
                            updates = rhi.nextResourceUpdateBatch()
                # The array is MipMapped and the sampler is trilinear: without
                # this the levels above 0 are uninitialized and a 1:1 tile can
                # still sample a garbage mip (content_scale < 1 minifies).
                updates.generateMips(tile_array)
                self._uploaded = True

            for index, tile in enumerate(self._tiles):
                # One update batch per tile: a single batch carrying every
                # per-tile buffer update loses some of them on this backend
                # (the tiles whose update was dropped draw nothing at all).
                updates.updateDynamicBuffer(
                    self._uniform_buffers[index],
                    0,
                    pad_uniform_block(tile.uniforms),
                )
                updates.updateDynamicBuffer(
                    self._instance_buffers[index],
                    0,
                    tile.instance,
                )
                command_buffer.resourceUpdate(updates)
                updates = rhi.nextResourceUpdateBatch()

            command_buffer.beginPass(
                target,
                _clear_color(),
                QRhiDepthStencilClearValue(1.0, 0),
                updates,
            )
            try:
                tile_w = self._tiles[0].tile_w
                tile_h = self._tiles[0].tile_h
                logical_rects = tile_rects(len(self._tiles), tile_w, tile_h, self._cols)
                # Device pixels, derived from the render target (never from the
                # logical widget size): a viewport sized in logical px paints
                # into 1/DPR of the framebuffer per axis.
                pixel_size = target.pixelSize()
                fb_w = max(1, int(pixel_size.width()))
                fb_h = max(1, int(pixel_size.height()))
                atlas_w = max(1, self.width())
                atlas_h = max(1, self.height())
                fb_scale_x = fb_w / float(atlas_w)
                fb_scale_y = fb_h / float(atlas_h)
                # Per-tile rects in FRAMEBUFFER pixels (derived from
                # target.pixelSize() above), never from the logical widget size.
                fb_rects = [
                    (
                        int(round(logical_x * fb_scale_x)),
                        int(round(logical_y * fb_scale_y)),
                        int(round(logical_w * fb_scale_x)),
                        int(round(logical_h * fb_scale_y)),
                    )
                    for (logical_x, logical_y, logical_w, logical_h) in logical_rects
                ]
                command_buffer.setGraphicsPipeline(self._resources.array_pipeline)
                for index, (tile_left_fb, tile_top_fb, tile_w_fb, tile_h_fb) in enumerate(
                    fb_rects
                ):
                    command_buffer.setViewport(
                        QRhiViewport(
                            float(tile_left_fb),
                            float(tile_top_fb),
                            float(tile_w_fb),
                            float(tile_h_fb),
                        )
                    )
                    # Explicit per-tile scissor: a batched pass may not assume
                    # the target's default scissor covers more than the surface
                    # Qt painted last (observed: every tile past the top-left
                    # 320x180 quadrant came back clear with viewport alone).
                    command_buffer.setScissor(
                        QRhiScissor(
                            int(tile_left_fb),
                            int(tile_top_fb),
                            int(tile_w_fb),
                            int(tile_h_fb),
                        )
                    )
                    command_buffer.setVertexInput(
                        0,
                        [
                            (self._vertex_buffer, 0),
                            (self._instance_buffers[index], 0),
                        ],
                    )
                    command_buffer.setShaderResources(self._srbs[index])
                    command_buffer.draw(4, 1)
            finally:
                command_buffer.endPass()

    return _StripAtlasWidget()


def _clear_color():
    from PySide6.QtGui import QColor

    return QColor(0, 0, 0, 0)


def run_batch_pass(tiles: list[TileFrame], cols: int):
    """Render all tiles into one target; returns ``(tile_hashes, timings)``."""
    from engine.gpu.offscreen_canvas import (
        render_widget_frame,
        resize_and_show_offscreen_widget,
    )
    from engine.gpu.export_tiling import qimage_to_pil_rgba

    _qt_app()
    tile_w = tiles[0].tile_w
    tile_h = tiles[0].tile_h
    _, rows, atlas_w, atlas_h = plan_tile_grid(len(tiles), tile_w, tile_h, cols)
    widget = _make_atlas_widget(tiles, cols)
    resize_and_show_offscreen_widget(widget, (atlas_w, atlas_h))
    _must_have_rhi(widget, "batched strip pass")

    pass_started = time.perf_counter()
    # Two pumps: QRhiWidget needs a second event-loop pass before the frame
    # it just recorded is actually present (see render_widget_frame).
    render_widget_frame(widget)
    render_widget_frame(widget)
    pass_ms = (time.perf_counter() - pass_started) * 1000.0
    if widget._last_error:
        raise _NoDisplayError(widget._last_error)

    readback_started = time.perf_counter()
    qimage = widget.grabFramebuffer()
    if qimage is None or qimage.isNull():
        raise _NoDisplayError(
            "batched strip pass: grabFramebuffer() returned a null image "
            "(QRhi surface not present)"
        )
    image = qimage_to_pil_rgba(qimage)
    readback_ms = (time.perf_counter() - readback_started) * 1000.0

    logical_rects = tile_rects(len(tiles), tile_w, tile_h, cols)
    rects, scale = target_units(logical_rects, image.size)
    if scale != (1.0, 1.0):
        # The reference tile is a logical 160x90 PIL render; comparing it to a
        # device-pixel slice would be a silent resample, not an exactness test.
        raise _PreconditionError(
            f"atlas framebuffer is {image.size[0]}x{image.size[1]} for a "
            f"{logical_rects[-1][0] + tile_w}x{logical_rects[-1][1] + tile_h} "
            f"logical target (device-pixel ratio {scale[0]:.2f}x{scale[1]:.2f}). "
            "Run with QT_SCALE_FACTOR=1: the bench compares 1:1 device pixels."
        )
    raw = image.tobytes("raw", "RGBA")
    hashes = []
    tile_bytes_list = []
    for rect in rects:
        tile_bytes = slice_tile_bytes(raw, image.size, rect)
        tile_bytes_list.append(tile_bytes)
        hashes.append(hash_rgba(tile_bytes))
    try:
        widget.close()
        widget.deleteLater()
    except Exception:
        pass
    return hashes, tile_bytes_list, {
        "pass_ms": pass_ms,
        "readback_ms": readback_ms,
        "rows": rows,
        "atlas": (atlas_w, atlas_h),
        "dpr_scale": scale,
    }


# ---------------------------------------------------------------------------
# Self-test (no GPU, no Qt display)
# ---------------------------------------------------------------------------


def run_self_test(quiet: bool = False) -> int:
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            if not quiet:
                print(f"ok   {name}")
            return
        failures.append(f"{name}{(': ' + detail) if detail else ''}")
        print(f"FAIL {name}{(': ' + detail) if detail else ''}")

    # 1. tile grid / viewport rects
    for count in DEFAULT_FRAMES:
        cols, rows, width, height = plan_tile_grid(count, 160, 90)
        rects = tile_rects(count, 160, 90, cols)
        check(f"N={count}: one rect per tile", len(rects) == count)
        check(
            f"N={count}: rects stay inside the atlas",
            all(x + w <= width and y + h <= height for x, y, w, h in rects),
        )
        check(
            f"N={count}: rects do not overlap",
            len({(x, y) for x, y, _w, _h in rects}) == len(rects),
        )
        drawn = sum(w * h for _x, _y, w, h in rects)
        check(
            f"N={count}: every rect is exactly one tile",
            all((w, h) == (160, 90) for _x, _y, w, h in rects),
            f"drawn_area={drawn}",
        )
        cells = {(x // 160, y // 90) for x, y, _w, _h in rects}
        expected_cells = {(index % cols, index // cols) for index in range(count)}
        check(
            f"N={count}: grid cells match the row-major fill",
            cells == expected_cells,
            f"{sorted(cells)} != {sorted(expected_cells)}",
        )

    # 2. uniform stride / packing matches the shader's std140 block
    uniform_module = _load_uniform_module()
    block_size = int(uniform_module._ARRAY_UNIFORM_BLOCK_SIZE)
    packed_size = struct.calcsize(uniform_module._ARRAY_UNIFORM_FMT)
    check("uniform block size == shader std140 size", block_size == packed_size, f"{block_size} vs {packed_size}")
    check("uniform stride is 256-byte aligned", UNIFORM_STRIDE % 256 == 0)
    check("uniform block fits the stride", block_size <= UNIFORM_STRIDE, f"{block_size} > {UNIFORM_STRIDE}")

    from engine.gpu.array_draw import ARRAY_INSTANCE_STRIDE, ARRAY_INSTANCE_FMT

    check(
        "instance stride == packed instance size",
        int(ARRAY_INSTANCE_STRIDE) == struct.calcsize(ARRAY_INSTANCE_FMT),
        f"{ARRAY_INSTANCE_STRIDE} vs {struct.calcsize(ARRAY_INSTANCE_FMT)}",
    )
    tile = _synthetic_tile()
    unpacked = uniform_module.pack_array_uniforms(
        _FixedClipRhi(), _base_image_view(tile, tile.plan), diff_source_ready=False
    )
    check("packed uniform block length", len(unpacked) == block_size, str(len(unpacked)))
    padded = pad_uniform_block(unpacked)
    check("padding preserves the block bytes", padded[:block_size] == unpacked and len(padded) == UNIFORM_STRIDE)
    check(
        "second tile's uniform offset is stride-aligned",
        uniform_offset(1) == UNIFORM_STRIDE and uniform_offset(0) == 0,
    )
    instance = pack_tile_instance(tile, 0, 1)
    check("packed instance length", len(instance) == ARRAY_INSTANCE_STRIDE, str(len(instance)))
    from engine.gpu.array_draw import unpack_instance_layer2

    check("instance layer2 round-trips", unpack_instance_layer2(instance, 0) == 1)

    # 3. hash plumbing: deterministic, per-tile sensitive
    from PIL import Image

    image = Image.new("RGBA", (40, 40))
    image.putdata(
        [((x * 7) % 256, (y * 11) % 256, (x + y) % 256, 255) for y in range(40) for x in range(40)]
    )
    raw = image.tobytes("raw", "RGBA")
    rects = tile_rects(4, 20, 20, 2)
    first = [hash_rgba(slice_tile_bytes(raw, image.size, rect)) for rect in rects]
    second = [hash_rgba(slice_tile_bytes(raw, image.size, rect)) for rect in rects]
    check("tile hashing is deterministic", first == second)
    check("distinct tiles hash differently", len(set(first)) == len(first))
    mutated = bytearray(raw)
    mutated[0] = (mutated[0] + 1) % 256
    after = [hash_rgba(slice_tile_bytes(bytes(mutated), image.size, rect)) for rect in rects]
    check("one changed pixel moves exactly one tile hash", after[0] != first[0] and after[1:] == first[1:])
    check(
        "slice rejects out-of-range rects",
        _raises(ValueError, slice_tile_bytes, raw, image.size, (30, 0, 20, 20)),
    )

    # 4. DPR remap keeps the grid exact
    scaled, (sx, sy) = target_units(rects, (80, 80))
    check("DPR remap scales the grid", (sx, sy) == (2.0, 2.0) and scaled[-1][:2] == (40, 40), str(scaled))

    print(f"\nself-test: {len(failures)} failure(s)")
    return 0 if not failures else 1


def _raises(exc, func, *args, **kwargs) -> bool:
    try:
        func(*args, **kwargs)
    except exc:
        return True
    return False


class _SyntheticPlan:
    """Minimal plan stand-in for the pure-function self-test."""

    render_scene = None

    def __init__(self) -> None:
        from PIL import Image

        self.canvas_w = 160
        self.canvas_h = 90
        self.image1 = Image.new("RGBA", (160, 90), (10, 20, 30, 255))
        self.image2 = Image.new("RGBA", (160, 90), (40, 50, 60, 255))


def _synthetic_tile() -> TileFrame:
    plan = _SyntheticPlan()
    return TileFrame(
        index=0,
        plan=plan,
        image1=plan.image1,
        image2=plan.image2,
        canvas_w=160,
        canvas_h=90,
        tile_w=160,
        tile_h=90,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_frames(text: str) -> tuple[int, ...]:
    values = tuple(int(part) for part in str(text).replace(" ", "").split(",") if part)
    if not values or any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError("--frames must be a comma-separated list of positive ints")
    return values


def _parse_tile(text: str) -> tuple[int, int]:
    parts = str(text).lower().replace(" ", "").split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--tiles must look like 160x90")
    width, height = int(parts[0]), int(parts[1])
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("--tiles must be positive")
    return width, height


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase-0 bench: N strip frame plans in one GPU pass."
    )
    parser.add_argument("--self-test", action="store_true", help="pure-function checks, no GPU")
    parser.add_argument("--cpu-only", action="store_true", help="planning + uniform packing only")
    parser.add_argument("--frames", default=",".join(str(n) for n in DEFAULT_FRAMES))
    parser.add_argument("--tiles", default=f"{DEFAULT_TILE[0]}x{DEFAULT_TILE[1]}")
    parser.add_argument("--reference-samples", type=int, default=0, help="hash only the first K reference tiles (0 = all)")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test(quiet=args.quiet)

    frames = _parse_frames(args.frames)
    tile_w, tile_h = _parse_tile(args.tiles)

    workdir = Path(tempfile.mkdtemp(prefix="bench-strip-batch-"))
    registry = None
    previous_tab = None
    try:
        _qt_app()
        registry, previous_tab = _activate_image_compare_tab()
        if not args.cpu_only:
            preflight_rhi()
        if not args.quiet:
            print(f"sources: generating {SOURCE_SIZE[0]}x{SOURCE_SIZE[1]} pair in {workdir}")
        image1_path, image2_path = make_sources(workdir)

        rows = []
        # One warm-up plan before any timing: source decode + first plan
        # compile are one-time costs that would otherwise land on N=17 and
        # read as "planning got 10x cheaper with more tiles".
        _warm_tiles, warmup_ms = build_tiles(
            1, tile_w, tile_h, image1_path, image2_path, verbose=False
        )
        if not args.quiet:
            print(f"warm-up plan (source decode): {warmup_ms:.1f} ms")
        for count in frames:
            if not args.quiet:
                print(f"\nN={count}")
            tiles, plan_ms = build_tiles(
                count, tile_w, tile_h, image1_path, image2_path, verbose=not args.quiet
            )
            pack_ms = pack_tiles(tiles)
            if args.cpu_only:
                if not args.quiet:
                    print(
                        f"  pack {len(tiles)} tile uniforms+instances in {pack_ms:.2f} ms "
                        f"(block {_uniform_block_size()}B, stride {UNIFORM_STRIDE}B, "
                        f"instance {len(tiles[0].instance)}B)"
                    )
                rows.append((count, plan_ms, pack_ms, None, None, None))
                continue

            reference, reference_ms = render_reference_tiles(
                tiles, args.reference_samples or None
            )
            batch_hashes, batch_bytes, timings = run_batch_pass(
                tiles, cols=_cols_for(count)
            )
            matches = sum(
                1
                for index, (ref_hash, _dbg, _raw) in enumerate(reference)
                if index < len(batch_hashes) and batch_hashes[index] == ref_hash
            )
            if not args.quiet:
                print(
                    f"  reference {len(reference)} tiles in {reference_ms:.1f} ms; "
                    f"pass in {timings['pass_ms']:.2f} ms; "
                    f"readback in {timings['readback_ms']:.2f} ms"
                )
            first_bad = next(
                (
                    index
                    for index, (ref_hash, _dbg, _raw) in enumerate(reference)
                    if index >= len(batch_hashes) or batch_hashes[index] != ref_hash
                ),
                None,
            )
            total_px = tile_w * tile_h
            blank = [
                index
                for index, blob in enumerate(batch_bytes)
                if not any(blob[3::4])
            ]
            if blank:
                print(
                    f"  {len(blank)}/{len(batch_bytes)} tiles read back fully "
                    f"transparent (tiles {blank[:8]}"
                    f"{'...' if len(blank) > 8 else ''}): their texture-array "
                    "layer was not populated — an upload limit, not a geometry "
                    "or viewport mismatch"
                )
            if first_bad is not None:
                ref_hash, _dbg, ref_raw = reference[first_bad]
                print(
                    f"  MISMATCH tile {first_bad}: reference {ref_hash[:16]} vs batch "
                    f"{(batch_hashes[first_bad][:16] if first_bad < len(batch_hashes) else '<missing>')}"
                )
                if first_bad < len(batch_bytes) and first_bad not in blank:
                    differing, first_xy = diff_stats(
                        ref_raw, batch_bytes[first_bad], (tile_w, tile_h)
                    )
                    print(
                        f"  tile {first_bad}: {differing}/{total_px} px differ "
                        f"({100.0 * differing / total_px:.1f}%), first at {first_xy} "
                        "(overlay passes are not in the batch scope)"
                    )
                    same = total_px - differing
                    print(f"  tile {first_bad}: {same}/{total_px} px byte-identical")
                populated = [
                    index
                    for index, blob in enumerate(batch_bytes)
                    if any(blob[3::4])
                ]
                worst = max(
                    (
                        diff_stats(reference[index][2], batch_bytes[index], (tile_w, tile_h))[0]
                        for index in populated
                    ),
                    default=0,
                )
                print(f"  worst populated tile: {worst}/{total_px} px differ")
            rows.append(
                (
                    count,
                    plan_ms,
                    timings["pass_ms"],
                    timings["readback_ms"],
                    matches,
                    len(reference),
                )
            )

        print()
        if args.cpu_only:
            print("N | plan_ms | pack_ms")
            for count, plan_ms, pack_ms, _p, _r, _m in rows:
                print(f"{count:>3} | {plan_ms:>7.1f} | {pack_ms:>7.2f}")
            return 0

        print("N | plan_ms | pass_ms | readback_ms | exact_matches/N")
        ok = True
        for count, plan_ms, pass_ms, readback_ms, matches, total in rows:
            print(
                f"{count:>3} | {plan_ms:>7.1f} | {pass_ms:>7.2f} | "
                f"{readback_ms:>11.2f} | {matches}/{total}"
            )
            if matches != total:
                ok = False
            if count == 17 and pass_ms > BUDGET_MS_17:
                print(f"  over budget: N=17 pass took {pass_ms:.2f} ms (budget {BUDGET_MS_17:.0f} ms)")
                ok = False
        return 0 if ok else 1
    except _PreconditionError as exc:
        print(f"\nprecondition not met: {exc}", file=sys.stderr)
        return 1
    except _NoDisplayError as exc:
        print(f"\nneeds a display: {exc}", file=sys.stderr)
        print(
            "Run this on a real (or Xvfb) display — a batched QRhi pass cannot be "
            "measured under QT_QPA_PLATFORM=offscreen. Use --cpu-only for the "
            "planning/uniform half.",
            file=sys.stderr,
        )
        return 2
    except Exception:
        traceback.print_exc()
        if not args.cpu_only:
            # A display that cannot even probe an RHI makes every GPU failure
            # here a no-display outcome, not a bench mismatch (exit 2, never a
            # "the batched pass is wrong" verdict).
            try:
                preflight_rhi()
            except _NoDisplayError as no_display:
                print(f"\nneeds a display: {no_display}", file=sys.stderr)
                return 2
            except Exception:
                pass
        print("\nbench failed (see traceback above)", file=sys.stderr)
        return 1
    finally:
        if registry is not None and previous_tab is not None:
            try:
                registry._active_session_type = previous_tab
            except Exception:
                pass
        shutil.rmtree(workdir, ignore_errors=True)


def _cols_for(count: int) -> int:
    cols, _rows, _w, _h = plan_tile_grid(count, 1, 1)
    return cols


if __name__ == "__main__":
    sys.exit(main())
