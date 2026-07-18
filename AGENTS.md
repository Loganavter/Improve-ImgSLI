# Improve-ImgSLI Agent Guide

This file is for CLI AI agents and other automated coding assistants. Read it before making changes.

Human-oriented cheat sheet: [docs/dev/README.md](docs/dev/README.md). IDE-specific entry points: [.github/copilot-instructions.md](.github/copilot-instructions.md), [.cursor/rules/improve-imgsli.mdc](.cursor/rules/improve-imgsli.mdc). Cursor skills: [.cursor/skills/imgsli-devtools/](.cursor/skills/imgsli-devtools/), [.cursor/skills/sli-ui-toolkit-docs-first/](.cursor/skills/sli-ui-toolkit-docs-first/).

The codebase is a Python/PySide6 application under `src/` (production, declarative, well-decomposed).

---

## Agent Tooling

Commands and facilities wired for automated assistants:

| Tool | Command / env | Purpose |
|---|---|---|
| cloc | `./launcher.sh context --cloc-only` | Per-directory code stats for Improve-ImgSLI + `sli-ui-toolkit` → `cloc.txt` (gitignored), full tree expansion. `--toolkit-dir DIR` if the sibling checkout is not auto-found. |
| Contract tests | `./launcher.sh test tests/contracts -q` | Fast AST/architecture dogmas — run before large refactors. See `tests/contracts/_framework.py`. |
| Runtime tracer | `IMGSLI_TRACE=1` or `./launcher.sh run --debug` | Causal chain across dispatch / EventBus / render. Output: `~/.local/share/ImproveImgSLI/trace.jsonl`. See [docs/dev/TRACING.md](docs/dev/TRACING.md). |
| UI inspector | `./launcher.sh run --ui-inspector` | In-app widget, palette, theme-token, QSS diagnostics. See [docs/dev/UI_INSPECTOR.md](docs/dev/UI_INSPECTOR.md). |
| Startup phases | `IMGSLI_STARTUP_TRACE=1` | Bootstrap timing via `src/core/startup_trace.py`. |
| Focused tests | `env QT_QPA_PLATFORM=offscreen pytest -q tests/<area>/…` | Offscreen Qt for headless runs. |

Local-only dirs (gitignored, not in repo): `.cursor/` (except committed `.cursor/rules/` and `.cursor/skills/`), `.claude/`, `.agents/`, `.codex/`, `.windsurf/`, `.aider*`.

### Task routing

| Task | Start here |
|---|---|
| Architecture overview | [docs/dev/ARCHITECTURE.md](docs/dev/ARCHITECTURE.md) |
| Interface / isolation contracts | [docs/dev/CONTRACTS.md](docs/dev/CONTRACTS.md) (three senses) |
| New canvas feature | [docs/dev/QRHI_CANVAS_FEATURES.md](docs/dev/QRHI_CANVAS_FEATURES.md) |
| New workspace tab | [docs/dev/tabs/index.md](docs/dev/tabs/index.md) |
| Dialog / CSD chrome | [docs/dev/DIALOGS.md](docs/dev/DIALOGS.md) |
| Toolkit widgets | [docs/dev/UI_TOOLKIT_LIBRARY.md](docs/dev/UI_TOOLKIT_LIBRARY.md) |
| Find Action / palette | [docs/dev/ACTIONS.md](docs/dev/ACTIONS.md) |
| Help authoring | [docs/dev/HELP_SYSTEM.md](docs/dev/HELP_SYSTEM.md) |
| “Weird after click/zoom” | [docs/dev/TRACING.md](docs/dev/TRACING.md) |
| Known Qt quirks | [docs/dev/KNOWN_BUGS.md](docs/dev/KNOWN_BUGS.md) |
| Open engineering debt | [docs/dev/TODO.md](docs/dev/TODO.md) |

---

## Python Codebase Areas

The Python tree under `src/` is the reference implementation and the production code. When a task touches a plugin, **always read the Python equivalent first** — it documents the intended decomposition.

### Canvas, magnifier, overlays, render/export parity

Read:

1. [docs/dev/QRHI_CANVAS_FEATURES.md](docs/dev/QRHI_CANVAS_FEATURES.md)
2. [docs/dev/CONTRACTS.md](docs/dev/CONTRACTS.md) — complete contracts reference
3. [src/ui/canvas_presentation](src/ui/canvas_presentation)
4. [src/ui/widgets/canvas](src/ui/widgets/canvas)
5. [src/tabs/image_compare/canvas](src/tabs/image_compare/canvas)

Important:

- Live canvas, export preview, final export, and video snapshot rendering must stay visually consistent.
- If you change diff rendering, verify `highlight`, `grayscale`, `edges`, and `ssim` in both live and export paths.
- Avoid appending feature-specific logic to generic `canvas_presentation` helpers if it belongs in a feature folder.

### Help system and documentation UI

Read:

1. [docs/dev/HELP_SYSTEM.md](docs/dev/HELP_SYSTEM.md) — host shell, tab `contribute_help`, authoring, figure budgets
2. [src/plugins/help/dialog.py](src/plugins/help/dialog.py)
3. `sli_ui_toolkit.widgets.HelpDocumentView` in the external
   `Loganavter/sli-ui-toolkit` repository

Important:

- Host topics: `src/resources/help/` (`tree.json` + `en|ru/ui|platform/`). Tab topics: `src/tabs/<tab>/resources/help/`.
- Prefer `HelpDocumentView` + illustrated topic pages over `QTextBrowser` HTML.
- Keep help pages scenario-based, anchor-friendly, and split into short `###` sections.
- When features change, update help pages as part of the same task.

### Toolkit widgets and reusable UI

Read:

1. External toolkit repository: `https://github.com/Loganavter/sli-ui-toolkit`
2. Local checkout (optional): sibling `../sli-ui-toolkit` or `--toolkit-dir DIR` for `./launcher.sh context --cloc-only`
3. App-side overview: [docs/dev/UI_TOOLKIT_LIBRARY.md](docs/dev/UI_TOOLKIT_LIBRARY.md)
4. Toolkit `docs/dev/README.md` and `docs/dev/ARCHITECTURE.md` (in the toolkit repo)
5. Toolkit `docs/user/API_CATALOG.md` and `docs/dev/DESIGN_LANGUAGE.md`
6. For button/control work, also read toolkit `docs/user/BUTTON_API.md` and `docs/user/FLYOUT_SYSTEM.md` when relevant.

Important:

- Prefer public imports from `sli_ui_toolkit.widgets` for app code.
- Keep app-specific logic out of toolkit code.
- If a control family grows, split it into a folder like `buttons/` or `comboboxes/`.
- **Never** use raw `QFormLayout`/`QVBoxLayout` blocks for widget construction — use the toolkit painter pipeline.
- **Never** use QSS (`setStyleSheet`) to style toolkit widgets — the painter pipeline owns all visual output.

### Export, snapshot rendering, video editor

Read:

1. [src/tabs/image_compare/services/image_export/](src/tabs/image_compare/services/image_export/) and [src/tabs/multi_compare/services/image_export.py](src/tabs/multi_compare/services/image_export.py)
2. [src/tabs/image_compare/services/snapshot_render_plan_builder.py](src/tabs/image_compare/services/snapshot_render_plan_builder.py)
3. [src/tabs/image_compare/services/video_snapshot_rendering/](src/tabs/image_compare/services/video_snapshot_rendering) (tab implementation; plugin stub proxies via `create_startup_service`)

Important:

- Export paths are easy to desync from live rendering. Check them explicitly.
- Toast/progress UX for long-running export work is part of the product, not a side detail.

### Workspace tabs, state (Store/Redux), and cross-component events

Read:

1. [docs/dev/tabs/index.md](docs/dev/tabs/index.md) — tab interface, file layout, session lifecycle
2. [docs/dev/STORE.md](docs/dev/STORE.md) — Redux-style state contract (`Action → Dispatcher → RootReducer → Store`)
3. [docs/dev/EVENT_BUS.md](docs/dev/EVENT_BUS.md) — pub/sub for cross-component notifications, not for state
4. [docs/dev/THEMING.md](docs/dev/THEMING.md) — palette + QSS pipeline (toolkit `ThemeManager` + app-side wiring)
5. [src/core/store.py](src/core/store.py), [src/core/state_management/dispatcher.py](src/core/state_management/dispatcher.py), [src/core/state_management/reducers.py](src/core/state_management/reducers.py)
6. [src/core/plugin_system/event_bus.py](src/core/plugin_system/event_bus.py)

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

- Image load rejects sources above `65536 px` on a side (`AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION`). This is a decode/RAM sanity bound (codec still decompresses a full frame once; spill into `TiledPixelStore` is strip-written without a second full `HxWx4` copy), not a GPU-tile ceiling. Still-image export above `16384 px` (`AppConstants.EXPORT_TESTED_MAX_EDGE`) is allowed but warns that the path is untested (Image Compare and Multi Compare).
- Full-resolution pixel data for all canvas tabs lives in `TiledPixelStore` (`shared/image_processing/tiled_pixel_store.py`) — memmap-backed, always tiled. Shared render helpers: `shared/rendering/host_texture_cache.py`, `export_tiling.py`, `tile_geometry.py`.
- `ssim` has special handling because some paths depend on cached diff images and GPU diff textures.
- Help pages now support anchors and generated in-page TOC. Keep headings stable.

## Tests

See [docs/dev/TESTING.md](docs/dev/TESTING.md) for full layout and conventions.

Tests are grouped by subsystem under `tests/`:

- `tests/contracts/` — static architectural dogmas (AST scan, no runtime). **Run these first** after structural changes: `./launcher.sh test tests/contracts -q`. Each test encodes a rule from `docs/dev/CONTRACTS.md`, `ARCHITECTURE.md`, or canvas-feature docs — read the failing test name and its module docstring before “fixing” code around the dogma.
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

When something goes wrong after a click / zoom / state change and the cause is not obvious from the diff:

1. Reproduce with `./launcher.sh run --debug` (tracer on) or `IMGSLI_TRACE=1 ./launcher.sh run`.
2. Read `~/.local/share/ImproveImgSLI/trace.jsonl` — filter by `trace_id` from the input event that opened the chain.
3. See [docs/dev/TRACING.md](docs/dev/TRACING.md) for kind/category reference and filtering tips.
4. For plain text logs (not causal chains): [docs/dev/LOGGING.md](docs/dev/LOGGING.md) (`~/.local/share/ImproveImgSLI/log.txt`, overwritten each start).
5. For widget/theme/QSS mismatches: `./launcher.sh run --ui-inspector` — [docs/dev/UI_INSPECTOR.md](docs/dev/UI_INSPECTOR.md).

The tracer captures Redux dispatches, EventBus publishes, and render frames — much faster than hand-instrumenting with `logger` calls.

## When To Update Docs

Update documentation in the same task if you change:

- help page behavior or content
- toolkit public widget API
- rendering/export architecture
- user-visible hotkeys, settings, or workflow

Usually this means touching one of:

- [src/resources/help/en](src/resources/help/en)
- external `sli-ui-toolkit` `docs/user/API_CATALOG.md`
- external `sli-ui-toolkit` `docs/dev/ARCHITECTURE.md`
- [docs/dev/HELP_SYSTEM.md](docs/dev/HELP_SYSTEM.md)
- [docs/dev/QRHI_CANVAS_FEATURES.md](docs/dev/QRHI_CANVAS_FEATURES.md)

## Good Defaults For Agents

- Read [docs/dev/README.md](docs/dev/README.md) for misconceptions before assuming web-app patterns.
- For codebase size / where-the-code-lives questions, run `./launcher.sh context --cloc-only` and read `cloc.txt`. For everything else, search and read docs in the repo directly.
- Run `./launcher.sh test tests/contracts -q` after refactors that touch imports, canvas features, plugins, or tab layout.
- Prefer codebase search over guessing file locations.
- Prefer small, explicit patches.
- Prefer adding a focused regression test when fixing rendering/export/UI wiring bugs.
- If a bug involves preview vs export mismatch, inspect both code paths before changing anything.
- If runtime behavior is unclear after reading code, enable the tracer (`--debug`) before adding log statements.
