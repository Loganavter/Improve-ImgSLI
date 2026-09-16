"""Ctx-first resolver protocol + binding bundle (overlay-shell S1).

``OverlayResolver`` is the tab-side seam for per-frame overlay blocks:
``resolve(ctx)`` takes the opaque per-frame pass context first and
returns packed uniform blocks (engine types: ``tuple[bytes, ...]``).
The engine forwards ``ctx`` without interpreting it and never names
tab geometry -- the tab binds its own frame sources (frame state and
host-side helpers) behind the closure before handing blocks over.

``OverlayBinding`` declares *what* to mount for one pass (shader
location + uniform size). Blocks flow per frame through the resolver,
so the bundle itself holds no per-frame state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .semantic import SemanticOverlayItems, SemanticResolver

__all__ = [
    "OverlayBinding",
    "OverlayResolver",
    "SemanticOverlayItems",
    "SemanticResolver",
]


@runtime_checkable
class OverlayResolver(Protocol):
    """Tab-side uniform-block resolver: ctx in, packed blocks out."""

    def __call__(self, ctx: Any) -> tuple[bytes, ...]:
        """Resolve this frame's uniform blocks from the opaque context."""
        ...


@dataclass(frozen=True, slots=True)
class OverlayBinding:
    """Mount declaration for one overlay pass (bindings only, no GPU)."""

    shader_dir: Path
    shader_stem: str
    uniform_size: int
