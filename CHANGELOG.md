# Changelog

## [Unreleased]

### Fixed

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
