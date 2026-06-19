# Contributing Guide

Thank you for your interest in contributing to Improve-ImgSLI! This guide helps you set up a development environment, understand the repository layout, and build distributables.

If you are a user who just wants to install and use the app, please see:
- docs/INSTALL: docs/INSTALL.md
- In-app Help (recommended): src/resources/help/en/
- Russian Help: src/resources/help/ru/

## Quick start (development)

Prerequisites:
- Python 3.10+ recommended
- Git
- On Linux/macOS: bash shell for launcher scripts
- On Windows for packaging: Inno Setup (optional, for installer build)

Clone and run:
```bash
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
chmod +x launcher.sh
./launcher.sh run
```

The launcher script manages a virtual environment, installs dependencies, and runs the app. Explore additional commands:
```bash
./launcher.sh help
```
Common actions:
- Install/refresh dependencies: `./launcher.sh install`
- Recreate venv from scratch: `./launcher.sh recreate`
- Delete venv and Python caches: `./launcher.sh delete`
- Clear Python caches only: `./launcher.sh rm-cache`
- Run the test suite: `./launcher.sh test`
- Install/uninstall desktop entry: `./launcher.sh install-desktop` / `uninstall-desktop`
- Enable/disable persistent debug logging: `./launcher.sh --enable-logging` / `--disable-logging`
- Debug logging for one session: `./launcher.sh run --debug`
- Force a theme: `./launcher.sh run --theme dark`
- Inspect UI colors and QSS candidates: `./launcher.sh run --ui-inspector`

Tip: Prefer updating the in-app Help when you add features; the README links to those docs.

## Repository structure (high level)

- src/core: app bootstrap, store (state), settings, theme, plugin coordination, tracing
- src/domain: domain types and workspace model, Qt adapters
- src/events: in-process event bus
- src/services: IO, system, and workflow services
- src/tabs: workspace tab system (contract, registry, built-in tabs)
- src/plugins: feature plugins (analysis, comparison, export, help, layout, settings, video_editor)
- src/ui: Qt UI — main window, canvas (infra/features/presentation), presenters (MVP), widgets, managers, onboarding
- src/shared_toolkit: shared utilities reused by the app and launcher scripts
- src/resources: application assets (icons, fonts, styles, themes) and user Help in multiple languages
- sli-ui-toolkit: external versioned UI toolkit consumed by the app (widgets, managers, services)
- build: packaging templates (Windows / Flatpak / AUR) and CI helpers
- tests: pytest suite (contracts, plugins, render, runtime, toolkit, video)
- launcher.sh: CLI helper to manage venv and run common tasks

Useful entry points:
- App main: src/__main__.py
- UI main window: src/ui/main_window/window.py (composed from sibling modules: actions.py, appearance.py, composer.py, layouts.py, lifecycle.py, runtime.py, startup.py, ui.py)
- Main presenter: src/ui/presenters/main_window/presenter.py
- Store (state): src/core/store.py and src/core/store_*.py modules
- Theme: src/core/theme.py
- Bootstrap: src/core/bootstrap.py
- Help Index (EN): src/resources/help/en/introduction.md
- Canvas feature architecture: docs/dev/CANVAS_FEATURES.md
- Developer docs index: docs/dev/README.md

## Architectural notes

- Pattern: MVP (Model-View-Presenter). Keep UI (Qt widgets), presenter logic, and core state/services decoupled.
- State: Redux-style store (`src/core/store.py` + `store_*` modules). Actions → reducers → notify subscribers. Never mutate state in reducers — use `dataclasses.replace`.
- Events: `src/events/` event bus for async, decoupled notifications. Watch for circular event chains (max depth 10).
- Canvas features: zero direct imports of features in shared code. Communication goes through capability aliases, `CanvasWidgetFeature` contracts, and auto-discovery in `src/ui/canvas_infra/scene/widget_registry.py`. All visual attributes are in canvas-px. See docs/dev/CANVAS_FEATURES.md and the `_template/` feature for a starting point.
- Plugins / tabs: features and workspace tabs are pluggable; degrade gracefully when an optional plugin is missing.
- Logging: use the standard `logging` module via the project's logger. Avoid `print` statements.
- Shared components: consider using the external `sli-ui-toolkit` package and `src/shared_toolkit` for reusable UI and utilities. Toolkit changes belong in the `Loganavter/sli-ui-toolkit` repository, not in this app tree.

More background: see `docs/dev/ARCHITECTURE.md`, `docs/dev/CONTRACTS.md`, `docs/dev/TAB_CONTRACT.md`, `docs/dev/UI_TOOLKIT_LIBRARY.md`, `docs/dev/TESTING.md`, `docs/dev/TRACING.md`, and the top-level `AGENTS.md` / `VISION.md`.

Developer UI inspection: `docs/dev/UI_INSPECTOR.md` describes the
`--ui-inspector` launcher flag and the Wayland-safe in-app overlay used for
widget color, palette, theme-token, and QSS candidate diagnostics.

## Coding guidelines

- Python 3.10+ syntax; prefer type hints where practical.
- Keep modules focused; avoid creating new "god" modules.
- UI strings should support translations when visible to users.
- Follow existing naming and folder conventions.
- Keep public APIs of presenters/services minimal and explicit.

### Commit messages

- Prefer Conventional Commits (optional but encouraged):
  - feat: new user-facing feature
  - fix: bug fix
  - refactor: code restructure without feature change
  - docs: documentation-only change
  - perf: performance improvements
  - build/chore: packaging, CI, tooling
  - revert: revert a previous commit

### Opening issues and PRs

- Before large changes, open an Issue to discuss approach.
- Keep PRs focused and reasonably small.
- Include a short summary of the change and any user-facing impacts.
- Update in-app Help files under src/resources/help/... when appropriate.

## Running from source (minimal)

Linux/macOS:
```bash
chmod +x launcher.sh
./launcher.sh run
```

Windows (PowerShell or bash via Git Bash):
```powershell
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
bash launcher.sh run
```

If you prefer manual venv management:
```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS
# .\venv\Scripts\activate       # Windows PowerShell
pip install -r requirements-gui.txt
pip install -r requirements-dev.txt   # optional: tests
python -m src
```

Runtime deps live in `requirements-gui.txt` (PyQt6, Pillow, numpy, scikit-image, imagecodecs, PyOpenGL, Markdown). Dev/test deps live in `requirements-dev.txt` (pytest, pytest-sugar).

## Running tests

```bash
./launcher.sh test                          # full suite
./launcher.sh test tests/runtime -k gesture # forward extra args to pytest
```

See `docs/dev/TESTING.md` for conventions and layout of the `tests/` tree.

## Building packages

### Windows (PyInstaller + Inno Setup)

1) Create binaries with PyInstaller using the provided spec:
```bash
python -m pip install -r requirements-gui.txt pyinstaller
python -m PyInstaller build/Windows-template/Improve_ImgSLI.spec
```
- Spec file: build/Windows-template/Improve_ImgSLI.spec
- Helper script: build/Windows-template/build_windows.py (and build.bat)

2) Build installer with Inno Setup:
- Open build/Windows-template/inno_setup_6.iss in Inno Setup Compiler
- Press F9 (Compile) to produce the installer in build/Windows-template/Output

### Flatpak (Flathub)

- Flatpak manifest: build/Flatpak-template/io.github.Loganavter.Improve-ImgSLI.yaml
- Metadata: build/Flatpak-template/io.github.Loganavter.Improve-ImgSLI.metainfo.xml
- Python modules: build/Flatpak-template/python3-modules.json
- Pinned requirements: build/Flatpak-template/requirements.txt

Install/run (user side):
```bash
flatpak install io.github.Loganavter.Improve-ImgSLI
flatpak run io.github.Loganavter.Improve-ImgSLI
```

### Arch Linux (AUR)

- PKGBUILD: build/AUR-template/PKGBUILD
- Desktop file and launcher script in build/AUR-template/

Users can install via helpers:
```bash
yay -S improve-imgsli
```

## Documentation and translations

Developer documentation lives in `docs/dev/` (see `docs/dev/README.md` for the index). User-facing Help and UI strings are split across several locations:

- In-app Help (Markdown topics, one folder per language):
  - `src/resources/help/en/` (reference)
  - `src/resources/help/ru/`, `src/resources/help/pt_BR/`, `src/resources/help/zh/`
- Shared UI translations (JSON, merged recursively at runtime; dotted keys via `tr("...")`):
  - `src/resources/i18n/{en,ru,pt_BR,zh}/` — see `src/resources/i18n/README.md` for conventions
  - Loader: `src/resources/translations.py`
- Per-area / per-plugin / per-feature translations, co-located with the code they belong to:
  - `src/ui/main_window/translations.py`
  - `src/tabs/multi_compare/resources/i18n/`
  - `src/plugins/help/resources/i18n/`
  - `src/plugins/export/resources/i18n/`
  - `src/plugins/settings/resources/i18n/` (+ `src/plugins/settings/translations.py`)
  - `src/plugins/video_editor/resources/i18n/` (+ `src/plugins/video_editor/translations.py`)
  - `src/ui/canvas_features/<feature>/resources/i18n/` (e.g. `magnifier/`)

When you add or modify features:
- Update or add the corresponding topic in Help (e.g., magnifier, settings, export).
- Add new UI strings to the matching `i18n/` folder (shared vs. feature/plugin-local) and reuse existing dotted keys where possible.
- Keep all language packs in sync — keys should exist in every language directory.
- Keep README minimal; link to Help for details.

## Acknowledgements

Thanks to everyone who has helped shape Improve-ImgSLI over the years. A few specific shout-outs:

- [@johnpetersa19](https://github.com/johnpetersa19) — for cleaning up the README Markdown in [PR #18](https://github.com/Loganavter/Improve-ImgSLI/pull/18).
- [@Anduin9527](https://github.com/Anduin9527/Improve-ImgSLI) — the GUI-refresh idea introduced around v3–v4 was borrowed from their fork.

## License

This project is licensed under the MIT License. See:
- LICENSE
