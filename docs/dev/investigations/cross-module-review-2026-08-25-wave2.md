# Investigation: deep review wave 2 — threading, shared/services, security, video editor, tests

Date: 2026-08-25. Second review wave (five parallel passes) after
[cross-module-review-2026-08-25.md](cross-module-review-2026-08-25.md):
threading/concurrency, `shared/`+`services/` resource lifecycle,
untrusted-input attack surface, the full video_editor subsystem, and
test-quality/coverage gaps. Every finding verified against source with
file:line; intentional-by-design spots excluded. Open items are tracked in
[TODO.md](../TODO.md) ("review wave 2" sections); user-visible correctness
issues also indexed in known-bugs (private notes repo).

---

## W1. Threading / concurrency

### W1.1 Shutdown deadlock: pool drain vs unbounded GPU-marshal wait

`core/bootstrap.py:366-372` drains the app pool with
`waitForDone(2000)`; an export worker parked in
`plugins/export/services/gpu_export.py:_request`
(`payload["event"].wait()`, no timeout) waits for a GUI-thread slot that
can never run while the GUI thread is blocked in `waitForDone`. Mutual
wait → multi-second freeze on every quit during an active GPU round-trip,
then forced cleanup. Fix direction: timeout on the marshal event +
drain-before-shutdown-step ordering.

### W1.2 `os._exit` kills an export worker writing directly to its final path

`__main__.py:385` hard-exits after exec returns; queued-only
`globalInstance().clear()` does not stop running workers. Still-image
export writes straight to the chosen path (`pil_save.py:236`); the
delete-partial handler never runs when the process dies mid-encode →
truncated output file at the user's path, no error anywhere. Project
packaging is safe (tmp+replace); still-image export needs the same
atomicity.

### W1.3 EventBus is unlocked while emitted from worker threads

`core/plugin_system/event_bus.py:100-137`: `emit` rebuilds
`_subscribers[event_type]`; `subscribe` appends without a lock; worker
threads emit (`_session_controller.py:136-141`, export/recording error
paths). Interleaving loses a just-added subscriber silently. Currently
masked because handlers only re-emit Qt signals. Fix: lock around
subscribe/emit snapshot.

### W1.4 Metrics results have no staleness token

`tabs/image_compare/services/analysis/metrics.py:79-102` writes
PSNR/SSIM unconditionally on worker completion — unlike unify
(`_unification_task_id`) and cached-diff (`request_key`). Slow SSIM for
pair A landing after switching to pair B shows A's numbers; concurrent
calculations resolve last-finish-wins.

### W1.5 Dispatcher lock: two latent cracks

Verified sound today (lock spans reduce→write-back→history→subscribers),
but: `subscribe`/`unsubscribe` (`dispatcher.py:280-286`) mutate without
the lock; and any store callback dispatching synchronously deadlocks the
non-reentrant lock — currently avoided only by discipline at two sites
(`menu_controller.py:161`, `_session_controller.py:71-80` wrap in
`singleShot(0)`); `multi_compare/scene/store.py:530-596` delivers
synchronously inside the held lock. Document the contract or enforce it.

### W1.6 Smaller concurrency items

- `GpuExportProxy.shutdown()` doesn't drain queued requests; a later
  delivery recreates the offscreen widget post-shutdown
  (`gpu_export_proxy.py:50-54,192`).
- `request_cancel()` TOCTOU: cancel pressed before the worker starts is
  erased by the worker's later `_cancel_requested = False`
  (`video_export/service.py:101-103,433`).
- `processEvents()` pumped mid-render in the GPU slot and during shutdown
  (`gpu_export_proxy.py:140`, `gpu_export.py:115`) — reentrancy hazard.
- Deferred unify trigger `singleShot(50)` can set blocking flags
  (`unification_in_progress` → blocks undo) on the wrong session after a
  workspace switch (`loading.py:286,262-268`).
- ThumbnailService cancel/regenerate accounting can double-decrement
  (`thumbnails.py:412-416,115,395-401`).

Checked and SOUND: dispatcher core locking, GenericWorker pinning design,
superseded-worker guards, tile prefetcher, pyramid publish protocol,
StoreLease tokens, video render-loop pipelining (pipe-drain threads,
terminate/kill escalation), GPU marshal confinement of all QRhi work,
export save-flow cancellation events, atomic project packaging.

## W2. shared/ + services/: resources, caches, I/O

### W2.1 16-bit sources truncated mod-256 into the RGBA8 store

`tiled_pixel_store.py:206-232`: ndarray branch assigns into uint8 memmap
without scaling — uint16 JXL (imagecodecs bounded path) becomes silent
bit-crushed garbage (300→44); vips path `cast("uchar")` is plain C
truncation for ushort (`:411-412`). Channel-count case handled; dtype
case not.

### W2.2 Embedded pixel-cache lifecycle: wrong owner deletes shared files

`from_embedded_cache` wraps a file owned by the project extract cache;
`TiledPixelStore.close()` does unconditional `os.remove(path)`
(`tiled_pixel_store.py:737-746`) → closing one session deletes the
shared extracted buffer while `pixel_cache_registry._cache` still maps
the media path to it → reload of the same project in-run fails
FileNotFoundError. Needs an ownership flag or registry invalidation.

### W2.3 Truncated extract-cache members reused forever

Reuse check is `st_size > 0` (`project_package.py:404-406,446-448`);
extraction writes directly (no tmp+rename). Crash/disk-full mid-first-
load leaves a partial file every future open trusts. The catalog carries
authoritative byte counts that the check ignores.

### W2.4 Project extract cache never purged

Cache dir keyed by `<path>:<mtime_ns>` hash (`project_package.py:110-120`)
— every save changes mtime, next open extracts a full new copy; nothing
deletes old `projects/*` dirs (only spill purge exists). Multi-GB growth
per edit-reopen cycle.

### W2.5 `_uid_cache` sits outside the host-texture budget

`host_texture_cache.py:13,44-45,71-82`: `evict_over_budget` counts only
`_cache`; `_uid_cache` holds up to four whole-image QImages (~6.4 GiB
resident at 20000×20000 on top of the ~3 GiB budget). Also `image_uid`
churns fresh tags for ndarray sources (setattr rejected) → uid cache is
pure miss there.

### W2.6 Other

- `resize_images_processor` swallows resample failure and returns a
  mismatch-sized pair presented as "unified" (`resize.py:153-154`).
- `prescale.py:68-74` lacks unify's abort/OSError-fallback policy:
  disk-full during video export surfaces as raw OSError; canceled
  exports burn CPU to completion.
- Size bound checked *after* full-frame decode on the bounded path
  (`tiled_pixel_store.py:390-392`).
- `qt_conversion.pil_to_qimage_zero_copy` TypeError-fallback builds
  QImage over a local buffer with no kept reference — scanlines point at
  freed memory once returned (`qt_conversion.py:56-74`).
- Clipboard temp artifacts never reclaimed; URL paste loads body into RAM
  unbounded; `file://` paste drops percent-decoding
  (`clipboard_images.py:36,53-57,84-97`).
- Bare `except:` at `progressive_loader.py:302`; unbounded
  `ProgressiveImageLoader._full_cache`.

Checked and SOUND: spill-dir lifecycle (QLockFile, fallocate preflight,
cleanup on all failure paths), pyramid build math, TileTextureService
LRU/accounting, project-zip atomicity, recent_projects hardening,
windows_file_association, regions/tile geometry guards.

## W3. Untrusted input (desktop-calibrated)

Threat: malicious `.imgsli`/image files shared between users. No code
execution found; crash/DoS/resource issues below.

- **W3.1** `pixel_cache` width/height from project.json go straight into
  `np.memmap(shape=(h,w,4))` with truthiness-only validation and no file-
  size check (`project_io.py:324-327`, `pixel_cache_registry.py:12-13`,
  `tiled_pixel_store.py:182-183`) → crafted project crashes the app
  (SIGBUS on Linux) on open; also bypasses MAX_SUPPORTED_IMAGE_DIMENSION.
  Fix: clamp dims + verify `st_size >= w*h*4`.
- **W3.2** No decompression caps anywhere in the zip pipeline: per-member
  extraction (`copyfileobj`) and whole-member RAM reads
  (`read_project_json_from_zip`, preview bytes, GNOME thumbnailer) are
  unbounded — a ~10 MB project can expand to hundreds of GB; thumbnailer
  triggers on directory listing.
- **W3.3** Legacy v1 projects resolve arbitrary absolute paths from the
  file — on Windows a UNC reference (`\\host\share\a.png`) triggers
  automatic SMB credential exchange on mere open.
- **W3.4** Zip-slip guard uses string-prefix `startswith` without
  separator (`project_package.py:400-403,441-444`) — sibling-dir escape
  possible in principle; replace with `is_relative_to`.
- Minor: `encoding.py:18` falls back to CWD-relative ffmpeg binary;
  `manual_args` positional append lets a `-`-leading output filename parse
  as an option; `shlex.split` mangles Windows backslash paths.

Checked and SAFE: no extractall/symlink materialization; comment metadata
(PIL-framed, no format-string path); zero shell=True/os.system across the
tree (ffmpeg argv-list, stdin-fed); no pickle/yaml; plugin discovery scans
install tree only (no user-writable auto-import); recents rendering
argument-interpolated; image previews through hardened Qt loaders;
pyvips streaming size-bypass documented as accepted risk (AGENTS.md).

## W4. Video editor subsystem

- **W4.1 [critical]** `VideoProjectModel` is `@dataclass(frozen=True)`
  (`model.py:55-56`) but mutated directly at ≥9 sites (`set_resolution`,
  preview scale/dimensions, fps/aspect, container, bootstrap). Verified
  live: `FrozenInstanceError` raised inside Qt slots is swallowed →
  source resolution is *silently never applied*, dialog always shows
  1920×1080 (`bootstrap.py:37-41` catches-and-logs). Drop `frozen=True`
  or route everything through `replace()`.
- **W4.2** Stale global-bounds race: `recalculate_global_bounds`
  early-returns while a previous calculation is in flight; the result
  computed from pre-edit snapshots is installed with no reschedule
  (`preview.py:633-656`, `playback.py:107-113`). Needs a generation
  counter (same shape as `_render_task_id`).
- **W4.3** Presenter leaked per dialog open/close: connects to long-lived
  controller signals, `cleanup()` never disconnects, parentless QObject
  never deleteLater'd (`presenter.py:122-128,225-237`) — pools/timers
  accumulate; stale handlers fire on every future export.
- **W4.4** Cancel/failure leaves the partial output file
  (`service.py:475-484`); frame drops are silent (`render_loop.py:117-119`)
  and progress hits 100% before finalize verifies exit code
  (`render_loop.py:154-155`).
- **W4.5** Duplicate channel evaluator in timeline callbacks diverges
  from `evaluate_channel` on exact-keyframe hits
  (`widgets/timeline/app_callbacks.py:54-69` vs `keyframing/engine/values.py:324-347`)
  — delegate instead of keeping two implementations of one contract.
- Also: mixed int/float scalars fall back to hold instead of lerp
  (`values.py:432-451`); notification thumbnail tempfile never deleted;
  GUI-thread blocking fallback render on prepare-error
  (`preview.py:527-547`); hardcoded English strings bypassing `tr()`
  (runtime.py:185, shell.py:428, export_flow.py:151); settings persisted
  on every keystroke (`persistence.py:84-97`); recorder toggle stuck if
  stop() raises (`recording_flow.py:42-44`).
- Checked and SOUND: PreviewCoordinator request-id guarding (checked
  before apply AND in finish), prepare-key fingerprinting, keyframe
  engine interpolation edge cases, snapshot immutability/undo isolation,
  ffmpeg process escalation ladder, thumbnail bookkeeping guarantees,
  blockSignals discipline.

## W5. Test quality — what can silently break

| Invariant | Coverage | Gap |
|---|---|---|
| Dispatcher thread-safety (ARCHITECTURE.md claim) | **NONE** | removing the lock fails nothing |
| MC residency rekey-on-swap | none (IC has direct tests) | MC blank-frame regressions pass green |
| `drop_covered_fallback_tiles` (MC) | **ZERO tests** | double-draw/z-fighting undetected |
| Letterbox focus preservation | IC only | MC owns its own projection stack, unenforced rule |
| Reducer purity sweep | ~6 actions, one action's I/O check | MC actions unchecked |
| Project-I/O negative paths | happy paths only | corrupt-ZIP/zip-slip/unwritable-dir branches written but never executed |

Fake drift: `_Store` fake special-cases the document slot differently
than the real workspace store (would miss misdirected restores);
video-preview `_FakeCombo/_FakeSettingsManager` over-mock real widget
semantics. Flaky classes beyond the 4 known failures: single-drain exact-
geometry asserts (~6 more candidate files), grab()-pixel asserts, strict
palette-equality asserts — recommend a bounded drain-until-stable helper
instead of per-test fixes. Seven assertion-free smoke tests found.

Top recommendations: (1) MC residency parity tests, (2)
`drop_covered_fallback_tiles` direct tests, (3) concurrent-dispatch test
pinning the thread-safety claim, (4) project-I/O negative paths, (5)
deflake-by-construction helper, (6) corrupt-ini graceful-load test, (7)
widen reducer purity sweep to all action types, (8) one real-widget
integration anchor for the video-preview fakes.

---

## Resulting rules

1. Exit-time rule: nothing may hard-exit while workers hold write handles
   to user files; still-image export gets tmp+replace like project
   packaging.
2. Every async result that lands in visible state carries a staleness
   token (metrics is the last unguarded pipeline).
3. Files extracted from containers are owned by their extractor; stores
   wrapping them must be read-only tenants (ownership flag).
4. All dimensions/byte-counts read from project files are clamped against
   declared constants and verified against actual file sizes before use.
