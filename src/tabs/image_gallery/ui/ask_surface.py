"""Ask AI surface — the one ask body shared by the flyout and the sidebar host.

The flyout used to BE the surface (a ``BaseFlyout`` with every row inline), so
there was nothing a tab-level panel could embed without forking it. This widget
is that body: title/scope, the question row (``CustomLineEdit`` on the toolkit
submit preset + include-images toggle), the live answer pane, the status badge,
the "N previous questions" line and a scrollable Q/A history list read from
``services.ask_log``.

Two hosts wrap the SAME instance (no second surface, no second flyout):

* ``ui/ask_ai.py::AskAiFlyout`` — the anchored ``BaseFlyout`` shell (positioning,
  fade, resize grip, saved size);
* ``ui/ask_sidebar.py::AskAiSidebar`` — the tab-level right-hand panel.

The surface is purely presentational: it never calls a backend and never writes
the log. The history list is seeded by ``ui/widget_parts/ask_ai_surface.py``
(``ask_log.recent``) and selecting an entry only re-displays the stored answer —
no API call. Advisory only: it renders text, it never mutates rank/selection.

Audit-Meta: pattern=state-machine size=exempt reason="one ask body: history selection, live-tail pane and status badge share a single widget lifecycle; splitting would fork the ask UI"
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRow,
    CustomLineEdit,
    IconListWidget,

    Text,
)
# `Label` left the public surface in text 2b; the class survives as a
# documented internal exception until the Text-capability tickets close.
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

from tabs.image_gallery.icons import Icon as GalleryIcon

#: Minimum surface width (the ask body must not collapse).
MIN_WIDTH_PX = 300
#: Fallback minimum height (scaled) used only if the layout cannot report its
#: own floor; the flyout shell tracks the real content layout instead.
MIN_HEIGHT_PX = 160
#: Design-px height of one history row (question line + answer line).
HISTORY_ROW_HEIGHT = 56
#: Answer characters shown on a history row; the full text is its tooltip.
HISTORY_ANSWER_CHARS = 180
#: How many stored exchanges the history list shows (bounded widgets).
HISTORY_LIMIT = 50

#: href scheme for an answer's image link. ``gallery-image:<percent-path>`` —
#: the surface emits ``imageActivated(path)`` when one is clicked.
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


def _one_line(text) -> str:  # type: ignore[no-untyped-def]
    """Collapse whitespace so one exchange fits a row's line."""
    try:
        return " ".join(str(text or "").split())
    except Exception:
        return ""


def _clip(text: str, limit: int = HISTORY_ANSWER_CHARS) -> str:
    """Bound a history row's answer text (full text stays in the tooltip)."""
    text = _one_line(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _make_history_list(parent: QWidget, row_factory) -> IconListWidget:  # type: ignore[no-untyped-def]
    """Build the scrollable history list (factory keeps the theme contract happy)."""
    return IconListWidget(
        parent,
        row_height=HISTORY_ROW_HEIGHT,
        button_factory=row_factory,
    )


class AskAiSurface(QWidget):
    """Question + live answer + scrollable Q/A history (host-agnostic)."""

    submitted = Signal(str)
    #: An answer image link was clicked — carries the item's path.
    imageActivated = Signal(str)
    #: The wrapped answer changed size; the flyout shell repositions on this.
    layoutRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._default_prompt = "What matters here?"
        # Localized chrome, injected by the controller / sidebar host (i18n).
        # Defaults are English so the surface is usable standalone.
        self._title_text = "Ask AI"
        self._busy_text = "Thinking…"
        self._read_badge = "AI read, unverified"
        self._error_text = "AI could not answer."
        self._cached_suffix = " · cached"
        self._history_text = "{n} previous questions"
        self._history_title_text = "History"
        self._history_empty_text = "No questions yet."
        # Currently-selected LLM from the tab's AI settings — shown in the
        # status badge instead of the raw backend token ("vlm"/"text").
        self._model = ""
        self._last_text = ""
        self._last_links: dict[str, str] = {}
        self._history_records: list[dict] = []
        self._history_syncing = False
        self._include_images = False

        root = QVBoxLayout(self)
        root.setContentsMargins(
            scaled_px(12), scaled_px(12), scaled_px(12), scaled_px(12)
        )
        root.setSpacing(scaled_px(8))

        self._title = Text(self._title_text, mode="plain", pixel_size=13, bold=True, parent=self)
        self._scope = Text("", mode="plain", pixel_size=16, parent=self)

        # Question row: a container so the navigation section can own the row
        # (edit + include-images toggle) as one unit.
        self.question_row = QWidget(self)
        self.question_row.setObjectName("gallery_ask_ai_question_row")
        edit_row = QHBoxLayout(self.question_row)
        edit_row.setContentsMargins(0, 0, 0, 0)
        edit_row.setSpacing(scaled_px(6))
        self._edit = CustomLineEdit(parent=self.question_row)
        self._edit.setPlaceholderText(self._default_prompt)
        self._edit.setMinimumWidth(scaled_px(300))
        try:
            self._edit.setClearButtonEnabled(True)
        except Exception:
            pass
        # Standard toolkit submit preset: Tab accepts the placeholder on an
        # empty field, Enter resolves text-or-placeholder via `submitted`.
        try:
            self._edit.setSubmitPreset(True)
        except Exception:
            pass
        self._edit.submitted.connect(self._on_field_submitted)
        self._images_toggle = Button(
            icon=(GalleryIcon.ASK_IMAGES_OFF, GalleryIcon.ASK_IMAGES),
            variant="ghost",
            toggle=True,
            # Design px — Button(size=...) scales internally (no scaled_px).
            size=(28, 28),
            parent=self.question_row,
        )
        self._images_toggle.setObjectName("gallery_ask_ai_images_toggle")
        self._images_hint = ""
        self._images_downsample = ""
        try:
            self._images_toggle.setChecked(False)
            self._images_toggle.clicked.connect(self._on_images_toggled)
        except Exception:
            pass
        edit_row.addWidget(self._edit, 1)
        edit_row.addWidget(self._images_toggle, 0)

        self._result = Label("", pixel_size=16, word_wrap=True, parent=self)
        self._result.setMinimumWidth(scaled_px(MIN_WIDTH_PX - 40))
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

        self._status = Text("", mode="plain", pixel_size=16, parent=self)
        # Legacy count-only affordance ("N previous questions") — kept beside
        # the list so the persisted log stays observable at a glance.
        self._history_count = 0
        self._history = Text("", mode="plain", pixel_size=14, parent=self)

        # History block: title + scrollable list (one two-line row per
        # exchange) + empty state. Hidden while there is nothing to show.
        self._history_title = Text(
            self._history_title_text, mode="plain", pixel_size=12, bold=True, parent=self
        )
        self._history_title.setObjectName("gallery_ask_ai_history_title")
        self._history_list = _make_history_list(self, self._history_row_button)
        self._history_list.setObjectName("gallery_ask_ai_history")
        try:
            self._history_list.setMaximumHeight(scaled_px(220))
        except Exception:
            pass
        self._history_empty = Text(
            self._history_empty_text, mode="plain", pixel_size=14, parent=self
        )
        self._history_empty.setObjectName("gallery_ask_ai_history_empty")
        try:
            self._history_list.currentRowChanged.connect(self._on_history_row_changed)
        except Exception:
            pass

        root.addWidget(self._title)
        root.addWidget(self._scope)
        root.addWidget(self.question_row)
        root.addWidget(self._result)
        root.addWidget(self._status)
        root.addWidget(self._history)
        root.addWidget(self._history_title)
        root.addWidget(self._history_list)
        root.addWidget(self._history_empty)

        self._sync_row_visibility()

    # -- question row -------------------------------------------------------

    def _on_field_submitted(self, question: str) -> None:
        """Preset submit path: the field resolved text-or-placeholder."""
        try:
            resolved = str(question or "").strip() or self._default_prompt
        except Exception:
            resolved = self._default_prompt
        self._submit_question(resolved)

    def emit_submit(self) -> None:
        """Fallback submit path (host Enter): resolve the text here."""
        try:
            question = self._edit.text().strip() or self._default_prompt
        except Exception:
            question = self._default_prompt
        self._submit_question(question)

    def _submit_question(self, question: str) -> None:
        # Guard against a double submit when both the field's submitted and
        # the host's Enter handler see the same Return.
        import time

        now = time.monotonic()
        if now - getattr(self, "_last_submit_at", 0.0) < 0.4:
            return
        self._last_submit_at = now
        # Enter must send-and-release: drop any selection left by the Tab
        # prefill and take focus off the field.
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

    def focus_question(self) -> None:
        """Put the caret in the question field (host open path)."""
        try:
            self._edit.setFocus()
        except Exception:
            pass

    def set_title_visible(self, visible: bool) -> None:
        """Show/hide the surface's own title (the sidebar header labels it)."""
        try:
            self._title.setVisible(bool(visible))
        except Exception:
            pass

    # -- localized chrome ---------------------------------------------------

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
        cached: str | None = None,
        history: str | None = None,
        history_title: str | None = None,
        history_empty: str | None = None,
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
        if cached is not None:
            self._cached_suffix = str(cached)
        if history is not None:
            self._history_text = str(history)
            self._render_history()
        if history_title is not None:
            self._history_title_text = str(history_title)
            try:
                self._history_title.setText(self._history_title_text)
            except Exception:
                pass
        if history_empty is not None:
            self._history_empty_text = str(history_empty)
            try:
                self._history_empty.setText(self._history_empty_text)
            except Exception:
                pass
        if images_hint is not None or images_downsample is not None:
            if images_hint is not None:
                self._images_hint = str(images_hint)
            if images_downsample is not None:
                self._images_downsample = str(images_downsample)
            self.set_images_tooltip(
                "\n".join(s for s in (self._images_hint, self._images_downsample) if s)
            )
        self._sync_row_visibility()

    def set_images_tooltip(self, text: str) -> None:
        """Tooltip of the include-images toggle (two lines: meaning + downscale)."""
        self._images_toggle.setToolTip(str(text or ""))

    # -- scope lifecycle (called by the host before showing) ----------------

    def prepare_scope(
        self,
        *,
        scope_label: str = "",
        default_prompt: str = "What matters here?",
        title: str = "",
        initial_result=None,  # type: ignore[no-untyped-def]
        initial_error: str = "",
        initial_links: dict | None = None,
        show_images_toggle: bool = True,
        history_count: int | None = None,
        history_records: list | None = None,
    ) -> None:
        """Reset for one scope; seed the persisted answer/history BEFORE a show.

        ``initial_result``/``initial_error`` seed the pane before the host's
        show animation starts (setting them after the show clears the fade
        snapshot and flashes the panel white).
        """
        self._default_prompt = str(default_prompt or "What matters here?")
        self._title.setText(str(title or self._title_text))
        scope_text = str(scope_label or "")
        self._scope.setText(scope_text)
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
        self._history_count = 0
        self._history.setText("")
        if history_count is not None:
            self._history_count = max(0, int(history_count))
        if history_records is not None:
            # A stored answer for the same scope wins over the newest record;
            # otherwise the pane opens on the tail (newest) exchange.
            self.set_history_records(
                history_records,
                show_tail=initial_result is None and not initial_error,
            )
        # Restore the include-images toggle the user left on last time.
        saved_images = bool(getattr(self, "_saved_include_images", False))
        try:
            self._images_toggle.setChecked(saved_images)
        except Exception:
            pass
        self._include_images = saved_images
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
        self._render_history()
        self._sync_row_visibility()
        self.focus_question()

    # -- history ------------------------------------------------------------

    def has_answer(self) -> bool:
        """True when the live pane currently carries answer text."""
        return bool(str(self._last_text or ""))

    def set_history_records(
        self,
        records,  # type: ignore[no-untyped-def]
        *,
        show_tail: bool = False,
        highlight_tail: bool = False,
    ) -> None:
        """Render the stored exchanges, oldest → newest (``recent()`` is newest-first).

        ``show_tail=True`` selects the newest row and displays its answer in the
        pane — the live/tail view when no fresher answer exists. ``highlight_tail``
        only parks the list cursor on the newest row: the live pane keeps the
        answer it already shows (a just-arrived answer carries image links the
        stored record does not).
        """
        rows: list[dict] = []
        try:
            rows = [dict(r) for r in (records or []) if isinstance(r, dict)]
        except Exception:
            rows = []
        rows.reverse()
        # Bound the number of live row widgets (the log itself is bounded too).
        rows = rows[-HISTORY_LIMIT:]
        self._history_records = rows
        self._history_syncing = True
        try:
            self._history_list.clear()
            for record in rows:
                self._history_list.add_item(
                    str(record.get("question") or "—"),
                    data=record,
                    row_height=HISTORY_ROW_HEIGHT,
                )
        except Exception:
            self._history_records = []
        finally:
            self._history_syncing = False
        self._sync_row_visibility()
        if rows and show_tail:
            self.select_history(len(rows) - 1)
        elif rows and highlight_tail:
            self._select_row_silent(len(rows) - 1)

    def _select_row_silent(self, index: int) -> None:
        """Highlight a row without re-displaying its answer."""
        self._history_syncing = True
        try:
            self._history_list.setCurrentRow(index)
        except Exception:
            pass
        finally:
            self._history_syncing = False

    def history_row_buttons(self) -> list:
        """The live history row buttons, oldest → newest (navigation rows)."""
        buttons = []
        try:
            for index in range(int(self._history_list.count())):
                button = self._history_list.row_button(index)
                if button is not None:
                    buttons.append(button)
        except Exception:
            return []
        return buttons

    def select_history(self, index: int) -> None:
        """Select one stored exchange and show its answer (no API call)."""
        try:
            index = int(index)
        except Exception:
            return
        if index < 0 or index >= len(self._history_records):
            return
        self._history_syncing = True
        try:
            self._history_list.setCurrentRow(index)
        except Exception:
            pass
        finally:
            self._history_syncing = False
        self._show_history_answer(index)

    def selected_history_index(self) -> int:
        """Index of the selected exchange (``-1`` when none)."""
        try:
            return int(self._history_list.currentRow())
        except Exception:
            return -1

    def _on_history_row_changed(self, row) -> None:  # type: ignore[no-untyped-def]
        if self._history_syncing:
            return
        try:
            index = int(row)
        except Exception:
            return
        self._show_history_answer(index)

    def _show_history_answer(self, index: int) -> None:
        if index < 0 or index >= len(self._history_records):
            return
        record = self._history_records[index]
        backend = record.get("backend")
        model = ""
        if isinstance(backend, dict):
            model = str(backend.get("model") or "")
        self._set_answer(
            str(record.get("answer") or ""),
            model=model,
            cached=bool(record.get("cache_hit", False)),
            links=None,
        )

    def _history_row_button(self, spec) -> Button:  # type: ignore[no-untyped-def]
        """One history row: the question line above its answer line.

        The toolkit ``Button(rows=...)`` keeps both lines in one focusable,
        clickable, keyboard-activatable row — the same visual language as the
        sidebar nav rows, without a bespoke row widget.
        """
        record = spec.data if isinstance(spec.data, dict) else {}
        question = _one_line(record.get("question") or spec.text) or "—"
        answer = _clip(record.get("answer") or "")
        button = Button(
            rows=[
                ButtonRow(
                    question,
                    size=12,
                    weight="bold",
                    ratio=0.42,
                    elide=True,
                    h_align=Qt.AlignmentFlag.AlignLeft,
                ),
                ButtonRow(
                    answer or "—",
                    size=11,
                    ratio=0.58,
                    elide=True,
                    h_align=Qt.AlignmentFlag.AlignLeft,
                ),
            ],
            variant="sidebar_nav",
            toggle=False,
            size=(0, int(getattr(spec, "row_height", HISTORY_ROW_HEIGHT) or HISTORY_ROW_HEIGHT)),
            corner_radius=6,
            content_align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            content_padding=(scaled_px(8), 0.0, scaled_px(8), 0.0),
            parent=self._history_list,
        )
        full = f"{question}\n\n{_one_line(record.get('answer') or '')}"
        try:
            button.setToolTip(full.strip())
        except Exception:
            pass
        return button

    def set_history_count(self, count: int) -> None:
        """Show ``"N previous questions"`` for the persisted Q/A log (0 hides)."""
        try:
            self._history_count = max(0, int(count))
        except Exception:
            self._history_count = 0
        self._render_history()
        self.layoutRequested.emit()

    def _render_history(self) -> None:
        """Paint the legacy count line from ``_history_text`` + the current count."""
        count = max(0, int(getattr(self, "_history_count", 0) or 0))
        text = ""
        if count > 0:
            template = str(getattr(self, "_history_text", "") or "")
            text = template.replace("{n}", str(count)) if template else ""
            if not text:
                text = f"{count} previous questions"
        try:
            self._history.setText(text)
        except Exception:
            pass
        self._sync_row_visibility()

    # -- answer pane --------------------------------------------------------

    def show_result(
        self,
        text: str,
        *,
        model: str = "",
        backend: str = "",
        cached: bool = False,
        links: dict | None = None,
    ) -> None:
        self._set_answer(text, model=model, backend=backend, cached=cached, links=links)

    def _set_answer(
        self,
        text: str,
        *,
        model: str = "",
        backend: str = "",
        cached: bool = False,
        links: dict | None = None,
    ) -> None:
        badge = self._read_badge
        label = (
            str(model or "")
            or str(getattr(self, "_model", "") or "")
            or str(backend or "")
        )
        if label:
            badge += f" · {label}"
        if cached:
            badge += str(getattr(self, "_cached_suffix", " · cached") or "")
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
        self.layoutRequested.emit()

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
        """Escape the answer and wrap every item name in an accent link."""
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
        parts.sort(key=len, reverse=True)
        try:
            pattern = _re.compile("|".join(parts), _re.IGNORECASE)
        except _re.error:
            return escaped
        accent = _accent_hex()

        def _repl(match) -> str:  # type: ignore[no-untyped-def]
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

    def set_busy(self, busy: bool) -> None:
        try:
            self._edit.setReadOnly(bool(busy))
        except Exception:
            pass
        self._status.setText(self._busy_text if busy else "")
        self._sync_row_visibility()
        self.layoutRequested.emit()

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
        self.layoutRequested.emit()

    def _sync_row_visibility(self) -> None:
        """Collapse rows that carry no text (and the list when it is empty).

        An empty row must not reserve height: the flyout floor tracks the
        layout, so a blank pane would otherwise keep the surface tall with dead
        space under the question field.
        """
        has_history = bool(self._history_records)
        for label in (self._result, self._status, self._history, self._history_empty):
            try:
                label.setVisible(bool(label.text()))
            except Exception:
                pass
        for label in (self._history_title,):
            try:
                label.setVisible(bool(has_history and label.text()))
            except Exception:
                pass
        try:
            self._history_list.setVisible(has_history)
        except Exception:
            pass
        try:
            self._history_empty.setVisible(bool(self._history_empty.text()) and not has_history)
        except Exception:
            pass

    # -- draft persistence --------------------------------------------------

    def persist_draft(self) -> None:
        """Keep the user's draft + include-images toggle across hide/reopen."""
        try:
            self._saved_text = self._edit.text()
        except Exception:
            pass
        try:
            self._saved_include_images = bool(self._images_toggle.isChecked())
        except Exception:
            pass


__all__ = [
    "AskAiSurface",
    "HISTORY_ANSWER_CHARS",
    "HISTORY_LIMIT",
    "HISTORY_ROW_HEIGHT",
    "IMAGE_HREF_SCHEME",
    "MIN_HEIGHT_PX",
    "MIN_WIDTH_PX",
]
