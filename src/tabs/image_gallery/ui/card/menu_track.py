"""Hover tracking for the gallery card context menu.

Split out of ``ui/card/context_menu.py`` per CODE_PATTERNS (file-size
policy): keeping the card hover highlight while its popup menu is open
(and clearing it on hide) is hover lifecycle, not menu building.
"""

from __future__ import annotations


def track_open_menu(card, menu, owner=None) -> None:  # type: ignore[no-untyped-def]
    """Keep the card hover highlight while its context menu is open.

    The popup takes the mouse, so the card gets a Leave that would clear
    the underline. The hover filter skips the hide while the tracked menu
    is visible (see ``_CardHoverFilter``); on hide the bar is cleared
    deterministically — no cursor polling.

    Do NOT re-derive hover at hide time from ``QCursor.pos()`` /
    ``mapFromGlobal``. That polled geometry lies on Wayland (stale
    global-vs-moment position), checks "cursor over card" true while the
    cursor actually sits on the popup, and pins the underline on with no
    way to clear it (stuck-ON; a stuck-OFF merely waits for the next
    Enter). Recorded lesson, REMOVED once already:
    ``gallery-hover-loss-2026-09-26.md`` § Timeline item 3. Real hover is
    re-established by Qt's own Enter/Leave after the popup is gone.

    ``owner`` is passed through (grid cards carry no ``_gallery_owner`` —
    the pool builds them without one) so hide-time traces can resolve the
    marquee gesture the same way the open-time trace does.
    """
    try:
        if card is None or menu is None:
            return
        try:
            card._gallery_open_menu = menu  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.card.hover import _show_card_hover_underline

            _show_card_hover_underline(card)
        except Exception:
            pass
        try:
            about = getattr(menu, "aboutToHide", None)
            if about is not None and hasattr(about, "connect"):
                try:
                    # Explicit owner threaded from _on_card_context (fail-open
                    # None: hide-time traces degrade to "none", see
                    # marquee_snapshot — shared-with-tests signature).
                    _menu_owner = owner
                except Exception:
                    _menu_owner = None

                def _on_menu_hidden(c=card, m=menu, o=_menu_owner) -> None:
                    try:
                        if getattr(c, "_gallery_open_menu", None) is m:
                            c._gallery_open_menu = None  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    try:
                        from tabs.image_gallery.debug import gallery_debug as _dbg2
                        from tabs.image_gallery.ui.card.marquee_snapshot import marquee_snapshot as _snap

                        _dbg2("card menu hidden marquee=%s", _snap(o, c))
                    except Exception:
                        pass
                    try:
                        from tabs.image_gallery.ui.card.hover import (
                            _hide_card_hover_underline as _hide,
                        )

                        _hide(c)
                    except Exception:
                        pass

                about.connect(_on_menu_hidden)
        except Exception:
            pass
    except Exception:
        pass
