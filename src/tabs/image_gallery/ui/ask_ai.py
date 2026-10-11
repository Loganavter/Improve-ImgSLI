"""Ask AI flyout (A3) — one scope-aware ask surface.

A toolkit ``BaseFlyout`` with a ``CustomLineEdit`` (pre-filled, overridable
default prompt: ``Tab`` accepts it, ``Enter`` sends) and a result pane marked
"AI read, unverified". Advisory only: the flyout renders text, it never
mutates rank/selection/store. All async work is dispatched by the controller
(``GalleryController.ask_ai_question``); this widget is pure surface.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import BaseFlyout, CustomLineEdit, Label

#: Minimum flyout width (the ask surface must not collapse).
MIN_WIDTH_PX = 300
MIN_HEIGHT_PX = 160


class _ResizeGrip(QWidget):
    """Bottom-right drag handle — resizes the flyout (an in-window child).

    A real ``QSizeGrip`` only resizes top-level windows, and the toolkit has no
    resizable flyout, so the grip drives the flyout/container geometry itself.
    """

    def __init__(self, flyout: "AskAiFlyout") -> None:
        super().__init__(flyout)
        self._flyout = flyout
        self._start = None
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setFixedSize(scaled_px(16), scaled_px(16))
        try:
            self.setObjectName("gallery_ask_ai_resize_grip")
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        try:
            from PySide6.QtGui import QColor, QPainter, QPen

            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor(150, 150, 150, 170), 1.4))
            w, h = self.width(), self.height()
            for off in (3, 7, 11):
                p.drawLine(w - off, h - 2, w - 2, h - off)
            p.end()
        except Exception:
            pass

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = (event.globalPosition().toPoint(), self._flyout.size())
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start is None:
            return
        start, size0 = self._start
        pos = event.globalPosition().toPoint()
        self._flyout.apply_user_size(
            size0.width() + (pos.x() - start.x()),
            size0.height() + (pos.y() - start.y()),
        )
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._start = None
        event.accept()


class AskAiFlyout(BaseFlyout):
    """Free-form question + AI result, anchored to a card or series header."""

    flyout_group = "gallery_ask_ai"

    submitted = Signal(str)
    closed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._default_prompt = "Summary"
        # Localized chrome, injected by the controller (i18n). Defaults are
        # English so the widget is usable standalone (tests/toolkit preview).
        self._title_text = "Ask AI"
        self._busy_text = "Thinking…"
        self._read_badge = "AI read, unverified"
        self._error_text = "AI could not answer."
        self.content_layout.setContentsMargins(
            scaled_px(12), scaled_px(12), scaled_px(12), scaled_px(12)
        )
        self.content_layout.setSpacing(scaled_px(8))

        self._title = Label(self._title_text, pixel_size=13, bold=True, parent=self)
        self._scope = Label("", pixel_size=11, parent=self)
        self._edit = CustomLineEdit(parent=self)
        self._edit.setPlaceholderText(self._default_prompt)
        self._edit.setMinimumWidth(scaled_px(300))
        try:
            self._edit.setClearButtonEnabled(True)
        except Exception:
            pass
        self._edit.returnPressed.connect(self._emit_submit)
        self._edit.installEventFilter(self)
        self._result = Label("", pixel_size=12, word_wrap=True, parent=self)
        self._result.setMinimumWidth(scaled_px(MIN_WIDTH_PX - 40))
        self._status = Label("", pixel_size=11, parent=self)

        for widget in (
            self._title,
            self._scope,
            self._edit,
            self._result,
            self._status,
        ):
            self.content_layout.addWidget(widget)

        # User resize support (toolkit flyouts auto-size only).
        self._user_size: tuple[int, int] | None = None
        try:
            self.setMinimumSize(scaled_px(MIN_WIDTH_PX), scaled_px(MIN_HEIGHT_PX))
        except Exception:
            pass
        self._grip = _ResizeGrip(self)

    # -- interaction --------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt name)
        # Tab accepts the grayed default prompt (else it is just a placeholder
        # and the user must retype it). Enter always sends.
        if obj is self._edit and event.type() == QEvent.Type.KeyPress:
            try:
                if event.key() == Qt.Key.Key_Tab and not self._edit.text().strip():
                    self._edit.setText(self._default_prompt)
                    self._edit.selectAll()
                    return True
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _emit_submit(self) -> None:
        # Guard against a double submit when both the field's returnPressed
        # and this flyout's keyPressEvent see the same Return.
        import time

        now = time.monotonic()
        if now - getattr(self, "_last_submit_at", 0.0) < 0.4:
            return
        self._last_submit_at = now
        try:
            question = self._edit.text().strip() or self._default_prompt
        except Exception:
            question = self._default_prompt
        # Enter must send-and-release: drop any selection left by the Tab
        # prefill and take focus off the field (the field otherwise keeps a
        # highlighted selection on screen).
        try:
            self._edit.deselect()
        except Exception:
            pass
        try:
            self._edit.clearFocus()
        except Exception:
            pass
        self.submitted.emit(question)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        # The flyout's own key handler is the reliable Enter path: the toolkit
        # nav section delivers Return/Enter here when the focused field yields
        # it (the field's returnPressed is not always reached in the live
        # window). Return always sends.
        try:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._emit_submit()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def set_texts(
        self,
        *,
        title: str | None = None,
        busy: str | None = None,
        read_badge: str | None = None,
        error: str | None = None,
    ) -> None:
        """Inject localized chrome strings (from the tab i18n)."""
        if title:
            self._title_text = str(title)
            try:
                self._title.setText(self._title_text)
            except Exception:
                pass
        if busy:
            self._busy_text = str(busy)
        if read_badge:
            self._read_badge = str(read_badge)
        if error:
            self._error_text = str(error)

    def open_for(
        self,
        anchor: QWidget,
        *,
        scope_label: str = "",
        default_prompt: str = "Summary",
        title: str = "",
        initial_result=None,
        initial_error: str = "",
    ) -> None:
        """Reset + show under *anchor*; focus lands in the question field.

        ``initial_result``/``initial_error`` seed the pane BEFORE the show
        animation starts (the persisted-answer prefill). Setting them after
        the show — via ``reposition()`` — would clear the fade snapshot while
        its animation is still running, flashing the panel white.
        """
        self._default_prompt = str(default_prompt or "Summary")
        self._title.setText(str(title or self._title_text))
        scope_text = str(scope_label or "")
        self._scope.setText(scope_text)
        # No scope line = no empty row (series scope has no label at all).
        try:
            self._scope.setVisible(bool(scope_text))
        except Exception:
            pass
        self._edit.setText("")
        self._edit.setPlaceholderText(self._default_prompt)
        self._edit.setReadOnly(False)
        self._result.setText("")
        self._status.setText("")
        if initial_result is not None:
            self.show_result(
                getattr(initial_result, "text", "") or "",
                backend=getattr(initial_result, "backend", "") or "",
                cached=bool(getattr(initial_result, "cached", False)),
            )
        elif initial_error:
            self.show_error(initial_error)
        try:
            self._edit.setFocus()
        except Exception:
            pass
        try:
            self.show_aligned(
                anchor,
                anchor_point="bottom-left",
                flyout_point="top-left",
                offset=scaled_px(8),
                animation="fade",
            )
        except Exception:
            try:
                self.show_aligned(anchor)
            except Exception:
                pass
        # Apply a persisted manual size / fit the seeded result, deferred past
        # the show animation (see _relayout).
        self._relayout()

    # -- state (called by the controller) -----------------------------------

    def _relayout(self) -> None:
        """Re-run the surface layout after the wrapped result text changed.

        A wrapped ``Label`` only reports its tall height once the parent
        width is fixed; without this the result overflows its row and
        overlaps the status line. ``reposition()`` is the toolkit's sanctioned
        re-size path (a raw ``adjustSize()`` collapses the surface because the
        container is briefly hidden for the fade).
        """
        try:
            self._result.updateGeometry()
            self._status.updateGeometry()
            if not self.isVisible():
                return
            # Never resize while the show animation is running: clearing the
            # fade snapshot mid-animation paints the panel white until the
            # animation ends. Defer the resize to the animation's finish.
            anim = getattr(self, "_show_animation", None)
            if anim is not None:
                if not getattr(self, "_ask_reposition_pending", False):
                    self._ask_reposition_pending = True
                    try:
                        anim.finished.connect(self._after_show_reposition)
                    except Exception:
                        self._ask_reposition_pending = False
                return
            if getattr(self, "_user_size", None) is not None:
                # Manual size wins over auto-size: re-wrap at the user's width
                # and grow only if the content needs more height.
                self.apply_user_size(*self._user_size)
                return
            self._reposition_now()
        except Exception:
            pass

    def _after_show_reposition(self) -> None:
        self._ask_reposition_pending = False
        if not self.isVisible():
            return
        if getattr(self, "_user_size", None) is not None:
            self.apply_user_size(*self._user_size)
        else:
            self._reposition_now()

    def _reposition_now(self) -> None:
        # Do not yank focus back to the field if the user is already typing a
        # follow-up when the previous answer lands.
        prev = getattr(self, "_skip_focus_grab", False)
        self._skip_focus_grab = True
        try:
            self.reposition()
        finally:
            self._skip_focus_grab = prev

    # -- manual resize -------------------------------------------------------

    def apply_user_size(self, width: int, height: int) -> None:
        """Set the flyout to a user-chosen size (grip drag), keeping content."""
        m = self.SHADOW_RADIUS
        w = max(scaled_px(MIN_WIDTH_PX), int(width))
        h = max(scaled_px(MIN_HEIGHT_PX), int(height))
        try:
            self.resize(w, h)
            self.container.setGeometry(m, m, w - 2 * m, h - 2 * m)
            layout = self.container.layout()
            if layout is not None:
                layout.activate()
                # Grow (never shrink below the user's height) if the wrapped
                # content needs more room.
                try:
                    need = int(layout.heightForWidth(w - 2 * m)) + 2 * m
                except Exception:
                    need = 0
                if need > h:
                    h = need
                    self.resize(w, h)
                    self.container.setGeometry(m, m, w - 2 * m, h - 2 * m)
                    layout.activate()
        except Exception:
            pass
        self._user_size = (w, h)
        self._layout_grip()

    def _layout_grip(self) -> None:
        try:
            grip = self._grip
            grip.move(self.width() - grip.width() - 3, self.height() - grip.height() - 3)
            grip.raise_()
        except Exception:
            pass

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        self._layout_grip()

    def set_busy(self, busy: bool) -> None:
        try:
            self._edit.setReadOnly(bool(busy))
        except Exception:
            pass
        self._status.setText(self._busy_text if busy else "")
        self._relayout()

    def reshow(self, anchor: QWidget) -> None:
        """Re-show in place WITHOUT resetting the question/result pane.

        Used when a late answer arrives after the user dismissed the flyout —
        the answer must not vanish silently.
        """
        if anchor is None:
            return
        try:
            self.show_aligned(
                anchor,
                anchor_point="bottom-left",
                flyout_point="top-left",
                offset=scaled_px(8),
                animation="none",
                grab_focus=False,
            )
        except Exception:
            try:
                self.show_aligned(anchor, grab_focus=False)
            except Exception:
                pass

    def show_result(self, text: str, *, backend: str = "", cached: bool = False) -> None:
        badge = self._read_badge
        if backend:
            badge += f" · {backend}"
        if cached:
            badge += " · cached"
        self._result.setText(str(text or ""))
        self._status.setText(badge)
        self._relayout()

    def show_error(self, message: str) -> None:
        self._result.setText("")
        self._status.setText(str(message or self._error_text))
        self._relayout()

    def restore_focus_on_hide(self) -> bool:
        return False

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().hideEvent(event)
        try:
            self.closed.emit()
        except Exception:
            pass


__all__ = ["AskAiFlyout"]
