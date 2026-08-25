# Investigation: orchestration 6-agent rework — ImportError `_STATE_SLOT`, haltura audit and registry stale

## Status: Done (2026-08-25)

6-agent orchestration gave топорные prompts without `improve-imgsli-internal-docs` reporting standard. One agent (security) returned empty. Regression: `tests/runtime/test_session_rehydrate.py:13` imports `from tabs.multi_compare.tab import _STATE_SLOT` but `src/tabs/multi_compare/tab.py:10` never re-exported it (real owner `src/tabs/multi_compare/use_cases/persistence.py:24`). `pytest` → `ImportError: cannot import name '_STATE_SLOT'`. `docs/dev/file_size_registry.json:1` stale after size-changing edits. This audit fixes the regression, re-syncs registry and audits whether other agents' claims match `docs/dev/TODO.md:22` and `docs/dev/investigations/cross-module-review-2026-08-25.md:1` / `cross-module-review-2026-08-25-wave2.md:1`.

References: `improve-imgsli-internal-docs/.cursor/skills/internal-docs-hygiene/SKILL.md:1` (paths mirror public repo, investigation format, privacy boundary `4bcc276a`), example `improve-imgsli-internal-docs/docs/dev/investigations/image-compare-first-activation-flicker-and-qrhi.md:1` (Trigger → Root cause → False leads → Fix → Files changed → Testing).

## Trigger

- After splitting `src/tabs/multi_compare/tab.py:1` into thin-owner + `src/tabs/multi_compare/use_cases/persistence.py:1`, `_STATE_SLOT = "multi_compare.state"` moved to persistence but `tab.py:13` kept only `from tabs.multi_compare.use_cases import persistence` without re-export. Test harness `tests/runtime/test_session_rehydrate.py:13` still `from tabs.multi_compare.tab import _STATE_SLOT, MultiCompareTab`.
- `PYTHONPATH=src pytest -q` → `ImportError: cannot import name '_STATE_SLOT' from 'tabs.multi_compare.tab' (src/tabs/multi_compare/tab.py:1)` — blocks entire runtime suite (collect-only passes, import fails).
- `python src/devtools/file_meta.py --check` → mismatches for `src/services/io/project_package.py:1` (549→621) and `src/shared/image_processing/tiled_pixel_store.py:82` (923→937) after concurrent edits.
- Need to verify other 5 agents didn't stub `TODO.md` P1/P2 items.

## Root cause

1. **Re-export omitted** — `tab.py:11` preserved `from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _IMAGE_EXTENSIONS` (single source per `src/shared/image_extensions.py:10`, C9 divergence fix) but `use_cases/persistence.py:24` was not mirrored. `grep -rn "from tabs.multi_compare.tab import _STATE_SLOT"` had exactly one consumer (`tests/runtime/test_session_rehydrate.py:13`); no contract test enforced the re-export (tab-sandbox scans `src/ui/` only, see C-section `cross-module-review-2026-08-25.md:137`).
2. **Registry stale** — `src/devtools/file_meta.py:163` `write_registry()` not run after edits that grew `project_package.py:1` (+70 lines atomic extract + purge), `tiled_pixel_store.py:206` (+16-bit fix), `tab.py:1` (+1 line), and background-tab gating `src/tabs/image_compare/use_cases/chrome_sync.py:1` (+~100), `widget.py` etc. `file_size_registry.json:2` still carried old `lines`.
3. **Orchestration halturn** — prompts lacked `internal-docs-hygiene` investigation skeleton, so agents optimized for diff count not verification. Security workstream did zero commits (empty report); concurrency and clipboard/prescale left gaps.

## False leads (what was tried)

1. **Check if `_STATE_SLOT` should stay private** — inspected `src/tabs/multi_compare/tests/runtime/test_session_state_slot_isolation.py:10` and siblings: all internal tests import from `tabs.multi_compare.use_cases.persistence` directly. Only the public `tests/runtime/test_session_rehydrate.py:13` goes through `tab.py`. Avoided duplicating constant; chose re-export to keep single truth while unblocking public test contract.
2. **`from tabs.multi_compare.use_cases.persistence import _STATE_SLOT` vs `__all__` dynamic** — considered `persistence._STATE_SLOT` attribute access; explicit import is what test expects and matches history before split (direct symbol).
3. **Registry auto-fix by file_meta scan threshold** — `file_meta.py:121` only tracks oversize+marker. Three new oversize files `src/tabs/image_compare/use_cases/chrome_sync.py:538`, `src/tabs/image_compare/widget.py:584`, `src/ui/actions/palette/dialog.py:534` lack `Audit-Meta:` but are not in registry (correct per tool). `test_oversized_files_have_audit_meta` still fails — deferred as separate file-size policy violation, not registry staleness. Not auto-adding markers here (would hide policy debt).
4. **Full `pytest -q` without offscreen** — Wayland + QRhi requires `QT_QPA_PLATFORM=offscreen`; direct run hangs. Switched to `QT_QPA_PLATFORM=offscreen PYTHONPATH=src pytest --collect-only` for smoke, then targeted `tests/runtime/test_session_rehydrate.py` and `tests/contracts/test_file_size_policy.py`.

## Fix

- `src/tabs/multi_compare/tab.py:10` — added `from tabs.multi_compare.use_cases.persistence import _STATE_SLOT` after `ACCEPTED_IMAGE_EXTENSIONS` line, preserving `shared.image_extensions` import. Verified `grep -rn "from tabs.multi_compare.tab import _STATE_SLOT"` now resolves and `PYTHONPATH=src python -c "from tabs.multi_compare.tab import _STATE_SLOT"` succeeds (`multi_compare.state`).
- `docs/dev/file_size_registry.json:1` — regenerated via `python src/devtools/file_meta.py --write-registry` (42 entries, 621/937 line counts). `python src/devtools/file_meta.py --check` → `Registry OK`.

## Files changed

| File | Change |
|------|--------|
| `src/tabs/multi_compare/tab.py:11-14` | Re-export `_STATE_SLOT` from `use_cases.persistence` while keeping `from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS` |
| `docs/dev/file_size_registry.json:1` | Regenerated via `file_meta.py --write-registry` (project_package 549→621, tiled_pixel_store 923→937, 42 entries) |
| `docs/dev/investigations/audit-2026-08-25-orchestration-halture.md:1` | This investigation (internal-docs format, host-level `docs/dev/` per hygiene skill) |

No other source edits in this audit pass; pending worktree fixes (dispatcher, gpu_export, project_package, etc.) are inventoried below as prior agents' work.

## Testing

- `grep -rn "from tabs.multi_compare.tab import _STATE_SLOT" tests/` → `tests/runtime/test_session_rehydrate.py:13` now resolves.
- `PYTHONPATH=src python -c "from tabs.multi_compare.tab import _STATE_SLOT, MultiCompareTab; print(_STATE_SLOT)"` → `multi_compare.state`.
- `PYTHONPATH=src python src/devtools/file_meta.py --write-registry` → `Wrote ... (42 entries)`; `--check` → `Registry OK`.
- `QT_QPA_PLATFORM=offscreen PYTHONPATH=src pytest tests/runtime/test_session_rehydrate.py -q` → `2 passed` (qapp).
- `QT_QPA_PLATFORM=offscreen PYTHONPATH=src pytest tests/contracts -q` → `1473 passed, 2 skipped, 4 failed` — remaining failures are pre-existing policy/arrow-key tests (`test_file_size_policy.py:47` oversize, `test_no_arrow_key_redirection.py:103`), not ImportError; `QT_QPA_PLATFORM=offscreen pytest --collect-only` succeeds (ImportError gone).
- `wc -l src/tabs/multi_compare/tab.py` 372→373 (splitlines 373, wc 372 due to missing trailing newline — file_meta uses splitlines, hence registry stable after write).

## Audit: заявлено vs реально (TODO.md vs git diff)

### P1 Cross-tab failure surfacing (`TODO.md:22`, A1–A3,C9) — **Done, not халтура**

- Заявлено: MC log-only → `CoreErrorOccurredEvent`, video export re-raise, `.jxl` unified, `print()` removed.
- Реально: `src/tabs/multi_compare/use_cases/loading.py:16,27` `_emit_mc_load_error` + `event_bus.emit(CoreErrorOccurredEvent)` (22 lines, `read_image:44`, `on_full_resolution_error:220`); `src/tabs/image_compare/plugins/video_editor/services/video_export/service.py:469` now `raise` after log; `src/shared/image_extensions.py:10` single source, `mc/ui/drag_drop.py:21`, `ic/use_cases/drag_drop.py:12` both `from shared.image_extensions`; `src/ui/actions/widget_pulse.py:1` zero `print(`. Git diff vs HEAD shows already committed (periodic backup `df92949f`), so pending diff doesn't list it — verifier must read file, not just `git diff HEAD`.

### P1 Shutdown / pixel correctness (`TODO.md:49`, W1–W2, W4.1) — **Mostly done, 2 gaps**

- `src/tabs/image_compare/plugins/video_editor/model.py:56` `VideoProjectModel` now `@dataclass` (was `frozen=True`) — live `FrozenInstanceError` eliminated, `set_resolution:73` mutates.
- `src/shared/image_processing/tiled_pixel_store.py:226` `_to_u8` scales `uint16 >>8` not mod-256; `pyvips` path `img /257 .cast("uchar")` `tiled_pixel_store.py:427`.
- `src/core/bootstrap.py:356` `shutdown` drains `thread_pool.waitForDone(2000)` before lifecycle, comment references `gpu_export.py:_request`.
- `src/shared/image_processing/pil_save.py:215` still-image export tmp+replace atomic (project packaging already had it).
- Gaps: **`src/tabs/image_compare/plugins/video_editor/presenter_parts/preview.py:633` stale global-bounds generation counter not fully ported** (relies on `request_id` guard only for render, not for `recalculate_global_bounds` early-return without reschedule — W4.2 partial). **`src/plugins/export/services/gpu_export.py:18` / `gpu_export_proxy.py:51` shutdown drain is in uncommitted worktree** (`git diff HEAD` shows `_shutting_down` flag, `disconnect`, `processEvents` removal) — correct but not yet committed, so `df92949f` HEAD still has deadlock risk.

### P2 Concurrency / resource lifecycle (`TODO.md:106`) — **Worktree correct but uncommitted → халтура по процессу**

- `src/core/plugin_system/event_bus.py:40` `_lock = threading.Lock()` + `emit:100` snapshot under lock — correct.
- `src/core/state_management/dispatcher.py:116` class doc about no-sync-dispatch, `subscribe:291`/`unsubscribe:294` under `with self._lock`, `list(self._subscribers)` copy — pending diff, not in HEAD.
- `src/tabs/image_compare/services/analysis/metrics.py:18` `_metrics_request_id` staleness token — pending.
- `src/shared/rendering/host_texture_cache.py:59` `evict_over_budget` now sums `_uid_cache` — pending.
- `src/shared/rendering/image_identity.py:21` fallback no longer churns counter for ndarray — pending.
- `src/shared/image_processing/resize.py:153` now `raise RuntimeError` instead of returning mismatched pair — pending.
- `src/shared/image_processing/prescale.py:28` `should_abort` + OSError fallback — pending.
- `src/services/io/project_package.py:376` `_is_within_directory` via `is_relative_to`, `_atomic_extract_member` tmp+rename, size verify, `purge_old_project_caches` — pending (621 lines, `Audit-Meta` added).
- **Missing**: `src/shared/clipboard_images.py:36,79` still no percent-decode (`file://`), unbounded `response.read()` (W2.6), temp-file leak; `src/shared/image_processing/tiled_pixel_store.py:737` `from_embedded_cache` ownership flag not added (close deletes shared extract cache) — W2.2 unaddressed.

### P2 Security (untrusted-input) (`TODO.md:81`, W3) — **Халтура: empty report confirmed**

- `src/services/io/project_io.py:323` **is fixed** for W3.1 clamp + `st_size >= w*h*4` (`project_io.py:356-374`) — contradicts empty-report claim but present in HEAD (periodic backup). Likely another agent backfilled after security empty, but not attributed.
- Still open: per-member/cumulative decompression caps (W3.2) — `project_package.py:404` `copyfileobj` unbounded, `read_project_json_from_zip:373` whole-member RAM, GNOME thumbnailer; legacy v1 absolute/UNC path prompt (W3.3) — `project_io.py:390` resolves without warn; CWD-relative ffmpeg fallback `encoding.py:18`, `-` filename option, `shlex.split` backslash (minor) — not touched.

### P2 Background-tab render gating (`TODO.md:172`, `tabs/background-tab-policy.md`) — **Done, but file-size policy халтура**

- Commit `c6a0edde` (8 files, 433 ins): `src/tabs/image_compare/use_cases/chrome_sync.py:141` visibility gate, `render_flow.py:72` stale defer, `tab.py:19` `on_activated` flush, `widget.py:114` defer, `multi_compare/tab.py:50` + `canvas_widget.py:83` MC gate, metrics defer. Mirrors `appearance.py` stale-flush, no new machinery — per TODO phases.
- **Gap**: `chrome_sync.py:538`, `widget.py:584`, `ui/actions/palette/dialog.py:534` now over 500 without `Audit-Meta:` — `tests/contracts/test_file_size_policy.py:47` fails (3 violations). Registry regenerated but violations remain — needs `Audit-Meta: pattern=... reason=...` or split.

### P2 Contract-test blind spots (`TODO.md:192`) — **Not started**

- Scanners still narrow (`legacy_tab_widgets` only, etc.) — no diff. Expected widen first, then fix `project_preview.py:91`, `platform.py:83`, `__main__.py:366`, `session_picker/tab.py:59`, `keyboard.py:199` — only `keyboard.py:199` hardcoded branch removed (`df92949f` shows 8-line change), rest partial.

## Unclosed gaps (where agents халтурят — требует доделки)

1. **Security caps** — add `DecompressionBomb` limits to `project_package.py:404` / `project_io.py:373` / thumbnailer; UNC warning for v1 projects; `is_relative_to` already done for `project_package` but verify `project_package.py:441` second site.
2. **Embedded pixel-cache ownership** — `tiled_pixel_store.py:737` `close()` must not `os.remove` when `from_embedded_cache` (add `owned_by_cache` flag or `pixel_cache_registry.invalidate` on close per `TODO.md:124`).
3. **Clipboard hardening** — `clipboard_images.py:36` `urllib.parse.unquote` for `file://`, `clipboard_images.py:79` cap `response.read( max_bytes )` + size header check, delete `clip_*.png` / `url_image_*` on consume.
4. **Commit pending worktree** — `dispatcher.py:116`, `gpu_export*.py`, `project_package.py`, `metrics.py`, `host_texture_cache.py`, `resize.py`, `prescale.py`, `image_identity.py` are correct but unstaged; need commit + `file_size_registry.json` already re-synced (confirm after commit line counts: `project_package.py:621`).
5. **File-size markers** — add `Audit-Meta: pattern=state-machine reason=...` to `chrome_sync.py:1`, `image_compare/widget.py:1`, `ui/actions/palette/dialog.py:1` or split per `CODE_PATTERNS.md` (thin-owner + `use_cases/`), then `--write-registry`.
6. **Preview global-bounds generation** — `preview.py:633` add counter like `_render_task_id` to drop stale early-return result and reschedule.
7. **Presenter leak** — verify `presenter.py:130` `_disconnect_service_signals` is called on every `cleanup()`/`deleteLater` path (W4.3 fix appears in tree but not in HEAD diff — ensure committed).
