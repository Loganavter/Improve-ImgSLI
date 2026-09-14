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
  ``reset()`` clears the list in place and bumps ``frame_id``,
  ``record()`` appends one small frozen dataclass. No timers, no threads.
- ``snapshot_last_frame`` / ``last_frame_snapshot`` — the single allowed
  module global: an immutable tuple copy of the last completed frame for
  tests. Nothing else is global.

Phase-2 frame bus (task-engine-2abcd-2026-09-14, bucket 2C): the phases
that write into the bus are ``prepare_frame`` (early-skip reason),
``realize_*`` (budget/deadline/residency), ``build_array_draw_plan``
(LOD keys + entry count), ``coverage`` (numbers), ``resourceUpdate``/mips
(dirty layers) and ``submit`` (gate + begin/end fact). ``mag_gate`` and
``fallback`` already wrote since P1A; the rest record through the same
``record()`` shape — record calls only, zero draw-behavior change.

``ids`` schema (v1, ``IDS_SCHEMA_VERSION``): element 0 SHOULD be
``frame_tag(frame_id)`` (``"frame=N"``); the remaining elements are small
correlation atoms — texture-key tuples, diff keys, ``viewport_hash()``
strings, ``BudgetStats.as_tuple()`` tuples. Atoms are stored by reference
and never interpreted (``LevelKey`` and other engine objects flow through
today), so ``record()`` does not enforce the schema — ``make_ids()``
builds it. ``BudgetStats`` is the canonical carrier for count/time budget
facts (upload-loop budget, LOD settle window, mips cascade).

Pilot writers (additive only — existing logs are never removed):
``render_gate.py`` mag-gate and ``rhi_renderer/use_cases/fallback.py``
record into the context passed in as ``frame_context`` (``None`` by
default, so all existing call sites are behavior-identical).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

__all__ = [
    "IDS_SCHEMA_VERSION",
    "INVALIDATE_PREFIX",
    "VERDICT_RAN",
    "VERDICT_SKIPPED",
    "BudgetStats",
    "FrameDecision",
    "FrameContext",
    "frame_tag",
    "last_frame_snapshot",
    "make_ids",
    "snapshot_last_frame",
    "viewport_hash",
]

VERDICT_RAN = "ran"
VERDICT_SKIPPED = "skipped"

#: Version of the ``ids`` correlation schema documented above. Bump (and
#: migrate writers via ``make_ids``) when the atom layout changes.
IDS_SCHEMA_VERSION = 1

#: Pass-name prefix for the P4 attributed-invalidation bus: every timer arm,
#: singleShot deferral and external invalidation request records here as
#: ``invalidate.<source>`` (e.g. ``invalidate.schedule.fps_timer``) with the
#: arming reason. Render-decision passes (``mag_gate``, ``fallback``,
#: ``loupe.*``) keep their own names; ``invalidations()`` selects this
#: namespace back out.
INVALIDATE_PREFIX = "invalidate."

_VERDICTS = (VERDICT_RAN, VERDICT_SKIPPED)


@dataclass(frozen=True, slots=True)
class FrameDecision:
    """One render decision within a frame (brief field ``pass``)."""

    pass_name: str
    verdict: str  # VERDICT_RAN | VERDICT_SKIPPED
    reason: str
    ids: tuple = ()


@dataclass(frozen=True, slots=True)
class BudgetStats:
    """Canonical carrier for count/time budget facts on the frame bus.

    ``budget``/``uploaded``/``skipped`` describe a count-bounded loop
    (tile upload batch); ``time_ms``/``budget_ms`` describe a wall-clock
    budget (upload deadline, LOD settle window, mips cascade); the
    ``realize_*``/mips phases fill every field, lighter phases (LOD
    settle) fill only the time side. ``describe()`` renders the
    grep-friendly reason fragment; ``as_tuple()`` renders the
    ``ids``-schema atom.
    """

    budget: int = 0
    uploaded: int = 0
    skipped: int = 0
    time_ms: float = 0.0
    budget_ms: float = 0.0
    more_pending: bool = False

    def describe(self) -> str:
        """Grep-friendly reason fragment for ``record()`` reason strings."""
        return (
            f"budget={self.budget} uploaded={self.uploaded}"
            f" skipped={self.skipped}"
            f" time_ms={self.time_ms:.2f}/{self.budget_ms:.2f}"
            f" more_pending={self.more_pending}"
        )

    def as_tuple(self) -> tuple:
        """``ids``-schema atom for this budget fact."""
        return (
            self.budget,
            self.uploaded,
            self.skipped,
            round(self.time_ms, 3),
            round(self.budget_ms, 3),
            self.more_pending,
        )


def frame_tag(frame_id: int) -> str:
    """Element 0 of every schema-v1 ``ids`` tuple (``"frame=N"``)."""
    return f"frame={int(frame_id)}"


def make_ids(frame_id: int, *parts: object) -> tuple:
    """Build a schema-v1 ``ids`` tuple: frame tag first, then atoms.

    Atoms are stored by reference (never formatted here) — engine objects
    such as ``LevelKey`` flow through untouched, exactly as ``record()``
    has always stored them.
    """
    return (frame_tag(frame_id), *parts)


def viewport_hash(
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
    canvas_size: tuple[float, float] | None = None,
) -> str:
    """Deterministic 12-hex viewport identity for frame-bus correlation.

    Pure function of rounded geometry (4 decimals — below sub-pixel
    jitter, above float noise): same camera + canvas hashes equal, any
    pan/zoom/resize changes the hash. ``None`` sides hash as ``"none"``
    so early-skip records (no viewport yet) still get a stable value.
    """
    def _norm(value: object) -> str:
        if value is None:
            return "none"
        try:
            items = tuple(value)  # type: ignore[arg-type]
        except TypeError:
            items = (value,)
        parts: list[str] = []
        for item in items:
            try:
                parts.append(f"{float(item):.4f}")  # type: ignore[arg-type]
            except (TypeError, ValueError):
                parts.append(str(item))
        return ",".join(parts)

    payload = (
        f"zoom={_norm(viewport_zoom)}"
        f"|offset={_norm(viewport_offset)}"
        f"|canvas={_norm(canvas_size)}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


class FrameContext:
    """Collector for the current frame's decisions. Reused per frame."""

    __slots__ = ("_decisions", "_frame_id")

    def __init__(self) -> None:
        self._decisions: list[FrameDecision] = []
        self._frame_id: int = 0

    @property
    def frame_id(self) -> int:
        """Monotonic frame counter, bumped by every ``reset()``."""
        return self._frame_id

    def record(
        self,
        pass_name: str,
        verdict: str,
        reason: str,
        ids: tuple = (),
    ) -> FrameDecision:
        """Append one decision. Stores ``ids`` by reference (no formatting).

        ``ids`` follows the schema-v1 layout (``make_ids()`` builds it:
        frame tag first, then correlation atoms) but is not enforced
        here — engine objects such as ``LevelKey`` flow through by
        reference exactly as before.
        """
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

    def record_invalidation(
        self,
        source: str,
        reason: str,
        ids: tuple = (),
        verdict: str = VERDICT_RAN,
    ) -> FrameDecision:
        """Append one attributed-invalidation record (P4 bus, additive).

        ``source`` is the arming site (``schedule.fps_timer``,
        ``keepwarm.tick`` …); the stored pass is
        ``f"{INVALIDATE_PREFIX}{source}"`` so ``invalidations()`` can
        select the bus back out. ``verdict`` is ``ran`` for arms/fires and
        ``skipped`` for dedup-acks, stops and idle stand-downs. Same cost
        as ``record()`` — one frozen dataclass; callers gate on
        ``ic_invalidate_debug_enabled()`` (see ``trace_invalidation``) so
        steady production pays nothing.
        """
        return self.record(
            f"{INVALIDATE_PREFIX}{source}", verdict, reason, ids
        )

    def invalidations(self) -> list[FrameDecision]:
        """All bus records in insertion order (``invalidate.*`` passes)."""
        return [d for d in self._decisions if d.pass_name.startswith(INVALIDATE_PREFIX)]

    def reset(self) -> None:
        """Clear in place for the next frame (keeps the list allocation).

        Also bumps ``frame_id``: the renderer calls ``reset()`` once at
        the top of every ``render()`` (including the early-skip path), so
        the counter advances per frame with no renderer rewiring.
        """
        del self._decisions[:]
        self._frame_id += 1

    def begin_frame(self) -> int:
        """Explicit ``reset()`` + the new frame's id (future callers)."""
        self.reset()
        return self._frame_id

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
