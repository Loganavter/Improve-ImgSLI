# Changelog

## [Unreleased]

### Fixed

- **Hover no longer pops the value flyout on scroll-value controls.** The
  divider / magnifier-guide width buttons (Image Compare, Multi Compare) show
  the value **inside** the button on hover; the value pill above the button is
  a keyboard/click-focus affordance only. Hovering used to raise the pill and
  suppress the in-button digit, so the same number appeared twice and hover
  looked like a separate mode.

### Fixed

- **The text context menu is a real popup, and opening it no longer wipes the
  text selection.** The help-page and image-properties text menus were opened
  through the app-wide RMB policy (`in_window`), so they were plain child
  widgets of the dialog: clipped to the dialog rect and unable to overflow it.
  Both now open as a native top-level popup, parented to the **document**
  (a content widget — a `Qt.Popup` parented to the top-level breaks that
  window's compositing on Wayland, see `inv-2026-10-06-ql-rhi-menu-first`);
  the popup transient-parents to the dialog and sits at the click point.
  `ContextMenuManager.open_entries`/`open_context_menu_entries` gained an
  optional per-call `surface=` override for this; the app-wide policy is
  unchanged (the gallery ask-ai sequence still needs `in_window`).
  A popup-surface menu is a top-level without focus, so it never sees the
  Escape key itself — the app-level Escape handler now also closes the
  manager's active menu. The selection half of the report (the right-press
  collapsing the selection, so every copy row came up disabled) was a
  toolkit bug and is fixed there: `sli-ui-toolkit` PR for
  `ui/widgets/text/engine/events.py`.

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
