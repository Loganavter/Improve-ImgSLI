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
`IMGSLI_MCP_ARTIFACTS` (scratch dir), `IMGSLI_MCP_TIMEOUT` (boot budget),
`IMGSLI_MCP_CONTROL_SOCKET` / `IMGSLI_CONTROL_DIR` (which live instance to
attach to), `IMGSLI_MCP_DISPLAY` (opt-in private display for a visible
fallback window, e.g. `:97`).

## Surface at a glance

14 tools — 7 read-only, 7 mutating (reads and writes never share a tool):

| Tool | Kind | What it does |
|---|---|---|
| `list_actions` | read | ActionRegistry catalog (id, label, owner tab, shortcut) |
| `list_sessions` | read | workspace sessions (id, type, title, active) |
| `get_state` | read | Redux Store slice by dotted path |
| `read_log` | read | tail `log.txt`, optional level filter |
| `query_trace` | read | search `trace.jsonl` newest-first |
| `dump_ui_layout` | read | widget tree JSON (geometry, colors, bound action ids) |
| `list_surfaces` | read | capture-surface names for `capture_surface` |
| `open_tab` | write | open/focus a tab kind (live) or launch it (fallback) |
| `run_action` | write | run one ActionRegistry id |
| `open_folder` | write | hand a folder to the gallery (live: routed) |
| `set_theme` | write | set `theme` (light/dark); live-now or persisted |
| `set_language` | write | set `language` (en/ru/zh/pt_BR) |
| `capture_surface` | write | screenshot a named surface to PNG |
| `press_keys` | write | inject keyboard combos into the running app (live-only) |

Resources: `app://actions`, `app://state`, `app://sessions`, `app://log`,
`app://ui-layout`, `app://theme`; templates `app://action/{id}`,
`app://tab/{name}/layout`. Prompts: `diagnose_gallery`, `capture_and_inspect`.

The catalog itself is the source of truth — read it with `--check` or a
`tools/list` request rather than trusting this table.

## How it drives the app

Every tool answers from the **live instance** when one is running, and falls
back to the headless Phase-1 path when none is. Results say which path answered
(`"source": "live"` or `"source": "fallback"`).

### Live attach (preferred)

The app runs a control server on a unix socket `control.sock` inside a control
dir, with a pointer file `instance.json` (`{pid, socket, started, version}`)
beside it. Discovery order, highest priority first:

1. `IMGSLI_MCP_CONTROL_SOCKET` — an explicit socket path;
2. `IMGSLI_CONTROL_DIR` — an explicit control dir;
3. `$XDG_RUNTIME_DIR` when set and writable, else `<app data dir>/run`
   (`~/.local/share/ImproveImgSLI/run`).

One tool call is one newline-delimited JSON request
(`{"id", "method", "params"}`) answered by
`{"id", "ok": true, "result"}` or
`{"id", "ok": false, "error", "hint"}`. On this path the tools act on the window
the user is driving: `open_tab` switches in place, `run_action` runs live,
`open_folder` really routes the folder (`routed: true`), `set_theme` /
`set_language` apply now (`applies_on: "now"`), and `press_keys` injects
keyboard combos the Find Action catalog does not cover. Mutations with no
Phase-1 analogue carry `live: true` (there is no fresh `pid` to report).

Staleness and failure are non-events for the caller: a pointer whose pid is dead
is stale, a socket nobody listens on is "no live instance", and a connection
the app refuses or closes surfaces as a fallback — never as a user-visible
error. After a transport failure the server pauses re-attaching for a couple of
seconds so a dead socket is not retried on every call. The app refuses
connections from another uid (its own `SO_PEERCRED` check); this client only has
to degrade cleanly.

### Fallback (Phase 1: no live instance)

Phase 1 composes the primitives the app already ships:

- **State/catalog/sessions** — a read-only devtool flag,
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

Fallback safety rules (`mcp-server/app/process_policy.py`):

- **Headless by default.** A fallback boot gets
  `QT_QPA_PLATFORM=offscreen` with `DISPLAY`, `WAYLAND_DISPLAY` and
  `XDG_SESSION_TYPE` scrubbed, so it can never land a window on the user's
  desktop. (On this machine's Wayland session Qt ignores `DISPLAY` unless `xcb`
  is forced, which is exactly how a fallback spawn once opened a window on the
  live desktop.) `IMGSLI_MCP_DISPLAY` (a private `:97` Xvfb) is the explicit
  opt-in for a visible fallback window.
- **No duplicate windows.** `open_tab` reuses the tab's live fallback process —
  the result gains `reused: true` instead of spawning a second window.
- **The live log survives.** A boot truncates `log.txt`, so the server copies it
  to the artifacts dir (`live-log.txt`) before any boot while a live instance is
  attached, and `read_log` serves that preserved copy.

**Limitations, stated plainly:** fallback reads boot a throwaway headless app
and may be ~30 s stale; fallback mutations start a *new* process (they affect a
running window only through live attach); fallback `open_folder` reports
`routed: false`, so the folder must be dropped on the gallery. `press_keys` is
**live-only** — with no instance it errors honestly, it never fakes input. The
live QRhi/GL canvas is not capturable headlessly (see
[SCREENSHOTS.md](SCREENSHOTS.md) §Known limitation).

## Security model

- **Local only.** stdio subprocess, never TCP/HTTP; no network code.
- **Allowlisted actions.** `run_action` rejects ids absent from the
  ActionRegistry snapshot *before* launching, with close-match suggestions.
- **Existing directories only** for `open_folder`; no traversal.
- **No file contents.** Only the app's own log/tracer/catalog/layout artifacts
  are returned — never user images or arbitrary files.
- **Read-only default**; mutations are distinct named tools with honest
  `annotations` (`run_action` sets `destructiveHint: true`; `press_keys` is
  non-destructive but non-idempotent).
- **Keyboard input is live-only.** `press_keys` injects into the running app
  through the control socket; with no instance it answers an honest error
  rather than pretending. Key names are allowlisted app-side.

The live channel is the in-app control server: a unix socket in the control dir
(env-gated, no TCP), refusing connections from other uids. Reads and mutations
on a live instance are the same tools — the answering path is visible in every
result as `source`.

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
