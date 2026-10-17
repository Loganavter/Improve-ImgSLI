"""Context menu for gallery card — per-card + selection actions (toolkit ContextMenu).

Package split of the former ``ui/card/context_menu.py`` per
``plan-gallery-split-2026-10-17`` (Part C6). The public surface is unchanged:
every name is re-exported here so ``from tabs.image_gallery.ui.card.context_menu
import X`` and ``import tabs.image_gallery.ui.card.context_menu as cm`` keep
working — notably ``popup_gallery_card_context_menu`` (also lazy re-exported by
``ui/card.py`` and imported by ``ui/card/__init__.py``).

Submodules by concern:

- ``translator.py`` — ``_t`` / ``_resolve_menu_translator`` / ``_bind_menu_translator``
- ``predicates.py`` — selection + target gating (``_selection_*``, ``_targets_*``, ``_is_source``)
- ``icons.py`` — ``_resolve_menu_icon`` / ``_menu_icon`` (+ ``_MENU_ICON_CACHE``)
- ``popup.py`` — ``popup_gallery_card_context_menu`` (entry point)

Right-click on a card opens a standard toolkit ``ContextMenu`` under the
cursor (``popup_at(QCursor.pos())``). The menu merges two groups:

1. Selection section (ex-HUD flyout: Analyze / Find similar) — shown only
   when a non-empty selection exists. No "clear selection" entry by design
   — deselect is Esc, menus offer actions ON the set.
2. Per-card actions mirroring the hover capsule: Make best / Reject /
   Remove from view (+ Make source, every mode), plus the manual
   grouping pair — Ungroup (dissolve into the tail) and Group (pin the
   menu-rule targets into a brand-new series; multi-select only, hidden
   when the selection is already exactly one whole series).
   Make best / Reject / Remove from view apply to the whole selection when
   the clicked card is selected (file-manager rule), else to the clicked
   card alone.
   The Reject entry tracks state: all targets rejected → "Unreject",
   otherwise "Reject".
   "Remove from view" drops the card from the grid (file on disk
   stays); selection actions never touch the grid — hence the
   separator between the sections.

Compare actions were removed from this menu (no Compare → / ⇄ Compare):
carry flows live in the stats strip / keyboard paths, not here.
Move was removed as well — carrying to another tab is drag-only (press-move
past the drag threshold on a card starts the QDrag; drop onto a workspace
tab delivers it).
"""

from __future__ import annotations

from .icons import _MENU_ICON_CACHE, _menu_icon, _resolve_menu_icon
from .popup import popup_gallery_card_context_menu
from .predicates import (
    _is_source,
    _selection_count,
    _selection_label,
    _targets_all_rejected,
    _targets_any_grouped,
    _targets_are_single_series,
)
from .translator import _bind_menu_translator, _resolve_menu_translator, _t

__all__ = [
    "_MENU_ICON_CACHE",
    "_bind_menu_translator",
    "_is_source",
    "_menu_icon",
    "_resolve_menu_icon",
    "_resolve_menu_translator",
    "_selection_count",
    "_selection_label",
    "_t",
    "_targets_all_rejected",
    "_targets_any_grouped",
    "_targets_are_single_series",
    "popup_gallery_card_context_menu",
]
