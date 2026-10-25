"""The bounded in-process log ring behind the control channel's ``read_log``.

``log.txt`` is truncated by ``setup_logging`` on every start, so it cannot answer
"what happened in the *running* process". ``LogRing`` keeps the newest records in
memory instead; the control server attaches it to the app logger on start and
detaches it on stop.

Split out of ``core/control/server.py`` (docs/dev/FILE_SIZE_POLICY.md): a pure
``logging.Handler`` with no transport, no Qt, no state beyond its deque.
"""

from __future__ import annotations

import logging
from collections import deque

#: Bounded size of the live log ring (records kept for ``read_log``).
LOG_RING_CAPACITY = 2000


class LogRing(logging.Handler):
    """Bounded in-process capture of the app logger.

    ``log.txt`` is truncated by ``setup_logging`` on every start, so it cannot
    answer "what happened in the *running* process". This handler keeps the
    newest records in memory instead; the server attaches it to the app logger
    (``core.log_names.APP_LOGGER_NAME``) on start and detaches on stop.
    """

    def __init__(self, capacity: int = LOG_RING_CAPACITY) -> None:
        super().__init__(level=logging.DEBUG)
        self._entries: deque[tuple[str, str]] = deque(maxlen=capacity)
        self.setFormatter(
            logging.Formatter("%(asctime)s - [%(levelname)s] - %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._entries.append((record.levelname, self.format(record)))
        except Exception:  # never let logging kill the app
            pass

    def entries(self) -> list[tuple[str, str]]:
        return list(self._entries)
