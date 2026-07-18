## Buttons and Controls

The toolbar sits above the canvas in a compare session. It holds the tools for that session — split line, view modes, magnifier, recording — while lists, add/save, and the settings gear live in the surrounding chrome.

### The toolbar {#toolbar}

- **Where** — a strip of icon controls above the canvas.
- **What** — toggles, value nudges, and buttons that open panels or dialogs for the active session type.
- **How dense** — depends on {{tr:settings.ui_mode}} (first-run onboarding or [Settings → Appearance](help://settings#interface)).

:::figure{side=block height=107}
![Session toolbar]({{img:ui.buttons.toolbar}})
Toolbar above the canvas.
:::

### UI modes {#ui-modes}

The same tools are laid out differently in each {{tr:settings.ui_mode}}. Pick a mode once at first run; change it later under Settings.

### {{tr:settings.ui_mode_beginner}} {#mode-beginner}

More separate buttons — one control ≈ one job. Friendly with the mouse; good for learning where each tool lives.

:::figure{side=block height=65}
![Beginner toolbar layout]({{img:ui.buttons.mode_beginner}})
{{tr:settings.ui_mode}} → {{tr:settings.ui_mode_beginner}}.
:::

### {{tr:settings.ui_mode_advanced}} {#mode-advanced}

Fewer icons. Some controls already combine a short click with a scroll (for example orientation + thickness).

:::figure{side=block height=65}
![Advanced toolbar layout]({{img:ui.buttons.mode_advanced}})
{{tr:settings.ui_mode}} → {{tr:settings.ui_mode_advanced}}.
:::

### {{tr:settings.ui_mode_expert}} {#mode-expert}

Densest strip: one control can carry click, scroll, and other mouse buttons so more of the window stays on the image.

:::figure{side=block height=65}
![Expert toolbar layout]({{img:ui.buttons.mode_expert}})
{{tr:settings.ui_mode}} → {{tr:settings.ui_mode_expert}}.
:::

### Multi-action controls {#multi-action}

In {{tr:settings.ui_mode_advanced}} and especially {{tr:settings.ui_mode_expert}}, the same icon often does more than one thing:

- **Short click** — primary action or toggle.
- **Scroll** — nudge a numeric value (divider thickness, magnifier size, …) without opening a dialog.
- **Long-press** — stronger variant on some list buttons (clear a whole list; swap both lists).
- **Other mouse buttons** (expert) — for example right-click for color or middle-click to reset on compact divider controls.

{{tr:settings.ui_mode_beginner}} keeps those jobs on separate buttons instead of stacking them.

:::figure{side=block height=44}
![Long-press on a list button]({{img:ui.buttons.long_press}})
List button — short click vs long-press.
:::

### Product examples {#examples}

- **{{tr:workspace.session_types.image_compare}}** — in denser modes, scroll divider width or magnifier size on one control; long-press clear / swap on list buttons. Details: [Lists and Panels](help://ui.lists_flyouts).
- **{{tr:workspace.session_types.multi_compare}}** — same thickness / visibility habits on grid lines (`D`).

### Find a control by name {#find-action}

Press `Ctrl+Shift+P` ({{tr:menu.find_action}}), type part of the label, then run the action or open {{tr:action.palette.learn_more}} / `Ctrl+Enter` when the row has a help topic.
