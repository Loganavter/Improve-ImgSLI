"""Bounded in-memory log ring for the diagnostics report.

The disk log file is opened ``mode="w"`` on every start and only holds what
was flushed — a crash can lose the tail. This handler keeps the last N
formatted records in memory, independent of the file handler, so the report
always carries the recent log tail.

Thread-safety: ``logging.Handler.handle`` already serialises ``emit``
calls, but ``snapshot`` may be called from the report thread while another
thread logs, so the deque is guarded by its own lock.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Iterable

DEFAULT_LOGRING_CAPACITY = 300

# Mirrors the app's own formatter so the report tail is recognisable.
LOGRING_FORMAT = "%(asctime)s - [%(levelname)s] - (%(filename)s:%(lineno)d) - %(message)s"

__all__ = [
    "DEFAULT_LOGRING_CAPACITY",
    "LOGRING_FORMAT",
    "RingBuffer",
    "RingBufferHandler",
]


class RingBuffer:
    """A lock-guarded bounded deque."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._items: deque = deque(maxlen=capacity)
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return int(self._items.maxlen or 0)

    def append(self, item) -> None:
        with self._lock:
            self._items.append(item)

    def extend(self, items: Iterable) -> None:
        with self._lock:
            for item in items:
                self._items.append(item)

    def snapshot(self) -> list:
        with self._lock:
            return list(self._items)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class RingBufferHandler(logging.Handler):
    """A ``logging.Handler`` that only keeps the last ``capacity`` records."""

    def __init__(self, capacity: int = DEFAULT_LOGRING_CAPACITY, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        self._buffer = RingBuffer(capacity)
        self.setFormatter(logging.Formatter(LOGRING_FORMAT))

    @property
    def capacity(self) -> int:
        return self._buffer.capacity

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102 (logging API)
        try:
            line = self.format(record)
        except Exception:
            # Fail-open for the *ring*: never let a bad formatter break logging.
            try:
                line = str(record.getMessage())
            except Exception:
                return
        self._buffer.append(line)

    def snapshot(self) -> list[str]:
        """Formatted log lines, oldest first."""
        return self._buffer.snapshot()
