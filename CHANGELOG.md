# Changelog

## [Unreleased]

### Fixed

- **Hover no longer pops the value flyout on scroll-value controls.** The
  divider / magnifier-guide width buttons (Image Compare, Multi Compare) show
  the value **inside** the button on hover; the value pill above the button is
  a keyboard/click-focus affordance only. Hovering used to raise the pill and
  suppress the in-button digit, so the same number appeared twice and hover
  looked like a separate mode.

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
