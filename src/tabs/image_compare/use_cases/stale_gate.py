"""StaleGate — deduped chrome sync (plan_image_pipeline.md Phase 5).

Merges ``widget._render_stale`` / ``widget._metrics_stale`` /
``chrome_sync._render_stale`` / ``_workspace_language_stale`` into a single
set[str] gate (``presenter._stale`` style) so showEvent flushes once.

Usage:
    gate = StaleGate()
    gate.mark("render")   # or "metrics", "language"
    if gate.consume("render"): flush_render()
"""

from __future__ import annotations


class StaleGate:
    def __init__(self) -> None:
        self._stale: set[str] = set()

    def mark(self, kind: str) -> None:
        self._stale.add(kind)

    def is_stale(self, kind: str) -> bool:
        return kind in self._stale

    def consume(self, kind: str) -> bool:
        if kind in self._stale:
            self._stale.discard(kind)
            return True
        return False

    def consume_all(self) -> set[str]:
        out = set(self._stale)
        self._stale.clear()
        return out

    @property
    def stale(self) -> set[str]:
        return set(self._stale)

    def __contains__(self, kind: str) -> bool:
        return kind in self._stale

    def __bool__(self) -> bool:
        return bool(self._stale)

    def clear(self) -> None:
        self._stale.clear()
