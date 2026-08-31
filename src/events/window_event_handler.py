import logging
import os
import traceback

from PySide6.QtCore import QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent

logger = logging.getLogger("ImproveImgSLI")

def _dnd_debug(msg, *args, stack=False, **kwargs):
    # Gated by same flag as [ic-dnd] but also IMGSLI_DND_DEBUG for window-level
    if os.environ.get("IMGSLI_DND_DEBUG") or os.environ.get("IMGSLI_IMAGE_COMPARE_DEBUG") or os.environ.get("IMGSLI_IC_DEBUG"):
        # Use WARNING so visible without --debug, like ic_dnd_debug
        logger.warning("[dnd-window] " + msg, *args, **kwargs)
        if stack:
            try:
                s = "".join(traceback.format_stack(limit=7)[:-2])
                logger.warning("[dnd-window] stack:\n%s", s)
            except Exception:
                pass
    else:
        logger.debug("[dnd-window] " + msg, *args, **kwargs)


def _dbg_overlay_state(widget) -> str:
    """Compact overlay state for debug lines."""
    try:
        if widget is None:
            return "widget=None"
        canvas = getattr(widget, "image_label", None)
        overlay = getattr(widget, "drag_overlay", None)
        c_vis = "?"
        c_geom = "?"
        o_vis = "?"
        o_geom = "?"
        try:
            c_vis = canvas.is_drag_overlay_visible() if canvas and hasattr(canvas, "is_drag_overlay_visible") else "?"
        except Exception as e:
            c_vis = f"err:{e}"
        try:
            c_geom = repr(canvas.geometry()) if canvas else "?"
        except Exception:
            pass
        try:
            o_vis = overlay.isVisible() if overlay else "?"
            o_geom = repr(overlay.geometry()) if overlay else "?"
        except Exception:
            pass
        w_vis = "?"
        try:
            w_vis = widget.is_drag_overlay_visible() if hasattr(widget, "is_drag_overlay_visible") else "?"
        except Exception:
            pass
        return f"canvas_vis={c_vis} widget_vis={w_vis} overlay_isVisible={o_vis} canvas_geom={c_geom} overlay_geom={o_geom}"
    except Exception as e:
        return f"err:{e}"

class WindowEventHandler(QObject):
    def __init__(self, store, main_controller, widget, parent=None):
        super().__init__(parent)
        self.store = store

        self.main_controller = main_controller
        self.widget = widget
        self.main_window = parent
        self._first_external_load_pending = True
        self._drag_leave_timer = QTimer(self)
        self._drag_leave_timer.setSingleShot(True)
        self._drag_leave_timer.setInterval(80)
        self._drag_leave_timer.timeout.connect(self._handle_deferred_drag_leave)

    def _schedule_load_when_stable(
        self, image_paths: list[str], slot_num: int, delay_ms: int = 100
    ):
        def _try_load():

            is_stable = (
                bool(getattr(self.main_window, "_is_ui_stable", True))
                and self.main_window.isVisible()
            )
            if not is_stable:
                QTimer.singleShot(delay_ms, _try_load)
                return
            if self.main_controller and self.main_controller.sessions:
                self.main_controller.sessions.load_images_from_paths(
                    image_paths, slot_num
                )
            self._first_external_load_pending = False

        if self._first_external_load_pending:
            QTimer.singleShot(delay_ms, _try_load)
        else:
            QTimer.singleShot(0, _try_load)

    def handle_drag_enter(self, event: QDragEnterEvent):
        # DEBUG: log every enter with full overlay state to diagnose "still blocks"
        _dnd_debug(
            "handle_drag_enter ENTER hasUrls=%s %s timerActive=%s",
            event.mimeData().hasUrls(),
            _dbg_overlay_state(self.widget),
            self._drag_leave_timer.isActive(),
            stack=True,
        )
        if event.mimeData().hasUrls():
            was_visible = getattr(self.widget, "is_drag_overlay_visible", lambda: "?")()
            self._drag_leave_timer.stop()
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            _dnd_debug(
                "handle_drag_enter -> show overlay was_visible=%s %s",
                was_visible,
                _dbg_overlay_state(self.widget),
                stack=False,
            )
            self._safe_update_drag_overlays(True)
            _dnd_debug(
                "handle_drag_enter DONE after_show=%s %s",
                getattr(self.widget, "is_drag_overlay_visible", lambda: "?")(),
                _dbg_overlay_state(self.widget),
            )
        else:
            _dnd_debug("handle_drag_enter IGNORE no Urls")
            event.ignore()

    def _safe_update_drag_overlays(self, visible):
        import time
        _before = getattr(self.widget, "is_drag_overlay_visible", lambda: "?")() if self.widget and hasattr(self.widget, "is_drag_overlay_visible") else "?"
        _before_state = _dbg_overlay_state(self.widget)
        _ts = time.monotonic()
        if self.widget is not None and hasattr(self.widget, "update_drag_overlays"):
            try:
                self.widget.update_drag_overlays(
                    self.store.viewport.view_state.is_horizontal, visible=visible
                )
                _after = getattr(self.widget, "is_drag_overlay_visible", lambda: "?")() if hasattr(self.widget, "is_drag_overlay_visible") else "?"
                _after_state = _dbg_overlay_state(self.widget)
                # Always log visibility changes, plus periodic state for post-drop blocking diagnosis
                if _before != visible or _after != visible or visible is False:
                    _dnd_debug(
                        "_safe_update_drag_overlays visible=%s before=%s after=%s t=%.3f before_state=[%s] after_state=[%s]",
                        visible,
                        _before,
                        _after,
                        _ts,
                        _before_state,
                        _after_state,
                        stack=True,
                    )
                else:
                    _dnd_debug(
                        "_safe_update_drag_overlays visible=%s before=%s after=%s t=%.3f [%s]",
                        visible,
                        _before,
                        _after,
                        _ts,
                        _after_state,
                    )
            except (AttributeError, RuntimeError) as e:
                logger.warning(
                    f"WindowEventHandler._safe_update_drag_overlays: failed to update drag overlays: {e}"
                )

    def handle_drag_move(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            self._drag_leave_timer.stop()
            # DEBUG: log if overlay should be visible but isn't (input blocked)
            try:
                vis = getattr(self.widget, "is_drag_overlay_visible", lambda: "?")()
                if not vis:
                    _dnd_debug("handle_drag_move hasUrls but overlay NOT visible %s", _dbg_overlay_state(self.widget))
            except Exception:
                pass
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def handle_drag_leave(self, event):
        _dnd_debug("handle_drag_leave -> start 80ms timer %s", _dbg_overlay_state(self.widget))
        self._drag_leave_timer.start()
        event.accept()

    def handle_drop(self, event: QDropEvent):
        import time
        _drop_ts = time.monotonic()
        _dnd_debug(
            "handle_drop ENTER %s timerActive=%s t=%.3f",
            _dbg_overlay_state(self.widget),
            self._drag_leave_timer.isActive(),
            _drop_ts,
            stack=True,
        )
        self._drag_leave_timer.stop()
        self._safe_update_drag_overlays(False)
        # Force immediate visual hide – TopLevelInWindowOverlay hide() alone
        # waits for next paint, which is coalesced with the RHI canvas repaint
        # triggered only after image decode (0.5s). Repaint parent now.
        # Also force canvas repaint so RHI drag tiles disappear instantly and
        # don't block input during the async decode.
        try:
            if self.widget:
                self.widget.update()
                self.widget.repaint()
                if hasattr(self.widget, "drag_overlay"):
                    self.widget.drag_overlay.update()
                    self.widget.drag_overlay.repaint()
                # RHI canvas overlay (set_drag_overlay_state) only scheduled
                # widget.update(); force immediate repaint so tiles don't
                # linger logically visible while visually coalesced.
                canvas = getattr(self.widget, "image_label", None)
                if canvas is not None:
                    try:
                        canvas.update()
                        # QRhiWidget repaint is coalesced via RHI; requestUpdate
                        # is the explicit flush path, but update() + process
                        # is sufficient to clear the overlay state immediately.
                        if hasattr(canvas, "repaint"):
                            canvas.repaint()
                    except Exception:
                        pass
        except Exception:
            pass
        _dnd_debug(
            "handle_drop hide overlay is_drag_overlay_visible=%s %s",
            getattr(self.widget, "is_drag_overlay_visible", lambda: "?")() if self.widget and hasattr(self.widget, "is_drag_overlay_visible") else "?",
            _dbg_overlay_state(self.widget),
            stack=True,
        )
        # DEBUG: post-drop blocking check — verify overlay stays hidden and new input not blocked
        def _post_drop_check(delay_ms: int):
            def _check():
                vis = getattr(self.widget, "is_drag_overlay_visible", lambda: "?")()
                state = _dbg_overlay_state(self.widget)
                _dnd_debug("handle_drop post-check +%dms vis=%s %s", delay_ms, vis, state, stack=False)
                # If still visible after drop, it blocks new DnD (the reported bug)
                if vis:
                    _dnd_debug("handle_drop POST-CHECK BLOCKING! overlay still visible +%dms %s", delay_ms, state, stack=True)
            return _check

        for _d in (50, 200, 500, 1000):
            try:
                QTimer.singleShot(_d, _post_drop_check(_d))
            except Exception:
                pass

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()

            image_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]

            if not image_paths:
                event.ignore()
                return

            pos = (
                event.position().toPoint()
                if hasattr(event, "position")
                else event.pos()
            )
            slot = 1 if self._is_in_left_area(pos) else 2

            if self._try_tab_registry_drop(
                image_paths,
                hint={"is_left_area": slot == 1, "slot": slot},
            ):
                event.acceptProposedAction()
                return

            event.acceptProposedAction()

            QTimer.singleShot(
                150,
                lambda: (
                    self.main_controller.sessions.load_images_from_paths(
                        image_paths, slot
                    )
                    if self.main_controller and self.main_controller.sessions
                    else None
                ),
            )
        else:
            event.ignore()

    def _try_tab_registry_drop(
        self,
        image_paths: list[str],
        hint: dict | None = None,
    ) -> bool:
        try:
            session = self.store.get_active_workspace_session()
            if session is None:
                return False
            registry = getattr(getattr(self.main_window, "ui", None), "_tab_registry", None)
            if registry is None:
                return False
            from pathlib import Path
            paths = [Path(p) for p in image_paths]
            handled = registry.route_drop(session.session_type, paths, hint=hint)
            return handled
        except Exception:
            logger.exception("WindowEventHandler._try_tab_registry_drop failed")
            return False

    def handle_resize(self, event):
        if self.widget is None:
            return
        self.widget.update_drag_overlays(
            self.store.viewport.view_state.is_horizontal, self.widget.is_drag_overlay_visible()
        )

    def handle_close(self, event):
        event.accept()

    def _is_in_left_area(self, pos: QPoint) -> bool:
        if self.widget is None:
            return True
        if not self.widget.image_label.isVisible():
            return True
        label_rect = self.widget.image_label.geometry()
        local_to_label = (
            0 <= pos.x() <= self.widget.image_label.width()
            and 0 <= pos.y() <= self.widget.image_label.height()
        )

        if not self.store.viewport.view_state.is_horizontal:
            mid_x = (
                self.widget.image_label.width() / 2
                if local_to_label
                else label_rect.x() + label_rect.width() / 2
            )
            return pos.x() < mid_x
        else:
            mid_y = (
                self.widget.image_label.height() / 2
                if local_to_label
                else label_rect.y() + label_rect.height() / 2
            )
            return pos.y() < mid_y

    def _handle_deferred_drag_leave(self):
        self._safe_update_drag_overlays(False)
