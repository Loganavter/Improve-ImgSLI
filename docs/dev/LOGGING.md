# Logging

Host-specific logging setup. Shared conventions (stdlib `logging` only, unique-prefix recipe, temporary-diagnostics workflow, silencing) live in the canonical doc: [sli-ui-toolkit logging conventions](https://github.com/Loganavter/sli-ui-toolkit/blob/main/docs/dev/LOGGING.md).

## Setup

| Path | Role |
|---|---|
| `sli_ui_toolkit/core/logging.py:setup_logging` | Builds the `"ImproveImgSLI"` logger: stream handler (**stderr**) + file handler (per-OS data dir), uniform formatter |
| `src/core/bootstrap.py:_configure_logging` | Calls `setup_logging("ImproveImgSLI", effective_debug, "IMPROVE_DEBUG")` at startup |
| `src/core/startup_trace.py` | Optional phase timing when `IMGSLI_STARTUP_TRACE=1` (logger name `ImproveImgSLI.startup`) |
| `src/__main__.py` | CLI flags `--debug` / `--enable-logging` / `--disable-logging` |

Log file location (cleared on every start, `mode="w"`):
- Linux: `${XDG_DATA_HOME:-~/.local/share}/ImproveImgSLI/log.txt`
- macOS: `~/Library/Application Support/ImproveImgSLI/log.txt`
- Windows: `%APPDATA%/ImproveImgSLI/log.txt`

Format:
```
2026-06-26 11:31:45,313 - [DEBUG] - (rhi_renderer.py:54) - [rhi-render-debug] render begin ...
```

## Log level — how it's resolved

`setup_logging` picks `DEBUG` vs `INFO` based on, in order:
1. `IMPROVE_SUPPRESS_DEBUG=1` env var → force `INFO` (override switch off).
2. `IMPROVE_DEBUG=1` env var → force `DEBUG`.
3. CLI flag `--debug` → `DEBUG` for this session.
4. Persisted setting `debug_mode_enabled` (in QSettings, toggled via `--enable-logging` / `--disable-logging` or the Settings UI) → `DEBUG` or `INFO`.
5. Default → `INFO`.

The level applies to both handlers. Switching it from the Settings UI takes effect immediately via re-`setup_logging`.

## Getting a logger

Always use the `"ImproveImgSLI"` namespace (or a sub-logger of it). The root logger isn't configured.

```python
import logging
logger = logging.getLogger("ImproveImgSLI")              # default; most modules use this
logger = logging.getLogger("ImproveImgSLI.rhi")          # sub-logger for a subsystem
logger = logging.getLogger("ImproveImgSLI.plugin.lifecycle")
```

Sub-loggers inherit handlers + level. They show up in the format as `[DEBUG]` etc., but the filename column already tells you which module produced the line.

## Levels — when to use what

| Level | Use for |
|---|---|
| `logger.debug(...)` | Verbose diagnostic detail. Only visible with `--debug` / `debug_mode_enabled`. Default for everything that doesn't matter to a normal user. |
| `logger.info(...)` | Significant lifecycle events (plugin initialized, theme changed, etc.). Visible by default. Use sparingly — info should be readable. |
| `logger.warning(...)` | Something is off but the app continues (missing file with fallback, deprecated path, slow operation). |
| `logger.error(...)` | A real failure that the user/dev needs to know about. Pair with `exc_info=True` if there's an exception. |
| `logger.critical(...)` | Rare. Reserved for app-fatal conditions. |

```python
logger.error(f"Plugin {name} failed during {stage}: {err}", exc_info=True)
```

## Shared conventions (canonical)

- Unique-prefix recipe and rationale — see the [canonical doc](https://github.com/Loganavter/sli-ui-toolkit/blob/main/docs/dev/LOGGING.md); host streams below follow it (env-gated helper + bracketed prefix + documented var).
- Never-`print()` rationale — see the [canonical doc](https://github.com/Loganavter/sli-ui-toolkit/blob/main/docs/dev/LOGGING.md); committed code uses `logging` so output flows through the configured handlers into `log.txt`.
- Temporary-diagnostics methodology — see the [canonical doc](https://github.com/Loganavter/sli-ui-toolkit/blob/main/docs/dev/LOGGING.md); add greppable `logger.debug`/`logger.warning` lines with a unique prefix, then remove them after the fix.
- Silencing theory — see the [canonical doc](https://github.com/Loganavter/sli-ui-toolkit/blob/main/docs/dev/LOGGING.md); for env-gated host streams unset the env var, or raise a sub-logger level locally:

```python
logging.getLogger("ImproveImgSLI.rhi").setLevel(logging.WARNING)
```

Do **not** wire a noisy subsystem's debug stream to the global `debug_mode_enabled` switch — that turns one log file into white noise.

## Host subsystem debug streams

Env-gated streams following the canonical unique-prefix recipe:

- `IMGSLI_RESIZE_DEBUG` → `[rhi-render-debug]` (`src/engine/cache/render_debug.py`, shared by every tab's tile-array path), `[resize-debug]` (`src/ui/main_window/runtime.py`); plus `IMGSLI_RESIZE_DEBUG_VISUAL` for the visual variant.
- `IMGSLI_MC_FIRST_FRAME_DEBUG` → Multi Compare first-frame timeline (`src/tabs/multi_compare/first_frame_debug.py`).
- `IMGSLI_IC_FIRST_FRAME_DEBUG` → Image Compare first-frame timeline (`src/tabs/image_compare/first_frame_debug.py`).
- `IMGSLI_GALLERY_DEBUG` → `[gallery-dnd]` DnD/open routing, `[gallery-debug]` gallery lifecycle (`src/tabs/image_gallery/debug.py`; IC helpers mirror the pattern in `src/tabs/image_compare/debug.py`).
- `IMGSLI_IMAGE_COMPARE_DEBUG` / `IMGSLI_IC_DEBUG` → `[ic-dnd]` drag/drop routing (`src/tabs/image_compare/debug.py:ic_dnd_debug / ic_debug`).
- `IMGSLI_IC_PREVIEW_DEBUG` → `[ic-preview]` preview display gate (`src/tabs/image_compare/debug.py:ic_preview_debug`): applied display tier per `apply_store_to_canvas` plus deferred/skip reasons.
- `IMGSLI_IC_GAP_DEBUG` → `[ic-gap]` gap diagnostics (`src/tabs/image_compare/debug.py:ic_gap_debug`): geometry, pick, `gap_correlation`, `resolve_lod`, `draw_plan`, bbox coverage. Also emits `core.tracing` `ic.gap.*` when `IMGSLI_TRACE=1`. Analyze with `python src/devtools/analyze_ic_gap.py --log ~/.local/share/ImproveImgSLI/log.txt`.
- `IMGSLI_IC_LOUPE_DEBUG` → `[ic-loupe]` magnifier residency/LOD trace (`src/tabs/image_compare/debug.py:ic_loupe_debug`): `TileTextureService.request_level` answers, dropped-slice reasons, texture-choice and dedup verdicts; the same points also record into the per-frame `FrameContext` (see `src/tabs/image_compare/canvas/loupe_trace.py` for the sig/time/once throttle recipes).
- `IMGSLI_IC_INVALIDATE_DEBUG` → `[ic-invalidate]` attributed invalidation bus (`src/tabs/image_compare/debug.py:ic_invalidate_debug`): every scheduler/keep-warm/timer arm and fire/skip records source+reason into `FrameContext` (`src/tabs/image_compare/canvas/frame_context.py`); flag off costs one env check per site.
- `IMGSLI_AUTOCROP_DEBUG` → `[autocrop-debug]` auto-crop diagnostics (`src/shared/image_processing/autocrop/debug.py`; consumed at load/presentation sites).
- `UI_NAV_DEBUG` → nav routing diagnostics (`src/events/router.py` + `src/events/app_event_handler.py`): standalone, needs neither `--debug` nor toolkit debug flags.

### Full env-flag registry (audit 2026-09-20, reorg waves W1–W3)

Every `IMGSLI_*` gate parses via `shared/debug_flags.env_flag` (permissive:
any non-empty value except `0/false/no/off`). Scope legend: `log` = gated
log lines only; `visual` = changes pixels; `dump` = writes capture files;
`behavior` = changes runtime behavior (NOT a debug log — do not mistake for one);
`tuning` = numeric/path knob; `trace` = tracer/startup facility; `removed` = deleted.

| Flag | Scope | Parsing | Owner file(s) |
|---|---|---|---|
| `IMGSLI_TRACE`, `IMGSLI_TRACE_KINDS`, `IMGSLI_TRACE_SKIP` | trace | permissive / filter lists | `src/core/tracing/tracer.py` |
| `IMGSLI_STARTUP_TRACE` | trace | `env_flag` | `src/core/startup_trace.py` |
| `IMGSLI_RESIZE_DEBUG` | log | `env_flag` | `src/engine/cache/render_debug.py`, `src/ui/main_window/runtime.py` |
| `IMGSLI_RESIZE_DEBUG_VISUAL` | visual | `env_flag` | `src/ui/main_window/runtime.py` |
| `IMGSLI_RESIZE_SHIELD` | behavior | `env_flag` | `src/ui/main_window/runtime.py` |
| `IMGSLI_FLYOUT_DEBUG` | log | `env_flag` | `src/ui/widgets/flyout_debug.py` |
| `IMGSLI_TILE_DUMP` | dump | cached at import (restart to toggle) | `src/engine/cache/tile_debug.py` |
| `IMGSLI_GALLERY_DEBUG` | log | `env_flag` | `src/tabs/image_gallery/debug.py` |
| `IMGSLI_IMAGE_COMPARE_DEBUG` / `IMGSLI_IC_DEBUG` | log | `env_flag` (aliases, same gate) | `src/tabs/image_compare/debug.py` |
| `IMGSLI_MULTI_COMPARE_DEBUG` / `IMGSLI_MC_DEBUG` | log | `env_flag` (aliases, same gate) | `src/tabs/multi_compare/debug.py` |
| `IMGSLI_IC_PREVIEW_DEBUG`, `IMGSLI_IC_GAP_DEBUG`, `IMGSLI_IC_LABEL_DEBUG`, `IMGSLI_IC_LOUPE_DEBUG`, `IMGSLI_IC_INVALIDATE_DEBUG`, `IMGSLI_MAGNIFIER_DEBUG` | log | `env_flag` | `src/tabs/image_compare/debug.py` |
| `IMGSLI_IC_FIRST_FRAME_DEBUG` / `IMGSLI_MC_FIRST_FRAME_DEBUG` | log | `env_flag` (thin wrappers, shared body) | `src/tabs/*/first_frame_debug.py`, `src/ui/canvas_infra/rhi/rhi_render.py` |
| `IMGSLI_VIDEO_EDITOR_DEBUG` / `IMGSLI_IC_VIDEO_DEBUG` | log | `env_flag` (aliases, editor zone) | `src/tabs/image_compare/debug.py:ic_video_debug`, `plugins/video_editor/*` (editor sites), `src/plugins/export/*` (platform-local inline gates) |
| `IMGSLI_TIMELINE_DEBUG` | log | `env_flag` (timeline zone only) | `plugins/video_editor/debug_timeline.py:timeline_debug_enabled`, dialog `shell.py` |
| `IMGSLI_THUMBNAIL_DEBUG` | log + dump | `env_flag` (pipeline zone only) | `src/tabs/image_compare/debug.py:ic_thumbnail_debug`, thumbnail pipeline (`services/thumbnails.py`, `presenter_parts/thumbnails.py`) |
| `IMGSLI_VIDEO_PERF_DEBUG` / `IMGSLI_IC_PERF_DEBUG` | log | `env_flag` (aliases) | `src/tabs/image_compare/debug.py:ic_perf_debug` |
| `IMGSLI_LASER_DEBUG` | log | `env_flag` (all 14 sites verified log-only 2026-09-20) | guides/magnifier/scroll/pickers (5 files) |
| `IMGSLI_LASER_UI_DEBUG` | reserved | `env_flag` (read nowhere yet) | convention only — mandatory gate for any future laser UI-visibility use |
| `IMGSLI_AUTOCROP_DEBUG` | log | `env_flag` | `src/shared/image_processing/autocrop/debug.py` |
| `IMGSLI_DND_DEBUG` | log | `env_flag` | `src/events/app_event/window_events.py`, `src/events/window_event_handler.py` |
| `IMGSLI_DOUBLE_GEOM_DEBUG` | log | `env_flag` | `src/ui/widgets/unified_list_picker/debug.py` |
| `IMGSLI_SHELF_RESIZE_DEBUG` | log | single helper `sizing._shelf_resize_debug` | `src/tabs/session_picker/recent/use_cases/sizing.py`, `panel.py` |
| `IMGSLI_GLASS_PANEL_DEBUG` (+ `_SIZE`, `_SYNC_PROBE`) | log | cached at import / truthy | `src/engine/gpu/glass_panel.py`, `src/ui/widgets/glass_hud/*` |
| `IMGSLI_GLASS_PANEL_DEBUG_TINT` | visual | cached at import | `src/engine/gpu/glass_panel.py` |
| `IMGSLI_GLASS_PANEL_DEBUG_DUMP` | dump | `<dir>` path | `src/engine/gpu/glass_panel.py` |
| `IMGSLI_GLASS_PANEL_DISPLAY_BACKEND` | behavior | `=rhi` switch | `src/ui/widgets/glass_hud/*` |
| `IMGSLI_FAULT_DUMP` (+ `_FILE`, `_INTERVAL`) | dump | `env_flag` + path + int w/ fail-open default 15 | `src/core/windowed_stdio.py` |
| `IMGSLI_SKIP_MIP_CASCADE` | behavior | `env_flag` | `src/tabs/multi_compare/scene/renderer.py` |
| `IMGSLI_MC_RMB_SURFACE` | behavior | `=in_window\|popup` | `src/tabs/multi_compare/canvas/interaction.py` |
| `IMGSLI_MC_DND_DIAG_LIGHT_MOVE` | behavior | diag-only A/B, never ship | `src/tabs/multi_compare/debug.py` |
| `IMGSLI_DND_KEEPWARM_MS`, `IMGSLI_DND_ENTER_DELAY_MS` | tuning | int ms | `src/tabs/image_compare/canvas/widget.py`, `src/events/window_event_handler.py` |
| `IMGSLI_SKIP_FILE_ASSOCIATION` | behavior | `env_flag` | `src/services/system/windows_file_association.py` |
| `IMGSLI_PROJECT_CACHE` | tuning | path override | `src/services/io/project_package.py` |
| `IMGSLI_PROFILE_MAGNIFIER_TOGGLE` | trace | `env_flag` (cProfile) | magnifier toolbar `handlers.py` |
| `IMPROVE_IMGSLI_RHI_BACKEND`, `IMPROVE_IMGSLI_ALLOW_LSFGVK`, `IMPROVE_IMGSLI_STRICT_CONTRACTS` | behavior | `IMPROVE_` prefix (legacy naming) | `src/ui/canvas_infra/rhi/rhi_backend.py`, `workspace_transition_mask.py` |
| `IMGSLI_ACTIVATION_PROBE` | removed | deleted 2026-09-20 (was TEMPORARY in `src/__main__.py`) | — |
| `IMGSLI_TOAST_DEBUG` | removed | deleted earlier (no `src/` refs; docs residue cleaned 2026-09-20) | — |

Notes: video-family flags are NARROW since 2026-09-20 (host-dbgflags W5):
`VIDEO_EDITOR`/`IC_VIDEO` gate the editor zone only (`ic_video_debug`),
`TIMELINE` the timeline zone only (`timeline_debug_enabled`), `THUMBNAIL`
the pipeline zone only (`ic_thumbnail_debug` + pixel dump gate). Migration:
set `IMGSLI_THUMBNAIL_DEBUG=1` for pipeline, `IMGSLI_TIMELINE_DEBUG=1` for
timeline. `IMPROVE_IMGSLI_*` vs `IMGSLI_*` prefix duality is historical; both spellings
are honored only where listed above.

## Startup trace

Cold-startup phase timing (bootstrap vs deferred plugin load):

```bash
IMGSLI_STARTUP_TRACE=1 python src/__main__.py
grep 'ImproveImgSLI.startup' ~/.local/share/ImproveImgSLI/log.txt
```

## Reading existing logs

```bash
tail -f ~/.local/share/ImproveImgSLI/log.txt              # follow live
grep '\[mag-recolor-debug\]' ~/.local/share/ImproveImgSLI/log.txt
```

The log file is overwritten on every app start (`mode="w"`), so capture sessions you care about.

## See also

- [Canonical logging conventions](https://github.com/Loganavter/sli-ui-toolkit/blob/main/docs/dev/LOGGING.md) — shared recipe/rationale (unique-prefix, never-print, temp-diagnostics, silencing)
- [TRACING.md](TRACING.md) — structured tracer for Redux/EventBus/render chains (separate facility, complementary to plain logging)
- `sli_ui_toolkit/core/logging.py:setup_logging` — full source
- [AGENTS.md](../../AGENTS.md) — agent guide; see **Debugging Runtime Issues** and **Agent Tooling**
