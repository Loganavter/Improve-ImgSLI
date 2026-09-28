"""Hover helpers — underline highlight only (painter pipeline only).

Card actions live in the right-click context menu
(``ui/card/context_menu.py``); hover only paints the accent underline.
Audit-Meta: pattern=thin-owner size=exempt reason="single card-hover lifecycle — hover filter and underline share one owner-resolution path"
"""

from __future__ import annotations

import time
from PySide6.QtCore import QEvent, QObject
from sli_ui_toolkit.managers import scaled_px


def _hover_diag_enabled() -> bool:
    """Separate key for the gate-zone dump (bisect aid, not a feature)."""
    try:
        from shared.debug_flags import env_flag

        return bool(env_flag("IMGSLI_GALLERY_HOVER_DIAG"))
    except Exception:
        return False


def log_card_gates(card, owner, trigger: str) -> None:  # type: ignore[no-untyped-def]
    """One-line dump of EVERY gate in the card-buttons show path.

    Gated by ``IMGSLI_GALLERY_HOVER_DIAG=1`` only (never in the default
    streams). Call at Enter/Leave/show/hide/sync decision points; when a
    hover shows nothing, this line names the exact gate that said no
    (or proves no decision point ran at all).
    """
    if not _hover_diag_enabled():
        return
    try:
        import logging as _logging

        _logger = _logging.getLogger("ImproveImgSLI")
    except Exception:
        return
    try:
        path = getattr(getattr(card, "_gallery_item", None), "path", "?")
        # Suppression window: remaining ms (>0 means capsule blocked).
        try:
            now = time.monotonic()
            remains = [
                max(0.0, float(getattr(o, "_gallery_capsule_suppress_until", 0.0) or 0.0) - now)
                for o in (owner, card)
                if o is not None
            ]
            suppress_ms = int(max(remains) * 1000) if remains else 0
        except Exception:
            suppress_ms = -1
        try:
            hovered = bool(getattr(card, "_gallery_delete_hovered", False))
        except Exception:
            hovered = False
        try:
            from PySide6.QtCore import Qt as _Qt

            transparent = bool(card.testAttribute(_Qt.WidgetAttribute.WA_TransparentForMouseEvents))
            enabled = bool(card.isEnabled())
            visible = bool(card.isVisible())
        except Exception:
            transparent, enabled, visible = "?", "?", "?"
        try:
            btn = getattr(card, "_gallery_delete_btn", None)
            pin = getattr(card, "_gallery_delete_pin", None)
            import shiboken6 as _shib

            btn_ok = btn is not None and bool(_shib.isValid(btn))
            btn_vis = bool(btn.isVisible()) if btn_ok else False
        except Exception:
            btn_ok, btn_vis = False, False
            pin = None
        try:
            in_host = btn is not None and card.parent() is btn.parent() and btn.parent() is not None
        except Exception:
            in_host = False
        try:
            shown = bool(card.isVisibleTo(btn.parent())) if (btn is not None and in_host) else False
        except Exception:
            shown = False
        try:
            rejected = bool(getattr(getattr(card, "_gallery_item", None), "rejected", False))
        except Exception:
            rejected = False
        try:
            flyout = getattr(card, "_gallery_card_flyout", None)
            fly_vis = bool(flyout.isVisible()) if flyout is not None else False
            fly = "shown" if fly_vis else ("exists" if flyout is not None else "none")
        except Exception:
            fly = "?"
        try:
            bg_locked = bool(card.is_bg_locked()) if hasattr(card, "is_bg_locked") else False
        except Exception:
            bg_locked = False
        try:
            gesture, filt = None, None
            for cand in (owner, getattr(card, "_gallery_owner", None)):
                try:
                    gv = getattr(cand, "grid_view", None) or getattr(cand, "widget", None)
                    gv = getattr(gv, "_grid_view", gv)
                    gesture = getattr(gv, "_marquee_gesture", None)
                    if gesture is not None:
                        filt = bool(getattr(gesture, "app_filter_installed", False))
                        break
                except Exception:
                    continue
            gest = "none" if gesture is None else ("active" if bool(getattr(gesture, "active", False)) else ("filter" if filt else "idle"))
        except Exception:
            gest = "?"
        _logger.warning(
            "[gallery-debug] [gates] %s card=%s suppress_ms=%s hovered=%s in_host=%s shown=%s "
            "rejected=%s btn=%s/%s flyout=%s marquee=%s tmouse=%s ena=%s vis=%s bglock=%s",
            trigger, path, suppress_ms, hovered, in_host, shown,
            rejected, btn_ok, btn_vis, fly, gest,
            transparent, enabled, visible, bg_locked,
        )
    except Exception:
        pass


def _event_pos(event) -> str:
    """Position carried BY the event (trustworthy).

    Unlike polled ``QCursor.pos()`` (stale on Wayland, wrong moment), the
    event's own position is the boundary witness: where Qt says the cursor
    was when this Enter/Leave was synthesized.
    """
    for attr in ("position", "globalPosition", "pos"):
        try:
            p = getattr(event, attr, None)
            v = p() if callable(p) else p
            if v is not None:
                try:
                    return "%d,%d" % (int(v.x()), int(v.y()))
                except Exception:
                    return str(v)
        except Exception:
            continue
    return "?"


def _mouse_buttons_int() -> int:
    """Live mouse buttons bitmask (fail-open, -1 on error).

    Distinguishes real hover (0) from press-drag (≠0, e.g. marquee band):
    while a button is held Qt routes moves to the press receiver and the
    card never gets Enter.
    """
    try:
        from PySide6.QtWidgets import QApplication

        b = QApplication.mouseButtons()
        try:
            return int(getattr(b, "value", b))
        except Exception:
            return int(b)
    except Exception:
        return -1


def _hdbg(msg: str, *args) -> None:
    """One-line hover trace (env-gated, fail-open)."""
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg(msg, *args)
    except Exception:
        pass


class _CardHoverFilter(QObject):
    """Hover highlight for gallery cards: accent underline on Enter/Leave.

    Card actions live in the right-click context menu — hover never opens
    menus or buttons, so it cannot fight the context menu over the overlay.
    """

    def __init__(self, card, owner=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(card)
        self._card = card
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._card:
            if event.type() == QEvent.Type.Enter:
                _hdbg(
                    "card hover enter card=%s buttons=%s ev_pos=%s",
                    getattr(getattr(self._card, "_gallery_item", None), "path", "?"),
                    _mouse_buttons_int(),
                    _event_pos(event),
                )
                try:
                    _show_card_hover_underline(self._card)
                except Exception:
                    pass
            elif event.type() == QEvent.Type.Leave:
                # The context-menu popup takes the mouse and the card gets a
                # Leave — keep the highlight while the tracked menu is open.
                try:
                    _open = getattr(self._card, "_gallery_open_menu", None)
                    if _open is not None:
                        try:
                            _menu_live = bool(_open.isVisible())
                        except Exception:
                            _menu_live = False
                        if _menu_live:
                            _hdbg(
                                "card hover leave keep hide-reason=MENU_OPEN card=%s",
                                getattr(getattr(self._card, "_gallery_item", None), "path", "?"),
                            )
                            return False
                        try:
                            self._card._gallery_open_menu = None  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    _hide_card_hover_underline(self._card)
                except Exception as exc:
                    _hdbg("card hover leave FAILED err=%r", exc)
        return False


def _show_card_hover_underline(card) -> None:  # type: ignore[no-untyped-def]
    """S2-2: hovered card — 3px accent bar 234×3 r1.5 at 8,159 inside card per svg x874 y359."""
    try:
        # Use overlay flag instead of whole-button underline (which is full width at edge)
        card._hover_blue_bar = True  # type: ignore[attr-defined]
        card.update()
    except Exception:
        pass
    # Keep legacy underline as fallback for non-overlay path
    try:
        from tabs.image_gallery.ui.card.dots import _accent_color

        card.setUnderlineThickness(float(scaled_px(3)))
        card.setUnderlineTongueReach(float(scaled_px(2)))
        card.setUnderlineColor(_accent_color())
        # Do not show whole-button underline — overlay draws inset bar
        card.setShowUnderline(False)
    except Exception:
        pass


def _hide_card_hover_underline(card) -> None:  # type: ignore[no-untyped-def]
    try:
        card._hover_blue_bar = False  # type: ignore[attr-defined]
        card.update()
    except Exception:
        pass
    try:
        card.setShowUnderline(False)
    except Exception:
        pass
