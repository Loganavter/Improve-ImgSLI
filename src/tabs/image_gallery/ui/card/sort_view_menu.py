"""FM-style Sort by / View submenus for the gallery card context menu.

Split out of ``ui/card/context_menu.py`` per CODE_PATTERNS (file-size
policy): the submenu builders + dispatcher live here, the card menu only
appends the sections when the caller wires toolbar callbacks. State and
sorting itself stay with the toolbar (``set_sort_index`` /
``set_view_list``); this module never sorts, it only mirrors + drives.
"""

from __future__ import annotations


def _t(translate, key: str, default: str) -> str:
    if translate is None:
        return default
    try:
        return translate(key, default)
    except Exception:
        try:
            return translate(key)  # type: ignore[call-arg]
        except Exception:
            return default


SORT_OPTIONS = (
    ("gallery.sort.rank", "image_gallery.sort_rank", "Rank", 0),
    ("gallery.sort.name", "image_gallery.sort_name", "Name", 1),
    ("gallery.sort.date", "image_gallery.sort_date", "Date", 2),
    ("gallery.sort.quality", "image_gallery.sort_quality", "AI quality", 3),
)

VIEW_OPTIONS = (
    ("gallery.view.grid", "image_gallery.view_grid", "Grid", False),
    ("gallery.view.list", "image_gallery.view_list", "List", True),
)


def _submenu_icons():
    """Per-entry icon for the Sort/View submenu (product rule: every entry has one)."""
    from tabs.image_gallery.icons import Icon

    return {
        "gallery.sort_by": "text_filename.svg",
        "gallery.sort.rank": "star.svg",
        "gallery.sort.name": "text_filename.svg",
        "gallery.sort.date": "sync.svg",
        "gallery.sort.quality": Icon.ALGORITHMS,
        "gallery.view": Icon.VIEW_GRID,
        "gallery.view.grid": Icon.VIEW_GRID,
        "gallery.view.list": Icon.VIEW_LIST,
    }


def sort_view_sections(  # type: ignore[no-untyped-def]
    translate, sort_index: int | None, view_is_list: bool | None
) -> list:
    """Build Sort by / View submenu entries (each preceded by a separator)."""
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator

    icons = _submenu_icons()
    sections: list = []
    if sort_index is not None:
        try:
            cur = int(sort_index)
        except Exception:
            cur = -1
        sections.append(ContextMenuSeparator())
        sections.append(
            ContextMenuAction(
                "gallery.sort_by",
                _t(translate, "image_gallery.sort_by", "Sort by"),
                icon=icons.get("gallery.sort_by"),
                children=tuple(
                    ContextMenuAction(
                        action_id,
                        _t(translate, key, default),
                        icon=icons.get(action_id),
                        data=index,
                        checkable=True,
                        checked=cur == index,
                    )
                    for action_id, key, default, index in SORT_OPTIONS
                ),
            )
        )
    if view_is_list is not None:
        try:
            is_list = bool(view_is_list)
        except Exception:
            is_list = False
        sections.append(ContextMenuSeparator())
        sections.append(
            ContextMenuAction(
                "gallery.view",
                _t(translate, "image_gallery.view", "View"),
                icon=icons.get("gallery.view"),
                children=tuple(
                    ContextMenuAction(
                        action_id,
                        _t(translate, key, default),
                        icon=icons.get(action_id),
                        data=is_list_value,
                        checkable=True,
                        checked=is_list == is_list_value,
                    )
                    for action_id, key, default, is_list_value in VIEW_OPTIONS
                ),
            )
        )
    return sections


def popup_empty_context_menu(  # type: ignore[no-untyped-def]
    parent_widget,
    global_pos,
    translate,
    sort_index: int | None,
    on_sort_index,
    view_is_list: bool | None,
    on_view_toggled,
):
    """Popup Sort by / View menu for empty canvas (FM background menu).

    Only the wired sections are shown (a section needs its callback).
    """
    from PySide6.QtGui import QCursor as _QCursor

    from ui.context_menu.manager import open_context_menu_entries

    entries = sort_view_sections(
        translate,
        sort_index if callable(on_sort_index) else None,
        view_is_list if callable(on_view_toggled) else None,
    )
    if not entries:
        return None

    def _on_triggered(action_id: str, data: object) -> None:
        try:
            from tabs.image_gallery.debug import gallery_debug as _dbg

            _dbg("empty menu triggered action=%s data=%r", action_id, data)
        except Exception:
            pass
        try:
            handle_sort_view_action(action_id, data, on_sort_index, on_view_toggled)
        except Exception:
            pass

    try:
        pos = global_pos if global_pos is not None else _QCursor.pos()
    except Exception:
        pos = global_pos
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg("empty menu open n=%d", len(entries))
    except Exception:
        pass
    try:
        return open_context_menu_entries(
            source_widget=parent_widget,
            global_pos=pos,
            entries=tuple(entries),
            key=("gallery-empty",),
            on_triggered=_on_triggered,
        )
    except Exception:
        return None


def handle_sort_view_action(  # type: ignore[no-untyped-def]
    action_id: str,
    data: object,
    on_sort_index=None,
    on_view_toggled=None,
) -> bool:
    """Dispatch a Sort by / View submenu action; True when handled."""
    if action_id in ("gallery.sort.rank", "gallery.sort.name", "gallery.sort.date", "gallery.sort.quality"):
        if not callable(on_sort_index):
            return False
        try:
            on_sort_index(int(data))  # type: ignore[operator]
        except Exception:
            pass
        return True
    if action_id in ("gallery.view.grid", "gallery.view.list"):
        if not callable(on_view_toggled):
            return False
        try:
            on_view_toggled(bool(data))
        except Exception:
            pass
        return True
    return False
