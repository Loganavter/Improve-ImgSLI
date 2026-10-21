---
name: help-authoring
description: Authors and maintains the in-app Help manual (host + tab topics, fs scan, figure budgets, literal on-screen labels). Use when adding or updating help pages, contributing a tab's help hub, changing help figures or their assets, or aligning labels in help text.
---

# In-app Help authoring

Improve-ImgSLI ships an illustrated manual (hubs → cards → pages) rendered by
the app's `HelpDialog` (`src/plugins/help/dialog.py`): toolkit
`parse_help_blocks` → `Text(mode="document")`, with host-owned TOC card,
scroll area and figure lightbox. Primary discovery stays Find Action; Help
teaches shape and habits.

Authoritative reference: [docs/dev/HELP_SYSTEM.md](../../docs/dev/HELP_SYSTEM.md) — read it before designing a page. This skill is the decision map.

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
| Rendering | toolkit `parse_help_blocks` → `Text(mode="document")`; dialog, TOC, scroll area and lightbox are app chrome (`src/plugins/help/dialog.py`, `image_lightbox.py`) — read-only from the app side |

Tabs publish hub presentation via `create_service("contribute_help")`; the
Help plugin never imports `tabs.*`. Structure itself is scanned from the
filesystem — dirs are hubs, `*.md` files are pages, ids are dotted paths.

## Authoring rules (summary)

- Page title `##`; concept sections `###` with stable `{#anchor}`; the TOC is generated from anchored `###` — keep titles short.
- **Tables parse** (`parse_help_blocks` → `TableBlock`: first row is the header when the next line is a `---` separator; `\|` escapes a pipe) — but the corpus test still rejects `| … |` rows in shipped bodies (`test_help_tree.py`), so keep `- **X** — …` lists until that assertion is lifted.
- Labels are literal, on-screen names in `**bold**` (no `{{tr:}}` tokens): write the control exactly as the UI shows it. Bodies ship in en + ru + zh + pt_BR; a missing language falls back to EN. Prose canon: [docs/dev/HELP_STYLE_GUIDE.md](../../docs/dev/HELP_STYLE_GUIDE.md). <!-- doc-truth:allow -->
- Figures as body-relative paths into the owning package's `assets/`. Never add figures outside the per-topic budget table in HELP_SYSTEM.md.
- Cross-link with `help://dotted.path#anchor`; no trailing `### Related` dumps — weave links into prose or use a short `### Next topics`.

### Host vs tab content

- Keep host generic pages to shared behavior only; put tab specifics in contributed tab pages.
- In host leave a stub only: `###` header + stable `{#anchor}` + one line + `help://` link to the tab overview.
- Keep anchors stable — TOC and `help://dotted.path#anchor` links depend on them; never rename to fix duplication.
- Anti-pattern (pre-webcanon): a host page duplicated the MC overview instead of linking to `help://workspace.multi_compare.overview`.
- Positive pattern: `platform.settings` shell + tab sections via `build_settings_contribution` (`src/tabs/image_compare/use_cases/registration.py:49`).

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
package's `assets/`; caption explains the picture (what is shown), not a menu
path; size
with `width=`/`height=` (prefer `height=` for toolbar strips); lightbox is
free.

## Verification loop

```bash
env QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_help_*.py
```

Key tests: `test_help_tree.py` (paths, hub fragments, scenario-card page shape),
`test_help_bodies.py` (literal labels — no `{{tr:`, body-relative images), <!-- doc-truth:allow -->
`test_help_browser_navigation.py` (incl. Missing-page),
`test_help_dialog_opens.py`. Scenario shape (`##` + `###`) is enough for the
tests — figures are never required.
