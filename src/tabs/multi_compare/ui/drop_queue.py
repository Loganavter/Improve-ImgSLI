"""FIFO dedup queue for multi-compare external drops — collaborator object.

Owns its own lifecycle (queued entries, max 1 inflight per anchor slot,
``QTimer.singleShot(0)`` delivery), so per ``docs/dev/CODE_PATTERNS.md``
("Who owns the state — collaborator object vs use_cases function") it is a
small parameterizable object with its own state, not another batch of
functions over the widget. The owner (``MultiCompareWidget`` state) is
received via method args — :meth:`DropQueue.enqueue` takes the widget per
call, same as the ``ui/drag_drop.py`` functions-taking-owner convention.

Isolation: imports only this tab (``tabs.multi_compare.debug``) plus
stdlib/Qt. No Store (delivery is one ``images_dropped`` emit per entry),
no EventBus, no QSS, no layout. The queue-full summary is an injectable
``overflow_reporter`` hook defaulting (lazily, to stay import-cycle-free)
to ``drag_drop._emit_dnd_overflow_summary``.
"""

from __future__ import annotations

import logging

from tabs.multi_compare.debug import (
    mc_dnd_debug as _dnd_log,
)

logger = logging.getLogger("ImproveImgSLI")


def _normpath_str(p) -> str:
    """Normalized path string for DropQueue dedup keys (IC ``slot.py`` parity).

    ``os.path.normpath`` over ``os.fspath`` heals textual variants of the
    same file (``/x/./f.png`` vs ``/x/f.png``, ``str`` vs ``Path``) without
    ever equating distinct files.
    """
    import os as _os

    try:
        return _os.path.normpath(_os.fspath(p))
    except Exception:
        return str(p)


class DropQueue:
    """FIFO dedup queue for MC external drops — A1 IC mirror.

    Dedup key ``(anchor_slot, normpath)`` (``anchor_slot`` is the pure
    :func:`placement.anchor_slot_for_path` verdict, ``0`` for root/empty).
    Max 1 inflight per anchor slot: the next entry for a busy slot waits
    while entries for free slots flow — same shape as IC's
    ``image_compare.use_cases.drag_drop.DropQueue`` (there the key is the
    1/2 slot number). Delivery is one ``images_dropped`` emit per entry,
    scheduled past the P7 accept via ``QTimer.singleShot(0)``. The
    internal-drag Move echo never enters the queue (untouched branch in
    :func:`tabs.multi_compare.ui.drag_drop.drop_event`).
    """

    #: Cap on total pending paths (queued + inflight). A pathological drop
    #: (or rapid-fire drops) must not pile unbounded worker intake; the
    #: trimmed tail is reported via the queue-full summary, never silent.
    MAX_PENDING_PATHS = 128

    def __init__(self, overflow_reporter=None) -> None:
        """Create the queue.

        ``overflow_reporter`` — optional ``(widget, dropped, *, reason)``
        callable for the queue-full summary (production default:
        ``drag_drop._emit_dnd_overflow_summary`` via lazy import).
        """
        from collections import deque as _dq

        self._queue: _dq[tuple[int, list, object, object]] = _dq()
        self._inflight_slots: set[int] = set()
        self._queued_keys: set[tuple[int, str]] = set()
        self._inflight_keys: set[tuple[int, str]] = set()
        # Hook for the queue-full summary
        # (``drag_drop._emit_dnd_overflow_summary``). Optional so unit tests
        # can inject a fake; None keeps the production wiring via a lazy
        # import — this module must stay importable from ``drag_drop`` at
        # top level, so no top-level ``drag_drop`` import here.
        self._overflow_reporter = overflow_reporter

    def _report_overflow(self, widget, dropped: list, *, reason: str) -> None:
        report = self._overflow_reporter
        if report is None:
            from tabs.multi_compare.ui.drag_drop import (
                _emit_dnd_overflow_summary as report,
            )
        report(widget, dropped, reason=reason)

    def _pending_path_count(self) -> int:
        try:
            queued = sum(len(paths) for _, paths, _, _, _ in self._queue)
        except Exception:
            queued = len(self._queue)
        try:
            return queued + len(self._inflight_keys)
        except Exception:
            return queued

    def enqueue(self, anchor_slot: int | None, paths, widget, target, side) -> bool:
        slot = int(anchor_slot) if anchor_slot is not None else 0
        uniq: list = []
        for raw in paths:
            n = _normpath_str(raw)
            key = (slot, n)
            if key in self._queued_keys or key in self._inflight_keys:
                _dnd_log("DropQueue dedup skip slot=%s path=%s", slot, n)
                continue
            uniq.append(raw)
            self._queued_keys.add(key)
        if not uniq:
            _dnd_log("DropQueue enqueue slot=%s -> all deduped, skip", slot)
            return False
        budget = self.MAX_PENDING_PATHS - self._pending_path_count()
        if budget < len(uniq):
            dropped = uniq[max(budget, 0):]
            uniq = uniq[:max(budget, 0)]
            for raw in dropped:
                self._queued_keys.discard((slot, _normpath_str(raw)))
            _dnd_log(
                "DropQueue cap slot=%s: queued %d, dropped %d (max %d)",
                slot, len(uniq), len(dropped), self.MAX_PENDING_PATHS,
            )
            self._report_overflow(widget, dropped, reason="queue_full")
            if not uniq:
                return False
        self._queue.append((slot, uniq, widget, target, side))
        _dnd_log(
            "DropQueue enqueue slot=%s paths=%s queued=%s inflight=%s",
            slot, [str(p) for p in uniq][:3], len(self._queue),
            sorted(self._inflight_slots),
        )
        self._try_process()
        return True

    def _try_process(self) -> None:
        from PySide6.QtCore import QTimer as _QTimer

        entry = None
        for slot, paths, widget, target, side in list(self._queue):
            if slot not in self._inflight_slots:
                entry = (slot, paths, widget, target, side)
                break
        if entry is None:
            return
        slot, paths, widget, target, side = entry
        try:
            self._queue.remove(entry)  # type: ignore[arg-type]
        except Exception:
            from collections import deque as _dq

            new_q = _dq(x for x in self._queue if x is not entry)
            self._queue = new_q
        normed: list[str] = []
        for raw in paths:
            n = _normpath_str(raw)
            normed.append(n)
            self._queued_keys.discard((slot, n))
            self._inflight_keys.add((slot, n))
        self._inflight_slots.add(slot)
        _dnd_log("DropQueue _try_process start slot=%s paths=%s", slot, normed[:3])

        def _do_emit(
            q=self, sl=slot, keys=normed, wid=widget, tgt=target,
            sd=side, ps=list(paths),
        ):
            try:
                wid.images_dropped.emit(list(ps), tgt, sd)
            except Exception:
                logger.exception("[mc-dnd] DropQueue emit failed")
            for _n in keys:
                q._inflight_keys.discard((int(sl), _n))
            q._inflight_slots.discard(int(sl))
            _dnd_log("DropQueue finish slot=%s remaining queued=%s", sl, len(q._queue))
            q._try_process()

        _QTimer.singleShot(0, _do_emit)

    def clear(self) -> None:
        self._queue.clear()
        self._inflight_slots.clear()
        self._queued_keys.clear()
        self._inflight_keys.clear()


_drop_queue = DropQueue()


def get_drop_queue() -> DropQueue:
    return _drop_queue
