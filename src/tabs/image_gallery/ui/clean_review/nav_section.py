"""Clean Review (S3) keyboard navigation — three real rows, modal edge.

The overlay is a navigation **section** while it is visible, and the section is
a ``ToolbarRowsSection`` (``sli_ui_toolkit/ui/managers/navigation_sections.py``)
over the three rows the overlay already has, in visual top-to-bottom order:

============  =========================================================
row           controls (``owns`` = the row container)
============  =========================================================
header        close button (objectName clean_review_close, the header's
              only focusable control, so the row *is* that button —
              title/subtitle carry no focus; no inert container)
item strip    per-item Restore buttons (objectName clean_review_restore)
              and the informational more tile (clean_review_filmstrip_more)
action bar    Restore all, Cancel and Move (clean_review_restore_all,
              clean_review_cancel, clean_review_move)
============  =========================================================

``↑``/``↓`` cross rows, ``←``/``→`` step inside the current row (the toolkit
section's own row-local step), and Enter/Space are never claimed here — the
focused toolkit ``Button`` activates itself
(``widgets/buttons/events.py::_activate_via_keyboard`` → the same ``clicked``
path a mouse click takes). At the first/last row the vertical edge **wraps
inside the overlay** (``↑`` on the header hands the ring to the action bar,
``↓`` on the action bar back to the header) instead of yielding: a modal must
not walk the ring onto the gallery grid behind the veil. The toolkit
``NavigationManager``'s modal-edge consume stays the safety net for anything
the wrap does not claim.

The strip is rebuilt by ``populate.py`` on every repopulate (per-item
``↩ Restore``, a triage flip, a reopen), so :func:`rows` re-reads the current
containers on every call — it never caches a widget list. A rebuild that drops
the focused widget hands the ring back to the strip
(:func:`restore_after_rebuild`).

``extra_keys`` stays empty on purpose: ``←``/``→`` are not intercepted by the
manager and are re-delivered to the section by the overlay's own
``keyPressEvent``. That is the same row step — the section is still the single
owner — and it keeps the legacy modal contract (the manager only sees arrows,
Tab/Backtab and ``extra_keys`` for this section).

Register/unregister ride the overlay's show/close lifecycle
(``clean_review/__init__.py``: registration at the end of ``show_for`` after
``show_overlay()``; unregistration first thing in every close path — ``hide``,
``hideEvent``, ``closeEvent``). Both are idempotent and fail-open. The close
path hands the ring back to the widget that opened S3
(:func:`remember_opener` / :func:`restore_opener_focus`, the Quick Look
``focus_restore`` idiom), so a keyboard reader does not land back at the
window's first focusable widget.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection
from sli_ui_toolkit.ui.managers.nav_graph import focus_reason

#: Overlay attribute holding the registered section (idempotent register).
SECTION_ATTR = "_clean_review_nav_section"

#: Overlay attribute holding the widget that opened S3 (return-focus half).
OPENER_ATTR = "_clean_review_opener"

#: Overlay attribute disarming the return-focus until the next open.
RESTORED_ATTR = "_clean_review_focus_restored"


def rows(overlay) -> list:
    """The overlay's navigable rows, top to bottom — re-read, never cached.

    ``_strip_row`` is replaced by every ``populate`` (the old strip is
    destroyed), so a cached list would point at deleted widgets after the
    first per-item restore.
    """
    return [
        getattr(overlay, "_close_btn", None),
        getattr(overlay, "_strip_row", None),
        getattr(overlay, "_action_bar", None),
    ]


def focused_widget(overlay):
    """The focus widget of the overlay's window, or ``None``.

    ``QApplication.focusWidget()`` reports ``None`` while the window is not
    OS-active (the control channel drives the app that way), so ask the
    overlay's own window first — the Quick Look ``focused_widget`` idiom.
    """
    try:
        focused = overlay.focusWidget()
        if focused is not None:
            return focused
    except Exception:
        pass
    try:
        return QApplication.focusWidget()
    except Exception:
        return None


class CleanReviewNavSection(ToolbarRowsSection):
    """S3's header / strip / action rows as a modal toolkit row section.

    The control table lives in the module docstring. Everything key-related is
    the toolkit section's (row containers in visual order, ``←``/``→`` inside a
    row, ``↓``/``↑`` between rows, focus reason through the app's policy);
    this subclass adds only the modal wrap at the vertical edges and keeps the
    whole overlay subtree ``owns``-ed so the manager's ceiling never hands a
    key or the focus to a widget behind the veil.
    """

    def __init__(self, overlay: QWidget) -> None:
        super().__init__(lambda: rows(overlay), tag="clean-review")
        self._overlay = overlay

    @property
    def modal(self) -> bool:
        """The overlay owns the keyboard for its window while it is visible.

        Read by the manager via ``getattr(spec, "modal", False)`` (the same raw
        read as ``extra_keys``) — must stay a property, never a method.
        """
        return True

    @property
    def extra_keys(self) -> frozenset:
        """Deliberately empty: ``←``/``→`` reach the row step natively.

        The manager leaves horizontal arrows to the focused widget unless a
        section opts in; the overlay's ``keyPressEvent`` re-delivers them to
        :meth:`navigate`, so the section is still the single row owner. The
        Escape key is not claimed either — it must keep closing the overlay.
        """
        return frozenset()

    def owns(self, widget) -> bool:  # noqa: ANN001 (duck-typed section protocol)
        """The whole overlay subtree belongs to the section.

        Wider than the three rows on purpose: the overlay itself is the
        ceiling owner, so a ring left on it (or on a non-focusable part of the
        veil) is still "inside" for the manager and can never resolve as a
        neighbour's widget.
        """
        try:
            return bool(widget is self._overlay or self._overlay.isAncestorOf(widget))
        except Exception:
            return False

    def navigate(self, key: int, widget) -> bool:  # noqa: ANN001
        """Row navigation, with the modal vertical edges wrapping inside S3."""
        if super().navigate(key, widget):
            return True
        # Only a widget already inside one of the rows may wrap; a bare
        # overlay/veil key stays declined (the manager consumes it at the
        # modal edge when it is an arrow).
        if self._row_of(widget) is None:
            return False
        if key == Qt.Key.Key_Up:
            return self.focus_last(reason=focus_reason())
        if key == Qt.Key.Key_Down:
            return self.focus_first(reason=focus_reason())
        return False

    @staticmethod
    def _focusable(row) -> list:  # noqa: ANN001 (toolkit row protocol)
        """Focus targets in a row, with a single-control row counting itself.

        The toolkit's row scan only looks at a row's *children*; the header
        row is the ✕ button itself (its only focusable control), so without
        this a ``↑`` from the strip would find an empty header row and wrap to
        the action bar instead of stepping back up.
        """
        items = ToolbarRowsSection._focusable(row)
        if items:
            return items
        try:
            if (
                row.focusPolicy() == Qt.FocusPolicy.StrongFocus
                and row.isVisible()
                and row.isEnabled()
            ):
                return [row]
        except Exception:
            pass
        return []

    def focus_strip(self) -> bool:
        """Land the ring on the strip's first live control (rebuild rescue)."""
        strip = getattr(self._overlay, "_strip_row", None)
        if strip is None:
            return self.focus_first(reason=focus_reason())
        return self._focus_first_in(strip, focus_reason())


def section_of(overlay):
    """The registered section, or ``None`` while the overlay is closed."""
    return getattr(overlay, SECTION_ATTR, None)


def remember_opener(overlay) -> None:
    """Remember who opened S3 and re-arm the close-time return-focus.

    The opener is captured as a widget (S3 opens from a toolbar action or a
    card that stays alive for the overlay's lifetime). A focus already inside
    another in-window overlay (S3 re-shown after Quick Look closes) is not an
    opener — the original one is kept, but the restore is still re-armed for
    the next close.
    """
    try:
        setattr(overlay, RESTORED_ATTR, False)
    except Exception:
        return
    opener = focused_widget(overlay)
    if opener is None or opener is overlay:
        return
    try:
        if overlay.isAncestorOf(opener):
            return
    except Exception:
        return
    if _inside_other_overlay(opener, overlay):
        return
    try:
        setattr(overlay, OPENER_ATTR, opener)
    except Exception:
        pass


def _inside_other_overlay(widget, overlay) -> bool:
    """True when *widget* lives inside a different ``TopLevelInWindowOverlay``."""
    try:
        from sli_ui_toolkit.widgets import TopLevelInWindowOverlay
    except Exception:
        return False
    node = widget
    while node is not None:
        try:
            if node is not overlay and isinstance(node, TopLevelInWindowOverlay):
                return True
            node = node.parentWidget()
        except Exception:
            return False
    return False


def restore_opener_focus(overlay) -> bool:
    """Hand the keyboard cursor back to the opener. Once per open."""
    try:
        if bool(getattr(overlay, RESTORED_ATTR, False)):
            return False
        setattr(overlay, RESTORED_ATTR, True)
    except Exception:
        return False
    opener = getattr(overlay, OPENER_ATTR, None)
    if opener is None:
        return False
    # A hand-off close (S3 hides because a card opened Quick Look) leaves the
    # ring to the overlay that just took it — restoring here would pull focus
    # back out of Quick Look (the overlay sets ``_ql_return`` before hiding).
    if getattr(overlay, "_ql_return", None) is not None:
        return False
    try:
        if not opener.isVisible() or not opener.isEnabled():
            return False
        opener.setFocus(focus_reason())
        return True
    except Exception:
        return False


def restore_after_rebuild(overlay) -> bool:
    """Keep the ring inside S3 after ``populate`` replaced the strip.

    A rebuild destroys the focused ``↩ Restore`` button, which would leave the
    ring on the bare overlay — and a bare-overlay arrow is consumed at the
    modal edge without moving anything. Only rescues a LOST ring: a user who
    has meanwhile moved to the header or action bar stays there.
    """
    section = section_of(overlay)
    if section is None:
        return False
    try:
        if not overlay.isVisible():
            return False
    except Exception:
        return False
    focused = focused_widget(overlay)
    if focused is not None and focused is not overlay:
        try:
            if section._row_of(focused) is not None:
                return False
        except Exception:
            pass
    return section.focus_strip()


def register(overlay) -> None:
    """Make the overlay a modal navigation section while visible (idempotent)."""
    if overlay is None:
        return
    try:
        section = section_of(overlay)
        if section is None:
            section = CleanReviewNavSection(overlay)
            setattr(overlay, SECTION_ATTR, section)
        NavigationManager.get_instance().register(overlay, section)
    except Exception:
        return
    # Enter on the header row (its only control is ✕ — row-local arrows and
    # Down then walk the strip and the action bar). Deferred second attempt
    # covers a layout that is not settled at the first tick.
    section.focus_first(reason=focus_reason())
    QTimer.singleShot(0, lambda: _enter_if_unfocused(overlay, section))


def _enter_if_unfocused(overlay, section) -> None:
    if section_of(overlay) is not section:
        return
    focused = focused_widget(overlay)
    if focused is None or focused is overlay:
        try:
            section.focus_first(reason=focus_reason())
        except Exception:
            pass


def unregister(overlay) -> None:
    """Drop the section again and restore the opener (idempotent, fail-open)."""
    if overlay is None:
        return
    try:
        NavigationManager.get_instance().unregister(overlay)
    except Exception:
        pass
    try:
        setattr(overlay, SECTION_ATTR, None)
    except Exception:
        pass
    restore_opener_focus(overlay)


__all__ = [
    "CleanReviewNavSection",
    "OPENER_ATTR",
    "RESTORED_ATTR",
    "SECTION_ATTR",
    "focused_widget",
    "register",
    "remember_opener",
    "restore_after_rebuild",
    "restore_opener_focus",
    "rows",
    "section_of",
    "unregister",
]
