"""Host-owned FlyoutManager show policy for Improve-ImgSLI.

Toolkit widgets only expose identity tags (``flyout_group``). Coexistence rules
live here so groups can be tuned without patching ``sli-ui-toolkit``.
"""

from __future__ import annotations

import inspect

from sli_ui_toolkit.managers import FlyoutManager, GroupShowPolicy

# Mutual-exclusion set: opening any of these dismisses the others.
# Context menus are intentionally excluded — they stack above other flyouts and
# close themselves on outside click / action, not when a list animates/refreshes.
# ``info_hud`` (the corner resolution/filename chips) and ``zoom_indicator``
# (the corner zoom-percent chip) are also intentionally excluded: they must
# never be a dismiss target of anything, see ``_configure_pinned_hud_rules``
# below.
_EXCLUSIVE_GROUPS = (
    "unified_list",
    "options",
    "font_settings",
    "toggle",
    "actions",
    "default",
)

_STACKING_WRAPPED = False
_TITLE_BAR_RESIZE_PATCHED = False
_BUTTON_SUPPRESS_PATCHED = False


def install_flyout_show_policy() -> GroupShowPolicy:
    """Install app dismiss/active rules on the process-wide FlyoutManager."""
    policy = GroupShowPolicy()
    # Right-click menus overlay other flyouts; do not steal active or get
    # dismissed when UnifiedFlyout refreshes/raises during open animation.
    policy.configure_group(
        "context_menu",
        dismisses=(),
        claim_active=False,
    )
    for group in _EXCLUSIVE_GROUPS:
        if group == "default":
            continue
        policy.configure_group(
            group,
            dismisses=_EXCLUSIVE_GROUPS,
            claim_active=True,
        )
    _configure_pinned_hud_rules(policy)
    # Hosts combo_interpolation, whose dropdown is an "options" flyout —
    # letting that (or any other exclusive group) dismiss this one on open
    # would close the sliders panel mid-pick. Closing is hover/timer-driven
    # instead, see MagnifierSettingsHoverController.
    policy.configure_group("magnifier_settings", dismisses=(), claim_active=False)
    # SliderHintFlyout (the small "what does this slider do" popup) is
    # unconfigured -> falls into the "default" group, whose fallback is
    # exclusive (dismiss every other open flyout). Since it's shown from
    # hover *while* the magnifier-settings panel above it is already open,
    # that fallback was closing the parent panel every time a slider hint
    # appeared. dismisses=() makes opening the hint a no-op for every other
    # flyout, matching its own hover/timer-driven lifecycle (see
    # SliderHintController).
    policy.configure_group("slider_hint", dismisses=(), claim_active=False)
    # _ScrollValueFlyout (ScrollValueButton's own wheel-nudge value popup,
    # e.g. divider/magnifier width buttons) — same "default"-fallback
    # DISMISS_ALL problem as slider_hint above, except worse: it was killing
    # every flyout on screen, including the pinned zoom/info HUD chips
    # (pinned only exempts a flyout from *its own* passive-dismiss paths,
    # not from being named/DISMISS_ALL-targeted by another flyout opening).
    policy.configure_group("scroll_value", dismisses=(), claim_active=False)

    manager = FlyoutManager.get_instance()
    manager.set_show_policy(policy)
    _install_context_menu_topmost_stacking(manager)
    _install_title_bar_resize_keeps_context_menus()
    _install_button_suppress_clears_context_menu_flag()
    return policy


def _configure_pinned_hud_rules(policy: GroupShowPolicy) -> None:
    """The corner HUD chips (``InfoHUD``/``ZoomIndicator``, ``flyout_group``
    ``"info_hud"``/``"zoom_indicator"``) must never be dismissed by another
    flyout opening.

    They are already ``pinned=True`` (see ``ui/widgets/info_hud.py`` and
    ``ui/widgets/zoom_indicator.py``), which covers outside click / wheel /
    window-deactivate / anchor-move — but pinned only protects a flyout from
    *those* passive paths; a host ``GroupShowPolicy`` can still dismiss a
    pinned flyout when another group opens (see sli-ui-toolkit's
    FLYOUT_SYSTEM.md, "Pinned flyouts"). Every ``_EXCLUSIVE_GROUPS`` member's
    dismiss set is scoped to that literal tuple, so simply not including
    these groups in it is enough to make every *other* group leave them
    alone. This call is the explicit, readable half: it stops either HUD
    from ever dismissing anything if that assumption changes (e.g.
    ``pinned`` is ever dropped from one of them).
    """
    policy.configure_group("info_hud", dismisses=(), claim_active=False)
    policy.configure_group("zoom_indicator", dismisses=(), claim_active=False)


def _title_bar_resize_needs_context_menu_patch() -> bool:
    """True for toolkit builds that still ``close_all()`` on host Resize/Move."""
    try:
        from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar
    except Exception:
        return False
    try:
        source = inspect.getsource(CustomTitleBar._hide_active_flyouts)
    except Exception:
        return False
    return "close_all" in source and "context_menu" not in source


def _install_title_bar_resize_keeps_context_menus() -> None:
    """Keep CSD File/Help menus open when opening them triggers a host Resize.

    sli-ui-toolkit ≤3.1.1 calls ``FlyoutManager.close_all()`` from
    ``CustomTitleBar`` on every host Resize/Move. A taller File menu (Open/Save
    Project) often causes exactly that resize on first open, so the click looks
    like a no-op. Newer toolkit builds already skip ``flyout_group=context_menu``.
    """
    global _TITLE_BAR_RESIZE_PATCHED
    if _TITLE_BAR_RESIZE_PATCHED:
        return
    if not _title_bar_resize_needs_context_menu_patch():
        return

    from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar

    def _hide_active_flyouts(self) -> None:
        try:
            mgr = FlyoutManager.get_instance()
            for flyout in list(getattr(mgr, "_registered_flyouts", ())):
                try:
                    if not flyout.isVisible():
                        continue
                    if getattr(flyout, "flyout_group", None) == "context_menu":
                        continue
                    if getattr(flyout, "pinned", False):
                        continue
                    flyout.hide()
                except RuntimeError:
                    getattr(mgr, "_registered_flyouts", set()).discard(flyout)
                except Exception:
                    continue
            active = getattr(mgr, "_active_flyout", None)
            if active is not None:
                try:
                    if (
                        not active.isVisible()
                        or getattr(active, "flyout_group", None) != "context_menu"
                    ):
                        mgr._active_flyout = None
                except Exception:
                    mgr._active_flyout = None
        except Exception:
            pass

    CustomTitleBar._hide_active_flyouts = _hide_active_flyouts  # type: ignore[method-assign]
    _TITLE_BAR_RESIZE_PATCHED = True


def _button_suppress_needs_paired_clear_patch() -> bool:
    """True when ``_emit_click_signals`` clears only ``_suppress_next_click``."""
    try:
        from sli_ui_toolkit.ui.widgets.buttons.button import Button
    except Exception:
        return False
    try:
        source = inspect.getsource(Button._emit_click_signals)
    except Exception:
        return False
    return "_suppress_next_context_menu" not in source


def _install_button_suppress_clears_context_menu_flag() -> None:
    """Clear paired context-menu suppress when a suppressed click is eaten.

    sli-ui-toolkit ≤3.1.1 sets both ``_suppress_next_click`` and
    ``_suppress_next_context_menu`` when dismissing a flyout via its anchor.
    Release consumes only the click flag, so the next File/Help click is
    swallowed by ``TitleBarMenuStrip`` / ``popup_context_menu_for_anchor``.
    """
    global _BUTTON_SUPPRESS_PATCHED
    if _BUTTON_SUPPRESS_PATCHED:
        return
    if not _button_suppress_needs_paired_clear_patch():
        return

    from sli_ui_toolkit.ui.widgets.buttons.button import Button

    original = Button._emit_click_signals

    def _emit_click_signals(self) -> None:
        if getattr(self, "_suppress_next_click", False):
            self._suppress_next_click = False
            if getattr(self, "_suppress_next_context_menu", False):
                self._suppress_next_context_menu = False
            return
        original(self)

    Button._emit_click_signals = _emit_click_signals  # type: ignore[method-assign]
    _BUTTON_SUPPRESS_PATCHED = True


def _install_context_menu_topmost_stacking(manager: FlyoutManager) -> None:
    """Keep visible in-window context menus above any flyout that just showed/raised.

    UnifiedFlyout animation calls ``raise_()`` without going through policy; the
    toolkit ``FlyoutManager.ensure_overlay_stacking`` covers that path. This
    wrapper is a belt-and-suspenders re-raise after ``request_show``.

    ПКМ menus opened via ``ContextMenuManager`` use ``surface="popup"`` and are
    not registered with FlyoutManager, so this only affects in-window menus
    (``show_aligned`` / button dropdowns).
    """
    global _STACKING_WRAPPED
    if _STACKING_WRAPPED:
        return
    _STACKING_WRAPPED = True
    original = manager.request_show

    def request_show(flyout):
        try:
            from ui.widgets.canvas.rhi_focus import park_keyboard_focus_off_qrhi

            park_keyboard_focus_off_qrhi()
        except Exception:
            pass
        ok = original(flyout)
        try:
            ensure = getattr(manager, "ensure_overlay_stacking", None)
            if callable(ensure):
                ensure(raised=flyout)
            else:
                from ui.context_menu.manager import get_context_menu_manager

                get_context_menu_manager().raise_active_menus()
        except Exception:
            pass
        return ok

    manager.request_show = request_show  # type: ignore[method-assign]
