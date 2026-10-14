# DONE — logging-hygiene (task-logging-hygiene-2026-10-14)

## STATUS

DONE. Noisy host-UI / host-core subsystem debug streams are now env-gated:
each is completely silent unless its own explicit `IMGSLI_*_DEBUG` (or the
pre-existing `UI_NAV_DEBUG`) flag is set — even with the persisted
`debug_mode_enabled=true` forcing the global level to DEBUG. Warnings/errors
and genuinely useful one-shot lifecycle lines were left untouched.

Branch: `agent/logging-hygiene/work`
Commit: `chore(logging): gate noisy subsystem traces behind explicit env flags [task-logging-hygiene-2026-10-14]`

## TESTS

Run from repo clone root, `QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1`:

- `PYTHONPATH=src python3 -m pytest -q tests/contracts -p no:cacheprovider`
  → **2030 passed, 66 skipped** (green; includes `test_file_size_policy`
  after the registry refresh).
- `PYTHONPATH=src python3 -m pytest -q tests/contracts tests/runtime/test_host_debug_gating.py -p no:cacheprovider`
  → **2048 passed, 66 skipped** (contracts + the new focused logging test).
- New focused test: `tests/runtime/test_host_debug_gating.py`
  → **18 passed**. Proves every gated stream is silent without its flag and
  emits (at WARNING) with it; `layout_tree_debug_enabled()` /
  `startup_debug_enabled()` track the env; `nav_debug` reuses `UI_NAV_DEBUG`.
- `PYTHONPATH=src python3 -m pytest -q tests/runtime -p no:cacheprovider`
  → **522 passed** (whole runtime suite).
- `PYTHONPATH=src python3 -m pytest -q tests/test_*.py tests/plugins -p no:cacheprovider`
  → **382 passed, 3 skipped**.
- `PYTHONPATH=src python3 -m pytest -q tests/devtools/test_docs_link_graph.py tests/contracts/test_file_size_policy.py -p no:cacheprovider`
  → **8 passed**.
- AST proof (`python3` scan of `src/core`, `src/ui`, `src/shared_toolkit`,
  `src/tabs/use_cases`): **no bare `logger.debug(` with a helper-gated noisy
  prefix remains** (265 files scanned). `[flyout-debug]` in
  `font_manager.py` remains a `_logger.debug(` but is wrapped in
  `if _env_flag("IMGSLI_FLYOUT_DEBUG"):` (verified with grep -B1).

## INTERFACE

New public helpers (import from these; do not re-implement the gate):

- `src/ui/host_debug.py` — `transient_debug` / `transient_close_debug`,
  `ctx_menu_debug`, `workspace_transition_debug`, `layout_tree_debug`
  (+`layout_tree_debug_enabled`), `startup_debug` (+`startup_debug_enabled`),
  `rhi_primer_debug`, `scroll_value_debug` (+`*_enabled`). Hybrid emit:
  `WARNING` when the explicit flag is set (visible without `--debug`),
  nothing otherwise.
- `src/core/nav_debug.py` — `nav_debug(msg, *args)` /
  `nav_debug_enabled()`; gated on the existing `UI_NAV_DEBUG` flag.

Env flags (all `env_flag` parsing, scope `log`): `IMGSLI_TRANSIENT_DEBUG`,
`IMGSLI_CTX_MENU_DEBUG`, `IMGSLI_WORKSPACE_DEBUG`, `IMGSLI_LAYOUT_DEBUG`,
`IMGSLI_STARTUP_DEBUG`, `IMGSLI_RHI_PRIMER_DEBUG`, `IMGSLI_SCROLL_VALUE_DEBUG`,
`IMGSLI_CAPABILITY_DEBUG`; `UI_NAV_DEBUG` and `IMGSLI_FLYOUT_DEBUG` extended
in place (no fork).

## SELF-REVIEW

- **Scope honored.** Touched `src/core/**`, `src/ui/**`, `src/shared_toolkit/**`
  (font_manager — allowed by supervisor steer), `src/tabs/use_cases/**`
  (capability_routing — allowed by supervisor steer), `docs/dev/LOGGING.md`,
  `docs/dev/file_size_registry.json` (mechanical line-count refresh required
  by the contract), and `tests/**`. Did **not** touch
  `src/tabs/image_gallery/**`, `src/tabs/image_compare/**`,
  `src/tabs/multi_compare/**`, or the external `sli-ui-toolkit`.
- **No behavior change** other than log visibility: all gated sites were
  `logger.debug(...)`; no warning/error/exception was removed. The
  `[workspace-transition]` `cover skipped` warnings and the mask contract
  error stay at their original levels.
- **Layout tree dump** is not even built when `IMGSLI_LAYOUT_DEBUG` is unset
  (early return before `_tree()`), so the huge dumps cost nothing by default.
- **Warning-level hybrid emit** is intentional and documented in each helper
  (mirrors `tabs/image_gallery/debug.py` / `tabs/image_compare/debug.py` and
  `ui/widgets/unified_list_picker/debug.py`): the flag is a deliberate
  opt-in, so the trace should be visible without also passing `--debug`.
- **Tests are falsifiable**: `test_stream_silent_without_flag` fails on HEAD
  (the raw `logger.debug` lines fire under a DEBUG-level caplog) and passes
  now; `test_stream_emits_with_flag` proves the flag path is wired.

## SUMMARY

Gated subsystems + flags:

| Subsystem | Prefix(es) | Flag | Where |
|---|---|---|---|
| transient UI | `[transient]`, `[transient-close]` | `IMGSLI_TRANSIENT_DEBUG` | `ui/managers/transient_ui_manager.py`, `ui/managers/transient_ui_parts/closing.py` |
| context menus | `[ctx-menu]` | `IMGSLI_CTX_MENU_DEBUG` | `ui/context_menu/manager.py`, `ui/presenters/main_window/connections.py` |
| workspace transitions | `[workspace-transition]` | `IMGSLI_WORKSPACE_DEBUG` | `ui/presenters/main_window/workspace.py`, `ui/main_window/workspace_transition_mask.py`, `ui/main_window/layouts.py` |
| layout tree dump | `[layout-tree]` | `IMGSLI_LAYOUT_DEBUG` | `ui/main_window/lifecycle.py` |
| startup pipeline | `[startup]` | `IMGSLI_STARTUP_DEBUG` | `ui/main_window/lifecycle.py` |
| RHI primer | `[rhi-primer]` | `IMGSLI_RHI_PRIMER_DEBUG` | `ui/canvas_infra/rhi/rhi_backend.py` |
| scroll-value control | `[scroll-value]` | `IMGSLI_SCROLL_VALUE_DEBUG` | `ui/widgets/scroll_value_button.py` |
| shell navigation | `[nav-titlebar]`, `[nav-tabstrip]`, `[nav-picker]`, `[nav-card]`, `[nav-tab]` | `UI_NAV_DEBUG` (reused) | `core/app_shell_navigation.py`, `core/navigation_sections.py` via `core/nav_debug.py` |
| startup capability routing | `[startup-service]` | `IMGSLI_CAPABILITY_DEBUG` | `src/tabs/use_cases/capability_routing.py` |
| font apply | `[flyout-debug]` | `IMGSLI_FLYOUT_DEBUG` (reused) | `src/shared_toolkit/ui/managers/font_manager.py` |

New registry rows added to `docs/dev/LOGGING.md` "Full env-flag registry"
(all scope `log`, parsing `env_flag`): `UI_NAV_DEBUG` (new row),
`IMGSLI_TRANSIENT_DEBUG`, `IMGSLI_CTX_MENU_DEBUG`, `IMGSLI_WORKSPACE_DEBUG`,
`IMGSLI_LAYOUT_DEBUG`, `IMGSLI_STARTUP_DEBUG`, `IMGSLI_RHI_PRIMER_DEBUG`,
`IMGSLI_SCROLL_VALUE_DEBUG`, `IMGSLI_CAPABILITY_DEBUG`; `IMGSLI_FLYOUT_DEBUG`
row extended with the font_manager owner. The "Host subsystem debug streams"
list gained a matching bullet per stream.

Out-of-scope follow-ups (not touched; flagged for the supervisor):

- `[video-editor-debug]` bare `logger.debug` in `src/plugins/export/plugin.py`
  (2 sites) and `src/plugins/export/controller.py` (1 site) — `src/plugins`
  was not in scope. Most video-editor sites are already gated via
  `ic_video_debug` (`IMGSLI_VIDEO_EDITOR_DEBUG`) in
  `src/tabs/image_compare/debug.py` (owned by other workers). Asked the
  supervisor whether to gate the `src/plugins/export/*` three sites.
- `src/shared/analysis/differ.py` emits per-tile `[GRAYSCALE_TILE]` debug
  inside loops — a potential high-frequency flood, but `src/shared` was
  limited to `debug_flags.py` by the task scope.
- `csd_debug` (`src/ui/main_window/csd_menu_strip.py`) and the
  `UIManager.show_settings_dialog` caller trace remain plain `logger.debug`
  (low-frequency, not in the reported flood set).
