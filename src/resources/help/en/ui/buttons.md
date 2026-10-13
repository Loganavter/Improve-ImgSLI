---
description: Understand the toolbar and how UI modes group controls.
icon: text-manipulator.svg
---
## Buttons and Controls

The toolbar holds the tools of the active session, and the **UI Mode** setting decides how many actions share one control.

### The toolbar {#toolbar}

The **Toolbar** is the strip of icon controls for the active session. Each control either toggles a feature on or off, steps a numeric value, or opens a panel or dialog. The tab contributes the set of controls, so the strip changes when you switch tabs.

:::figure{side=block height=107}
![Session toolbar](../../assets/ui/toolbar.jpg)
The toolbar above the canvas; its icon set changes with the active session.
:::

### UI modes {#ui-modes}

The same tools appear in every **UI Mode**; only their layout differs. Fewer controls per mode means fewer clicks but more combinations packed onto each control. Pick a mode during the first run, or change it later in [Settings](help://platform.settings#interface) → **Appearance**.

#### Beginner {#mode-beginner}

The default mode: each control does one job, so the tools spread over more, single-purpose buttons.

:::figure{side=block height=65}
![Beginner toolbar layout](../../assets/ui/mode_beginner.png)
Beginner layout: the same tools spread over more, single-purpose buttons.
:::

#### Advanced {#mode-advanced}

Fewer icons. Some controls combine a short click with a scroll — for example, orientation and thickness on one control.

:::figure{side=block height=65}
![Advanced toolbar layout](../../assets/ui/mode_advanced.png)
Advanced layout: related controls share one icon, combining a click with a scroll.
:::

#### Expert {#mode-expert}

The densest strip: a single control combines a click, a scroll, and the other mouse buttons.

:::figure{side=block height=65}
![Expert toolbar layout](../../assets/ui/mode_expert.png)
Expert layout: the fewest icons, each combining click, scroll, and the other mouse buttons.
:::

### Multi-action controls {#multi-action}

In **Advanced** and especially in **Expert**, the same icon often does more than one thing:

- **Short click** — primary action or toggle.
- **Scroll** — nudge a numeric value without opening a dialog.
- **Long-press** — stronger variant on some list buttons (clear a whole list; swap both lists).
- **Other mouse buttons** — in **Expert**, for example right-click for color or middle-click to hide or restore the divider on a compact divider control.

**Beginner** splits the click-plus-scroll combinations across separate single-purpose controls; the list buttons' long-press works in every mode.

:::figure{side=block height=44}
![Long-press on a list button](../../assets/ui/long_press.png)
A list button: a short click runs the usual action, a long-press runs the stronger one.
:::

### Find a control by name {#find-action}

**Find Action** (`Ctrl+Shift+P`) finds every action by part of its label, including ones with no visible button. `Ctrl+Enter` on a row opens **Learn more** when the row has a help topic.
