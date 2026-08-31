"""AbortSignal — generation-based cancellation token for pipeline runs.

Replaces legacy task id monotonic token + store lease capture in
_session_controller / loading. One signal per pipeline run;
every async stage checks is_aborted() or should_abort() closure.
"""

from __future__ import annotations


class AbortSignal:
    """Lightweight cancellation token.

    Usage:
        signal = AbortSignal()
        # pass to pipeline.ensure(signal=signal)
        # to cancel:
        signal.abort()
        # in worker:
        if signal.is_aborted(): return
        # or as callable for should_abort lambdas:
        if signal(): return
    """

    def __init__(self) -> None:
        self._aborted = False
        self._generation = 0

    def abort(self) -> None:
        self._aborted = True
        self._generation += 1

    def is_aborted(self) -> bool:
        return self._aborted

    def generation(self) -> int:
        return self._generation

    def should_abort(self) -> bool:
        return self._aborted

    def __call__(self) -> bool:
        return self._aborted

    def __bool__(self) -> bool:
        return not self._aborted

    def reset(self) -> None:
        self._aborted = False

    @classmethod
    def aborted(cls) -> "AbortSignal":
        s = cls()
        s.abort()
        return s

    @classmethod
    def never(cls) -> "AbortSignal":
        return cls()
