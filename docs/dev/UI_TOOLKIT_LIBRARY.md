# UI Toolkit Library (app-side boundary)

`sli-ui-toolkit` is a separate, versioned PySide6 UI package (not vendored
here — installed from `requirements-gui.txt`). This page covers only the
**app-side boundary**: what belongs in the app vs. the toolkit, and where
Improve-ImgSLI deliberately keeps app-owned UI logic.

For the toolkit's own API, package layout, and widget catalog — the parts
that change with the toolkit's own release cadence — **read the toolkit's
own docs first, not a copy here**: see AGENTS.md § "Toolkit widgets and
reusable UI" for the reading list (toolkit `docs/dev/README.md`,
`docs/dev/ARCHITECTURE.md`, `docs/user/API_CATALOG.md`,
`docs/dev/DESIGN_LANGUAGE.md`, `docs/user/BUTTON_API.md`,
`docs/user/FLYOUT_SYSTEM.md`), or the external
`Loganavter/sli-ui-toolkit` repository directly. A duplicated API/package
listing here would just go stale on every toolkit bump — this file used to
carry one and it already had drifted from the installed package.

## What belongs where

Code belongs in the toolkit when it can be used in a standalone PySide6 app
without importing any Improve-ImgSLI application module — reusable widgets,
generic flyout/dialog/overlay infrastructure, the i18n system, theme/icon
managers, worker primitives, painter/style bridges. Application state,
canvas logic, feature services, and plugins stay in the app.

**Before writing new interface code, check whether the toolkit already has
it** (see AGENTS.md) — don't default to stock Qt.

## Boundary rules

- Code inside `sli_ui_toolkit` must not import application packages
  (`core`, `domain`, `features`, `ui`, `services`, …) or depend on
  application concepts (store objects, viewport state, document state).
- Toolkit widgets receive app-specific behavior only through constructor
  parameters, callbacks/protocols, plain dataclasses/Qt signals, and
  icons/resources passed in from app code — never the reverse.
- Prefer public imports from `sli_ui_toolkit.widgets` for app code; keep
  app-specific logic out of toolkit code.
- **Never** use raw `QFormLayout`/`QVBoxLayout` blocks for widget
  construction — use the toolkit painter pipeline.
- **Never** use QSS (`setStyleSheet`) to style toolkit widgets — the
  painter pipeline owns all visual output.

## App-side dialog geometry (`shared_toolkit/ui/layout_sizing.py`)

Improve-ImgSLI keeps content-driven dialog sizing in the app layer (not in
`sli-ui-toolkit`).

**Full guide (skeleton, CSD, crush-resistant layouts, preview sizeHints,
i18n):** [DIALOGS.md](DIALOGS.md).

Short recipe:

1. **Primitives** — `widget_width_hint`, `sum_visible_widget_height_hint`, `measure_scroll_pages_stack`, `clamp_to_screen`.
2. **Per-dialog module** — e.g. `plugins/export/layout_geometry.py`, `plugins/settings/layout_geometry.py`.
3. **Apply** — `apply_dialog_geometry` + `GeometryApplyPolicy` (`lock_minimum_to_computed` for non-scroll dialogs; `force_resize` on the **initial** finalize after CSD).
4. **Lifecycle** — `ThemedDialog.install_dialog_geometry`; deferred finalize via `QTimer.singleShot(0, …)`; `sync_csd_chrome` after programmatic resize.

Reference consumers: Export (preview + form — best template for
content-locked dialogs), Settings (sidebar + scroll pages), Video editor,
Help, Image properties.
