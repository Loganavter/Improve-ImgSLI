"""Return the keyboard cursor to the gallery card that opened Quick Look.

Closing the panel used to drop its own focus on the floor: the overlay is a
plain in-window widget (no focus proxy), so once it unmapped Qt had no
"previous widget" to go back to and the window's own fallback handed the
cursor to its first focusable widget. A reader who opened Quick Look from the
20th card had to walk back from the beginning (reported live).

Fix shape:

* ``show_for`` calls :func:`remember_opener` — the **identity** of the opener,
  its path, not a widget pointer (a card is recycled/rebuilt while the panel is
  open, so a pointer would go stale);
* the lifecycle's navigation-graph exit (``overlay_parts/lifecycle.py``) calls
  :func:`restore_opener_focus` — every close path (Esc, veil, ✕, direct
  hide/close) already funnels through there.

Resolution reuses the grid's own API (``grid_view/nav.py`` +
``grid_view/marquee.card_for``): the opener card when it is still live, else
the grid's own current-or-first live card, else the gallery widget itself. The
focus reason comes from the app's one policy
(``NavigationManager.current_focus_reason()``: mouse history → no ring,
keyboard → ring) — never a hardcoded Qt reason.

Idempotent and fail-open: the first close wins (a second close must not steal
focus back from wherever the user has moved on), and a missing grid / card /
owner is a silent no-op — focus is never left unset because a lookup raised.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

#: Overlay attribute holding the opener's path (the stable identity).
OPENER_ATTR = "_opener_path"

#: Overlay attribute disarming the restore until the next ``show_for``.
RESTORED_ATTR = "_opener_focus_restored"


def remember_opener(overlay, item) -> None:
    """Remember *item* as the panel's opener and re-arm the close restore.

    Called from ``show_for`` for every open (and every refresh that re-shows an
    item), so a reopen anchors on the item it was opened for.
    """
    try:
        path = getattr(item, "path", None)
    except Exception:
        path = None
    try:
        setattr(overlay, OPENER_ATTR, Path(path) if path is not None else None)
        setattr(overlay, RESTORED_ATTR, False)
    except Exception:
        pass


def restore_opener_focus(overlay) -> bool:
    """Hand the keyboard cursor back to the opener card. Once per open."""
    try:
        if bool(getattr(overlay, RESTORED_ATTR, False)):
            return False
        setattr(overlay, RESTORED_ATTR, True)
    except Exception:
        return False
    try:
        owner = getattr(overlay, "_owner", None)
    except Exception:
        owner = None
    try:
        opener = getattr(overlay, OPENER_ATTR, None)
    except Exception:
        opener = None
    try:
        if _focus_in_grid(owner, opener):
            return True
    except Exception:
        pass
    return _focus_gallery_widget(owner)


def _focus_in_grid(owner, opener) -> bool:
    grid = _grid_view(owner)
    if grid is None:
        return False
    try:
        if not grid.isVisible():
            return False
    except Exception:
        pass
    if opener is not None:
        card = _card_for(grid, opener)
        if _focusable(card) and grid.focus_card(card):
            return True
    # Opener recycled/rebuilt away (or never known): the grid's own
    # current-or-first live card — never the window's first focusable widget.
    try:
        current = grid.focused_card()
    except Exception:
        current = None
    if _focusable(current) and grid.focus_card(current):
        return True
    return bool(grid.focus_first_card())


def _focus_gallery_widget(owner) -> bool:
    """Last resort: the gallery widget itself (its arrows bootstrap the grid)."""
    widget = _gallery_widget(owner)
    if widget is None:
        return False
    try:
        widget.setFocus(_focus_reason())
        return True
    except Exception:
        return False


def _grid_view(owner):
    """The gallery grid view behind *owner* (widget, or controller → widget).

    Discriminated by the grid's own API (``card_for``) rather than by class, so
    the storeless widget shape and the production ``controller.widget._grid_view``
    nesting resolve through the same probe (mirrors
    ``use_cases/selection._selection_visual_targets``).
    """
    found: list = []

    def _take(candidate) -> None:
        try:
            if (
                candidate is not None
                and callable(getattr(candidate, "card_for", None))
                and all(candidate is not other for other in found)
            ):
                found.append(candidate)
        except Exception:
            pass

    for attr in ("grid_view", "_grid_view"):
        try:
            _take(getattr(owner, attr, None))
        except Exception:
            continue
    for nest in ("widget", "_widget"):
        try:
            _take(getattr(getattr(owner, nest, None), "_grid_view", None))
        except Exception:
            continue
    return found[0] if found else None


def _gallery_widget(owner):
    """The gallery widget itself (the controller's ``widget``, else *owner*)."""
    if owner is None:
        return None
    for attr in ("widget", "_widget"):
        try:
            candidate = getattr(owner, attr, None)
        except Exception:
            candidate = None
        if candidate is not None:
            return candidate
    return owner


def _card_for(grid, path):
    try:
        return grid.card_for(path)
    except Exception:
        return None


def _focusable(card) -> bool:
    if card is None:
        return False
    try:
        return bool(card.isVisible() and card.isEnabled())
    except Exception:
        return False


def _focus_reason() -> Qt.FocusReason:
    """The app's focus-reason policy (mouse → no ring, keyboard → ring)."""
    try:
        from sli_ui_toolkit.managers import NavigationManager

        return NavigationManager.get_instance().current_focus_reason()
    except Exception:
        return Qt.FocusReason.OtherFocusReason


__all__ = [
    "OPENER_ATTR",
    "RESTORED_ATTR",
    "remember_opener",
    "restore_opener_focus",
]
