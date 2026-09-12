# ShelfWidget

Self-assembling shelf chrome: a rounded, tinted two-layer panel with a
header (title) and a content host. Shared by the Session Picker Recent
shelf and the color picker's recents row — the same component, different
contents.

Source: `src/ui/widgets/shelf.py`

## Construction

| Param | Meaning |
|---|---|
| `surface_token: str = "Window"` | panel tint token |
| `content_well: bool = False` | paint the content host opaquely with the host surface color (the Session Picker's "two backings" composition) |

`set_title(text)` / `title_label()` manage the header; `content_host()`
is where contents go; `root_layout()` exposes the shelf layout.

## Inspection

Family `ShelfWidget`; state: `title`, `content_well`, `surface_token`.

Used by: Session Picker recent panel (panel/items_view/shelf_chrome) and
`RecentColorsRow`.
