# DragGhostWidget

In-window drag ghost for image/session drag & drop: translucent,
mouse-transparent widget that follows the cursor while a drag is in flight.
Host-owned (used by the drag-and-drop event layer, not a toolkit primitive).

Source: `src/ui/widgets/drag_ghost_widget.py`

## Construction

| Param | Meaning |
|---|---|
| `parent` | the window the ghost floats over |

`set_pixmap(pixmap)` sets the ghost image; `setOpacity` controls
translucency; `move(pos)` is parent-relative. `make_count_slot_pixmap`
builds the "N items" slot badge for multi-select drags.

## Inspection

Family `DragGhostWidget` (config auto-derives; transient widget, state
intentionally empty).

Used by: `events/drag_drop_handler.py`, `events/image_carry.py`.
