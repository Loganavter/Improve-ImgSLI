# Settings persistence

Where user settings live, how they are loaded and saved, and why the save
path is shaped the way it is (single full-snapshot writer). Also a
troubleshooting guide for "my settings randomly reset".

Related: [CONTRACTS.md](CONTRACTS.md) (Dogma 4 — apply path uses a single
full-snapshot writer; Dogma 5 — mutation service requires a key),
[STORE.md](STORE.md) (the Store the snapshot is taken from),
[LOGGING.md](LOGGING.md) (`[settings]` debug lines),
[ARCHITECTURE.md](ARCHITECTURE.md) (bootstrap order).

## The file

| What | Where |
|---|---|
| Settings file | `~/.config/improve-imgsli/improve-imgsli.conf` (Qt `QSettings("improve-imgsli", "improve-imgsli")`, INI format) |
| Backup | same path + `.backup` — refreshed after every full save; heals a truncated file at startup |
| Format | flat keys in `[General]` (plus `[multi_compare]` and per-plugin groups) |

`SettingsState` (`src/core/store_settings.py`) is the in-memory authority;
the file is a derived serialization of it, not a second source of truth.

## Load path (startup)

1. `ApplicationContext.initialize()` configures logging **before** the
   persistent state is loaded (see below why the order matters), then calls
   `_load_persistent_state()` (`src/core/bootstrap.py`).
2. `SettingsManager.load_all_settings(store)` reads every key with an
   explicit type (`_get_setting`) and fills the Store. Canvas-feature and
   tab-owned settings are loaded through the same pass.
3. If the file exists but is missing the critical keys (`language`,
   `theme`) and a `.backup` exists, the backup is restored first
   (`_restore_backup_if_corrupt`) — covers a kill mid-save leaving a
   truncated INI.

Logging is configured before the load so the `[settings]` diagnostics are
actually emitted — the previous order (logging last) silently dropped every
load-time line.

## Save paths

There is exactly **one** writer for settings-file content: a **full
snapshot of the Store** (`save_all_settings(store)`), taken from:

1. **Window shutdown** — `PersistWindowStateStep` (`src/ui/main_window/lifecycle.py`), after the window geometry is written into the Store.
2. **Quick export** — `image_export/state.py` persists the export options block.
3. **Settings dialog apply** — `SettingsApplicationService.apply()` mutates the Store via dispatches, then `_schedule_persist()` → `SettingsManager.schedule_persist(store)` — a debounced (150 ms, coalesced) full snapshot, so an OK click survives even if the app never shuts down cleanly.

Every full save ends with `QSettings.sync()` + `_refresh_backup()`.

### Why no incremental writes

`apply()` used to write individual keys immediately
(`manager._save_setting(key, value)` per changed field). The settings
dialog's widgets can drift from the Store (the dialog can be hidden and
re-shown — Find Action member path — and `sync_from_store` must cover
every control `get_settings()` reads back). A stale widget then silently
overwrote a good value with its default — the observed "random settings
reset" (`ui_mode` → beginner, `ui_scale_factor` → widget default,
`rhi_backend` → default, written on a settings OK with no log).

The fix was structural: **apply-path code may not call the incremental
writer at all**; the file is only ever written as a coherent snapshot, so
it always equals the Store. `_save_setting` remains only for direct
single-key writers outside the apply path (video-editor dirs/favorites,
first-run flag) whose value is simultaneously stored in the Store — the
snapshot then re-writes the same value and cannot clobber it.

Contract tests encode this: `tests/contracts/test_settings_persistence_contract.py`
(Dogma 4a — no `_save_setting` in apply methods; Dogma 4b — `apply()` must
call `_schedule_persist`). See [CONTRACTS.md](CONTRACTS.md).

## The dialog apply flow

1. OK (or Find Action member activation) → `settings_confirmed` →
   `SettingsApplicationService.apply(data)`.
2. Each `_apply_*` method dispatches `Set*Action` into the Store (the
   store is the only thing mutated).
3. `apply()` ends with `_schedule_persist()` — the debounced full snapshot.
4. `show_settings_dialog` → `sync_from_store()` re-seeds every control
   `get_settings()` reads back (checkboxes, UI-mode radios, scale slider,
   rhi combo) so a reused dialog cannot drift.

## Adding a new persisted setting

The contract tests (`tests/contracts/test_settings_persistence_contract.py`)
verify the rules below mechanically — a new field that skips a step fails
the suite (typed loads, load⇄save full-pass pairing, store coverage, apply
path). Pick the case that matches:

### A. A user preference changed from the Settings dialog

1. **Add the field to `SettingsState`** (`src/core/store_settings.py`) with a
   sensible default — this is the in-memory authority.
2. **Typed load** in `load_all_settings`
   (`src/plugins/settings/manager.py`):
   `s.my_field = self._get_setting("my_field", <default>, str)` — the type
   must be one of `str | int | float | bool` (no implicit formats).
3. **Save** in `save_all_settings`: one `self._save_setting("my_field", ...)`
   line. This is the full-snapshot writer — the load/save pairing is what
   the "full-pass" contract test checks.
4. **Apply path**: create a `SetMyFieldAction`, dispatch it inside the
   relevant `_apply_*` method of `SettingsApplicationService`
   (`src/plugins/settings/application_service.py`). Do **not** call
   `_save_setting` there — Dogma 4 forbids incremental writes in the apply
   path; the debounced `_schedule_persist()` at the end of `apply()` writes
   the snapshot, so the Store change reaches the file automatically.
5. **Dialog seeding**: if the control can survive a hide/re-show, extend
   `sync_from_store()` to re-seed it from the Store (the mode radios, scale
   slider and rhi combo are the precedent — a control `get_settings()`
   reads back must track the Store, or a stale widget silently overwrites
   the value on the next OK).

### B. A value written from outside the dialog (direct single-key writer)

Video-editor dirs/favorites, first-run flag, last-seen version: mutate the
Store field **and** call `manager._save_setting(key, value)` with the same
value. The Store copy is what the next full snapshot writes back — if the
Store never holds the value, the next snapshot clobbers the direct write
with the Store default.

### C. A structured blob (e.g. `keyboard_overrides`)

Give it a dedicated helper pair `_load_<name>` / `_save_<name>` in
`SettingsManager`, wire both into the master load/save passes, and declare
the field in `JSON_PERSISTED_STORE_SETTINGS`
(`tests/contracts/_framework.py`) with a one-line reason.

### D. Genuinely runtime-transient value

Declare it in `TRANSIENT_STORE_SETTINGS` (`tests/contracts/_framework.py`)
with a reason. The contract fails for any *other* uncovered field, so an
undeclared field is caught at test time, not by a user's settings reset.

### Verify

`./launcher.sh test tests/contracts -q` (typed-load, full-pass pairing,
store coverage, apply-path dogmas) plus a roundtrip check — apply → wait
the persist debounce → restart → the value survives.

## Debug instrumentation

With `--debug` (or `IMPROVE_DEBUG=1`), `~/.local/share/ImproveImgSLI/log.txt`
contains:

```
[settings] SettingsManager init file=… backup=…
[settings] health check: file=… keys=89 backup=True
[settings] load_all_settings START caller=… keys_in_file=89
[settings] load_all_settings DONE theme=… language=… ui_mode=… window=…
[settings] save_all_settings START caller=… store_digest=theme=… language=… ui_mode=… rhi_backend=…
[settings] save_all_settings DONE keys_in_file=89 backup=…
[settings] skip saving <key> (None) caller=…
```

`caller=` is the nearest call chain, so every load and every save is
attributable. `keys_in_file` on load reveals a file that was wiped or
partially overwritten before startup.

## Troubleshooting a "random settings reset"

1. Open `~/.local/share/ImproveImgSLI/log.txt` (the run that observed the
   reset — log.txt is overwritten each start, so reproduce first).
2. **Load side**: `load_all_settings START … keys_in_file=…` — a small
   count or `restored from backup` means the file was already broken at
   startup (previous session crashed mid-save; check the previous run's
   `save_all_settings` line).
3. **Save side**: `save_all_settings START … store_digest=…` — if the
   digest shows defaults (`ui_mode=beginner`, `window=1024x768`,
   `rhi_backend=default`) for a value you know you changed, the Store
   itself was default — look at the `caller=` chain and whether a second
   app instance (or an offscreen/headless run) wrote over the file.
4. If a save is missing entirely from the log, the writer was not one of
   the three save paths — check for direct `_save_setting` callers
   (`rg "_save_setting" src`) and for processes running without `--debug`
   (their log overwrote the previous one).
