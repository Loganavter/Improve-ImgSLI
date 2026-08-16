import logging
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Literal

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.helpers.rounded_clip import RoundedClipEffect

if TYPE_CHECKING:
    from sli_ui_toolkit.managers import FlyoutManager
    from sli_ui_toolkit.theme import ThemeManager
    from sli_ui_toolkit.ui.widgets.composite.list_panel import ListPanel

logger = logging.getLogger(__name__)

# Back-compat alias for in-package imports.
_RoundedClipEffect = RoundedClipEffect

# Shared with RatingListItem.item_type — "image" renders a thumbnail-first
# row, "simple" renders a text-only row (single-list flyout mode).
ListItemType = Literal["image", "simple"]


class _UnifiedFlyoutBase:
    """Type-only surface shared by every ``UnifiedFlyout`` mixin.

    Not a real runtime base — each mixin (bootstrap/style/layout/refresh/
    content/dragdrop) assumes ``self`` ends up being the fully-composed
    ``UnifiedFlyout(QWidget)`` (see ``__init__.py``), and reads/writes
    attributes that live in a *different* mixin or in ``QWidget`` itself.
    This class exists purely so mypy can resolve those cross-mixin
    references; it declares plain annotations only (no ``= value``), so
    nothing is created at class-definition time and it adds nothing to the
    real MRO beyond an extra ``object`` — same trick as ``ThemedWidget``
    (``ui/widgets/themed.py``), generalized to a 6-way mixin split.
    """

    # -------- constructor args (untyped on purpose — host-supplied) --------
    store: Any
    main_controller: Any
    main_window: Any

    # -------- runtime state (bootstrap.py) --------
    mode: "FlyoutMode"
    source_list_num: int
    _is_closing: bool
    item_height: int
    item_font: Any
    last_close_timestamp: float
    last_close_mode: "FlyoutMode"
    _anim: Any
    _is_simple_mode: bool
    _is_refreshing: bool
    _structure_sync_scheduled: bool
    _drag_enabled: bool
    _refresh_timer: QTimer
    flyout_manager: "FlyoutManager"
    _anchor_left: QWidget | None
    _anchor_right: QWidget | None
    _anchor_widget: QWidget | None
    _move_duration_ms: int
    _drop_offset_px: int
    overlay_layer: Any
    container_widget: QWidget
    panel_left: "ListPanel"
    panel_right: "ListPanel"
    _container_clip: Any
    _panel_left_clip: Any
    _panel_right_clip: Any
    theme_manager: "ThemeManager"

    # -------- class constants (UnifiedFlyout, __init__.py) --------
    SHADOW_RADIUS: int
    MARGIN: int
    SINGLE_PANEL_GAP_Y: int
    flyout_group: str

    # -------- signals (UnifiedFlyout, __init__.py) --------
    item_chosen: Signal
    simple_item_chosen: Signal
    item_context_menu_requested: Signal
    closing_animation_finished: Signal

    # -------- cross-mixin methods --------
    set_row_factory: Callable[[Any], None]
    _apply_style: Callable[[], None]
    _apply_container_geometry: Callable[[], None]
    start_closing_animation: Callable[..., None]
    _on_animation_finished: Callable[..., None]
    anchor_for_list: Callable[[int], QWidget | None]
    _schedule_structure_sync: Callable[[], None]
    sync_from_store: Callable[[], None]
    _on_item_selected: Callable[..., None]
    _on_item_right_clicked: Callable[..., None]
    _get_current_index: Callable[..., int]
    _get_item_rating: Callable[..., Any]
    _create_rating_gesture: Callable[..., Any]
    _increment_rating: Callable[..., None]
    _decrement_rating: Callable[..., None]
    _reorder_item: Callable[..., None]
    _move_item_between_lists: Callable[..., None]
    update_drop_indicator: Callable[..., None]
    clear_drop_indicator: Callable[..., None]
    handle_drop: Callable[..., Any]
    _sync_anchor_open_state: Callable[[int | None], None]
    _build_single_mode_geometry: Callable[..., Any]
    _position_panels_for_single: Callable[..., None]
    refreshGeometry: Callable[..., None]
    _update_geometry_in_double_mode_internal: Callable[..., None]
    _apply_refreshed_geometry: Callable[..., None]
    _apply_single_mode_refresh_geometry: Callable[..., None]
    populate: Callable[..., None]

    # -------- QWidget/QObject surface --------
    isVisible: Callable[[], bool]
    hide: Callable[[], None]
    show: Callable[[], None]
    raise_: Callable[[], None]
    resize: Callable[..., None]
    move: Callable[..., None]
    setGeometry: Callable[..., None]
    geometry: Callable[[], Any]
    rect: Callable[[], Any]
    mapFromGlobal: Callable[[Any], Any]
    mapToGlobal: Callable[[Any], Any]
    style: Callable[[], Any]
    update: Callable[..., None]
    setProperty: Callable[[str, Any], bool]
    setAttribute: Callable[..., None]
    setFocusPolicy: Callable[[Any], None]
    setGraphicsEffect: Callable[[Any], None]
    destroyed: Signal
    width: Callable[[], int]
    height: Callable[[], int]
    size: Callable[[], Any]


class FlyoutMode(Enum):
    HIDDEN = 0
    SINGLE_LEFT = 1
    SINGLE_RIGHT = 2
    DOUBLE = 3
    SINGLE_SIMPLE = 4


def items_for_list(document, list_num: int):
    """Items for side ``list_num`` (1|2).

    Prefers neutral ``list1``/``list2``; falls back to host-domain
    ``image_list1``/``image_list2`` (Improve-ImgSLI document shape).
    """
    if list_num == 1:
        items = getattr(document, "list1", None)
        if items is None:
            items = getattr(document, "image_list1", None)
    elif list_num == 2:
        items = getattr(document, "list2", None)
        if items is None:
            items = getattr(document, "image_list2", None)
    else:
        return []
    return items if items is not None else []


def current_index_for_list(document, list_num: int) -> int:
    if list_num == 1:
        return int(getattr(document, "current_index1", -1))
    if list_num == 2:
        return int(getattr(document, "current_index2", -1))
    return -1


def set_items_for_list(document, list_num: int, items) -> None:
    """Write items, preferring neutral ``list1``/``list2`` when present."""
    seq = list(items) if items is not None else []
    if list_num == 1:
        if hasattr(document, "list1"):
            document.list1 = seq
        elif hasattr(document, "image_list1"):
            document.image_list1 = seq
        return
    if list_num == 2:
        if hasattr(document, "list2"):
            document.list2 = seq
        elif hasattr(document, "image_list2"):
            document.image_list2 = seq
