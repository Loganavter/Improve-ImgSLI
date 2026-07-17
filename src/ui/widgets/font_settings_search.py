"""Find Action chrome index for ``FontSettingsFlyout``.

Controls are tagged at flyout build time; tab ``register_*_actions`` expands
the index with lazy ``ensure_visible`` targets so rows stay listed while the
flyout is closed.
"""

from __future__ import annotations

from ui.actions.search_index import PROP_GROUP, SearchIndex, SearchGroup, group

# Shared member keys — match ``FontSettingsFlyout._retranslate`` / labels.json.
_SIZE = "label.font_size"
_BOLD = "label.bold"
_OPACITY = "label.opacity"
_COLOR = "label.color"
_BACKGROUND = "label.background"
_DRAW_BG = "label.draw_text_background"
_POS_EDGES = "label.position_edges"
_POS_SPLIT = "label.position_split_line"

_CORE_MEMBERS: tuple[str, ...] = (
    _SIZE,
    _BOLD,
    _OPACITY,
    _COLOR,
    _BACKGROUND,
    _DRAW_BG,
)
_PLACEMENT_MEMBERS: tuple[str, ...] = (_POS_EDGES, _POS_SPLIT)


def font_settings_search(
    title_key: str,
    *,
    include_placement: bool = True,
) -> SearchIndex:
    """Build a SearchIndex for the text-settings flyout.

    ``title_key`` is the group / breadcrumb title (tab-specific text-settings
    action label). Placement radios are IC-only; multi_compare hides them.
    """
    members = _CORE_MEMBERS + (_PLACEMENT_MEMBERS if include_placement else ())
    return SearchIndex.of(group(title_key, *members))


def tag_font_settings_flyout(
    flyout,
    *,
    title_key: str = "font_settings",
    include_placement: bool = True,
) -> SearchGroup:
    """Tag flyout controls for Find Action resolve / pulse.

    ``title_key`` is stored as ``PROP_GROUP`` for diagnostics; contribute uses
    the tab-specific SearchIndex title for catalog labels.
    """
    index = font_settings_search(title_key, include_placement=include_placement)
    group_def = index.groups[0]
    flyout.setProperty(PROP_GROUP, group_def.title_key)
    group_def.tag_member(flyout.size_slider, _SIZE)
    group_def.tag_member(flyout.weight_slider, _BOLD)
    group_def.tag_member(flyout.opacity_slider, _OPACITY)
    group_def.tag_member(flyout.color_swatch, _COLOR)
    group_def.tag_member(flyout.bg_color_swatch, _BACKGROUND)
    group_def.tag_member(flyout.draw_bg_switch, _DRAW_BG)
    if include_placement:
        radios = getattr(flyout, "_pos_radios", None) or {}
        edges = radios.get("edges")
        split = radios.get("split_line")
        if edges is not None:
            group_def.tag_member(edges, _POS_EDGES)
        if split is not None:
            group_def.tag_member(split, _POS_SPLIT)
    return group_def
