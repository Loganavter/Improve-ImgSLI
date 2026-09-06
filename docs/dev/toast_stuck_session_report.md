# Session report: stuck loading toast — from dead manager to leaked inflight alias

Date: 2026-09-05. Branch: `feat/toast-cleanup` (built on `feat/toast-host-owned`).
Area: loading-toast lifecycle, both canvas tabs (`src/tabs/_shared/`, IC pyramid/decode pipeline).
Related: [plan_toast_refactor.md](./plan_toast_refactor.md), [plan_toast_cleanup.md](./plan_toast_cleanup.md), [plugins/layout.md](./plugins/layout.md), [LOGGING.md](./LOGGING.md), [tabs/capability-mechanisms.md](./tabs/capability-mechanisms.md), internal-docs `bug-a1-multi-compare-load-silently-skips`.

## Symptom

Two user-visible complaints, one session:

1. Toasts never appear at all (save, loading, metrics).
2. After (1) was fixed: loading toast progress reaches pyramid stage, then hangs forever ("прогресс вроде закончился, а вроде и застрял").

## Root cause 1: toast manager is None forever (fixed)

`LayoutPlugin.setup_ui_reference` (`src/plugins/layout/plugin.py:32`) creates the tab-owned
`layout_manager` exactly once via `create_startup_service("layout_manager", …)`. The sole provider
(`ImageCompareTab`, `src/tabs/image_compare/service_factory.py:98`) returns `None` while
`tab._widget` is unset — and at setup time only the `session_picker` page exists (lazy pages,
`src/tabs/use_cases/pages.py:19-34`, `tabs/background-tab-policy.md:21-25`). No retry exists, so
`window.toast_manager` stays `None` forever; every consumer degrades silently by design
(capability-mechanisms.md Policy rule 1). Proven by prod log:
`save_flow.py:130 "Toast manager unavailable; continuing export without toast UI"`.
Docs cross-check confirmed the diagnosis and the sanctioned shape (lazy `image_canvas` precedent,
`layout_manager` known gap for MC/SP).

Fix (`feat/toast-host-owned`): host-owned `ToastManager(parent_window)` in `LayoutPlugin`
(anchor optional per toolkit `FEEDBACK_API.md`), anchor repoint stays in
`Ui_ImageComparisonApp.sync_session_mode`; toast creation stripped from
`ImageCompareLayoutManager`. All per-tab getters kept as-is — their `None`-guards simply
stopped triggering. Same session also routed MC silent load failures through
`CoreErrorOccurredEvent` (internal-docs bug-a1).

## Root cause 2: leaked `(slot, path)` inflight alias suppresses pyramid→toast mapping (fixed)

With the manager alive, paired-slot toasts still hung. `[toast-debug]` tracing (temporary,
`IMGSLI_TOAST_DEBUG`, removed after verify per LOGGING.md) showed pyramid builds completing
with `NO slot mapping`: `start_pyramid_builds` (`loading_pyramid.py:75`) passed `slot_id=None`
because `_has_inflight_for_slot` saw "decode in flight" — while Unify had finished 10 ms earlier.

The stale entries were `(slot, path)` aliases: `slot.py:696` `setdefault`s them into the shared
`pipeline._inflight` dict on the `ImageLoadService` path, but only the legacy fallback path ever
popped them (`_clear`). The service cleaned only its own `path+mtime+box` key on completion, so
the alias leaked with a live signal forever — every later pyramid start for that slot skipped
the `uid→slot` mapping, and paired slots have no other finish path (unpaired rescue +
decode-land progress only; finish lives exclusively in pyramid `complete`).

Fix: `ImageLoadService._on_result`/`_on_finished` pop the alias via `_pop_alias()` (same-dict +
pipeline-dict, only if the entry is still ours). Verified live:
`pyramid start: slot=1 toast_live=True` → `finish: slot=1 … DONE`.

## Root cause 3 (found by the same trace): no terminal for decode-after-pyramid order (fixed)

One run showed the flip side: slot 2's full decode was *genuinely* still in flight at pyramid
start (`toast_live=False` — correct), the pyramid built from the already-streamed store and
completed unmapped, and nothing ever finished the toast when the decode landed. Paired slots
had no decode-completion finish by design.

Fix: `PyramidBuildCoordinator.start_build` gained `toast_live: bool = True` — the `uid→slot`
mapping is now always recorded (keep-first), while progress bumps and skip-path finishes still
honor liveness (preview-tier race protection preserved). IC caller always passes the slot;
MC callers unchanged (never suppressed). Same-image-both-slots keeps the first mapping
(rare, documented in code).

## Self-inflicted bug caught by the trace (fixed)

First version of `_pop_alias` called `toast_debug` without importing it. The `NameError` fired
*after* the silent pop, propagating out of `_on_result`/`_on_finished` and skipping
`controller._on_image_loaded` / `on_full_load_finished`. Fixed by adding the import; lesson:
temporary diagnostics must never sit on the result-delivery path without a test exercising it.

## Cleanup (recon → orchestration, 4 + 3 agents)

Parallel recon inventoried the whole toast plane: 9 sticky-toast paths without guaranteed close,
~250 LOC prod-dead `if coord is None` fallbacks kept for `SimpleNamespace` fakes, a 3-deep save
delegation chain (~70 LOC pure forwarding), overlapping state maps, write-only `_save_workers`,
ghost keys, and toolkit-side defects (`close()` without `deleteLater` → every toast leaks;
redundant per-tick progress path; broad `except pass` on anchors).

Executed on `feat/toast-cleanup` (plan_toast_cleanup.md):
- Phase A: guaranteed close on abort/stalled/in-flight/cancel/error orphans (+15 tests).
- Phase B: −606 LOC (fallbacks, `pyramid_build_task` translator, Layer-2 forwards, ghost field;
  fakes rewritten to inject coordinators).
- Phase C (toolkit repo, branch `feat/toast-lifecycle`, unmerged — needs PR): destroy-on-close,
  `content=None` progress fast path, `isValid` anchor guards, 4.2.4 + CHANGELOG.
- Verify: 1021+ passed; failures/contracts limited to pre-existing sets (proven via stash reruns).

## Leftover / follow-ups

- `[toast-debug]` instrumentation removed in full (this commit); no `IMGSLI_TOAST_DEBUG` references remain in `src/`.
- App progress paths → `content=None` fast path: blocked on toolkit Phase C landing.
- `.jxl`/accept-list unification, IC `ui_mode` race, `display_path_style`, ghost keys,
  `AbortSignal` unification: tracked in plan_toast_cleanup.md §5.
- Phase 5 manual verify (export/cancel/corrupt-drop/tab-switch, zero `"Toast manager unavailable"`):
  done by reporter for the paired-slot hang; full matrix still open.
