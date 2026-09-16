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
- ``UniformPassView`` (``views.py``): pilot-compat surface exposing the
  legacy four access points (``rhi`` / ``ensure_items`` /
  ``prepare_vertex_buffer`` / ``uniform_buffers``) over an
  ``OverlayShell``, so Phase-3 behavior tests keep pinning the
  delegation without the tab owning GPU objects.

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

from .bindings import OverlayBinding, OverlayResolver
from .shell import FULLSCREEN_VERTICES, OverlayShell
from .views import UniformPassView

__all__ = [
    "FULLSCREEN_VERTICES",
    "OverlayBinding",
    "OverlayResolver",
    "OverlayShell",
    "UniformPassView",
]
