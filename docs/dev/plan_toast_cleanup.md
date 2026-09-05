# Plan: toast lifecycle cleanup (close-leaks + legacy removal + toolkit fix)

Status: `Done` — A+B merged+verified on `feat/toast-cleanup` 2026-09-05 (−606 LOC, 15+38 leak/close tests green); C ready as toolkit branch `feat/toast-lifecycle` (4.2.4, unmerged — needs PR per toolkit rules); `[toast-debug]` removal + app `content=None` adoption pending manual verify
Area: `src/tabs/_shared/loading_toast.py:1`, `src/tabs/_shared/pyramid.py:1`, `src/tabs/_shared/save_flow.py:1`, `src/tabs/save_toast.py:1`, `src/tabs/image_compare/use_cases/loading_toast.py:1`, `src/tabs/image_compare/use_cases/loading_pyramid.py:1`, `src/tabs/multi_compare/use_cases/loading.py:1`, `src/tabs/image_compare/services/analysis/metrics.py:1`, `src/tabs/image_compare/presenters/image_canvas/background_parts/diff_toasts.py:1`, `src/tabs/image_compare/pipeline/image_load_service.py:1`, toolkit `ui/widgets/composite/toast/`
Related: [plan_toast_refactor.md](./plan_toast_refactor.md) (ownership fix, Done except manual verify), [tabs/capability-mechanisms.md](./tabs/capability-mechanisms.md), [LOGGING.md](./LOGGING.md) (temp `[toast-debug]` stream, `IMGSLI_TOAST_DEBUG`), internal-docs `bug-a1-multi-compare-load-silently-skips`
Skills: `skills/imgsli-devtools/SKILL.md`, `skills/sli-ui-toolkit-docs-first/SKILL.md` (toolkit changes via its repo PR: version + CHANGELOG), internal-docs `skills/docs-orchestrator/SKILL.md` (worktrees `/tmp/opencode/`, never `main`, supervisor merges + removes trees same turn)

> **Executor note.** Trigger: paired-slot loading toast hangs forever — root-caused to a leaked `(slot, path)` alias in `pipeline._inflight` (fixed: `image_load_service.py` `_pop_alias` on result/finish). Recon (4 agents, 2026-09-05) showed the hang is 1 of 9 sticky-toast (`duration=0`) paths with no guaranteed close, ~250 LOC of prod-dead `if coord is None` fallbacks kept for `SimpleNamespace` fakes, a 3-deep save delegation chain with ~70 LOC pure forwarding, overlapping state maps, and a toolkit-side leak (`close()` without `deleteLater`) + redundant per-tick progress path. This plan closes the class, not the instance. Temp `[toast-debug]` lines stay until manual verify passes, then removed in one commit (LOGGING.md: no leftover noise).

## 1. Goal and non-goals

**Goal:** every sticky toast has a guaranteed terminal (finish/dismiss/close) on all exits; delete prod-dead fallback/duplication layers; fix toolkit toast destruction + progress fast path.
- Zero `duration=0` toasts without a reachable close on abort/error/skip/empty-pool paths
- −250 LOC legacy fallbacks (fakes rewritten to inject coordinators, as `session_init.py:24-32` does)
- Toolkit: no per-toast leak, progress-only updates skip text/repolish/reposition

**Non-goals / do not touch:**
- `CoreErrorOccurredEvent → AppMessageDialog.warning` policy (dialog, not toast — deliberate)
- `.jxl`/extension-list unification, `ui_mode`-for-IC race, `display_path_style` param, `__full_count__`/ghost-key removal (follow-ups, §5)
- Store/Dispatcher/EventBus shapes; `AbortSignal` unification across tabs (needs isolation-dogma sanction)
- Merging the two `AbortSignal` impls, `_inflight` key-shape convergence

**Locked decisions (do not reopen):**
- Coordinators (`LoadingToastCoordinator`, `PyramidBuildCoordinator`) are the single production path; per-tab `use_cases/` wrappers become thin delegates without `None`-fallback bodies
- `content=None` is the progress-only update shape (toolkit already supports it); app progress paths stop resending full strings
- Toolkit changes land in `sli-ui-toolkit` repo with version bump + CHANGELOG (its AGENTS.md hard rules), app only consumes

## 2. Recon summary (verified 2026-09-05 — do not re-research)

Close-leak sites (sticky toast, no guaranteed terminal): save done-on-external-cancel (`save_flow.py:168-170`), save signal-connect failure (`:276-279`), save sync-cancel swallow (`:288-291`), pyramid already-in-flight skip without finish (`pyramid.py:218-225`), pyramid abort/stalled with mapping left (`:270-284`), finish/dismiss after manager loss pops map but leaves pixels (`loading_toast.py:171-180`, metrics `:223-257`, diff `:116-121`), IC full-res error shows dialog but never finishes toast (`image_decode.py:78-90,521-530` — MC has paired dismiss+emit), metrics no-pool/stale/mode-flip orphans (`metrics.py:60-66,146-147,186-187`), diff key-mismatch + invalidate-without-manager (`diff_toasts.py:122-123`, `lifecycle.py:98-106`).
Dead duplication: 5 coordinator guards in IC `loading_toast.py` (~61 LOC), 8 in MC `loading.py` (~116 LOC), legacy pyramid path in `loading_pyramid.py:102-180` (~79 LOC) + `pyramid_build_task` translator (~31 LOC), 6+6 thin delegates with fallback halves in both controllers (~60 LOC), Layer-2 save forwards (~67 LOC, keep IC `_on_success_notify` + worker builders + MC `start_save_worker`), `_save_workers` write-only, `session.loading_toast_uid_slot` ghost field.
Toolkit: `hide_and_close` never destroys (registry `destroyed→pop` never fires) + `theme_changed` conns leak; progress tick pays font-metrics + same-string `setText` + repolish ×3 + show/raise + 2×O(N) reposition; broad `except pass` hides dead-anchor mispositioning.

## 3. Execution phases (worktrees `/tmp/opencode/<slug>`, `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`)

| Phase | Worktree / branch | Work | Verify |
|---|---|---|---|
| A close-leaks | `imgsli-toastA` / `feat/toastA-close-leaks` (Improve-ImgSLI) | finish/dismiss on: pyramid abort+stalled+already-in-flight (coordinator), save external-cancel + signal-connect + sync-cancel orphans, IC decode-error toast finish (MC parity), metrics no-pool/stale/mode-flip close, diff key-mismatch/invalidate close. Only production paths + new tests (new files under `tests/plugins/` or `src/tabs/<tab>/tests/`); do NOT touch legacy fallbacks (Phase B owns them) or `[toast-debug]` lines | focused toast/save/metrics/diff suites offscreen; contracts |
| B legacy removal | `imgsli-toastB` / `feat/toastB-legacy` (Improve-ImgSLI) | collapse IC/MC loading-toast wrappers + `loading_pyramid.py` legacy path + controller fallback halves to direct coordinator calls; rewrite `SimpleNamespace` fakes to inject `LoadingToastCoordinator`/`PyramidBuildCoordinator`; delete Layer-2 save pure forwards (keep real-logic methods), `_save_workers` dict, ghost `loading_toast_uid_slot` field. Do NOT touch close-leak lines from Phase A (different hunks; merge handles it) or `[toast-debug]` lines | full `src/tabs/*/tests` + `tests/plugins` offscreen; contracts incl. no-tab-internals-leak + file-size registry regen (`file_meta.py --write-registry`) |
| C toolkit | `slitoolkit-toastC` / `feat/toast-lifecycle` (sli-ui-toolkit) | `hide_and_close` destroys (`deleteLater`, `destroyed→pop` stays single registry exit); `update_message` fast path for `content is None and actions is None` (skip text/repolish/show-raise, keep scheduled reposition); narrow anchor/toast guards (`isValid`/null instead of `except pass`); document `content=None` in `FEEDBACK_API.md`; bump patch version + CHANGELOG (repo hard rules) | toolkit pytest + mypy (CI runs mypy, 0 errors); app progress paths switch to `content=None` ONLY after C lands (follow-up, §5) |

Supervisor merges A+B into `feat/toast-cleanup` (expect no conflicts: disjoint files/hunks), runs contracts, removes worktrees same turn. C merges in toolkit repo separately.

## 4. Risks

- Phase B test-fake rewrites are the bulk risk (799 `SimpleNamespace` hits repo-wide; scope is toast/loading/pyramid fakes only — do not boil the ocean)
- Abort-path finishing changes user-visible behavior (toast now closes on superseded loads) — intended, but Phase 5 manual check covers it
- Toolkit `deleteLater` changes destruction timing — its own test suite + app smoke must pass before app adopts `content=None`
- `[toast-debug]` lines remain until manual verify of the `_pop_alias` fix passes, then one removal commit

## 5. Follow-ups (not this plan)

- App progress paths → `content=None` (blocked on C)
- `.jxl`/accept-list unification, IC `ui_mode` race, `display_path_style`, ghost keys (`__full_count__`, `_pending_*`), `AbortSignal` unification sanction
- `TODO.md`/`plan_*.md` line-ref refresh, `[toast-debug]` removal commit
