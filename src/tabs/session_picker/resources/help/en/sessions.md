## Workspace Tabs and Session Picker

Manage sessions in the tab strip and open new compare types from the Session Picker home page.

### Session Picker {#session-picker}

- **Open** — {{tr:action.workspace.open_session_picker}} (or the add-tab control).
- **Choose** — card for {{tr:workspace.session_types.image_compare}} or {{tr:workspace.session_types.multi_compare}}.
- **Recent** — recent ``.imgsli`` projects (grid or list, sort by last opened or name). Click to reopen. Cards whose file is gone stay listed but cannot be opened. Cards show a canvas preview from ``preview.png`` inside the project when available (older packages with ``preview.jpg`` still work; otherwise the session-type icon is used). Drop a project file onto the panel to pin it to the list without opening it. Right-click to open, remove / reveal in the folder, or check [Image Properties](help://image_properties).

### Keyboard {#keyboard}

Move between cards with the arrow keys and open the focused project with `Enter` — the full list lives under [Hotkeys](help://hotkeys#keyboard-navigation).

:::figure{side=block width=420}
![Session Picker]({{img:platform.workspace.session_picker}})
{{tr:action.workspace.open_session_picker}} — {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}.
:::

### Open a session without the picker {#new-session-actions}

From {{tr:menu.find_action}} (`Ctrl+Shift+P`):

- {{tr:action.workspace.new_image_compare}}
- {{tr:action.workspace.new_multi_compare}}

{{tr:action.workspace.open_session_picker}} returns you to the home page when you want to choose visually.

### Tab strip {#tab-strip}

- **Switch** — click a tab.
- **Close** — removes that session; if it was the last one, the Session Picker opens instead of quitting.
- **Context menu** — rename, close, or close other tabs.

### Rename a tab {#rename}

Use the tab context menu rename action, enter a name, and confirm. Auto titles stay language-aware until you set a custom name.

### Next topics {#next-topics}

Quick workflows: [Getting Started](help://introduction). Session tools: [Comparison](help://comparison) or [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).
