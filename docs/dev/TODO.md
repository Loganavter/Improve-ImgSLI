# Development TODO

Shared engineering backlog for work that is too large for incidental bug-fix
patches.

Priority markers:

- `P0` - blocks a critical workflow or causes data loss/crashes.
- `P1` - important product limitation or visible correctness issue.
- `P2` - infrastructure debt that should be planned, but is not urgent.
- `P3` - cleanup, documentation, or quality-of-life work.

Status markers:

- `Open` - not started.
- `Design needed` - needs an architecture pass before implementation.
- `Blocked` - waiting on another task or external constraint.
- `In progress` - actively being worked on.

## P2 - Unify theme-repaint mechanism

Status: `In progress` (design landed 2026-07-13; Phases 0-2 of the migration
plan implemented 2026-07-13 — `ThemedWidget` mixin + `multi_compare`
toolbar/footer migrated, `image_compare` chrome widgets migrated onto
`ThemedBackgroundContainer`, `ImageCompareWidget`/`SessionPickerWidget` page
backgrounds self-paint and `MainWindowAppearance.update_chrome_background`
is deleted; Phases 3-4 still open, opportunistic. The separate
multi_compare backdrop-staleness symptom that motivated this work is
root-caused and fixed — see [KNOWN_BUGS.md](KNOWN_BUGS.md) — turned out to
be the `setPalette()`/`setAutoFillBackground` Qt quirk, not a
compositing/Wayland issue.)

Area: theming, `ui/main_window/appearance.py`, `TabContract.apply_appearance`,
toolkit widget base classes

Related local docs:

- [THEMING.md](./THEMING.md#repaint-on-theme-change-the-themedwidget-mixin) —
  `ThemedWidget` mixin, migration status, what it intentionally does not
  solve.
- [KNOWN_BUGS.md](./KNOWN_BUGS.md) — the `setPalette()`/`autoFillBackground`
  root cause and fix for the backdrop-staleness symptom that originally
  motivated this unification.

Found while debugging multi_compare's toolbar/footer staying on the old
theme color after a theme switch. Four independent, mutually-unaware
mechanisms currently repaint widgets on `theme_changed` — toolkit widgets
self-subscribing (~20+ files, opt-in per widget), app dialogs
self-subscribing separately (settings/image_properties/export/video_editor,
copy-pasted per file), the `TabContract.apply_appearance` per-tab hook
(tabs must remember to repaint every owned widget by hand — multi_compare
forgot toolbar/footer), and `MainWindowAppearance.update_chrome_background`
(window-level, one-layout-level-deep tree-walk, duplicates responsibility
`apply_appearance` already owns). None of these fail loudly when a widget
isn't covered by any of them — full inventory and the `ThemedWidget` mixin
are in THEMING.md. Do not do a big-bang migration of the ~20 already-working
toolkit widgets — only fold widgets in as they're touched.

## P2 - Session-state infrastructure

Status: `Open`

Area: workspace sessions, tab lifecycle, Redux/store ownership

Related local docs:

- [Multi Compare TODO](../../src/tabs/multi_compare/docs/TODO.md)

Backlog of improvements to the workspace-session machinery
(`core/store_workspace.py`, `domain/workspace.py`, `tabs/contract.py`,
`core/state_management/dispatcher.py`). Not urgent, but captured so the context
is not lost.

Current state as of 2026-06-25:

- `WorkspaceSession` owns `document`, `viewport`, plus generic `state_slots`,
  `resources`, `metadata` dicts.
- `_activate_workspace_session` swaps `store.document` / `store.viewport` to
  point at the active session. Everything that reads via `store.document.*`
  follows the active session transparently.
- Dispatcher (`state_management/dispatcher.py`) re-points the active session's
  `document`/`viewport` after every reducer pass so the session does not keep a
  stale ref. Without this, switching back to an older session restored the
  pre-action state.
- `TabRegistry.activate(session_type)` fires `TabContract.on_activated` on each
  `sync_session_mode`.
- `TabRegistry.deactivate(session_type)` exists, but the main window does not
  call it when switching away.
- `on_session_created` and `on_session_closed` are wired as of 2026-07-09 (see
  below) — `WorkspaceSessionActions.create_workspace_session`/
  `close_workspace_session` emit `WorkspaceSessionCreatedEvent`/
  `WorkspaceSessionClosedEvent` on the `EventBus`, and `ui/main_window/
  layouts.py` routes them to `TabRegistry.notify_session_created`/
  `notify_session_closed`.
- Multi Compare's per-session snapshot lives on `state_slots["multi_compare.
  state"]` as of 2026-07-09 (see below) — no more tab-instance-local dict.

### Wire `on_session_created` / `on_session_closed` — Done (2026-07-09)

Wired via `EventBus` (`core/events.py`'s `WorkspaceSessionCreatedEvent`/
`WorkspaceSessionClosedEvent`), emitted from `WorkspaceSessionActions`
(`core/main_controller_parts/sessions.py` — the single real funnel for
session create/close) and routed to `TabRegistry.notify_session_created`/
`notify_session_closed` from `ui/main_window/layouts.py`'s
`_install_tab_registry`. Not wired for the bootstrap `session_picker`
session created inside `Store.__init__` — harmless, `SessionPickerTab`
doesn't override either hook.

### Move multi-compare snapshot onto `state_slots` — Done (2026-07-09)

`MultiCompareTab` no longer keeps `dict[session_id -> MultiCompareState]` on
`self` — state now lives on `state_slots["multi_compare.state"]`
(`store.set_session_state_slot`/`ensure_session_state_slot`), dropped
automatically on session close now that `on_session_created`/
`on_session_closed` are wired (see above).

**Known open bug, pre-existing, unrelated to the move above** (confirmed by
diffing against pre-move file versions and re-running in isolation):
`_default_state()`'s
`_last_session_settings` module-level global gets mutated by ANY
multi-compare widget's divider/label change, so a brand-new session created
right after an existing session's divider color changes inherits that color
instead of the true default. This makes
`test_multi_compare_state_is_saved_per_workspace_session` and
`test_multi_compare_mode_apply_resyncs_divider_underlines` fail already on
`HEAD`, before this pass touched anything — needs a separate fix (likely:
the "restore last used settings" behavior in `_default_state` should not
apply to a session created while another session already has unsaved
in-memory changes, or it needs its own explicit opt-in rather than being
baked into the state-slot factory).

### Persistence / project files

Status: `In progress` — infrastructure landed 2026-07-09, no UI yet.

`state_slots` and `resources` hold runtime objects such as numpy arrays and QRhi
texture handles. No JSON/pickle layer existed. For "open project" or "recent session" the
two options considered were per-tab serializers registered on `TabContract`, or
a `SessionBlueprint.snapshot/restore` pair invoked by a project I/O service.
Went with the former: `SessionBlueprint` (`core/session_blueprints.py`) is a
frozen, declarative *creation-time defaults* blueprint (slot factories,
resource-namespace defaults) with no per-instance state to snapshot from;
each tab already owns the split between persistable identity (paths, indices,
settings) and runtime-only state (decoded pixels, GPU handles, caches) for its
own `state_slots` entries, so the tab is the natural owner of "what subset of
my state is a snapshot."

**Landed (infrastructure only, no menu/dialog wiring):**

- `TabContract` (`tabs/contract.py`) gained two hooks, both with safe no-op
  defaults (`None` / do-nothing) so tabs that don't implement them are simply
  skipped by project save/load, not broken by it:
  - `serialize_session(session_id, context) -> dict | None` — return a
    JSON-serializable snapshot, or `None` if unsupported.
  - `deserialize_session(session_id, data, context) -> None` — restore from a
    snapshot into an already-created session (blueprint defaults are already
    in `state_slots`; the hook overwrites them).
- `TabRegistry` (`tabs/registry.py`) gained matching passthrough methods
  (`serialize_session`/`deserialize_session`) that look up the tab by
  `session_type` and log-and-swallow exceptions, mirroring the existing
  `contribute_all_settings`/`apply_appearance` iteration pattern.
- `services/io/project_io.py` (new): `build_project_data`/`load_project_data`
  (pure, take `store`/`tab_registry`/`workspace_actions` as args, no file I/O)
  plus `save_project_file`/`load_project_file` thin JSON-file wrappers.
  `load_project_data` creates each session through `workspace_actions`
  (`WorkspaceSessionActions`, the same funnel documented in "Wire
  `on_session_created`/`on_session_closed`" above) rather than calling
  `store.create_workspace_session` directly, so blueprint defaults and
  session-lifecycle events still fire before `deserialize_session` overwrites
  the defaults. Sessions whose tab returns `None` from `serialize_session` are
  silently omitted from the save.
- Implemented for both tabs that currently have a `state_slots` entry:
  - `image_compare` (`tabs/image_compare/tab.py`): serializes `DocumentModel`
    (`image_list1/2` as `path`/`display_name`/`rating` triples,
    `current_index1/2`, `image1_path`/`image2_path`) plus the small
    `image_compare.state` slot (`show_file_names`, `edit_name_1/2`). Decoded
    `ImageItem.image` pixels are never persisted — `path` is already the
    reload source of truth (see the "Actioned" `ImageSessionState`/
    `loaded_image*_paths` note above, same rationale).
  - `multi_compare` (`tabs/multi_compare/tab.py`): serializes `slots` (id,
    `path`, `label` — `image: np.ndarray` omitted, same path-is-truth
    rationale), the layout tree (`LeafNode`/`SplitNode`, new
    `_serialize_layout_node`/`_deserialize_layout_node` helpers), `zoom`/
    `pan_x`/`pan_y`/`focused_slot_id`/`max_slots`, and `label_settings`/
    `divider_settings`. The existing `_save_last_settings`/`_load_last_settings`
    QSettings code (dict shape for divider/label) was refactored into shared
    `_divider_to_dict`/`_divider_from_dict`/`_label_to_dict`/`_label_from_dict`
    helpers so the QSettings "last used settings" path and the new project
    hooks build the same dict shape instead of duplicating it.
- Verified with a manual round-trip script (serialize → deserialize against
  fake stores, plus a real `save_project_file`/`load_project_file` through a
  temp file) — not added as a `tests/` file in this pass since it needs the
  same fake-store scaffolding `tests/runtime/test_multi_compare_label_settings.py`
  already has; a real test file is a reasonable immediate follow-up before
  wiring UI on top of this.

**Not done / explicitly deferred:**

- No "Save Project" / "Open Project" menu items, `QFileDialog`, or
  `.imgsli-project` file-association wiring — this pass is infrastructure
  only, by explicit scope decision (see conversation this landed in).
- Pixel/array reload-on-open (turning a restored `path` back into decoded
  image data) is NOT triggered by `deserialize_session` — it only restores
  the path/state metadata. Actually redecoding from disk needs the tab's
  normal image-loading pipeline (`tabs/image_compare/use_cases/loading.py`'s
  `load_images_from_paths`, which needs a `controller`), which is UI-layer
  wiring, not infra. Whatever builds the "Open Project" UI action needs to
  also trigger each restored session's normal load-from-path flow after
  `deserialize_session` returns.
- `session_picker` and other tabs without a `state_slots` entry don't
  implement the hooks yet (inherit the `None`/no-op default) — nothing to
  serialize for them today.

### Per-session undo/redo

`Dispatcher._action_history` is global. To support "undo within tab", the
history would need to be sharded per active session and stored on the session
itself, likely as a new `state_slots["action_history"]` or a dedicated
`WorkspaceSession.history` field. Switching tabs would swap which history is
"current".

### Duplicate-as-new-session

`create_workspace_session` already deep-copies `canvas_widget_state`. A full
"Duplicate tab" command needs:

- deep-copy `document` and decide whether image refs are shared or cloned,
- deep-copy `viewport.session_data`,
- copy `state_slots`/`resources` opt-in per blueprint because some entries are
  intentionally session-local, such as thread pools and QRhi textures.

This probably belongs on `SessionBlueprint` as a `clone(session) -> session`
hook.

### Multi-compare per-session: real model

Today the `MultiCompareWidget` has a single embedded `MultiCompareStore` that
is swapped via `replace_state`. Long-term it would be cleaner to:

- keep the widget purely visual,
- bind it to whatever `MultiCompareState` lives on the active session's
  `state_slots`,
- have all actions dispatch through a workspace-aware store so undo,
  serialization, and cross-tab observers all just work.

### Document the contract

`TAB_CONTRACT.md` should describe:

- which hooks fire when,
- recommended way to use `state_slots` vs ad-hoc instance dicts,
- ownership rules for `resources` namespaces.

## P2 - Bring multi_compare up to image_compare's host-memory bounding

Status: `Open`

Area: `src/tabs/multi_compare/scene/passes/base_images.py`,
`src/tabs/multi_compare/scene/resources.py`,
`src/shared/rendering/tile_texture_service.py`,
[tile-rendering-system.md](rendering/tile-rendering-system.md#host-side-memory-bounding)

The GPU-side tile grid is already properly shared: `TileTextureService`
(`shared/rendering/tile_texture_service.py`) and apron padding
(`shared/rendering/tile_geometry.py`'s `_apron_rect`/`_TILE_APRON_PX`) live
in `shared/rendering/` and both `image_compare` and `multi_compare` already
import the same code (`multi_compare/scene/renderer.py` constructs its own
`TileTextureService` instance, not a reimplementation). Per-side visible-rect
math (`_visible_side_image_rect` vs `_visible_slot_image_rect`) is
deliberately *not* shared — it mirrors each tab's own shader uv derivation,
and the two viewport models genuinely differ (image_compare: letterbox +
split + separate hi-res "source" role; multi_compare: plain per-slot
pan/zoom/fit) — forcing a shared abstraction here risks exactly the
draw/residency mismatch bug the tiling system is fragile to.

What is a real, confirmed gap (checked 2026-07-13, `grep` for
`LazyPixelSource`/`_texture_upload_cache` under `src/tabs/multi_compare/`
returns nothing):

- `multi_compare` has GPU-tile eviction (`tile_service.evict_over_budget`,
  `SLOT_TILE_CACHE_BUDGET_BYTES`) but **no host-side QImage cache budget**
  equivalent to image_compare's `_texture_upload_cache` LRU
  (`touch_texture_upload_cache`/`evict_texture_upload_cache_over_budget` in
  `image_compare/canvas/texture_parts/upload_queue.py`). Every slot's
  full-resolution QImage stays resident in host RAM uncapped.
- `LazyPixelSource`/`maybe_wrap_for_lazy_storage` (the memmap-spill large-image
  path, see tile-rendering-system.md) is wired into image_compare's load path
  only (`_session_controller.py`, `use_cases/loading.py`). A multi_compare
  slot loaded with an 18000×18000px image today hits the same anonymous-heap
  OOM risk that motivated Phase 2/3 originally, just not yet fixed here.

Proposed direction: generalize the host-texture-cache LRU helpers in
`upload_queue.py` into `shared/rendering/` (keyed generically rather than on
image_compare's fixed 5 texture-key roles), and wire
`maybe_wrap_for_lazy_storage`/`close_if_lazy` into multi_compare's slot-load
path. This is consistent with `TAB_CONTRACT.md`'s isolation rule — that rule
targets app-level i18n/theme/QSS keys specifically; `shared/rendering/` is
already the sanctioned place for cross-tab render infra reuse (precedent:
`TileTextureService` itself).

## P3 - Consider a GEGL-style always-tiled pixel storage model

Status: `Open`

Area: `src/shared/image_processing/lazy_pixel_source.py`,
`src/tabs/image_compare/canvas/rhi_renderer/resources.py`,
[tile-rendering-system.md](rendering/tile-rendering-system.md#host-side-memory-bounding)

Today large-source memory handling is threshold-gated: images stay a plain
in-memory PIL image until they cross `AppConstants.PHASE3_LAZY_THRESHOLD_PX`
(16384px), at which point they switch to `LazyPixelSource` (memmap-backed,
disk-spilled). This is a two-tier model — small images get the fast/simple
path, huge ones get the safe-but-slower path — and the threshold has to be
picked and defended (see 2026-07-13 conversation reasoning: below the
threshold, memmap spill is pure overhead — disk I/O on every load, per-access
`.crop()`/`.to_pil()` materialization cost, extra failure surface from
`tempfile.mkstemp`/`os.makedirs`).

GIMP's GEGL backend does not have this two-tier split at all — every image,
regardless of size, goes through the same tiled (`GeglBuffer`, ~128×128px
tiles) lazy-cache architecture with disk swap under memory pressure. Worth
evaluating whether a similar "always tiled, no threshold" model would be
simpler to reason about long-term than maintaining a manually-tuned
threshold plus two separate code paths (`is_lazy` branches throughout
`realize_tile_plan`, `qimage_from_pil`, SSIM diff, export). Not clearly a
win — GEGL's tile size (128px) and update cadence are tuned for a very
different workload (arbitrary compositing graph, not a two-image compare
viewer), and rewriting the whole pixel-storage layer to be unconditionally
tiled is a much bigger and riskier change than tuning one threshold.
Captured as a "worth investigating," not a committed plan.

Right now contributors have no source of truth besides reading code.
