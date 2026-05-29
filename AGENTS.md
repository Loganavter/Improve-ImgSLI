# Improve-ImgSLI Agent Guide

This file is for CLI AI agents and other automated coding assistants. Read it before making changes.

## First Read

Start with these files in this order:

1. [readme.md](/home/jorj/Загрузки/Improve-ImgSLI/readme.md)
2. [CONTRIBUTING.md](/home/jorj/Загрузки/Improve-ImgSLI/CONTRIBUTING.md)
3. [docs/INSTALL.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/INSTALL.md)

Then read the area-specific docs in [docs/dev/](docs/dev/) that match the task. Two cross-cutting docs are always useful:

- [docs/dev/TESTING.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/TESTING.md) — `/tests` layout and conventions before adding or running tests.
- [docs/dev/TRACING.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/TRACING.md) — runtime tracer for Redux/EventBus/render causal chains when debugging.

## Area Docs

### Canvas, magnifier, overlays, render/export parity

Read:

1. [docs/dev/CANVAS_FEATURES.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/CANVAS_FEATURES.md)
2. [docs/dev/CONTRACTS.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/CONTRACTS.md) — complete contracts reference
3. [src/ui/canvas_presentation](/home/jorj/Загрузки/Improve-ImgSLI/src/ui/canvas_presentation)
4. [src/ui/widgets/gl_canvas](/home/jorj/Загрузки/Improve-ImgSLI/src/ui/widgets/gl_canvas)

Important:

- Live canvas, export preview, final export, and video snapshot rendering must stay visually consistent.
- If you change diff rendering, verify `highlight`, `grayscale`, `edges`, and `ssim` in both live and export paths.
- Avoid appending feature-specific logic to generic `canvas_presentation` helpers if it belongs in a feature folder.

### Help system and documentation UI

Read:

1. [docs/dev/HELP_WIDGET.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/HELP_WIDGET.md)
2. [src/plugins/help/dialog.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/help/dialog.py)
3. [packages/sli-ui-toolkit/src/sli_ui_toolkit/ui/widgets/composite/markdown_help_dialog.py](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/src/sli_ui_toolkit/ui/widgets/composite/markdown_help_dialog.py)

Important:

- Help content lives in `src/resources/help/<lang>/`.
- Keep help pages scenario-based, anchor-friendly, and split into short `###` sections.
- When features change, update help pages as part of the same task.

### Toolkit widgets and reusable UI

Read:

1. [packages/sli-ui-toolkit/README.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/README.md)
2. [packages/sli-ui-toolkit/docs/README.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/README.md)
3. [packages/sli-ui-toolkit/docs/ARCHITECTURE.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/ARCHITECTURE.md)
4. [packages/sli-ui-toolkit/docs/API_CATALOG.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/API_CATALOG.md)
5. [packages/sli-ui-toolkit/docs/DESIGN_LANGUAGE.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/DESIGN_LANGUAGE.md)

Important:

- Prefer public imports from `sli_ui_toolkit.widgets` for app code.
- Keep app-specific logic out of toolkit code.
- If a control family grows, split it into a folder like `buttons/` or `comboboxes/`.

### Export, snapshot rendering, video editor

Read:

1. [src/plugins/export/services/image_export.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/export/services/image_export.py)
2. [src/plugins/export/services/snapshot_render_plan_builder.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/export/services/snapshot_render_plan_builder.py)
3. [src/plugins/video_editor/services/video_snapshot_rendering.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/video_editor/services/video_snapshot_rendering.py)

Important:

- Export paths are easy to desync from live rendering. Check them explicitly.
- Toast/progress UX for long-running export work is part of the product, not a side detail.

## Project Structure

Use this mental model:

- `src/core/`: app state, settings, events, reducers, shared runtime contracts
- `src/plugins/`: feature/domain plugin layer
- `src/ui/`: presenters, canvas integration, Qt widgets, main window
- `src/shared/`: shared processing and rendering helpers
- `src/shared_toolkit/`: app-side QSS/resources and older shared UI integration points
- `packages/sli-ui-toolkit/`: reusable PyQt toolkit extracted from the app
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

## Recommended Workflow

1. Read the relevant docs first.
2. Inspect the existing code path end-to-end before editing.
3. Patch the actual owner layer instead of adding workaround glue in random presenters.
4. Update docs/help when the user-visible behavior changes.
5. Run focused tests for the touched subsystem.

## Tests

See [docs/dev/TESTING.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/TESTING.md) for full layout and conventions.

Tests are grouped by subsystem under `tests/`:

- `tests/contracts/` — static architectural dogmas (AST scan, no runtime).
- `tests/runtime/` — registry, Feature State API, stacking policy.
- `tests/render/` — GL pass behavior with fake `SimpleNamespace` context.
- `tests/plugins/` — plugin behavior (export, help, settings, toast, clipboard).
- `tests/toolkit/` — `sli-ui-toolkit` public API.
- `tests/video/` — video editor preview/timeline/keyframes contracts.

Common focused test pattern:

```bash
env QT_QPA_PLATFORM=offscreen pytest -q tests/<area>/<target_test>.py
```

Examples:

```bash
env QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_export_diff_support.py
env QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_toast_and_metrics.py
env QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_help_dialog_anchors.py
env QT_QPA_PLATFORM=offscreen pytest -q tests/toolkit/test_fluent_combobox_api.py
env QT_QPA_PLATFORM=offscreen pytest -q tests/contracts            # all architecture contracts
env QT_QPA_PLATFORM=offscreen pytest -q tests/render                # render-pass contracts
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
- [packages/sli-ui-toolkit/docs/API_CATALOG.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/API_CATALOG.md)
- [packages/sli-ui-toolkit/docs/ARCHITECTURE.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/ARCHITECTURE.md)
- [docs/dev/HELP_WIDGET.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/HELP_WIDGET.md)
- [docs/dev/CANVAS_FEATURES.md](/home/jorj/Загрузки/Improve-ImgSLI/docs/dev/CANVAS_FEATURES.md)

## Good Defaults For Agents

- Prefer `rg` for code search.
- Prefer small, explicit patches.
- Prefer adding a focused regression test when fixing rendering/export/UI wiring bugs.
- If a bug involves preview vs export mismatch, inspect both code paths before changing anything.
