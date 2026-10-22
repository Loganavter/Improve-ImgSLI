# WorkspaceTabStrip

Workspace-specific behavior over the toolkit `AdaptiveTabStrip`:
browser-like close interactions. Eats mouse presses that land on a tab's
close-button slot so `QTabBar` does not activate the tab on press while the
X is being clicked; middle-click closes.

Source: `src/ui/widgets/workspace_tab_strip.py`

## Construction

`AdaptiveTabStrip` parameters; `close_policy` defaults to
`CloseButtonPolicy.ALL`.

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
