---
name: imgsli-devtools
description: Runs Improve-ImgSLI developer tools for debugging and validation. Use when investigating runtime UI bugs, trace chains, theme or QSS mismatches, translation gaps, stale shaders, startup timing, codebase size questions, or before large refactors.
---

# Improve-ImgSLI devtools

Pick a tool by symptom. Read the linked doc only when you need filtering or interpretation details.

## Symptom → tool

| Symptom | Command | Doc |
|---|---|---|
| Weird after click / zoom / state change | `./launcher.sh run --debug` or `IMGSLI_TRACE=1 ./launcher.sh run` | [docs/dev/TRACING.md](../../docs/dev/TRACING.md) |
| MC zoom “jumps” on first flyout (chip unchanged) | re-check mitigations; see gotchas | `qrhi-gotchas.md` (private sibling repo) (sharded: `docs/dev/rendering/cases/display-lags-store.md`) |
| Widget color / palette / theme token / QSS candidate | `./launcher.sh run --ui-inspector` | [docs/dev/UI_INSPECTOR.md](../../docs/dev/UI_INSPECTOR.md) |
| Slow or unclear startup | `IMGSLI_STARTUP_TRACE=1 ./launcher.sh run` | `src/core/startup_trace.py` |
| Where is the code mass? | `./launcher.sh context --cloc-only` → `cloc.txt` (`--toolkit-dir DIR` if the sibling toolkit is not auto-found) | [AGENTS.md](../../AGENTS.md) |
| Missing or empty i18n keys | `python src/devtools/check_translations.py --strict` | — |
| Help screenshots missing / broken | grep body-relative image paths in `src/*/resources/help/` | [docs/dev/HELP_SYSTEM.md](../../docs/dev/HELP_SYSTEM.md) § Figure paths |
| Stale `.qsb` shaders | `python src/devtools/compile_shaders.py --check` | `src/devtools/compile_shaders.py` |
| Architecture dogma after structural change | `./launcher.sh test tests/contracts -q` | [docs/dev/CONTRACTS.md](../../docs/dev/CONTRACTS.md) |
| Focused subsystem test | `env QT_QPA_PLATFORM=offscreen pytest -q tests/<area>/…` | [docs/dev/TESTING.md](../../docs/dev/TESTING.md) |
| Layout / spacing / geometry (gaps, margins, sizes) | `./launcher.sh run --open-tab image_compare --dump-ui-layout /path/to/layout.json` — `--run-action <id>` opens other windows (Settings, Help, …) first | [docs/dev/UI_LAYOUT_DUMP.md](../../docs/dev/UI_LAYOUT_DUMP.md) |
| Anything that needs the app *driven*: reproduce a click/keyboard symptom, click a control by element id, read the Store/actions/log from a running instance, take a live screenshot | Run a private instance with `IMGSLI_CONTROL=1` and drive it over MCP (`mcp-server/app/server.py`): `ui_elements`, `ui_click`/`ui_hover`/`ui_focus`, `press_keys`, `capture_surface`, `get_state`, `list_actions`, `read_log`, `query_trace`, `jobs_list` | [docs/dev/MCP.md](../../docs/dev/MCP.md); recipe (private sibling `improve-imgsli-internal-docs`): `docs/dev/RUNBOOK_LIVE_MCP_VERIFICATION.md` |
| "A control is not reachable by keyboard" (arrows/Tab do nothing) | `ui_nav_state` (sections, focus, `owned_by_section`, open overlays) → `nav_key` (delivers the key through the app's own navigation and reports `section:<name>`/`focus`/`surface`/`unhandled`). Never judge this from Qt focus, and never from `ui_click` (in-process ⇒ fires even for unreachable widgets) | [docs/dev/MCP.md](../../docs/dev/MCP.md) § Judging keyboard reachability |

Tracer output: `~/.local/share/ImproveImgSLI/trace.jsonl`. Plain logs: `~/.local/share/ImproveImgSLI/log.txt` ([docs/dev/LOGGING.md](../../docs/dev/LOGGING.md)).

## Workflow

1. **Reproduce** with the narrowest tool (tracer or ui-inspector), not ad-hoc `logger` calls.
2. **Read** the matching `docs/dev/` page for how to filter or interpret output.
3. **Fix** in the smallest layer that owns the bug (store, presenter, plugin, canvas feature).
4. **Verify** with the same tool plus a focused test when behavior is non-obvious.

## Rules

- `context --cloc-only` is for code-size orientation only — do not expect a doc bundle.
- UI inspector is a dev diagnostic overlay, not a user-facing feature.
- Contract tests are fast AST checks — run them before large import or layout refactors.
- Known Qt quirks: `KNOWN_BUGS.md` (private sibling repo) (sharded: `docs/bugs/cases/`) before assuming a new bug.
- After moving/renaming/adding docs under `docs/` or `src/tabs/*/docs/`, run `python src/devtools/docs_link_graph.py --write-index` — a stale `DOC_INDEX.md` or a broken relative doc link fails `tests/devtools/test_docs_link_graph.py`.

## Private docs (sibling `improve-imgsli-internal-docs`)

`KNOWN_BUGS.md` and `rendering/qrhi-gotchas.md` were moved out of this public
repo into the private sibling `improve-imgsli-internal-docs` (paths mirror the
original layout). The links above point there relative to this file; on
machines without that sibling checkout the docs are simply absent — fall back
to script output and logs rather than the public repo.

## `src/devtools/` inventory

| Script | Role |
|---|---|
| `context_cloc.py` | cloc tables for app + optional sibling toolkit |
| `check_translations.py` | locale gap report (`--root`, `--reference en`, `--strict`) |
| `compile_shaders.py` | GLSL → `.qsb` (`--check`, `--clean`) |
| `ui_inspector/` | in-app widget / palette / QSS diagnostics (via `--ui-inspector`) |
| `ui_layout_dump.py` | headless widget-tree JSON dump (via `--dump-ui-layout`) |
| `docs_link_graph.py` | doc-link graph + `DOC_INDEX.md` regeneration (`--write-index`) |
