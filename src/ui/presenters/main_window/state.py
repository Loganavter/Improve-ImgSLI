def _chrome_sync(presenter):
    toolbar = getattr(getattr(presenter, "features", None), "toolbar", None)
    if toolbar is None:
        return None
    return getattr(toolbar, "chrome_sync", None)


def apply_initial_settings_to_ui(presenter):
    chrome = _chrome_sync(presenter)
    if chrome is not None:
        chrome.apply_initial_state(presenter)
    on_language_changed(presenter)


def on_store_state_changed(presenter, domain: str):
    from ui.widgets.flyout_debug import flyout_debug

    flyout_debug("on_store_state_changed(domain=%r)", domain)

    if domain == "workspace":
        from ui.presenters.main_window.workspace import (
            cover_active_session_transition,
            sync_session_mode,
            sync_workspace_tabs,
        )

        # Cover before swapping the stack page so the flash hides first paint.
        cover_active_session_transition(presenter)
        sync_workspace_tabs(presenter)
        sync_session_mode(presenter)
        chrome = _chrome_sync(presenter)
        if chrome is not None:
            chrome.on_workspace_changed(presenter)
        return

    is_viewport_domain = domain == "viewport" or domain.startswith("viewport.")
    if not is_viewport_domain and domain not in ("document", "settings"):
        return

    viewport_subdomain = (
        domain.split(".", 1)[1] if is_viewport_domain and "." in domain else None
    )
    if viewport_subdomain in {"interaction", "geometry"}:
        return

    chrome = _chrome_sync(presenter)
    if chrome is not None:
        chrome.handle_store_domain(presenter, domain)


def on_language_changed(presenter):
    """Handle non-text consequences of a language switch.

    Static text re-applies itself via the ``language_changed`` signal in
    ``sli_ui_toolkit.i18n``; this function only triggers dynamic content
    that doesn't go through ``translatable_*`` bindings.

    Workspace-page chrome (Image Compare lists, flyouts, etc.) is skipped
    while that page is stacked away — same idea as visible-only theme
    ``apply_appearance``. Call ``flush_stale_workspace_language`` when the
    page becomes current again. Button polish is not needed for text-only
    changes.
    """
    lang_code = presenter.store.settings.current_language
    from ui.presenters.main_window.workspace import configure_workspace_actions

    configure_workspace_actions(presenter)
    presenter.get_feature("settings").on_language_changed()
    if (
        hasattr(presenter.main_window_app, "tray_manager")
        and presenter.main_window_app.tray_manager
    ):
        presenter.main_window_app.tray_manager.update_language(lang_code)

    chrome = _chrome_sync(presenter)
    if chrome is not None:
        chrome.on_language_changed(presenter)

    from shared_toolkit.ui.layout_sizing import defer_dialog_geometry
    from ui.layout_geometry import apply_main_window_minimum

    defer_dialog_geometry(
        presenter.main_window_app,
        lambda: apply_main_window_minimum(presenter.main_window_app),
    )


def flush_stale_workspace_language(presenter) -> None:
    """Apply deferred language chrome when a workspace page becomes visible."""
    chrome = _chrome_sync(presenter)
    if chrome is not None:
        chrome.flush_stale_workspace_language(presenter)