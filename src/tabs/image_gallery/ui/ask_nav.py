"""Keyboard ownership for the Ask AI surface (flyout and sidebar hosts).

The surface is not a single control column: the question row (field +
include-images toggle) sits above a one-button-per-exchange history list. The
section models exactly that shape with the toolkit's row primitives:

* rows, visual top to bottom = the host's chrome rows (the sidebar's ✕), the
  question row, then every live history row button;
* ``←``/``→`` stay inside the question row (field ↔ toggle, with the toolkit's
  caret-at-boundary yield so the caret is never stolen mid-text);
* ``↓``/``↑`` step question row ↔ history entry ↔ history entry;
* edges **wrap inside the ask surface** instead of yielding — the flyout is a
  popup over the gallery grid, so yielding would hand the ring to a card behind
  it while the flyout stays up.

One section per visible host: ``AskAiFlyout`` registers itself on show and
drops on hide; ``AskAiSidebar`` does the same. ``register`` is idempotent and
takes ownership away from a previously visible host (the same surface cannot be
claimed twice — see ``docs/dev/CONTRACTS.md`` "One owner per section").
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection
from sli_ui_toolkit.ui.managers.nav_graph import focus_reason

#: Host attribute holding its registered section (idempotent register).
SECTION_ATTR = "_ask_nav_section"

#: The host currently owning the surface's rows (only one at a time).
_ACTIVE_OWNER = None


def _chrome_rows(host) -> list:
    provider = getattr(host, "nav_chrome_rows", None)
    if not callable(provider):
        return []
    try:
        return [row for row in provider() if row is not None]
    except Exception:
        return []


def rows(host, surface) -> list:
    """The ask surface's navigable rows, visual top to bottom."""
    out = _chrome_rows(host)
    question_row = getattr(surface, "question_row", None)
    if question_row is not None:
        out.append(question_row)
    try:
        out.extend(surface.history_row_buttons())
    except Exception:
        pass
    return out


class AskSurfaceNavSection(ToolbarRowsSection):
    """Question row + history entries as one wrapped row section."""

    def __init__(self, host, surface) -> None:
        super().__init__(lambda: rows(host, surface), tag="gallery-ask")
        self._host = host
        self._surface = surface

    @staticmethod
    def _focusable(row) -> list:  # noqa: ANN001 (toolkit row protocol)
        """Focus targets in a row, with a single-control row counting itself.

        The toolkit scan only looks at a row's *children*; a history entry (and
        the sidebar's ✕) is the row itself, so without this the ring could
        never land on it.
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
        if key not in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            return False
        current = self._row_of(widget)
        ordered = self._rows()
        if current is None or current not in ordered:
            return False
        if key == Qt.Key.Key_Up and ordered.index(current) == 0:
            return self.focus_last(reason=focus_reason())
        if key == Qt.Key.Key_Down and ordered.index(current) == len(ordered) - 1:
            return self.focus_first(reason=focus_reason())
        return False


def section_of(host):
    """The host's registered section, or ``None``."""
    return getattr(host, SECTION_ATTR, None)


def register(host, surface) -> None:
    """Make the visible ask host a navigation section (idempotent)."""
    global _ACTIVE_OWNER
    if host is None or surface is None:
        return
    if _ACTIVE_OWNER is not None and _ACTIVE_OWNER is not host:
        unregister(_ACTIVE_OWNER)
    try:
        section = section_of(host)
        if section is None or getattr(section, "_surface", None) is not surface:
            section = AskSurfaceNavSection(host, surface)
            setattr(host, SECTION_ATTR, section)
        NavigationManager.get_instance().register(host, section)
        _ACTIVE_OWNER = host
    except Exception:
        return


def unregister(host) -> None:
    """Drop the host's section again (idempotent, fail-open)."""
    global _ACTIVE_OWNER
    if host is None:
        return
    try:
        NavigationManager.get_instance().unregister(host)
    except Exception:
        pass
    try:
        setattr(host, SECTION_ATTR, None)
    except Exception:
        pass
    if _ACTIVE_OWNER is host:
        _ACTIVE_OWNER = None


__all__ = [
    "AskSurfaceNavSection",
    "SECTION_ATTR",
    "register",
    "rows",
    "section_of",
    "unregister",
]
