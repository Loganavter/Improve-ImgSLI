# Help plugin (hierarchical illustrated manual)

Status: **live** — host shell + tab-owned topic contributions

Product role: secondary illustrated topics (hubs → cards → pages). Primary
discovery stays **Find Action** / command palette. See [ACTIONS.md](./ACTIONS.md)
for `help_page` / `help_anchor` on actions.

Related:

- [tabs/capability-mechanisms.md](./tabs/capability-mechanisms.md) — `notify_all("contribute_help")`
- [HELP_WIDGET.md](./HELP_WIDGET.md) — toolkit `MarkdownHelpDialog` / `QTextBrowser` helpers (tests only)
- Toolkit: `sli_ui_toolkit.widgets.HelpDocumentView`

---

## Ownership split

| Owner | Owns |
|-------|------|
| Host plugin `plugins/help/` | Dialog shell, navigator, hub UI, merge, host topics (UI + Platform) |
| Host `resources/help/` | `tree.json` shell + host page bodies + shared `assets/` |
| Each tab | Subtree under Workspace, page bodies, aliases, icon resolver, help i18n keys |

Host **must not** import `tabs.*` for icons or hardcode tab topic trees.
Tabs publish via the same broadcast pattern as settings/actions.

```text
TabRegistry.notify_all("contribute_help", HelpContributionRegistry)
  → each tab create_service("contribute_help", registry)
  → merge into host HelpTree
```

Called from `TabRegistry.install_pages` via `contribute_all_help()`:
collect contributions with `notify_all("contribute_help", registry)`, then
`install_help_contributions(registry)` so the Help plugin never imports
`tabs.*`.

---

## Plugin modules

| Module | Role |
|--------|------|
| `plugin.py` | `HelpPlugin` — `show_dialog`, language events |
| `dialog.py` | `HelpDialog` — splitter, back bar, hub / document |
| `navigator.py` | Stack + back / forward |
| `hub_page.py` | Session-picker-style topic cards |
| `back_bar.py` | Full-width breadcrumb + back |
| `tree.py` | Host load, contribution merge, body/asset resolve |
| `contribution.py` | `HelpContributionRegistry` API for tabs |
| `labels.py` | `title_key` / `description_key` via `tr()` |
| `icons.py` | App icons + contributed tab resolvers |
| `interpolate.py` | `{{tr:dotted.key}}` in markdown bodies |
| `layout_geometry.py` | Dialog size / sidebar widths |

Toolkit owns rendering only (`HelpDocumentView` / `parse_help_blocks`).

---

## Tree merge contract

Host `resources/help/tree.json` defines root hubs (`workspace`, `ui`,
`platform`) and host pages. `workspace.children` starts **empty**; tabs
append hubs under `attach_under="workspace"`.

Tab contribution (example: `tabs/image_compare/help.py`):

```python
def contribute_help(registry: HelpContributionRegistry) -> None:
    registry.contribute(
        attach_under="workspace",
        child_ids=("workspace.image_compare",),
        nodes={...},           # hub + pages (same JSON shape as tree.json nodes)
        aliases={"magnifier": "workspace.image_compare.magnifier", ...},
        body_root=Path(__file__).parent / "resources" / "help",
        resolve_icon=resolve_help_icon,  # optional
    )
```

Rules:

- Contributed `node_id`s must be unique across the merged tree.
- Alias conflicts (same slug → different targets) raise at merge.
- Page `body` paths are relative to that tab's `body_root/<lang>/`.
- Shared figures stay under host `resources/help/assets/`; tabs may pass
  `asset_root` for their own screenshots.
- Stable `help_page` slugs live as **aliases** on the contributing tab (or
  host for platform/UI), so Learn more / F1 do not break when nodes move.

---

## File layout

```text
src/plugins/help/                 # dialog + merge
src/resources/help/
  tree.json                       # host shell only
  en|ru|zh|pt_BR/ui/…  en|ru|zh|pt_BR/platform/…    # host topics
  assets/                         # optional screenshots when a page needs them
src/tabs/<tab>/
  help.py                         # contribute_help(...)
  resources/help/<lang>/*.md      # tab topic bodies
  resources/i18n/<lang>/….json    # <tab>.help.* keys
```

---

## Authoring style (reader-facing)

Help is a **secondary illustrated manual**, not a glossary dump and not a
developer design doc. Aim for the clarity of manuals like Blender’s: one
idea per section, short description under a clear heading, screenshot only
when the chrome itself is the point.

Primary discovery stays Find Action; Help teaches *shape* and *habits*.

### Page skeleton

```markdown
## Topic title

One or two sentences: what this is and when you need it. Cross-link related
topics; do not repeat their whole page.

### First concept {#stable-anchor}

What / where / how. Optional figure **immediately under** this heading if
the section is about a visible surface (panel, dialog, layout).

### Next concept {#…}
…
```

- Page title = `##`. Scenario / concept sections = `###` with stable `{#anchor}`.
- TOC is generated from anchored `###` — keep titles short and scannable.
- Ban trailing `### Related` / `### Связанное` dumps; weave `help://` links
  into the prose or end with `### Next topics` / `### Дальше по темам` when
  a short outbound list helps.

### Definition-style inventories (Blender-like, within our subset)

We do **not** have Sphinx definition lists or blue term headings yet. Approximate:

```markdown
### Object types {#types}   <!-- or a toolbar group -->

- **List manager** — in-window panel opened from the list dropdown; reorder,
  rate, and move rows here.
- **Add files** — button beside each dropdown; appends to that side only.
- **Swap** (`X`) — short click exchanges the current pair; long-press swaps
  both lists.
```

Rules:

1. **One term → one short sentence** (or two). Prefer a bullet list of
   term + em dash + prose over a single paragraph of comma-joined labels.
2. **Name the concept in the reader’s language** first. Use `{{tr:…}}` when
   the UI string is the searchable name (toolbar, menu, Find Action). Do not
   chain three long `{{tr:}}` titles in one sentence — that reads as a tag
   cloud.
3. **Bold is for the defined term** at the start of a definition bullet, not
   for every control mention. Elsewhere prefer plain `{{tr:…}}` or backticks
   for chords (`Ctrl+S`).
4. **Nesting** is limited: our parser has flat lists only (no indented
   sub-lists). For a subtype, either a second `###` or a follow-up sentence
   under the parent bullet — do not fake hierarchy with spaces.
5. **Keys** use `` `Chord` `` so they render as kbd when they look like
   shortcuts.

### Panels vs dialogs (wording)

In user-facing text say **panel** / **всплывающая панель** / **painel** /
**面板** (or **панель**), never “flyout”. Reserve “flyout” for code, themes,
and anchor ids (`#toolbar-flyouts`, `#flyouts`). Contrast: panel = in-window
chrome; dialog = separate window (export, settings, properties).

### Figures and tips

- Figure policy above still applies (budget, placement beside the `###`).
- Blender-style “tip” callouts are **not** in the v1 subset. Until
  `:::tip` exists, a short trailing sentence is enough
  (“If the list is empty, the panel does not open.”). Do not invent HTML/QSS
  tip boxes in page bodies.
- Prefer a **cropped** shot of the element being taught (open list panel,
  status of a control), not a full-window dump — when real assets replace
  placeholders.

### Language keys (`{{tr:…}}`)

See also [RESOURCES_I18N](./RESOURCES_I18N.md). In Help bodies:

- Prefer keys that match Find Action / toolbar labels.
- Missing key → fix i18n (or add a help-specific key under the owner pack);
  do not leave English tokens in RU prose.
- Host pages use host packs; tab pages may use that tab’s `resources/i18n`
  (loaded with the tab).

### What the renderer cannot do yet

Tracked as toolkit / Help follow-ups — do **not** author pages as if these
already work:

| Wanted (Blender-like) | Today |
|---|---|
| True definition-list / term heading style | `###` + `- **Term** — …` bullets |
| Nested indented terms | Flat lists only |
| Tip / note admonitions | Plain sentence (or deferred `:::tip`) |
| GFM pipe tables | Bullet chord lists |
| Figure left / center / right | `side=left\|center\|right\|block` (v1+) |
| Glossary dotted links | Normal `help://` / http(s) links |

Style reference: `ui.lists_flyouts` (definition bullets + `center` / `left`
figures).

---

## Figure policy

**Default is zero figures.** A page does not need a picture to be valid. Find
Action + `{{tr:…}}` labels + `help://` links are the primary teaching tools.
Add `:::figure` only when a screenshot answers a question that prose cannot
(layout, spatial gesture, dialog shape, mode that *looks* different).

### Budget

| Budget | When | Placement | Examples (current tree) |
|---|---|---|---|
| **0 — none** | Chord inventories, settings inventories, short orientation, anything fully named by UI strings | — | `platform.hotkeys`, `platform.settings`, `ui.buttons` |
| **1 — one** | One primary surface or spatial idea for the whole page | After the intro paragraph (or beside the one `###` that needs it); `side=right` | `getting_started` (session picker), `file_project` (paste overlay), `export` (dialog), `multi_compare.overview` (`#layouts`), `canvas_navigation` (`#zoom`) |
| **2 — several** | Page teaches **distinct visual states** that look different | One figure **next to the `###` section** it illustrates — not a stack under the title | `comparison` (`#split-line` + `#difference-modes`), `magnifier` (`#enabling` + `#combined-mode`), `video` (`#timeline` + `#export-encode`), `lists_flyouts` (`#list-manager` + `#toolbar-flyouts`) |

More than two figures on one page is uncommon; a third is allowed only for
another distinct visual state (e.g. magnifier multi-instance). A fourth usually
means split the topic into another hub child.

### Rules

1. **Need before asset.** Write the section first; add a figure only if a
   reader would still ask “what does that look like?”
2. **Screenshots.** Prefer real product shots. Temporary `placeholder.png` is
   allowed **only** in budgeted slots below, with a caption that says
   placeholder / временный скриншот. Do not sprinkle extras.
3. **Caption = UI path.** Prefer `{{tr:…}}` breadcrumbs in the caption; do not
   invent English control names.
4. **Side layout.** `:::figure{side=…}`:
   - `right` / `left` — float beside adjacent paragraphs (Blender-like wrap)
   - `center` — full-width row, image and caption centered
   - `block` — full-width row, left-aligned (default)
5. **Assets.** Host shared shots under `resources/help/assets/`; tab-owned
   shots under that tab’s `asset_root` / `resources/help/assets/`. Prefer
   theme-neutral or ship light+dark when chrome color matters.
6. **Tests do not require figures.** Scenario shape (`##` + `###`) is enough;
   see `test_help_page_bodies_are_scenario_cards`.

### Per-topic figure slots

Bodies ship in **en + ru + zh + pt_BR** (missing lang falls back to EN). Topic
depth is `adequate` across the tree; do not claim deeper coverage without
real encyclopedia-level pages.

| Topic | Budget | Figure targets (placeholders until real shots) |
|---|:-:|---|
| `ui.buttons` | 0 | — |
| `ui.lists_flyouts` | 2 | `#list-manager` (center), `#toolbar-flyouts` (left) |
| `ui.canvas_navigation` | 1 | Beside `#zoom` |
| `platform.getting_started` | 0 | — |
| `platform.workspace` | 1 | Beside `#session-picker` |
| `platform.image_properties` | 1 | Beside `#open` |
| `platform.settings` | 0 | — |
| `platform.hotkeys` | 0 | — |
| `platform.file_project` | 1 | Beside `#loading-images` (paste overlay) |
| `workspace.image_compare.comparison` | 2 | `#split-line`, `#difference-modes` |
| `workspace.image_compare.magnifier` | 2 | `#enabling`, `#combined-mode` |
| `workspace.image_compare.export` | 1 | Beside `#saving-an-image` |
| `workspace.image_compare.video` | 2 | `#timeline`, `#export-encode` |
| `workspace.multi_compare.overview` | 1 | `#layouts` (center) |

Replace placeholders in place; do not add figures outside this table. Optional
later gaps (still budget-0 unless raised): `ui.buttons` `#flyouts`,
`platform.workspace` `#tab-strip`, `comparison` `#scroll-images`, settings shell.

---

## Rendering

```text
markdown subset → parse_help_blocks() → HelpDocumentView
  ├── HelpDocumentToc (chrome, optional)
  └── HelpDocumentBodyCanvas (unified paint + selection)
```

The body is a single custom canvas (`HelpDocumentBodyCanvas` in
`sli-ui-toolkit`): one text index, one selection model, `QTextLayout` paint
path. Cross-block drag-select, Select all, and Copy as Markdown operate on the
full page (headings, list markers, paragraphs). TOC remains separate chrome
above the canvas (clickable `_LinkLabel` rows, not part of body selection).

Public document API used by the app: `set_markdown`, `plain_text`,
`selected_plain_text()`, `selected_markdown()`, `select_all_text()`,
`scroll_to_anchor`, `textContextMenuRequested(QPoint)`.

Help body right-click opens a toolkit `ContextMenu` via
`open_help_text_context_menu` → `ContextMenuManager`. That path passes
`surface="popup"` so the menu is a frameless Qt popup (not a child of
`HelpDialog`'s overlay). Button-anchored menus elsewhere stay in-window.
Dismiss and hit-testing go through the manager's `contains_global` /
outside-close paths like canvas ПКМ menus.

v1 blocks: headings (+ `{#anchor}`), paragraphs (bold/italic/code/kbd/links),
lists, optional `:::figure` / images (see [Figure policy](#figure-policy)),
optional TOC. **No GFM pipe tables** — consecutive `| … |` rows become one
paragraph; use `- \`chord\` — action` lists instead (see `platform/hotkeys.md`).

Dialog navigation:

| Zone | Behaviour |
|------|-----------|
| Content | hub cards or `HelpDocumentView` |
| Sidebar | siblings of the current level only |
| Back bar | full width; stack pop + breadcrumb |
| Links | `help://slug#anchor`, `#anchor`, http(s) |

---

## Opening Help

- Menu / hotkey → `UIManager.show_help_dialog`
- Palette Learn more / `help_page` → `show_help_dialog(page=…, anchor=…)`
- Tabs → `context.call_service("show_help_dialog")` (host `TabContext` service)
- Dialog Help menus (Export / Video Editor) → same path

`HelpDialog` is always a **parentless** top-level `Window` (not transient-for
the main shell). Parenting it to `MainWindow` made WMs raise the whole main
window group and bury independent windows like Video Editor.

No new methods on `TabContract` — only `create_service("contribute_help", …)`.

---

## Testing

- `tests/plugins/test_help_tree.py` — aliases, merge, scenario page shape
- `tests/plugins/test_help_interpolate.py` — `{{tr:}}`
- `tests/plugins/test_help_browser_navigation.py` — navigator / dialog UX
- `tests/plugins/test_help_dialog_opens.py` — plugin open path
- Toolkit: `HelpDocumentView` / block parse tests

Focused run:

```bash
env QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_help_*.py
```

---

## Follow-ups

- Real screenshots per [Figure policy](#figure-policy) (replace placeholders in budgeted slots)
- Toolkit: optional `:::tip` / richer definition-list blocks if the subset grows
- F1 → topic page without opening the palette
- Optional Help menu demotion vs Find Action
- Guides / capture / laser as separate pages (only if first-class UI grows)

