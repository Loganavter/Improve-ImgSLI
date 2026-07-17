---
name: imgsli-devtools
description: Runs Improve-ImgSLI developer tools for debugging and validation. Use when investigating runtime UI bugs, trace chains, theme or QSS mismatches, translation gaps, stale shaders, startup timing, codebase size questions, or before large refactors.
---

# Improve-ImgSLI devtools

Pick a tool by symptom. Read the linked doc only when you need filtering or interpretation details.

## Symptom → tool

| Symptom | Command | Doc |
|---|---|---|
| Weird after click / zoom / state change | `./launcher.sh run --debug` or `IMGSLI_TRACE=1 ./launcher.sh run` | [docs/dev/TRACING.md](../../../docs/dev/TRACING.md) |
| Widget color / palette / theme token / QSS candidate | `./launcher.sh run --ui-inspector` | [docs/dev/UI_INSPECTOR.md](../../../docs/dev/UI_INSPECTOR.md) |
| Slow or unclear startup | `IMGSLI_STARTUP_TRACE=1 ./launcher.sh run` | `src/core/startup_trace.py` |
| Where is the code mass? | `./launcher.sh context --cloc-only` → `cloc.txt` | [AGENTS.md](../../../AGENTS.md) |
| Missing or empty i18n keys | `python src/devtools/check_translations.py --strict` | — |
| Stale `.qsb` shaders | `python src/devtools/compile_shaders.py --check` | `src/devtools/compile_shaders.py` |
| Architecture dogma after structural change | `./launcher.sh test tests/contracts -q` | [docs/dev/CONTRACTS.md](../../../docs/dev/CONTRACTS.md) |
| Focused subsystem test | `env QT_QPA_PLATFORM=offscreen pytest -q tests/<area>/…` | [docs/dev/TESTING.md](../../../docs/dev/TESTING.md) |

Tracer output: `~/.local/share/ImproveImgSLI/trace.jsonl`. Plain logs: `~/.local/share/ImproveImgSLI/log.txt` ([docs/dev/LOGGING.md](../../../docs/dev/LOGGING.md)).

## Workflow

1. **Reproduce** with the narrowest tool (tracer or ui-inspector), not ad-hoc `logger` calls.
2. **Read** the matching `docs/dev/` page for how to filter or interpret output.
3. **Fix** in the smallest layer that owns the bug (store, presenter, plugin, canvas feature).
4. **Verify** with the same tool plus a focused test when behavior is non-obvious.

## Rules

- `context --cloc-only` is for code-size orientation only — do not expect a doc bundle.
- UI inspector is a dev diagnostic overlay, not a user-facing feature.
- Contract tests are fast AST checks — run them before large import or layout refactors.
- Known Qt quirks: [docs/dev/KNOWN_BUGS.md](../../../docs/dev/KNOWN_BUGS.md) before assuming a new bug.

## `src/devtools/` inventory

| Script | Role |
|---|---|
| `context_cloc.sh` | cloc tables for app + optional sibling toolkit |
| `check_translations.py` | locale gap report (`--root`, `--reference en`, `--strict`) |
| `compile_shaders.py` | GLSL → `.qsb` (`--check`, `--clean`) |
| `ui_inspector/` | in-app widget / palette / QSS diagnostics (via `--ui-inspector`) |
