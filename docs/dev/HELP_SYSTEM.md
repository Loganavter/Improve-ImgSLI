# Help plugin (hierarchical illustrated manual)

Status: **live** — host shell + tab-owned topic contributions

Product role: secondary illustrated topics (hubs → cards → pages). Primary
discovery stays **Find Action** / command palette. See [ACTIONS.md](./ACTIONS.md)
for `help_page` / `help_anchor` on actions.

Related:

- [tabs/capability-mechanisms.md](./tabs/capability-mechanisms.md) — `notify_all("contribute_help")`
- Toolkit: `sli_ui_toolkit.widgets.HelpDocumentView`

---

## Ownership split

| Owner | Owns |
|-------|------|
| Host plugin `plugins/help/` | Dialog shell, navigator, hub UI, fs scan, host topics (`about` / `platform.*` / `ui.*`) |
| Host `resources/help/` | Host page bodies + host `assets/` |
| Each plugin (`export`, `settings`, `image_properties`, `onboarding`) | `resources/help/` package (bodies, assets) + `HELP_MOUNT` line, owned i18n keys |
| Each tab | `resources/help/` package (bodies, assets), hub presentation fragment, icon resolver, help i18n keys |

Host **must not** import `tabs.*` or `plugins/<name>` for icons or hardcode
topic trees. Tab hub presentation flows through the same broadcast pattern
as settings/actions (`create_service("contribute_help")`); structure itself
is scanned from the filesystem, so there is nothing to hardcode.

```text
scan_help_tree()  # scan.py — dirs are hubs, *.md files are pages
  + TabRegistry.collect_help_contributions()  # capability_routing.py
      → each tab create_service("contribute_help") -> HelpHubContribution | None
  → install_help_contributions(fragments)  # tree.py — hub meta + resolvers overlay
  → host HelpTree
```

Called from `TabRegistry.install_pages` via `contribute_all_help()`.
`HelpHubContribution` is frozen, `owner_tab == i18n_namespace` per
`isolation.md:60`, so `tabs.*` is never imported by the Help plugin.
Single-page tabs (and all plugins) contribute nothing — page titles come
from each page's own `##` heading (see `labels.py`).

---

## Plugin modules

| Module | Role |
|--------|------|
| `plugin.py` | `HelpPlugin` — `show_dialog`, language events |
| `dialog.py` | `HelpDialog` — splitter, back bar, hub / document |
| `navigator.py` | Stack + back / forward |
| `hub_page.py` | Session-picker-style topic cards |
| `back_bar.py` | Full-width breadcrumb + back |
| `tree.py` | Scan assembly (`install_help_contributions(list[HelpHubContribution])`), `resolve_path`, body/asset resolve |
| `scan.py` | Filesystem discovery (dirs = hubs, `*.md` = pages, dotted ids) + hub-meta overlay |
| `contribution.py` | `HelpHubContribution` (frozen, `owner_tab`, `mount`, hub title/desc/icon, `resolve_icon`) |
| `meta.py` | Page frontmatter (`description`, `icon`) parse + strip |
| `labels.py` | Titles from each page's `##` heading; subtitles from page frontmatter `description`, else the first paragraph; `title_key` / `description_key` via `tr()` for hubs only |
| `icons.py` | App icons + contributed tab resolvers |
| `layout_geometry.py` | Dialog size / sidebar widths |

Toolkit owns rendering only (`HelpDocumentView` / `parse_help_blocks`).

---

## Tree scan contract (web canon)

The filesystem is the tree — no registry. `scan_help_tree()` (`scan.py`)
discovers every `<package>/resources/help/` dir (host + `tabs/*` +
`plugins/*`) and derives, from the `en/` bodies:

- a directory is a **hub**, a `*.md` file is a **page**;
- the node id is the dotted path (`ui/buttons.md` → `ui.buttons`);
- host mounts at the root; `tabs/<name>` mounts at `workspace.<name>`;
  plugins mount at the `HELP_MOUNT` dotted id declared in
  `plugins/<name>/help.py` (single line).

Layout convention per mount: exactly one `*.md` directly under `en/` (and
no subdirectories) means the mount id itself is a page (e.g.
`platform.settings` → `settings.md`); otherwise the mount is a hub of
pages.

Tab hub contribution (example: `tabs/image_compare/help.py`):

```python
def build_help_hub_contribution():
    from plugins.help.contribution import HelpHubContribution
    return HelpHubContribution(
        owner_tab="image_compare",
        mount="workspace.image_compare",
        title="Image Compare",
        description="Two-image compare, magnifier, export",
        icon="vertical_split.svg",
        title_key="image_compare.workspace.session_types.image_compare",
        description_key="image_compare.help.hub.desc",
        resolve_icon=resolve_help_icon,  # optional
    )
```

Rules:

- Page titles come from each page's own `##` heading (current language,
  fallback EN with an `[en]` badge). Card subtitles come from the page's
  leading frontmatter `description` (plain text, no markup), else its first
  paragraph. No per-page i18n keys.
- A page body may open with a minimal frontmatter block carrying the card
  `description` and `icon` (both optional; unknown keys ignored; CRLF and an
  unterminated block tolerated). The scan reads it into the node; the rendered
  body has it stripped (`plugins/help/meta.py`):

  ```markdown
  ---
  description: One short card line, no markup
  icon: settings.svg
  ---
  ## Topic title
  ```

  The `icon` name must resolve via `get_app_icon` (host pack) or the tab's
  `resolve_icon` — pinned by `tests/plugins/test_help_icons.py`.
- Tab-hub titles/descriptions/icons come from the fragment above; the four
  app-shell hubs (`root` / `workspace` / `ui` / `platform`) keep static meta
  in `scan.py`.
- Images are body-relative paths (`../../assets/ui/toolbar.jpg`) living in
  the owning package's `assets/`; they must not escape that package's
  `resources/help/` dir (pinned by `tests/plugins/test_help_bodies.py`).
  Host `resources/help/assets/` is for host shots only.
- Stable entry points (`help_page` on actions, F1, Learn more) are **dotted
  paths** (`workspace.image_compare.comparison`), not slugs. A move breaks
  inbound prose links visibly — the dialog renders a `## Missing page`
  placeholder ("ну увы") instead of failing.
- Deleting a doc = deleting its files. Inbound `help://` links need no
  same-day fix; they resolve to the placeholder until prose is cleaned.

---

## File layout

```text
src/plugins/help/                 # dialog + scan
src/plugins/<plugin>/             # export, settings, image_properties, onboarding
  help.py                         # HELP_MOUNT = "<mount>" — host reads it, never imports the plugin
  resources/help/                 # plugin package (bodies + assets)
    <lang>/*.md
    assets/…
  resources/i18n/<lang>/….json    # owner pack keys (auto-registered, see below)
src/resources/help/               # host package (host pages only)
  en|ru|zh|pt_BR/about.md, ui/…, platform/{file_project,hotkeys}.md
  assets/
    ui/…                          # host screenshots only
src/tabs/<tab>/
  help.py                         # build_help_hub_contribution(...) or nothing (single-page tabs)
  resources/help/                 # tab package (bodies + assets)
    <lang>/*.md
    assets/*.jpg
  resources/i18n/<lang>/….json    # <tab>.help.* keys
```

Two registration paths, opposite defaults: `<pkg>/resources/i18n` packs
**auto-register** on plugin/tab discovery (zero code — drop the files), so
moved `settings.*` keys needed no registration change; help packages are
**discovered** the same way — a new `resources/help/` dir under `tabs/*`
mounts at `workspace/<name>` with zero code (plugins add one `HELP_MOUNT`
line).

Bodies reference figures as body-relative paths (`../../assets/ui/x.jpg`)
inside the owning package's `assets/` — host for platform/UI, tab for
workspace topics (see [Figure paths](#figure-paths)).

---

## Authoring style (reader-facing)

Help is a **secondary illustrated manual**, not a glossary dump and not a
developer design doc. Aim for the clarity of manuals like Blender’s: one
idea per section, short description under a clear heading, screenshot only
when the chrome itself is the point.

Primary discovery stays Find Action; Help teaches *shape* and *habits*.

### Page skeleton

```markdown
---
description: One short card line, no markup
icon: settings.svg
---
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
- Frontmatter is optional but expected: the card `description` (plain text,
  no `**markup**`) and a resolvable `icon` (see
  [Tree scan contract](#tree-scan-contract-web-canon)).
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
2. **Name the concept in the reader’s language** first. Write the literal
   on-screen label in `**bold**`, exactly as the UI shows it. Do not chain
   three long labels in one sentence — that reads as a tag cloud.
3. **Bold is for a UI label or the defined term.** Wrap every control, menu
   item, session type, and dialog name in `**bold**` and never use it as a
   bare grammatical subject; elsewhere backticks for chords (`Ctrl+S`).
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

### Tables

GFM-style pipe tables render as bordered grids (the same `TableBlock`
surface the Image Properties dialog uses — label/value columns with real
divider lines). The first row becomes the **bold header** when the next
line is a `---` separator:

```markdown
| Setting | Meaning |
|---|---|
| `quality` | JPEG quality, 1–100 |
| Alpha | keep the alpha channel |
```

- Header optional: without the `---` separator row the first line is a
  plain body row.
- Alignment markers (`:---:` / `---:`) are accepted and ignored — all cells
  render left-aligned.
- `\|` escapes a literal pipe inside a cell; cells support the usual
  inline formatting (`` `code` ``, `**bold**`).
- Use tables for short key/value inventories (≤ 5–6 columns). Prefer
  definition bullets (above) when the left column is a term with a long
  explanation.

### Figures and tips

- Figure policy above still applies (budget, placement beside the `###`).
- Blender-style “tip” callouts are **not** in the v1 subset. Until
  `:::tip` exists, a short trailing sentence is enough
  (“If the list is empty, the panel does not open.”). Do not invent HTML/QSS
  tip boxes in page bodies.
- Prefer a **cropped** shot of the element being taught (open list panel,
  status of a control), not a full-window dump — when real assets replace
  placeholders.

### Labels (literal, per language)

See also [RESOURCES_I18N](./RESOURCES_I18N.md). Help bodies no longer resolve
`{{tr:…}}` keys at runtime — each language body carries literal, on-screen <!-- doc-truth:allow -->
labels:

- Write the label exactly as the UI shows it, in `**bold**` (toolbar, menu,
  Find Action, session type, dialog). The UI string is the searchable name.
- Do not invent near-synonyms; the label must match the screen
  ([HELP_STYLE_GUIDE.md](HELP_STYLE_GUIDE.md) §3.1, §4.5).
- Keep labels in sync per language; a label rename in the UI is a help edit in
  `en|ru|zh|pt_BR` in the same change.
- Do not leave raw tokens or English words in RU/ZH/PT prose.

### Figure paths

Bodies reference screenshots as body-relative paths into the owning
package's `assets/` — host for platform/UI, tab for workspace topics:

```markdown
:::figure{side=block height=107}
![Session Picker](../../assets/platform/session_picker.jpg)
**Session Picker**.
:::
```

- Paths are relative to the page file; they must not escape that package's
  `resources/help/` dir (pinned by `tests/plugins/test_help_bodies.py`).
- Prefer final filenames so shipping a shot means overwriting the file — no
  md / locale edits.
- Tab topics own their screenshots under `tabs/<tab>/resources/help/assets/`;
  do not put compare figures in host `resources/help/assets/`.
- Missing image → broken image, intentionally visible (same as an unknown
  path anywhere on the web).

### What the renderer cannot do yet

Tracked as toolkit / Help follow-ups — do **not** author pages as if these
already work:

| Wanted (Blender-like) | Today |
|---|---|
| True definition-list / term heading style | `###` + `- **Term** — …` bullets |
| Nested indented terms | Flat lists only |
| Tip / note admonitions | Plain sentence (or deferred `:::tip`) |
| Figure left / center / right | `side=left\|center\|right\|block` (v1+) |
| Glossary dotted links | Normal `help://` / http(s) links |

Style reference: `comparison` (definition bullets + `block`
figures).

---

## Figure policy

**Default is zero figures.** A page does not need a picture to be valid. Find
Action + literal **on-screen labels** + `help://` links are the primary
teaching tools.
Add `:::figure` only when a screenshot answers a question that prose cannot
(layout, spatial gesture, dialog shape, mode that *looks* different).

### Budget

| Budget | When | Placement | Examples (current tree) |
|---|---|---|---|
| **0 — none** | Chord inventories, short orientation, anything fully named by UI strings | — | `about`, `multi_compare.layouts`, `multi_compare.viewing` |
| **1 — one** | One primary surface or spatial idea for the whole page | After the intro paragraph (or under the one `###` that needs it); prefer `side=block` | `getting_started` (onboarding mode picker), `file_project` (paste overlay), `export` (dialog), `workspace.settings` (dialog), `multi_compare.overview` (`#layouts`) |
| **2 — several** | Page teaches **distinct visual states** that look different | One figure **next to the `###` section** it illustrates — not a stack under the title | `comparison` (`#split-line` + `#difference-modes`), `magnifier` (`#enabling` + `#combined-mode`), `video` (`#timeline` + `#export-encode`) |
| **3+ — exception** | Several modes / gestures that each *look* different and must not share one collage | One figure per mode or gesture section | `ui.buttons` (toolbar + three modes + long-press) |

More than two figures on one page is uncommon; a third is allowed only for
another distinct visual state. Going above that needs an explicit exception in
the per-topic table (do not use it to decorate every bullet).

### Rules

1. **Need before asset.** Write the section first; add a figure only if a
   reader would still ask “what does that look like?”
2. **Screenshots.** Prefer real product shots under final filenames. Do not
   sprinkle extras.
3. **Caption explains the picture.** Say what is shown and what to look at —
   not the menu path. Put the path in the body text next to the figure.
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
7. **Assets.** Reference via body-relative paths (see [Figure paths](#figure-paths)).
   Host shots under `resources/help/assets/`; tab shots under that tab’s
   `resources/help/assets/`. Prefer
   theme-neutral or ship light+dark when chrome color matters.
8. **Tests do not require figures.** Scenario shape (`##` + `###`) is enough;
   see `test_help_page_bodies_are_scenario_cards`.

### Per-topic figure budgets

Bodies ship in **en + ru + zh + pt_BR** (missing lang falls back to EN). Topic
depth is `adequate` across the tree; do not claim deeper coverage without
real encyclopedia-level pages.

| Topic | Budget |
|---|:-:|
| `about` | 0 |
| `ui.buttons` | 5 |
| `platform.getting_started` | 1 |
| `platform.image_properties` | 1 |
| `platform.settings` | 1 |
| `platform.hotkeys` | 1 |
| `platform.tabs` | 1 |
| `platform.file_project` | 1 |
| `workspace.session_picker` | 1 |
| `workspace.image_compare.comparison` | 2 |
| `workspace.image_compare.magnifier` | 2 |
| `workspace.export` | 1 |
| `workspace.image_compare.video` | 2 |
| `workspace.multi_compare.overview` | 1 |
| `workspace.multi_compare.layouts` | 0 |
| `workspace.multi_compare.viewing` | 0 |
| `workspace.multi_compare.export` | 1 |
| `workspace.image_gallery.{overview,triage,quality,ranking,ask_ai}` | 1 |

Going above the budget needs an explicit exception here (do not use figures
to decorate every bullet).

_2026-10-13: the budgets for `platform.{getting_started,settings,hotkeys,tabs}`,
`workspace.multi_compare.export`, and the four `workspace.image_gallery.*`
pages were raised to **1** so each page carries one real screenshot next to
the surface it explains (previously all were 0). `about`,
`multi_compare.layouts`, and `multi_compare.viewing` stay at 0 — no
capturable surface matches them (orientation prose; a QRhi/GL canvas that
cannot be grabbed headlessly)._ `ranking` joined the set on 2026-10-18 at
0 figures (prose only; no capturable surface).

Optional later gaps (still budget-0 unless raised):
`workspace.session_picker` `#tab-strip`, `comparison` `#scroll-images`, settings shell.

---

## Rendering

```text
markdown subset → parse_help_blocks() → HelpDocumentView
  ├── HelpDocumentToc (chrome, optional)
  └── HelpDocumentBodyCanvas (unified paint + selection)
```

The body is a single custom canvas (`HelpDocumentBodyCanvas` in
`sli-ui-toolkit`): one text index, one selection model, `QTextLayout` paint
path. Selection spans the whole page (headings, list markers, paragraphs), and
**Copy as Markdown maps the selection back to the page source** — the selected
blocks only, with their markup (the blocks parsed from the page carry that
geometry), so a two-label selection copies two lines, never the page. TOC
remains separate chrome above the canvas (clickable `_LinkLabel` rows, not part
of body selection).

Public document API used by the app: `set_markdown`, `plain_text`,
`selected_plain_text()`, `selected_markdown()`, `select_all_text()`,
`scroll_to_anchor`, `textContextMenuRequested(QPoint)`.

Help body right-click opens a toolkit `ContextMenu` via
`open_help_text_context_menu` → `ContextMenuManager`. That path passes
`surface="popup"` so the menu is a frameless Qt popup (not a child of
`HelpDialog`'s overlay). Button-anchored menus elsewhere stay in-window.
Dismiss and hit-testing go through the manager's `contains_global` /
outside-close paths like canvas ПКМ menus.

v2 blocks: headings `#` … `######` (+ `{#anchor}`), paragraphs
(bold/italic/code/kbd/links), lists, fenced `` ``` ``` `` code blocks
(monospaced), optional `:::figure` / images (see [Figure policy](#figure-policy)),
optional TOC. **No GFM pipe tables** — consecutive `| … |` rows become one
paragraph; use `- \`chord\` — action` lists instead (see `platform/hotkeys.md`).
The toolkit's own `docs/user/*.md` (shown in the inspector's Docs section)
rely on `#` headings and code fences; app help pages keep using `##`/`###`
for TOC-friendly anchors.

Dialog navigation:

| Zone | Behaviour |
|------|-----------|
| Content | hub cards or `HelpDocumentView` |
| Sidebar | siblings of the current level only |
| Back bar | full width; stack pop + breadcrumb |
| Links | `help://dotted.path#anchor`, `#anchor`, http(s) |

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

## Topic search

`HelpDialog` has a search field pinned above the topic tree (toolkit
`SidebarDialogShell(sidebar_header=…)`). It matches node **titles** and
**page body content** in the current language **and** English (Find
Action-style cross-language haystack — a query survives a language switch),
ranks with the toolkit `match_score` scorer, and shows the top ~12 results
in the sidebar list with node icons. Matching is NFKD-normalized and
**non-fuzzy** (exact / prefix / substring): body content only ranks when
the query is a real locatable substring — a fuzzy subsequence hit cannot
be found on the page, so it never appears in results. Topic **descriptions
are deliberately not indexed** — page content replaces them as the
body-text haystack. Activating a content match pushes the topic through the
existing navigator, **scrolls to the first occurrence and highlights it**
with the document's text selection (accent wash, same normalization as the
scorer); title-only matches just open the page normally. The result list
stays until Esc/clear restores the sibling tree. A live search re-runs on
`update_language`.

The sidebar column (nav list + search field) is only shown when the current
node has siblings — at the root hub the whole column collapses so the main
section owns the full width, and the search field appears once you drill
into a hub or page.

---

## Testing

- `tests/plugins/test_help_tree.py` — paths, hub fragments, scenario page shape
- `tests/plugins/test_help_meta.py` — frontmatter parse/strip (`meta.py`)
- `tests/plugins/test_help_icons.py` — every hub/page icon resolves
- `tests/plugins/test_help_labels.py` — frontmatter subtitle + markup-stripped fallback
- `tests/plugins/test_help_bodies.py` — literal labels (no `{{tr:`), body-relative images <!-- doc-truth:allow -->
- `tests/plugins/test_help_browser_navigation.py` — navigator / dialog UX (incl. Missing-page)
- `tests/plugins/test_help_dialog_opens.py` — plugin open path
- Toolkit: `HelpDocumentView` / block parse tests

Focused run:

```bash
env QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_help_*.py
```

---

## Follow-ups

- Toolkit: optional `:::tip` / richer definition-list blocks if the subset grows
- F1 → topic page without opening the palette
- Guides / capture / laser as separate pages (only if first-class UI grows)
