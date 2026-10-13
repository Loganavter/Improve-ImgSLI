"""Ask AI flyout (A3) — one scope-aware ask surface.
Audit-Meta: pattern=single-surface size=exempt reason="one scope-aware ask flyout — its fade/persist/menu/status state is one cohesive surface; splitting would scatter the flyout lifecycle"

A toolkit ``BaseFlyout`` with a ``CustomLineEdit`` on the toolkit submit
preset (pre-filled, overridable default prompt: ``Tab`` accepts it,
``Enter`` sends) and a result pane marked
"AI read, unverified". Advisory only: the flyout renders text, it never
mutates rank/selection/store. All async work is dispatched by the controller
(``GalleryController.ask_ai_question``); this widget is pure surface.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import BaseFlyout, Button, CustomLineEdit, Label

from tabs.image_gallery.icons import Icon as GalleryIcon
from tabs.image_gallery.ui.ask_ai_grip import AskAiResizeGrip

#: Minimum flyout width (the ask surface must not collapse).
MIN_WIDTH_PX = 300
#: Fallback minimum height (scaled) used only if the layout cannot report its
#: own floor; the real minimum tracks the content layout (see _min_height).
MIN_HEIGHT_PX = 160

#: href scheme for an answer's image link. ``gallery-image:<percent-path>`` —
#: the flyout emits ``imageActivated(path)`` when one is clicked.
IMAGE_HREF_SCHEME = "gallery-image:"

def _accent_hex() -> str:
    """The app's blue accent as a hex string (theme token → light/dark fallback)."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        color = try_resolve_theme_color(ThemeManager.get_instance(), "accent")
        if color is not None:
            from PySide6.QtGui import QColor

            q = QColor(color) if not isinstance(color, QColor) else color
            if q.isValid():
                return q.name()
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.card.dots import _is_dark

        return "#0096FF" if _is_dark() else "#0078D4"
    except Exception:
        return "#0096FF"
class AskAiFlyout(BaseFlyout):
    """Free-form question + AI result, anchored to a card or series header."""

    flyout_group = "gallery_ask_ai"
    # Sequenced cycle: if another flyout is still fading out, wait for it to
    # finish before this one opens (FlyoutManager deferral) — no overlapping
    # fades.
    wait_for_close_before_show = True

    submitted = Signal(str)
    closed = Signal()
    #: An answer image link was clicked — carries the item's path. The host
    #: opens Quick Look for it.
    imageActivated = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._default_prompt = "What matters here?"
        # Localized chrome, injected by the controller (i18n). Defaults are
        # English so the widget is usable standalone (tests/toolkit preview).
        self._title_text = "Ask AI"
        self._busy_text = "Thinking…"
        self._read_badge = "AI read, unverified"
        self._error_text = "AI could not answer."
        # Currently-selected LLM from the tab's AI settings — shown in the
        # status badge instead of the raw backend token ("vlm"/"text").
        self._model = ""
        self.content_layout.setContentsMargins(
            scaled_px(12), scaled_px(12), scaled_px(12), scaled_px(12)
        )
        self.content_layout.setSpacing(scaled_px(8))

        self._title = Label(self._title_text, pixel_size=13, bold=True, parent=self)
        self._scope = Label("", pixel_size=16, parent=self)
        self._edit = CustomLineEdit(parent=self)
        self._edit.setPlaceholderText(self._default_prompt)
        self._edit.setMinimumWidth(scaled_px(300))
        try:
            self._edit.setClearButtonEnabled(True)
        except Exception:
            pass
        # Standard toolkit submit preset: Tab accepts the placeholder on an
        # empty field, Enter resolves text-or-placeholder via `submitted`.
        # (The flyout-level keyPressEvent Enter fallback below stays: the
        # toolkit nav section does not always deliver Return to the focused
        # field in the live window.)
        try:
            self._edit.setSubmitPreset(True)
        except Exception:
            pass
        self._edit.submitted.connect(self._on_field_submitted)
        # Include-images toggle (plan: Ask AI carries AI output for now). Off by
        # default = metrics only (a crossed-out image); on = send the images.
        self._include_images = False
        self._images_toggle = Button(
            icon=(GalleryIcon.ASK_IMAGES_OFF, GalleryIcon.ASK_IMAGES),
            variant="ghost",
            toggle=True,
            size=(scaled_px(28), scaled_px(28)),
            parent=self,
        )
        self._images_toggle.setObjectName("gallery_ask_ai_images_toggle")
        self._images_hint = ""
        self._images_downsample = ""
        try:
            self._images_toggle.setChecked(False)
            self._images_toggle.clicked.connect(self._on_images_toggled)
        except Exception:
            pass
        self._result = Label("", pixel_size=16, word_wrap=True, parent=self)
        self._result.setMinimumWidth(scaled_px(MIN_WIDTH_PX - 40))
        # Selectable answer text + clickable image links: the answer names its
        # variants, and each name opens that image (Quick Look). Links get the
        # app accent + underline + a pointing-hand cursor from Qt's rich text.
        self._last_text: str = ""
        self._last_links: dict[str, str] = {}
        try:
            self._result.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
                | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
        except Exception:
            pass
        try:
            self._result.linkActivated.connect(self._on_result_link)
        except Exception:
            pass
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed_links)
        except Exception:
            pass
        self._status = Label("", pixel_size=16, parent=self)
        # Title, scope, then the question row (edit + images toggle).
        self.content_layout.addWidget(self._title)
        self.content_layout.addWidget(self._scope)
        try:
            edit_row = QHBoxLayout()
            edit_row.setContentsMargins(0, 0, 0, 0)
            edit_row.setSpacing(scaled_px(6))
            edit_row.addWidget(self._edit, 1)
            edit_row.addWidget(self._images_toggle, 0)
            self.content_layout.addLayout(edit_row)
        except Exception:
            self.content_layout.addWidget(self._edit)
        self.content_layout.addWidget(self._result)
        self.content_layout.addWidget(self._status)

        # Empty result/status rows reserve no height (see _sync_row_visibility).
        self._sync_row_visibility()

        # User resize support (toolkit flyouts auto-size only).
        self._user_size: tuple[int, int] | None = None
        try:
            self.setMinimumSize(scaled_px(MIN_WIDTH_PX), self._min_height())
        except Exception:
            pass
        self._grip = AskAiResizeGrip(self)

    # -- interaction --------------------------------------------------------

    def _on_field_submitted(self, question: str) -> None:
        """Preset submit path: the field resolved text-or-placeholder."""
        try:
            resolved = str(question or "").strip() or self._default_prompt
        except Exception:
            resolved = self._default_prompt
        self._submit_question(resolved)

    def _emit_submit(self) -> None:
        """Fallback submit path (flyout-level Enter): resolve the text here."""
        try:
            question = self._edit.text().strip() or self._default_prompt
        except Exception:
            question = self._default_prompt
        self._submit_question(question)

    def _submit_question(self, question: str) -> None:
        # Guard against a double submit when both the field's submitted and
        # this flyout's keyPressEvent see the same Return.
        import time

        now = time.monotonic()
        if now - getattr(self, "_last_submit_at", 0.0) < 0.4:
            return
        self._last_submit_at = now
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

    def _on_images_toggled(self) -> None:
        try:
            self._include_images = bool(self._images_toggle.isChecked())
        except Exception:
            self._include_images = False

    def include_images(self) -> bool:
        """Whether the question should carry the images (VLM) or metrics only."""
        try:
            return bool(self._images_toggle.isChecked())
        except Exception:
            return bool(getattr(self, "_include_images", False))

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
        images_hint: str | None = None,
        images_downsample: str | None = None,
        model: str | None = None,
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
        if model is not None:
            self._model = str(model or "")
        if images_hint is not None or images_downsample is not None:
            if images_hint is not None:
                self._images_hint = str(images_hint)
            if images_downsample is not None:
                self._images_downsample = str(images_downsample)
            self.set_images_tooltip(
                "\n".join(s for s in (self._images_hint, self._images_downsample) if s)
            )

    def set_images_tooltip(self, text: str) -> None:
        """Tooltip of the include-images toggle (two lines: meaning + downscale)."""
        self._images_toggle.setToolTip(str(text or ""))

    def open_for(
        self,
        anchor: QWidget,
        *,
        scope_label: str = "",
        default_prompt: str = "What matters here?",
        title: str = "",
        initial_result=None,
        initial_error: str = "",
        initial_links: dict | None = None,
        grow_up: bool = False,
        show_images_toggle: bool = True,
    ) -> None:
        """Reset + show under *anchor*; focus lands in the question field.

        ``initial_result``/``initial_error`` seed the pane BEFORE the show
        animation starts (the persisted-answer prefill). Setting them after
        the show — via ``reposition()`` — would clear the fade snapshot while
        its animation is still running, flashing the panel white.

        ``show_images_toggle=False`` hides the include-images toggle (region
        scope: the images always go out, so there is nothing to toggle).
        """
        self._default_prompt = str(default_prompt or "What matters here?")
        self._title.setText(str(title or self._title_text))
        scope_text = str(scope_label or "")
        self._scope.setText(scope_text)
        # No scope line = no empty row (series scope has no label at all).
        try:
            self._scope.setVisible(bool(scope_text))
        except Exception:
            pass
        self._edit.setText(str(getattr(self, "_saved_text", "") or ""))
        self._edit.setPlaceholderText(self._default_prompt)
        self._edit.setReadOnly(False)
        self._last_text = ""
        self._last_links = {}
        try:
            self._result.setTextFormat(Qt.TextFormat.PlainText)
        except Exception:
            pass
        self._result.setText("")
        self._status.setText("")
        # Restore the include-images toggle the user left on last time (saved
        # on hide) instead of forcing it back off on every open.
        saved_images = bool(getattr(self, "_saved_include_images", False))
        try:
            self._images_toggle.setChecked(saved_images)
        except Exception:
            pass
        self._include_images = saved_images
        self._sync_row_visibility()
        # Region scope always sends the images: no toggle to show.
        try:
            self._images_toggle.setVisible(bool(show_images_toggle))
        except Exception:
            pass
        if initial_result is not None:
            self.show_result(
                getattr(initial_result, "text", "") or "",
                backend=getattr(initial_result, "backend", "") or "",
                cached=bool(getattr(initial_result, "cached", False)),
                links=initial_links,
            )
        elif initial_error:
            self.show_error(initial_error)
        try:
            self._edit.setFocus()
        except Exception:
            pass
        # A remembered manual size must land on the FIRST frame: pin the
        # flyout's minimum to it so show_aligned()'s adjustSize() cannot
        # collapse it to the min-content size for the fade-in and then jump
        # once _relayout applies the saved size after the animation. The
        # post-animation _relayout still re-applies it (and may grow for
        # content); this only removes the min-size first frame.
        saved_size = getattr(self, "_user_size", None)
        if saved_size is not None:
            try:
                self.setMinimumSize(int(saved_size[0]), int(saved_size[1]))
            except Exception:
                pass
        try:
            # ``grow_up`` pins the flyout's BOTTOM-CENTER to the anchor's
            # TOP-CENTER so a taller wrapped result expands upward (the
            # region-inspection flyout above the held selection); the
            # default grows downward from the anchor's bottom-left.
            anchor_point = "top-center" if grow_up else "bottom-left"
            flyout_point = "bottom-center" if grow_up else "top-left"
            self._grow_up = bool(grow_up)
            self.show_aligned(
                anchor,
                anchor_point=anchor_point,
                flyout_point=flyout_point,
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

    def _min_height(self) -> int:
        """Minimum shell height the content layout actually needs (+ shadow).

        Tracks the layout floor instead of the fixed ``MIN_HEIGHT_PX``
        constant so the ask surface can never be shrunk below what its rows
        require — under it the wrapped result/status rows clip or overlap.
        Falls back to the constant when the layout cannot report a floor.
        """
        m = self.SHADOW_RADIUS
        try:
            layout = self.container.layout()
            if layout is not None:
                layout.activate()
                need = int(layout.minimumSize().height()) + 2 * m
                if need > 2 * m:
                    return need
        except Exception:
            pass
        return scaled_px(MIN_HEIGHT_PX)

    def _sync_row_visibility(self) -> None:
        """Collapse the result/status rows when they carry no text.

        An empty row must not reserve height: the flyout floor tracks the
        layout (see ``_min_height``), so a blank pane would otherwise keep the
        surface tall with dead space under the question field. The scope line
        is handled the same way in :meth:`open_for`.
        """
        for label in (self._result, self._status):
            try:
                label.setVisible(bool(label.text()))
            except Exception:
                pass

    def apply_user_size(self, width: int, height: int) -> None:
        """Set the flyout to a user-chosen size (grip drag), keeping content."""
        m = self.SHADOW_RADIUS
        w = max(scaled_px(MIN_WIDTH_PX), int(width))
        h = max(self._min_height(), int(height))
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
        self._sync_row_visibility()
        self._relayout()

    def reshow(self, anchor: QWidget) -> None:
        """Re-show in place WITHOUT resetting the question/result pane.

        Used when a late answer arrives after the user dismissed the flyout —
        the answer must not vanish silently.
        """
        if anchor is None:
            return
        try:
            grow_up = bool(getattr(self, "_grow_up", False))
            self.show_aligned(
                anchor,
                anchor_point="top-center" if grow_up else "bottom-left",
                flyout_point="bottom-center" if grow_up else "top-left",
                offset=scaled_px(8),
                animation="none",
                grab_focus=False,
            )
        except Exception:
            try:
                self.show_aligned(anchor, grab_focus=False)
            except Exception:
                pass

    def show_result(self, text: str, *, model: str = "", backend: str = "", cached: bool = False, links: dict | None = None) -> None:
        badge = self._read_badge
        # Show the currently-selected LLM (settings), never the raw backend
        # token ("vlm"/"text"); fall back to the backend only when no model is
        # configured.
        label = str(model or "") or str(getattr(self, "_model", "") or "") or str(backend or "")
        if label:
            badge += f" · {label}"
        if cached:
            badge += " · cached"
        self._last_text = str(text or "")
        try:
            self._last_links = {
                str(k): str(v) for k, v in dict(links or {}).items() if k and v
            }
        except Exception:
            self._last_links = {}
        self._render_result()
        self._status.setText(badge)
        self._sync_row_visibility()
        self._relayout()

    def _render_result(self) -> None:
        """Paint the answer: rich text with image links, or plain text."""
        text = str(getattr(self, "_last_text", "") or "")
        links = dict(getattr(self, "_last_links", None) or {})
        try:
            if links:
                self._result.setTextFormat(Qt.TextFormat.RichText)
                self._result.setText(self._render_links(text, links))
            else:
                self._result.setTextFormat(Qt.TextFormat.PlainText)
                self._result.setText(text)
        except Exception:
            try:
                self._result.setText(text)
            except Exception:
                pass

    def _render_links(self, text: str, links: dict) -> str:
        """Escape the answer and wrap every item name in an accent link.

        Names are matched longest-first, case-insensitively, over the HTML-escaped
        text so an ``<a>`` is never nested inside another (one regex pass, not
        sequential substitutions).
        """
        import html as _html
        import re as _re
        from urllib.parse import quote

        raw = str(text or "")
        escaped = _html.escape(raw)
        names = [(str(k), str(v)) for k, v in dict(links or {}).items() if k and v]
        if not raw or not names:
            return escaped
        lookup: dict[str, str] = {}
        parts: list[str] = []
        for name, path in names:
            esc = _html.escape(name)
            if not esc:
                continue
            lookup.setdefault(esc.lower(), path)
            parts.append(_re.escape(esc))
        if not parts:
            return escaped
        # Longest display name first so the alternation prefers the fuller match.
        parts.sort(key=len, reverse=True)
        try:
            pattern = _re.compile("|".join(parts), _re.IGNORECASE)
        except _re.error:
            return escaped
        accent = _accent_hex()

        def _repl(match) -> str:
            token = match.group(0)
            path = lookup.get(token.lower())
            if not path:
                return token
            href = f"{IMAGE_HREF_SCHEME}{quote(path)}"
            return (
                f'<a href="{href}" style="color:{accent}; '
                f'text-decoration:underline;">{token}</a>'
            )

        return pattern.sub(_repl, escaped)

    def _on_result_link(self, href: str) -> None:
        """A link in the answer was activated → open that image (host side)."""
        path = self._href_to_path(href)
        if not path:
            return
        try:
            self.imageActivated.emit(path)
        except Exception:
            pass

    @staticmethod
    def _href_to_path(href: str) -> str:
        from urllib.parse import unquote

        try:
            s = str(href or "")
        except Exception:
            return ""
        if not s.startswith(IMAGE_HREF_SCHEME):
            return ""
        try:
            return unquote(s[len(IMAGE_HREF_SCHEME):])
        except Exception:
            return ""

    def _on_theme_changed_links(self, *_args) -> None:
        """Re-render links so the accent follows a live theme flip."""
        try:
            if getattr(self, "_last_links", None):
                self._render_result()
        except Exception:
            pass

    def show_error(self, message: str) -> None:
        self._last_text = ""
        self._last_links = {}
        try:
            self._result.setTextFormat(Qt.TextFormat.PlainText)
        except Exception:
            pass
        self._result.setText("")
        self._status.setText(str(message or self._error_text))
        self._sync_row_visibility()
        self._relayout()

    def restore_focus_on_hide(self) -> bool:
        return False

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().hideEvent(event)
        # Persist the user's draft + include-images toggle across hide/reopen
        # (auto-dismiss on outside click must not lose what was typed).
        try:
            self._saved_text = self._edit.text()
        except Exception:
            pass
        try:
            self._saved_include_images = bool(self._images_toggle.isChecked())
        except Exception:
            pass
        try:
            self.closed.emit()
        except Exception:
            pass


__all__ = ["AskAiFlyout"]
