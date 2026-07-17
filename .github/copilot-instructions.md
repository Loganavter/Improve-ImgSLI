# GitHub Copilot — Improve-ImgSLI

Read these before suggesting or applying changes:

1. [AGENTS.md](../AGENTS.md) — agent guide: architecture dogmas, area routing, tooling, tests
2. [docs/dev/README.md](../docs/dev/README.md) — cheat sheet for humans and agents (misconceptions, stack, task index)

Hard rules (do not bypass):

- State changes: `Dispatcher.dispatch` → `RootReducer.reduce`; never mutate `Store` fields directly.
- Toolkit widgets: painter pipeline only — no raw `QFormLayout`/`QVBoxLayout` construction blocks, no QSS on toolkit widgets.
- New workspace mode: self-contained `src/tabs/<name>/` implementing `TabContract` — not logic in `core/`.
- Rendering parity: live canvas, export preview, final export, and video snapshots must stay visually consistent.
- User-visible changes: update i18n and in-app Help in the same task.

Quick checks:

```bash
./launcher.sh test tests/contracts -q    # architectural dogmas (AST, fast)
env QT_QPA_PLATFORM=offscreen pytest -q tests/<area>/<test>.py
./launcher.sh context --cloc-only        # code-size stats only → cloc.txt
```

Docs are in the repo (`docs/dev/`, `AGENTS.md`) — read/search them directly; no bundled doc dump needed.

Debugging runtime chains: [docs/dev/TRACING.md](../docs/dev/TRACING.md) (`IMGSLI_TRACE=1` or `./launcher.sh run --debug`).
