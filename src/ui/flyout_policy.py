"""Host-owned FlyoutManager show policy for Improve-ImgSLI.

Toolkit widgets only expose identity tags (``flyout_group``). Coexistence rules
live here so groups can be tuned without patching ``sli-ui-toolkit``.
"""

from __future__ import annotations

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
    return policy


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
