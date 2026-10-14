"""Bounded ring of recent user actions ("breadcrumbs") for the report.

Fed by the dispatcher: every ``Dispatcher.dispatch`` notifies its
subscribers with the ``Action``; we record a compact, timestamped entry.
Bounded (default 50) and lock-guarded because dispatches can occur on the
main thread and (rarely) on worker threads.

Read-only by construction — the buffer never mutates store state.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

DEFAULT_BREADCRUMB_CAPACITY = 50

__all__ = [
    "DEFAULT_BREADCRUMB_CAPACITY",
    "Breadcrumb",
    "BreadcrumbBuffer",
]


@dataclass(frozen=True, slots=True)
class Breadcrumb:
    timestamp: float
    kind: str
    label: str
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "kind": self.kind,
            "label": self.label,
            "detail": self.detail,
        }


class BreadcrumbBuffer:
    """Bounded, thread-safe ring of :class:`Breadcrumb` entries."""

    def __init__(self, capacity: int = DEFAULT_BREADCRUMB_CAPACITY) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._items: deque[Breadcrumb] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._bound_dispatcher: Any | None = None

    @property
    def capacity(self) -> int:
        return int(self._items.maxlen or 0)

    def record(self, kind: str, label: str, detail: str = "") -> Breadcrumb:
        crumb = Breadcrumb(
            timestamp=time.time(),
            kind=str(kind),
            label=str(label),
            detail=str(detail),
        )
        with self._lock:
            self._items.append(crumb)
        return crumb

    def bind_dispatcher(self, dispatcher: Any) -> None:
        """Subscribe to a ``Dispatcher``'s action stream (idempotent)."""
        if dispatcher is None or dispatcher is self._bound_dispatcher:
            return
        subscribe = getattr(dispatcher, "subscribe", None)
        if not callable(subscribe):
            return
        try:
            subscribe(self._on_action)
        except Exception:
            return
        self._bound_dispatcher = dispatcher

    def unbind_dispatcher(self) -> None:
        dispatcher = self._bound_dispatcher
        if dispatcher is None:
            return
        unsubscribe = getattr(dispatcher, "unsubscribe", None)
        if callable(unsubscribe):
            try:
                unsubscribe(self._on_action)
            except Exception:
                pass
        self._bound_dispatcher = None

    def _on_action(self, action: Any) -> None:
        try:
            label = getattr(action, "type", None) or type(action).__name__
            self.record("action", str(label))
        except Exception:
            # Breadcrumbs must never break the thing they observe.
            pass

    def snapshot(self) -> list[Breadcrumb]:
        with self._lock:
            return list(self._items)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [crumb.as_dict() for crumb in self.snapshot()]

    def iter_labels(self) -> Iterable[str]:
        for crumb in self.snapshot():
            yield crumb.label

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
