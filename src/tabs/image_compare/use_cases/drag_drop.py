"""External file-drop handling for ``ImageCompareTab`` -- split out to keep
that class down to the ``TabContract`` surface itself. ``accepts_drop``/
``handle_drop`` are required ``TabContract`` method names, so ``tab.py``
keeps thin delegators of those exact names.
"""

from __future__ import annotations

import logging
from pathlib import Path

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _IMAGE_EXTENSIONS
from tabs.image_compare.debug import ic_dnd_debug as _dnd_log

logger = logging.getLogger("ImproveImgSLI")


def accepts_drop(paths: list[Path]) -> bool:
    _dnd_log("accepts_drop: %d paths %r", len(paths), paths[:3])
    for p in paths:
        ok = p.suffix.lower() in _IMAGE_EXTENSIONS
        if ok:
            _dnd_log("  accepts_drop: %s suffix=%s -> True", p, p.suffix.lower())
            return True
        _dnd_log("  accepts_drop: %s suffix=%s -> False", p, p.suffix.lower())
    return False


class DropQueue:
    """FIFO dedup queue for DnD drops — Phase 3.

    Dedup key (slot, normpath). Max 1 inflight per slot (like AbortSignal).
    Hide is done synchronously before acceptProposedAction (before enqueue returns).
    Next drop immediately accept + enqueue even if previous inflight.
    """

    def __init__(self) -> None:
        from collections import deque as _dq

        self._queue: _dq[tuple[int, list[str], object, object]] = _dq()
        self._inflight_slots: set[int] = set()
        self._queued_keys: set[tuple[int, str]] = set()
        self._inflight_keys: set[tuple[int, str]] = set()

    def _hide_sync(self, widget) -> None:
        # hide synchronously before accept — matches window_event_handler hide
        try:
            if widget is not None and hasattr(widget, "update_drag_overlays"):
                horiz = False
                try:
                    ctx = getattr(widget, "_context", None)
                    store = getattr(ctx, "store", None) if ctx is not None else None
                    if store is not None:
                        try:
                            horiz = bool(store.viewport.view_state.is_horizontal)
                        except Exception:
                            horiz = False
                except Exception:
                    horiz = False
                widget.update_drag_overlays(horizontal=horiz, visible=False)
            # extra direct canvas hide for RHI SSOT
            try:
                canvas = getattr(widget, "image_label", None)
                if canvas is not None and hasattr(canvas, "set_drag_overlay_state"):
                    try:
                        canvas.set_drag_overlay_state(visible=False)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def enqueue(self, slot: int, image_paths: list[str], widget, sessions) -> bool:
        import os as _os

        # dedup (slot, normpath) — FIFO
        uniq: list[str] = []
        for p in image_paths:
            try:
                n = _os.path.normpath(str(p))
            except Exception:
                n = str(p)
            key = (int(slot), n)
            if key in self._queued_keys or key in self._inflight_keys:
                _dnd_log("DropQueue dedup skip slot=%s path=%s", slot, n)
                continue
            uniq.append(n)
            self._queued_keys.add(key)
        if not uniq:
            _dnd_log("DropQueue enqueue slot=%s -> all deduped, skip", slot)
            return False
        # hide synchronously before acceptProposedAction
        self._hide_sync(widget)
        self._queue.append((int(slot), uniq, widget, sessions))
        _dnd_log("DropQueue enqueue slot=%s paths=%s queued=%s inflight=%s", slot, uniq[:3], len(self._queue), self._inflight_slots)
        self._try_process()
        return True

    def _try_process(self) -> None:
        from PySide6.QtCore import QTimer as _QTimer

        # scan queue for first entry whose slot not inflight
        idx_to_run: int | None = None
        entry = None
        for idx, (slot, paths, w, s) in enumerate(list(self._queue)):
            if slot not in self._inflight_slots:
                idx_to_run = idx
                entry = (slot, paths, w, s)
                break
        if entry is None:
            return
        slot, paths, widget, sessions = entry
        # remove from queue
        try:
            self._queue.remove(entry)  # type: ignore[arg-type]
        except Exception:
            # fallback: rebuild without entry
            from collections import deque as _dq

            new_q = _dq(x for x in self._queue if x is not entry)
            self._queue = new_q
        for n in paths:
            key = (int(slot), n)
            self._queued_keys.discard(key)
            self._inflight_keys.add(key)
        self._inflight_slots.add(int(slot))
        _dnd_log("DropQueue _try_process start slot=%s paths=%s", slot, paths[:3])
        import time as _t

        _sched_t = _t.monotonic()

        def _do_load(q=self, sl=slot, ps=paths, wid=widget, sess=sessions, st=_sched_t):
            _dnd_log(
                "handle_drop: _do_load ENTER slot=%s t=%.3f dt=%.3f widget_vis_before=%s",
                sl,
                _t.monotonic(),
                _t.monotonic() - st,
                getattr(wid, "is_drag_overlay_visible", lambda: "?")(),
            )
            try:
                sess.load_images_from_paths(ps, sl)
                _dnd_log(
                    "handle_drop: _do_load done t=%.3f widget_vis_after=%s",
                    _t.monotonic(),
                    getattr(wid, "is_drag_overlay_visible", lambda: "?")(),
                )
            except Exception as e:
                _dnd_log("handle_drop: _do_load failed %r", e)
            try:
                vis_after = getattr(wid, "is_drag_overlay_visible", lambda: "?")()
                ov_vis = getattr(getattr(wid, "drag_overlay", None), "isVisible", lambda: "?")()
                _dnd_log("handle_drop: _do_load post-check canvas_vis=%s overlay_isVisible=%s", vis_after, ov_vis)
                if vis_after or ov_vis:
                    _dnd_log("handle_drop: BLOCKING after load! canvas_vis=%s overlay=%s", vis_after, ov_vis)
            except Exception:
                pass
            # release inflight and try next
            for _n in ps:
                q._inflight_keys.discard((int(sl), _n))
            q._inflight_slots.discard(int(sl))
            _dnd_log("DropQueue finish slot=%s remaining queued=%s", sl, len(q._queue))
            q._try_process()

        _QTimer.singleShot(0, _do_load)

    def clear(self) -> None:
        self._queue.clear()
        self._inflight_slots.clear()
        self._queued_keys.clear()
        self._inflight_keys.clear()


_drop_queue = DropQueue()


def get_drop_queue() -> DropQueue:
    return _drop_queue


def handle_drop(tab, paths: list[Path], hint: dict | None = None) -> bool:
    _dnd_log("handle_drop: ENTER %d paths %r hint=%r", len(paths), paths[:5], hint)
    widget = tab._widget
    if widget is None:
        _dnd_log("handle_drop: widget is None -> False")
        logger.warning("ImageCompareTab.handle_drop: widget is not initialized")
        return False
    main_window = getattr(widget._context, "main_window", None) if widget._context else None
    if main_window is None:
        logger.warning("ImageCompareTab.handle_drop: main_window is unavailable")
        return False
    controller = getattr(main_window, "main_controller", None)
    if controller is None:
        presenter = getattr(main_window, "presenter", None)
        controller = getattr(presenter, "main_controller", None)
    sessions = getattr(controller, "sessions", None) if controller else None
    if sessions is None:
        logger.warning(
            "ImageCompareTab.handle_drop: sessions controller unavailable "
            "(main_controller=%r presenter=%r)",
            getattr(main_window, "main_controller", None),
            getattr(main_window, "presenter", None),
        )
        return False
    image_paths = [str(p) for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
    _dnd_log("handle_drop: filtered %d/%d image_paths %r", len(image_paths), len(paths), image_paths[:3])
    if not image_paths:
        _dnd_log("handle_drop: no supported image paths -> False")
        logger.warning(
            "ImageCompareTab.handle_drop: no supported image paths in %s",
            paths,
        )
        return False
    slot = 1
    if hint is not None:
        if "slot" in hint:
            slot = 1 if int(hint.get("slot") or 1) == 1 else 2
        elif "is_left_area" in hint:
            slot = 1 if bool(hint.get("is_left_area")) else 2
    _dnd_log("handle_drop: scheduling load slot=%s paths=%r widget_vis=%s", slot, image_paths[:3], getattr(widget, "is_drag_overlay_visible", lambda: "?")())
    # Phase 3: hide synchronously before acceptProposedAction, FIFO dedup with max 1 inflight per slot
    import time as _t

    _sched_t = _t.monotonic()
    # hide before enqueue -> before window_event_handler acceptProposedAction
    try:
        _drop_queue._hide_sync(widget)
    except Exception:
        pass
    enq = _drop_queue.enqueue(slot, image_paths, widget, sessions)
    if not enq:
        # deduped but still accept to prevent OS retry
        _dnd_log("handle_drop: deduped, still accept t=%.3f", _t.monotonic() - _sched_t)
    _dnd_log("handle_drop: scheduled t=%.3f, returning True (overlay should already be hidden by WindowEventHandler vis=%s)", _sched_t, getattr(widget, "is_drag_overlay_visible", lambda: "?")())
    return True
