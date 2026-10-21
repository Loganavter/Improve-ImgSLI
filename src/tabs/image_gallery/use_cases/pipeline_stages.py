"""Declared stage readiness for the gallery pipeline (pure, no Qt).

S2 of plan-gallery-jev-pipeline: a tiny ledger that answers ONE question —
"must this stage run now for this folder generation and this input
fingerprint?" — as a data declaration plus a single-flight gate. It is
deliberately NOT a framework: no scheduling, no Qt, no controller wiring
(the controller calls ``begin``/``finished`` from its schedule sites, J1).

Semantic contract (``scope`` = folder generation int, ``fingerprint`` = a
content key string):

- ``begin(stage, scope, fingerprint)`` → ``True`` means "run now"; ``False``
  means "skip" because either ``(stage, scope, fingerprint)`` already
  completed OR a run for ``(stage, scope)`` is in flight (single-flight).
- A refusal **because a run is in flight** KEEPS the refused fingerprint
  (coalesced to the newest one). A run that started from an older content key
  must not swallow the newer trigger: live 2026-10-21 the last VLM score
  arrived while a rank was in flight, its trigger was dropped, and the order
  applied last was built from the earlier vector (the refused fingerprint had
  nowhere to go — plan-gallery-ai-judgement J1).
- ``finished(stage, scope, *, ok=True)`` → clears the in-flight marker and
  RETURNS the fingerprint refused during that run when it differs from the one
  just completed (and is not already completed) — the caller re-runs exactly
  once for it. ``None`` means "nothing to re-run, or nothing new". Existing
  callers may ignore the value (single-flight stays the only gate; the retry
  is a returned fact, not a second gate). On success (``ok``) the finished
  fingerprint is recorded as completed; a handled failure passes ``ok=False``
  so the same fingerprint can be retried.
- ``invalidate(scope=None)`` → drops completed + in-flight + pending for one
  scope (or all) when the folder/series world changes.
- ``reset()`` → full clear (tests).

``rank_completeness`` is the ONE place that decides "complete vs partial" for
a rank vector (plan-gallery-ai-judgement P1/M2): a rank may only be applied
from a vector that scores every member of the series.

INTERFACE: ``register_stage``, ``stage_requires``, ``StageGate``, ``begin``,
``finished``, ``invalidate``, ``reset``, ``rank_completeness``.
"""

from __future__ import annotations

import threading

#: Stage name -> declared input names. A guarded data declaration only;
#: the gate never reads it (readiness ordering is the caller's job).
_STAGES: dict[str, tuple[str, ...]] = {}


def register_stage(name: str, requires=()) -> None:
    """Declare stage *name* with its input dependencies (data only)."""
    try:
        _STAGES[str(name)] = tuple(str(r) for r in (requires or ()))
    except Exception:
        _STAGES[str(name)] = ()


def stage_requires(name: str) -> tuple[str, ...]:
    """Declared inputs for *name* (empty tuple when unregistered)."""
    try:
        return _STAGES.get(str(name), ())
    except Exception:
        return ()


def rank_completeness(members, vector) -> tuple[int, int, str]:
    """``(scored, total, reason)`` for one series' measured vector.

    The ONE decision point for "complete vs partial" (plan-gallery-ai-judgement
    P1/M2): ``scored == total`` means every member carries at least one
    applicable measured score in *vector*, so a rank built from that vector
    speaks about the whole series. Otherwise ``reason`` names the loss (an
    empty string means complete) and the caller must refuse the rank — an order
    built from a vector whose member has no scores ranks that member on nothing
    (live 2026-10-21: ``img_6`` received a rank while its last score arrived
    during the rank).

    Counts come from the vector, never from the items: the vector IS the
    payload the rank is built from, so an alias with an empty ``scores``
    mapping was never scored. A vector with fewer entries than *members* is
    partial as well (a member with no entry at all). Never raises.
    """
    try:
        total = len(list(members or ()))
    except Exception:
        total = 0
    if total <= 0:
        return 0, 0, ""
    entries: list = []
    try:
        entries = list((vector or {}).get("items", ()) or ())
    except Exception:
        entries = []
    scored = 0
    for entry in entries:
        try:
            if entry.get("scores"):
                scored += 1
        except Exception:
            continue
    if scored >= total and len(entries) >= total:
        return scored, total, ""
    if len(entries) != total:
        reason = f"{len(entries)} of {total} members are in the vector"
    else:
        reason = f"{scored} of {total} members carry a measured score"
    return scored, total, reason


class StageGate:
    """Single-flight + completed ledger keyed by ``(stage, scope[, fingerprint])``.

    One ``begin``/``finished`` pair per run: ``begin`` claims the scope (or
    reports skip), ``finished`` releases it, records the completed fingerprint
    on success and hands back the fingerprint that was refused meanwhile.
    Thread-safe (one lock over the ledger); no Qt.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._completed: set[tuple] = set()
        self._inflight: dict[tuple, str] = {}
        #: Run -> newest fingerprint refused while it was in flight (J1).
        self._pending: dict[tuple, str] = {}

    def begin(self, stage, scope, fingerprint) -> bool:
        """True = run now; False = already completed or in flight."""
        run = (stage, scope)
        key = (stage, scope, fingerprint)
        with self._lock:
            if key in self._completed:
                return False
            if run in self._inflight:
                # Keep the newer content key: it is the state the caller wants
                # ranked once this run releases the scope (coalesce to newest).
                self._pending[run] = fingerprint
                return False
            self._inflight[run] = fingerprint
            return True

    def finished(self, stage, scope, *, ok: bool = True) -> str | None:
        """Clear the in-flight marker; return a fingerprint to re-run, if any.

        The return value is the fingerprint refused during the run when it
        differs from the one just completed and was not already completed —
        exactly one retry for it. ``None`` = nothing new (a second identical
        trigger, a clean run, or a run with no refusal), so a caller that
        ignores the value cannot loop.
        """
        run = (stage, scope)
        with self._lock:
            fingerprint = self._inflight.pop(run, None)
            if ok and fingerprint is not None:
                self._completed.add((stage, scope, fingerprint))
            pending = self._pending.pop(run, None)
            if pending is None or pending == fingerprint:
                return None
            if (stage, scope, pending) in self._completed:
                return None
            return pending

    def invalidate(self, scope=None) -> None:
        """Drop completed + in-flight + pending for *scope* (or all when None)."""
        with self._lock:
            if scope is None:
                self._completed.clear()
                self._inflight.clear()
                self._pending.clear()
                return
            self._completed = {k for k in self._completed if k[1] != scope}
            self._inflight = {k: v for k, v in self._inflight.items() if k[1] != scope}
            self._pending = {k: v for k, v in self._pending.items() if k[1] != scope}

    def reset(self) -> None:
        """Full clear (tests / fresh world)."""
        with self._lock:
            self._completed.clear()
            self._inflight.clear()
            self._pending.clear()


#: Module default gate shared by the thin wrappers below.
_DEFAULT_GATE = StageGate()


def begin(stage, scope, fingerprint) -> bool:
    """``StageGate.begin`` on the module default gate."""
    return _DEFAULT_GATE.begin(stage, scope, fingerprint)


def finished(stage, scope, *, ok: bool = True) -> str | None:
    """``StageGate.finished`` on the module default gate (returns the retry)."""
    return _DEFAULT_GATE.finished(stage, scope, ok=ok)


def invalidate(scope=None) -> None:
    """``StageGate.invalidate`` on the module default gate."""
    _DEFAULT_GATE.invalidate(scope)


def reset() -> None:
    """``StageGate.reset`` on the module default gate."""
    _DEFAULT_GATE.reset()
