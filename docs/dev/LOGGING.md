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

- `IMGSLI_RESIZE_DEBUG` → `[rhi-render-debug]` (`src/ui/canvas_infra/rhi/rhi_render.py`), `[resize-debug]` (`src/ui/main_window/runtime.py`); plus `IMGSLI_RESIZE_DEBUG_VISUAL` for the visual variant.
- `IMGSLI_MC_FIRST_FRAME_DEBUG` → Multi Compare first-frame timeline (`src/tabs/multi_compare/first_frame_debug.py`).
- `IMGSLI_IC_FIRST_FRAME_DEBUG` → Image Compare first-frame timeline (`src/tabs/image_compare/first_frame_debug.py`).
- `IMGSLI_GALLERY_DEBUG` → `[gallery-dnd]` DnD/open routing, `[gallery-debug]` gallery lifecycle (helpers mirrored in `src/tabs/image_compare/debug.py` docstring; original `src/tabs/image_gallery/debug.py` removed with the gallery tab).
- `IMGSLI_IMAGE_COMPARE_DEBUG` / `IMGSLI_IC_DEBUG` → `[ic-dnd]` drag/drop routing (`src/tabs/image_compare/debug.py:ic_dnd_debug / ic_debug`).
- `IMGSLI_IC_PREVIEW_DEBUG` → `[ic-preview]` preview display gate (`src/tabs/image_compare/debug.py:ic_preview_debug`): applied display tier per `apply_store_to_canvas` plus deferred/skip reasons.
- `IMGSLI_IC_GAP_DEBUG` → `[ic-gap]` gap diagnostics (`src/tabs/image_compare/debug.py:ic_gap_debug`): geometry, pick, `gap_correlation`, `resolve_lod`, `draw_plan`, bbox coverage. Also emits `core.tracing` `ic.gap.*` when `IMGSLI_TRACE=1`. Analyze with `python src/devtools/analyze_ic_gap.py --log ~/.local/share/ImproveImgSLI/log.txt`.
- `IMGSLI_AUTOCROP_DEBUG` → `[autocrop-debug]` auto-crop diagnostics (`src/shared/image_processing/autocrop/debug.py`; consumed at load/presentation sites).

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
