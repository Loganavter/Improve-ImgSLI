"""Language-change broadcast reaches every i18n widget through the shared translations manager."""

from pathlib import Path


def test_language_change_is_broadcast_to_all_i18n_widgets(monkeypatch):
    from plugins.settings.controller import SettingsController

    emitted = []
    monkeypatch.setattr(
        "resources.translations.emit_language_changed", emitted.append
    )

    controller = SettingsController.__new__(SettingsController)
    controller.mutations = type(
        "_Mutations",
        (),
        {"set_settings_value": lambda *args, **kwargs: True},
    )()
    controller.presenter = None

    controller.change_language("ru")

    assert emitted == ["ru"]


def test_language_broadcast_updates_global_current_language(monkeypatch):
    import resources.translations as translations

    emitted = []
    monkeypatch.setattr(translations, "_emit_language_changed", emitted.append)
    previous = translations._manager._current_lang
    try:
        translations.emit_language_changed("ru")

        assert translations.get_current_language() == "ru"
        assert emitted == ["ru"]
    finally:
        translations._manager._current_lang = previous


def test_main_window_host_exposes_store_before_ui_setup():
    startup_source = (
        Path(__file__).parents[2] / "src" / "ui" / "main_window" / "startup.py"
    ).read_text(encoding="utf-8")

    assign_pos = startup_source.index("window._app_host.store = window.store")
    setup_pos = startup_source.index("window.ui.setupUi(window._app_host)")

    assert assign_pos < setup_pos
