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
- ``finished(stage, scope, *, ok=True)`` → clears the in-flight marker. On
  success (``ok``) it also records the fingerprint as completed; a handled
  failure passes ``ok=False`` so the same fingerprint can be retried.
- ``invalidate(scope=None)`` → drops completed + in-flight for one scope (or
  all) when the folder/series world changes.
- ``reset()`` → full clear (tests).

INTERFACE: ``register_stage``, ``stage_requires``, ``StageGate``, ``begin``,
``finished``, ``invalidate``, ``reset``.
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


class StageGate:
    """Single-flight + completed ledger keyed by ``(stage, scope[, fingerprint])``.

    One ``begin``/``finished`` pair per run: ``begin`` claims the scope (or
    reports skip), ``finished`` releases it and, on success, records the
    fingerprint as done. Thread-safe (one lock over the ledger); no Qt.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._completed: set[tuple] = set()
        self._inflight: dict[tuple, object] = {}

    def begin(self, stage, scope, fingerprint) -> bool:
        """True = run now; False = already completed or in flight."""
        run = (stage, scope)
        key = (stage, scope, fingerprint)
        with self._lock:
            if key in self._completed or run in self._inflight:
                return False
            self._inflight[run] = fingerprint
            return True

    def finished(self, stage, scope, *, ok: bool = True) -> None:
        """Clear the in-flight marker; on success record the fingerprint done."""
        run = (stage, scope)
        with self._lock:
            fingerprint = self._inflight.pop(run, None)
            if ok and fingerprint is not None:
                self._completed.add((stage, scope, fingerprint))

    def invalidate(self, scope=None) -> None:
        """Drop completed + in-flight for *scope* (or all when None)."""
        with self._lock:
            if scope is None:
                self._completed.clear()
                self._inflight.clear()
                return
            self._completed = {k for k in self._completed if k[1] != scope}
            self._inflight = {k: v for k, v in self._inflight.items() if k[1] != scope}

    def reset(self) -> None:
        """Full clear (tests / fresh world)."""
        with self._lock:
            self._completed.clear()
            self._inflight.clear()


#: Module default gate shared by the thin wrappers below.
_DEFAULT_GATE = StageGate()


def begin(stage, scope, fingerprint) -> bool:
    """``StageGate.begin`` on the module default gate."""
    return _DEFAULT_GATE.begin(stage, scope, fingerprint)


def finished(stage, scope, *, ok: bool = True) -> None:
    """``StageGate.finished`` on the module default gate."""
    _DEFAULT_GATE.finished(stage, scope, ok=ok)


def invalidate(scope=None) -> None:
    """``StageGate.invalidate`` on the module default gate."""
    _DEFAULT_GATE.invalidate(scope)


def reset() -> None:
    """``StageGate.reset`` on the module default gate."""
    _DEFAULT_GATE.reset()
