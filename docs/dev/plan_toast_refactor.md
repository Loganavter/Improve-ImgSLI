# Plan: host-owned ToastManager + toast refactor for both canvas tabs

Status: `Done` — Phases 1–4 executed 2026-09-05 on `feat/toast-host-owned` (3 parallel workers + supervisor fixups); Phase 5 manual verify pending
Area: `src/plugins/layout/plugin.py:27`, `src/ui/main_window/window.py:247`, `src/ui/main_window/ui.py:118`, `src/tabs/image_compare/ui/layout_manager.py:15`, `src/tabs/image_compare/service_factory.py:98`, `src/tabs/_shared/save_flow.py:106`, `src/tabs/_shared/loading_toast.py:42`, `src/tabs/multi_compare/use_cases/loading.py:45`
Related: [tabs/capability-mechanisms.md](./tabs/capability-mechanisms.md) §host→tab `create_startup_service` + Known gaps, [tabs/background-tab-policy.md](./tabs/background-tab-policy.md) (lazy pages), [plugins/layout.md](./plugins/layout.md), `sli-ui-toolkit` [FEEDBACK_API.md](../../../sli-ui-toolkit/docs/user/FEEDBACK_API.md) (`ToastManager(parent_window, image_label=None)` — anchor optional)
TODO ref: internal-docs `bug-a1-multi-compare-load-silently-skips` (MC silent load failures, no toast)
Skills: `skills/imgsli-devtools/SKILL.md` (contracts `./launcher.sh test tests/contracts -q`, `QT_QPA_PLATFORM=offscreen pytest`), `skills/sli-ui-toolkit-docs-first/SKILL.md` (read order followed down to `FEEDBACK_API.md`; `requirements-gui.txt` has `-e ../sli-ui-toolkit`, sibling source authoritative)

> **Executor note.** Trigger: toasts are dead app-wide — `~/.local/share/ImproveImgSLI/log.txt` shows `save_flow.py:130 "Toast manager unavailable; continuing export without toast UI"`. Root cause is a one-shot `LayoutPlugin.setup_ui_reference` racing lazy tab pages: the sole `layout_manager` provider (`ImageCompareTab`, `service_factory.py:98`) returns `None` while `tab._widget` is unset, and at setup time only the `session_picker` page exists (`activate_default` seeds the bootstrap default; IC/MC pages materialize on first activation per `background-tab-policy.md`). No retry exists, so `window.toast_manager` stays `None` forever — every consumer (`SaveToastMixin`, `LoadingToastCoordinator`, IC/MC loading wrappers, metrics service) degrades silently by design (capability-mechanisms.md Policy rule 1). MC has a second, independent hole: several load-failure paths log-and-return without any user signal (internal-docs bug-a1). This plan fixes ownership first (toasts alive), then plugs the silent paths (toasts meaningful), for both tabs. No new user-visible strings — no i18n/help churn.

## 1. Goal and non-goals

**Goal:** one host-owned `ToastManager` that is never `None` after shell setup, anchored to the active tab's canvas, serving both IC and MC save/loading/metrics toasts; MC load failures surface via the existing `CoreErrorOccurredEvent` path instead of log-only.
- `window.toast_manager is not None` after `setup_ui_reference`, even with zero canvas tabs ever opened
- Save toast (both tabs), loading toast (both tabs), SSIM/metrics toast (IC) all reach a live manager
- MC corrupt-file drop → user-visible signal (existing warning-dialog policy, not a new toast type)

**Non-goals / do not touch:**
- `sli-ui-toolkit` `ToastManager`/`ToastNotification` internals — toolkit is a fixed external dependency for this task (docs-first: `FEEDBACK_API.md` covers the used API; `set_anchor` already exists)
- QSS/painter pipeline, theme tokens (`toast.*` in `themes.json` untouched)
- Store/Dispatcher/EventBus dogma; `CoreErrorOccurredEvent → error_occurred → AppMessageDialog.warning` policy stays (dialog, not toast — deliberate, see §3.3)
- `image_canvas` `LazyTabService` wiring (already correct precedent)
- Accepted-extension-list unification (`.jxl` IC/MC drift, bug-a1 part 2) — separate task, noted in §5

**Locked decisions (do not reopen):**
- Toast host lives in `LayoutPlugin` (already the documented owner of `toast_manager` for host convenience, `plugins/layout.md:29`), not in a new plugin/service
- Anchor repoint stays in `Ui_ImageComparisonApp.sync_session_mode` (`ui.py:118-125`) via `create_service("toast_anchor_widget")` — IC (`service_factory.py:322`) and MC (`tab.py:385`) providers already exist; `session_picker` intentionally provides none (manager falls back to parent-window-relative placement per toolkit `FEEDBACK_API.md`)
- Per-tab `get_toast_manager` lambdas/call sites are **kept as-is** in this plan — they all funnel into `window.toast_manager`, which becomes non-`None`. Deduplicating them into one accessor is an optional follow-up, not required to fix the bug

## 2. Research summary (verified 2026-09-05 — do not re-research)

### 2.1 Inventory — every toast path and why each is dead/silent today

| # | Call site | Manager source | Today's fate |
|---|---|---|---|
| 1 | `tabs/_shared/save_flow.py:106` `_create_save_toast` (both tabs via delegates `ic/.../save_flow.py:38`, `mc/.../save_flow.py:28`) | `SaveToastMixin._get_toast_manager` → `main_window_app.toast_manager` (`tabs/save_toast.py:24`) | `None` → `INFO "continuing export without toast UI"`, export proceeds toastless (proven by prod log) |
| 2 | `tabs/_shared/loading_toast.py:86` `LoadingToastCoordinator.show` (both tabs) | injected lambda: IC `session_init.py:11` (`presenter.main_window_app.toast_manager`), MC `controller.py:94` (`context.main_window.toast_manager`) | `None` → silent `return`, no debug log on `show` |
| 3 | `ic/use_cases/loading_toast.py:41` legacy wrappers (pre-coordinator call sites) | `presenter.main_window_app.toast_manager` | `None` → `debug` + `return` |
| 4 | `ic/presenters/image_canvas/background_parts/diff_toasts.py:9` | `presenter.main_window_app.toast_manager` | `None` → guarded, no toast |
| 5 | `ic/services/analysis/metrics.py:189,213` SSIM toast | `runtime.toast_manager_getter` → `window_shell.toast_manager` (`ic/plugin.py:109`) | `None` → guarded (`:190`), no toast |
| 6 | Host: `ui/main_window/project/busy.py:42`, `open.py:151`, `services/io/recent_projects.py:279` | `window.toast_manager` directly | `None` → guarded/logged, no toast |
| 7 | MC load failures `mc/use_cases/loading.py:122-124` (+ `:291-293` decode-fail dismiss-only) | n/a (never reaches toast/event) | log-only → **silent skip**, independent of manager liveness (internal-docs bug-a1) |

Manager construction chain (single point of failure): `MainWindowPresenter.__init__` (`presenter.py:78`) → `LayoutPlugin.setup_ui_reference` (`plugin.py:32`) → `create_startup_service("layout_manager")` → IC factory returns `None` when `tab._widget is None` (`service_factory.py:99`) → `LayoutPlugin.manager = None` → `LayoutPlugin.toast_manager → None` (`plugin.py:41`) → `MainWindow.toast_manager → None` (`window.py:247`, caches only success). At setup time only `session_picker` page exists (lazy pages: `tabs/use_cases/pages.py:19-34`, `background-tab-policy.md:21-25`); IC/MC widgets are `None`. One-shot call, no retry — dead forever, including after IC is opened.

### 2.2 Why host-owned is the sanctioned shape

- Toolkit API: `ToastManager(parent_window, image_label=None)` — anchor **optional** (`FEEDBACK_API.md`); `set_anchor` repoints later. App-side `ImageCompareLayoutManager` over-constrains by requiring `ui.image_label` at construction; the toolkit does not.
- Precedent: `image_canvas` already solved the identical lazy-widget race with `LazyTabService` (`composer.py:115-125`, capability-mechanisms.md `image_canvas` section). Toast ownership split (mode fanout stays tab-owned, toast host becomes host-owned) mirrors that separation.
- Capability policy: `layout_manager` missing for MC/SP is a documented known gap (capability-mechanisms.md gaps section) — host-owned toasts close the user-visible symptom without forcing MC/SP to implement layout managers.
- Doc contradiction noted (not fixed here): `tabs/contract.md:38-43` claims `create_page` runs "once during application startup"; lazy truth is `background-tab-policy.md:21-25` + `pages.py`. Diagnosis follows the lazy truth.

### 2.3 Adjacent gap found, explicitly out of scope

`ImageCompareLayoutManager` is **never created** when the IC page materializes lazily (only `setup_ui_reference` creates it, once, too early) — so `ui_mode` apply (`beginner/advanced/expert` chrome) likely never reaches IC either. Same one-shot race, different symptom. Tracked as follow-up in §5; this plan must not entangle the two (different blast radius: toast = additive host object, modes = tab chrome behavior).

## 3. Design

### 3.1 Split LayoutPlugin: mode fanout (tab-owned, nullable) vs toast host (host-owned, non-null)

```python
# src/plugins/layout/plugin.py
def setup_ui_reference(self, ui, parent_window=None):
    ...existing create_startup_service("layout_manager") for modes...
    if self._toast_manager is None and parent_window is not None:
        from sli_ui_toolkit.widgets import ToastManager  # public import (skill hard rule)
        self._toast_manager = ToastManager(parent_window)  # anchor=None: valid per FEEDBACK_API.md
        anchor = <resolve active tab toast_anchor_widget if any>
        if anchor is not None:
            self._toast_manager.set_anchor(anchor)

@property
def toast_manager(self):
    return self._toast_manager  # never None after setup_ui_reference
```

- `self.manager` (modes) keeps current semantics exactly, including `None` degradation in `on_ui_mode_changed`.
- Remove `toast_manager` creation from `ImageCompareLayoutManager.__init__` (`layout_manager.py:32-33`) — it becomes pure chrome-layout; keep the attribute as a deprecated `None` stub only if a contract test pins it (none found — `rg layout_manager tests` is clean), else delete.
- `MainWindow.toast_manager` (`window.py:247`) unchanged — it now resolves non-`None` on first access and caches.
- Anchor repoint on tab switch already exists (`ui.py:121-125`); extend it with a `None`-anchor guard so switching to `session_picker` keeps the last canvas anchor (documented fallback, no crash: toolkit `_position_toasts`/`_toast_max_width` already swallow anchor errors).

### 3.2 Both tabs ride the same manager, no call-site changes

Rows 1–6 of §2.1 need zero edits: their `None`-guards simply stop triggering. `SaveToastMixin`, `LoadingToastCoordinator`, IC/MC wrappers, metrics runtime, host project flows all light up. This is deliberate — minimal diff, maximal coverage, no Store/EventBus shape changes.

### 3.3 MC silent load failures → existing error path (dialog, not toast)

`mc/use_cases/loading.py:45-67` already emits `CoreErrorOccurredEvent` for some failures → `MainController._on_core_error_occurred` → `error_occurred` signal → `on_error_occurred` modal warning (`actions.py:13`). Wire the remaining silent paths (`loading.py:122-124`, `:291-293`, plus `load_single_auto`/`on_images_dropped` skip sites per bug-a1) into the **same** helper. No new toast type, no policy change — log-only is the bug, the dialog is the sanctioned signal. IC parity: IC emits the same event class for the same failure class (`slot.py:376,552`, `image_decode.py:87,530`).

## 4. Execution phases (fresh branch `feat/toast-host-owned` off `main`; worktrees `/tmp/opencode/<repo>-<slug>` per docs-orchestrator hygiene; `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider` for tests)

| Phase | Work | Files | Verify |
|---|---|---|---|
| 0 | Setup: branch off `main`, confirm prod repro signature (`"continuing export without toast UI"` in `log.txt`) | — | `git branch --show-current` |
| 1 | Host-owned manager in `LayoutPlugin`; strip toast creation from `ImageCompareLayoutManager`; `None`-anchor guard in `sync_session_mode` | `plugins/layout/plugin.py`, `tabs/image_compare/ui/layout_manager.py`, `ui/main_window/ui.py` | New regression test (Phase 4) red→green |
| 2 | MC silent paths → `CoreErrorOccurredEvent` helper | `tabs/multi_compare/use_cases/loading.py` (+ callers `load_single_auto`, `on_images_dropped`) | focused `pytest tests/...mc...loading` + new silent-failure test asserting event emission on corrupt drop |
| 3 | Regression tests: (a) `setup_ui_reference` with IC widget `None` → `toast_manager is not None` (offscreen `QWidget` parent); (b) `show/update` round-trip on host manager; (c) MC corrupt-load emits error event | `tests/plugins/test_toast_host_owned.py` (new) | `QT_QPA_PLATFORM=offscreen pytest tests/plugins -k toast` |
| 4 | Contracts + full focused suites; docs: update `plugins/layout.md` (host-owned manager + anchor fallback), `docs_link_graph.py --write-index`, translations check `--strict` (expect zero new keys) | `docs/dev/plugins/layout.md`, `DOC_INDEX.md` | `./launcher.sh test tests/contracts -q`; `check_translations.py --strict` |
| 5 | Manual verify: `./launcher.sh run --debug`, export in IC + MC (toast + cancel), MC corrupt drop (warning), tab switch picker↔IC↔MC (anchor repoint, no crash); `trace.jsonl` shows no toast-adjacent errors | — | `log.txt` has zero `"Toast manager unavailable"` |

## 5. Follow-ups (not this plan)

- `ImageCompareLayoutManager` lazy creation on first IC activation (ui-mode race, §2.3) — separate plan, touches chrome behavior
- Per-tab `get_toast_manager` lambda dedup into one host accessor (cosmetic; call sites work as-is)
- `.jxl`/extension-list IC↔MC unification (bug-a1 part 2)
- `tabs/contract.md:38-43` "startup" wording vs lazy truth — one-line doc fix, bundle with Phase 4 if trivial
- Stale `docs/dev/investigations/*` links (dir no longer exists; `docs_link_graph` scope) — report, do not fix here

## 6. Risks

- Toast stacking parent: `ToastNotification` parents to `parent_window` (top-level) — must confirm no CSD/overlay z-order burial in manual Phase 5 (`--ui-inspector` if misplaced). Mitigation: toolkit `_position_toasts` + `raise_()` on every show/update; anchor math already production-proven for IC.
- `session_picker`-active anchor staleness: last-canvas anchor kept; canvas pages live forever (no teardown), so dangling-anchor risk is minimal; toolkit broad-except guards placement math.
- `feat/mc-refactor` divergence: MC `loading.py`/`controller.py` are under active refactor — rebase Phase 2 onto its tip or land this first; plan assumes `main`.
