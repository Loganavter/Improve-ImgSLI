# Changelog

## [Unreleased]

### Fixed

- **"Copy as Markdown" in the help viewer copies the selected fragment, not the
  whole page.** Selecting two labels (e.g. two list items) and choosing the
  menu row put the entire page on the clipboard: the mapping was a plain-text
  substring search over the page source, and a selection spanning more than one
  block never occurs verbatim there (the text index strips `1.`/`-`/`**` and
  joins blocks with blank lines), so the "best effort" fallback returned the
  full markdown. The toolkit now carries each parsed block's source geometry
  and maps the live selection through it (selected list items / headings /
  paragraphs copy their own source lines, a whole inline span keeps its
  `**`/backticks/link target, a partial span copies plain text, table cells
  keep their ` | ` separators, and Select-all still reproduces the page).
  Toolkit `CHANGELOG.md` has the mechanism; this repo pins the user-facing case
  in `tests/plugins/test_help_text_context_menu.py`
  (`test_help_copy_markdown_copies_only_the_selected_list_items` — red before:
  the clipboard held the whole page).

- **Hover no longer pops the value flyout on scroll-value controls.** The
  divider / magnifier-guide width buttons (Image Compare, Multi Compare) show
  the value **inside** the button on hover; the value pill above the button is
  a keyboard/click-focus affordance only. Hovering used to raise the pill and
  suppress the in-button digit, so the same number appeared twice and hover
  looked like a separate mode.

- **The text context menu keeps the text selection, and stays a visible
  in-window menu.** Two reported symptoms in one menu: opening it wiped the
  text selection (so every copy row came up disabled) and the menu was not a
  "real" top-level popup. The selection half is a **toolkit** bug and is
  fixed there: the document canvas treated *every* mouse press as the start
  of a selection gesture, so the right-press that opens the menu re-anchored
  the selection to a caret; non-left buttons are now ignored (toolkit PR:
  `ui/widgets/text/engine/events.py`). The popup half was tried and
  **reverted**: on Wayland/Mutter a `Qt.Popup`-surface `ContextMenu` gets a
  `wl_surface` with **no compositor role** (neither an `xdg_popup` nor a
  subsurface), so the compositor never composites it — the menu is painted
  (its buffer reaches the server) but nothing appears, and the host window's
  drawing is disturbed. Proof: a `WAYLAND_DEBUG` trace of the live app shows
  the menu's surface created with only a viewport and never given an
  `xdg_surface`, while the dialog and the main window get theirs. Both text
  menus therefore stay on the app-wide RMB surface (`in_window`), i.e. a
  child overlay of the dialog, which is always visible. A top-level-surface
  menu has no focus, so it never sees the Escape key itself — the app-level
  Escape handler now also closes the manager's active menu.

### Changed

- **Image Gallery — ranking now states its provenance.** A series rank is
  produced by one of two backends, and the badge / stats strip say which:
  **Algorithms** (the deterministic metric-fusion floor) or **AI (Jev)** (the
  opt-in, marked, non-deterministic Jev ranking that degrades visibly to the
  Algorithms rank). A user pick reads as **Manual**. Ranked items carry
  `rank_source` (`fusion` / `jev` / `manual`) and the gallery tracks the active
  `rank_domain`; an item with no measured axis shows **no number** (never
  `#0`). New help topic **Ranking: Algorithms and AI**; i18n added for en, ru,
  zh, pt_BR. See `plan-gallery-rank-backends-2026-10-15`.
