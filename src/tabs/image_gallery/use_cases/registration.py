"""Settings-section registration for ``ImageGalleryTab`` (Stage 2/3 returns).

Stage 2 doc says ``ui/settings_ai.py`` returns — SettingsContribution with
section base_url/api_key/model (ambient, order 30).
"""

from __future__ import annotations


def _make_gallery_sections(tab):  # type: ignore[no-untyped-def]
    try:
        from tabs.image_gallery.ui.settings_ai import SECTION as AI_SECTION

        # Resolve icon to gallery icon if SECTION.icon is None
        if getattr(AI_SECTION, "icon", None) is None:
            try:
                from tabs.image_gallery.icons import Icon, get_icon

                # Patch icon onto section (dataclass is frozen — recreate)
                from dataclasses import replace

                patched = replace(AI_SECTION, icon=get_icon(Icon.GALLERY))
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

    ``tab._widget._context._tr`` first, then the legacy
    ``tab._gallery_context._tr`` fallback; ``None`` when neither is wired.
    """
    try:
        ctx = getattr(getattr(tab, "_widget", None), "_context", None)
        tr = getattr(ctx, "_tr", None) if ctx is not None else None
        if tr is not None:
            return tr
    except Exception:
        pass
    try:
        ctx = getattr(tab, "_gallery_context", None)
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


def register_actions(tab, registry) -> None:
    """Register real Find Action descriptors for the gallery triage topic."""
    # Find Action ids stubs: gallery.keep-best-of-series etc (design.md:129).
    # Thin delegation to use_cases/triage; widget handles keyPressEvent too.
    # Register real descriptors when a page exists; otherwise stubs.
    try:
        from tabs.image_gallery.actions import (
            GALLERY_CLEAN_REJECTED,
            GALLERY_KEEP_BEST,
            GALLERY_RUN_TRIAGE,
            GALLERY_SET_AS_SOURCE,
        )
        from core.actions.types import ActionDescriptor, ActionTarget

        # Helper to get controller/widget if available.
        ctrl = tab._controller
        wid = tab._widget
        # keep-best
        registry.register(
            ActionDescriptor(
                action_id=GALLERY_KEEP_BEST,
                label_key="image_gallery.action.keep_best",
                description_key="image_gallery.action.keep_best_desc",
                breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
                owner_tab=tab.session_type,
                topic="triage",
                shortcut=None,
                help_page="workspace.image_gallery.triage",
                run=lambda: getattr(ctrl, "keep_best_of_series", lambda: None)(),
                target=ActionTarget(widget=wid) if wid is not None else None,
            )
        )
        # clean-rejected → open S3 overlay
        registry.register(
            ActionDescriptor(
                action_id=GALLERY_CLEAN_REJECTED,
                label_key="image_gallery.action.clean_rejected",
                description_key="image_gallery.action.clean_rejected_desc",
                breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
                owner_tab=tab.session_type,
                topic="triage",
                shortcut=None,
                help_page="workspace.image_gallery.triage",
                run=lambda: getattr(ctrl, "show_clean_review", lambda: None)(),
                target=ActionTarget(widget=wid) if wid is not None else None,
            )
        )
        # run-triage → reopen folder (rerun clustering)
        def _run_triage():
            try:
                if ctrl is not None and getattr(ctrl.state, "folder", None) is not None:
                    ctrl.open_folder(ctrl.state.folder)
            except Exception:
                pass

        registry.register(
            ActionDescriptor(
                action_id=GALLERY_RUN_TRIAGE,
                label_key="image_gallery.action.run_triage",
                description_key=None,
                breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
                owner_tab=tab.session_type,
                topic="triage",
                shortcut=None,
                help_page="workspace.image_gallery.triage",
                run=_run_triage,
                target=ActionTarget(widget=wid) if wid is not None else None,
            )
        )
        # set-as-source — same hooks path as the overlay setSource
        # signal and the card context menu: stale-keys + fidelity
        # re-run (never a bare state write; action id/UX unchanged).
        def _set_as_source():
            try:
                sel = None
                if ctrl is not None and hasattr(ctrl.state, "selected_paths"):
                    sel = next(iter(ctrl.state.selected_paths), None)
                if sel is None:
                    return
                try:
                    from tabs.image_gallery.ui.quick_look_hooks import (
                        on_quick_set_source as _ql_set_source,
                    )

                    owner = wid if wid is not None else ctrl
                    _ql_set_source(owner, sel)
                except Exception:
                    # Fallback: route through the controller entry
                    # point (dispatch + mirror), never a bare write.
                    try:
                        ctrl.set_source(sel)
                    except Exception:
                        pass
            except Exception:
                pass

        registry.register(
            ActionDescriptor(
                action_id=GALLERY_SET_AS_SOURCE,
                label_key="image_gallery.action.set_as_source",
                description_key=None,
                breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
                owner_tab=tab.session_type,
                topic="triage",
                shortcut=None,
                help_page="workspace.image_gallery.quality",
                run=_set_as_source,
                target=ActionTarget(widget=wid) if wid is not None else None,
            )
        )
        return True
    except Exception:
        # Fallback: ensure stubs exist via actions helper.
        try:
            from tabs.image_gallery.actions import register_gallery_action_stubs

            register_gallery_action_stubs(registry)
            return True
        except Exception:
            return None
