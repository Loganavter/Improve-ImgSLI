## Buttons and Controls

The toolbar sits above the canvas in a compare session. It holds the tools for that session — divider, view modes, magnifier, recording — while the lists, add/save controls, and the settings gear sit in the window around it.

### The toolbar {#toolbar}

The **Toolbar** is the strip of icon controls for the active session type. Each control either toggles a feature on or off, steps a numeric value, or opens a panel or dialog.

:::figure{side=block height=107}
![Session toolbar](../../assets/ui/toolbar.jpg)
The toolbar above the canvas; its icon set changes with the active session type.
:::

### UI modes {#ui-modes}

The same tools appear in every **UI Mode**; only their layout differs. Fewer controls per mode means fewer clicks but more combinations packed onto each control. Pick a mode during the first run, or change it later in [Settings → Appearance](help://platform.settings#interface).

#### Beginner {#mode-beginner}

More separate buttons: each control does one job.

:::figure{side=block height=65}
![Beginner toolbar layout](../../assets/ui/mode_beginner.png)
Beginner layout: the same tools spread over more, single-purpose buttons.
:::

#### Advanced {#mode-advanced}

Fewer icons. Some controls already combine a short click with a scroll — for example, orientation and thickness on one control.

:::figure{side=block height=65}
![Advanced toolbar layout](../../assets/ui/mode_advanced.png)
Advanced layout: related controls share one icon, combining a click with a scroll.
:::

#### Expert {#mode-expert}

The densest strip: a single control combines a click, a scroll, and other mouse buttons.

:::figure{side=block height=65}
![Expert toolbar layout](../../assets/ui/mode_expert.png)
Expert layout: the fewest icons, each combining click, scroll, and the other mouse buttons.
:::

### Multi-action controls {#multi-action}

In **Advanced** and especially in **Expert**, the same icon often does more than one thing:

- **Short click** — primary action or toggle.
- **Scroll** — nudge a numeric value (divider thickness, magnifier size, and so on) without opening a dialog.
- **Long-press** — stronger variant on some list buttons (clear a whole list; swap both lists).
- **Other mouse buttons** — in **Expert**, for example right-click for color or middle-click to reset on compact divider controls.

Beginner keeps those jobs on separate buttons instead of stacking them.

:::figure{side=block height=44}
![Long-press on a list button](../../assets/ui/long_press.png)
A list button: a short click runs the usual action, a long-press runs the stronger one.
:::

### Find a control by name {#find-action}

Press `Ctrl+Shift+P` to open **Find Action**, type part of a label, then run the action or press `Ctrl+Enter` to open **Learn more** when the row has a help topic. This reaches every action, including ones that have no visible button.
