"""Hover helpers — underline + flyout capsule (painter pipeline only).
Audit-Meta: pattern=thin-owner size=exempt reason="single card-hover lifecycle — hover filter, capsule show/hide, post-action suppression and tri-color icons share one owner-resolution path; splitting spreads suppression windows across modules"
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px

# Stage 2 flyout group for hover capsule (FLYOUT_SYSTEM.md).
GALLERY_CARD_FLYOUT_GROUP = "gallery_card"

# Post-action suppression window (ms): grid rebuilds recreate cards under
# the cursor, whose fresh Enter would instantly re-show the capsule the
# action just hid. Stamped on the owner (survives rebuilds).
_CAPSULE_SUPPRESS_MS = 600


def _suppress_capsule(owner, card=None, ms: int = _CAPSULE_SUPPRESS_MS) -> None:
    try:
        until = time.monotonic() + max(0, int(ms)) / 1000.0
        for obj in (owner, card):
            try:
                if obj is not None:
                    obj._gallery_capsule_suppress_until = until  # type: ignore[attr-defined]
            except Exception:
                pass
    except Exception:
        pass


def _capsule_suppressed(owner, card=None) -> bool:
    try:
        now = time.monotonic()
        for obj in (owner, card):
            try:
                if obj is not None and now < float(getattr(obj, "_gallery_capsule_suppress_until", 0.0) or 0.0):
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def _resolve_card_owner(card, hint=None):
    """Effective triage owner for *card* (fail-open None).

    Pool-recycled cards are built owner-less (grid ``_acquire_card`` passes
    no owner), so the hover filter's ``self._owner`` is None for them — but
    the post-action suppression is stamped on the real owner (controller)
    by ``_after_card_action``. Resolve the same way the capsule action
    handler does: explicit hint → ``card._gallery_owner`` → window
    ``_gallery_controller``/``_gallery_owner``. Without this the 600 ms
    post-action window is skipped for recycled cards and the capsule pops
    back up under the stationary cursor mid-rebuild.
    """
    try:
        if hint is not None:
            return hint
    except Exception:
        pass
    try:
        stored = getattr(card, "_gallery_owner", None)
        if stored is not None:
            return stored
    except Exception:
        pass
    try:
        win = card.window()
        if win is not None:
            return getattr(win, "_gallery_controller", None) or getattr(win, "_gallery_owner", None)
    except Exception:
        pass
    return None


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


def _capsule_content_diag(flyout, card=None) -> str:
    """Compact one-line dump of the capsule's live buttons (debug only).

    ``n=`` total buttons; per button ``aid:vis/eff/size/icon`` where
    ``vis`` is the Qt visible flag, ``eff`` effective visibility against
    the card, ``size`` ``WxH``, ``icon`` ``ok`` when the rasterized pixmap
    at the button's icon size is non-null, else ``blank``. Call only when
    the gallery debug stream is enabled (does pixmap work per button).
    """
    try:
        buttons = list(getattr(flyout, "_buttons", {}).items())
    except Exception:
        return "n=? (no _buttons)"
    parts = []
    for aid, btn in buttons:
        try:
            import shiboken6 as _shib

            valid = bool(_shib.isValid(btn))
        except Exception:
            valid = False
        if not valid:
            parts.append(f"{aid}:invalid")
            continue
        try:
            vis = "v" if bool(btn.isVisible()) else "h"
        except Exception:
            vis = "?"
        try:
            eff = "V" if (card is not None and bool(btn.isVisibleTo(card))) else ("v" if card is None else "H")
        except Exception:
            eff = "?"
        try:
            size = f"{btn.width()}x{btn.height()}"
        except Exception:
            size = "?"
        try:
            from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import (
                normalized_icon_pixmap as _px,
            )

            icon_val = getattr(btn, "_icon_unchecked", None)
            pm = _px(icon_val, 14)
            icon = "ok" if (pm is not None and not pm.isNull()) else "blank"
        except Exception:
            icon = "?"
        parts.append(f"{aid}:{vis}/{eff}/{size}/{icon}")
    return f"n={len(parts)} " + ",".join(parts)


def _notify_owner_hud(owner, text: str) -> None:
    """Transient HUD notice for card actions (fail-open)."""
    try:
        hud = getattr(owner, "_selection_hud", None)
        if hud is None:
            w = getattr(owner, "widget", None)
            hud = getattr(w, "_selection_hud", None) if w is not None else None
        if hud is not None and hasattr(hud, "notify"):
            hud.notify(text)
    except Exception:
        pass


def _theme_is_dark() -> bool:
    """Darkness for fallback selection — delegates to ``dots._is_dark``.

    Rule A: ``gallery.card.hover`` IS a registered token (both themes in
    ``themes.json``), so this only picks the hardcoded pair when tokens are
    absent; an unregistered palette resolves light, never dark.
    """
    try:
        from tabs.image_gallery.ui.card.dots import _is_dark as _dots_is_dark

        return bool(_dots_is_dark())
    except Exception:
        return False


def _capsule_icon_color(action_id: str):
    """Tri-color capsule icons (svg hover pill): star gold · cross red · swap accent.

    Accent chain (frozen seam): ``gallery.accent.bar`` → ``accent`` →
    ``#0078D4`` (light) / ``#0096FF`` (dark).
    """
    fallbacks = {
        "make_best": ("gallery.status.warn", (232, 182, 76)),
        "reject": ("gallery.status.danger", (217, 48, 37)),
        "compare": ("gallery.accent.bar", (0, 120, 212)),
        "set_source": ("gallery.accent.bar", (0, 120, 212)),
    }
    token, rgb = fallbacks.get(action_id, ("gallery.accent.bar", (0, 120, 212)))
    try:
        from PySide6.QtGui import QColor

        from sli_ui_toolkit.managers import ThemeManager
        from ui.theming import try_resolve_theme_color

        if token == "gallery.accent.bar":
            for tok in ("gallery.accent.bar", "accent"):
                c = try_resolve_theme_color(ThemeManager.get_instance(), tok)
                if c is not None:
                    return c if isinstance(c, QColor) else QColor(c)
        else:
            c = try_resolve_theme_color(ThemeManager.get_instance(), token)
            if c is not None:
                return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        from PySide6.QtGui import QColor as _QC

        if token == "gallery.accent.bar" and not _theme_is_dark():
            return _QC(*rgb)
        if token == "gallery.accent.bar":
            return _QC(0, 150, 255)
        return _QC(*rgb)
    except Exception:
        return None


class _CardHoverFilter(QObject):
    """Shows gallery_card IconActionFlyout on hover; hides on leave.

    S2-2: also toggles the 3px accent underline at the card bottom
    (mockup c4) via the toolkit whole-button underline API. Hover
    background lightening is the built-in variant hover overlay.
    """

    def __init__(self, card, owner=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(card)
        self._card = card
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._card:
            if event.type() == QEvent.Type.Enter:
                # Resolve the real owner (pool cards are built owner-less —
                # suppression is stamped on the controller, see
                # _resolve_card_owner) before consulting the post-action
                # window, and hand it to the show path so the action
                # closure captures the same owner.
                eff_owner = _resolve_card_owner(self._card, self._owner)
                _hdbg(
                    "card hover enter card=%s suppressed=%s buttons=%s ev_pos=%s",
                    getattr(getattr(self._card, "_gallery_item", None), "path", "?"),
                    _capsule_suppressed(eff_owner, self._card),
                    _mouse_buttons_int(),
                    _event_pos(event),
                )
                log_card_gates(self._card, eff_owner, "enter")
                try:
                    # Hover FX is the translucent shelf-style wash
                    # (overlay painter) — no opaque bg swap. Underline only.
                    _show_card_hover_underline(self._card)
                except Exception:
                    pass
                try:
                    from tabs.image_gallery.ui.card.delete_button import (
                        sync_card_delete_button as _sync_del,
                    )

                    self._card._gallery_delete_hovered = True  # type: ignore[attr-defined]
                    _sync_del(self._card)
                except Exception as exc:
                    _hdbg("delete sync on Enter FAILED err=%r", exc)
                try:
                    if _capsule_suppressed(eff_owner, self._card):
                        _hdbg("capsule NOT shown hide-reason=SUPPRESSED path=%s", getattr(getattr(self._card, "_gallery_item", None), "path", "?"))
                        log_card_gates(self._card, eff_owner, "show-suppressed")
                    else:
                        show_gallery_card_flyout(self._card, eff_owner)
                        log_card_gates(self._card, eff_owner, "show-done")
                except Exception as exc:
                    _hdbg("capsule show on Enter FAILED err=%r", exc)
            elif event.type() == QEvent.Type.Leave:
                try:
                    _hide_card_hover_underline(self._card)
                except Exception:
                    pass
                # Card-or-badge hover unit: the delete ✕ overhangs outside the
                # card rect, so leaving toward it keeps BOTH (its Enter is
                # imminent — the log proves capsule-hide/X-enter pairs). Only
                # a leave toward neither hides both on the same tick.
                try:
                    from tabs.image_gallery.ui.card.delete_button import (
                        card_delete_contains_cursor as _over_del,
                    )
                    from tabs.image_gallery.ui.card.delete_button import (
                        hide_card_delete_button as _hide_del,
                    )

                    self._card._gallery_delete_hovered = False  # type: ignore[attr-defined]
                    over = bool(_over_del(self._card))
                    log_card_gates(self._card, self._owner, "leave")
                    if not over:
                        _hdbg(
                            "card hover leave hide-reason=LEAVE_OUTSIDE card=%s over_delete=%s buttons=%s ev_pos=%s",
                            getattr(getattr(self._card, "_gallery_item", None), "path", "?"),
                            over,
                            _mouse_buttons_int(),
                            _event_pos(event),
                        )
                        hide_gallery_card_flyout(self._card)
                        _hide_del(self._card)
                    else:
                        _hdbg(
                            "card hover leave keep hide-reason=LEAVE_TOWARD_BADGE card=%s over_delete=%s buttons=%s ev_pos=%s",
                            getattr(getattr(self._card, "_gallery_item", None), "path", "?"),
                            over,
                            _mouse_buttons_int(),
                            _event_pos(event),
                        )
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


# -- Hover mini-capsule: IconActionFlyout pattern --------------------

def _pale_reject_color():
    """Rejected-state capsule ✕: danger hue at disabled alpha (pale, still clickable).

    Disabled via ``setEnabled(False)`` would block the un-reject click, so
    the paleness is a foreground color with the toolkit's disabled alpha
    (110, same wash as atomic checkbox/radio) instead of a state switch.
    """
    try:
        from PySide6.QtGui import QColor as _QC

        base = _capsule_icon_color("reject")
        pale = _QC(base)
        try:
            pale.setAlpha(110)
        except Exception:
            pass
        return pale
    except Exception:
        return None


def _rejected_tooltip() -> str:
    """Tooltip for the capsule ✕ on a rejected card (un-reject action)."""
    return "↩ Return"


def _gallery_card_actions_spec(include_source: bool = False, rejected: bool = False) -> list:
    """Specs for hover capsule: ★ make best · ✕ reject · ⇄ compare (+ Set as source for fidelity).

    On a rejected card the ✕ flips to the return action (pale icon +
    "↩ Return" tooltip); the ``action_id`` stays ``reject`` so the
    trigger handler (toggle) is unchanged.
    """
    try:
        from sli_ui_toolkit.widgets import IconAction

        actions = [
            IconAction(action_id="make_best", icon="star", tooltip="★ Make best"),
            IconAction(
                action_id="reject",
                icon="close",
                tooltip=_rejected_tooltip() if rejected else "✕ Reject",
            ),
            IconAction(action_id="compare", icon="compare", tooltip="⇄ Compare"),
        ]
        if include_source:
            # Fidelity only — icon "photo" exists in toolkit; tooltip uses i18n fallback.
            actions.append(IconAction(action_id="set_source", icon="photo", tooltip="Set as source"))
        return actions
    except Exception:
        return []


def ensure_gallery_card_flyout(parent: QWidget):  # type: ignore[no-untyped-def]
    """Get or create gallery_card IconActionFlyout for *parent* window.

    Group ``gallery_card`` ensures exclusive show policy via FlyoutManager.

    Sizing: the svg's 88×30 (x1022 y198) is the *visible pill*, not the
    outer widget — BaseFlyout's shell adds 2×8 shadow margins and the
    container 2×4 content padding. Clamping the outer widget to 88×30
    starved the buttons (28px each) to a 72×14 box. Compact
    ``button_size=22`` lands the visible container at 30px tall (22+2×4,
    matching the svg height); width auto-follows the action count
    (3, or 4 in fidelity mode) via ``update_state`` → ``adjustSize``.
    """
    try:
        from sli_ui_toolkit.widgets import IconActionFlyout

        # For inside positioning the flyout must be a child of the card itself, not the window.
        # Keep per-card instance to avoid cross-card leaks.
        existing = getattr(parent, "_gallery_card_flyout", None)
        if existing is not None:
            try:
                import shiboken6

                if shiboken6.isValid(existing):
                    _hdbg("capsule ensure reuse path=%s", getattr(getattr(parent, "_gallery_item", None), "path", "?"))
                    return existing
                _hdbg("capsule ensure stale (invalid) — recreating path=%s", getattr(getattr(parent, "_gallery_item", None), "path", "?"))
            except Exception:
                return existing
        flyout = IconActionFlyout(parent, button_size=22, icon_size=14)
        # Identity for GroupShowPolicy.
        try:
            flyout.flyout_group = GALLERY_CARD_FLYOUT_GROUP  # type: ignore[attr-defined]
        except Exception:
            pass
        # Hover-frequency pill: one bare show() per card Enter, and cards
        # also sweep under a stationary cursor during grid scroll. Never
        # kick window activation from it — under Wayland Qt reports
        # inactive mid-scroll, so every show would mint a stale
        # xdg-activation request and the compositor answers the storm
        # with busy-cursor feedback (MC-zoom precedent:
        # test_mc_zoom_no_busy_cursor.py). Clicks focus the pill buttons
        # naturally, so nothing is lost by staying quiet.
        try:
            flyout._no_window_activate = True  # type: ignore[attr-defined]
        except Exception:
            pass
        # Hover-only pill: never steal keyboard focus on show. The stock
        # show() grabs focus into the pill and weakens StrongFocus
        # ancestors (grid included) until hide — so Space activated the
        # focused pill button instead of deleting the selection, arrows
        # navigated within the pill instead of the grid, and Del lived or
        # died by focus-propagation luck (stale focus after rebuild churn
        # swallowed it). _skip_focus_grab also skips nav-section
        # registration, so arrows stay with the gallery while hovering.
        # Clicks still focus pill buttons naturally (and Del from there
        # propagates up to the grid), keyboard users lose nothing: every
        # pill action has a grid key (B / Space-Del / Enter-compare).
        try:
            flyout._skip_focus_grab = True  # type: ignore[attr-defined]
        except Exception:
            pass
        flyout.set_actions(_gallery_card_actions_spec())
        try:
            parent._gallery_card_flyout = flyout  # type: ignore[attr-defined]
        except Exception:
            pass
        _hdbg("capsule ensure created path=%s", getattr(getattr(parent, "_gallery_item", None), "path", "?"))
        return flyout
    except Exception as exc:
        _hdbg("capsule ensure FAILED hide-reason=ENSURE_FAIL path=%s err=%r", getattr(getattr(parent, "_gallery_item", None), "path", "?"), exc)
        return None


def show_gallery_card_flyout(card, owner=None) -> None:  # type: ignore[no-untyped-def]
    """Show hover mini-capsule anchored to *card* (IconActionFlyout, group gallery_card)."""
    try:
        flyout = ensure_gallery_card_flyout(card)
        if flyout is None:
            _hdbg(
                "capsule NOT shown hide-reason=ENSURE_FAIL path=%s",
                getattr(getattr(card, "_gallery_item", None), "path", "?"),
            )
            return

        # Fidelity mode adds "Set as source" to the capsule (A2 spec).
        # Rejected cards flip the ✕ to the return action (tooltip + pale).
        try:
            try:
                _item = getattr(card, "_gallery_item", None)
                _rejected_card = bool(getattr(_item, "rejected", False))
            except Exception:
                _rejected_card = False
            _mode = getattr(card, "_gallery_mode", None)
            if _mode is None:
                _owner_tmp = owner if owner is not None else getattr(card, "_gallery_owner", None)
                if _owner_tmp is not None:
                    st = getattr(_owner_tmp, "state", None)
                    _mode = getattr(st, "mode", None) if st is not None else getattr(_owner_tmp, "_mode", None)
            _include = False
            try:
                ms = str(_mode.value).lower() if hasattr(_mode, "value") else str(_mode).lower() if _mode is not None else ""
                _include = ms == "fidelity"
            except Exception:
                _include = False
            flyout.set_actions(
                _gallery_card_actions_spec(include_source=_include, rejected=_rejected_card)
            )
            _hdbg(
                "capsule mode mode=%r include_source=%d rejected=%d path=%s",
                ms,
                1 if _include else 0,
                1 if _rejected_card else 0,
                getattr(getattr(card, "_gallery_item", None), "path", "?"),
            )
        except Exception as exc:
            _hdbg("capsule mode-resolve FAILED err=%r", exc)

        # S2 tri-color capsule icons: star gold · cross red · swap accent
        # (painter-pipeline foreground, no QSS). Rejected cards: pale ✕.
        try:
            try:
                _item_fg = getattr(card, "_gallery_item", None)
                _rejected_fg = bool(getattr(_item_fg, "rejected", False))
            except Exception:
                _rejected_fg = False
            for _aid in ("make_best", "reject", "compare", "set_source"):
                try:
                    _btn = flyout.action_button(_aid)
                except Exception:
                    _btn = None
                if _btn is None:
                    continue
                try:
                    if _aid == "reject" and _rejected_fg:
                        _btn.setForegroundColor(_pale_reject_color())
                    else:
                        _btn.setForegroundColor(_capsule_icon_color(_aid))
                except Exception:
                    pass
        except Exception:
            pass

        # Wire actionTriggered to triage helpers.
        def _on_trigger(action_id: str, c=card, o=owner) -> None:
            def _log(msg, *args):
                _hdbg(msg, *args)

            # Resolve owner: explicit or stored on card/window.
            actual_owner = o
            if actual_owner is None:
                actual_owner = getattr(c, "_gallery_owner", None)
            if actual_owner is None:
                # Try to find controller via window.
                try:
                    win = c.window()
                    actual_owner = getattr(win, "_gallery_controller", None) or getattr(win, "_gallery_owner", None)
                except Exception:
                    actual_owner = None
            item = getattr(c, "_gallery_item", None)
            path = getattr(item, "path", None) if item is not None else None
            if path is None:
                try:
                    path = Path(str(c.property("gallery_path") or ""))
                except Exception:
                    return
            _log("capsule action %s path=%s", action_id, path)
            # Stamp suppression BEFORE triage: the rebuild below recycles
            # cards under the stationary cursor and Qt synthesizes Enter
            # mid-rebuild — the end-of-action stamp in _after_card_action
            # comes too late for those (live 2026-09-26: Enter 37 ms after
            # the click, stamp only after the rebuild finished).
            _suppress_capsule(_resolve_card_owner(c, actual_owner), c)
            try:
                if action_id == "make_best":
                    from tabs.image_gallery.use_cases import triage as _triage

                    _triage.make_best(actual_owner, path)
                    _after_card_action(c, actual_owner, f"Best: {Path(path).name}")
                elif action_id == "reject":
                    from tabs.image_gallery.use_cases import triage as _triage

                    try:
                        rejected = bool(_triage.toggle_reject(actual_owner, path))
                    except Exception:
                        _log("capsule reject raised path=%s", path, exc_info=True)
                        return
                    name = Path(path).name
                    _after_card_action(
                        c, actual_owner, f"Rejected {name}" if rejected else f"Restored {name}"
                    )
                elif action_id == "compare":
                    # Dispatch to carry/compare — reuse selection/carry flow.
                    from tabs.image_gallery.use_cases import carry as _carry

                    # Ensure selection contains this path then carry.
                    try:
                        if actual_owner is not None and hasattr(actual_owner, "state"):
                            sel = getattr(actual_owner.state, "selected_paths", set())
                            if path not in sel:
                                sel.add(path)
                    except Exception:
                        pass
                    try:
                        _carry.carry_selected(actual_owner)
                    except Exception:
                        pass
                elif action_id == "set_source":
                    # Lazy to avoid cycle.
                    from tabs.image_gallery.ui.card.context_menu import _ctx_set_source

                    _ctx_set_source(actual_owner, path)
            except Exception:
                pass

        # Connect once.
        try:
            flyout.actionTriggered.disconnect()
        except Exception:
            pass
        flyout.actionTriggered.connect(_on_trigger)
        # Show inside card top-right per svg x1022 y198 (6px from preview top, 8px from right).
        # Outer widget width = visible pill + 2×SHADOW_RADIUS(8) — position from the
        # live sizeHint (set_actions→update_state→adjustSize), never a hardcoded 88.
        try:
            flyout.setParent(card)
            try:
                flyout.update_state()
            except Exception:
                pass
            try:
                # Capsule hugs the top-right corner: half margins —
                # right 4, top 7. The delete ✕ overhangs the same corner;
                # the capsule's outer edge is transparent shadow there, so
                # the overlap stays a few px.
                flyout.move(card.width() - flyout.width() - scaled_px(4), scaled_px(7))
            except Exception:
                pass
            flyout.show()
            try:
                flyout.raise_()
            except Exception:
                pass
            try:
                from tabs.image_gallery.debug import (
                    gallery_debug_enabled as _dbg_on,
                )

                _content = _capsule_content_diag(flyout, card) if _dbg_on() else "n/a"
            except Exception:
                _content = "?"
            _hdbg(
                "capsule shown path=%s pos=(%s,%s) size=(%s,%s) content=[%s]",
                getattr(getattr(card, "_gallery_item", None), "path", "?"),
                flyout.x(),
                flyout.y(),
                flyout.width(),
                flyout.height(),
                _content,
            )
        except Exception as exc:
            _hdbg("capsule show FAILED fallback path=%s err=%r", getattr(getattr(card, "_gallery_item", None), "path", "?"), exc)
            try:
                flyout.show_above(card)
                _hdbg("capsule shown via show_above path=%s", getattr(getattr(card, "_gallery_item", None), "path", "?"))
            except Exception as exc2:
                _hdbg("capsule show_above FAILED err=%r", exc2)
                try:
                    flyout.show_for_button(card)  # type: ignore[attr-defined]
                    _hdbg("capsule shown via show_for_button path=%s", getattr(getattr(card, "_gallery_item", None), "path", "?"))
                except Exception as exc3:
                    _hdbg("capsule NOT shown hide-reason=SHOW_FAIL path=%s err=%r", getattr(getattr(card, "_gallery_item", None), "path", "?"), exc3)
    except Exception as exc:
        _hdbg("capsule show outer FAILED hide-reason=SHOW_FAIL err=%r", exc)


def _after_card_action(card, owner, notice: str | None = None) -> None:
    """Close the capsule after an action, block its instant re-show, notify.

    The grid rebuild recreates cards under the cursor — without suppression
    the fresh Enter re-opens the capsule the action just closed.
    """
    try:
        hide_gallery_card_flyout(card)
    except Exception as exc:
        _hdbg("capsule hide-after-action FAILED err=%r", exc)
    _suppress_capsule(owner, card)
    try:
        until = float(getattr(owner, "_gallery_capsule_suppress_until", 0.0) or 0.0)
    except Exception:
        until = 0.0
    if notice:
        _notify_owner_hud(owner, notice)
    _hdbg("capsule action done hide-reason=POST_ACTION_SUPPRESS suppress_until=%.3f notice=%r", until, notice)


def hide_gallery_card_flyout(card) -> None:  # type: ignore[no-untyped-def]
    try:
        flyout = ensure_gallery_card_flyout(card)
        _path = getattr(getattr(card, "_gallery_item", None), "path", "?")
        if flyout is None:
            _hdbg("capsule hide skip hide-reason=ENSURE_FAIL path=%s", _path)
            return
        if flyout.isVisible():
            flyout.hide()
            _hdbg("capsule hidden hide-reason=LEAVE path=%s", _path)
        else:
            _hdbg("capsule hide skip hide-reason=ALREADY_HIDDEN path=%s", _path)
    except Exception as exc:
        _hdbg("capsule hide FAILED err=%r", exc)
