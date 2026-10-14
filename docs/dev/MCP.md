# MCP server (app control)

A local **Model Context Protocol** server that exposes the app to LLM agents —
the app-side counterpart to the docs MCP server. It speaks MCP revision
**`2026-07-28`** over **stdio** and also accepts the legacy `initialize`
handshake, so today's clients work unchanged.

Source: [`mcp-server/app/`](../../mcp-server/app/) — see its
[README](../../mcp-server/app/README.md) for the full surface and security model.
The catalog is declared in `mcp-server/app/catalog.py`, implemented in
`backend.py`, and transported by `protocol.py`.

```bash
python3 mcp-server/app/server.py --check    # print the declared catalog
python3 mcp-server/app/server.py            # serve on stdio
```

## Wiring

`~/.config/opencode/opencode.jsonc` → `mcpServers.app`, next to
`mcpServers.docs`:

```jsonc
{
  "mcpServers": {
    "app": {
      "type": "local",
      "command": "python3",
      "args": ["/abs/path/to/Improve-ImgSLI/mcp-server/app/server.py"],
      "environment": { "IMGSLI_REPO_ROOT": "/abs/path/to/Improve-ImgSLI" }
    }
  }
}
```

The app venv is auto-detected (`venv/bin/python` when present). Knobs:
`IMGSLI_MCP_ARTIFACTS` (scratch dir), `IMGSLI_MCP_TIMEOUT` (boot budget).

## Surface at a glance

13 tools — 7 read-only, 6 mutating (reads and writes never share a tool):

| Tool | Kind | What it does |
|---|---|---|
| `list_actions` | read | ActionRegistry catalog (id, label, owner tab, shortcut) |
| `list_sessions` | read | workspace sessions (id, type, title, active) |
| `get_state` | read | Redux Store slice by dotted path |
| `read_log` | read | tail `log.txt`, optional level filter |
| `query_trace` | read | search `trace.jsonl` newest-first |
| `dump_ui_layout` | read | widget tree JSON (geometry, colors, bound action ids) |
| `list_surfaces` | read | capture-surface names for `capture_surface` |
| `open_tab` | write | launch the app on a given tab kind |
| `run_action` | write | run one ActionRegistry id in a fresh process |
| `open_folder` | write | validate an image directory, launch the gallery |
| `set_theme` | write | persist `theme` (light/dark) |
| `set_language` | write | persist `language` (en/ru/zh/pt_BR) |
| `capture_surface` | write | screenshot a named surface to PNG |

Resources: `app://actions`, `app://state`, `app://sessions`, `app://log`,
`app://ui-layout`, `app://theme`; templates `app://action/{id}`,
`app://tab/{name}/layout`. Prompts: `diagnose_gallery`, `capture_and_inspect`.

The catalog itself is the source of truth — read it with `--check` or a
`tools/list` request rather than trusting this table.

## Phase 1: how it drives the app

There is **no channel into a running window** yet; that is Phase 2. Phase 1
composes the primitives the app already ships:

- **State/catalog/sessions** — a new read-only devtool flag,
  `python src/__main__.py --dump-app-snapshot <json>`, serializes the
  ActionRegistry catalog and Redux `Store` slices
  ([`src/devtools/app_snapshot.py`](../../src/devtools/app_snapshot.py)) and
  exits. Wired exactly like `--dump-ui-layout`. Snapshot reads are cached ~30 s.
- **Widget tree** — `--dump-ui-layout` (see [UI_LAYOUT_DUMP.md](UI_LAYOUT_DUMP.md)).
- **Log / tracer** — `log.txt` and `trace.jsonl` under the app data dir
  (see [LOGGING.md](LOGGING.md), [TRACING.md](TRACING.md)).
- **Mutations** — a detached `python src/__main__.py --open-tab … --run-action …`.
- **Screenshots** — `src/devtools/capture_surface.py` on a private Xvfb
  (see [SCREENSHOTS.md](SCREENSHOTS.md)).
- **Theme / language** — the app's own QSettings keys via a headless Qt
  subprocess; applies on next start.

**Limitations, stated plainly:** reads boot a throwaway headless app and may be
~30 s stale; mutations start a *new* process and do not affect an app that is
already open; `open_folder` validates the directory but reports
`routed: false` until Phase 2. The live QRhi/GL canvas is not capturable
headlessly (see [SCREENSHOTS.md](SCREENSHOTS.md) §Known limitation).

## Security model

- **Local only.** stdio subprocess, never TCP/HTTP; no network code.
- **Allowlisted actions.** `run_action` rejects ids absent from the
  ActionRegistry snapshot *before* launching, with close-match suggestions.
- **Existing directories only** for `open_folder`; no traversal.
- **No file contents.** Only the app's own log/tracer/catalog/layout artifacts
  are returned — never user images or arbitrary files.
- **Read-only default**; mutations are distinct named tools with honest
  `annotations` (`run_action` sets `destructiveHint: true`).

Phase 2 will add the in-app control server (`IMGSLI_CONTROL=1`, unix socket in
`$XDG_RUNTIME_DIR`, env-gated, no TCP) so `get_state`/`list_sessions`/
`run_action`/`set_*` act on the live window and event subscriptions are
possible. It is **out of scope** for this server.

## The `mcp` SDK

`mcp-server/requirements.txt` pins `mcp>=2.3` (verified to support
`2026-07-28`). It is optional: `mcp-server/app/protocol.py` implements the
stdio JSON-RPC surface with the standard library only, because this
environment's Python is PEP 668 externally-managed with root-owned
site-packages. The catalog/backend are transport-agnostic and can be registered
with the SDK's low-level `Server` unchanged.

## See also

- [mcp-server/app/README.md](../../mcp-server/app/README.md) — full surface + wiring
- [TRACING.md](TRACING.md) — the causal tracer `query_trace` reads
- [LOGGING.md](LOGGING.md) — `log.txt` layout `read_log` parses
- [UI_LAYOUT_DUMP.md](UI_LAYOUT_DUMP.md) — the widget-tree dump
- [SCREENSHOTS.md](SCREENSHOTS.md) — Xvfb requirements for `capture_surface`
