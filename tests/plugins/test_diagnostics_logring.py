"""The in-memory log ring keeps exactly the last N records, in order."""

from __future__ import annotations

import logging

from plugins.diagnostics.logring import RingBuffer, RingBufferHandler


def test_ring_buffer_keeps_last_n_in_order() -> None:
    buf = RingBuffer(capacity=5)
    for i in range(12):
        buf.append(f"item-{i:02d}")
    assert buf.snapshot() == ["item-07", "item-08", "item-09", "item-10", "item-11"]
    assert len(buf) == 5
    assert buf.capacity == 5


def test_ring_buffer_handler_keeps_exactly_last_n() -> None:
    handler = RingBufferHandler(capacity=5)
    logger = logging.getLogger("diagnostics-test-ring")
    saved_handlers = logger.handlers
    saved_level = logger.level
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        for i in range(12):
            logger.info("ring-line-%02d", i)
    finally:
        logger.handlers = saved_handlers
        logger.setLevel(saved_level)

    snapshot = handler.snapshot()
    assert handler.capacity == 5
    assert len(snapshot) == 5
    for index, expected in enumerate(range(7, 12)):
        assert f"ring-line-{expected:02d}" in snapshot[index]


def test_ring_buffer_handler_is_independent_of_file_handler() -> None:
    """A ring snapshot survives even if other handlers are never flushed."""
    handler = RingBufferHandler(capacity=3)
    record = logging.LogRecord(
        name="x", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="boom-%s", args=("tail",), exc_info=None,
    )
    handler.emit(record)
    assert any("boom-tail" in line for line in handler.snapshot())
