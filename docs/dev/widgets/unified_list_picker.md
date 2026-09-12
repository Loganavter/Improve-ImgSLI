# UnifiedListPicker

Unified list/flyout picker for the Image Compare session lists: a
six-mixin composition (`Bootstrap`, `Style`, `Layout`, `Refresh`,
`Content`, `DragDrop`) over `QWidget`, with selection, rating, reorder and
cross-list moves delegated to the host session handler.

Source: `src/ui/widgets/unified_list_picker/` (picker, common, bootstrap,
style, layout, refresh, content, dragdrop, session, simple_adapter)

## Construction

| Param | Meaning |
|---|---|
| `host` / `session` | picker host and session handler |
| `mode: FlyoutMode` | single/double list mode |

`create_double_list(...)` is the app's rating picker (hard-wires
`make_rating_row_factory` from `ui.widgets.rating_item`).
`SimpleUnifiedFlyoutStore` / `SimpleUnifiedFlyoutController` provide a
standalone adapter for hosts without a session handler. Signals:
`item_chosen`, `simple_item_chosen`, `item_context_menu_requested`.

## Inspection

Family `UnifiedListPicker`; state: `drag_enabled`, `flyout_group`.

Used by: image_compare transient flyouts and session loading, main-window
ui-manager bootstrap.
