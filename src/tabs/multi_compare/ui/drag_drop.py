"""Drag & drop / pending-placement orchestration for ``MultiCompareWidget``.

Audit-Meta: pattern=thin-owner-target size=927 reason="widget-owned DnD use_cases (functions-taking-owner; Qt event names delegated by widget); queue lifecycle in ui/drop_queue.py collaborator"

Split out of ``widget.py`` to keep that class down to composition/wiring --
mirrors the ``use_cases`` split applied to ``MultiCompareController``. Every
function here takes the widget as its first argument and reads/writes its
instance state (``_pending_duplicate_source``, ``_pending_paste_paths``)
directly, same calling convention as the controller's use_cases modules. The
``DropQueue`` queue lifecycle lives in ``drop_queue.py`` (collaborator object
with its own queue/inflight state, owner passed via method args) and is
re-exported here for backward compatibility.

Qt calls ``dragEnterEvent``/``dragMoveEvent``/``dragLeaveEvent``/``dropEvent``/
``eventFilter`` by name on the widget itself, so those stay defined as thin
methods on ``MultiCompareWidget`` that delegate into this module.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent

from shared.image_extensions import (
    has_image_urls,
    is_accepted_image_path,
    is_loadable_image_path,
)
from tabs.multi_compare.debug import (
    mc_dnd_debug as _dnd_log,
    mc_dnd_diag_light_move_enabled,
)
from tabs.multi_compare.scene import actions
from tabs.multi_compare.ui import chrome
from tabs.multi_compare.ui.canvas_widget import INTERNAL_SLOT_MIME
from tabs._shared.overflow_summary import summarize_overflow
from tabs.multi_compare.ui.drop_queue import DropQueue, get_drop_queue
from tabs.multi_compare.use_cases import placement as _placement
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


# Re-exported for backward compatibility: tests and callers import
# ``DropQueue``/``get_drop_queue`` from this module; the lifecycle itself
# lives in ``tabs.multi_compare.ui.drop_queue`` (collaborator object with
# its own queue/inflight state, owner passed via method args).
__all__ = [  # noqa: F822 — re-exported names are used by external importers
    "DropQueue",
    "get_drop_queue",
]


def _emit_dnd_overflow_summary(widget, overflow, *, reason: str = "queue_full") -> None:
    """One summary per gesture for capped/dropped DnD intake (no dialog flood).

    Single channel: the controller's ``report_user_error`` (bus dialog by
    house policy, loud-log fallback inside). No controller (headless
    fakes) → loud log here, never silent, never raising.
    """
    if not overflow:
        return
    try:
        ctrl = getattr(widget, "_controller", None)
    except Exception:
        ctrl = None
    report = getattr(ctrl, "report_user_error", None)
    if not callable(report):
        logger.warning(
            "mc dnd %s overflow: %d file(s) not queued", reason, len(overflow)
        )
        return
    try:
        count = len(overflow)
        names = summarize_overflow(overflow, limit=5, extra=True)
        message = (
            f"Drop queue is full ({DropQueue.MAX_PENDING_PATHS} pending max): "
            f"{count} file{'s' if count != 1 else ''} not queued — {names}"
        )
        report(message)
    except Exception:
        logger.exception(
            "mc dnd %s overflow summary failed for %d file(s)", reason, len(overflow)
        )


def _mime_url_count(mime) -> int:
    try:
        return len(mime.urls())
    except Exception:
        return -1


def _schedule_placeholder_recheck(widget) -> None:
    """Re-evaluate the placeholder cover shortly after drag-enter.

    The dismiss check in ``apply_drag_preview`` runs synchronously, i.e. one
    frame behind: at drag-enter presents is still 0 even though the just
    dispatched ``update()`` is about to present frame #1. Moves re-check
    every tick, but a user who enters and holds still would never re-check,
    so retry once after the frame has had time to land. No-op if the drag
    already ended (or the widget is gone).
    """
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(150, lambda: _placeholder_recheck_tick(widget))
    except Exception:
        pass


def _placeholder_recheck_tick(widget) -> None:
    try:
        if not bool(getattr(getattr(widget, "state", None), "drag_active", False)):
            return
        chrome.dismiss_placeholder_for_dnd(widget)
    except Exception:
        pass


def _canvas_gate_snapshot(widget) -> str:
    """One-line first-frame-gate status for preview logs.

    Tells whether overlay pixels can actually reach the screen yet:
    presents vs the 10-frame gate, firstFrameRendered emitted or not,
    startup placeholder still covering or not. All reads are defensive
    (fakes in tests may lack any of these).
    """
    canvas = getattr(widget, "canvas", None)
    presents = getattr(canvas, "_rhi_presents_completed", "?")
    first_frame = getattr(canvas, "_first_frame_emitted", "?")
    ph = getattr(widget, "_startup_placeholder", None)
    try:
        ph_state = (
            "visible" if ph.isVisible()
            else "dismissed" if getattr(ph, "_dismissed", False)
            else "hidden"
        )
    except Exception:
        ph_state = "?" if ph is not None else "none"
    return f"presents={presents} first_frame={first_frame} placeholder={ph_state}"


def internal_source_slot_id(mime) -> int | None:
    if not mime.hasFormat(INTERNAL_SLOT_MIME):
        return None
    try:
        return int(bytes(mime.data(INTERNAL_SLOT_MIME)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def owned_internal_source_slot_id(widget, mime) -> int | None:
    """Slot id from *mime* when that slot lives in THIS widget's state.

    Slot ids are per-session, so a drag started in another Multi Compare tab
    (reachable by holding the cursor over that tab's strip button — the strip
    dwell-switches sessions mid-drag) must never drive this tab's internal
    reorder: the id would resolve to an unrelated slot here, or to nothing.
    Foreign payloads fall through to the external path (``setUrls`` is on the
    same mime since slots carry ``WORKSPACE_TAB_PATHS_MIME``), i.e. the image
    is added where it was dropped — gallery-drag parity.
    """
    sid = internal_source_slot_id(mime)
    if sid is None:
        return None
    try:
        return sid if any(slot.id == sid for slot in widget.state.slots) else None
    except Exception:
        return None


def grid_local_pos(widget, pos):
    return widget.canvas.mapFrom(widget, pos)


def resolve_drop_target(widget, pos, *, internal: bool):
    local = grid_local_pos(widget, pos)
    if internal:
        return widget.canvas.compute_drop_target(local, include_center=True)
    return widget.canvas.compute_drop_target(local)


def apply_drag_preview(
    widget, event, internal: bool, source_id: int | None = None
) -> None:
    t0 = time.monotonic()
    pos = event.position().toPoint()
    _apply_preview_at(
        widget, pos, internal=internal, source_id=source_id, t0=t0
    )


def _apply_preview_at(
    widget, pos, *, internal: bool, source_id: int | None, t0: float
) -> None:
    """Preview core working on resolved values (no Qt event touched).

    Split out so dragEnter can defer past ``accept()``: capturing the event
    itself for a later tick would be use-after-free, plain values are safe.
    """
    tgt_path, side, root_tgt, swap_id = resolve_drop_target(
        widget, pos, internal=internal
    )
    # dragMove fires per mouse tick — log only when the resolved target
    # changes, otherwise one gesture floods the log with identical lines.
    sig = (internal, source_id, tgt_path, side, root_tgt, swap_id)
    if sig != getattr(widget, "_dnd_preview_sig", None):
        widget._dnd_preview_sig = sig
        _dnd_log(
            "preview internal=%s pos=%s source=%s target_path=%s side=%s root=%s swap=%s %s",
            internal, pos, source_id, tgt_path, side, root_tgt, swap_id,
            _canvas_gate_snapshot(widget),
        )
    # Runs per dragMove, not just on target change: the check is synchronous
    # (one frame behind the dispatched update), so the first evaluation above
    # always sees presents==0 on a fresh canvas. Its own logging is deduped
    # inside the helper.
    chrome.dismiss_placeholder_for_dnd(widget)  # logs the decision itself
    # No state change → no dispatch (STORE.md invariant 2 covers *changes*).
    # Per-tick dispatches of an identical SetDragState each pay the full
    # core-Dispatcher pipeline (lock, RootReducer, slot write, emit) plus a
    # composition rebuild and a full re-render downstream — at 60Hz mouse
    # ticks that starves the event loop and freezes the DnD cursor feedback.
    # Same-target moves degrade to IC semantics: accept (by the caller), no
    # work. The reducer's own SetDragState equality guard is the backstop
    # for the other dispatch sites (pending preview).
    dispatched = False
    if _drag_preview_changed(
        widget,
        internal=internal,
        source_id=source_id,
        tgt_path=tgt_path,
        side=side,
        root_tgt=root_tgt,
        swap_id=swap_id,
    ):
        widget.store.dispatch(
            actions.set_drag_state(
                active=True,
                internal=internal,
                source_slot_id=source_id,
                target_path=tgt_path,
                target_side=side,
                target_root=root_tgt,
                target_swap_slot_id=swap_id,
            )
        )
        dispatched = True
    _timing_add(widget, (time.monotonic() - t0) * 1000.0, dispatched)


def _drag_preview_changed(
    widget,
    *,
    internal: bool,
    source_id: int | None,
    tgt_path: tuple[int, ...] | None,
    side: str | None,
    root_tgt: bool,
    swap_id: int | None,
) -> bool:
    """True when the resolved preview differs from current drag state.

    Compared against live state (not the last-dispatched payload) so a
    mid-gesture external change (drop/leave/cancel) can never desync the
    gate. Fail-open (True) when state is unreadable — preserves the old
    always-dispatch behavior rather than dropping a real update.
    """
    try:
        st = widget.state
        return (
            st.drag_active is not True
            or st.drag_internal != internal
            or st.drag_source_slot_id != source_id
            or st.drag_target_path != tgt_path
            or st.drag_target_side != side
            or st.drag_target_root != root_tgt
            or st.drag_target_swap_slot_id != swap_id
        )
    except Exception:
        return True


def _timing_reset(widget) -> None:
    """Start per-gesture cost accounting (moves/handler-ms on the widget,
    frames/raster-ms on the canvas — see passes.py). Summary is emitted on
    leave/drop; all reads are defensive for test fakes."""
    widget._dnd_timing = {
        "t0": time.monotonic(),
        "moves": 0,
        "handler_ms": 0.0,
        "dispatched": 0,
    }
    canvas = getattr(widget, "canvas", None)
    if canvas is not None:
        canvas._dnd_frame_stats = {"frames": 0, "raster_ms": 0.0}


def _timing_add(widget, handler_ms: float, dispatched: bool) -> None:
    acc = getattr(widget, "_dnd_timing", None)
    if acc is None:
        return
    acc["moves"] += 1
    acc["handler_ms"] += handler_ms
    if dispatched:
        acc["dispatched"] += 1


def _timing_emit(widget, why: str) -> None:
    acc = getattr(widget, "_dnd_timing", None)
    if acc is None:
        return
    widget._dnd_timing = None
    canvas = getattr(widget, "canvas", None)
    facc = getattr(canvas, "_dnd_frame_stats", None)
    dur_ms = (time.monotonic() - acc["t0"]) * 1000.0
    moves, handler_ms = acc["moves"], acc["handler_ms"]
    dispatched = acc.get("dispatched", "?")
    skipped = moves - dispatched if isinstance(dispatched, int) else "?"
    if isinstance(facc, dict):
        frames, raster_ms = facc["frames"], facc["raster_ms"]
        facc["frames"] = 0
        facc["raster_ms"] = 0.0
    else:
        frames, raster_ms = "?", "?"
    avg_handler = handler_ms / moves if moves else 0.0
    if isinstance(frames, int) and frames:
        avg_raster = raster_ms / frames
        raster_part = f"raster_total={raster_ms:.1f}ms raster_avg={avg_raster:.2f}ms"
    else:
        raster_part = f"raster_total={raster_ms}ms"
    _dnd_log(
        "gesture %s: moves=%d dispatched=%s skipped=%s duration=%.0fms "
        "handler_total=%.1fms handler_avg=%.2fms frames=%s %s",
        why, moves, dispatched, skipped, dur_ms, handler_ms, avg_handler,
        frames, raster_part,
    )


def _safe_preview(
    widget, event, *, internal: bool, source_id: int | None = None
) -> None:
    """Run ``apply_drag_preview`` without ever swallowing ``accept()``.

    Mirrors image_compare's ``_safe_update_drag_overlays``: the accept
    verdict is already sent (see callers), so a preview failure must degrade
    to a missing highlight, never to a missing Status answer (which the
    drag source reads as "wait").
    """
    try:
        apply_drag_preview(widget, event, internal=internal, source_id=source_id)
    except Exception:
        logger.exception("[mc-dnd] apply_drag_preview failed")


def drag_enter_event(widget, event: QDragEnterEvent) -> None:
    cancel_pending_placements(widget)
    widget._dnd_preview_sig = None  # new gesture — log its first preview
    widget._dnd_ph_sig = None  # ...and its placeholder decision
    _timing_reset(widget)
    widget._dnd_light_logged = False
    widget._dnd_gen = getattr(widget, "_dnd_gen", 0) + 1
    mime = event.mimeData()
    source_id = owned_internal_source_slot_id(widget, mime)
    if source_id is not None:
        _dnd_log("dragEnter internal source=%s", source_id)
        # Echo: internal drags propose MoveAction (interaction.py) and the
        # answered action must stay Move. Accept FIRST, then defer the
        # preview work past it: Status must not wait on resolve/dispatch.
        event.acceptProposedAction()
        _defer_enter_preview(widget, event, internal=True, source_id=source_id)
        _schedule_placeholder_recheck(widget)
        return
    if has_image_urls(mime):
        _dnd_log("dragEnter external urls=%s", _mime_url_count(mime))
        # Force Copy like image_compare's window handler: echoing the
        # compositor's early proposal (Move/unset on the first motions)
        # makes the source show move/forbidden cursors until negotiation
        # converges. Accept FIRST, preview work deferred past it.
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        _defer_enter_preview(widget, event, internal=False)
        _schedule_placeholder_recheck(widget)
        return
    _dnd_log("dragEnter ignored (no slot mime, no image urls)")
    event.ignore()


def _defer_enter_preview(
    widget, event, *, internal: bool, source_id: int | None = None
) -> None:
    """Run the enter preview on the next tick, past ``accept()``.

    Only the mime verdict stays synchronous (it gates accept vs ignore);
    resolve/dispatch/dismiss cost ~7-20ms and would otherwise delay the
    Status answer by that much. Captures plain values, never the event.
    A generation guard drops the deferred work if leave/drop (or a newer
    enter) already ended this gesture — a flick-through must not resurrect
    a stale preview.
    """
    try:
        from PySide6.QtCore import QTimer

        gen = getattr(widget, "_dnd_gen", 0)
        pos = event.position().toPoint()
        t0 = time.monotonic()

        def _tick() -> None:
            try:
                if gen != getattr(widget, "_dnd_gen", None):
                    return
                _apply_preview_at(
                    widget, pos,
                    internal=internal, source_id=source_id, t0=t0,
                )
            except Exception:
                logger.exception("[mc-dnd] deferred enter preview failed")

        QTimer.singleShot(0, _tick)
    except Exception:
        logger.exception("[mc-dnd] deferring enter preview failed")


def drag_move_event(widget, event: QDragMoveEvent) -> None:
    if mc_dnd_diag_light_move_enabled():
        # Diagnostic-only: image_compare semantics (accept, no work).
        mime = event.mimeData()
        if owned_internal_source_slot_id(widget, mime) is not None:
            if not getattr(widget, "_dnd_light_logged", False):
                widget._dnd_light_logged = True
                _dnd_log("dragMove DIAG-LIGHT (accept-only, no dispatch/render)")
            event.acceptProposedAction()
        elif has_image_urls(mime):
            if not getattr(widget, "_dnd_light_logged", False):
                widget._dnd_light_logged = True
                _dnd_log("dragMove DIAG-LIGHT (accept-only, no dispatch/render)")
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()
        return
    source_id = owned_internal_source_slot_id(widget, event.mimeData())
    if source_id is not None:
        event.acceptProposedAction()
        _safe_preview(widget, event, internal=True, source_id=source_id)
        return
    if has_image_urls(event.mimeData()):
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        _safe_preview(widget, event, internal=False)
        return
    _dnd_log("dragMove ignored (no slot mime, no image urls)")
    event.ignore()


def drag_leave_event(widget, event: QDragLeaveEvent) -> None:
    _dnd_log("dragLeave")
    widget._dnd_preview_sig = None
    widget._dnd_gen = getattr(widget, "_dnd_gen", 0) + 1
    _timing_emit(widget, "leave")
    widget.store.dispatch(actions.set_drag_state(active=False))
    event.accept()


def drop_event(widget, event: QDropEvent) -> None:
    mime = event.mimeData()
    source_id = owned_internal_source_slot_id(widget, mime)
    if source_id is not None:
        tgt_path, side, _, swap_id = resolve_drop_target(
            widget, event.position().toPoint(), internal=True
        )
        _dnd_log(
            "drop internal source=%s target_path=%s side=%s swap=%s",
            source_id, tgt_path, side, swap_id,
        )
        _timing_emit(widget, "drop")
        widget._dnd_preview_sig = None
        widget._dnd_gen = getattr(widget, "_dnd_gen", 0) + 1
        widget.store.dispatch(actions.set_drag_state(active=False))
        if side is not None:
            apply_internal_drop(widget, source_id, tgt_path, side, swap_id)
        else:
            _dnd_log("drop internal ignored (source=%s side=%s)", source_id, side)
        event.acceptProposedAction()
        return

    # P7: accept FIRST on a suffix-only verdict — no resolve, no dispatch,
    # no filesystem stat, no emit before accept. The drag source (Mutter)
    # holds busy/waiting until Qt's finish() fires after dropEvent returns,
    # so every GUI millisecond before accept/return holds that cursor. The
    # rest runs deferred on the next tick (value capture only, never the
    # event). The internal echo above is intentionally untouched.
    t_drop = time.monotonic()
    try:
        urls = mime.urls()
    except Exception:
        urls = []
    local_files: list[str] = []
    suffix_hit = False
    for url in urls:
        try:
            local = url.toLocalFile()
        except Exception:
            continue
        local_files.append(local)
        if is_accepted_image_path(local):
            suffix_hit = True
    if not suffix_hit:
        _dnd_log("drop external ignored (no supported image files)")
        try:
            event.ignore()
        except Exception:
            pass
        return
    try:
        pos = event.position().toPoint()
    except Exception:
        pos = None
    widget._dnd_preview_sig = None
    widget._dnd_gen = getattr(widget, "_dnd_gen", 0) + 1
    gen = getattr(widget, "_dnd_gen", 0)
    try:
        event.acceptProposedAction()
    except Exception:
        logger.exception("[mc-dnd] drop accept failed")
        return
    _dnd_log(
        "drop external accept-first files=%d (deferring resolve/dispatch/emit)",
        len(local_files),
    )
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(
            0,
            lambda: _finish_external_drop(widget, local_files, pos, gen, t_drop),
        )
    except Exception:
        logger.exception("[mc-dnd] deferring drop work failed")


def _finish_external_drop(widget, local_files: list[str], pos, gen: int, t_drop: float) -> None:
    """Deferred half of an external drop: runs past accept/return.

    Resolve → clear-drag dispatch → is_file filter → DropQueue enqueue
    (FIFO dedup, one emit per entry). Stale generations (a newer gesture
    started first) are dropped.
    """
    try:
        if gen != getattr(widget, "_dnd_gen", None):
            _dnd_log("drop external deferred skipped (stale gen=%s)", gen)
            return
        t0 = time.monotonic()
        if pos is None:
            tgt_path, side, root_tgt = None, None, False
        else:
            tgt_path, side, root_tgt, _ = resolve_drop_target(
                widget, pos, internal=False
            )
        widget.store.dispatch(actions.set_drag_state(active=False))
        # B3: single seam predicate (accepted-extension ∧ is_file) — the
        # accept-fast-path above stays suffix-only on purpose (no FS stat
        # before accept); the deferred half may stat.
        paths = [Path(local) for local in local_files if is_loadable_image_path(local)]
        _dnd_log(
            "drop external files=%d target_path=%s side=%s root=%s accept_ms=%.1f work_ms=%.1f",
            len(paths), tgt_path, side, root_tgt,
            (t0 - t_drop) * 1000.0, (time.monotonic() - t0) * 1000.0,
        )
        _timing_emit(widget, "drop")
        if paths:
            # Pure-placement anchor for the DropQueue slot key: first leaf
            # under the resolved target (0 for root/empty) — tree data in,
            # no live-canvas read. A rapid double-drop of the same file
            # dedups on (anchor, normpath) instead of double-loading.
            anchor = _placement.anchor_slot_for_path(widget.state.root, tgt_path)
            queued = get_drop_queue().enqueue(
                anchor, paths, widget, (tgt_path, root_tgt), side
            )
            if not queued:
                _dnd_log("drop external deduped (all files already queued/inflight)")
        else:
            _dnd_log("drop external ignored (no supported image files)")
    except Exception:
        logger.exception("[mc-dnd] deferred drop failed")


def apply_internal_drop(
    widget,
    source_id: int,
    target_path: tuple[int, ...] | None,
    side: str,
    swap_slot_id: int | None,
) -> None:
    if side == "center" and swap_slot_id is not None and swap_slot_id != source_id:
        _dnd_log("internal drop: swap %s <-> %s", source_id, swap_slot_id)
        widget.store.dispatch(actions.swap_slots(source_id, swap_slot_id))
        return
    if target_path is None:
        _dnd_log("internal drop: ignored (target_path=None side=%s)", side)
        return
    anchor_slot = anchor_slot_for_path(widget, target_path)
    if anchor_slot is None or anchor_slot == source_id:
        _dnd_log(
            "internal drop: ignored (source=%s anchor=%s side=%s)",
            source_id, anchor_slot, side,
        )
        return
    _dnd_log(
        "internal drop: move %s anchor=%s path=%s side=%s",
        source_id, anchor_slot, target_path, side,
    )
    widget.store.dispatch(
        actions.move_slot(
            source_slot_id=source_id,
            target_path=target_path,
            target_anchor_slot_id=anchor_slot,
            side=side,
        )
    )


def anchor_slot_for_path(widget, path: tuple[int, ...]) -> int | None:
    """Return slot_id of the first leaf inside the subtree at ``path``.

    Thin shell over the pure :func:`placement.anchor_slot_for_path`
    (tree data in, no canvas reads) — kept under this name so the
    internal-drop Move path stays byte-identical.
    """
    return _placement.anchor_slot_for_path(widget.state.root, path)


def begin_pending_duplicate(widget, source_slot_id: int) -> None:
    cancel_pending_placements(widget)
    source = next((s for s in widget.state.slots if s.id == source_slot_id), None)
    if source is None or source.path is None:
        _dnd_log("pending duplicate: ignored (no image source=%s)", source_slot_id)
        return
    try:
        from tabs.multi_compare.pipeline.cache import slot_has_pixels

        canvas = getattr(widget, "canvas", None)
        if not slot_has_pixels(getattr(canvas, "pixel_cache", None), source):
            _dnd_log("pending duplicate: ignored (source not loaded=%s)", source_slot_id)
            return
    except Exception:
        pass
    _dnd_log("pending duplicate: armed source=%s", source_slot_id)
    widget._pending_duplicate_source = source_slot_id
    arm_pending_placement_input(widget)
    update_pending_drag_preview(widget, canvas_cursor_pos(widget), internal=True)


def begin_pending_paste(widget, paths: list[Path]) -> None:
    """Enter external DnD placement: highlight under cursor, click to drop."""
    cancel_pending_placements(widget)
    # B3: seam predicate (accepted-extension ∧ is_file), parity with the
    # deferred-drop finish — a non-image survivor must never arm placement.
    valid = [Path(p) for p in paths if is_loadable_image_path(p)]
    if not valid:
        _dnd_log("pending paste: ignored (no valid files)")
        return
    _dnd_log("pending paste: armed files=%d", len(valid))
    widget._pending_paste_paths = valid
    arm_pending_placement_input(widget)
    update_pending_drag_preview(widget, canvas_cursor_pos(widget), internal=False)


def has_pending_placement(widget) -> bool:
    return (
        widget._pending_duplicate_source is not None
        or widget._pending_paste_paths is not None
    )


def cancel_pending_placements(widget) -> None:
    had = has_pending_placement(widget)
    widget._pending_duplicate_source = None
    widget._pending_paste_paths = None
    if not had:
        return
    try:
        widget.canvas.removeEventFilter(widget)
    except Exception:
        pass
    widget.canvas.unsetCursor()
    widget.store.dispatch(actions.set_drag_state(active=False))


def arm_pending_placement_input(widget) -> None:
    widget.canvas.setCursor(Qt.CursorShape.DragCopyCursor)
    widget.canvas.installEventFilter(widget)
    # FocusReason from the manager (last-input modality), never a literal —
    # keyboard-navigation guide §7. A drop is mouse-driven, so this resolves
    # to MouseFocusReason: no keyboard focus ring while placing.
    from core.navigation import NavigationManager

    widget.canvas.setFocus(NavigationManager.get_instance().current_focus_reason())


def canvas_cursor_pos(widget):
    from PySide6.QtGui import QCursor

    return widget.canvas.mapFromGlobal(QCursor.pos())


def update_pending_drag_preview(widget, pos, *, internal: bool) -> None:
    include_center = internal
    if internal:
        tgt_path, side, root_tgt, swap_id = widget.canvas.compute_drop_target(
            pos, include_center=include_center
        )
        if _drag_preview_changed(
            widget,
            internal=True,
            source_id=widget._pending_duplicate_source,
            tgt_path=tgt_path,
            side=side,
            root_tgt=root_tgt,
            swap_id=swap_id,
        ):
            widget.store.dispatch(
                actions.set_drag_state(
                    active=True,
                    internal=True,
                    source_slot_id=widget._pending_duplicate_source,
                    target_path=tgt_path,
                    target_side=side,
                    target_root=root_tgt,
                    target_swap_slot_id=swap_id,
                )
            )
        chrome.dismiss_placeholder_for_dnd(widget)  # logs the decision itself
        return
    tgt_path, side, root_tgt, _ = widget.canvas.compute_drop_target(pos)
    if _drag_preview_changed(
        widget,
        internal=False,
        source_id=None,
        tgt_path=tgt_path,
        side=side,
        root_tgt=root_tgt,
        swap_id=None,
    ):
        widget.store.dispatch(
            actions.set_drag_state(
                active=True,
                internal=False,
                target_path=tgt_path,
                target_side=side,
                target_root=root_tgt,
            )
        )
    chrome.dismiss_placeholder_for_dnd(widget)  # logs the decision itself


def event_filter(widget, watched, event) -> bool:
    if not has_pending_placement(widget) or watched is not widget.canvas:
        return False
    internal = widget._pending_duplicate_source is not None
    et = event.type()
    if et == QEvent.Type.MouseMove:
        pos = (
            event.position().toPoint()
            if hasattr(event, "position")
            else event.pos()
        )
        update_pending_drag_preview(widget, pos, internal=internal)
        return True
    if et == QEvent.Type.MouseButtonPress:
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            pos = (
                event.position().toPoint()
                if hasattr(event, "position")
                else event.pos()
            )
            if internal:
                tgt_path, side, root_tgt, _ = widget.canvas.compute_drop_target(
                    pos, include_center=False
                )
                finalize_pending_duplicate(widget, tgt_path, side, root_tgt)
            else:
                tgt_path, side, root_tgt, _ = widget.canvas.compute_drop_target(pos)
                finalize_pending_paste(widget, tgt_path, side, root_tgt)
            cancel_pending_placements(widget)
            return True
        if button == Qt.MouseButton.RightButton:
            cancel_pending_placements(widget)
            return True
    if et == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
        cancel_pending_placements(widget)
        return True
    return False


def finalize_pending_paste(
    widget,
    target_path: tuple[int, ...] | None,
    side: str | None,
    target_root: bool,
) -> None:
    paths = widget._pending_paste_paths
    if not paths:
        return
    # Empty canvas: compute_drop_target returns (None, None, True, None).
    # Real file dropEvent still emits; add_image_at treats target_root.
    if side is None and not target_root:
        _dnd_log("pending paste: ignored (side=None root=False)")
        return
    _dnd_log(
        "pending paste: finalize files=%d path=%s side=%s root=%s",
        len(paths), target_path, side, target_root,
    )
    widget.images_dropped.emit(list(paths), (target_path, target_root), side)


def finalize_pending_duplicate(
    widget,
    target_path: tuple[int, ...] | None,
    side: str | None,
    target_root: bool,
) -> None:
    source_id = widget._pending_duplicate_source
    if source_id is None or side is None:
        return
    source = next((s for s in widget.state.slots if s.id == source_id), None)
    if source is None or source.path is None:
        _dnd_log("pending duplicate: ignored (source gone=%s)", source_id)
        return
    try:
        from tabs.multi_compare.pipeline.cache import slot_has_pixels

        canvas = getattr(widget, "canvas", None)
        cache = getattr(canvas, "pixel_cache", None)
        if not slot_has_pixels(cache, source):
            _dnd_log("pending duplicate: ignored (source not loaded=%s)", source_id)
            return
    except Exception:
        pass
    _dnd_log(
        "pending duplicate: finalize source=%s path=%s side=%s root=%s",
        source_id, target_path, side, target_root,
    )
    # B1: path-only duplicate — pixels resolve from the session cache (same
    # content key), no pixel copy through the action.
    before = len(widget.state.slots)
    widget.store.dispatch(
        actions.add_slot(
            path=source.path,
            label=source.label,
            target_path=tuple(target_path or ()),
            side=side,
            target_root=target_root,
        )
    )
    if len(widget.state.slots) > before:
        try:
            new_id = widget.state.slots[-1].id
            controller = getattr(widget, "_controller", None)
            if controller is not None:
                controller.ensure_visible_slots_loading()
            else:
                _dnd_log("pending duplicate: created slot %s (cache-warm fill)", new_id)
        except Exception:
            pass