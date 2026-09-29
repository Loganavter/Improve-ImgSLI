"""Hover tracking for the gallery card context menu.

Split out of ``ui/card/context_menu.py`` per CODE_PATTERNS (file-size
policy): keeping the card hover highlight while its popup menu is open
(and restoring it on hide) is hover lifecycle, not menu building.
"""

from __future__ import annotations


def track_open_menu(card, menu, owner=None) -> None:  # type: ignore[no-untyped-def]
    """Keep the card hover highlight while its context menu is open.

    The popup takes the mouse, so the card gets a Leave that would clear
    the underline. The hover filter skips the hide while the tracked menu
    is visible (see ``_CardHoverFilter``); on hide we restore the highlight
    and drop the (possibly stale) reference.

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
                    _menu_owner = owner if owner is not None else getattr(card, "_gallery_owner", None)
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
                            _show_card_hover_underline as _show,
                        )

                        _show(c)
                    except Exception:
                        pass

                about.connect(_on_menu_hidden)
        except Exception:
            pass
    except Exception:
        pass
