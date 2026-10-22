# DragGhostWidget

In-window drag ghost for image/session drag & drop: translucent,
mouse-transparent widget that follows the cursor while a drag is in flight.
Host-owned (used by the drag-and-drop event layer, not a toolkit primitive).

Source: `src/ui/widgets/drag_ghost_widget.py`

## Construction

| Param | Meaning |
|---|---|
| `parent` | in-content overlay parent (`get_content_overlay_layer()`) — **required**; `None` raises `ValueError`, and the message forbids the window overlay host |

`set_pixmap(pixmap)` sets the ghost image; `setOpacity` controls
translucency; `move(QPoint)` takes **global** coordinates and maps them into
the parent (`mapFromGlobal`), while non-`QPoint` args go to `QWidget.move` as
usual. `make_count_slot_pixmap` builds the "N items" slot badge for
multi-select drags.

## Inspection

Family `DragGhostWidget` (config auto-derives; transient widget, state
intentionally empty).

Used by: `ui/widgets/drag_ghost_service.py` (`GhostService`, owns the
lifecycle); the flows reach it from `events/image_carry.py` and
`events/drag_drop_handler.py`.
