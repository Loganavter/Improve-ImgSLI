---
name: help-authoring
description: Authors and maintains the in-app Help manual (host + tab topics, tree.json merge, figure budgets, {{tr:}}/{{img:}} tokens, i18n keys, figure checks). Use when adding or updating help pages, contributing a tab's help subtree, changing help figures or their assets, or fixing help i18n keys.
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
| Host shell / dialog / merge | `src/plugins/help/` |
| Host topics + shared assets | `src/resources/help/` (`tree.json`, `figures.json`, `en|ru|zh|pt_BR/`, `assets/`) |
| Tab topics | `src/tabs/<tab>/help.py` (`contribute_help(..., attach_under="workspace", body_root=..., asset_root=...)`) + `src/tabs/<tab>/resources/help/` |
| Toolkit rendering | `sli_ui_toolkit.widgets.HelpDocumentView` (read-only from the app side) |

Tabs publish via `notify_all("contribute_help", registry)`; the Help plugin
never imports `tabs.*`. Host `workspace` hub starts empty — tabs append under
`attach_under="workspace"`.

## Authoring rules (summary)

- Page title `##`; concept sections `###` with stable `{#anchor}`; the TOC is generated from anchored `###` — keep titles short.
- **No GFM pipe tables** in bodies: consecutive `| … |` rows render as one paragraph. Use `- **X** — …` lists.
- i18n: labels via `{{tr:dotted.key}}`; never hardcode control names. Bodies ship in en + ru + zh + pt_BR; a missing language falls back to EN.
- Figures via `{{img:slot.id}}` → path in the owning package's `figures.json`. Never add figures outside the per-topic slot table in HELP_SYSTEM.md.
- Cross-link with `help://slug#anchor`; no trailing `### Related` dumps — weave links into prose or use a short `### Next topics`.

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

Rules: need before asset; screenshots go to the exact paths already listed in
`figures.json` (stubs are byte-identical to `assets/_stub.jpg` and are
reported by `check_help_figures.py`); caption = UI path via `{{tr:…}}`; size
with `width=`/`height=` (prefer `height=` for toolbar strips); lightbox is
free.

## Verification loop

```bash
python src/devtools/check_help_figures.py                  # ready / stub / missing inventory
python src/devtools/check_help_figures.py --json --strict  # machine-checkable; fails on stubs/missing
env QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_help_*.py
```

Key tests: `test_help_tree.py` (aliases, merge, scenario-card page shape),
`test_help_interpolate.py` (`{{tr:}}` / `{{img:}}`), `test_help_browser_navigation.py`,
`test_help_dialog_opens.py`. Scenario shape (`##` + `###`) is enough for the
tests — figures are never required.
