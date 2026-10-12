"""Quick look helpers — thin re-export shim (split into concern modules).

The grab-bag was split per CODE_PATTERNS.md thin owner + ui/ (plain
functions taking the overlay; state stays on ``QuickLookOverlay``).
Import paths are unchanged: ``from tabs.image_gallery.ui.quick_look.helpers
import populate_preview`` keeps working via these re-exports.

Homes: ``labels_theme`` (labels + theme tokens), ``overlay_build`` (painted
chrome + ``build_overlay_ui``), ``preview`` (preview pixmaps + source dims),
``meta`` (filename meta + brief), ``headers`` (report/series headers),
``nav`` (prev/next), ``resize`` (border/ring + card re-layout).
"""

from __future__ import annotations

from tabs.image_gallery.ui.quick_look.labels_theme import (
    _is_dark_theme,
    _theme_color,
    _token_color,
    _token_rgba_qcolor,
    _set_colored_text,
    _POINT_PT_BY_PIXEL,
    _apply_point_size,
    _make_label,
)
from tabs.image_gallery.ui.quick_look.overlay_build import (
    _AccentPillHost,
    QUICK_LOOK_CARD_RADIUS_PX,
    QUICK_LOOK_NAV_GLYPH_PT,
    _CardPlate,
    _RuleWidget,
    build_overlay_ui,
)
from tabs.image_gallery.ui.quick_look.preview import (
    _thumb_pixmap,
    _fast_image_size,
    _load_scaled_pixmap,
    _source_dimensions,
    populate_preview,
)
from tabs.image_gallery.ui.quick_look.insets import (
    populate_source_inset,
)
from tabs.image_gallery.ui.quick_look.meta import (
    populate_filename_meta,
    _item_smaller_than_source,
    local_brief_fallback,
    populate_brief,
)
from tabs.image_gallery.ui.quick_look.headers import (
    populate_report_header,
    series_size_note,
)
from tabs.image_gallery.ui.quick_look.nav import (
    reposition_nav_buttons,
    nav_button_at,
    _walk_for_nav_button,
)
from tabs.image_gallery.ui.quick_look.resize import (
    reposition_grip,
    clamp_card_size,
    RESIZE_BORDER_PX,
    resize_zone_at,
    resize_cursor_for,
    apply_resize_cursor,
    _distribute_column_floors,
    relayout_report_rows,
    _repin_after_card_resize,
    _reflow_footer,
    _relayout_on_card_resize,
    handle_border_press,
    handle_border_move,
    handle_border_release,
    ring_zone_at,
    handle_ring_press,
    handle_ring_hover,
    handle_ring_release,
    trace_move,
)

__all__ = [
    "_is_dark_theme",
    "_theme_color",
    "_token_color",
    "_token_rgba_qcolor",
    "_set_colored_text",
    "_POINT_PT_BY_PIXEL",
    "_apply_point_size",
    "_make_label",
    "_AccentPillHost",
    "QUICK_LOOK_CARD_RADIUS_PX",
    "QUICK_LOOK_NAV_GLYPH_PT",
    "_CardPlate",
    "_RuleWidget",
    "build_overlay_ui",
    "_thumb_pixmap",
    "_fast_image_size",
    "_load_scaled_pixmap",
    "_source_dimensions",
    "populate_preview",
    "populate_source_inset",
    "populate_filename_meta",
    "_item_smaller_than_source",
    "local_brief_fallback",
    "populate_brief",
    "populate_report_header",
    "series_size_note",
    "reposition_nav_buttons",
    "nav_button_at",
    "_walk_for_nav_button",
    "reposition_grip",
    "clamp_card_size",
    "RESIZE_BORDER_PX",
    "resize_zone_at",
    "resize_cursor_for",
    "apply_resize_cursor",
    "_distribute_column_floors",
    "relayout_report_rows",
    "_repin_after_card_resize",
    "_reflow_footer",
    "_relayout_on_card_resize",
    "handle_border_press",
    "handle_border_move",
    "handle_border_release",
    "ring_zone_at",
    "handle_ring_press",
    "handle_ring_hover",
    "handle_ring_release",
    "trace_move",
]
