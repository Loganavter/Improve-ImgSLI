# sli-ui-toolkit Architecture

This document explains how the toolkit is laid out, which imports are public, and where new code should go.

If you need something else:

- integration overview: [../README.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/README.md)
- public reference: [API_CATALOG.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/API_CATALOG.md)
- visual conventions: [DESIGN_LANGUAGE.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/DESIGN_LANGUAGE.md)

## What This Package Is

`sli-ui-toolkit` is a reusable PyQt6 UI layer with three main responsibilities:

- provide custom-painted widgets and small reusable composites;
- provide shared UI infrastructure such as theming, icon resolution, i18n, flyout management, and workers;
- keep host-app specifics outside the toolkit and inject them through configuration hooks.

It is not a full application framework. App-specific icons, translations, business logic, and resource-folder conventions should stay in the host app.

## Public Surface

The toolkit intentionally exposes a small number of public entry points.

### Stable imports

- `sli_ui_toolkit`
  Bootstrap/configuration helpers and a few common primitives.
- `sli_ui_toolkit.widgets`
  Main public widget catalog.
- `sli_ui_toolkit.theme`
  `ThemeManager`.
- `sli_ui_toolkit.i18n`
  Translation manager and `tr(...)`.
- `sli_ui_toolkit.icons`
  Icon resolver configuration.

### Internal imports

Everything under `sli_ui_toolkit.ui...` is implementation detail first.

Direct imports from internal modules are acceptable only when:

- a public re-export does not exist yet;
- the module is intentionally specialized and not meant for the broad public surface;
- you are working on toolkit internals themselves.

As a rule, application code should prefer `sli_ui_toolkit.widgets`.

## Layering

The package is easiest to understand as five layers.

### 1. Bootstrap and shared services

Files:

- `__init__.py`
- `theme.py`
- `i18n.py`
- `icons.py`
- `config.py`
- `core/`
- `workers/`

Responsibilities:

- startup configuration hooks;
- theme registration and theme switching;
- translation lookup;
- icon resolution;
- generic worker helpers;
- low-level shared utilities.

This layer should not depend on app code.

### 2. Public aggregation

Files:

- `widgets.py`
- `ui/widgets/atomic/__init__.py`
- `ui/widgets/composite/__init__.py`
- `ui/widgets/buttons/__init__.py`
- `ui/widgets/comboboxes/__init__.py`

Responsibilities:

- re-export public widgets from their implementation folders;
- keep import ergonomics stable even if internals move.

This layer is where compatibility is preserved when implementation files are reorganized.

### 3. Low-level widgets

Folders:

- `ui/widgets/atomic/`
- `ui/widgets/buttons/`
- `ui/widgets/comboboxes/`

Responsibilities:

- standalone input and display widgets;
- custom-painted controls;
- small self-contained UI primitives.

Use these folders when a widget can stand on its own without needing a higher-level shell.

Examples:

- `Button` lives in `ui/widgets/buttons/`
- `ComboBox` lives in `ui/widgets/comboboxes/`
- `CheckBox`, `Slider`, `CustomLineEdit`, `MinimalistScrollBar` live in `ui/widgets/atomic/`

### 4. Composite widgets

Folder:

- `ui/widgets/composite/`

Responsibilities:

- reusable multi-widget assemblies;
- flyouts, dialog shells, console widgets, help dialogs, path pickers, and similar “assembled” controls;
- package-level reusable UX patterns.

Use this layer when the unit is bigger than one primitive and has meaningful internal structure.

Examples:

- `SidebarDialogShell`
- `DialogActionBar`
- `MarkdownHelpDialog`
- `ProcessConsoleWidget`

### 5. Specialized UI families

Folders:

- `ui/widgets/composite/calendar_widget/`
- `ui/widgets/composite/timeline_widget/`
- `ui/widgets/composite/sunburst_chart/`
- `ui/widgets/composite/unified_flyout/`
- `ui/widgets/list_items/`
- `ui/widgets/overlays/`

Responsibilities:

- isolated feature families with multiple internal files;
- widgets that are too large to keep as single-module composites.

If a widget family starts needing private helpers, models, renderers, or interaction controllers, it should become a folder like this.

## Directory Map

This is the practical meaning of the main folders.

### `ui/widgets/atomic/`

Simple widgets and compatibility re-exports.

Put code here when:

- the widget is small;
- the widget has little or no internal decomposition;
- it is a basic primitive.

Do not put large subsystems here just because they are “single controls”. `ComboBox` was already large enough to deserve its own folder.

### `ui/widgets/buttons/`

The unified button system.

Typical internal split:

- public re-export;
- main widget implementation;
- painter;
- menu/dropdown helpers;
- group container.

Use this folder as the model for any control family that grows beyond one file.

### `ui/widgets/comboboxes/`

ComboBox family.

Current split:

- `combobox.py`
  Public re-export.
- `combo_box.py`
  Main `ComboBox`.
- `_overlay.py`
  Popup rendering and interaction.
- `_search.py`
  Search and ranking helpers.
- `_models.py`
  Small internal item model.
- `scrollable_combobox.py`
  Separate lightweight widget with different behavior.

This is the expected pattern for future medium-sized control families.

### `ui/widgets/composite/`

Reusable multi-widget assemblies.

A composite belongs here when:

- it owns layout and coordination between child widgets;
- it is not just a thin wrapper around a single primitive;
- it can be reused in multiple dialogs or apps.

### `ui/widgets/helpers/`

Pure UI helpers and drawing helpers.

This folder should contain code that:

- has no app-specific meaning;
- is reusable across multiple widgets;
- does not need widget ownership.

Typical examples:

- underline drawing;
- shadow drawing;
- overlay geometry calculations.

### `ui/managers/`

Shared UI stateful managers.

Use this layer for singleton-like or coordination objects such as:

- `ThemeManager`
- flyout manager / auto-hide coordination
- delayed action helpers

### `ui/services/`

UI-related services that are not widgets.

Examples:

- icon services;
- window prewarm helpers.

### `workers/`

Generic async helpers built around Qt worker primitives.

Keep this folder generic. If a worker knows app business rules, it belongs in the app, not here.

## Import Rules

Use these rules to keep the package readable.

### Allowed

- widgets depend on `ThemeManager`, helpers, and small shared config;
- composite widgets depend on atomic widgets, buttons, comboboxes, helpers, and managers;
- public aggregators re-export from implementation modules;
- private modules inside one widget family can import each other.

### Avoid

- helpers importing widgets;
- atomic widgets importing composite widgets;
- broad sideways imports between unrelated widget families;
- business logic in toolkit widgets;
- app resource conventions inside toolkit code.

If two widget families start depending on each other heavily, there is usually a missing lower-level helper or service.

## How To Add New Code

Use this decision tree.

### Add to `atomic/`

When the new thing is:

- a small standalone control;
- a label, line edit, spinner, switch, checkbox, or similarly small primitive.

### Add a new folder like `buttons/` or `comboboxes/`

When the control family:

- is still one conceptual widget type;
- already needs private helpers, painter logic, popup logic, models, or internal state modules;
- benefits from keeping a thin public re-export and several private files.

### Add to `composite/`

When the new thing:

- assembles multiple existing widgets;
- owns a layout shell or interaction shell;
- is reusable but not “atomic”.

### Add a specialized subfolder under `composite/`

When the composite itself becomes a subsystem with:

- models;
- scene/view layers;
- rendering helpers;
- multiple interaction modes.

## How To Move Code Without Breaking Apps

The package already uses compatibility re-exports for this.

Safe pattern:

1. Move the real implementation to a better folder.
2. Keep the old module path as a thin import shim.
3. Keep `widgets.py` exporting the same public names.
4. Update docs to point to the new canonical location.

This is how `ComboBox` was reorganized into `ui/widgets/comboboxes/` without breaking older imports.

## Host-App Boundary

Keep these outside the toolkit:

- app icon enums and asset paths;
- app resource directory conventions;
- app translation content;
- app business rules and state transitions;
- app-specific plugins or controllers.

The toolkit should accept those via:

- `configure_icon_resolver(...)`
- `configure_i18n(...)`
- `configure_toolkit(...)`
- constructor parameters and thin app adapters.

Good example:

- `MarkdownHelpDialog` in the toolkit is generic.
- the app-specific help loader stays in the app and only feeds localized markdown sections into the dialog.

## Deferred Migration: Move Toward Feature-First Viewport Control

This is a deferred architecture direction, not an active refactor.

Target outcome:

- remove the extra “viewport orchestration” layer where possible;
- make canvas feature contracts the primary control surface;
- stop routing ordinary viewport UI actions through a separate plugin controller when the feature layer already owns the behavior.

In practice this means moving toward:

- `UI/settings/video tooling -> feature contract/property access/settings bindings`

instead of:

- `UI/settings/video tooling -> viewport plugin/controller -> string alias lookup -> feature command`

### Why This Is Not Done Yet

The current `viewport` plugin still centralizes a few cross-cutting concerns that cannot just be deleted:

- update emission;
- recording checkpoints;
- interaction begin/end lifecycle;
- some settings persistence;
- multi-feature coordination for magnifier/capture/guides/splitter behavior.

Removing the plugin layer before those concerns are redistributed would just spread the same complexity across more files.

### Migration Path

If this work is resumed later, do it in this order.

1. Introduce a typed canvas adapter layer.
   This should wrap feature-command lookup behind grouped APIs such as `magnifier`, `capture`, `guides`, and `splitter`.
2. Remove direct string-alias access from `plugins/viewport/controller.py`.
   The controller should stop calling `get_canvas_feature_command_by_alias(...)` directly.
3. Isolate true cross-cutting runtime behavior.
   Extract update emission, recording checkpoints, and interaction session lifecycle into a small shared runtime coordinator.
4. Push feature-owned behavior back to the owning feature family.
   Magnifier-specific behavior should live with magnifier, guides-specific behavior with guides, and so on.
5. Rewire UI/settings integrations to use feature contracts directly where no orchestration is needed.
   At this point the viewport plugin should only remain where it still adds real coordination value.
6. Delete or drastically shrink the viewport plugin.
   If the remaining code is only thin wiring, remove the extra layer entirely.

### Conditions For Removal

The separate viewport plugin/controller can be dropped only when all of the following are true:

- feature command/property/settings surfaces are complete enough for normal UI use;
- recording/update lifecycle is handled elsewhere;
- settings persistence is no longer hidden inside viewport controller methods;
- no important multi-feature interaction still depends on plugin-local orchestration.

Until then, the safer intermediate goal is a thin façade, not immediate deletion.

## Common Mistakes

- Treating `README.md` as the full API manual.
- Adding app-specific behavior directly into toolkit widgets.
- Importing deep internal modules from app code when a public re-export exists.
- Keeping a growing widget in one giant file after it has clearly become a widget family.
- Duplicating shared painting or geometry logic instead of moving it into `helpers/`.

## Current High-Level Shape

If you just need the mental model, it is this:

- bootstrap/configuration at the package root;
- stable public widget exports in `widgets.py`;
- primitives in `atomic/`, `buttons/`, and `comboboxes/`;
- reusable assembled widgets in `composite/`;
- larger specialized subsystems in their own subfolders;
- host-app specifics injected from outside.
