---
name: help-authoring
description: Authors and maintains the in-app Help manual (host + tab topics, fs scan, figure budgets, {{tr:}} tokens, i18n keys). Use when adding or updating help pages, contributing a tab's help hub, changing help figures or their assets, or fixing help i18n keys.
---

# In-app Help authoring

Improve-ImgSLI ships an illustrated manual (hubs → cards → pages) rendered by
the toolkit `HelpDocumentView`. Primary discovery stays Find Action; Help
teaches shape and habits.

Authoritative reference: [docs/dev/HELP_SYSTEM.md](../../../docs/dev/HELP_SYSTEM.md) — read it before designing a page. This skill is the decision map.

## When to touch Help

Per AGENTS.md, any user-visible change (behavior, hotkeys, settings, workflows)
updates the matching help page **in the same task**. New tab → contribute its
own subtree; new feature → new `###` section or page; changed dialog → update
its page.

## Where things live

| Owner | Path |
|---|---|
| Host scan / dialog | `src/plugins/help/` |
| Host topics + shared assets | `src/resources/help/` (`en|ru|zh|pt_BR/`, `assets/`) |
| Tab topics | `src/tabs/<tab>/help.py` (`build_help_hub_contribution()` for multi-page hubs, mount = `workspace.<tab>` by convention) + `src/tabs/<tab>/resources/help/` |
| Toolkit rendering | `sli_ui_toolkit.widgets.HelpDocumentView` (read-only from the app side) |

Tabs publish hub presentation via `create_service("contribute_help")`; the
Help plugin never imports `tabs.*`. Structure itself is scanned from the
filesystem — dirs are hubs, `*.md` files are pages, ids are dotted paths.

## Authoring rules (summary)

- Page title `##`; concept sections `###` with stable `{#anchor}`; the TOC is generated from anchored `###` — keep titles short.
- **No GFM pipe tables** in bodies: consecutive `| … |` rows render as one paragraph. Use `- **X** — …` lists.
- i18n: labels via `{{tr:dotted.key}}`; never hardcode control names. Bodies ship in en + ru + zh + pt_BR; a missing language falls back to EN.
- Figures as body-relative paths into the owning package's `assets/`. Never add figures outside the per-topic budget table in HELP_SYSTEM.md.
- Cross-link with `help://dotted.path#anchor`; no trailing `### Related` dumps — weave links into prose or use a short `### Next topics`.

### Host vs tab content

- Keep host generic pages to shared behavior only; put tab specifics in contributed tab pages.
- In host leave a stub only: `###` header + stable `{#anchor}` + one line + `help://` link to the tab overview.
- Keep anchors stable — TOC and `help://dotted.path#anchor` links depend on them; never rename to fix duplication.
- Anti-pattern (pre-webcanon): a host page duplicated the MC overview instead of linking to `help://workspace.multi_compare.overview`.
- Positive pattern: `platform.settings` shell + tab sections via `build_settings_contribution` (`src/tabs/image_compare/use_cases/registration.py:43`).

## Figure policy (default zero)

A page does not need a picture. Add `:::figure` only when a screenshot answers
a question prose cannot (layout, spatial gesture, dialog shape, a mode that
*looks* different).

| Budget | When | Placement |
|---|---|---|
| 0 | Chord/settings inventories, anything fully named by UI strings | — |
| 1 | One primary surface / spatial idea for the whole page | after intro, prefer `side=block` |
| 2 | Page teaches distinct visual states | one figure next to the `###` it illustrates |
| 3+ | Exception: several modes/gestures that each look different | one per mode/gesture section |

Rules: need before asset; screenshots go to final filenames under the owning
package's `assets/`; caption = UI path via `{{tr:…}}`; size
with `width=`/`height=` (prefer `height=` for toolbar strips); lightbox is
free.

## Verification loop

```bash
env QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_help_*.py
```

Key tests: `test_help_tree.py` (paths, hub fragments, scenario-card page shape),
`test_help_interpolate.py` (`{{tr:}}`, body-relative images),
`test_help_browser_navigation.py` (incl. Missing-page),
`test_help_dialog_opens.py`. Scenario shape (`##` + `###`) is enough for the
tests — figures are never required.
