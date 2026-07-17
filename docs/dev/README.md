# Development Documentation

Improve-ImgSLI is a **desktop workspace** for image / media comparison (Image Compare, Multi Compare, export, video timeline). These docs cover architecture, contracts, and how to change the product safely.

User install: [INSTALL.md](../INSTALL.md). Contributor setup: [CONTRIBUTING.md](../../CONTRIBUTING.md). Product story: [Development History](../DEVELOPMENT_HISTORY.md) · [VISION.md](../../VISION.md).

**AI / agent onboarding:** [AGENTS.md](../../AGENTS.md) (tooling, task routing, dogmas). Cursor skills: `.cursor/skills/imgsli-devtools/`, `.cursor/skills/sli-ui-toolkit-docs-first/`. Docs: search `docs/dev/` in-repo. Codebase size only: `./launcher.sh context --cloc-only`.

## Project cheat sheet

Orientation for humans and agents. Misconceptions first, then affirmative facts.

### What this is not

- Is this a React / web app? — **No.** Desktop Python under `src/`, UI via **PySide6** (Qt).
- Is it Electron / Chromium? — **No.** Native Qt + a custom-drawn toolkit, not a browser shell.
- Is the UI QML / Qt Quick? — **Mostly no.** App chrome is toolkit-painted widgets; the comparison canvas is **QRhi** (GPU).
- Is state Redux.js / Zustand? — **No JS store.** In-process: `Action → Dispatcher → RootReducer → Store` ([STORE.md](STORE.md)).
- Do widgets mutate app state directly? — **No.** Dispatch actions. EventBus is for facts (“export finished”), not a second store ([EVENT_BUS.md](EVENT_BUS.md)).
- Are Settings / Help / Export “core”? — **No.** App-wide plugins in `src/plugins/`; workspace modes in `src/tabs/` ([tabs/index.md](tabs/index.md), [PLUGINS.md](PLUGINS.md)).
- Is `sli-ui-toolkit` vendored here? — **No.** Separate package ([UI_TOOLKIT_LIBRARY.md](UI_TOOLKIT_LIBRARY.md)). Painter pipeline owns toolkit looks — not ad-hoc QSS.
- Do live canvas and export share one path? — **Not automatically.** Live, preview, final export, and video snapshots must stay visually consistent on purpose ([QRHI_CANVAS_FEATURES.md](QRHI_CANVAS_FEATURES.md)).
- Is Find Action a mini-app? — **No.** `ActionRegistry` catalog with reveal/pulse into real widgets ([ACTIONS.md](ACTIONS.md)).
- Will this be rewritten in C++/Rust? — **No (closed topic).** A short failed experiment around first-frame flicker was abandoned; the flicker was fixed in Python. A full rewrite is unlikely. Story: [Development History](../DEVELOPMENT_HISTORY.md).

### Stack and layout

| Piece | Choice |
|---|---|
| Language / UI | Python 3.10+, PySide6 |
| App state | Redux-style Store + tab-owned slots |
| Workspace modes | Tabs (`image_compare`, `multi_compare`, session picker) |
| App-wide features | Plugins (settings, help, export, …) |
| Chrome widgets | External `sli-ui-toolkit` |
| Canvas | QRhi feature stack (per-tab features) |
| Pixels | `TiledPixelStore` (memmap) + host texture cache |
| Locales | EN / RU / zh / pt_BR under `src/resources/i18n/` + tab/plugin packs |
| Themes | `themes.json` + toolkit `ThemeManager` ([THEMING.md](THEMING.md)) |

```
src/
  core/          bootstrap, store, dispatcher, plugins host, events
  domain/        Qt-light data shapes
  ui/            main window, presenters, shared canvas chrome
  plugins/       settings, help, export, …
  tabs/          workspace modes (own UI, state, canvas, i18n, help)
  shared/        image processing + rendering helpers
  shared_toolkit/  app-side QSS / older glue (prefer sli-ui-toolkit for new UI)
  resources/     themes, host i18n, host help
  services/      I/O, notifications, OS integration
```

### Day-0 commands

```bash
./launcher.sh run          # app
./launcher.sh test         # suite
./launcher.sh run --debug  # one-shot debug log
./launcher.sh run --ui-inspector
```

Focused tests: `env QT_QPA_PLATFORM=offscreen pytest -q tests/<area>/…` — see [TESTING.md](TESTING.md).

### Hard rules (do not “cleverly” bypass)

- State changes go through the dispatcher; do not poke `Store` fields.
- Toolkit widgets: no raw form layouts for construction, no QSS for looks.
- New workspace mode = new `src/tabs/<name>/` implementing the tab contract — not logic stuffed into `core/`.
- Rendering / export / video snapshot parity is product behavior, not optional polish.
- User-visible strings and Help topics update with the feature ([RESOURCES_I18N.md](RESOURCES_I18N.md), [HELP_SYSTEM.md](HELP_SYSTEM.md)).
- Soft limit today: load rejects sources above **65536 px** on a side — not because of tiles (GPU residency is tiled), but because decode still materializes a full frame once. Spill into `TiledPixelStore` is strip-written (no second full copy). Still-image export above **16384 px** on a side is allowed but shows an untested-resolution warning (Image Compare and Multi Compare).

### Where to look

| Task | Start here |
|---|---|
| Architecture overview | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Protocols / isolation | [CONTRACTS.md](CONTRACTS.md) |
| New canvas feature | [QRHI_CANVAS_FEATURES.md](QRHI_CANVAS_FEATURES.md) |
| New workspace tab | [tabs/index.md](tabs/index.md) |
| Dialog / CSD chrome | [DIALOGS.md](DIALOGS.md) |
| Toolkit widgets | [UI_TOOLKIT_LIBRARY.md](UI_TOOLKIT_LIBRARY.md) |
| Find Action row | [ACTIONS.md](ACTIONS.md) |
| “Weird after click/zoom” | [TRACING.md](TRACING.md) |
| Known Qt quirks | [KNOWN_BUGS.md](KNOWN_BUGS.md) |
| Open engineering debt | [TODO.md](TODO.md) |
| AI / agent onboarding | [AGENTS.md](../../AGENTS.md) · search `docs/dev/` · `./launcher.sh context --cloc-only` for size stats |

## Doc index

### Architecture and state

- [ARCHITECTURE.md](ARCHITECTURE.md) — layers and bootstrap
- [CONTRACTS.md](CONTRACTS.md) — protocols and feature isolation
- [STORE.md](STORE.md) — actions / reducers / store
- [EVENT_BUS.md](EVENT_BUS.md) — pub/sub for facts, not state
- [PRESENTERS.md](PRESENTERS.md) — UI ↔ store bridge
- [PLUGINS.md](PLUGINS.md) — plugin host
- [tabs/index.md](tabs/index.md) · [TAB_CONTRACT.md](TAB_CONTRACT.md) — workspace tabs
- [CAPABILITY_ALIASES.md](CAPABILITY_ALIASES.md) — capability name aliases

### UI, chrome, product surfaces

- [UI_TOOLKIT_LIBRARY.md](UI_TOOLKIT_LIBRARY.md) — `sli-ui-toolkit`
- [DIALOGS.md](DIALOGS.md) — dialog geometry and CSD
- [THEMING.md](THEMING.md) — palette / QSS registration
- [RESOURCES_I18N.md](RESOURCES_I18N.md) — translations and resources
- [ACTIONS.md](ACTIONS.md) — Find Action catalog
- [HELP_SYSTEM.md](HELP_SYSTEM.md) · [HELP_WIDGET.md](HELP_WIDGET.md)

### Rendering and canvas

- [QRHI_CANVAS_FEATURES.md](QRHI_CANVAS_FEATURES.md) — feature system, zoom/pan
- [rendering/index.md](rendering/index.md) — rendering docs hub
- [rendering/display-image-pipeline.md](rendering/display-image-pipeline.md)
- [rendering/tile-rendering-system.md](rendering/tile-rendering-system.md)
- [RHI_RENDERER_REFACTOR.md](RHI_RENDERER_REFACTOR.md) · [CANVAS_FEATURE_REGISTRY_PER_TAB.md](CANVAS_FEATURE_REGISTRY_PER_TAB.md) — active plans

### Debug, test, ops

- [TESTING.md](TESTING.md) — suite layout and conventions
- [TRACING.md](TRACING.md) — Redux / EventBus / frame tracer
- [UI_INSPECTOR.md](UI_INSPECTOR.md) — theme / QSS inspector
- [LOGGING.md](LOGGING.md) — logging
- [KNOWN_BUGS.md](KNOWN_BUGS.md) — diagnosed platform quirks
- [TODO.md](TODO.md) — open work
