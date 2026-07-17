"""ActionRegistry contract — unique ids, owner filter, IC targets."""

from __future__ import annotations

from types import SimpleNamespace

from core.actions.types import ActionDescriptor, ActionTarget
from tabs.image_compare.actions import register_image_compare_actions
from ui.actions.platform import register_platform_actions
from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests


def _noop() -> None:
    return None


def test_action_ids_unique_after_platform_and_ic_register():
    reset_action_registry_for_tests()
    registry = ActionRegistry()

    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        registry=registry,
    )

    widget = SimpleNamespace(
        btn_magnifier=object(),
        btn_swap=object(),
        btn_freeze=object(),
        btn_file_names=object(),
        btn_quick_save=object(),
    )
    register_image_compare_actions(
        widget=widget,
        presenter=SimpleNamespace(),
        registry=registry,
        quick_save=_noop,
    )

    ids = [a.action_id for a in registry.all_actions()]
    assert len(ids) == len(set(ids))
    assert "platform.settings" in ids
    assert "image_compare.magnifier.enabled" in ids


def test_list_for_filters_by_owner_tab():
    registry = ActionRegistry()
    registry.register(
        ActionDescriptor(
            action_id="platform.x",
            label_key="menu.settings",
            owner_tab=None,
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="image_compare.x",
            label_key="action.image_compare.magnifier",
            owner_tab="image_compare",
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="multi_compare.x",
            label_key="action.image_compare.swap",
            owner_tab="multi_compare",
            run=_noop,
        )
    )

    listed = registry.list_for(active_tab="image_compare")
    ids = {a.action_id for a in listed}
    assert ids == {"platform.x", "image_compare.x"}


def test_list_for_skips_hidden_toolbar_widgets():
    """UI-mode layout hides unused toolbar buttons — Find Action must match."""
    registry = ActionRegistry()
    visible = SimpleNamespace(isHidden=lambda: False)
    hidden = SimpleNamespace(isHidden=lambda: True)
    registry.register(
        ActionDescriptor(
            action_id="multi_compare.divider.width",
            label_key="multi_compare.action.divider_width",
            owner_tab="multi_compare",
            target=ActionTarget(widget=visible),
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="multi_compare.divider.color",
            label_key="multi_compare.action.divider_color",
            owner_tab="multi_compare",
            target=ActionTarget(widget=hidden),
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="multi_compare.divider.visible",
            label_key="multi_compare.action.divider_visible",
            owner_tab="multi_compare",
            target=ActionTarget(widget=hidden),
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="settings.page.builtin.general",
            label_key="settings.general",
            owner_tab=None,
            target=ActionTarget(ensure_visible=_noop),
            run=_noop,
        )
    )

    ids = {a.action_id for a in registry.list_for(active_tab="multi_compare")}
    assert "multi_compare.divider.width" in ids
    assert "multi_compare.divider.color" not in ids
    assert "multi_compare.divider.visible" not in ids
    assert "settings.page.builtin.general" in ids


def test_list_for_query_and_topic():
    registry = ActionRegistry()
    registry.register(
        ActionDescriptor(
            action_id="image_compare.magnifier.enabled",
            label_key="action.image_compare.magnifier",
            owner_tab="image_compare",
            topic="magnifier",
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="image_compare.swap",
            label_key="action.image_compare.swap",
            owner_tab="image_compare",
            topic="session",
            run=_noop,
        )
    )

    by_topic = registry.list_for(active_tab="image_compare", topic="magnifier")
    assert [a.action_id for a in by_topic] == ["image_compare.magnifier.enabled"]

    by_query = registry.list_for(active_tab="image_compare", query="swap")
    assert [a.action_id for a in by_query] == ["image_compare.swap"]


def test_list_for_soft_ranks_prefix_before_substring():
    registry = ActionRegistry()
    registry.register(
        ActionDescriptor(
            action_id="platform.contains_help_somewhere",
            label_key="action.misc.contains_help",
            owner_tab=None,
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="platform.help",
            label_key="menu.show_help",
            owner_tab=None,
            run=_noop,
        )
    )
    ranked = registry.list_for(active_tab=None, query="help")
    assert [a.action_id for a in ranked][0] == "platform.help"


def test_list_for_query_matches_translated_label(monkeypatch):
    """Users type UI strings («Настройки»), not i18n keys."""

    def _fake_display(key, lang=None):
        return {
            "menu.settings": "Настройки",
            "menu.show_help": "Показать справку",
        }.get(key, key)

    monkeypatch.setattr("ui.actions.registry._display_text", _fake_display)
    registry = ActionRegistry()
    registry.register(
        ActionDescriptor(
            action_id="platform.settings",
            label_key="menu.settings",
            owner_tab=None,
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="platform.help",
            label_key="menu.show_help",
            owner_tab=None,
            run=_noop,
        )
    )
    by_ru = registry.list_for(active_tab=None, query="настро")
    assert [a.action_id for a in by_ru] == ["platform.settings"]

    by_words = registry.list_for(active_tab=None, query="показать справ")
    assert [a.action_id for a in by_words] == ["platform.help"]


def test_image_compare_targets_are_explicit_widget_refs():
    registry = ActionRegistry()
    btn_magnifier = object()
    btn_swap = object()
    widget = SimpleNamespace(
        btn_magnifier=btn_magnifier,
        btn_swap=btn_swap,
        btn_freeze=object(),
        btn_file_names=object(),
        btn_quick_save=object(),
    )
    register_image_compare_actions(
        widget=widget,
        presenter=SimpleNamespace(),
        registry=registry,
        quick_save=_noop,
    )

    magnifier = registry.get("image_compare.magnifier.enabled")
    assert magnifier is not None
    assert isinstance(magnifier.target, ActionTarget)
    assert magnifier.target.widget is btn_magnifier

    swap = registry.get("image_compare.swap")
    assert swap is not None
    assert swap.target is not None
    assert swap.target.widget is btn_swap


def test_unregister_owner_clears_tab_actions_only():
    registry = ActionRegistry()
    registry.register(
        ActionDescriptor(
            action_id="platform.x",
            label_key="menu.settings",
            owner_tab=None,
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="image_compare.x",
            label_key="action.image_compare.magnifier",
            owner_tab="image_compare",
            run=_noop,
        )
    )
    registry.unregister_owner("image_compare")
    ids = {a.action_id for a in registry.all_actions()}
    assert ids == {"platform.x"}


def test_unregister_prefix_clears_matching_ids_only():
    registry = ActionRegistry()
    registry.register(
        ActionDescriptor(
            action_id="image_compare.magnifier.enabled",
            label_key="image_compare.action.magnifier",
            owner_tab="image_compare",
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="image_compare.video_editor.play",
            label_key="button.play",
            owner_tab="image_compare",
            run=_noop,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="image_compare.video_editor.export",
            label_key="action.export_video",
            owner_tab="image_compare",
            run=_noop,
        )
    )
    registry.unregister_prefix("image_compare.video_editor.")
    ids = {a.action_id for a in registry.all_actions()}
    assert ids == {"image_compare.magnifier.enabled"}


def test_image_compare_registers_expanded_catalog():
    from tabs.image_compare.actions import _SPECS, register_image_compare_actions

    registry = ActionRegistry()
    attrs = {spec.attr: object() for spec in _SPECS}
    widget = SimpleNamespace(**attrs)
    register_image_compare_actions(
        widget=widget,
        presenter=SimpleNamespace(),
        registry=registry,
        quick_save=_noop,
    )
    ids = {a.action_id for a in registry.all_actions()}
    assert len(ids) == len(_SPECS)
    assert all(a.target is not None and a.target.widget is not None for a in registry.all_actions())


def test_multi_compare_registers_toolbar_actions():
    from tabs.multi_compare.actions import register_multi_compare_actions

    registry = ActionRegistry()
    toolbar = SimpleNamespace(
        btn_add=object(),
        btn_divider_visible=object(),
        btn_divider_color=object(),
        btn_divider_width=object(),
        btn_text_settings=object(),
        btn_quick_save=object(),
    )
    footer = SimpleNamespace(btn_save=object())
    register_multi_compare_actions(toolbar=toolbar, footer=footer, registry=registry)
    ids = {a.action_id for a in registry.all_actions()}
    assert "multi_compare.add_images" in ids
    assert "multi_compare.divider.width" in ids
    assert "multi_compare.quick_save" in ids
    assert "multi_compare.save" in ids
    assert all(a.owner_tab == "multi_compare" for a in registry.all_actions())


def test_platform_registers_settings_and_workspace_actions():
    from ui.actions.platform import register_platform_actions, register_settings_page_actions

    registry = ActionRegistry()
    sections: list[str] = []
    sidebar_hits: list[str] = []
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        show_settings_section=lambda sid: sections.append(sid),
        resolve_settings_sidebar=lambda sid: sidebar_hits.append(sid) or f"row:{sid}",
        open_session_picker=_noop,
        new_image_compare=_noop,
        new_multi_compare=_noop,
        registry=registry,
    )
    ids = {a.action_id for a in registry.all_actions()}
    assert "settings.page.builtin.general" in ids
    assert "settings.page.builtin.interface" in ids
    assert "settings.page.builtin.performance" in ids
    assert "workspace.open_session_picker" in ids
    assert "workspace.new_multi_compare" in ids
    # Mirror includes tab-owned analysis once contributions are loaded
    assert "settings.page.image_compare.analysis" in ids
    analysis = registry.get("settings.page.image_compare.analysis")
    assert analysis is not None
    assert analysis.owner_tab == "image_compare"
    assert analysis.help_page == "settings"
    assert registry.get("platform.help") is not None
    assert registry.get("platform.help").help_page == "introduction"

    general = registry.get("settings.page.builtin.general")
    assert general is not None and general.target is not None
    assert callable(general.target.ensure_visible)
    assert general.target.menu_action_id is None
    assert general.target.resolve_widget() == "row:builtin.general"
    assert sidebar_hits == ["builtin.general"]

    # Re-register settings pages alone still replaces by id (no crash)
    register_settings_page_actions(
        show_settings_section=lambda sid: sections.append(sid),
        registry=registry,
    )
    registry.get("settings.page.builtin.general").run()
    assert "builtin.general" in sections
    # Without resolve hook, reveal still has ensure_visible (opens dialog)
    re_general = registry.get("settings.page.builtin.general")
    assert re_general is not None and re_general.target is not None
    assert callable(re_general.target.ensure_visible)
    assert re_general.target.resolve_widget is None
    assert re_general.target.menu_action_id is None

    perf = registry.get("settings.page.builtin.performance")
    assert perf is not None
    assert perf.description_key == "action.settings.optimization_desc"
    # Chrome lives on per-control slots, not the thin page jump row or the
    # generic group row — a "vulkan" query must surface "Vulkan" itself.
    vulkan = registry.get(
        "settings.group.builtin.performance.settings.render_backend"
        ".settings.render_backend_vulkan"
    )
    assert vulkan is not None
    assert vulkan.label_key == "settings.render_backend_vulkan"
    assert any(
        a.action_id == vulkan.action_id
        for a in registry.list_for(active_tab=None, query="vulkan")
    )

    theme = registry.get(
        "settings.group.builtin.general.settings.appearance.label.theme"
    )
    assert theme is not None
    assert theme.label_key == "label.theme"


def test_settings_page_search_keys_match_translated_chrome():
    """Find Action must hit Settings chrome by UI language (e.g. «тема»)."""
    import resources.translations as translations
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        show_settings_section=_noop,
        registry=registry,
    )

    previous = translations._manager._current_lang
    try:
        translations.emit_language_changed("ru")
        theme_hits = {
            a.action_id for a in registry.list_for(active_tab=None, query="тема")
        }
        assert (
            "settings.group.builtin.general.settings.appearance.label.theme"
            in theme_hits
        )
        vulkan_hits = {
            a.action_id for a in registry.list_for(active_tab=None, query="vulkan")
        }
        assert (
            "settings.group.builtin.performance.settings.render_backend"
            ".settings.render_backend_vulkan" in vulkan_hits
        )
    finally:
        translations._manager._current_lang = previous
        translations.emit_language_changed(previous or "en")


def test_settings_search_group_appears_in_palette_breadcrumb():
    import resources.translations as translations
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import (
        ActionRegistry,
        action_breadcrumb_text,
        reset_action_registry_for_tests,
    )

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        show_settings_section=_noop,
        registry=registry,
    )
    iface = registry.get("settings.page.builtin.interface")
    font = registry.get("settings.group.builtin.interface.settings.ui_font")
    assert iface is not None and font is not None

    previous = translations._manager._current_lang
    try:
        translations.emit_language_changed("ru")
        crumb_page = action_breadcrumb_text(iface)
        assert "Внешний вид" in crumb_page
        assert crumb_page.count("▸") == 1

        crumb_font = action_breadcrumb_text(font)
        assert "Внешний вид" in crumb_font
        assert "Шрифт" in crumb_font
        assert crumb_font.count("▸") == 2
    finally:
        translations._manager._current_lang = previous
        translations.emit_language_changed(previous or "en")


def test_settings_search_index_is_single_source_for_page_and_extras():
    from plugins.settings.pages.interface import SEARCH as IFACE_SEARCH, UI_FONT
    from plugins.settings.registry import get_settings_registry
    from plugins.settings.search import SearchIndex, group
    from tabs.image_compare.ui.settings_performance import SEARCH as PERF_EXTRA

    assert "settings.custom" in UI_FONT.keys
    assert IFACE_SEARCH.action_groups[1][0] == "settings.ui_font"
    assert "settings.custom" in IFACE_SEARCH.keys

    settings_reg = get_settings_registry()
    from plugins.settings.registry import ensure_tab_settings_contributions

    ensure_tab_settings_contributions()
    perf = next(
        s for s in settings_reg.all_sections() if s.section_id == "builtin.performance"
    )
    merged_ic = settings_reg.search_for(perf, active_tab="image_compare")
    assert "settings.render_backend_vulkan" in merged_ic.keys
    assert "settings.optimize_magnifier_movement" in merged_ic.keys
    assert PERF_EXTRA.keys

    merged_picker = settings_reg.search_for(perf, active_tab="session_picker")
    assert "settings.render_backend_vulkan" in merged_picker.keys
    assert "settings.optimize_magnifier_movement" not in merged_picker.keys

    solo = SearchIndex.of(group("settings.ui_font", "settings.custom"))
    assert solo.keys == ("settings.ui_font", "settings.custom")


def test_settings_search_keys_have_translations_in_all_langs():
    """Bare literals / missing i18n keys silently vanish from Find Action."""
    from resources.translations import tr
    from plugins.settings.registry import (
        ensure_tab_settings_contributions,
        get_settings_registry,
    )

    ensure_tab_settings_contributions()
    langs = ("en", "ru", "zh", "pt_BR")
    missing: list[str] = []
    for section in get_settings_registry().all_sections():
        for key in get_settings_registry().search_for(section, active_tab=None).keys:
            for lang in langs:
                text = tr(key, lang)
                if not text or text == key:
                    missing.append(f"{section.section_id}:{key}:{lang}")
    assert missing == [], f"untranslated settings search keys: {missing[:20]}"


def test_settings_search_matches_across_ui_languages():
    """«английский» must hit General even when the active UI language is RU."""
    import resources.translations as translations
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        show_settings_section=_noop,
        registry=registry,
    )
    previous = translations._manager._current_lang
    try:
        translations.emit_language_changed("ru")
        # A language query should hit the concrete "English" slot, not just
        # the generic "Язык" group row.
        lang_id = "settings.group.builtin.general.label.language.settings.language_en"
        for query in ("английский", "english", "english language".split()[0]):
            hits = {
                a.action_id
                for a in registry.list_for(active_tab=None, query=query)
            }
            assert lang_id in hits, query
    finally:
        translations._manager._current_lang = previous
        translations.emit_language_changed(previous or "en")


def test_empty_palette_lists_language_slot_without_query():
    """«Язык» must appear in the empty Find Action list, not only after typing."""
    import resources.translations as translations
    from ui.actions.palette.common import tr_action
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        show_settings_section=_noop,
        registry=registry,
    )
    previous = translations._manager._current_lang
    try:
        translations.emit_language_changed("ru")
        empty = registry.list_for(active_tab=None, query="")
        labels = {tr_action(a.label_key, a.label_key) for a in empty}
        ids = {a.action_id for a in empty}
        assert "settings.group.builtin.general.label.language" in ids
        assert "Язык" in labels
        assert "Шрифт интерфейса" in labels
        # Query still finds the same slot
        hits = registry.list_for(active_tab=None, query="язык")
        assert any(
            a.action_id == "settings.group.builtin.general.label.language" for a in hits
        )
    finally:
        translations._manager._current_lang = previous
        translations.emit_language_changed(previous or "en")


def test_empty_palette_lists_settings_pages_next_to_platform_settings():
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        show_settings_section=_noop,
        registry=registry,
    )
    ids = [a.action_id for a in registry.list_for(active_tab=None, query="")]
    assert "platform.settings" in ids
    assert "settings.page.builtin.general" in ids
    lang_group_id = "settings.group.builtin.general.label.language"
    lang_en_id = f"{lang_group_id}.settings.language_en"
    appearance_group_id = "settings.group.builtin.general.settings.appearance"
    assert lang_group_id in ids
    assert lang_en_id in ids
    settings_idx = ids.index("platform.settings")
    general_idx = ids.index("settings.page.builtin.general")
    lang_idx = ids.index(lang_group_id)
    lang_en_idx = ids.index(lang_en_id)
    appearance_idx = ids.index(appearance_group_id)
    interface_idx = ids.index("settings.page.builtin.interface")
    assert general_idx == settings_idx + 1
    # Group slots (and their member rows) sit directly under their page —
    # browsable without typing a query, in registration order.
    assert lang_idx == general_idx + 1
    assert lang_idx < lang_en_idx < appearance_idx
    assert interface_idx > appearance_idx
    # IC-only performance extras stay out of the empty session-picker list
    assert not any(
        i.startswith("settings.group.builtin.performance.settings.interactive")
        for i in ids
    )


def test_empty_palette_lists_concrete_settings_slots_without_query():
    """Concrete controls (e.g. "Vulkan") must browse, not just search-match."""
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        show_settings_section=_noop,
        registry=registry,
    )
    ids = {a.action_id for a in registry.list_for(active_tab=None, query="")}
    vulkan_id = (
        "settings.group.builtin.performance.settings.render_backend"
        ".settings.render_backend_vulkan"
    )
    assert vulkan_id in ids


def test_search_treats_e_and_yo_as_equivalent():
    """«темная»/«тёмная» must match the same slot regardless of ё vs е."""
    import resources.translations as translations
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        show_settings_section=_noop,
        registry=registry,
    )
    dark_id = "settings.group.builtin.general.settings.appearance.settings.dark"
    previous = translations._manager._current_lang
    try:
        translations.emit_language_changed("ru")
        # "Тёмная" (dark theme label) contains ё; both spellings must match.
        for query in ("тёмная", "темная"):
            hits = {
                a.action_id for a in registry.list_for(active_tab=None, query=query)
            }
            assert dark_id in hits, query
    finally:
        translations._manager._current_lang = previous
        translations.emit_language_changed(previous or "en")


def test_settings_extra_search_hidden_when_tab_inactive():
    import resources.translations as translations
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import (
        ActionRegistry,
        action_breadcrumb_text,
        reset_action_registry_for_tests,
    )

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        show_settings_section=_noop,
        registry=registry,
    )
    previous = translations._manager._current_lang
    try:
        translations.emit_language_changed("ru")
        interactive_id = (
            "settings.group.builtin.performance.settings.interactive_optimization"
        )
        # "лупы" ("magnifier's") lives on the concrete magnifier-movement slot,
        # not the generic group row.
        magnifier_id = f"{interactive_id}.settings.optimize_magnifier_movement"
        assert registry.get(interactive_id) is not None
        assert registry.get(magnifier_id) is not None
        assert interactive_id not in {
            a.action_id
            for a in registry.list_for(active_tab="session_picker", query="")
        }
        assert interactive_id in {
            a.action_id
            for a in registry.list_for(active_tab="image_compare", query="")
        }
        assert not any(
            a.action_id == magnifier_id
            for a in registry.list_for(active_tab="session_picker", query="луп")
        )
        assert any(
            a.action_id == magnifier_id
            for a in registry.list_for(active_tab="image_compare", query="луп")
        )
        slot = registry.get(magnifier_id)
        assert slot is not None
        # The row shows the concrete control's own name; the group stays in
        # the breadcrumb so the user still knows where it lives.
        assert action_breadcrumb_text(slot) == "Настройки ▸ Оптимизация ▸ Интерактивная оптимизация"
    finally:
        translations._manager._current_lang = previous
        translations.emit_language_changed(previous or "en")


def test_image_compare_create_service_contribute_actions():
    from tabs.image_compare.actions import _SPECS
    from tabs.image_compare.tab import ImageCompareTab

    registry = ActionRegistry()
    tab = ImageCompareTab()
    attrs = {spec.attr: object() for spec in _SPECS}
    tab._widget = SimpleNamespace(**attrs)
    assert tab.create_service("contribute_actions", registry) is True
    assert "image_compare.magnifier.enabled" in {a.action_id for a in registry.all_actions()}
    magnifier = registry.get("image_compare.magnifier.enabled")
    assert magnifier is not None
    assert magnifier.label_key.startswith("image_compare.action.")
    assert magnifier.help_page == "magnifier"
    export = registry.get("image_compare.save")
    assert export is not None
    assert export.help_page == "export"


def test_multi_compare_create_service_contribute_actions():
    from tabs.multi_compare.tab import MultiCompareTab

    registry = ActionRegistry()
    tab = MultiCompareTab()
    tab._widget = SimpleNamespace(
        toolbar=SimpleNamespace(
            btn_add=object(),
            btn_divider_visible=object(),
            btn_divider_color=object(),
            btn_divider_width=object(),
            btn_text_settings=object(),
            btn_quick_save=object(),
        ),
        footer=SimpleNamespace(btn_save=object()),
    )
    assert tab.create_service("contribute_actions", registry) is True
    ids = {a.action_id for a in registry.all_actions()}
    assert "multi_compare.add_images" in ids
    assert "multi_compare.save" in ids
    add = registry.get("multi_compare.add_images")
    assert add is not None
    assert add.label_key.startswith("multi_compare.action.")

def test_find_for_widget_walks_ancestors():
    registry = ActionRegistry()
    child = object()
    parent = SimpleNamespace(parentWidget=lambda: None)
    # emulate parentWidget chain with a tiny fake
    class _W:
        def __init__(self, parent=None):
            self._parent = parent
        def parentWidget(self):
            return self._parent

    leaf = _W()
    host = _W()
    leaf._parent = host
    host._parent = None
    registry.register(
        ActionDescriptor(
            action_id="image_compare.magnifier.enabled",
            label_key="action.image_compare.magnifier",
            owner_tab="image_compare",
            topic="magnifier",
            run=_noop,
            target=ActionTarget(widget=host),
        )
    )
    match = registry.find_for_widget(leaf, active_tab="image_compare")
    assert match is not None
    assert match.topic == "magnifier"
    assert registry.topic_for_widget(leaf, active_tab="image_compare") == "magnifier"
