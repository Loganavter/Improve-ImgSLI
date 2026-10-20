# Plan — persistent cross-session catalog for the Image Gallery

Status: draft · Date: 2026-10-21 · Scope: `src/tabs/image_gallery/` (tab-owned)
Task: `task-gallery-persistent-cross-session-2026-10-12` · Base: `46433b51`

Related: [plan-gallery-analysis-engine-2026-10-20.md](plan-gallery-analysis-engine-2026-10-20.md)
(its non-goal at `:26-28` hands this task over) ·
[plan-gallery-split-2026-10-17.md](plan-gallery-split-2026-10-17.md) ·
[../../../../../docs/dev/CODE_PATTERNS.md](../../../../../docs/dev/CODE_PATTERNS.md)

**Premise.** Everything the gallery knows about a folder dies on exit: pool
membership lives in a session slot that is itself an in-memory dict
(`src/core/store_workspace.py:180`, `src/domain/workspace.py:15-21`), so it
survives tab switches but not a restart; the only cross-restart path is a saved
`.imgsli` project (`src/services/io/project_io.py:59`). Per-file caches
survive — the AI scorecard (`src/tabs/image_gallery/services/ai_cache.py:3-10`),
VLM tie-breaks/briefs (`services/vlm_cache.py:3-4`), Jev ranks
(`services/jev_cache.py:3-4`), metric profiles (`services/profile_cache.py:3-4`),
thumbnails (`services/thumbnail_cache.py:3-4`) — but a cache is a lookup, not a
catalog: it cannot answer "which folders do I know", "what was in this folder",
"what did the user decide", or "which axis came from which producer".

This plan adds **one** local SQLite catalog: a folder/file pool index plus user
decisions and per-axis analysis records, read once at restore, written from the
existing single dispatch seam.

---

## 1. Verified as-is map

Path convention for this whole document: a citation like `use_cases/persistence.py:95`
is relative to **`src/tabs/image_gallery/`**; anything starting with `src/`,
`docs/`, `tests/` or another top-level directory is repo-root relative. Every
line number below was opened during the survey (2026-10-21, base `46433b51`).

### 1.1 What actually survives a restart today

| Fact | Evidence |
|---|---|
| Session slots are a plain dict on an in-memory dataclass — no file, no journal | `src/domain/workspace.py:19` (`state_slots: dict[str, Any]`), `src/core/store_workspace.py:180` (`session.state_slots[slot_name] = value`) |
| The gallery slot is the tab's single in-run source of truth (pool, selection, filter, folder, triage summary) | `src/tabs/image_gallery/use_cases/persistence.py:11-15`, `src/tabs/image_gallery/state/models.py:27-41` |
| Restore rebuilds the controller mirror from the slot **without** rescanning when the slot carries items | `use_cases/persistence.py:95-112` → `GalleryController._sync_from_slot` (`use_cases/gallery_slot.py:218-301`) |
| A disk rescan happens only for an empty/absent/foreign slot (legacy sessions) | `use_cases/persistence.py:113-141` → `controller.open_folder` (`controller.py:1069-1073`) |
| Cross-restart persistence exists only as project save/load (and session duplicate), through `serialize_session`/`deserialize_session` | `src/services/io/project_io.py:59`, `src/services/io/project_io.py:182-204`, `src/core/main_controller_parts/sessions.py:153-166` |
| The serialized snapshot is v2 and carries `folder/filter_text/selection/triage_state/mode/source_path` + `items[]` of `{path, mtime_ns, status, rank}` | `use_cases/persistence.py:45`, `:159-177` |
| Deserialize rebuilds `GalleryItemMeta` from those four fields and writes the slot **directly**, bypassing the dispatcher | `use_cases/persistence.py:199-223`, `:229` |
| Chrome that does survive a restart: `view_list` + `judgment_domain` via `SessionState` (slot + QSettings fallback) | `tab.py:69-77`, `src/tabs/use_cases/session_state.py:1-14` |
| A gallery plugin session owns exactly one slot, `gallery` | `plugin.py:44-49`, `bootstrap_reducers.py:6` |

**Consequence:** there is no catalog to migrate. Schema starts at v1, and no
user has a stale on-disk catalog to reconcile (the only persistent artifacts
users hold are `.imgsli` project files and the five caches below).

### 1.2 What the in-memory models hold, and what is missing

| Field group | Held on | Persisted today? | Evidence |
|---|---|---|---|
| identity: `path`, `mtime_ns` (no size) | `GalleryItem` (`models.py:249-251`), `GalleryItemMeta` (`state/models.py:17-23`) | slot (in-run) + project | scanner writes only mtime: `services/folder_scanner.py:59` |
| thumbnail status string | `GalleryItem.thumbnail_status` (`models.py:252`), slot `status` | slot; pixmaps/LOADING never | `state/models.py:5-7`, `models.py:252-253` |
| AI result (rich: tags, defects, notes, axes, model) | `GalleryItem.analysis` (`models.py:255`) | **disk cache only**, keyed `path:mtime` + identity | `services/ai_cache.py:3-10`, `:198-210` |
| local detector numbers | `GalleryItem.metrics` (`models.py:264`) | **no** — recomputed every run | `use_cases/proxy_pass.py:305-328` re-runs when metrics are absent (`:310-312`) |
| rank + its origin | `GalleryItem.rank/rank_source` (`models.py:258-263`) | slot carries `rank` only, `rank_source` lost | `state/reducer.py:114-138` |
| crown/reject/best | `GalleryItem.rejected/is_best/crown_rank` (`models.py:266-268`) | **no** — not in slot, not in any cache | `state/models.py:17-23` has no such field; `state/reducer.py:39-48` |
| manual overrides (series) | `GalleryController._series_overrides` (`controller.py:224`) | **no, explicitly out of scope** in code | `controller.py:219-224` comment, `use_cases/series_override.py:6-8` |
| series objects | `GalleryState.series` (`models.py:332`) | **no** — restored pool comes back flat and is regrouped | `tab.py:178-182`, `use_cases/triage_run.py:328-339` |
| phash/embedding (grouping) | module dict `_SIGNATURE_CACHE` (`services/clustering.py:152-156`) | **no** — recomputed each process | `services/clustering.py:187-211` |
| metric profile (axis subset) | `GalleryState.metric_profile` (`models.py:344`) | transient field, but the **pin** survives via `profile_cache` | `services/profile_cache.py:90-120` |
| activity (queued/analyzing/…) | `GalleryItem.activity_*` (`models.py:293-296`) | deliberately never | `models.py:293` |
| hover/scroll/folder generation/thumb-inflight | widget + controller counters | never | `controller.py:249`, `:301`, `:266-267` |

### 1.3 Identity and invalidation as they exist (four different rules)

| Seam | Key | Evidence |
|---|---|---|
| thumbnail / AI scorecard | `sha256(resolved_path:mtime_ns)[:24]` | `services/thumbnail_cache.py:30-32`; `ai_cache` reuses it (`services/ai_cache.py:42`, `:198-210`) |
| VLM tie-break / brief | `sha256("path:mtime", …)` (+ optional source mtime) | `services/vlm_cache.py:36-46`, `:49-55` |
| Jev rank | `sha256(paths+mtimes+canonical payload)` | `services/jev_cache.py:60-81` |
| metric profile pin | `sha256(sorted(path:mtime) + mode + model + base_url + effort + pool ids)` | `services/profile_cache.py:90-120` |
| **phash/embedding (in memory)** | `(path, mtime_ns, size)` | `services/clustering.py:159-170` |
| Stage-2 analysis fingerprint (in memory) | paths + mtimes + presence flags of metrics/artifacts | `use_cases/proxy_pass.py:305-328` |

The exact behaviour today is coherent only because nothing durable needs a
single identity. A catalog does: one row set must describe one file version.
The `clustering` key already includes **size** while the four disk caches do
not — so "edited in place with preserved mtime" is already an inconsistency to
fix, not a new requirement.

### 1.4 Comment/code divergences found while verifying (facts, not opinions)

1. `services/folder_scanner.py:19-22` claims truncation "is surfaced by the
   widget via `set_scanning(n, total)`". No production caller passes the
   truncation count: `truncated` is only logged (`:64`, `:74`), and the only
   `set_scanning` callers are the triage progress path
   (`use_cases/triage_run.py:432`, `:446`) with `(0, len(items))`.
2. `models.py:3-5` says folder contents are "derived from disk on demand;
   nothing here needs to survive a session switch beyond the last-opened folder
   path". Since the slot learned the full pool (`use_cases/persistence.py:159-177`) the
   model is still disk-derived, but the pool *does* survive a switch — the
   docstring describes the pre-Redux tab.
3. `models.py:317-319` calls `judgment_domain` "Transient view state … session
   slot persistence is a follow-up", while `tab.py:69-77` already persists it
   through `SessionState` (slot + QSettings). Same for `view_list`.
4. `analysis/read.py:22-23` says `backend` "stays `None` until the catalog is
   wired into the producers (W5)" — that "catalog" is the **analysis engine's**
   provider/model resolver (`src/engine/analysis/catalog.py:1-12`), not this
   persistence catalog. Name collision: this plan never uses the bare word
   `catalog` for a module; the storage module is `gallery_catalog`.

### 1.5 Assumptions (not verified — do not build on them)

- **A1.** A real image folder's `scandir`+`stat` cost is materially higher than
  the empty-file probe in §9.1 (cold page cache, network mounts). Not measured.
- **A2.** `QStandardPaths.CacheLocation` may be wiped by OS cleaners on some
  platforms (`src/services/io/project_package.py:133-152` is a *cache* root). Not
  verified on any distro; treated as a risk, not a fact.
- **A3.** No other process opens the app's cache/data dirs concurrently. Not
  verified; the design still tolerates it via SQLite locking.

---

## 2. Scope of the catalog

### 2.1 Becomes persistent

| Domain | Content | Why it must persist |
|---|---|---|
| folder registry | absolute folder path, last seen, last completed scan, item count, per-folder view prefs (sort key, filter text, judgment domain) | answers "which folders do I know" and lets a new session open the last one |
| pool membership | `(folder, file, position)` + terminal thumbnail status | paints a known folder before/without a scan |
| file identity | path, `size`, `mtime_ns`, `content_key`, first/last seen, `missing_since` | binds every durable record to one file version |
| analysis records | one run per `(content_key, domain, producer, backend, profile)` + one row per axis with value/status/reason/producer/backend, plus artifact severities | per-axis provenance survives a restart (`src/engine/analysis/contracts.py:124-166`); local metrics stop being recomputed from scratch |
| user decisions | `rejected`, `is_best`, `crown_rank`, `manual_rank`, rating, labels | these are *user-authored*; losing them is the actual product defect |
| series | series key, members, `rank_source`, best/source file, manual overrides | the slot never carried them (`state/models.py:17-23`); restore currently regroups from scratch (`use_cases/triage_run.py:328-339`) |
| grouping signatures | phash + embedding per `content_key` (+ algorithm version) | turns `_SIGNATURE_CACHE` (`services/clustering.py:155`) into a durable index: series paint before decode |
| derived ranks (as a snapshot) | rank/rank_source per `(series, file)` | optional cache of the pure fusion result; always recomputable, never authoritative |

### 2.2 Deliberately NOT persistent

- hover, scroll offset, marquee, focus, selection *order* (selection is
  in-run session state; `state/models.py:27-41` — the slot keeps it per session,
  the catalog does not own it);
- `QPixmap`s, thumbnail LOADING in-flight flags, worker/generation counters
  (`state/models.py:5-7`, `controller.py:249`, `:301`);
- activity phases (`models.py:293-296`);
- the Ask-AI in-session answer cache (`controller.py:241-243`);
- the live metric profile object (`models.py:344`) — its *pin* stays in
  `profile_cache`; the catalog stores the profile **key** with the run, not a
  second profile store;
- vaults/secrets: the AI identity is `provider/model/base_url/params`, never
  `api_key` (`services/ai_cache.py:30-32` states the same rule for the cache;
  the catalog inherits it — `AiSettingsStore` owns credentials,
  `services/ai_settings_store.py:86-92`).

---

## 3. Data model

Module: `src/tabs/image_gallery/services/gallery_catalog/` — deliberately not
`catalog.py` (that name is taken by the engine resolver,
`src/engine/analysis/catalog.py`).

```
services/gallery_catalog/
    __init__.py      # public API only
    paths.py         # catalog_path() / override + dir/file modes
    keys.py          # content_key()  <-- THE identity seam
    schema.py        # DDL + user_version + forward migrations
    store.py         # read/write functions (one connection per call)
    hydrate.py       # rows -> GalleryItem / GallerySlotState (pure)
```

### 3.1 Schema (v1, `PRAGMA user_version = 1`)

```sql
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE folder (
    id            INTEGER PRIMARY KEY,
    path          TEXT NOT NULL UNIQUE,      -- absolute, normpath (no resolve())
    last_seen_ns  INTEGER NOT NULL,
    last_scan_ns  INTEGER,                   -- last completed reconcile
    item_count    INTEGER NOT NULL DEFAULT 0,
    sort_key      TEXT,                      -- toolbar indices: ui/toolbar/__init__.py:138
    filter_text   TEXT NOT NULL DEFAULT '',
    judgment_domain TEXT NOT NULL DEFAULT 'algorithms'
);

CREATE TABLE file (
    id            INTEGER PRIMARY KEY,
    path          TEXT NOT NULL UNIQUE,
    size          INTEGER NOT NULL,
    mtime_ns      INTEGER NOT NULL,
    content_key   TEXT NOT NULL,             -- keys.content_key(...)
    first_seen_ns INTEGER NOT NULL,
    last_seen_ns  INTEGER NOT NULL,
    missing_since_ns INTEGER                 -- set on ENOENT, cleared on return
);
CREATE INDEX file_content_key ON file(content_key);

CREATE TABLE folder_item (
    folder_id   INTEGER NOT NULL REFERENCES folder(id) ON DELETE CASCADE,
    file_id     INTEGER NOT NULL REFERENCES file(id)   ON DELETE CASCADE,
    position    INTEGER NOT NULL,            -- scan order (services/folder_scanner.py:70)
    thumb_status TEXT NOT NULL DEFAULT 'not_loaded',  -- terminal values only
    PRIMARY KEY (folder_id, file_id)
);
CREATE INDEX folder_item_pos ON folder_item(folder_id, position);

CREATE TABLE decision (                      -- USER-authored, never auto-written
    file_id     INTEGER PRIMARY KEY REFERENCES file(id) ON DELETE CASCADE,
    rating      INTEGER,                     -- NULL = unrated (open question Q4)
    labels      TEXT NOT NULL DEFAULT '[]',  -- JSON array of strings
    rejected    INTEGER NOT NULL DEFAULT 0,
    is_best     INTEGER NOT NULL DEFAULT 0,
    crown_rank  INTEGER,
    manual_rank INTEGER,                     -- rank_source == "manual"
    updated_ns  INTEGER NOT NULL
);

CREATE TABLE series (
    id             INTEGER PRIMARY KEY,
    folder_id      INTEGER NOT NULL REFERENCES folder(id) ON DELETE CASCADE,
    series_key     TEXT NOT NULL,             -- stable, derived from member content keys
    rank_source    TEXT,                      -- 'manual' | 'fusion' | 'jev'
    best_file_id   INTEGER REFERENCES file(id) ON DELETE SET NULL,
    source_file_id INTEGER REFERENCES file(id) ON DELETE SET NULL,
    updated_ns     INTEGER NOT NULL,
    UNIQUE (folder_id, series_key)
);

CREATE TABLE series_member (
    series_id  INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    file_id    INTEGER NOT NULL REFERENCES file(id)   ON DELETE CASCADE,
    member_rank INTEGER,
    PRIMARY KEY (series_id, file_id)
);

CREATE TABLE series_override (                -- controller._series_overrides
    folder_id  INTEGER NOT NULL REFERENCES folder(id) ON DELETE CASCADE,
    file_id    INTEGER NOT NULL REFERENCES file(id)   ON DELETE CASCADE,
    series_key TEXT,                          -- NULL = forced UNGROUPED
    updated_ns INTEGER NOT NULL,
    PRIMARY KEY (folder_id, file_id)
);

CREATE TABLE signature (                      -- clustering._SIGNATURE_CACHE
    content_key  TEXT PRIMARY KEY,
    algo_version INTEGER NOT NULL,            -- bump = every signature recomputed
    phash        INTEGER NOT NULL,
    embedding    BLOB NOT NULL                -- float32 little-endian
);

CREATE TABLE analysis_run (
    id            INTEGER PRIMARY KEY,
    file_id       INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
    content_key   TEXT NOT NULL,
    domain        TEXT NOT NULL,              -- 'algorithms' | 'ai' (JUDGMENT_DOMAINS, models.py:99)
    producer      TEXT NOT NULL,               -- 'local' | 'vlm' (analysis/read.py:42-44)
    backend_provider TEXT, backend_model TEXT, backend_base_url TEXT,
    backend_params   TEXT,                     -- canonical JSON (freeze_mapping, src/engine/analysis/contracts.py:106-110)
    profile_key   TEXT,                        -- profile_cache key, when the axis set was profiled
    prompt_schema_version INTEGER,
    status        TEXT NOT NULL,               -- 'ok' | 'error' | 'partial'
    error         TEXT,
    started_ns    INTEGER NOT NULL,
    finished_ns   INTEGER,
    UNIQUE (content_key, domain, producer, backend_provider, backend_model,
            backend_base_url, backend_params, profile_key)
);
CREATE INDEX analysis_run_file ON analysis_run(file_id, content_key, domain);

CREATE TABLE axis_value (
    run_id INTEGER NOT NULL REFERENCES analysis_run(id) ON DELETE CASCADE,
    axis   TEXT NOT NULL,
    value  REAL,                               -- NULL iff status forbids a value
    status TEXT NOT NULL,                      -- AXIS_STATUSES, src/engine/analysis/contracts.py:35
    reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, axis)
);
CREATE INDEX axis_value_axis ON axis_value(axis, status);

CREATE TABLE artifact_severity (
    run_id    INTEGER NOT NULL REFERENCES analysis_run(id) ON DELETE CASCADE,
    artifact  TEXT NOT NULL,                   -- models.Artifact (models.py:67-74)
    severity  TEXT NOT NULL,                   -- models.Severity (models.py:61-64)
    PRIMARY KEY (run_id, artifact)
);
```

Creation pragmas: `journal_mode=WAL`, `synchronous=NORMAL`,
`foreign_keys=ON`, `auto_vacuum=INCREMENTAL` (set **before** the first table —
it cannot be changed later without a `VACUUM`), `busy_timeout=2000`.

### 3.2 Schema version + migration policy

- `PRAGMA user_version` is the version; `schema.py` holds
  `MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]]`.
- Open path: read `user_version`; if `< CURRENT`, apply each migration in
  ascending order, **each in its own transaction**, then set the new version.
- If `user_version > CURRENT` (a downgraded app opened a newer DB): open
  **read-only**, log once, and behave as if no catalog exists (fail open for
  display, fail closed for writes). Never attempt a down-migration.
- v1 has no predecessor: no backfill from the JSON caches (they stay valid as
  payload stores; §3.3).

### 3.3 ONE content key, related to the caches

```python
# services/gallery_catalog/keys.py
def content_key(path: Path, mtime_ns: int, size: int) -> str:
    """sha256("<resolved path>:<size>:<mtime_ns>")[:24] — THE file-version key."""
```

```python
# services/thumbnail_cache.py (the existing seam, same name/signature)
def cache_key_for(path: Path, mtime_ns: int) -> str:
    try: size = path.stat().st_size
    except OSError: size = 0
    return content_key(path, mtime_ns, size)
```

`ai_cache` already imports `cache_key_for` (`services/ai_cache.py:42`), so it
inherits the change for free; `vlm_cache`, `jev_cache`, `profile_cache` each
build their own hash today (`services/vlm_cache.py:36-55`, `services/jev_cache.py:60-81`,
`services/profile_cache.py:90-120`) and are converted to fold in `content_key(...)`
instead of a hand-rolled `path:mtime` string, so **one** rule (path + size +
mtime) governs every invalidation.

Cost, stated plainly: this is a **one-time invalidation of every existing
cache** (all entries become misses and are recomputed), and one extra `stat`
per cache lookup. That is the price of having one rule instead of four; it is
owner decision Q5. Until it lands, the catalog must not store `content_key`
rows that the caches cannot agree with — wave order in §7 enforces this.

Relationship to the engine's G4 gate (`test_analysis_cache_identity.py`,
plan-gallery-analysis-engine `:297`): that gate is about **model identity**
(`BackendRef`), which `analysis_run.backend_*` carries separately. The file
identity (`content_key`) and the model identity (`BackendRef`) are two
orthogonal columns on purpose — one never substitutes for the other.

`size` is added to `GalleryItem` (+`services/folder_scanner.py`, both C1) and to
the catalog row, but **not** to `GalleryItemMeta` (`state/models.py:17-23`): the
session slot stays `path+mtime` (`use_cases/persistence.py:159-177`), because
adding a field there bumps `_SERIALIZE_VERSION` (`use_cases/persistence.py:45`)
and would give the slot a second identity rule of its own.

---

## 4. Read path at startup

### 4.1 Sequence

Hook: `restore_from` (`use_cases/persistence.py:85-141`) — the single place the
tab decides what to paint for a session. New branch, before the legacy rescan
at `:135`:

1. slot has items → **unchanged** (`:95-112`, slot wins, no catalog read).
2. slot empty/absent but carries `folder` → `gallery_catalog.load_pool(folder)`:
   one indexed query (`folder_item ⋈ file ⋈ decision`, ordered by `position`).
   Build `GalleryItem`s in `gallery_catalog/hydrate.py` (pure: rows → items, no
   Qt), set `state.folder`, `widget.set_folder_label(folder)`,
   `widget.rebuild_grid(items)` — the same trio the slot sync uses
   (`use_cases/gallery_slot.py:285-289`, `:293-296`).
3. Paint is **provisional**: every item from the catalog starts with
   `thumbnail_status` from `folder_item.thumb_status` and `analysis_status`
   from `analysis_run`; no axis value is rendered as current until the
   reconcile in step 4 confirms the file version (fail-closed matrix below).
4. Start **reconcile**: `scan_folder(folder)` (`services/folder_scanner.py:25`)
   — today synchronous, see §4.3 — diff against the catalog rows, apply
   added/removed/changed, then run the existing pipeline
   (`_hydrate_ai_cache`, `rebuild_grid`, `_begin_folder_schedule`,
   `_start_triage`, `use_cases/folder_loading.py:94-104`).
5. A new gallery session with **no** slot and no folder: `gallery_catalog.recent_folders(limit=1)`
   is offered (auto-open vs a picker is owner decision Q1); if the owner picks
   "auto", it is applied exactly like step 2 and the source is
   `on_session_created` (`tab.py:356-360`) or `create_page` (`tab.py:171-177`).

### 4.2 Fail-open / fail-closed matrix

| Catalog row | Disk state | What the user sees | Binding rule |
|---|---|---|---|
| file row, `mtime_ns`+`size` match | exists | normal card, stored decisions/ranks/axes shown | **bound** — content identity confirmed |
| file row, `mtime_ns` or `size` differs | exists | card + old thumbnail, marked `stale`; old axes NOT shown as current; re-analysis scheduled | **fail closed** — new `content_key`, new run; decisions are *offered* for re-apply (see §4.4), never silently rebound |
| file row, `missing_since_ns` set | ENOENT | "missing" placeholder; no thumbnail, decisions preserved | **fail closed** — never bind a different file to this row |
| no row | exists | new item, `not_loaded`, then normal pipeline | normal insert |
| row with a corrupt/NULL `content_key` | any | treated as "no record": placeholder, re-derive | **fail closed** |
| catalog DB unreadable/absent/read-only | any | today's behaviour exactly: rescan and paint | **fail open** — catalog is never required for correctness |
| `analysis_run` row whose `content_key` ≠ current file key | exists | axis rendered as `gap` with reason "record is for an older version" | **fail closed** — `AxisValue(status="gap")` is the only legal empty (`src/engine/analysis/contracts.py:124-137`) |

The invariant, in one sentence: *a missing or unreadable record may cost a
placeholder and a retry; it may never attach a neighbour's number to a file.*

### 4.3 "While a scan is in flight"

There is no in-flight scan today: `open_folder` scans synchronously on the GUI
thread and only then paints (`use_cases/folder_loading.py:88`, `:91-95`). So the
catalog path paints **first** and reconciles **after**; a slow reconcile is the
only new in-flight state. Two options, chosen per wave:

- **Option A (C3, default):** keep the synchronous scan, but run it *after* the
  catalog paint; the grid is already populated, so the scan no longer gates the
  first frame. On a cold/remote FS the UI still blocks during the scan — the
  honest limitation.
- **Option B (follow-up wave, not in §7):** move `scan_folder` to the existing thread pool
  (`controller.schedule` / `_begin_folder_schedule`, `controller.py:360-394`)
  and apply the diff under the existing `_folder_gen` guard (`controller.py:249`,
  `:315-337`) so a late scan cannot repopulate a switched folder. This is the
  only correct fix for a genuinely slow folder; it touches generation
  discipline heavily and is a separate, revertible wave.

### 4.4 Moved files

`content_key` contains the resolved **path**, so a rename is a *different* key
by construction (same as every cache today, `services/thumbnail_cache.py:31`). The
catalog therefore treats a move as delete + insert. User decisions may be
re-attached only on an exact `(size, mtime_ns)` match that is **unique within
the folder** and only into `decision` — never `analysis_run` (a decision is
user intent, an analysis is a content claim). Anything weaker re-analyses.
Exact content hashing for move detection is Q7.

---

## 5. Write path

### 5.1 Single writer

Every live gallery mutation already funnels through two functions:

- `_emit_gallery(owner, action)` — `use_cases/gallery_slot.py:130-166`
- `_transact_gallery(owner, actions)` — `use_cases/gallery_slot.py:169-188`

That is the write seam. The catalog **observes** it, it does not get its own
call sites scattered through the controllers:

1. after a successful dispatch, append `("observe_pool", owner)` to a pending
   buffer (membership + statuses + ranks come from the slot itself, via the
   existing selector read `_gallery_slot(owner)`, `use_cases/gallery_slot.py:119-127`);
2. for `GalleryTriageFinished` / manual-rank actions, also append
   `("observe_decisions", owner, ranks)` — that is where
   `_mark_triage_picks_manual` already runs (`use_cases/gallery_slot.py:144-148`), so the
   manual decisions are frozen before they are observed
   (`use_cases/triage_actions.py:24-54`);
3. a single `flush()` executes the buffer in **one transaction** on a Qt idle
   tick (`QTimer.singleShot(0, ...)`, same coalescing shape as
   `_pending_card_items`, `controller.py:266-267`), and unconditionally from
   `ImageGalleryTab.deactivate`/`dispose` (`tab.py:317`, `:448-462`).

`deserialize_session` writes the slot directly (`use_cases/persistence.py:229`),
bypassing the dispatcher, so a project load would be invisible to the writer.
Fix inside the read seam: `restore_from` calls
`gallery_catalog.observe_pool(folder, entries)` when it accepts a non-empty slot
(both project load and session switch), which makes the catalog lag at most one
activation.

### 5.2 Thread affinity

- All catalog reads/writes happen on the **GUI thread**. Workers never touch
  SQLite: thumbnail/AI/analysis completions are already marshaled to the GUI
  before they mutate items (`_pending_thumb_ready`, `controller.py:259-260`;
  `_pending_card_items`, `:266-267`).
- One connection per operation, `check_same_thread=True` (default), opened and
  closed inside the function — no long-lived handle, no cross-thread state, and
  nothing to tear down at exit. This mirrors the caches (module functions, no
  singleton; `services/thumbnail_cache.py:22-36`).
- `busy_timeout=2000` + WAL absorbs a second gallery tab writing at the same
  moment; SQLite is the single-writer arbiter, so no in-process lock is needed.

### 5.3 Crash safety and degradation

| Situation | Behaviour |
|---|---|
| crash mid-flush | WAL + one transaction per flush: the transaction is either fully applied or absent. Worst case loses the last buffer (≤ one idle tick). |
| `sqlite3.DatabaseError` at open (`file is not a database`, truncated) | rename to `catalog.sqlite3.corrupt-<utc>`, create a fresh DB, log once, continue with the in-memory path. |
| read-only dir / full disk (`OperationalError: readonly` / `database or disk is full`) | set a module-level `degraded` flag for this process; skip further writes; log once at WARNING; the gallery behaves exactly as today. Never blocks startup, never raises into a gesture. |
| locked by another process | `busy_timeout` then treat as degraded (same path). |
| corrupted *rows* (NULL key, unknown status) | row-level: drop the row from the result, never raise (`hydrate.py` validates against `AXIS_STATUSES`, `src/engine/analysis/contracts.py:35`). |

### 5.4 Compaction / pruning

- `prune()` (called from the same idle tick, at most once per 24 h, recorded in
  `meta`): delete `file` rows with `missing_since_ns` older than N days **and**
  no `decision` row; drop `folder_item` rows for those files;
  delete `analysis_run` rows whose `content_key` no longer appears in `file`.
- `PRAGMA incremental_vacuum` after a prune that deleted > 1 000 rows.
- `PRAGMA wal_checkpoint(TRUNCATE)` on `dispose` (`tab.py:448`) — cheap, keeps
  the `-wal` file from growing across sessions.
- Never `VACUUM` automatically (blocking, full-copy).
- Retention default (N days, folder age) is owner decision Q3.

---

## 6. Privacy

| Boundary | Rule | Enforcement |
|---|---|---|
| location | local only, under the app data dir (`src/core/control/discovery.py:56-67`), overridable by `IMGSLI_GALLERY_CATALOG` for tests | `paths.py` is the only place a path is built; gate G10 asserts it |
| permissions | dir `0700`, file `0600` (mirroring `_DIR_MODE`/`_FILE_MODE`, `src/core/control/discovery.py:50-53`) | unit test asserts `stat().st_mode` |
| network | the storage module imports no transport: no `services.ai_client`, `services.jev_client`, `services.vlm`, no `urllib`/`requests`/`socket` | AST gate G10 (mirrors `tests/contracts/test_analysis_*` style) |
| no secrets | `backend_*` columns hold provider/model/base_url/params; `api_key` is never written (`services/ai_cache.py:25-28` is the precedent) | test asserts a key present in settings never appears in any column |
| diagnostics | if catalog stats are ever added to the diagnostics report, paths go through `src/plugins/diagnostics/redact.py:109-126` (absolute paths are hashed, `tests/plugins/test_diagnostics_redact.py:9-15`, `:47`) | existing redaction test extended by that wave, not here |
| docs/tests | no real home paths in docs, tests, fixtures or commit messages — synthetic roots only (`/album/…`, `tmp_path`) | gate G10 greps the new module + this plan for `/home/`, `$HOME`, `~/.local` |

---

## 7. Waves with ownership

Constraint: max 4 parallel writers, one clone + one branch each. **Not claimed
(owned by `task-gallery-analysis-engine-*`):** `src/engine/analysis/**`,
`src/tabs/image_gallery/analysis/producers/**`, `services/ai_client/**`,
`tests/contracts/test_analysis_substrate_contracts.py`,
`tests/contracts/test_analysis_substrate_*.py`, `services/{ai_client,jev_client,series_priority,profile_ai,vlm}.py`
(the engine plan's W5 list, `plan-gallery-analysis-engine-2026-10-20.md:318-322`).
All new gates in this plan are **tab-local** (`src/tabs/image_gallery/tests/`),
so `tests/**` at the repo root is untouched.

| Wave | Owns files | Scope | Runs in parallel with |
|---|---|---|---|
| **C1 catalog-core** | `services/gallery_catalog/{__init__,paths,keys,schema,store,hydrate}.py`, `models.py` (+`GalleryItem.size`), `services/folder_scanner.py` (+`size`), `tests/catalog/test_catalog_schema.py`, `test_catalog_paths.py`, `test_catalog_store.py`, `test_catalog_privacy.py` | schema + migrations + `content_key` + store API + pure hydrate; **no callers**; behaviour-neutral | nothing (first) |
| **C2 content-identity** | `services/thumbnail_cache.py`, `services/ai_cache.py`, `services/vlm_cache.py`, `services/jev_cache.py`, `services/profile_cache.py`, `tests/catalog/test_content_key_single_rule.py` | one key rule (§3.3); one-time cache invalidation; G11 | nothing (must merge before C3/C4 write keys) |
| **C3 catalog-read** | `use_cases/persistence.py`, `use_cases/folder_loading.py`, `use_cases/catalog_hydrate.py`, `tests/catalog/test_catalog_restore.py`, `test_catalog_stale_rows.py` | §4: paint-from-catalog, reconcile, matrix; no writes beyond `observe_pool` | C4 (disjoint files) |
| **C4 catalog-write** | `use_cases/gallery_slot.py`, `use_cases/catalog_persist.py`, `services/clustering.py`, `use_cases/cache_reset.py`, `tests/catalog/test_catalog_write.py`, `test_catalog_prune.py` | §5: observe/flush, decisions, signatures, pruning, degraded mode; G4, G12, G13 | C3 (disjoint files) |

Serialization: C1 → C2 → (C3 ∥ C4). Two writers is the real parallelism here;
adding a third would mean splitting decisions away from the write seam, i.e. a
second writer — the thing this design exists to avoid.

**Declared interface** (C1 defines it in `services/gallery_catalog/__init__.py`;
C3 and C4 consume it verbatim — no second implementation, no local variant):

```python
@dataclass(frozen=True)
class PoolEntry:            # one slot item, without rich field access
    path: str
    mtime_ns: int
    size: int
    thumb_status: str = "not_loaded"   # terminal values only
    rank: int | None = None

def catalog_path() -> Path                              # paths.py
def content_key(path: Path, mtime_ns: int, size: int) -> str   # keys.py
def load_pool(folder: Path) -> list[PoolEntry]          # ordered by position
def observe_pool(folder: Path, entries: list[PoolEntry], *, now_ns: int | None = None) -> int
def observe_decisions(items) -> int                     # rejected/is_best/crown/manual/rating/labels
def observe_analysis(file_path: Path, run) -> int        # axes + artifacts, one run
def flush() -> int                                      # one transaction; rows written
def prune(now_ns: int | None = None) -> dict            # report, never raises
def recent_folders(limit: int = 5) -> list[dict]
```

C3 calls `observe_pool` (restore path) and `observe_analysis` (post-pipeline);
C4 calls `observe_pool`/`observe_decisions` from `_emit_gallery` and owns
`flush`/`prune` scheduling. Both write through the same C1 functions.

Per-wave verify (run in the clone, full form):

```
C1  PYTHONPATH=src QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 \
    python3 -m pytest src/tabs/image_gallery/tests/catalog -q -p no:cacheprovider
    PYTHONPATH=src python3 -c "import tabs.image_gallery.services.gallery_catalog.store as s; print(s.__file__)"  # clone path
C2  ... pytest src/tabs/image_gallery/tests/catalog src/tabs/image_gallery/tests -q
C3  ... pytest src/tabs/image_gallery/tests/catalog src/tabs/image_gallery/tests/runtime -q
C4  ... pytest src/tabs/image_gallery/tests/catalog src/tabs/image_gallery/tests -q
all ./launcher.sh test tests/contracts -q   (supervisor, merged tree)
```

What must **not** run in parallel: C1 with C2 (C2 imports `content_key`), any
wave touching `use_cases/gallery_slot.py` with another that does (C4 only), and
any wave with the engine crew's W5 (`services/vlm.py` vs our
`services/vlm_cache.py` — different files, but the engine's G4 AST gate may
need both sides consistent; coordinate, don't merge blind).

---

## 8. Gates / acceptance

Green suites are **not** acceptance: each gate below names what is red on
today's tree and why. Tab-local, `src/tabs/image_gallery/tests/catalog/`.

| Gate | Test | Red before because |
|---|---|---|
| G1 schema round-trip | `test_catalog_schema.py::test_roundtrip_v1` | `gallery_catalog` does not exist → collection error; after C1 a naive writer that drops `axis_value.status` fails round-trip equality |
| G2 forward migration | `test_catalog_schema.py::test_migration_v1_to_v2_fixture` | no versioned store exists; the fixture DB is built with v1 DDL and must survive `user_version` 1→2 |
| G3 corrupt DB | `test_catalog_store.py::test_truncated_db_opens_empty` | today nothing opens a DB; the assertion is "tab paints an empty pool, no exception, file renamed `.corrupt-*`" |
| G4 mid-write crash | `test_catalog_write.py::test_uncommitted_flush_leaves_no_rows` | a naive `execute` without an explicit transaction leaves half a pool; the test executes then closes **without** commit and asserts zero rows and a readable DB |
| G5 mtime/size change | `test_catalog_stale_rows.py::test_edited_file_is_not_bound` | today there is nothing to bind; a path-keyed naive implementation renders the old rank/is_best on the new content — the test asserts `analysis_run` is not reused and axes render as `gap` |
| G6 file moved | `test_catalog_stale_rows.py::test_rename_does_not_carry_analysis` | a path-keyed naive implementation rebinds by basename; asserts decisions may migrate on unique `(size,mtime)` but analysis rows never do |
| G7 file gone | `test_catalog_stale_rows.py::test_missing_file_keeps_decisions` | nothing survives today; asserts the "missing" placeholder + preserved `decision` row, no crash on `stat` ENOENT |
| G8 empty catalog | `test_catalog_restore.py::test_no_catalog_is_todays_behaviour` | must be green *and* identical: same `scan_folder` call count, same grid contents as the current path (`use_cases/folder_loading.py:88-104`) |
| G9 large folder | `test_catalog_restore.py::test_20k_pool_under_budget` | no reader exists; asserts `load_pool(20k)` ≤ 250 ms — a CI-safe **ceiling**, not the target (§9.1 measured 1.80 ms @2k; the §9.2 budget is 10 ms @5k) — and that no row is dropped silently by a cap |
| G10 privacy/no transport | `test_catalog_privacy.py::test_no_transport_imports`, `::test_paths_are_private`, `::test_no_home_literals` | the module does not exist; a copy-paste of a client helper would trip it |
| G11 one key rule | `test_content_key_single_rule.py::test_all_cache_keys_fold_size` | today `thumbnail_cache.cache_key_for` ignores size (`services/thumbnail_cache.py:31`) while `clustering._stat_key` includes it (`services/clustering.py:159-170`) — the test is **behaviour-red** on today's tree: change size with mtime fixed and the cache key must change |
| G12 single writer | `test_catalog_write.py::test_sql_only_in_gallery_catalog` | today `sqlite3` appears nowhere in `src/` (verified by grep); after C1 the AST gate asserts no other module opens a connection |
| G13 prune keeps decisions | `test_catalog_prune.py::test_prune_never_drops_decisions` | no prune exists; a naive age-based delete removes user-authored rows — the test asserts a `decision` row survives the file's `missing_since` age-out (see §5.4) |

G11 and G12 are the two gates that encode architecture rather than behaviour;
they are the ones that must survive a refactor. G5–G7 are the fail-closed
contract and are written **before** C3/C4 code (their red state is a failing
assertion against a first naive implementation, not an import error).

---

## 9. Risks / guards

### 9.1 Measured (this cell, 2026-10-21, synthetic empty files, hot cache)

Method: two ad-hoc probes run from an **uncommitted** scratch dir (not in the
repo): (a) N=2000 empty `.png` files in one dir → `scan_folder`, `stat` per file,
`json.dumps`/`loads` of the v2 snapshot shape, `GalleryItemMeta` loop;
(b) the analogue schema in §3.1 → one-transaction insert of 2 000 file rows +
2 000 membership rows, then the pool query. Median of 3 runs, `python3` 3.x
stdlib `sqlite3` 3.53.4, hot cache.

| Probe | Measured |
|---|---|
| `scan_folder()` over 2 000 files (`services/folder_scanner.py:25`) | **15.45 ms** |
| `os.stat()` per file (what a reconcile must pay too) | **14.36 ms** |
| `json.dumps` of the v2 snapshot (`use_cases/persistence.py:159-177`) | **1.53 ms** (419 KiB) |
| `json.loads` of the same | **1.29 ms** |
| `GalleryItemMeta` loop of `deserialize_session` (`use_cases/persistence.py:199-223`) | **1.06 ms** |
| sqlite: write 4 000 rows in one transaction (analogue schema) | **22.33 ms** (408 KiB DB) |
| sqlite: startup pool query, 2 000 rows | **1.80 ms** |
| sqlite: open + `count(*)` | **0.24 ms** |

Reading: a catalog read is ~8.6× cheaper than the scan it precedes, but the
scan itself is only ~15 ms here — **the catalog's payoff is preserved state,
not scan latency**. On a 2 000-file folder the whole added startup cost
(read + hydrate) is ~3 ms, which is the budget basis:

- budget: catalog read ≤ 10 ms at 5 000 rows, hydrate ≤ 5 ms, flush ≤ 50 ms
  per 5 000-row batch **off** the paint path;
- **not measured:** `_sync_from_slot` + `rebuild_grid` + per-card pixmap paint
  (needs Qt widgets/a window; `LIVE-PROOF WANTED` for C3), cold-cache
  `scandir`, and any folder on a network mount (assumption A1).

### 9.2 Startup time guard

The added work is bounded and ordered: `open()` (0.24 ms) → pool query
(1.8 ms @2k) → hydrate (the measured 1.06 ms @2k is the `GalleryItemMeta`
analogue; `GalleryItem` construction was not measured separately) → paint →
reconcile. If the read exceeds
its budget, the guard is to **paint from the catalog anyway and move the
reconcile off the first frame** — never to block the tab on the catalog. A
`[gallery-catalog]` debug line (same env-gated convention as
`src/tabs/image_gallery/debug.py:1-25`) records read/flush durations so the number
stays visible.

### 9.3 Migration of existing users

- **Nothing to migrate**: slots are in-memory (`src/core/store_workspace.py:180`), so
  the first run after this ships simply has no catalog; the empty-catalog gate
  (G8) proves that path equals today's behaviour.
- Project files: `.imgsli` v3 keeps working; `serialize_session` is not changed
  by this plan (the catalog is not part of the project format — decision Q6).
  `deserialize_session` keeps writing the slot (`use_cases/persistence.py:229`).
- The only user-visible risk is the **one-time cache miss** from C2 (§3.3):
  thumbnails re-render, AI scorecards re-query (cost/credits). Q5.

### 9.4 The two-sources-of-truth trap, and the rule that kills it

The slot and the catalog both describe the pool. Rule:

> **The slot owns the run; the catalog owns the restart. One reader, one
> writer, never both at once.**

- *Reader:* the catalog is consulted **only** in the branch where the slot has
  no items (`use_cases/persistence.py:113-141`). A non-empty slot is never merged with,
  or overridden by, catalog rows (`use_cases/persistence.py:95-112`).
- *Writer:* the catalog is written **only** from `_emit_gallery` /
  `_transact_gallery` (`use_cases/gallery_slot.py:130-188`) plus `observe_pool` at
  restore (§5.1) — the same action stream that produces the slot, so a
  disagreement means one of the two hooks is missing, not that the data
  diverged.
- *Gate:* after any action, `gallery_catalog.pool(folder)` must equal the slot's pool
  modulo terminal-status normalization (`G12` sibling assertion in
  `test_catalog_write.py`). A divergence is a bug in the write hook, never a
  reason to add a reconciliation loop.
- *Never:* a background "sync slot → catalog" loop. That is the shape that
  creates the second truth.

---

## 10. Open questions for the owner

1. **New-session behaviour.** With a known-folders registry, should a fresh
   gallery session open the last folder automatically, or show a recent-folders
   empty state? (Today: `clear_to_empty`, `use_cases/persistence.py:126-134`.)
2. **Analysis across a model change.** Keep runs per `(producer, model,
   endpoint)` and show older ones as stale, or drop them (today's cache
   behaviour is a miss: `services/ai_cache.py:3-10`)? The schema supports both; the UX
   default is not decidable from code.
3. **Retention/pruning.** Days before a missing file's row (and decisions) is
   dropped? Age for a folder to leave the registry? Row cap per folder?
4. **Ratings/labels.** Persist only what exists today (`rejected`, `is_best`,
   `crown_rank`, manual rank) or add user-facing rating/tags as a new concept?
   The `decision` table reserves `rating`/`labels`; adding UI is a product
   decision, not a schema one.
5. **Content identity cost.** Is a one-time invalidation of all five caches
   (adding `size` to the key, §3.3) acceptable? If not, the catalog keeps
   `path:mtime` and the "edited with preserved mtime" hole stays open —
   deliberately, and documented.
6. **Portability.** Should the catalog travel with an `.imgsli` project (so a
   shared project carries decisions), or stay strictly machine-local?
7. **Move detection.** Accept re-analysis after a rename (v1), or spend a quick
   content hash (first/last 64 KiB + size) to recognise moves?
8. **Data vs cache location.** `~/.local/share/ImproveImgSLI/gallery_catalog`
   (user data; survives cache cleaners) vs the existing
   `_cache_root()`/`~/.cache/ImproveImgSLI` that every gallery cache uses
   (`src/services/io/project_package.py:133-152`). Recommendation: the data dir,
   because `decision` rows are user-authored; assumption A2 says the cache root
   can be purged.

---

## Appendix — non-goals

- No second copy of the AI scorecard: `ai_cache` stays the payload store; the
  catalog stores **provenance rows + a pointer (the shared content key)**.
- No change to `serialize_session`'s slot shape or version, unless Q6 says the
  catalog travels with projects.
- No reimplementation of `scan_folder`, `filtering`, `rank_fusion`, or the
  metric-profile seam: the catalog reads their outputs.
- No remote/synced storage, no telemetry, no path reporting.
