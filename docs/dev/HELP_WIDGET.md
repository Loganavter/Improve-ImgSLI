# Help Widget

## Purpose

The help widget is a markdown-driven documentation dialog used by the `help` plugin. It provides:

- sidebar navigation between help pages;
- localized page discovery from `src/resources/help/<lang>/`;
- markdown-to-HTML rendering;
- automatic heading anchors;
- per-page table of contents;
- in-page and cross-page anchor navigation.

The generic implementation lives in the external `sli-ui-toolkit` package as `sli_ui_toolkit.ui.widgets.composite.markdown_help_dialog`. The app keeps a thin adapter in [src/plugins/help/dialog.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/help/dialog.py), and the dialog is instantiated by [src/plugins/help/plugin.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/help/plugin.py).

## Structure

### Main classes

| Type | Role |
|---|---|
| `MarkdownHelpSection` | Immutable page descriptor: order, slug, title, markdown body |
| `MarkdownHelpPageBrowser` | `QTextBrowser` subclass used to render one help page |
| `MarkdownHelpDialog` | Generic toolkit dialog: sidebar, rendering, TOC, anchor navigation |
| `HelpDialog` | App adapter: loads localized markdown sections and configures title/icon |

### Reused toolkit pieces

| Widget | Source | Purpose |
|---|---|---|
| `SidebarDialogShell` | `sli_ui_toolkit` | two-column dialog shell |
| `IconListWidget` | `sli_ui_toolkit` | page navigation sidebar |
| `MinimalistScrollBar` | `sli_ui_toolkit` | custom scrollbars |

## Data Source

Help content is loaded from language-specific markdown folders:

- `src/resources/help/en/`
- `src/resources/help/ru/`
- `src/resources/help/pt_BR/`
- `src/resources/help/zh/`

Files follow this naming contract:

```text
NNN_slug.md
```

Examples:

- `001_introduction.md`
- `003_view_navigation.md`
- `007_settings.md`

`NNN` defines ordering. `slug` is used for cross-page help links like `help://settings#preview-and-quality`.

## Rendering Pipeline

The widget is intentionally data-driven.

1. `HelpDialog._discover_sections()` resolves the active language directory.
2. `HelpDialog._read_sections_from_dir()` loads and sorts markdown files.
3. `HelpDialog._extract_title_and_body()` takes the first markdown heading as page title.
4. `MarkdownHelpDialog.set_sections()` receives normalized section descriptors.
5. `MarkdownHelpDialog._render_section_html()` converts markdown to HTML.
6. `ensure_heading_ids()` injects stable `id` attributes into headings when needed.
7. `build_page_toc()` creates an in-page table of contents from `h3` headings.
8. `MarkdownHelpDialog._apply_styles()` injects themed CSS and assigns final HTML to each page.

## Anchor Model

### Supported link types

| Link type | Meaning |
|---|---|
| `#anchor-id` | jump inside the current page |
| `help://slug` | open another help page |
| `help://slug#anchor-id` | open another page and jump to a section |
| `https://...` | open external link in desktop browser |

### Heading ids

Authors can define explicit anchor ids directly in markdown headings:

```md
### Preview And Quality {#preview-and-quality}
```

If no id is provided, the dialog generates one automatically from heading text.

### Why anchor scrolling is custom

The visible scroll owner is the outer `QScrollArea`, not the inner `QTextBrowser`. Because of that:

- `MarkdownHelpPageBrowser` computes anchor Y positions from the document layout;
- `MarkdownHelpDialog` moves the outer vertical scrollbar to the computed offset.

This is the reason anchor navigation is implemented in dialog code instead of relying only on `QTextBrowser.scrollToAnchor()`.

## Layout Model

The dialog uses this composition:

```text
SidebarDialogShell
├── sidebar: IconListWidget
└── content_area
    └── QScrollArea
        └── MarkdownHelpPageBrowser
```

Important constraint:

- page width is forced to the current `QScrollArea` viewport width;
- content should grow vertically, not horizontally;
- all wrapping behavior is controlled from the browser/document side.

## Theming

Theme colors come from `ThemeManager`. The dialog generates CSS dynamically in `_apply_styles()` for:

- body text;
- headings;
- lists;
- code blocks / inline code;
- links;
- generated TOC block.

The outer dialog shell also receives app QSS from the help plugin:

- `src/plugins/help/resources/help.qss`

## Authoring Rules For Help Pages

To keep the widget reliable:

- use one `##` page title per file;
- use `###` for section anchors and TOC generation;
- prefer stable ids in `{#anchor}` form for sections that may be linked from other pages;
- keep one topic per section;
- prefer cross-page references with `help://slug#anchor` when content would otherwise be duplicated.

## App-Specific vs Reusable Parts

### Good candidates for `sli-ui-toolkit`

These parts are now extracted into `sli-ui-toolkit`:

- `MarkdownHelpPageBrowser`
- heading-id normalization helpers
- markdown help page rendering
- generated in-page TOC
- `help://slug#anchor` style internal documentation navigation
- generic sidebar markdown help dialog shell

### Still app-specific today

These parts stay in the app:

- `resource_path("resources/help/...")` directory convention
- plugin lifecycle integration in `HelpPlugin`
- current language fallback policy tied to app resource layout
- app icon selection through `AppIcon.HELP`
- app-specific theme token expectations (`help.separator`, `dialog.text`, etc.)

## Resulting Split

After extraction the split is:

1. `MarkdownHelpDialog` in `sli-ui-toolkit` owns rendering, TOC generation, anchor handling, layout, and theme-driven HTML styling.
2. `HelpDialog` in Improve-ImgSLI owns localized resource discovery, language fallback, page-title extraction, localized TOC title, and app icon selection.

The app integration layer is now intentionally small:

- collect localized markdown files;
- convert them into section descriptors;
- open toolkit dialog with app-specific title/icon choices.

## Current Risks / Limitations

- The dialog depends on markdown heading discipline; bad headings reduce TOC and anchor quality.
- Anchor ids must stay stable once cross-page links start depending on them.
- Generated ids for non-Latin headings may be less useful than explicit `{#...}` ids, so authored anchors are preferred.
- The toolkit widget expects theme keys like `dialog.text`, `dialog.background`, `help.separator`, and `accent`.
- The app adapter still uses the project-specific `src/resources/help/<lang>/` convention.

## Related Files

- [src/plugins/help/dialog.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/help/dialog.py)
- [src/plugins/help/plugin.py](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/help/plugin.py)
- [src/plugins/help/resources/help.qss](/home/jorj/Загрузки/Improve-ImgSLI/src/plugins/help/resources/help.qss)
- [src/resources/help/en](/home/jorj/Загрузки/Improve-ImgSLI/src/resources/help/en)
- `sli_ui_toolkit.ui.widgets.composite.markdown_help_dialog`
- `sli_ui_toolkit.ui.widgets.composite.dialog_shell`
