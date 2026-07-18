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
| `interpolate.py` | `{{tr:dotted.key}}` / `{{img:figure.slot}}` in markdown bodies |
| `layout_geometry.py` | Dialog size / sidebar widths |

Toolkit owns rendering only (`HelpDocumentView` / `parse_help_blocks`).

---

## Tree merge contract

Host `resources/help/tree.json` defines the root hub (About page +
`workspace` / `ui` / `platform` children) and host pages.
`workspace.children` starts **empty**; tabs append hubs under
`attach_under="workspace"`.

Tab contribution (example: `tabs/image_compare/help.py`):

```python
def contribute_help(registry: HelpContributionRegistry) -> None:
    registry.contribute(
        attach_under="workspace",
        child_ids=("workspace.image_compare",),
        nodes={...},           # hub + pages (same JSON shape as tree.json nodes)
        aliases={"magnifier": "workspace.image_compare.magnifier", ...},
        body_root=Path(__file__).parent / "resources" / "help",
        asset_root=Path(__file__).parent / "resources" / "help",
        resolve_icon=resolve_help_icon,  # optional
    )
```

Rules:

- Contributed `node_id`s must be unique across the merged tree.
- Alias conflicts (same slug → different targets) raise at merge.
- Page `body` paths are relative to that tab's `body_root/<lang>/`.
- Tab figures live under that tab’s `figures.json` + `assets/`; pass
  `asset_root` (usually the same as `body_root`) so screenshots resolve.
  Host `resources/help/assets/` is for platform/UI shots only.
- Stable `help_page` slugs live as **aliases** on the contributing tab (or
  host for platform/UI), so Learn more / F1 do not break when nodes move.

---

## File layout

```text
src/plugins/help/                 # dialog + merge
src/resources/help/               # host package
  tree.json
  figures.json                    # host {{img:slot}} → assets/ path
  en|ru|zh|pt_BR/ui|platform/…    # host topic bodies
  assets/
    _stub.jpg                     # canonical stub (byte-match = still todo)
    ui/… platform/…               # host screenshots only
src/tabs/<tab>/
  help.py                         # contribute_help(..., asset_root=…)
  resources/help/                 # tab package (bodies + figures + assets)
    figures.json
    <lang>/*.md
    assets/*.jpg
  resources/i18n/<lang>/….json    # <tab>.help.* keys
```

Bodies reference figures as `{{img:slot.id}}`. Paths live in the owning
package’s `figures.json` — host for platform/UI, tab for workspace topics
(see [Figure tokens](#figure-tokens-img)).

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
and anchor ids (`#toolbar-flyouts`). Contrast: panel = in-window
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

### Figure tokens (`{{img:…}}`)

Bodies never hardcode screenshot paths. Use a slot id that resolves through
merged package `figures.json` maps at read time (host + each
`tabs/<tab>/resources/help/figures.json`):

```markdown
:::figure{side=block height=107}
![Session Picker]({{img:platform.workspace.session_picker}})
{{tr:action.workspace.open_session_picker}}.
:::
```

- Slot ids are stable (match the [per-topic figure slots](#per-topic-figure-slots)
  table: `topic.section`).
- Values are asset-relative paths under **that package’s** `assets/` (resolved
  via host + contributed `asset_root`s in `resolve_help_asset`). Prefer final
  filenames so shipping a shot means overwriting the file — no md / locale edits.
- Tab topics own their screenshots under `tabs/<tab>/resources/help/assets/`;
  do not put compare figures in host `resources/help/assets/`.
- Canonical stub bytes live at host `assets/_stub.jpg`. Any figure file that
  still matches those bytes is reported as **needs screenshot** by
  `python src/devtools/check_help_figures.py`.
- Unknown slot → token left unchanged (broken image is intentional / visible).

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

Style reference: `ui.lists_flyouts` (definition bullets + `center` / `block`
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
| **0 — none** | Chord inventories, settings inventories, short orientation, anything fully named by UI strings | — | `platform.hotkeys`, `platform.settings` |
| **1 — one** | One primary surface or spatial idea for the whole page | After the intro paragraph (or under the one `###` that needs it); prefer `side=block` | `getting_started` (session picker), `file_project` (paste overlay), `export` (dialog), `multi_compare.overview` (`#layouts`), `canvas_navigation` (`#zoom`) |
| **2 — several** | Page teaches **distinct visual states** that look different | One figure **next to the `###` section** it illustrates — not a stack under the title | `comparison` (`#split-line` + `#difference-modes`), `magnifier` (`#enabling` + `#combined-mode`), `video` (`#timeline` + `#export-encode`), `lists_flyouts` (`#list-manager` + `#toolbar-flyouts`) |
| **3+ — exception** | Several modes / gestures that each *look* different and must not share one collage | One figure per mode or gesture section | `ui.buttons` (toolbar + three modes + long-press) |

More than two figures on one page is uncommon; a third is allowed only for
another distinct visual state. Going above that needs an explicit exception in
the per-topic table (do not use it to decorate every bullet).

### Rules

1. **Need before asset.** Write the section first; add a figure only if a
   reader would still ask “what does that look like?”
2. **Screenshots.** Prefer real product shots under the final paths already
   listed in `figures.json`. Until then, those files may still be stub images
   (detected by `check_help_figures.py`). Do not sprinkle extras.
3. **Caption = UI path.** Prefer `{{tr:…}}` breadcrumbs in the caption; do not
   invent English control names.
4. **Side layout.** `:::figure{side=…}`:
   - `block` — full-width row, left-aligned (**default preference** for Help pages)
   - `center` — full-width row, image and caption centered
   - `right` / `left` — float beside adjacent paragraphs (Blender-like wrap; use sparingly)
5. **Size.** `width=` (px or `%` of the help column) and/or `height=` (px).
   The renderer fits the asset into that box with aspect ratio preserved
   (and never wider than the column). Prefer `height=` for toolbar strips so
   screenshots share a consistent vertical size.
6. **Lightbox.** Click a figure to open a dimmed in-window viewer over the Help
   content (below the CSD title bar; full-resolution asset, wheel zoom,
   middle-mouse pan, click or Esc to close).
7. **Assets.** Reference via `{{img:slot}}` (see [Figure tokens](#figure-tokens-img)).
   Host shots under `resources/help/assets/`; tab shots under that tab’s
   `resources/help/assets/` with `asset_root` on `contribute_help`. Prefer
   theme-neutral or ship light+dark when chrome color matters.
8. **Tests do not require figures.** Scenario shape (`##` + `###`) is enough;
   see `test_help_page_bodies_are_scenario_cards`.

### Per-topic figure slots

Bodies ship in **en + ru + zh + pt_BR** (missing lang falls back to EN). Topic
depth is `adequate` across the tree; do not claim deeper coverage without
real encyclopedia-level pages.

| Topic | Budget | `{{img:…}}` slots (paths in `figures.json`) |
|---|:-:|---|
| `about` | 0 | — |
| `ui.buttons` | 5 | `ui.buttons.toolbar`, `…mode_beginner`, `…mode_advanced`, `…mode_expert`, `…long_press` |
| `ui.lists_flyouts` | 2 | `ui.lists_flyouts.list_manager`, `ui.lists_flyouts.toolbar_flyouts` |
| `ui.canvas_navigation` | 1 | `ui.canvas_navigation.zoom` |
| `platform.getting_started` | 0 | — |
| `platform.workspace` | 1 | `platform.workspace.session_picker` |
| `platform.image_properties` | 1 | `platform.image_properties.open` |
| `platform.settings` | 0 | — |
| `platform.hotkeys` | 0 | — |
| `platform.file_project` | 1 | `platform.file_project.paste_overlay` |
| `workspace.image_compare.comparison` | 2 | `…comparison.split_line`, `…comparison.difference_modes` |
| `workspace.image_compare.magnifier` | 2 | `…magnifier.enabling`, `…magnifier.combined_mode` |
| `workspace.image_compare.export` | 1 | `workspace.image_compare.export.dialog` |
| `workspace.image_compare.video` | 2 | `…video.timeline`, `…video.export_encode` |
| `workspace.multi_compare.overview` | 1 | `workspace.multi_compare.overview.layouts` |

Update asset paths in `figures.json` only; do not add figures outside this
table. Optional later gaps (still budget-0 unless raised):
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
- `tests/plugins/test_help_interpolate.py` — `{{tr:}}` / `{{img:}}`
- `tests/devtools/test_check_help_figures.py` — figure coverage report
- `python src/devtools/check_help_figures.py` — ready / stub / missing inventory
  (`--json`, `--strict`)
- `tests/plugins/test_help_browser_navigation.py` — navigator / dialog UX
- `tests/plugins/test_help_dialog_opens.py` — plugin open path
- Toolkit: `HelpDocumentView` / block parse tests

Focused run:

```bash
env QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_help_*.py
python src/devtools/check_help_figures.py
```

---

## Follow-ups

- Real screenshots per [Figure policy](#figure-policy): overwrite files under
  the owning package’s `assets/` (host or `tabs/<tab>/resources/help/assets/`);
  re-run `check_help_figures.py` until stubs = 0
- Toolkit: optional `:::tip` / richer definition-list blocks if the subset grows
- F1 → topic page without opening the palette
- Optional Help menu demotion vs Find Action
- Guides / capture / laser as separate pages (only if first-class UI grows)

