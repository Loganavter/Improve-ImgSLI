# Logging

The project uses Python's stdlib `logging` exclusively — **never `print()`** in committed code. This guarantees output goes through one configured pipeline (level filter, console + file handlers, consistent format) and can be silenced or amplified without touching source.

## Setup

| Path | Role |
|---|---|
| `sli_ui_toolkit/core/logging.py:setup_logging` | Builds the `"ImproveImgSLI"` logger: stream handler (stdout) + file handler (per-OS data dir), uniform formatter |
| `src/core/bootstrap.py:_configure_logging` | Calls `setup_logging("ImproveImgSLI", effective_debug, "IMPROVE_DEBUG")` at startup |
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

## The unique-prefix convention (subsystem diagnostics)

When a subsystem has its own conditionally-enabled debug stream (RHI renderer, resize-burst tracer, etc.), the convention is:
1. Gate it on an env var:
   ```python
   def _rhi_render_debug_enabled() -> bool:
       return _env_flag("IMGSLI_RESIZE_DEBUG")

   def _rhi_render_debug(message: str, *args) -> None:
       if _rhi_render_debug_enabled():
           logger.debug("[rhi-render-debug] " + message, *args)
   ```
2. Tag every line with a unique bracketed prefix (`[rhi-render-debug]`, `[resize-debug]`, `[autohide]`).
3. Document the env var so users/devs can enable just that stream without drowning in the rest.

This lets you `grep '\[rhi-render-debug\]' log.txt` later instead of trying to remember which file logged what.

Existing examples:
- `src/ui/widgets/canvas/rhi_renderer.py:_rhi_render_debug` → `IMGSLI_RESIZE_DEBUG`
- `src/ui/main_window/runtime.py:_resize_debug` → `IMGSLI_RESIZE_DEBUG` / `IMGSLI_RESIZE_DEBUG_VISUAL`

Do **not** wire a noisy subsystem's debug stream to the global `debug_mode_enabled` switch — that turns one log file into white noise (the user has hit this; see [feedback_working_style](memory) on noise suppression).

## Collaborative debugging — the right way

When you're stuck on a behaviour you can't predict from source alone, the project convention for temporary diagnostics is **still `logger.debug` (or `logger.warning`) with a unique prefix**, not `print()`. Steps:

1. Add diagnostics at suspected boundaries:
   ```python
   logger.warning("[flyout-debug] enter: visible=%s anchor=%s", self.isVisible(), self._anchor)
   ```
   - Use `warning` (not `debug`) if the user isn't running with `--debug`, so you don't need to ask them to flip flags.
   - Always include a unique bracketed prefix (`[flyout-debug]`, `[mag-recolor-debug]`) so they're easy to grep + easy to remove.
2. For "who called this?" — `import traceback; traceback.print_stack(limit=12)` is fine (it's stdlib, not `print`, and writes to stderr) — or use `logger.warning("[xxx] stack:\n%s", "".join(traceback.format_stack(limit=12)))` to go through the same pipeline.
3. Ask the user to reproduce and paste the lines matching your prefix.
4. **Remove** the diagnostics after fixing. Don't leave `[flyout-debug]` lines in the tree — that's noise next session.

The `print()` shortcut is tempting because output appears unconditionally, but it splits the console output stream and doesn't make it into `log.txt`. Stick with `logger.warning` + unique prefix.

## Silencing noisy subsystems temporarily

If a subsystem's debug stream is drowning out something you care about, raise its level locally:

```python
logging.getLogger("ImproveImgSLI.rhi").setLevel(logging.WARNING)
```

Or, for env-gated streams, just unset the env var.

## Reading existing logs

```bash
tail -f ~/.local/share/ImproveImgSLI/log.txt              # follow live
grep '\[mag-recolor-debug\]' ~/.local/share/ImproveImgSLI/log.txt
```

The log file is overwritten on every app start (`mode="w"`), so capture sessions you care about.

## See also

- [TRACING.md](TRACING.md) — structured tracer for Redux/EventBus/render chains (separate facility, complementary to plain logging)
- `sli_ui_toolkit/core/logging.py:setup_logging` — full source
- [AGENTS.md "Working style" §3](/home/jorj/Загрузки/Improve-ImgSLI/AGENTS.md) — collaborative-debug pivot guidance
