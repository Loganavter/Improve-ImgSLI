# UI layout dump

Headless, machine-readable snapshot of the live widget tree: class, object
name, geometry, visibility, layout type, and the [Find Action](ACTIONS.md)
ids bound to each widget.

## Why

`ActionRegistry` (see [ACTIONS.md](ACTIONS.md)) already catalogs *what* the
app can do — every command has an id, label, shortcut, and (for chrome
targets) a live widget ref. It says nothing about *where* those controls sit
relative to each other. `UI Inspector` ([UI_INSPECTOR.md](UI_INSPECTOR.md))
answers that interactively for one widget at a time (`Shift+LeftClick`), but
it's a human-driven diagnostic tool, not something to script.

This dump combines both: a recursive tree of **every top-level window in the
process** — main window, plus Settings / Help / Video Editor / Export /
whatever else is currently open — each node tagged with the exact-match
action id(s) whose `ActionTarget.widget` is that widget. One JSON file
answers "what does the interface look like" and "what does each piece do"
together — intended for external/agent consumption, not for humans clicking
through a panel.

`UI Inspector` has two buttons wrapping the same `dump_ui_layout()` (see
[UI_INSPECTOR.md](UI_INSPECTOR.md#architecture)), for interactive dumps
without a CLI restart:

- **Dump widget** — dumps **only the selected widget's subtree** (with a
  `path` field listing the ancestor chain down to it, instead of the whole
  window): a focused view of one widget's layout. Falls back to the whole
  last-focused window if nothing is selected.
- **Dump window** — dumps the whole last-focused window tree (the original
  one-window behavior), regardless of selection.

## Usage

```bash
./launcher.sh run --dump-ui-layout /path/to/layout.json
```

Boots the app normally (offscreen-safe: `QT_QPA_PLATFORM=offscreen` works),
waits one settled event-loop turn after the window is shown, writes the tree,
then exits — no interaction required.

Startup lands on the Session Picker, not a workspace tab — a dump taken cold
only has host/platform `action_ids` (see [Output shape](#output-shape)
caveat below). To dump a specific tab's own chrome, either open an existing
project:

```bash
./launcher.sh run --dump-ui-layout /path/to/layout.json /path/to/project.imgsli
```

or create a fresh tab of that kind with `--open-tab` (no project file
needed) — it runs the matching `workspace.new_<tab_kind>` Find Action
(`workspace.new_image_compare`, `workspace.new_multi_compare`, …) before the
dump, with a slightly longer settle delay to let the tab's own layout land:

```bash
./launcher.sh run --open-tab image_compare --dump-ui-layout /path/to/layout.json
```

`--open-tab` takes any tab kind with a registered `workspace.new_<kind>`
action — not a fixed list — so it keeps working if new tab kinds are added.
An unknown kind logs a warning and is otherwise ignored (dump falls back to
whatever's on screen, i.e. the Session Picker).

### Other windows (Settings, Help, dialogs, …)

`--dump-ui-layout` always walks *every* top-level window
(`QApplication.topLevelWidgets()`), but most non-main windows are built
lazily and don't exist until something opens them. Use `--run-action` to run
a Find Action id first (see [ACTIONS.md](ACTIONS.md) for the full catalog,
e.g. `platform.settings`, `platform.help`); it's repeatable and runs in
order, after `--open-tab`:

```bash
./launcher.sh run --run-action platform.settings --dump-ui-layout /path/to/layout.json
./launcher.sh run --run-action platform.help --dump-ui-layout /path/to/layout.json
./launcher.sh run --open-tab image_compare --run-action platform.settings \
    --dump-ui-layout /path/to/layout.json
```

Only actions whose `run` callable actually shows the dialog (non-modal
`.show()`, not a blocking `.exec()`) work here — checked case by case, not
guaranteed for every action id. An unknown id logs a warning and is
otherwise ignored.

## Output shape

```json
{
  "windows": [
    {
      "class": "MainWindow",
      "object_name": "",
      "geometry": [0, 0, 1280, 800],
      "visible": true,
      "enabled": true,
      "layout": "QVBoxLayout",
      "action_ids": ["platform.settings"],
      "children": [ ... ]
    },
    {
      "class": "SettingsDialog",
      "object_name": "SettingsDialog",
      "geometry": [-200, 97, 1200, 605],
      "visible": true,
      "...": "..."
    }
  ]
}
```

- `windows` is every top-level widget in the process at dump time, in
  whatever order Qt returns them — includes closed-but-not-destroyed and
  otherwise-hidden helper windows, so check each entry's own `visible`.
- `geometry` is `[x, y, w, h]`; for a top-level window this is screen
  coordinates, for a child it's parent-relative (`QWidget.geometry()`).
- `layout` is the widget's own `QLayout` class name, omitted if none.
- `action_ids` is omitted if empty; only exact widget matches are included
  (an ancestor's action does not leak onto its children — unlike
  `ActionRegistry.find_for_widget`, which climbs the parent chain for pulse
  targeting). Chrome tagged via Qt dynamic properties instead of a static
  `ActionTarget.widget` ref (e.g. Settings page members, tagged through
  `SearchGroup.tag_member`/`tag_combo` for lazy `resolve_widget` lookup —
  see [ACTIONS.md](ACTIONS.md)) does **not** show up as `action_ids` here;
  cross-referencing those would mean calling `resolve_widget()` for every
  action during the dump, which can have side effects (e.g. opening a
  dropdown) — deliberately not done.
- Tab actions only appear once the tab has run its `contribute_actions`
  (i.e. once it's the active tab) — a dump taken at the Session Picker will
  show host/platform actions only, not `image_compare.*` / `multi_compare.*`.
- `family` / `state` carry the widget's declared inspector state
  (`InspectSpec.state` / `WidgetDescriptor.inspect.state`), resolved live and
  JSON-sanitized — omitted when the widget declares no spec. This is what
  makes hidden subtrees readable: a closed `UnifiedListPicker` still reports
  `mode` (`HIDDEN` / `SINGLE_LEFT` / `DOUBLE` …) and `source_list_num`, a row
  reports `index` / `full_path` / `is_current`, even though `visible` is
  false everywhere below it. Stock Qt widgets have no spec and stay
  geometry-only.

## Ownership

| Piece | Location |
|-------|----------|
| Tree walk + action cross-reference | `src/devtools/ui_layout_dump.py` (`dump_all_windows`, `dump_ui_layout`) |
| CLI flags | `src/__main__.py` (`--dump-ui-layout`, `--open-tab`, `--run-action`) |
| Launcher pass-through | `launcher.sh` (`run --dump-ui-layout <path> [--open-tab <kind>] [--run-action <id>]`) |
| Interactive trigger | `src/devtools/ui_inspector/app_window.py` (Dump widget / Dump window buttons), `app_controller.py` (`_dump_layout`, `_dump_window_layout`, focus tracking) |

No new widget introspection beyond `ActionRegistry.all_actions()` and plain
`QWidget` geometry/layout — deliberately lighter than `UI Inspector`'s
`widget_snapshot.py` (no palette/QSS/theme-token diagnostics), since those
answer a different question ("why does this pixel look wrong") than this
tool's ("what exists and where").