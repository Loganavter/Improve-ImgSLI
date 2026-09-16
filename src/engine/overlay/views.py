"""Pilot-compat surface over ``OverlayShell`` (overlay-shell S1).

Exposes the legacy four access points (``rhi`` / ``ensure_items`` /
``prepare_vertex_buffer`` / ``uniform_buffers``) that Phase-3 behavior
tests pin, delegating each to the owned ``OverlayShell``. The tab pass
keeps its historical staging lines unchanged; GPU allocation and draw
calls live in the shell, never here -- this class defines no
``initialize`` / ``release`` and mints no GPU objects itself, so it
never matches the legacy duplicate-resource fingerprint (see
``tests/contracts/test_overlay_shell.py``).
"""

from __future__ import annotations

from typing import Any

from .shell import OverlayShell

__all__ = ["UniformPassView"]


class UniformPassView:
    """Legacy staging surface delegating to one ``OverlayShell``."""

    def __init__(self, shell: OverlayShell) -> None:
        self._shell = shell

    @property
    def rhi(self) -> Any | None:
        return self._shell.rhi

    @property
    def uniform_buffers(self) -> list:
        return self._shell.slot_uniforms

    def ensure_items(self, count: int) -> None:
        self._shell.ensure_slots(count)

    def prepare_vertex_buffer(self, resource_updates: Any) -> None:
        self._shell.stage_quad(resource_updates)
