# WorkspaceTabStrip

Workspace-specific behavior over the toolkit `AdaptiveTabStrip`:
browser-like close interactions. Eats mouse presses that land on a tab's
close-button slot so the tab bar does not activate the tab on press while the
X is being clicked; middle-click closes.

Source: `src/ui/widgets/workspace_tab_strip.py`

## Width regimes

The strip adds no width policy of its own — the toolkit bar decides, in this
order: natural widths; proportional compression down to a couple of glyphs
beside the close slot; horizontal scrolling (tabs back at their natural width)
with a painter-drawn chevron in a gutter on each side. Arrows step one whole
tab per click, repeat while held, and dim at the row ends; the wheel scrolls
the strip and never changes the active tab. The host's
`CloseButtonPolicy.ALL` keeps the `×` on every tab in every regime — a tab
scrolled under a gutter has its slot hidden instead of floating over the arrow.

## Construction

`AdaptiveTabStrip` parameters; `close_policy` defaults to
`CloseButtonPolicy.ALL`.

## Drag reorder (default on)

The main window switches drag-to-reorder on for its strip
(`enable_workspace_tab_reordering` in `ui/main_window/ui.py`) — no setting, no
opt-in step. The toolkit keeps `setMovable` off by default, so the app is the
one opting in; the call is guarded by `hasattr(strip, "setMovable")` because the
app may run against a released toolkit that predates the API (the strip then
keeps the click-only behaviour).

Persistence lives in `ui/presenters/main_window/workspace_tab_order.py`:
`tabMoved(from, to)` reports the tab's final index, and the strip's visible
order (read through `tabData`, i.e. session ids) is written back into the
workspace session list. That list is the single source of truth for tab order —
it is what a project file saves and restores — so there is no second store and
no persistence by index alone. The active session id is untouched, so the
current tab stays current at its new position.

`Ui_ImageComparisonApp.sync_workspace_tabs` restores that order when the strip
is (re)built: tabs are matched by session id (never by index), stale tabs are
removed, new sessions are inserted at their list position. Programmatic moves
run with `_restoring_tab_order` set, so the rebuild never reports itself as a
user drag.

## Gallery drag & drop

The gallery's tab drag-and-drop is a host-installed handler, not Qt's default:

- `set_qdrag_drop_handler(handler)` — the strip forwards drag
  enter/move/drop to the handler (`dragEnterEvent`/`dragMoveEvent`/
  `dropEvent`).
- `set_tab_dwell_switch_handler(handler)` — hover-dwell tab switching while a
  drag is held over a tab.
- `_has_gallery_mime(mime)` gates what the strip accepts; foreign mime types
  fall through to the base class.

## Inspection

Family `WorkspaceTabStrip`; state: `tab_count`, `current_index`.

Used by: the main window workspace tabs (`ui/main_window/ui.py`).
