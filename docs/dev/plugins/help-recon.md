# Help per-owner recon (Phase R, 2026-10-12, read-only)

Pre-flight rows for every move wave of `help-per-owner-plan.md`. Commands
used: alias dump via `tree.json`, `rg "help://<slug>"`, `rg "^### .*{#"`,
`rg "{{tr:"` / `rg "{{img:"`, `rg "<node-id>" tests/`, `rg 'help_page='`.
Baseline: help focused 33 passed, `check_help_figures.py` 0 missing.

Global rules derived from recon (apply to every wave):

- **Slot ids are frozen byte-identical.** `test_help_interpolate.py:62-69`
  pins slot→path (`platform.workspace.session_picker` →
  `platform/session_picker.jpg`); `test_help_*.py:44-68` pins the full
  slot set. Only the owning `figures.json`/`asset_root` moves, never the
  slot string. Asset-relative paths stay identical, so resolution is
  unchanged.
- **Action ids and help node ids are independent namespaces.**
  `platform.settings` exists as both (action pinned in
  `test_action_registry.py:46,648`, `test_chrome_shortcut_parity.py:38`,
  `test_find_action_palette.py:148`, `test_launcher_cli.py:125`, and help
  node). Help moves never touch `*_actions.py` `action_id`s.
- **`help_page=` slugs are alias-based and stable** (`test_find_action_
  palette.py:449,478` pins `help_page="export"` → `opened == [("export",
  None)]` — alias level, survives node moves).

## Row 1 — `platform.settings` → settings plugin (Phase 3)

- Files: `src/resources/help/<en|ru|zh|pt_BR>/platform/settings.md` (1 body ×4).
- Aliases: `settings` (31 inbound `help://settings*` incl. `#general`,
  `#interface`, `#performance`).
- Anchors to preserve: `#open-settings`, `#search`, `#general`,
  `#interface`, `#performance`, `#image_compare`, `#keyboard`.
- i18n: **keys live in the HOST pack**
  (`src/resources/i18n/<lang>/settings/general.json`; no
  `src/plugins/settings/resources/i18n/` dir exists — verified
  2026-10-12: 18 `settings.*` keys, identical set ×4 langs, 0 missing).
  Bodies also use host `menu.*`/`action.*`/`label.*`/`ui.*`/`workspace.*`
  keys. Wave must move `settings.*` keys to a new plugin pack (×4 langs)
  or explicitly record host-pack refs as accepted impurity. Cross-pack keys
  (`workspace.session_types.*`, `ui.psnr/ssim`) stay — they are genuinely
  shared. Pack move needs **zero registration code**: `<pkg>/resources/i18n`
  auto-registers on plugin discovery (`core/plugin_system/registry.py:105`;
  files merge via `rglob("*.json")`) — verified 2026-10-12, just drop files.
- Figures: none (budget-0).
- Pins: node id `platform.settings` in `test_help_topic_search.py:116,127`
  (stays valid — node id unchanged, position unchanged).
- Actions: `plugins/settings/actions.py:127,178,226` (`help_page="settings"`).

## Row 2 — `platform.image_properties` → image_properties plugin (Phase 3)

- Files: `src/resources/help/<lang>/platform/image_properties.md` (×4).
- Aliases: `image_properties` (16 inbound).
- Anchors: `#open`, `#sections`, `#in-app`, `#close`.
- i18n: keys already in the plugin pack
  (`src/plugins/image_properties/resources/i18n/<lang>/
  image_properties.json` ✓ — verified 2026-10-12: 12 keys, identical set
  ×4 langs, 0 missing). Cross-pack: `workspace.session_types.*` (shared,
  stays).
- Figures: slot `platform.image_properties.open` (id frozen) + asset
  moves host `assets/` → plugin `resources/help/assets/` (same relpath).
- Pins: `tests/plugins/test_help_tree.py:35,52,62` — the ONLY test pinning
  this node id + body path. Phase 3 is the one wave allowed to edit those
  lines (new owner path).
- Actions: check `rg 'help_page="image_properties"'` at wave start.

## Row 3 — `platform.getting_started` → onboarding plugin (Phase 4)

- Files: `src/resources/help/<lang>/platform/getting_started.md` (×4).
- Aliases: `introduction` (12 inbound).
- Anchors: `#basic-workflow`, `#multi-compare`, `#discover`.
- i18n: mixed packs — `action.workspace.*`, `menu.*`,
  `workspace.session_types.*` are host/shared, but
  **`image_compare.action.save` lives ONLY in the IC tab pack**
  (`tabs/image_compare/resources/i18n/<lang>/image_compare.json:35`,
  absent from all host packs — verified 2026-10-12). Onboarding move keeps
  that ref by explicit decision (same posture as export Row 5), or the wave
  duplicates the key — decide at wave start, record it. No onboarding pack
  refs yet (pack exists with `onboarding.*` keys only).
- Pre-existing defect (out of scope, do NOT "fix" in the move commit —
  moves stay byte-identical): ru `getting_started.md:14` hardcodes
  `[Мультисравнение]` where en/zh/pt_BR use
  `{{tr:workspace.session_types.multi_compare}}`.
- Anchors identical ×4 langs (`#basic-workflow`, `#multi-compare`,
  `#discover` — verified 2026-10-12).
- Figures: none.
- Pins: `test_help_topic_search.py:113` (`platform.getting_started` —
  stays valid, node id unchanged).
- Note: onboarding plugin currently has zero help refs — hub is greenfield
  wiring around a moved body.

## Row 4 — `platform.workspace` → session_picker hub (Phase 4)

- Files: `src/resources/help/<lang>/platform/workspace.md` (×4).
- Aliases: `session_picker` (20 inbound), `workspace_tabs` — both
  preserved, retargeted to `workspace.session_picker`.
- Anchors: `#session-picker`, `#new-session-actions`, `#tab-strip`,
  `#rename`, `#next-topics`.
- i18n: `action.workspace.*`, `menu.*`, `workspace.session_types.*`
  (all host/shared packs — verified 2026-10-12: identical key set ×4
  langs, 0 missing; session_picker pack defines none of them).
  No owner-pack move needed.
- Anchors identical ×4 langs (`#session-picker`, `#new-session-actions`,
  `#tab-strip`, `#rename`, `#next-topics` — verified 2026-10-12).
- Figures: slot `platform.workspace.session_picker` (id frozen) + asset
  moves to `tabs/session_picker/resources/help/assets/` (same relpath).
- Pins: **this is the node-id rename wave.** `test_help_tree.py:36,37,51`,
  `test_help_topic_search.py:89,144,147` pin `platform.workspace` — update
  all to `workspace.session_picker` in this wave, nothing else.
- New node: `workspace.session_picker` hub under `workspace` (session_picker
  `help.py` extended; `attach_under="workspace"`, `child_ids` gains the hub).

## Row 5 — IC `export` → export plugin hub (Phase 2)

- Files: `tabs/image_compare/resources/help/<lang>/export.md` (×4) → new
  `src/plugins/export/resources/help/`.
- Aliases: `export` (12 inbound) — preserved, retargeted to
  `workspace.export`.
- Anchors: `#saving-an-image`, `#resolution-and-quality`,
  `#metadata-and-favorites`, `#quick-save`, `#video-editor` (note:
  `#video-editor` section cross-links the IC video page — keep the
  `help://video` link, do not duplicate content).
- i18n: 13 keys, identical set ×4 langs, 0 missing (verified 2026-10-12):
  4 `export.*` in the plugin pack, 5 `image_compare.action.*` in the IC tab
  pack (stay by decision — IC tab is always loaded, same posture as shared
  `menu.*`), `menu.find_action` / `label.quality` / `misc.set_as_favorite`
  host, `tooltip.use_favorite` in the export pack (duplicate also exists in
  the video_editor pack — do not dedupe in the move wave).
- Anchors identical ×4 langs (`#saving-an-image`,
  `#resolution-and-quality`, `#metadata-and-favorites`, `#quick-save`,
  `#video-editor` — verified 2026-10-12).
- Referrers beyond `plugins/export/actions.py:47` (all alias-level, none
  break): `tabs/image_compare/actions/_common.py:24` topic map +
  `_contribute.py:78`, `plugins/export/dialog.py:111`
  (`install_dialog_help_menu(page="export")`),
  `shared_toolkit/ui/decorate_dialog.py:144` (`page or "export"` default
  for ANY dialog), `help://export` in `platform/getting_started.md:18`
  and IC `video.md:3,59` (×4 langs), `test_action_registry.py:805`,
  `test_find_action_palette.py:449,478`.
- Figures: slot `workspace.image_compare.export.dialog` — **slot id frozen**
  (pinned in `test_help_interpolate.py:69` set test); owning
  `figures.json`/asset moves IC → export plugin (same relpath).
- Pins: IC hub children lose export (update IC section of `test_help_tree`
  in this wave); `test_find_action_palette.py:449,478` stays green
  unmodified (alias level).
- Actions: `plugins/export/actions.py:12,47` unchanged (slug stable).

## Row 6 — gallery hub, new content (Phase 5)

- No moves (no `tabs/image_gallery/help.py`; all gallery actions
  `help_page=None`: `actions.py:72`, `use_cases/registration.py:109,124,
  146,187`).
- New: `HelpContribution(owner_tab="image_gallery")`, hub
  `workspace.image_gallery` + pages (overview, triage/rate/review,
  quality metrics, ask-ai) per the Page authoring checklist in the plan.
- New aliases (suggest, freeze in Phase 0 extension): `image_gallery`,
  plus per-page slugs the gallery actions will use (replacing `None`).
- i18n: gallery pack exists (`tabs/image_gallery/resources/i18n/`) —
  new `image_gallery.help.*` keys there.
- Figures: new slots in gallery `figures.json` (budget ≤1/page); register
  in the HELP_SYSTEM.md per-topic table in the same wave.
