# Help web-canon refactor — plan

Status: **done** — branch `feat/help-webcanon`, base `main`.
P0 (deletions) + P1 (scanner) + P2 (fs source, `##` titles) + P3 (paths,
hub fragments) + P4 (inline images) + P5 (docs) landed.

## Goal

Kill `src/resources/help/tree.json` (and later the `{{img:slot}}`→`figures.json`
indirection): the filesystem is the tree, `##` headings are the titles, image
and link paths live inline in each page's own markdown. Deleting a doc =
deleting its files. Missing target = rendered `## Missing page` placeholder
("ну увы"), no link registry, no alias validation.

Non-goals: restructuring sidebar UX (hub layout stays), new help content,
translations workflow changes, `{{tr:}}` removal (content i18n stays).

## Target design

| Today | Web canon |
|---|---|
| `tree.json` nodes/children/aliases | Scan `<pkg>/resources/help/en/`: dir = hub, `*.md` = page, id = dotted path |
| Host shell (`root/workspace/ui/platform`) | Synthesized: fixed `ROOT_CHILDREN`, 4 static hub metas |
| Tab mounts (`attach_under`+`child_ids`) | Convention: `src/tabs/<name>` → `workspace.<name>` |
| Plugin mounts | One line per plugin: `HELP_MOUNT` in `plugins/<name>/help.py` |
| Single-page packages (`settings`, `export`, …) | Convention: exactly one `*.md` directly under `en/` (no subdirs) ⇒ the mount id itself is a page |
| `title_key/description_key` + 4 i18n packs | Title = `##` of current-lang body (fallback EN, then stem); card subtitle = first body paragraph |
| Tab hub titles/icons | `TabContract.localized_display_name()` / `.icon()` |
| `help_page="alias"` in actions, F1 probe | `help_page="dotted.path"`; unknown path ⇒ Missing-page placeholder (no warn-and-stay) |
| `{{img:slot}}` + 6×`figures.json` + `check_help_figures.py` | Relative asset paths inline in md; slot tooling deleted |
| `generate_llms.py` walks `tree.json` | Walks the fs scan |

## Phases (each lands green)

- **P1 — scanner + equivalence.** New `plugins/help/scan.py`: `scan_help_tree()`
  builds `HelpTree` (same runtime types) from fs; structure-only (titles
  placeholder). `HELP_MOUNT` added to 4 plugin `help.py`. New
  `tests/plugins/test_help_fsscan.py`: scanned ids/kinds/bodies/children-sets
  equal the merged registry tree. No behavior change.
- **P2 — flip the source.** `build_help_tree()` uses the scanner; titles from
  `##`, subtitles from first paragraph; `labels.py` simplified;
  `help.page.*`/`help.hub.*` keys deleted from 4 i18n packs; `tree.json`
  deleted. Tree tests rewritten to paths. Aliases still resolve (from
  contributor `_ALIASES`) so actions/F1 keep working.
- **P3 — kill aliases.** Actions `help_page` → dotted paths; `resolve_alias` →
  path resolve; `navigate_to` renders Missing-page instead of warn-and-stay;
  `_ALIASES` dicts + alias-freeze tests deleted; F1 probe checks node
  existence. Contribution type shrinks to mount info.
- **P4 — images inline.** Script converts every `{{img:slot}}` to a relative
  asset path; all 6 `figures.json` deleted; `interpolate.py` drops slot logic;
  `resolve_help_asset` resolves relative to the page's own package;
  `check_help_figures.py` + its test deleted (stub-tracking loss accepted).
- **P5 — docs + contracts.** `HELP_SYSTEM.md` (merge contract, figure policy,
  authoring, testing), `skills/help-authoring/SKILL.md`, `ACTIONS.md` alias
  note rewritten; `generate_llms.py` walks the scan; contract tests
  (`test_tabs_isolation`, `test_plugins_isolation`, `test_capability_ids`,
  `test_action_registry`) updated to the mount-only contribution shape.

## Risks / accepted losses

- Sidebar/hub-card order becomes fs-sorted (was curated); root order stays fixed.
- No retarget-on-move: moves break inbound prose links visibly (placeholder page).
- No stub-screenshot tracking after P4; no GFM-table dogma change (kept).
- `fix/help-rewrite-gal` touches the same bodies — rebase needed before merge.
- Frozen (`sys._MEIPASS`) packaging: discovery mirrors
  `check_help_figures.discover_help_packages` (same `src/`-relative globs);
  verify on a frozen build before merge.

## Verify per phase

`QT_QPA_PLATFORM=offscreen python3 -m pytest -p no:cacheprovider -q
tests/plugins/test_help_*.py tests/contracts` + `check_help_figures.py`
until P4 deletes it. Merge signal is the local run (see AGENTS.md).
