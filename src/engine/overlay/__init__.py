"""Shared fullscreen-quad uniform overlay shell (overlay-shell S1).

Minimal public API (S2 mounts onto this verbatim; names are stable):

- ``OverlayShell`` (``shell.py``): owns the retained GPU objects for one
  fullscreen-quad overlay pass -- vertex buffer, graphics pipeline,
  per-item uniform buffers + shader-resource bindings. Entry points:
  ``mount`` / ``ensure_slots`` / ``stage_quad`` / ``stage_slot`` /
  ``clip_matrix`` / ``draw`` / ``teardown``.
- ``OverlayResolver`` + ``OverlayBinding`` (``bindings.py``): the
  tab-side seam. ``OverlayResolver`` is ctx-first -- ``resolve(ctx)``
  takes the opaque per-frame pass context first and returns packed
  uniform blocks (engine types: ``tuple[bytes, ...]``). The engine never
  interprets ``ctx`` and never names tab geometry; the tab binds its own
  frame sources (frame state, host-side helpers) behind the closure.
- ``Rgba`` / ``RectItem`` / ``DiskItem`` / ``TextItem`` +
  ``SemanticOverlayItems`` + ``SemanticResolver`` + the ``pack_divider``
  / ``pack_guides`` / ``pack_capture`` / ``pack_grid_dividers`` /
  ``pack_arcs`` pack functions (``semantic.py``): the v2 scale-free
  seam. Resolvers return canvas-px items; the pack functions apply the
  shell-side scale and emit byte-identical uniform blocks, staged via
  ``OverlayShell.stage_packed``. ``bindings.py`` re-exports the v2
  protocol; the v1 byte-packing ``OverlayResolver`` stays intact for the
  F-b..F-c coexistence window.
- ``UniformPassView`` (``views.py``): pilot-compat surface exposing the
  legacy four access points (``rhi`` / ``ensure_items`` /
  ``prepare_vertex_buffer`` / ``uniform_buffers``) over an
  ``OverlayShell``, so Phase-3 behavior tests keep pinning the
  delegation without the tab owning GPU objects.
- ``TexturedOverlayShell`` (``textured.py``): owns the retained GPU
  objects for one raster-upload overlay pass -- vertex buffer,
  64-byte uniform buffer, linear sampler, RGBA8 texture grown on
  demand, shader-resource bindings, graphics pipeline (premultiplied
  blend, no scissor). Entry points: ``mount`` / ``stage_quad`` /
  ``stage_clip`` / ``upload_frame`` / ``draw`` / ``teardown`` plus
  the ``active`` flag.
- ``TexturedOverlayResolver`` + ``TexturedOverlayBinding``
  (``textured.py``): the tab-side seam for raster passes.
  ``TexturedOverlayResolver`` is ctx-first -- ``resolve(ctx)`` takes
  the opaque per-frame pass context first and returns a framebuffer
  raster as ``(width, height, pixels) | None`` (engine types: bytes
  intake, never host images). The engine never interprets ``ctx``
  and never names tab geometry; the tab binds its own frame sources
  behind the closure.

Ownership rule: tab passes declare bindings only (shader location,
uniform size, ctx-first resolvers, scissor choice). All GPU allocation
and all draw-recorder calls live here. See
``tests/contracts/test_overlay_shell.py`` (S1 owner; S2 extends it).

Method names deliberately differ from the legacy tab-side resource
shape (``initialize`` / ``ensure_items`` / ``release`` +
``uniform_buffers`` / ``srbs``): that shape's single-owner dogma
(``test_canvas_fullscreen_pass_resources_single_owner``) still points
at the tab-side class until the remaining consumers (magnifier, arcs,
filename overlay) migrate. When they do, re-point that dogma here and
retire the legacy class -- do not rename this shell back onto the
legacy names while both exist.
"""

from .bindings import (
    OverlayBinding,
    OverlayResolver,
    SemanticOverlayItems,
    SemanticResolver,
)
from .semantic import (
    ARC_UNIFORM_SIZE,
    CAPTURE_UNIFORM_SIZE,
    DIVIDER_UNIFORM_SIZE,
    GRID_DIVIDER_UNIFORM_SIZE,
    GUIDES_UNIFORM_SIZE,
    DiskItem,
    RectItem,
    Rgba,
    TextItem,
    pack_arcs,
    pack_capture,
    pack_divider,
    pack_grid_dividers,
    pack_guides,
)
from .shell import FULLSCREEN_VERTICES, OverlayShell
from .textured import (
    TEXTURED_UNIFORM_SIZE,
    TexturedOverlayBinding,
    TexturedOverlayResolver,
    TexturedOverlayShell,
)
from .views import UniformPassView

__all__ = [
    "FULLSCREEN_VERTICES",
    "TEXTURED_UNIFORM_SIZE",
    "ARC_UNIFORM_SIZE",
    "CAPTURE_UNIFORM_SIZE",
    "DIVIDER_UNIFORM_SIZE",
    "GRID_DIVIDER_UNIFORM_SIZE",
    "GUIDES_UNIFORM_SIZE",
    "DiskItem",
    "OverlayBinding",
    "OverlayResolver",
    "OverlayShell",
    "RectItem",
    "Rgba",
    "SemanticOverlayItems",
    "SemanticResolver",
    "TextItem",
    "TexturedOverlayBinding",
    "TexturedOverlayResolver",
    "TexturedOverlayShell",
    "UniformPassView",
    "pack_arcs",
    "pack_capture",
    "pack_divider",
    "pack_grid_dividers",
    "pack_guides",
]
