"""Host-owned FlyoutManager show policy for BlinkTable.

Toolkit widgets only expose identity tags (``flyout_group``). Coexistence rules
live here so groups can be tuned without patching ``sli-ui-toolkit``. A host
window can also declare ``flyout_scope_group`` so the untagged popups it owns
(ComboBox dropdowns and other toolkit-built surfaces, which cannot carry a tag
of their own) are grouped by window instead of all landing in ``default``.
"""

from __future__ import annotations

import inspect

from sli_ui_toolkit.managers import (
    DEFAULT_FLYOUT_GROUP,
    FlyoutManager,
    GroupShowPolicy,
    LayerStack,
    flyout_group_of,
)

# Mutual-exclusion set: opening any of these dismisses the others.
# Context menus are intentionally excluded — they stack above other flyouts and
# close themselves on outside click / action, not when a list animates/refreshes.
# ``info_hud`` (the corner resolution/filename chips) and ``zoom_indicator``
# (the corner zoom-percent chip) are also intentionally excluded: they must
# never be a dismiss target of *anything*, see ``_configure_pinned_hud_rules``
# below.
# ``default`` is the group every untagged flyout lands in. It is listed here so
# it is configured explicitly (with the same dismiss set as every other
# exclusive group) instead of falling through to ``GroupShowPolicy``'s
# DISMISS_ALL fallback — that fallback dismissed *every* visible flyout
# process-wide, HUD chips included, which is how opening an untagged flyout in
# one window (e.g. a Settings combo dropdown) hid the main window's corner
# chips.
_EXCLUSIVE_GROUPS = (
    "unified_list",
    "options",
    "font_settings",
    "toggle",
    "actions",
    "gallery_ask_ai",
    "default",
)

# Flyouts shown inside the Settings window (host scope, see
# ``_adopt_window_scope_group``). A Settings dropdown is an ordinary exclusive
# flyout: it closes the other exclusives (that is what every other exclusive
# group did to it while it was still untagged) — it is *kept out of*
# ``_EXCLUSIVE_GROUPS`` itself only so the two tuples below stay readable about
# which group is window-scoped.
_SETTINGS_GROUP = "settings"

# Dismiss target set shared by every exclusive group. One tuple, so "exclusive"
# has a single source of truth: ``default`` and ``settings`` belong to it too,
# and the HUD chips / context menu / hover hints never do.
_EXCLUSIVE_DISMISS_TARGETS = _EXCLUSIVE_GROUPS + (_SETTINGS_GROUP,)

# Groups that are given explicit rules below but are NOT part of the exclusive
# set (never dismiss each other, never claim active, or are handled one-off).
_NON_EXCLUSIVE_GROUPS = (
    "context_menu",
    "canvas_feature_settings",
    "slider_hint",
    "scroll_value",
)

# The corner HUD chips. They are undismissable by construction (coexistence
# edges to every configured group), see ``_configure_pinned_hud_rules``.
_HUD_CHIP_GROUPS = ("info_hud", "zoom_indicator")

# Attribute a top-level host window may declare to give the untagged flyouts it
# owns a group of their own (``SettingsDialog.flyout_scope_group``).
_WINDOW_SCOPE_ATTR = "flyout_scope_group"

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
    # Every exclusive group runs the same rule, ``default`` included: it
    # dismisses the exclusive set only (not the HUD chips, not the context
    # menu, not the hover hints below). Without this, an untagged flyout
    # opening anywhere — e.g. any Settings combo dropdown — hit the toolkit's
    # unconfigured-group fallback and hid every visible flyout in the process,
    # including the other window's pinned corner chips.
    for group in _EXCLUSIVE_DISMISS_TARGETS:
        policy.configure_group(
            group,
            dismisses=_EXCLUSIVE_DISMISS_TARGETS,
            claim_active=True,
        )
    _configure_pinned_hud_rules(policy)
    # Hosts a per-feature settings panel (e.g. combo_interpolation), whose own
    # dropdown is an "options" flyout — letting that (or any other exclusive
    # group) dismiss this one on open would close the panel mid-pick. Closing
    # is hover/timer-driven instead, see the owning tab's settings hover
    # controller (flyout_group="canvas_feature_settings", declared by the
    # tab-owned flyout widget).
    policy.configure_group("canvas_feature_settings", dismisses=(), claim_active=False)
    # Magnifier enable shows two flyouts at once: the bottom magnifier
    # controls (canvas_feature_settings) and the top panel-visibility
    # toggles (toggle group, via MagnifierVisibilityController). Without an
    # explicit coexistence rule the default exclusive policy would dismiss
    # whichever opened first when the second shows (seen as
    # PanelVisibilityFlyout hide 287ms after show while MagnifierSettingsFlyout
    # was still visible).
    policy.coexists_with("toggle", "canvas_feature_settings")
    # SliderHintFlyout (the small "what does this slider do" popup) used to be
    # unconfigured, so it landed in the "default" group and the then-exclusive
    # fallback closed the parent feature panel every time a hint appeared.
    # dismisses=() makes opening the hint a no-op for every other flyout,
    # matching its own hover/timer-driven lifecycle (see SliderHintController).
    policy.configure_group("slider_hint", dismisses=(), claim_active=False)
    # _ScrollValueFlyout (ScrollValueButton's own wheel-nudge value popup,
    # e.g. divider/width buttons) — same problem as slider_hint above: as an
    # untagged "default" flyout it was killing every flyout on screen,
    # including the pinned zoom/info HUD chips (pinned only exempts a flyout
    # from *its own* passive-dismiss paths, not from being dismissed by
    # another flyout opening).
    policy.configure_group("scroll_value", dismisses=(), claim_active=False)

    manager = FlyoutManager.get_instance()
    _install_overlay_layers(manager)
    manager.set_show_policy(policy)
    _install_context_menu_topmost_stacking(manager)
    _install_title_bar_resize_keeps_context_menus()
    _install_button_suppress_clears_context_menu_flag()
    return policy


def _install_overlay_layers(manager: FlyoutManager) -> None:
    """Give transient value flyouts their own layer above the base panels.

    Flyout z-order is not plain ``raise_()``: ``FlyoutManager.ensure_overlay_stacking``
    re-raises every flyout in a layer above ``base`` on each show/raise of any
    flyout (see ``layer_stack.py``). The value hints (``slider_hint`` /
    ``scroll_value``) otherwise live in ``base`` next to the settings panels
    that host their sliders, so a panel raised after the hint (e.g. on a
    per-tick store update while dragging a slider) covers the hint. Lifting
    them into their own layer keeps the hints above any base-layer panel while
    leaving ``context_menu`` topmost.
    """
    stack = (
        LayerStack(order=("base", "transient_value", "context_menu"))
        .assign_group("context_menu", "context_menu")
        .assign_group("slider_hint", "transient_value")
        .assign_group("scroll_value", "transient_value")
    )
    manager.set_layer_stack(stack)


def _configure_pinned_hud_rules(policy: GroupShowPolicy) -> None:
    """The corner HUD chips (``InfoHUD``/``ZoomIndicator``, ``flyout_group``
    ``"info_hud"``/``"zoom_indicator"``) must never be dismissed by another
    flyout opening.

    They are already ``pinned=True`` (see ``ui/widgets/glass_hud/info.py`` and
    ``ui/widgets/glass_hud/zoom.py``), which covers outside click / wheel /
    window-deactivate / anchor-move — but pinned only protects a flyout from
    *those* passive paths. The dismiss loop in ``FlyoutManager.request_show``
    consults ``pinned`` for the *showing* flyout only; a pinned flyout is
    still a legal dismiss target for whatever opens next (see sli-ui-toolkit's
    FLYOUT_SYSTEM.md, "Pinned flyouts").

    So the protection is stated from the keep-alive side, as coexistence edges
    to every group the app configures — including ``default``, which is what
    an untagged flyout (a Settings combo dropdown, say) resolves to. Edges are
    symmetric and are consulted before any dismiss set, so no configured group
    can ever dismiss a HUD chip, whether or not a future rule lists it as a
    target. Both chips still dismiss nothing and never claim "active".
    """
    protected = _EXCLUSIVE_DISMISS_TARGETS + _NON_EXCLUSIVE_GROUPS
    for hud_group in _HUD_CHIP_GROUPS:
        policy.configure_group(hud_group, dismisses=(), claim_active=False)
        for group in protected:
            if group != hud_group:
                policy.coexists_with(hud_group, group)


def _adopt_window_scope_group(flyout: object) -> None:
    """Give a group-less flyout the scope of the window it opens inside.

    Toolkit widgets that build their own popup (a ``ComboBox``'s dropdown
    overlay is the common one) carry no ``flyout_group``, so they all land in
    ``default`` and the host cannot tell an in-dialog dropdown from a canvas
    one — both used to dismiss every visible flyout process-wide. A host
    window may declare ``flyout_scope_group`` (``SettingsDialog`` declares
    ``"settings"``); an untagged flyout shown as part of that window adopts it.

    Only untagged flyouts are touched: context menus, ``options``, ``toggle``
    and the HUD chips keep their own declared group, so no dismiss rule is
    rewritten under them.
    """
    try:
        if flyout_group_of(flyout) != DEFAULT_FLYOUT_GROUP:
            return
        window_of = getattr(flyout, "window", None)
        window = window_of() if callable(window_of) else None
        scope = getattr(window, _WINDOW_SCOPE_ATTR, None)
        if isinstance(scope, str) and scope:
            flyout.flyout_group = scope
    except Exception:
        return


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

    CustomTitleBar._hide_active_flyouts = _hide_active_flyouts
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
    swallowed by ``CsdMenuStrip`` / ``popup_context_menu_for_anchor``.
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

    Button._emit_click_signals = _emit_click_signals
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
        _adopt_window_scope_group(flyout)
        try:
            from ui.canvas_infra.rhi.rhi_focus import park_keyboard_focus_off_qrhi

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

    manager.request_show = request_show