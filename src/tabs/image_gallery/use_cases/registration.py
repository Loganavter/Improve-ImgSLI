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
