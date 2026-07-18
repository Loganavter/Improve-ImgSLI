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
    manager = FlyoutManager.get_instance()
    manager.set_show_policy(policy)
    _install_context_menu_topmost_stacking(manager)
    _install_title_bar_resize_keeps_context_menus()
    _install_button_suppress_clears_context_menu_flag()
    return policy


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
