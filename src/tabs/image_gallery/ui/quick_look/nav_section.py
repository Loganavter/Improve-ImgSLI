"""Quick Look keyboard navigation — the toolkit's own rows, nothing bespoke.

The panel is a navigation **section** while it is visible, and the section is a
``ToolbarRowsSection`` (``sli_ui_toolkit/ui/managers/navigation_sections.py``)
over the three rows the panel already has, in visual top-to-bottom order:

============  =========================================================
row           controls (``owns`` = the row container)
============  =========================================================
header        the ✕ close button (``quicklook_close``) — the header's
              only focusable control, so the row *is* that button, the
              same single-control-row idiom Clean Review's header uses
              (``clean_review/nav_section.py``). It stays in the title
              layout; declaring it as a row is what makes it owned.
filmstrip     the per-item thumb ``Button`` (``overlay._strip_row``)
action bar    Set as source / Reject / Delete (``overlay._action_bar``)
============  =========================================================

Audit ``inv-nav-coverage-audit-2026-10-19`` rank 4: the ✕ used to sit outside
every declared row (arrow-unreachable), and the ``‹``/``›`` circles + SOURCE
inset thumb were unowned overlay children (a duplicate cursor and an inert
``StrongFocus`` stop). Circles and inset are now ``NoFocus`` by written decision
(``overlay_build/build.py``); the ✕ is this third row.

* ``←``/``→`` (and the ``‹``/``›`` circles) move the **focus ring** along the
  current row — the section's own row-local step, so the cursor IS the app's
  single cursor vocabulary (the toolkit ``FocusLayer``). The picture does not
  move; ``Enter`` shows the focused item. Same cursor-vs-applied idiom the
  adaptive tab bar pins
  (``tests/contracts/test_navigation_graph.py::test_tab_strip_left_right_requires_enter``).
* ``↓``/``↑`` cross between the three rows, so the action row's three buttons
  (**Set as source** / **Reject** / **Delete**) are reached with ``↓`` then
  ``←``/``→``, and the ✕ with ``↑`` from the strip.
* ``Enter`` and the space bar are never claimed here: the focused toolkit
  ``Button`` activates itself (``widgets/buttons/events.py::_activate_via_keyboard``
  → the same ``clicked`` → ``_switch`` path a mouse click takes).
* Arrows cannot reach the gallery grid behind the veil: the panel declares
  :attr:`QuickLookNavSection.modal` (``True``), so the toolkit
  ``NavigationManager`` treats it as a modal ceiling while it is visible —
  every arrow, the section's ``extra_keys`` and Tab/Backtab are routed into the
  panel, and a foreign focus steal is pulled back (``_reclaim_modal_focus``).
  Inside the panel the row edges **wrap** (``↑`` at the header hands the ring to
  the action bar, ``↓`` there hands it back to the header) instead of yielding
  to a neighbouring section; the manager's modal-edge consume stays as the
  safety net for whatever the wrap does not claim.

The strip is rebuilt whenever its fingerprint changes — ranks re-stamped by the
analysis pass, a triage flip, a theme/scale change (``strip/helpers.py::
_strip_fingerprint``; a plain step takes the selection-only fast path and
touches no widgets) — and that full rebuild replaces the thumb widgets. So the
focused thumb is snapshotted by ``gallery_path``, the identity
``strip/rebuild.py`` stamps on every thumb and the identity
``grid_view/nav.py::_focus_snapshot`` uses for cards, before the churn, and
restored at the strip's per-populate sync point
(``strip/rebuild.py::ensure_strip_scroll``).

Register/unregister ride the panel's show/close lifecycle
(``overlay_parts/show.py``, ``overlay_parts/lifecycle.py``); both are idempotent
and fail-open, and the close path still hands focus back to the opener card
(``quick_look/focus_restore.py``).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection
from sli_ui_toolkit.ui.managers.nav_graph import focus_reason

#: Overlay attribute holding the registered section (idempotent register).
SECTION_ATTR = "_ql_nav_section"

#: Overlay attribute holding the focused thumb's path across a strip rebuild
#: (the gallery grid's ``_rebuild_focus_path`` keeps the same thing per rebuild).
FOCUS_PATH_ATTR = "_ql_strip_focus_path"


def rows(overlay) -> list:
    """The panel's navigable rows, visual top-to-bottom.

    The ✕ is the header row (a single-control row is the control itself). Rows
    are re-read per call, so a rebuilt panel never hands back a stale widget.
    """
    return [
        getattr(overlay, "_close_btn", None),
        getattr(overlay, "_strip_row", None),
        getattr(overlay, "_action_bar", None),
    ]


def focused_widget(overlay):
    """The focus widget of the panel's window, or ``None``.

    ``QApplication.focusWidget()`` reports ``None`` while the window is not
    OS-active (the control channel drives the app that way), which would read as
    "the cursor is elsewhere" for a ring that is really in the strip. Ask the
    overlay's own window first, then fall back to the application.
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


def _is_thumb(widget) -> bool:
    """True for the strip's thumb ``Button`` (``quicklook_strip_N``).

    The containers are ``quicklook_strip_container_N`` — same prefix, but a
    container is NoFocus and paints no ring, so only the numbered Buttons are
    cursor targets (that mismatch was the live "no indication" report).
    """
    try:
        name = str(widget.objectName() or "")
    except Exception:
        return False
    if not name.startswith("quicklook_strip_"):
        return False
    return name[len("quicklook_strip_"):].isdigit()


def _thumb_path(widget) -> str | None:
    try:
        path = widget.property("gallery_path")
    except Exception:
        return None
    return str(path) if path else None


def strip_thumbs(overlay) -> list:
    """The live strip thumbs, left to right (``quicklook_strip_N`` buttons)."""
    row = getattr(overlay, "_strip_row", None)
    if row is None:
        return []
    thumbs = []
    try:
        children = row.findChildren(QWidget)
    except Exception:
        return []
    for widget in children:
        if _is_thumb(widget):
            thumbs.append(widget)
    try:
        return sorted(thumbs, key=lambda w: w.mapToGlobal(w.rect().center()).x())
    except Exception:
        return thumbs


def thumb_for_path(overlay, path):
    """The live thumb carrying *path* (``None`` when it is not in the strip)."""
    if path is None:
        return None
    for widget in strip_thumbs(overlay):
        if _thumb_path(widget) == str(path):
            return widget
    return None


def shown_thumb_path(overlay) -> str | None:
    """``gallery_path`` of the item the panel is showing."""
    try:
        items = list(getattr(overlay, "_series_items", None) or [])
        idx = int(getattr(overlay, "_current_idx", 0) or 0)
        return str(getattr(items[idx], "path", "")) or None
    except Exception:
        return None


def focus_snapshot(overlay) -> str | None:
    """``gallery_path`` of the focused thumb, or ``None`` when focus is elsewhere.

    Identity is the *path*, not the widget: the full rebuild clears
    ``_strip_buttons`` and ``deleteLater``\\ s every thumb, so a widget reference
    would go stale — the reason the gallery grid snapshots cards by path too.
    """
    focused = focused_widget(overlay)
    if focused is None or not _is_thumb(focused):
        return None
    return _thumb_path(focused)


def snapshot_focus(overlay) -> str | None:
    """Remember the focused thumb's path for the rebuild that is about to run.

    Called at the TOP of ``strip/rebuild_strip`` — by the tail the old widgets
    are gone and there is nothing left to read the path from.
    """
    path = focus_snapshot(overlay)
    try:
        setattr(overlay, FOCUS_PATH_ATTR, path)
    except Exception:
        pass
    return path


def _nav_active(overlay) -> bool:
    """True while the panel is a registered, visible navigation section."""
    if getattr(overlay, SECTION_ATTR, None) is None:
        return False
    try:
        return bool(overlay.isVisible())
    except Exception:
        return False


def _in_strip_row(overlay, widget) -> bool:
    row = getattr(overlay, "_strip_row", None)
    try:
        return bool(row is not None and (row is widget or row.isAncestorOf(widget)))
    except Exception:
        return False


def _focus_is_in_strip(overlay) -> bool:
    """True when focus is unset, on the panel, or somewhere in the strip row."""
    focused = focused_widget(overlay)
    if focused is None or focused is overlay:
        return True
    return _in_strip_row(overlay, focused)


def _place_cursor(overlay, path, *, only_if_lost: bool = False) -> bool:
    """Put the ring back on the thumb carrying *path* (fail-open).

    ``only_if_lost`` is the rule for the deferred second attempt: it rescues a
    ring the rebuild dropped, but never overrides a cursor the user has already
    moved in the same tick — the steal that made "arrow after Enter" a no-op
    (measured 2026-10-17: the deferred re-apply pulled the ring back off the
    thumb the user had just stepped to).
    """
    if not _nav_active(overlay):
        return False
    if only_if_lost:
        focused = focused_widget(overlay)
        if focused is not None and focused is not overlay:
            return False
    elif not _focus_is_in_strip(overlay):
        return False
    thumb = thumb_for_path(overlay, path)
    if thumb is None:
        return False
    try:
        thumb.setFocus(focus_reason())
    except Exception:
        return False
    return True


def focus_shown_thumb(overlay) -> bool:
    """Deliberately put the ring on the item the panel is showing.

    The explicit-request placement — the ‹/› circles landing, the section's
    ``focus_first`` entry, and the register-time ring — as opposed to
    :func:`restore_focus`, which only ever rescues a ring that a background
    rebuild dropped and must never pull focus away from a row button.
    """
    if not _nav_active(overlay):
        return False
    thumb = thumb_for_path(overlay, shown_thumb_path(overlay))
    if thumb is None:
        return False
    try:
        thumb.setFocus(focus_reason())
    except Exception:
        return False
    return True


def restore_focus(overlay, path) -> bool:
    """Re-focus the thumb carrying *path* — deferred, and never a focus thief.

    Fail-open and non-granting, like ``grid_view/nav.py::_restore_focus``: no
    path, an unregistered/hidden panel, a path that left the series, or a user
    who has meanwhile moved the ring onto a row button — all silent no-ops. The
    second attempt one tick later covers a rebuild that replaces the thumb
    widgets again after this call; it only ever fills a LOST ring.
    """
    try:
        if path is None or not _nav_active(overlay):
            return False
        if thumb_for_path(overlay, path) is None:
            return False
        placed = _place_cursor(overlay, path)
        QTimer.singleShot(0, lambda: _place_cursor(overlay, path, only_if_lost=True))
        return placed
    except Exception:
        return False


def restore_strip_focus(overlay) -> bool:
    """Re-focus the thumb :func:`snapshot_focus` remembered.

    The strip's per-populate sync point (``ensure_strip_scroll``) calls this on
    every rebuild, so a background repopulate (the metrics pass) cannot leave
    the panel's ring on a deleted widget.
    """
    try:
        return restore_focus(overlay, getattr(overlay, FOCUS_PATH_ATTR, None))
    except Exception:
        return False


def move_strip_focus(overlay, delta: int) -> bool:
    """Step the ring one thumb along the strip — the ``‹``/``›`` circles.

    Focus movement, exactly like ``←``/``→`` and through the same section step
    (the picture follows on ``Enter``), so the circles cannot drift into a
    second cursor of their own.
    """
    section = getattr(overlay, SECTION_ATTR, None)
    if section is None:
        return False
    focused = focused_widget(overlay)
    if not _in_strip_row(overlay, focused):
        # The ring is elsewhere (a row button, the bare panel): bring it back
        # to the item on screen first, then step from there — a circle press
        # always moves the strip's ring, never the picture.
        focus_shown_thumb(overlay)
        focused = focused_widget(overlay)
    if not _in_strip_row(overlay, focused):
        return bool(section.focus_first(reason=focus_reason()))
    key = Qt.Key.Key_Right if int(delta) > 0 else Qt.Key.Key_Left
    return bool(section.navigate(key, focused))


class QuickLookNavSection(ToolbarRowsSection):
    """The panel's three rows as a toolkit row section, plus the modal wrap.

    Everything key-related is the toolkit section's: it focuses a row's
    ``StrongFocus`` children (so the ring lands on the thumb ``Button``, never
    on its NoFocus container), steps ``←``/``→`` within a row, crosses
    ``↓``/``↑`` between rows, scrolls the focused thumb into view through the
    strip's ``OverlayScrollArea`` ancestor (``_ensure_visible``), and resolves
    the focus reason through the app's policy.

    Three overrides, all about the panel's shape:

    * the row edges **wrap inside the panel** (``↓`` from the action bar lands on
      the header ✕, ``↑`` from the header ✕ lands on the action bar) instead of
      yielding. ``ToolbarRowsSection`` yields at its boundaries so the shell can
      hand focus to the section above/below — right for a toolbar, wrong here: it
      walked the ring onto the gallery grid behind the veil while the panel
      stayed up with no ring on it (measured 2026-10-17: Up on the first thumb
      focused a card of the section registered before us, via
      ``NavigationManager._neighbor``);
    * :meth:`focus_first` enters on the item already on screen, not on the
      header — that override is the *bootstrap* entry, so the bottom-edge wrap
      calls the toolkit row directly instead (the ✕ is the top of the visual
      loop);
    * a single-control row (the ✕) counts itself as its only cursor target —
      the toolkit row scan only looks at a row's children.

    :attr:`modal` additionally makes the panel the manager's modal ceiling while
    it is visible: every arrow, its ``extra_keys`` and Tab/Backtab are routed
    into the panel, and the manager's modal-edge consume stays as the safety net
    for whatever the wrap does not claim.
    """

    def __init__(self, overlay: QWidget) -> None:
        super().__init__(lambda: rows(overlay), tag="quick-look")
        self._overlay = overlay

    @property
    def modal(self) -> bool:
        """The panel owns the keyboard for its window while it is visible.

        Read by the manager as ``getattr(spec, "modal", False)`` (same raw-read
        pattern as ``extra_keys``): the panel is the last registered section
        while shown, so it is the modal ceiling and the grid behind the veil
        receives no key or focus. Must stay a **property**, never a method.
        """
        return True

    @staticmethod
    def _focusable(row) -> list:  # noqa: ANN001 (toolkit row protocol)
        """Focus targets in a row, with a single-control row counting itself.

        The toolkit scan only looks at a row's *children*; the header row is the
        ✕ itself, so without this an empty scan would make the ✕ unreachable.
        Mirrors ``CleanReviewNavSection._focusable``.
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

    def navigate(self, key: int, widget) -> bool:  # noqa: ANN001
        if super().navigate(key, widget):
            return True
        # Panel edge: wrap inside the panel, never yield to the page behind
        # (see the class docstring). The manager's modal edge would consume the
        # key anyway; the wrap is the steer's requested shape. Down wraps to the
        # header row (the visual top), not to ``self.focus_first`` — that
        # override is the bootstrap entry and deliberately lands on the item on
        # screen.
        if key == Qt.Key.Key_Up:
            return self.focus_last(reason=focus_reason())
        if key == Qt.Key.Key_Down:
            return ToolbarRowsSection.focus_first(self, reason=focus_reason())
        return False

    def focus_first(self, ref_x=None, *, reason=None) -> bool:  # noqa: ANN001
        """Enter the section on the row item that is already on screen.

        The panel's "first" item is the item it is showing: the manager calls
        this when the bare owner holds focus and an arrow key arrives (its own
        bootstrap, ``navigation_manager.py``). Landing the ring on the first
        thumb would light a cursor on a picture nobody asked for — the next
        Enter would switch to it. Falls back to the toolkit row when the shown
        item has no thumb (a single-item series hides the strip).

        This is the *entry* override only: the bottom-edge ``↓`` wrap calls the
        toolkit ``focus_first`` directly, so wrapping lands on the header ✕.
        """
        if focus_shown_thumb(self._overlay):
            return True
        return super().focus_first(ref_x, reason=reason or focus_reason())

    # ``extra_keys`` (``←``/``→`` only — a **property**, because every reader
    # iterates the raw attribute: ``NavigationManager.eventFilter`` does
    # ``key in getattr(spec, "extra_keys", frozenset())`` and a method-shaped one
    # raised ``TypeError: argument of type 'method' is not a container or
    # iterable`` on every ``←``/``→``, live 2026-10-17), ``owns`` and
    # ``focus_last`` are inherited: Return/Enter stay with the focused ``Button``,
    # the section claims exactly its three rows, and "entering from below" lands
    # on the bottom row's first focusable — right for the action bar.


def section_of(overlay):
    """The registered section, or ``None`` while the panel is closed."""
    return getattr(overlay, SECTION_ATTR, None)


def register(overlay) -> None:
    """Make the panel a navigation section while it is visible (idempotent)."""
    if overlay is None:
        return
    try:
        section = section_of(overlay)
        if section is None:
            section = QuickLookNavSection(overlay)
            setattr(overlay, SECTION_ATTR, section)
        NavigationManager.get_instance().register(overlay, section)
    except Exception:
        return
    # Land the ring on the item already on screen. Do it BEFORE the manager's
    # own deferred bootstrap (registration queues it) — that bootstrap focuses
    # the section's first row once it sees the bare owner still focused, and
    # ``_bootstrap_if_still_owner`` skips once focus sits inside the section.
    restore_focus(overlay, shown_thumb_path(overlay))


def unregister(overlay) -> None:
    """Drop the section again (idempotent, fail-open)."""
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


__all__ = [
    "FOCUS_PATH_ATTR",
    "QuickLookNavSection",
    "SECTION_ATTR",
    "focus_shown_thumb",
    "focus_snapshot",
    "focused_widget",
    "move_strip_focus",
    "register",
    "restore_focus",
    "restore_strip_focus",
    "rows",
    "section_of",
    "shown_thumb_path",
    "snapshot_focus",
    "strip_thumbs",
    "thumb_for_path",
    "unregister",
]
