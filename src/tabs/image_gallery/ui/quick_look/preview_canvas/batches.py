"""Quick Look preview canvas -- QRhi resource-update-batch ownership.

Pinned invariant
(``src/tabs/image_gallery/tests/runtime/test_ql_rhi_batch_ownership.py``):
every batch handed out by ``rhi.nextResourceUpdateBatch()`` is consumed
exactly once on every path out of ``rhi_entry.render`` -- either handed to
``command_buffer.beginPass(target, clear, depth_clear, batch)`` or returned
to QRhi's shared resource-update pool via
``command_buffer.resourceUpdate(batch)`` (the tree-wide idiom; see
``engine.gpu.tiled_image_view.render``).

A batch abandoned on an early return is never recycled by QRhi: after 64
frames the pool is exhausted and Qt's own widget-compositing flush later
replays a pooled batch whose recorded uploads reference resources destroyed
in the meantime (SIGSEGV in
``QWidgetRepaintManager::flush -> rhiFlush``). Hence every early return
drains, and a batch the engine view submits internally is recorded as a
transfer instead of a second drain.

Split out of ``preview_canvas/rhi_entry.py`` (task
task-gallery-ql-preview-batch-module-2026-10-17): the invariant owns its
counter here; frame sequencing stays in ``rhi_entry``. Plain functions take
the canvas widget as their first argument (``CODE_PATTERNS.md`` -- thin
owner + module functions). Never raises.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QRhiDepthStencilClearValue

logger = logging.getLogger("ImproveImgSLI")

# Outstanding batches (taken minus consumed) is an int on the widget itself so
# the count survives the module boundary (diagnostics read it from the widget).
_COUNTER_ATTR = "_ql_rhi_batches_outstanding"


def _note(self, delta: int) -> int:
    """Advance the outstanding-batch counter (taken minus consumed).

    Diagnostic-only: the counter is a plain int on the widget
    (``_ql_rhi_batches_outstanding``) and the line is emitted through
    ``ql_cover`` only under the existing ``IMGSLI_QL_COVER_DEBUG`` gate
    (DEBUGGING.md rule 5 -- own flag, silent by default), so this is
    fail-open and effectively free when the gate is off. Never raises.
    """
    try:
        outstanding = int(getattr(self, _COUNTER_ATTR, 0) or 0) + int(delta)
    except Exception:
        return 0
    try:
        setattr(self, _COUNTER_ATTR, outstanding)
    except Exception:
        pass
    try:
        from tabs.image_gallery.debug import ql_cover, ql_cover_enabled

        if ql_cover_enabled():
            ql_cover(
                "QuickLook preview: rhi batches outstanding=%s (delta=%+d)",
                outstanding,
                int(delta),
            )
    except Exception:
        pass
    return outstanding


def take(self, rhi) -> tuple[object | None, bool]:
    """Take this frame's batch and count it outstanding (+1).

    Returns ``(batch, ok)``. ``ok`` is False only when the rhi refused the
    take (it raised): no batch was handed out, so the caller's frame skip
    owes nothing. A genuine ``None`` batch is ``(None, True)`` -- the caller
    keeps its existing path and simply stages nothing.
    """
    try:
        batch = rhi.nextResourceUpdateBatch()
    except Exception:
        return None, False
    if batch is not None:
        _note(self, 1)
    return batch, True


def drain(self, command_buffer, batch) -> None:
    """Consume a taken-but-unused batch via ``command_buffer.resourceUpdate``.

    The tree-wide idiom for a batch that no draw steals (see
    ``engine.gpu.tiled_image_view.render``): submitting it returns the
    batch to QRhi's shared resource-update pool. Skipping this on an early
    ``return`` abandons the batch -- it is never recycled, the pool is
    exhausted after 64 frames and Qt's own widget-compositing flush later
    replays a stale batch whose recorded uploads reference resources
    destroyed in the meantime (SIGSEGV photographed in
    ``QWidgetRepaintManager::flush -> rhiFlush``). Never raises.
    """
    if batch is None:
        return
    try:
        command_buffer.resourceUpdate(batch)
    except Exception:
        pass
    _note(self, -1)


def begin_pass(self, command_buffer, target, clear, batch) -> bool:
    """Hand the batch to ``beginPass`` (submitted, not abandoned).

    On success the batch is consumed (-1) and ``beginPass`` owns it; on
    failure the caller still owns it and must ``drain`` it. Never raises.
    """
    try:
        command_buffer.beginPass(
            target,
            clear,
            QRhiDepthStencilClearValue(1.0, 0),
            batch,
        )
    except Exception:
        return False
    _note(self, -1)
    return True


def transfer(self, batch) -> None:
    """Record a batch handed to another owner (the engine view submits it).

    Used instead of ``drain`` when a callee (``tiled_image_view.render``)
    consumes the batch internally: draining it again would double-consume.
    Never raises.
    """
    if batch is None:
        return
    _note(self, -1)
