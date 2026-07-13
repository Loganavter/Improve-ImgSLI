"""Install signal-based translation bindings for host-owned main window chrome."""

from __future__ import annotations

from sli_ui_toolkit.i18n import translatable_callback, translatable_tooltip

from resources.translations import tr


def install_translations(ui) -> None:
    """Bind host translations and ask tabs to bind their own UI."""
    translatable_callback(
        ui.main_window,
        lambda lang: ui.main_window.setWindowTitle(tr("app.name", lang)),
    )
    # `btn_new_session` is host-owned chrome (the workspace tab strip's "+"
    # button, always visible regardless of active tab) — bind it here, not
    # in any tab's translations, since no single tab owns it.
    translatable_tooltip(ui.btn_new_session, "tooltip.create_workspace_session")
    _install_tab_translations(ui)


def _install_tab_translations(ui) -> None:
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    registry.notify_all("install_translations", ui)
