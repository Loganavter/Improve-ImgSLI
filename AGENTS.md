# Improve-ImgSLI Agent Guide

This file is for CLI AI agents and other automated coding assistants. Read it before making changes.

The codebase is a Python/PySide6 application under `src/` (production, declarative, well-decomposed).

---

## Python Codebase Areas

The Python tree under `src/` is the reference implementation and the production code. When a task touches a plugin, **always read the Python equivalent first** — it documents the intended decomposition.

### Canvas, magnifier, overlays, render/export parity

Read:

1. [docs/dev/QRHI_CANVAS_FEATURES.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/QRHI_CANVAS_FEATURES.md)
2. [docs/dev/CONTRACTS.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/CONTRACTS.md) — complete contracts reference
3. [src/ui/canvas_presentation](/home/jorj/Загрузки/Improve-ImgSLI/src/ui/canvas_presentation)
4. [src/ui/widgets/canvas](/home/jorj/Загрузки/Improve-ImgSLI/src/ui/widgets/canvas)
5. [src/tabs/image_compare/canvas](/home/jorj/Загрузки/Improve-ImgSLI/src/tabs/image_compare/canvas)

Important:

- Live canvas, export preview, final export, and video snapshot rendering must stay visually consistent.
- If you change diff rendering, verify `highlight`, `grayscale`, `edges`, and `ssim` in both live and export paths.
- Avoid appending feature-specific logic to generic `canvas_presentation` helpers if it belongs in a feature folder.

### Help system and documentation UI

Read:

1. [docs/dev/HELP_WIDGET.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/HELP_WIDGET.md)
2. [src/plugins/help/dialog.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/help/dialog.py)
3. `sli_ui_toolkit.ui.widgets.composite.markdown_help_dialog` in the external `Loganavter/sli-ui-toolkit` repository

Important:

- Help content lives in `src/resources/help/<lang>/`.
- Keep help pages scenario-based, anchor-friendly, and split into short `###` sections.
- When features change, update help pages as part of the same task.

### Toolkit widgets and reusable UI

Read:

1. External toolkit repository: `https://github.com/Loganavter/sli-ui-toolkit`
2. Local toolkit checkout: [/home/jorj/Загрузки/sli-ui-toolkit](/home/jorj/Загрузки/sli-ui-toolkit)
3. App-side overview: [docs/dev/UI_TOOLKIT_LIBRARY.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/UI_TOOLKIT_LIBRARY.md)
4. Toolkit [docs/dev/README.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/dev/README.md) and [docs/dev/ARCHITECTURE.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/dev/ARCHITECTURE.md)
5. Toolkit [docs/user/API_CATALOG.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/user/API_CATALOG.md)
6. Toolkit [docs/dev/DESIGN_LANGUAGE.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/dev/DESIGN_LANGUAGE.md)
7. For button/control work, also read [docs/user/BUTTON_API.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/user/BUTTON_API.md) and [docs/user/FLYOUT_SYSTEM.md](/home/jorj/Загрузки/sli-ui-toolkit/docs/user/FLYOUT_SYSTEM.md) when relevant.

Important:

- Prefer public imports from `sli_ui_toolkit.widgets` for app code.
- Keep app-specific logic out of toolkit code.
- If a control family grows, split it into a folder like `buttons/` or `comboboxes/`.
- **Never** use raw `QFormLayout`/`QVBoxLayout` blocks for widget construction — use the toolkit painter pipeline.
- **Never** use QSS (`setStyleSheet`) to style toolkit widgets — the painter pipeline owns all visual output.

### Export, snapshot rendering, video editor

Read:

1. [src/tabs/image_compare/services/image_export.py](/home/jorj/Загрузки/Improve-ImgSLI/src/tabs/image_compare/services/image_export.py) and [src/tabs/multi_compare/services/image_export.py](/home/jorj/Загрузки/Improve-ImgSLI/src/tabs/multi_compare/services/image_export.py)
2. [src/tabs/image_compare/services/snapshot_render_plan_builder.py](/home/jorj/Загрузки/Improve-ImgSLI/src/tabs/image_compare/services/snapshot_render_plan_builder.py)
3. [src/tabs/image_compare/plugins/video_editor/services/video_snapshot_rendering.py](/home/jorj/Загрузки/Improve-ImgSLI/src/tabs/image_compare/plugins/video_editor/services/video_snapshot_rendering.py)

Important:

- Export paths are easy to desync from live rendering. Check them explicitly.
- Toast/progress UX for long-running export work is part of the product, not a side detail.

### Workspace tabs, state (Store/Redux), and cross-component events

Read:

1. [docs/dev/TAB_CONTRACT.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/TAB_CONTRACT.md) — tab interface, file layout, session lifecycle
2. [docs/dev/STORE.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/STORE.md) — Redux-style state contract (`Action → Dispatcher → RootReducer → Store`)
3. [docs/dev/EVENT_BUS.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/EVENT_BUS.md) — pub/sub for cross-component notifications, not for state
4. [docs/dev/THEMING.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/THEMING.md) — palette + QSS pipeline (toolkit `ThemeManager` + app-side wiring)
5. [src/core/store.py](/home/jorj/Загрузки/Improve-ImgSLI/src/core/store.py), [src/core/state_management/dispatcher.py](/home/jorj/Загрузки/Improve-ImgSLI/src/core/state_management/dispatcher.py), [src/core/state_management/reducers.py](/home/jorj/Загрузки/Improve-ImgSLI/src/core/state_management/reducers.py)
6. [src/core/plugin_system/event_bus.py](/home/jorj/Загрузки/Improve-ImgSLI/src/core/plugin_system/event_bus.py)

Important:

- A new tab is a self-contained module under `src/tabs/<tab_name>/` implementing `TabContract` (`tab.py`, `controller.py`, `widget.py`, own `resources/i18n/`) — don't wire tab-specific logic into core.
- All state mutation goes through `Dispatcher.dispatch` → `RootReducer.reduce`; never mutate `Store` fields directly.
- `EventBus` is for facts about the past ("an export finished"), not for state — state changes belong in the Store. Don't use one where the other belongs.
- Theming is centralized in the external `sli-ui-toolkit` `ThemeManager`; app-side palette/QSS registration happens in `src/core/bootstrap.py`. Don't hand-roll colors outside `themes.json`.

## Project Structure (Python)

Use this mental model for `src/`:

- `src/core/`: app state, settings, events, reducers, shared runtime contracts
- `src/plugins/`: feature/domain plugin layer
- `src/ui/`: presenters, canvas integration, Qt widgets, main window
- `src/shared/`: shared processing and rendering helpers
- `src/shared_toolkit/`: app-side QSS/resources and older shared UI integration points
- `sli-ui-toolkit`: external reusable PySide6 toolkit installed from `requirements-gui.txt`
- `src/resources/help/`: localized in-app help content

## Project Rules

- Do not treat this as a generic CRUD app. Rendering parity and interaction fidelity matter.
- Do not assume export preview and final export work the same as live canvas. Verify them.
- Do not move app code into `sli-ui-toolkit` unless it is truly reusable and app-agnostic.
- Do not add visible user-facing behavior without checking translations and help impact.
- Do not silently remove legacy compatibility imports from the toolkit unless the whole tree is migrated.

## Known Constraints

- Images above `16384 px` on either side are currently unsupported by software guard.
- `ssim` has special handling because some paths depend on cached diff images and GPU diff textures.
- Help pages now support anchors and generated in-page TOC. Keep headings stable.

## Tests

See [docs/dev/TESTING.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/TESTING.md) for full layout and conventions.

Tests are grouped by subsystem under `tests/`:

- `tests/contracts/` — static architectural dogmas (AST scan, no runtime).
- `tests/runtime/` — registry, Feature State API, stacking policy.
- `tests/render/` — GL pass behavior with fake `SimpleNamespace` context.
- `tests/plugins/` — plugin behavior (export, help, settings, toast, clipboard).
- `tests/video/` — video editor preview/timeline/keyframes contracts.
- `tests/devtools/` — developer tooling (UI inspector, QSS index).

Common focused test pattern:

```bash
env QT_QPA_PLATFORM=offscreen pytest -q tests/<area>/<target_test>.py
```

When fixing a rendering/export/UI wiring bug, prefer adding a focused regression test in the matching folder rather than at the top level of `tests/`.

## Debugging Runtime Issues

When something goes wrong after a click / zoom / state change and the cause is not obvious from the diff, use the runtime tracer described in [docs/dev/TRACING.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/TRACING.md). It captures the causal chain across Redux dispatches, EventBus publishes, and render frames — much faster than instrumenting with `logger` calls by hand.

## When To Update Docs

Update documentation in the same task if you change:

- help page behavior or content
- toolkit public widget API
- rendering/export architecture
- user-visible hotkeys, settings, or workflow

Usually this means touching one of:

- [src/resources/help/en](/home/jorj/Загрузки/Improve-ImgSLI/src/resources/help/en)
- external `sli-ui-toolkit` docs/user/API_CATALOG.md
- external `sli-ui-toolkit` docs/dev/ARCHITECTURE.md
- [docs/dev/HELP_WIDGET.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/HELP_WIDGET.md)
- [docs/dev/QRHI_CANVAS_FEATURES.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/QRHI_CANVAS_FEATURES.md)

## Good Defaults For Agents

- Prefer `search_files` for code search.
- Prefer small, explicit patches.
- Prefer adding a focused regression test when fixing rendering/export/UI wiring bugs.
- If a bug involves preview vs export mismatch, inspect both code paths before changing anything.
