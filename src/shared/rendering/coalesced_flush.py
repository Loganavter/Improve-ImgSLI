"""Collapses N triggers within one Qt event-loop tick into a single flush.

A store's ``on_change``/subscribe callback fires on every dispatched action;
instead of rebuilding derived render state synchronously per notification, a
canvas can set a dirty flag and schedule one deferred flush via
``QTimer.singleShot(0, ...)``. This generalizes that pattern for any noisy
producer -- a redux-style store's subscribe callback, in particular -- so it
lives here at the shared rendering level rather than duplicated per tab.

Mirrors GIMP's tool-event/idle-repaint split: cheap state updates happen
inline on every event, the expensive rebuild happens at most once per event
loop tick regardless of how many events arrived in between.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QTimer

__all__ = ["CoalescedFlush"]


class CoalescedFlush:
    """Schedules ``flush_fn`` at most once per event-loop tick.

    ``request()`` is safe to call any number of times before the scheduled
    flush runs -- only the first call in a given tick actually arms the
    timer; the rest are no-ops. ``flush_fn`` always sees whatever state is
    current at the time it runs, not a snapshot taken at ``request()`` time,
    so callers should read live state (e.g. ``self.state``) from inside it.
    """

    def __init__(self, flush_fn: Callable[[], None]) -> None:
        self._flush_fn = flush_fn
        self._pending = False

    def request(self) -> None:
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(0, self._run)

    def cancel(self) -> None:
        """Drop a scheduled flush without running it (e.g. on teardown)."""
        self._pending = False

    @property
    def pending(self) -> bool:
        return self._pending

    def _run(self) -> None:
        if not self._pending:
            return
        self._pending = False
        self._flush_fn()
