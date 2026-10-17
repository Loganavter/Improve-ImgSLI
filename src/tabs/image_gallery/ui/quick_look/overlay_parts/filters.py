"""QuickLookOverlay event filters — subtree hover watch + ``eventFilter``.

Moved verbatim from ``ui/quick_look.py`` (plan-gallery-split-2026-10-17,
Part C2). Plain functions taking the overlay as their first argument; the
class keeps same-named one-line delegators. ``super()`` becomes an explicit
``TopLevelInWindowOverlay`` call (the sole base) — same resolution.
"""

from __future__ import annotations

from sli_ui_toolkit.widgets import TopLevelInWindowOverlay


def _install_subtree_hover_watch(self, root) -> None:
    """Install this overlay as MouseMove observer on a content subtree.

    Idempotent (remove-then-install): ChildAdded storms must never stack
    duplicate filter entries on the same widget.
    """
    try:
        from PySide6.QtWidgets import QWidget as _QW

        stack = [root]
        seen = set()
        while stack:
            w = stack.pop()
            try:
                if w is None or id(w) in seen:
                    continue
                seen.add(id(w))
                if w is not self:
                    try:
                        w.removeEventFilter(self)
                    except Exception:
                        pass
                    try:
                        w.installEventFilter(self)
                    except Exception:
                        pass
                try:
                    stack.extend(w.findChildren(_QW))
                except Exception:
                    pass
            except Exception:
                continue
    except Exception:
        pass


def eventFilter(self, watched, event) -> bool:  # noqa: N802
    # W8: card-plate resizes (user drag via the corner grip or direct
    # resizes) re-run the same pin hooks as resizeEvent.
    # W9: the whole card border is an 8px resize strip (8 directions) —
    # press/move/release on the plate drive the border drag, plain
    # moves update the hover cursor. Same clamp + re-pin idiom as W8.
    try:
        from PySide6.QtCore import QEvent

        _watched_content = getattr(self, "_content", None)
        if event.type() == QEvent.Type.ChildAdded and (
            watched is _watched_content
            or (_watched_content is not None and _watched_content.isAncestorOf(watched))
        ):
            # D5: rows/strip/buttons are rebuilt per populate — watch
            # newcomers the same way as the initial subtree.
            try:
                child = event.child()
                if child is not None:
                    self._install_subtree_hover_watch(child)
            except Exception:
                pass
        if watched is getattr(self, "_content", None):
            t = event.type()
            if t == QEvent.Type.Resize:
                try:
                    self._reposition_source_inset()
                except Exception:
                    pass
                try:
                    from tabs.image_gallery.ui.quick_look.helpers import reposition_grip
                    reposition_grip(self)
                except Exception:
                    pass
            elif t == QEvent.Type.MouseButtonPress:
                try:
                    from tabs.image_gallery.ui.quick_look.helpers import handle_border_press
                    if handle_border_press(self, event):
                        return True
                except Exception:
                    pass
            elif t == QEvent.Type.MouseMove:
                try:
                    from tabs.image_gallery.ui.quick_look.helpers import handle_border_move
                    from tabs.image_gallery.ui.quick_look.helpers import trace_move

                    try:
                        trace_move(self, "plate-move", event.position().toPoint(), watched)
                    except Exception:
                        pass
                    if handle_border_move(self, event):
                        return True
                except Exception:
                    pass
            elif t == QEvent.Type.MouseButtonRelease:
                try:
                    from tabs.image_gallery.ui.quick_look.helpers import handle_border_release
                    if handle_border_release(self, event):
                        return True
                except Exception:
                    pass
            elif t == QEvent.Type.Leave:
                try:
                    if getattr(self, "_border_drag", None) is None:
                        from tabs.image_gallery.ui.quick_look.helpers import apply_resize_cursor

                        apply_resize_cursor(self, self._content, "plate", None)
                except Exception:
                    pass
        # D5: landing moves on content descendants (buttons, labels,
        # viewports, bars) never reach the plate filter above, so a
        # border→child jump strands a set plate cursor with no clear
        # path. Recompute the slot from the landing position; hover-only,
        # never consumed (drags keep the existing plate/ring paths).
        try:
            from PySide6.QtCore import QEvent as _QE2

            _content = getattr(self, "_content", None)
            _in_content = (
                _content is not None
                and watched is not _content
                and _content.isAncestorOf(watched)
            )
            if event.type() == _QE2.Type.MouseMove and _in_content:
                try:
                    from PySide6.QtCore import Qt as _Qt2

                    from tabs.image_gallery.ui.quick_look.helpers import (
                        apply_resize_cursor as _arc2,
                    )
                    from tabs.image_gallery.ui.quick_look.helpers import (
                        nav_button_at as _nba2,
                    )
                    from tabs.image_gallery.ui.quick_look.helpers import (
                        resize_zone_at as _rza2,
                    )

                    if getattr(self, "_border_drag", None) is None:
                        try:
                            _held = event.buttons()
                        except Exception:
                            _held = _Qt2.MouseButton.NoButton
                        if _held == _Qt2.MouseButton.NoButton:
                            try:
                                _global = event.globalPosition().toPoint()
                            except Exception:
                                _global = None
                            if _global is not None:
                                try:
                                    _ov_local = self.mapFromGlobal(_global)
                                except Exception:
                                    _ov_local = None
                                try:
                                    _c_local = _content.mapFromGlobal(_global)
                                except Exception:
                                    _c_local = None
                                if _ov_local is not None and _c_local is not None:
                                    # W11: nav-arrow rects never show resize.
                                    try:
                                        _nav = _nba2(self, _ov_local)
                                    except Exception:
                                        _nav = None
                                    if _nav is not None:
                                        _arc2(self, _content, "plate", None)
                                    else:
                                        from tabs.image_gallery.ui.quick_look.helpers import (
                                            resize_cursor_for as _rcf2,
                                        )

                                        _arc2(self, _content, "plate", _rcf2(_rza2(_content, _c_local)))
                except Exception:
                    pass
        except Exception:
            pass
        # Slot frame (IC parity): the preview host is the single
        # laid-out geometry authority; on its Resize mirror the rect
        # onto every layout-external child (GPU canvas, first-frame
        # cover) so the active surface never desyncs. Layout passes
        # that settle the host without a card resize also re-pin the
        # insets anchored to it.
        try:
            from PySide6.QtCore import QEvent as _QE

            if watched is getattr(self, "_preview_host", None) and event.type() == _QE.Type.Resize:
                try:
                    from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
                        _fit_preview_slot,
                    )
                    _fit_preview_slot(self)
                except Exception:
                    pass
                try:
                    self._reposition_source_inset()
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass
    return TopLevelInWindowOverlay.eventFilter(self, watched, event)
