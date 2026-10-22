# ShelfWidget

Self-assembling shelf chrome: a rounded, tinted two-layer panel with a
header (title) and a content host. Shared by the Session Picker Recent
shelf and the color picker's recents row — the same component, different
contents. `ShelfWidget(ThemedContainer, QWidget)`: the two-layer ordering
comes from `ThemedContainer.on_theme_changed → on_theme_derived →
on_theme_children`, not from `ThemedSurface`.

Source: `src/ui/widgets/shelf/widget.py` (package `src/ui/widgets/shelf/`,
re-exported by `ui/widgets/shelf/__init__.py` — `from ui.widgets.shelf import
ShelfWidget` is the supported import).

## Construction

| Param | Meaning |
|---|---|
| `surface_token: str = "surface.background"` | panel tint token |
| `content_well: bool = False` | paint the content host opaquely with the host surface color (the Session Picker's "two backings" composition) |

`set_title(text)` / `title_label()` manage the header; `content_host()`
is where contents go. Content API: `add_header_widget(widget)`,
`add_content_widget(widget)`, `header_host()`, `navigate(key, widget)`
(the layout itself is private — there is no `root_layout()`).

## Inspection

Family `ShelfWidget`; state: `title`, `content_well`, `surface_token`.

Used by: `src/tabs/session_picker/recent/panel.py` (`RecentProjectsPanel`;
its `items_view.py` is the content) and `src/ui/widgets/color/recents.py`
(`RecentColorsRow`).
