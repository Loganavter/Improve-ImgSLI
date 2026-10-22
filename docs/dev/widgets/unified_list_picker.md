# UnifiedListPicker

Unified list/flyout picker for the Image Compare session lists: a
six-mixin composition (`Bootstrap`, `Style`, `Layout`, `Refresh`,
`Content`, `DragDrop`) over `QWidget`, with selection, rating, reorder and
cross-list moves delegated to the host session handler.

Source: `src/ui/widgets/unified_list_picker/` (picker, common, bootstrap,
style, layout, refresh, content, dragdrop, session, simple_adapter, plus
`debug`, `double_geometry`, `nav`, `surface`)

## Construction

| Param | Meaning |
|---|---|
| `store` | Redux store |
| `main_controller` | host controller |
| `main_window` | host window (parent) |

`mode: FlyoutMode` is runtime state, not a constructor param —
`Bootstrap._initialize_runtime_state()` starts at `FlyoutMode.HIDDEN`
(`common.py` defines the enum). `create_double_list(...)` is the app's rating
picker (hard-wires `make_rating_row_factory` from `ui.widgets.rating_item`).
`SimpleUnifiedFlyoutStore` / `SimpleUnifiedFlyoutController` provide a
standalone adapter for hosts without a session handler. Signals:
`item_chosen`, `simple_item_chosen`, `item_context_menu_requested`,
`closing_animation_finished`.

## Inspection

Family `UnifiedListPicker`; state: `drag_enabled`, `flyout_group`.

Used by: image_compare transient flyouts and session loading, main-window
ui-manager bootstrap.
