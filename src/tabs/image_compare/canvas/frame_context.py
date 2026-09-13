# Audit-Meta: pattern=leaf-collector reason="P1A render-core consolidation scaffold: per-frame decision collector, stdlib-only leaf, no timers/threads"
"""Per-frame render decision collector (P1A frame-context scaffold).

Render decisions (mag-gate, fallback, dedups) are scattered and silent
across ~10 files; every feature re-invents guard/log scaffolding. This
module is the CORE mechanism built once: a small per-frame collector.

- ``FrameDecision`` — one decision: ``pass_name`` (the brief's ``pass``;
  renamed because ``pass`` is a keyword), ``verdict`` (``ran``/``skipped``),
  ``reason`` (grep-friendly free text, fallback-decision log style), ``ids``
  (small identity tuple for correlation — stored by reference, formatted
  only by ``dump()``).
- ``FrameContext`` — collector for the current frame. Reused per frame:
  ``reset()`` clears the list in place, ``record()`` appends one small
  frozen dataclass. No timers, no threads.
- ``snapshot_last_frame`` / ``last_frame_snapshot`` — the single allowed
  module global: an immutable tuple copy of the last completed frame for
  tests. Nothing else is global.

Pilot writers (additive only — existing logs are never removed):
``render_gate.py`` mag-gate and ``rhi_renderer/use_cases/fallback.py``
record into the context passed in as ``frame_context`` (``None`` by
default, so all existing call sites are behavior-identical).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "VERDICT_RAN",
    "VERDICT_SKIPPED",
    "FrameDecision",
    "FrameContext",
    "last_frame_snapshot",
    "snapshot_last_frame",
]

VERDICT_RAN = "ran"
VERDICT_SKIPPED = "skipped"

_VERDICTS = (VERDICT_RAN, VERDICT_SKIPPED)


@dataclass(frozen=True, slots=True)
class FrameDecision:
    """One render decision within a frame (brief field ``pass``)."""

    pass_name: str
    verdict: str  # VERDICT_RAN | VERDICT_SKIPPED
    reason: str
    ids: tuple = ()


class FrameContext:
    """Collector for the current frame's decisions. Reused per frame."""

    __slots__ = ("_decisions",)

    def __init__(self) -> None:
        self._decisions: list[FrameDecision] = []

    def record(
        self,
        pass_name: str,
        verdict: str,
        reason: str,
        ids: tuple = (),
    ) -> FrameDecision:
        """Append one decision. Stores ``ids`` by reference (no formatting)."""
        if verdict not in _VERDICTS:
            raise ValueError(f"verdict must be one of {_VERDICTS}, got {verdict!r}")
        decision = FrameDecision(
            pass_name=pass_name,
            verdict=verdict,
            reason=reason,
            ids=tuple(ids) if ids is not None else (),
        )
        self._decisions.append(decision)
        return decision

    def reset(self) -> None:
        """Clear in place for the next frame (keeps the list allocation)."""
        del self._decisions[:]

    def dump(self) -> str:
        """Grep-friendly single line per decision: verdict + reason + ids."""
        return "\n".join(
            f"[framectx] pass={d.pass_name} verdict={d.verdict}"
            f" reason={d.reason} ids={d.ids!r}"
            for d in self._decisions
        )

    def __len__(self) -> int:
        return len(self._decisions)

    def __iter__(self):
        return iter(self._decisions)


# The single allowed global: immutable snapshot of the last frame (tests).
_last_frame_snapshot: tuple[FrameDecision, ...] | None = None


def snapshot_last_frame(ctx: FrameContext) -> None:
    """Freeze the current frame's decisions for tests."""
    global _last_frame_snapshot
    _last_frame_snapshot = tuple(ctx._decisions)


def last_frame_snapshot() -> tuple[FrameDecision, ...] | None:
    """Return the last frozen frame snapshot (None before the first frame)."""
    return _last_frame_snapshot
