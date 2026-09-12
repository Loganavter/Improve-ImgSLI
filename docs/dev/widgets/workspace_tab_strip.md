# WorkspaceTabStrip

Workspace-specific behavior over the toolkit `AdaptiveTabStrip`:
browser-like close interactions. Eats mouse presses that land on a tab's
close-button slot so `QTabBar` does not activate the tab on press while the
X is being clicked; middle-click closes.

Source: `src/ui/widgets/workspace_tab_strip.py`

## Construction

`AdaptiveTabStrip` parameters; `close_policy` defaults to
`CloseButtonPolicy.ALL`.

## Inspection

Family `WorkspaceTabStrip`; state: `tab_count`, `current_index`.

Used by: the main window workspace tabs (`ui/main_window/ui.py`).
