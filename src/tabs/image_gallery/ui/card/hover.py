"""Hover helpers — underline + flyout capsule (painter pipeline only)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px

# Stage 2 flyout group for hover capsule (FLYOUT_SYSTEM.md).
GALLERY_CARD_FLYOUT_GROUP = "gallery_card"


def _card_idle_bg():
    """Idle card surface via theme token (RGB fallback == #383838)."""
    try:
        from PySide6.QtGui import QColor

        from sli_ui_toolkit.managers import ThemeManager
        from ui.theming import try_resolve_theme_color

        for token in ("gallery.card.background", "surface.background"):
            c = try_resolve_theme_color(ThemeManager.get_instance(), token)
            if c is not None:
                return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        from PySide6.QtGui import QColor as _QC

        return _QC(56, 56, 56)
    except Exception:
        return None


def _card_hover_bg():
    """Hovered card surface via theme token (RGB fallback == #424242, svg c4)."""
    try:
        from PySide6.QtGui import QColor

        from sli_ui_toolkit.managers import ThemeManager
        from ui.theming import try_resolve_theme_color

        for token in ("gallery.card.background.hover", "gallery.card.background"):
            c = try_resolve_theme_color(ThemeManager.get_instance(), token)
            if c is not None:
                return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        from PySide6.QtGui import QColor as _QC

        return _QC(66, 66, 66)
    except Exception:
        return None


def _capsule_icon_color(action_id: str):
    """Tri-color capsule icons (svg hover pill): star gold · cross red · swap accent."""
    fallbacks = {
        "make_best": ("gallery.status.warn", (232, 182, 76)),
        "reject": ("gallery.status.danger", (217, 48, 37)),
        "compare": ("gallery.accent.bar", (0, 150, 255)),
        "set_source": ("gallery.accent.bar", (0, 150, 255)),
    }
    token, rgb = fallbacks.get(action_id, ("gallery.accent.bar", (0, 150, 255)))
    try:
        from PySide6.QtGui import QColor

        from sli_ui_toolkit.managers import ThemeManager
        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        from PySide6.QtGui import QColor as _QC

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
                    # Hovered card bg #424242 per svg c4 (vs #383838 idle)
                    try:
                        self._card.set_override_bg_color(_card_hover_bg())
                    except Exception:
                        pass
                    try:
                        # Bg region also
                        for r in self._card.regions():
                            if r.id in ("bg", "text"):
                                self._card.update_region(r.id, override_bg_color=_card_hover_bg())
                    except Exception:
                        pass
                    _show_card_hover_underline(self._card)
                except Exception:
                    pass
                try:
                    show_gallery_card_flyout(self._card, self._owner)
                except Exception:
                    pass
            elif event.type() == QEvent.Type.Leave:
                try:
                    try:
                        self._card.set_override_bg_color(_card_idle_bg())
                    except Exception:
                        pass
                    try:
                        for r in self._card.regions():
                            if r.id in ("bg", "text"):
                                self._card.update_region(r.id, override_bg_color=_card_idle_bg())
                    except Exception:
                        pass
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
        from tabs.image_gallery.ui.card.dots import _ACCENT_TOKEN_FALLBACK, _token_color

        card.setUnderlineThickness(float(scaled_px(3)))
        card.setUnderlineTongueReach(float(scaled_px(2)))
        card.setUnderlineColor(_token_color(*_ACCENT_TOKEN_FALLBACK))
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
            try:
                if action_id == "make_best":
                    from tabs.image_gallery.use_cases import triage as _triage

                    _triage.make_best(actual_owner, path)
                elif action_id == "reject":
                    from tabs.image_gallery.use_cases import triage as _triage

                    _triage.toggle_reject(actual_owner, path)
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


def hide_gallery_card_flyout(card) -> None:  # type: ignore[no-untyped-def]
    try:
        flyout = ensure_gallery_card_flyout(card)
        if flyout is not None and flyout.isVisible():
            flyout.hide()
    except Exception:
        pass
