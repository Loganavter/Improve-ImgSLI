# UI Inspector

In-app, DevTools-style inspector for the painter-pipeline GUI.

## What it is

A tool window (launched with `--ui-inspector`) that inspects any widget.
Inspections are opened in **tabs** (like the Video Editor): Shift+click in
the app or a click on a Layout/Constructor tree row opens that widget in its
own tab (re-opening an already-open widget switches to its tab instead of
duplicating). Each tab has its own section set:

- **Object** — class/objectName/geometry/visibility/source file.
- **Config / State** — the widget's own `inspect_spec` (self-description):
  config auto-derived from the `__init__` signature, state from runtime
  getters, with human labels and `(private)` markers.
- **Regions** — Button-family regions: rects, per-region states, weights;
  the overlay draws every region, the hovered one filled.
- **Layers** — active painter layers in paint order (Background, Ripple,
  Content, Badge, ...).
- **Theme** — static token family (the widget's `token_family`, resolved
  against the current theme) + **live capture**: "Capture tokens" repaints
  the widget with `ThemeManager.get_color`/`try_get_color` wrapped and lists
  the exact keys resolved (missing keys flagged).
- **Layout** — collapsible tree of the whole window (web-devtools-style
  rows with twist indicators); clicking a row opens that widget in a new
  tab, hovering a row highlights it in the app via the overlay.
- **Constructor** — same tree view but rooted at the selected widget: every
  widget inside it; click to open a new tab, hover to highlight.
- **Code** — ONE unified, editable `TextView` (styled like the app's
    recent-projects shelf: rounded panel well behind the text) showing the
    generated **Configuration (live values)** snippet (a synthetic constructor
    call built from `WidgetInspection.config`, e.g.
    `Button(text='Edit', variant='surface', …)`; REF child widgets appear as
    `Type(...)` placeholders) followed by the widget class source. Any OTHER
  code in the source file is collapsed into a plain gap row (`·····`): click
  the row to expand that region inline, click again to collapse it. The
  gutter shows the hidden block's boundary line numbers, VS Code-style —
  the gap row carries the last line before the block, and the very next
  row its real number right after (e.g. `12` then immediately `17`), so
  the jump reads naturally; a disclosure arrow (`▸`) sits in the gutter
  LEFT of the gap row's number. The synthetic config snippet is marked
  with a dot (`·`) instead of a line number so the file counter never
  restarts below it. The gutter width (numbers + a constant arrow slot) is
  identical across compact/expanded/full, so the content's left offset
  never moves. The **Full/Compact** toggle button (top-left,
  `variant="default"`) expands/collapses everything at once and flips its
  own label. **Apply** hot-patches the LIVE widget class in place: the
  edited class region's methods/attributes are copied onto the real class,
  so the actual widget changes where it sits (same instance, host wiring
  intact; all instances of that class are affected) and repaints —
  **Revert** restores the snapshot of the original class. Method-level
  edits take effect on the live instance immediately; `__init__`-body
  edits do NOT re-run the constructor, so they only affect widgets created
  after the patch (the status line says so explicitly). Apply with an
  unedited class region is a no-op and reports "Nothing to patch" instead
  of claiming success. Python/PySide class bookkeeping (`staticMetaObject`,
  `__firstlineno__`, `__static_attributes__`, …) is never copied. Method-level
  edits take effect on the live instance immediately; `__init__`-body
  edits do NOT re-run the constructor, so they only affect widgets created
  after   the patch (the status line says so explicitly). **Apply never
  opens or builds the preview panel** — an already-open preview is
  refreshed with the Apply result in its caption; with the panel closed,
  feedback is the live widget change itself + the `[inspector-preview]`
  log lines. Apply with an
  unedited class region is a no-op and reports "Nothing to patch" instead
  of claiming success — the Apply button is disabled until the source is
  actually edited (same rule as Save), so a stray click never opens the
  preview panel for nothing. The Code editor is clamped to its page
  height and the TextView scrolls internally, and the preview panel is
  compact (preview capped at 144px, debug line capped) — opening the
  preview never pushes the page into a long fixed-height strip; everything
  stays inside the window. Editing the synthetic **Configuration
  snippet** at the top of the Code view enables **Apply**: the snippet's
  kwargs are written onto the live instance's config attributes
  (`name`/`_name`/`_name_override`, skipping Qt methods — a value named
  like a method never overwrites it), then the spec's optional
  `apply_config_refresh` hook (`InspectSpec.apply_config_refresh`,
  MRO-inherited; AdaptiveTabStrip re-syncs margins/spacing and rebuilds
  its close buttons) re-runs the layout passes `__init__` normally
  performs, and the widget is repainted — every write is reported in the
  debug line with its before/after value, and the live widget's geometry
  is logged after the apply. Without a refresh hook, attribute writes +
  repaint are all Apply can do — layout-affected values appear inert (the
  log says "NO refresh hook"). Snippet edits never
  enable Save — the snippet is synthetic, not file content. The preview
  is rebuilt from the CURRENT snippet, so config edits are visible there
  immediately. Python/PySide class bookkeeping
  (`staticMetaObject`,
  `__firstlineno__`, `__static_attributes__`, …) is never copied. **Preview**
  compiles the edited class and constructs a fresh instance — the current
  config values are used as constructor kwargs (module-level names like
  `CloseButtonPolicy.X` resolve through the widget's module namespace) —
  in a preview panel below the editor; while the panel is open it
  re-builds on every edit (debounced), so the effect of a change is
  visible before saving. Every Apply/Preview result is reported in the
  panel (auto-opened, so a failure is never silent) with a debug line:
  the compiled class, the resolved constructor signature, the kwargs used
  and the skipped values. **Apply** also rebuilds the preview panel from
  the edited class, so the patched widget is visible in the well right
  away (not just the status text). Constructor `parent` is never
  auto-filled (`__init__(self, parent)`-style widgets build with the
  preview host as parent); widgets without a sizeHint get a minimum
  height so the preview never renders as an empty strip. The preview is
  built from the config snippet only — runtime state (tabs, selection,
  rows) is copied from the live widget via the spec's optional
  `preview_seed` hook (`InspectSpec.preview_seed`, MRO-inherited like the
  spec itself; AdaptiveTabStrip seeds its tabs), so stateful composites
  preview as the real-looking widget instead of an empty shell. Enum
  members in the config snippet resolve even when the widget module does
  not import their class (e.g. the app's `AppIcon`, passed in as a
  constructor arg): enum classes seen in live config values are registered
  while the snippet is built, so `AppIcon.CLOSE`-style literals reach the
  preview constructor instead of being skipped. The gutter numbers the actual file lines (starting
  at the class statement; the snippet is plain 1-based). Save reconstructs
  the whole file with the edited class region — the snippet and gap rows
  are never written to disk. QSS candidates render as a synthetic snippet
  at the top of the Code page (heuristic; Qt exposes no computed styles):
  selector + source file:line + rule body, with `[matched]`/`[dead]`
  markers from the app-wide dead-selector scan (refreshed whenever the
  widget tree changes). Type selectors match the full class MRO (a
  base-class rule applies to subclasses, like Qt's cascade). A bare
  `QWidget` container (no class source of its own — e.g. the settings
  page's `ScrollableDialogPage.content_widget`) shows only the **creation
  site**: the enclosing function whose line creates/configures the widget,
  matched by objectName or by an instance attribute on its parent chain
  (searched in the app ancestor's file and the files its module imports,
  e.g. `create_scrollable_page` in `dialog_shell.py`), instead of the whole
  ancestor class (the entire `SettingsDialog`). The rest of the file stays
  collapsed into gap rows; Apply is disabled for such function-only
  regions (nothing to hot-patch), Save still rewrites the file.
- **Docs** — the widget's `docs=` reference: renders the per-widget doc
  file from [docs/dev/widgets/](widgets/).

Sidebar sections with nothing to show (e.g. Regions/Layers on a plain
QWidget) are hidden automatically; a section appears only when it has
content.
- **Native** (app layer) — native-window chain diagnostics + experiment
  buttons (toggle WA_NativeWindow / repaint / update).

## Launch

```bash
./launcher.sh run --ui-inspector
./launcher.sh --ui-inspector
```

`--ui-inspector` enables the inspector after the main UI is bootstrapped.

Interaction: **Shift+click** selects a widget; **Shift** hover highlights;
**Ctrl+Shift+I** toggles the inspector; **Escape** clears. In the Layout /
Constructor trees: **click a row** to open that widget in a new tab, **click
the twist** to expand/collapse, **hover a row** to highlight the widget in
the app. In the Layout /
Constructor trees: **click a row** to open that widget in a new tab, **click
the twist** to expand/collapse, **hover a row** to highlight the widget in
the app.

## Architecture

The inspection contract and the inspector UI live in **sli-ui-toolkit**
(`sli_ui_toolkit/ui/inspector/`):

- `contract.py` — `WidgetInspection`, `InspectField` (kind-aware),
  `InspectRegion`, `InspectLayer`, `FieldKind`.
- `spec.py` — `InspectSpec`/`SpecField`: widgets self-describe via an
  `inspect_spec` class attribute co-located in their own file; config
  auto-derives from `__init__`, state is curated with labels. `spec_of()`
  walks the MRO (subclasses inherit).
- `extract.py` — convention-driven readers (`name`/`_name`/`_name_override`/
  Qt dynamic properties), Button-family regions/layers.
- `registry.py` — `inspect_widget`: spec → `families/` matchers (buttons,
  flyouts, inputs, labels, nav, timeline, misc) → generic QWidget fallback.
- `capture.py` — live token capture (the `get_color` funnel).
- `qss_scan.py` — QSS candidate matching + dead-selector analysis.
- `code/editor.py` — `CodeSectionEditor` owner (construction, document model,
  editing/save/revert); per the thin-owner pattern its orthogonal
  concerns are split into `code/preview.py` (preview panel mechanics),
  `code/apply.py` (Apply: class patch + config apply), and
  `code/config.py` (snippet parsing shared by both) — plain functions
  taking the editor as their first argument, delegated under the same
  method names.
- `fields.py` / `rendering.py` / `tree.py` — shared field-row rendering
  and tree rows for the pages.
- `view.py` / `overlay.py` / `controller.py` — InspectorWindow (SidebarDialog-
  Shell + pages), per-region overlay, selection/hover controller.

The app (`src/devtools/ui_inspector/`) keeps a thin wiring layer:
`installer.py`, `app_window.py` (Native page + Dump layout),
`app_controller.py`, `native.py`, and app-family specs co-located in the app
widgets. Every app-side widget family under `src/ui/widgets/` (and the
Settings dialog) carries an `inspect_spec` with a `docs=` reference into
[docs/dev/widgets/](widgets/) — the Docs page renders that per-widget file.
Families: `ColorPickerDialog`, `ColorSwatch`, `RecentColorsRow`,
`DialogActionBar`, `OutputPathSection`, `ShelfWidget`, `ValueSlider`,
`ValueSliderRow`, `ScrollValueButton`, `WorkspaceTabStrip`, `ThemedSurface`,
`ThemedBackgroundContainer`, `StartupPlaceholder`, `DragGhostWidget`,
`FontSettingsFlyout`, `GlassHUD`, `InfoHUD`, `ZoomIndicator`,
`GlassPanelDisplayWidgetCpu`/`Rhi`, `RatingListItem`, `UnifiedListPicker`,
`SettingsDialog`. (New widgets: add the spec in the widget's own file; the
duck registry and the generic QWidget fallback cover everything else.)

## Wayland Constraints

- Overlays are in-process children of the inspected window; no global
  transparent overlays, no mouse/keyboard grabs.
- The inspector window is an opaque top-level tool window.

## Notes

- Adding a widget family: give the class an `inspect_spec` attribute
  (family + state fields + token_family; config auto-derives). The duck
  registry and the generic QWidget fallback cover everything else.
- The inspector is a diagnostic tool, not a user-facing feature — it is not
  documented in in-app Help.