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
./launcher.sh --help
```
Common actions:
- Recreate venv from scratch: `./launcher.sh recreate`
- Delete venv: `./launcher.sh delete`
- Enable extended logging: `./launcher.sh enable-logging`

Tip: Prefer updating the in-app Help when you add features; the README links to those docs.

## Repository structure (high level)

- src/core: core application logic (state, settings, logging, geometry, theme)
- src/ui: Qt UI, dialogs, presenters (MVP), widgets, managers
- src/image_processing: IO, resize/composition, analysis (metrics, edges, diff), drawing
- src/resources: application assets (icons, fonts, styles) and user Help in multiple languages
- src/shared_toolkit: shared library reused across projects (widgets, managers, utils, fonts)
- build: packaging templates (Windows/Flatpak/AUR), icons, desktop files, specs
- scripts: utility scripts (e.g., help content checks)
- launcher.sh: CLI helper to manage venv and run tasks

Useful entry points:
- App main: src/__main__.py
- UI main window: src/ui/main_window.py
- Presenter: src/ui/presenters/main_window_presenter.py
- Settings: src/core/settings.py
- Image composing: src/image_processing/composer.py
- Help Index (EN): src/resources/help/en/introduction.md

## Architectural notes

- Pattern: MVP (Model-View-Presenter). Keep UI (Qt widgets), presenter logic, and core state/services decoupled.
- Image pipeline: dynamic canvas rendering, magnifier draws beyond image bounds, caching for smooth UX with large images.
- Logging: use the standard logging system (src/core/logging.py). Avoid print statements.
- State: persist window geometry and selected options across sessions (src/core/app_state.py, src/core/settings.py).
- Shared components: consider using/adding to src/shared_toolkit for reusable UI or utilities across projects.

## Coding guidelines

- Python 3.10+ syntax; prefer type hints where practical.
- Keep modules focused; avoid creating new “god” modules.
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
# .\venv\Scripts\activate      # Windows PowerShell
pip install -r requirements.txt
python -m src
```

## Building packages

### Windows (PyInstaller + Inno Setup)

1) Create binaries with PyInstaller using the provided spec:
```bash
python -m pip install -r requirements.txt pyinstaller
python -m pyinstaller build/Windows-template/Improve_ImgSLI.spec
```
- Spec file: build/Windows-template/Improve_ImgSLI.spec

2) Build installer with Inno Setup:
- Open build/Windows-template/inno_setup_6.iss in Inno Setup Compiler
- Press F9 (Compile) to produce the installer in build/Windows-template/Output

### Flatpak (Flathub)

- Flatpak manifest: build/Flatpak-template/io.github.Loganavter.Improve-ImgSLI.yaml
- Metadata: build/Flatpak-template/io.github.Loganavter.Improve-ImgSLI.metainfo.xml
- Modules: build/Flatpak-template/python3-modules.json

Install/run (user side):
```bash
flatpak install io.github.Loganavter.Improve-ImgSLI
flatpak run io.github.Loganavter.Improve-ImgSLI
```

### Arch Linux (AUR)

- PKGBUILD: build/AUR-template/PKGBUILD
- Desktop file and launcher scripts in build/AUR-template/

Users can install via helpers:
```bash
yay -S improve-imgsli
```

## Documentation and translations

- In-app Help (EN): src/resources/help/en/
- In-app Help (RU): src/resources/help/ru/
- Other languages (e.g., zh, pt_BR) live under src/resources/help/

When you add or modify features:
- Update or add the corresponding topic in Help (e.g., magnifier, settings, export).
- Keep README minimal; link to Help for details.

## License

This project is licensed under the MIT License. See:
- LICENSE.txt