"""Settings-section + Find Action registration for ``ImageGalleryTab``.

Stage 2 doc says ``ui/settings_ai.py`` returns — SettingsContribution with
section base_url/api_key/model (ambient, order 30).

Wave-action-context (2026-10-20): the Find Action descriptors no longer close
over the controller and re-derive a scope. Each id maps to a handler taking an
``ActionContext`` (``GALLERY_ACTION_HANDLERS``); the descriptor's ``run`` builds
ONE context from the live tab (``origin="action"``) and calls the handler. A
refused action (empty scope, ambiguous single-target pick, nothing configured)
is a named :class:`~tabs.image_gallery.use_cases.action_context.Refusal`, never
a silent "act on something else".
"""

from __future__ import annotations

from tabs.image_gallery.use_cases.action_context import (
    REFUSAL_AMBIGUOUS_SCOPE,
    REFUSAL_EMPTY_SCOPE,
    REFUSAL_NO_HANDLER,
    ActionContext,
    Refusal,
    build_context,
)


def _make_gallery_sections(tab):  # type: ignore[no-untyped-def]
    try:
        from tabs.image_gallery.ui.settings_ai import SECTION as AI_SECTION

        # Resolve icon to gallery icon if SECTION.icon is None
        if getattr(AI_SECTION, "icon", None) is None:
            try:
                from dataclasses import replace
                from functools import partial

                from sli_ui_toolkit.icons import lazy_icon
                from tabs.image_gallery.icons import Icon, get_icon

                # Lazy handle: the settings sidebar re-resolves the section icon
                # on theme change; an eager QIcon froze at registration time.
                patched = replace(
                    AI_SECTION,
                    icon=lazy_icon(partial(get_icon, Icon.GALLERY)),
                )
                return (patched,)
            except Exception:
                return (AI_SECTION,)
        return (AI_SECTION,)
    except Exception:
        return ()


def build_settings_contribution(tab):  # type: ignore[no-untyped-def]
    """Return typed ``SettingsContribution`` for ``image_gallery``."""
    from plugins.settings.registry import SettingsContribution

    return SettingsContribution(
        owner_tab=tab.session_type,
        sections=_make_gallery_sections(tab),
        extras=(),
    )


def register_settings(tab, registry) -> None:
    contrib = build_settings_contribution(tab)
    for section in contrib.sections:
        registry.add(section)
    for extra in contrib.extras:
        registry.add_section_extra(
            extra.section_id,
            extra.build,
            owner_tab=contrib.owner_tab,
            order=extra.order,
            search=extra.search,
        )


def _tab_tr(tab):
    """Reuse the tab's existing context translator (no new resolver).

    ``tab._widget._context._tr`` — the only translator source
    (``_gallery_context`` was a never-assigned legacy alias); ``None`` when
    the widget/context is not wired yet.
    """
    try:
        ctx = getattr(getattr(tab, "_widget", None), "_context", None)
        tr = getattr(ctx, "_tr", None) if ctx is not None else None
        if tr is not None:
            return tr
    except Exception:
        pass
    return None


def build_topology_overlays(tab, parent):
    """Build + show this tab's grandfathered window-parented modals.

    Topology conformity hook: return the overlays as a list. Fail-open:
    no parent means no overlay.
    """
    if parent is None:
        return []
    from tabs.image_gallery.ui.clean_review import CleanReviewOverlay
    from tabs.image_gallery.ui.quick_look import QuickLookOverlay

    translate = _tab_tr(tab)
    overlays = [
        QuickLookOverlay(parent, translate=translate),
        CleanReviewOverlay(parent, translate=translate),
    ]
    for overlay in overlays:
        overlay.show_overlay()
    return overlays


def build_clipboard_service(tab, store, main_controller):
    """Clipboard paste service bound to this tab's gallery controller."""
    if tab._controller is None:
        return None
    from tabs.image_gallery.services.clipboard import ClipboardService

    return ClipboardService(store, main_controller, tab._controller)


# -- Find Action handlers (all take the ONE ActionContext) -------------------


def _no_handler(ctx: ActionContext, what: str) -> Refusal:
    return Refusal(REFUSAL_NO_HANDLER, ctx.targets, f"no {what} handler is attached")


def _action_keep_best(tab, ctx: ActionContext):
    """Keep the best card of every series (a pool-wide action, not a scope one)."""
    ctrl = getattr(tab, "_controller", None)
    if ctrl is None:
        return _no_handler(ctx, "keep-best")
    return ctrl.keep_best_of_series()


def _action_clean_rejected(tab, ctx: ActionContext):
    ctrl = getattr(tab, "_controller", None)
    if ctrl is None:
        return _no_handler(ctx, "clean-rejected")
    ctrl.show_clean_review()
    return None


def _action_run_triage(tab, ctx: ActionContext):
    ctrl = getattr(tab, "_controller", None)
    folder = getattr(getattr(ctrl, "state", None), "folder", None)
    if ctrl is None or folder is None:
        return _no_handler(ctx, "triage")
    ctrl.open_folder(folder)
    return None


def _action_set_as_source(tab, ctx: ActionContext):
    """Set the ONE target as source; a multi-selection is refused, not guessed."""
    if ctx.is_empty:
        return Refusal(REFUSAL_EMPTY_SCOPE, (), "no targets were resolved")
    if len(ctx.targets) != 1:
        return Refusal(
            REFUSAL_AMBIGUOUS_SCOPE,
            ctx.targets,
            "set-as-source needs exactly one target (a selection is ambiguous)",
        )
    ctrl = getattr(tab, "_controller", None)
    wid = getattr(tab, "_widget", None)
    sel = ctx.targets[0]
    try:
        # Same hooks path as the overlay setSource signal and the card menu:
        # stale-keys + fidelity re-run (never a bare state write).
        from tabs.image_gallery.ui.quick_look_hooks import (
            on_quick_set_source as _ql_set_source,
        )

        _ql_set_source(wid if wid is not None else ctrl, sel)
        return None
    except Exception:
        # Fallback: route through the controller entry point (dispatch +
        # mirror), never a bare write.
        try:
            ctrl.set_source(sel)
            return None
        except Exception:
            return _no_handler(ctx, "source")


def _action_reset_metrics(tab, ctx: ActionContext):
    from tabs.image_gallery.use_cases import gallery_actions

    owner = getattr(tab, "_controller", None) or getattr(tab, "_widget", None)
    if owner is None:
        return _no_handler(ctx, "metrics-reset")
    return gallery_actions.reset_metrics(owner, ctx)


#: The gallery's action inventory. EVERY id registered below must resolve here
#: with a ``(tab, ctx)`` signature — enforced by
#: ``tests/contracts/test_gallery_action_context.py``.
GALLERY_ACTION_HANDLERS = {
    "gallery.keep-best-of-series": _action_keep_best,
    "gallery.clean-rejected": _action_clean_rejected,
    "gallery.run-triage": _action_run_triage,
    "gallery.set-as-source": _action_set_as_source,
    "gallery.reset-metrics": _action_reset_metrics,
}


def handler_for(action_id: str):
    """The ``ActionContext`` handler registered for *action_id*, or None."""
    return GALLERY_ACTION_HANDLERS.get(action_id)


def run_action(tab, action_id: str):
    """Build the ONE action context for *tab* and run *action_id*.

    No controller/widget means no owner: a refused no-op (the registry is
    executed at startup by MCP, before a folder exists). An empty scope is a
    ``build_context`` result, and the handler refuses it by name.
    """
    handler = handler_for(action_id)
    owner = getattr(tab, "_controller", None) or getattr(tab, "_widget", None)
    if handler is None or owner is None:
        return None
    ctx = build_context(owner, origin="action")
    return handler(tab, ctx)


def _run_for(action_id: str, tab):
    return lambda: run_action(tab, action_id)


def _action_descriptors(tab):
    """Descriptor rows for the gallery Find Action topic (ctx handlers bound)."""
    from core.actions.types import ActionDescriptor, ActionTarget
    from tabs.image_gallery.actions import (
        GALLERY_CLEAN_REJECTED,
        GALLERY_KEEP_BEST,
        GALLERY_RESET_METRICS,
        GALLERY_RUN_TRIAGE,
        GALLERY_SET_AS_SOURCE,
    )

    wid = tab._widget
    target = ActionTarget(widget=wid) if wid is not None else None

    def row(action_id, label_key, *, description_key=None, topic="triage", help_page=None):
        return ActionDescriptor(
            action_id=action_id,
            label_key=label_key,
            description_key=description_key,
            breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
            owner_tab=tab.session_type,
            topic=topic,
            shortcut=None,
            help_page=help_page,
            run=_run_for(action_id, tab),
            target=target,
        )

    return (
        row(
            GALLERY_KEEP_BEST,
            "image_gallery.action.keep_best",
            description_key="image_gallery.action.keep_best_desc",
            help_page="workspace.image_gallery.triage",
        ),
        row(
            GALLERY_CLEAN_REJECTED,
            "image_gallery.action.clean_rejected",
            description_key="image_gallery.action.clean_rejected_desc",
            help_page="workspace.image_gallery.triage",
        ),
        row(
            GALLERY_RUN_TRIAGE,
            "image_gallery.action.run_triage",
            help_page="workspace.image_gallery.triage",
        ),
        row(
            GALLERY_SET_AS_SOURCE,
            "image_gallery.action.set_as_source",
            help_page="workspace.image_gallery.quality",
        ),
        row(
            GALLERY_RESET_METRICS,
            "image_gallery.card.reset_metrics_cache",
            topic="cache",
            help_page="workspace.image_gallery.triage",
        ),
    )


def register_actions(tab, registry) -> None:
    """Register real Find Action descriptors for the gallery triage topic.

    Find Action ids: gallery.keep-best-of-series etc (design.md:129). The
    widget handles keyPressEvent too. Every descriptor routes through a
    context-taking handler; none of them reads the selection itself.
    """
    try:
        for descriptor in _action_descriptors(tab):
            registry.register(descriptor)
        return True
    except Exception:
        # Fallback: ensure stubs exist via actions helper.
        try:
            from tabs.image_gallery.actions import register_gallery_action_stubs

            register_gallery_action_stubs(registry)
            return True
        except Exception:
            return None
