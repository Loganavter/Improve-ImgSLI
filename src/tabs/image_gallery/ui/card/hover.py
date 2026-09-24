"""Hover helpers — underline + flyout capsule (painter pipeline only)."""

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
                try:
                    # Hover FX is the translucent shelf-style wash
                    # (overlay painter) — no opaque bg swap. Underline only.
                    _show_card_hover_underline(self._card)
                except Exception:
                    pass
                try:
                    if _capsule_suppressed(self._owner, self._card):
                        try:
                            from tabs.image_gallery.debug import gallery_debug as _dbg

                            _dbg("capsule show suppressed (post-action window)")
                        except Exception:
                            pass
                    else:
                        show_gallery_card_flyout(self._card, self._owner)
                except Exception:
                    pass
            elif event.type() == QEvent.Type.Leave:
                try:
                    _hide_card_hover_underline(self._card)
                except Exception:
                    pass
                try:
                    hide_gallery_card_flyout(self._card)
                except Exception:
                    pass
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

def _gallery_card_actions_spec(include_source: bool = False) -> list:
    """Specs for hover capsule: ★ make best · ✕ reject · ⇄ compare (+ Set as source for fidelity)."""
    try:
        from sli_ui_toolkit.widgets import IconAction

        actions = [
            IconAction(action_id="make_best", icon="star", tooltip="★ Make best"),
            IconAction(action_id="reject", icon="close", tooltip="✕ Reject"),
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
                    return existing
            except Exception:
                return existing
        flyout = IconActionFlyout(parent, button_size=22, icon_size=14)
        # Identity for GroupShowPolicy.
        try:
            flyout.flyout_group = GALLERY_CARD_FLYOUT_GROUP  # type: ignore[attr-defined]
        except Exception:
            pass
        flyout.set_actions(_gallery_card_actions_spec())
        try:
            parent._gallery_card_flyout = flyout  # type: ignore[attr-defined]
        except Exception:
            pass
        return flyout
    except Exception:
        return None


def show_gallery_card_flyout(card, owner=None) -> None:  # type: ignore[no-untyped-def]
    """Show hover mini-capsule anchored to *card* (IconActionFlyout, group gallery_card)."""
    try:
        flyout = ensure_gallery_card_flyout(card)
        if flyout is None:
            return

        # Fidelity mode adds "Set as source" to the capsule (A2 spec).
        try:
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
            flyout.set_actions(_gallery_card_actions_spec(include_source=_include))
        except Exception:
            pass

        # S2 tri-color capsule icons: star gold · cross red · swap accent
        # (painter-pipeline foreground, no QSS).
        try:
            for _aid in ("make_best", "reject", "compare", "set_source"):
                try:
                    _btn = flyout.action_button(_aid)
                except Exception:
                    _btn = None
                if _btn is None:
                    continue
                try:
                    _btn.setForegroundColor(_capsule_icon_color(_aid))
                except Exception:
                    pass
        except Exception:
            pass

        # Wire actionTriggered to triage helpers.
        def _on_trigger(action_id: str, c=card, o=owner) -> None:
            try:
                from tabs.image_gallery.debug import gallery_debug as _dbg
            except Exception:
                _dbg = None  # type: ignore[assignment]

            def _log(msg, *args):
                try:
                    if _dbg is not None:
                        _dbg(msg, *args)
                except Exception:
                    pass

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
                # Card 250 wide, right margin 8, top 14 (preview 8,8 +6)
                flyout.move(card.width() - flyout.width() - scaled_px(8), scaled_px(14))
            except Exception:
                pass
            flyout.show()
            try:
                flyout.raise_()
            except Exception:
                pass
        except Exception:
            try:
                flyout.show_above(card)
            except Exception:
                try:
                    flyout.show_for_button(card)  # type: ignore[attr-defined]
                except Exception:
                    pass
    except Exception:
        pass


def _after_card_action(card, owner, notice: str | None = None) -> None:
    """Close the capsule after an action, block its instant re-show, notify.

    The grid rebuild recreates cards under the cursor — without suppression
    the fresh Enter re-opens the capsule the action just closed.
    """
    try:
        hide_gallery_card_flyout(card)
    except Exception:
        pass
    _suppress_capsule(owner, card)
    if notice:
        _notify_owner_hud(owner, notice)
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg("capsule action done notice=%r", notice)
    except Exception:
        pass


def hide_gallery_card_flyout(card) -> None:  # type: ignore[no-untyped-def]
    try:
        flyout = ensure_gallery_card_flyout(card)
        if flyout is not None and flyout.isVisible():
            flyout.hide()
    except Exception:
        pass
