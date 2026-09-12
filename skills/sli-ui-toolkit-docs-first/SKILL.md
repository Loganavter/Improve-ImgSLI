---
name: sli-ui-toolkit-docs-first
description: Fixes Improve-ImgSLI UI using sli-ui-toolkit documentation before reading toolkit source. Use for buttons, flyouts, dialogs, theming, painter pipeline, widget styling, toolkit API questions, or when a control looks wrong but app logic seems fine.
---

# sli-ui-toolkit — docs first

Toolkit docs usually answer the question. Read them before grepping `sli_ui_toolkit` source.

## Read order (stop when enough)

1. App bridge: [docs/dev/UI_TOOLKIT_LIBRARY.md](../../../docs/dev/UI_TOOLKIT_LIBRARY.md)
2. App theming / dialogs: [docs/dev/THEMING.md](../../../docs/dev/THEMING.md), [docs/dev/DIALOGS.md](../../../docs/dev/DIALOGS.md)
3. External toolkit docs (sibling `../sli-ui-toolkit`, install path, or repo `Loganavter/sli-ui-toolkit`):
   - `docs/user/API_CATALOG.md` — full public surface
   - `docs/user/BUTTON_API.md` — buttons, regions, `group=`, checked state
   - `docs/user/FLYOUT_SYSTEM.md` — flyout managers and show policy
   - `docs/dev/DESIGN_LANGUAGE.md` — tokens, variants, visual rules
   - `docs/dev/README.md`, `docs/dev/ARCHITECTURE.md` — package layout when docs are not widget-specific

### Which toolkit copy is authoritative

Before trusting or editing the sibling `../sli-ui-toolkit` checkout, check
`requirements-gui.txt` for an `-e ../sli-ui-toolkit` line. With that line the
toolkit is installed **editable** from the sibling — its local source and docs
are authoritative, and edits there are live. Without it (pinned version / git
ref / PyPI), the sibling — if present at all — is NOT what the app imports:
treat the toolkit as a fixed external dependency and use its released
docs/API only.

If visuals still do not match after reading docs, run `./launcher.sh run --ui-inspector` ([docs/dev/UI_INSPECTOR.md](../../../docs/dev/UI_INSPECTOR.md)).

## Hard rules

- Toolkit widgets use the **painter pipeline** — no ad-hoc QSS (`setStyleSheet`) on toolkit controls.
- No raw `QFormLayout` / `QVBoxLayout` construction blocks for toolkit UI — use the toolkit painter pipeline.
- Prefer `from sli_ui_toolkit.widgets import …` (public imports).
- App-specific logic stays in Improve-ImgSLI; reusable API belongs in the toolkit repo.

## App vs toolkit boundary

| Layer | Owns |
|---|---|
| Toolkit | Generic widgets, flyouts, theme bridge, painter, `AdaptiveTabStrip`, `TopTabHost` |
| App | `ui/flyout_policy.py`, dialog geometry (`plugins/*/layout_geometry.py`), canvas, store wiring, icons and i18n roots injected at startup |

Dialog sizing recipe: [docs/dev/DIALOGS.md](../../../docs/dev/DIALOGS.md) + per-dialog `layout_geometry.py` modules.

## When to open toolkit source

Only if documentation does not cover:

- an undocumented edge case or default
- a confirmed toolkit bug
- a need to verify exact implementation of a documented API

Do **not** read toolkit source to learn basics that `BUTTON_API.md` or `API_CATALOG.md` already explain.

## Common doc → task map

| Task | Start here |
|---|---|
| Toggle / icon button / underline | `BUTTON_API.md` |
| Popup / menu / exclusive groups | `FLYOUT_SYSTEM.md` + app `ui/flyout_policy.py` |
| Colors / dark mode / palette | `THEMING.md` + `DESIGN_LANGUAGE.md` |
| Modal / CSD / minimum size | `DIALOGS.md` |
| Tab strip / top tabs | `UI_TOOLKIT_LIBRARY.md` (AdaptiveTabStrip, TopTabHost) |
