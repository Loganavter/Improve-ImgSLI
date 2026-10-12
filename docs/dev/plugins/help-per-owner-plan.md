# Plan: help content per-owner (every plugin and tab owns its hub)

## Goal / non-goals

Goal: every plugin (`settings`, `export`, `image_properties`, `onboarding`)
and every tab (`image_compare`, `multi_compare`, `session_picker`,
`image_gallery`) owns its help hub (or page) — bodies, `figures.json`,
assets, aliases, icon resolver, i18n keys — collected through the
contribution protocol, the same way the settings dialog builds per-tab
pages (`SettingsContribution`, `plugins/settings/registry.py:95`). The host
`tree.json` keeps only the shell (root/about/workspace/ui/platform hubs)
plus genuinely host-owned pages.

Non-goals: renderer/markdown-subset changes (`:::tip` stays deferred per
`docs/dev/TODO.md:495`); new languages; splitting the video editor out of
the Image Compare hub (it is a tab-local plugin,
`tabs/image_compare/plugins/video_editor/`); toolkit docs; rewording page
bodies beyond moving them (moves are byte-identical, per language).

## Current state (audited 2026-10-12, code-first)

Mechanism exists for tabs, is missing for plugins, and content ownership
does not match either:

| Content | Lives in | Served as | Problem |
|---|---|---|---|
| `platform.settings` (+`#general/#interface/#performance` anchors) | host `src/resources/help/en\|ru\|zh\|pt_BR/platform/settings.md` | host node, alias `settings` (`tree.json:9`) | documents the **settings plugin**, owned by host |
| `platform.image_properties` | host body + host figure slot `platform.image_properties.open` | host node, alias pinned by `tests/plugins/test_help_tree.py:35,52,62` | documents the **image_properties plugin**, owned by host |
| `platform.getting_started` (alias `introduction`) | host body | host node | first-run/onboarding domain, owned by host; **onboarding plugin** has zero help refs |
| `platform.workspace` (aliases `session_picker`, `workspace_tabs`) | host body + host figure slot `platform.workspace.session_picker` | host node | documents the **session_picker tab**, owned by host |
| `workspace.image_compare.export` (alias `export`, 12× `help://export` refs) | **IC tab** hub (`tabs/image_compare/help.py:46`) | IC node | documents the **export plugin**, used by IC *and* MC (`plugins/export/actions.py:12` `_HELP = "export"`) |
| gallery (all actions `help_page=None`, `tabs/image_gallery/actions.py:72`, `use_cases/registration.py:109`) | nowhere — no `tabs/image_gallery/help.py` | — | biggest tab has no help subtree at all |
| `platform.file_project` (alias `file_management`, 16 refs), `platform.hotkeys`, `ui.*`, `about` | host | host nodes | genuinely cross-cutting/host chrome — **stays host** (explicit exception, not drift) |

Load-bearing invariant: every in-body link is alias-based (`help://export`,
`help://settings#performance`, … — 200+ refs, none hardcodes a node id
except tests). Moves are safe **iff** every current alias keeps resolving
to the moved page.

Baseline (pre-change, green): `pytest -q
tests/plugins/test_help_tree.py test_help_interpolate.py
test_help_browser_navigation.py test_help_dialog_opens.py` → 33 passed;
`python src/devtools/check_help_figures.py` → 0 missing.

## Target ownership map

| Hub / page | Owner | Attach under | Notes |
|---|---|---|---|
| `workspace.export` (hub: dialog, formats, quick-save) | export plugin (`src/plugins/export/help.py`, new) | `workspace` | node id changes IC→plugin; alias `export` preserved |
| `platform.settings` subtree (one page per section max, bodies move as-is first) | settings plugin (`src/plugins/settings/help.py`, new) | `platform` | aliases `settings` + `#general/#interface/#performance` anchors preserved (anchors are `{#…}` in bodies — moves keep them byte-identical) |
| `platform.image_properties` | image_properties plugin (`src/plugins/image_properties/help.py`, new) | `platform` | figure slot `platform.image_properties.open` + asset move to plugin package |
| `platform.getting_started` | onboarding plugin (`src/plugins/onboarding/help.py`, new) | `platform` | alias `introduction` preserved |
| `workspace.session_picker` (hub) | session_picker tab (`tabs/session_picker/help.py`, extend) | `workspace` | body moves from host `platform/workspace.md`; aliases `session_picker`, `workspace_tabs` preserved; figure slot `platform.workspace.session_picker` + asset move |
| `workspace.image_gallery` (hub, new pages: overview, triage, quality, ask-ai) | image_gallery tab (`tabs/image_gallery/help.py`, new) | `workspace` | only wave that authors new prose (×4 langs, EN first + fallback); wire `help_page` on gallery actions (replace `None`) |
| `workspace.image_compare` (minus export), `workspace.multi_compare.*`, `platform.file_project`, `platform.hotkeys`, `ui.*`, `about` | unchanged owners | — | IC hub drops the export child; nothing else moves |

## Mechanism

Mirror the settings pattern exactly (`plugins/settings/registry.py:95-104`,
`:269-294`):

1. `plugins/help/contribution.py`: add frozen `HelpPluginContribution`
   (`owner_plugin`, `attach_under`, `child_ids`, `nodes`, `aliases`,
   `body_root`, `asset_root`, `resolve_icon`) — same shape as
   `HelpContribution`, `owner_plugin` = plugin name (`export`, `settings`, …).
2. `plugins/help/tree.py`: `install_help_plugin_contributions()` — same
   immutable merge + node-id uniqueness + alias-conflict raise as
   `install_help_contributions`. Tab and plugin namespaces share one
   uniqueness scope (one merged tree).
3. Collection: plugins publish via `create_service("contribute_help")`
   like tabs (`capability_routing.collect_help_contributions`), or via a
   static registry call from `HelpPlugin.initialize` — decide in Phase 1,
   whichever keeps `plugins/help/` free of `plugins/<name>` imports
   (same rule as `tabs.*`: HELP_SYSTEM.md:24). Note the asymmetry
   (verified 2026-10-12): help `body_root`s are explicitly registered per
   contributor (`HelpContribution.body_root`, resolved in
   `tree.py:351-364`) — a new `resources/help/` dir alone changes nothing;
   i18n roots are the opposite — `<pkg>/resources/i18n` auto-registers on
   plugin/tab discovery (`core/plugin_system/registry.py:105-125`, files
   merge via `rglob("*.json")`), so new pack files need zero code changes
   and missing keys echo the key (`translations.py:59-61`).
4. Node-id policy: moved nodes take ids under the new owner
   (`workspace.export`, `workspace.session_picker`, plugin keeps
   `platform.*` ids where the hub position is unchanged). Old ids are
   **not** kept as aliases (aliases are slugs; node ids are internal) —
   except where tests pin them (see Risks).

## Area

`src/plugins/help/` (protocol+merge), `src/plugins/{export,settings,
image_properties,onboarding}/help.py` (new) + `resources/help/` packages
(new, moved bodies/figures/assets), `src/tabs/{session_picker,image_gallery}/
help.py` (+ gallery `resources/help/`), `src/resources/help/` (slim-down:
`tree.json`, host `figures.json`, deleted moved bodies), `src/plugins/export/
actions.py`, `src/plugins/settings/actions.py`, gallery actions
(`help_page=None` → real slugs), `tests/plugins/test_help_*.py`,
`docs/dev/HELP_SYSTEM.md` + `docs/dev/plugins/*.md`. Base branch: `main`.

## Ownership (waves)

Sequential waves, one agent (each wave = one reviewable unit; no shared
`relates_to`, so parallelization is optional). If parallelized later:
Wave per hub-row above, `owns_files` = that owner's package only, shared
seam = alias table in this doc (verbatim). Phase R recon may run as a
single read-only batch first (no locks needed).

## Phases

### Phase R — recon (precedes all moves, read-only)

Every move wave starts from a per-hub recon row, produced mechanically —
no hand-enumeration. For hub H (e.g. `platform.settings`, IC `export`):

1. Aliases → node: dump `resolve_alias` for every slug in the Target
   table + `rg "help://<slug>" src --count` (inbound refs, ×4 langs each).
2. Anchors: `rg "^### .*\\\{#" <hub-bodies>` — the `#section` targets
   (`help://settings#performance`) that byte-identical moves must preserve.
3. i18n: `rg "\{\{tr:" <hub-bodies>` → key list; confirm each key exists
   in the *new* owner's pack (`src/plugins/<p>/resources/i18n/` or
   `src/tabs/<tab>/resources/i18n/`), else the move carries an
   English-in-RU defect (Risk §3).
4. Figures: `rg "\{\{img:" <hub-bodies>` → slot list; confirm each slot
   in host `figures.json` (to be moved) or the owner's file; record asset
   paths to move.
5. Pins: `rg "<node-id>" tests/ docs/` — every test/doc hardcoding the
   node id (expected: only `test_help_tree.py` for image_properties).
6. Actions: `rg 'help_page="<slug>"' src` — F1/Learn-more entry points
   that must keep resolving post-move.

Output: one recon row per hub (files, aliases + inbound counts, anchors,
keys with owner-pack verdict, slots + assets, pinning tests, actions).
The row IS the wave's pre-flight checklist; a wave starts only when its
row is complete. Recon for all six hubs can run as one read-only batch
(`type: research`, exempt from queue locks).

Verify: recon rows committed in the wave PR description (or a
`docs/dev/plugins/help-recon-<hub>.md` note if non-trivial); Phase 0
slug-freeze test generated from the alias column.

### Page authoring checklist (for Phase 5 and any new prose)

Source of truth stays [HELP_SYSTEM.md](../HELP_SYSTEM.md) (§Authoring
style, §Figure policy, §Figure tokens) — this is the condensed
per-wave checklist, not a fork:

1. Skeleton: `##` title + `###` scenario sections with stable `{#anchor}`
   (TOC is generated — short scannable titles).
2. One idea per section; cross-link with `help://slug[#anchor]`, never
   repeat the target page. No trailing `### Related` dumps.
3. UI names via `{{tr:…}}` matching Find Action/toolbar labels; missing
   key → add it to the owner pack, never leave English in RU prose.
4. Definition inventories as `- **Term** — sentence` bullets (flat lists
   only); key/value tables ≤ 5–6 columns.
5. Figures: budget from the per-topic table (0 default, 1 per distinct
   visual state, 3+ needs exception); `{{img:slot}}` only, slots
   registered in the owner's `figures.json`; caption = `{{tr:…}}` UI path.
6. Languages: EN first — RU/ZH/PT-BR fall back to EN automatically, so
   ship EN and translate after; never copy EN text into other lang dirs.
7. Scenario shape must pass `test_help_page_bodies_are_scenario_cards`
   (`##` + `###`); tests do not require figures.

### Phase 0 — slug freeze (no behavior change)

Pin the alias→node contract before anything moves: extend
`tests/plugins/test_help_tree.py` with one assert per alias in the table
above (`resolve_alias` for `export`, `video`, `comparison`, `magnifier`,
`settings`, `introduction`, `file_management`, `hotkeys`,
`image_properties`, `session_picker`, `workspace_tabs`, `about`,
`view_navigation`) plus per-alias `help://` resolvability through
`read_help_page_markdown` link targets. This is the test that makes every
later move safe.

Verify: focused help tests green; `rg "help://" src --count` unchanged.

### Phase 1 — plugin contribution protocol (no content moves)

Implement Mechanism §1–3 + contract tests (mirror
`test_mc_pass_contract_shape.py` style): frozen dataclass shape,
owner_plugin validation, duplicate node-id raise, alias-conflict raise,
immutable merge (input dicts unmutated). Register zero real plugin
contributions yet (one empty-registration test).

Verify: new contract tests green; full help suite green; tree output
byte-identical (`build_help_tree` before/after diff empty).

### Phase 2 — export hub moves to the export plugin

New `src/plugins/export/help.py` + `resources/help/` (body moved
byte-identical ×4 langs from `tabs/image_compare/resources/help/<lang>/
export.md`; figure slot `workspace.image_compare.export.dialog` + asset
moves to plugin `figures.json`/`assets/`). IC `help.py` drops the export
node/alias/body; plugin contributes `workspace.export` hub under
`workspace` with alias `export`. `plugins/export/actions.py` unchanged
(slug stable).

Verify: slug-freeze tests green unmodified; `test_help_tree` IC section
updated (export child gone from IC hub, present under workspace);
`check_help_figures.py` 0 missing; F1 on an export action opens the moved
page (manual once, offscreen assert on `resolve_alias` + body read).

### Phase 3 — settings + image_properties hubs move to their plugins

Same shape as Phase 2, one plugin per commit: bodies
(`platform/settings.md`, `platform/image_properties.md` ×4 langs),
figure slot `platform.image_properties.open` + asset for the latter
(settings has budget-0, no assets). Node ids stay `platform.*`
(position unchanged); aliases unchanged.

Verify: `tests/plugins/test_help_tree.py:35,52,62` updated to the new
owner paths (the only test allowed to change its pinned ids — everything
else stays green unmodified); figures 0 missing.

### Phase 4 — onboarding hub + session_picker hub

`platform.getting_started` → `src/plugins/onboarding/help.py` (+package,
alias `introduction` kept). Host `platform/workspace.md` →
session_picker-owned `workspace.session_picker` hub (+package, aliases
`session_picker`/`workspace_tabs` kept, figure slot
`platform.workspace.session_picker` + asset moves).

Verify: slug-freeze green unmodified; figures 0 missing.

### Phase 5 — gallery hub (new content)

New `tabs/image_gallery/help.py` (`HelpContribution`,
`owner_tab="image_gallery"`, attach `workspace`) + `resources/help/`
with pages: overview, triage/rate/review, quality metrics, ask-ai.
Prose follows HELP_SYSTEM.md authoring style (scenario skeleton, figure
budget ≤1 per page, EN first — RU/ZH/PT-BR fall back to EN until
translated, which the reader supports). Wire real `help_page` slugs on
gallery actions (replace `help_page=None` in `actions.py`,
`use_cases/registration.py`).

Verify: new bodies pass `test_help_page_bodies_are_scenario_cards`;
slug-freeze extended with gallery aliases; figures 0 missing
(new slots added to the per-topic table in HELP_SYSTEM.md).

### Phase 6 — host slim-down + docs

`tree.json`: only shell + `about`, `platform.file_project`,
`platform.hotkeys`, `ui.*`. Delete moved host bodies; host `figures.json`
keeps host slots only. Update `HELP_SYSTEM.md` ownership table (§Ownership
split, §Tree merge contract, §File layout, per-topic figure table) +
`docs/dev/plugins/{help,export,settings,image_properties,onboarding}.md`
wiring sections. Run `python src/devtools/docs_link_graph.py
--write-index` (DOC_INDEX.md is generated — CI fails on stale index).

Verify: `tests/contracts` green; `check_help_figures.py` 0 missing;
`rg "platform/(settings|image_properties|getting_started|workspace)\.md"
src/resources/help` = 0; docs-link-graph test green.

## Verify (every phase)

- `QT_QPA_PLATFORM=offscreen pytest -q tests/plugins/test_help_*.py -p no:cacheprovider`
- `python src/devtools/check_help_figures.py` → 0 missing
- `tests/contracts` for cross-cutting phases (0, 1, 6); focused suites otherwise
- Falsification bar for new tests (per repo policy): each regression test
  names the pre-fix failure (alias unresolvable / figure missing / body
  not found), proven by running it against the pre-move tree.

## Risks / guards

1. **Alias stability is the load-bearing invariant.** 200+ `help://`
   refs + F1/Learn-more (`help_page` on 40+ actions) resolve through
   aliases, never node ids. Phase 0 test guards it; any phase that breaks
   a slug-freeze assert stops, no exceptions.
2. **Tests pin node ids in four files, not one.** `test_help_tree.py:35-37,
   51-52,62` (image_properties body path + workspace children),
   `test_help_topic_search.py:89,113,116,127,144,147`
   (`platform.workspace` / `getting_started` / `settings` nav data),
   `test_help_interpolate.py:62-69` (figure slot→path map + full slot
   set). Per-wave edit allowlist: Phase 2 — IC hub section of
   `test_help_tree` only; Phase 3 — image_properties lines only;
   Phase 4 — `platform.workspace` → `workspace.session_picker` in
   `test_help_tree` + `test_help_topic_search` only. Slot-id strings are
   never edited (frozen). Grep the diff per phase for any other pinned-id
   edit and reject it.
3. **i18n keys move with bodies — except `settings.*`, which live in the
   host pack.** Recon Row 1: `settings.*` keys are defined in
   `src/resources/i18n/<lang>/settings/general.json` (no
   `src/plugins/settings/resources/i18n/` dir exists), while
   `image_properties.*` and `export.*` already live in their plugin packs.
   Phase 3 must move `settings.*` keys ×4 langs to a new plugin pack;
   export bodies keep `image_compare.action.*` refs by explicit decision
   (no key fork). `title_key`/`description_key` namespaces must exist in
   the *new* owner's pack. Per-phase check: `rg "{{tr:" <moved-bodies>`
   × keys present in owner pack (recon rows list the exact sets).
4. **`platform.settings#section` anchors.** Anchors are `{#…}` headings
   inside moved bodies — byte-identical moves preserve them. Forbid
   rewording headings in move commits (separate content commits later).
5. **No `stash pop` recovery, no work on `main`.** One branch per wave
   (`docs/help-owner-<hub>`), PR per wave (CI is quota-blocked as of
   2026-10-12 — local-green is the merge signal per repo practice).

## Close-out verification

- Verified-scope: per-phase narrow (table above states why: alias +
   figure + focused-suite checks compose to full coverage; Phase 6 runs
   app-wide contracts).
- Suites run: recorded per phase in the Progress log below (commands +
   counts, full form).
- `file_meta --write-registry` after any line-count change (registry is
   CI-gated); `close_out_check.sh` equivalent done manually (no merges
   open, no `auto:` commits, branch deleted same turn) — script lives in
   `~/.local/bin`, absent on this machine.

## Progress log

- 2026-10-12: plan written. Baseline green: help focused 33 passed,
  `check_help_figures.py` 0 missing. Awaiting execution (register in
  `docs/backlog/queue.yaml` when a wave starts).
- 2026-10-12: Phase R done (`e2ff2b51`): recon rows for all six hubs in
  `docs/dev/plugins/help-recon.md`, verified by 4 parallel research
  workers, load-bearing claims spot-checked in code.
- 2026-10-12: Phase 0 done (`1d3bafdd`): slug-freeze pins (host 9 +
  tab 9 aliases + unknown-slug control), focused help set 36 passed.
- 2026-10-12: Phase 1 done (`d8b2700d`): `HelpPluginContribution` +
  immutable merge (shared scope) + duck-typed collection from
  `HelpPlugin.initialize` (Plugin base has no `create_service`);
  47 passed, tree output identical with zero contributions.
- 2026-10-12: Phase 2 done (this wave): export hub IC tab → export
  plugin (`workspace.export`, alias `export` preserved). Bodies ×4 +
  asset byte-identical (diff empty). 88 passed
  (plugin_contrib + tree + interpolate + browser + dialog_opens +
  topic_search + find_action_palette), figures 0 missing. Accepted
  deviations: `interpolate.discover_help_figure_map_paths` plugin glob +
  `tree._plugin_help_asset_roots` fallback (filesystem-based, tree roots
  win); slot ids frozen.
- 2026-10-12: Phase 3 done (settings + image_properties → plugin owners,
  one commit per plugin): bodies ×4 + asset byte-identical; `settings.*`
  keys moved host pack → new plugin pack (18 keys ×4, 0 missing, zero
  registration code — auto-discovery); slot ids frozen, asset relpaths
  identical. Accepted deviations: host `tree.json` aliases move WITH nodes
  (alias-without-node raises at `tree.py:450` — keeping them was
  impossible); `check_help_figures.py` learns plugin packages (gap flagged
  in Phase 2). Blocker resolved by supervisor: 3 order-dependent failures
  (pytest-randomly) fixed with fixture-level owner-pack registration
  (`test_help_topic_search` dialog/dialog_ru, `test_settings_dialog_
  geometry`); `test_settings_gallery_ai_page_is_body` proven pre-existing
  on clean base `550a05c4`, left untouched.
- 2026-10-12: Phase 4 done (onboarding + session_picker): getting_started
  → onboarding plugin (id stays `platform.getting_started`, IC-pack key
  ref kept by decision, ru quirk preserved); host workspace.md → session_picker
  as `workspace.session_picker` PAGE (accepted deviation: pre-existing hub
  of the same id flattened — hub+page cannot share the id, freeze asserts
  pin page kind; overview reparented under workspace unchanged). Bodies ×8
  + asset byte-identical, 91 passed, figures 0 missing.
