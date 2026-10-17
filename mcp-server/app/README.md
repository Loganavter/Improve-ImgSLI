# Improve-ImgSLI app MCP server

A **local stdio MCP server** that lets an LLM agent drive and inspect the
Improve-ImgSLI desktop app: list/run Find Actions, open tabs, read Store
settings and workspace sessions, dump the widget tree, tail the log, query the
causal tracer, screenshot devtool surfaces.

Speaks MCP spec revision **`2026-07-28`** (stateless per-request envelope,
`server/discover`, cacheable list results) and also accepts the legacy
`initialize` handshake so today's clients work unchanged.

```
python3 mcp-server/app/server.py            # serve on stdio
python3 mcp-server/app/server.py --check    # print the declared catalog, exit
```

## Wiring

`~/.config/opencode/opencode.jsonc` (or any MCP client), next to the docs
server:

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

The app's own venv is picked up automatically when `venv/bin/python` exists, so
no manual `PYTHONPATH` is needed. Environment knobs:

| Variable | Meaning | Default |
|---|---|---|
| `IMGSLI_REPO_ROOT` | checkout root the server drives | derived from `server.py` |
| `IMGSLI_MCP_ARTIFACTS` | scratch dir for snapshots / dumps / captures | `$XDG_CACHE_HOME/ImproveImgSLI/mcp` |
| `IMGSLI_MCP_TIMEOUT` | headless boot budget (seconds) | `120` |
| `IMGSLI_MCP_CONTROL_SOCKET` | explicit live-instance socket path | (discovery) |
| `IMGSLI_CONTROL_DIR` | explicit control dir to discover in | (discovery) |
| `IMGSLI_MCP_DISPLAY` | opt-in private display for a visible fallback window | headless |

## Surface

**Tools** (14 — 7 read-only, 7 mutating; reads and writes never share a tool):
`list_actions`, `list_sessions`, `get_state`, `read_log`, `query_trace`,
`dump_ui_layout`, `list_surfaces` · `open_tab`, `run_action`, `open_folder`,
`set_theme`, `set_language`, `capture_surface`, `press_keys` (live-only).

**Resources**: `app://actions`, `app://state`, `app://sessions`, `app://log`,
`app://ui-layout`, `app://theme`; templates `app://action/{id}`,
`app://tab/{name}/layout`.

**Prompts**: `diagnose_gallery`, `capture_and_inspect`.

Full catalog with annotations: `server.py --check`, or
[docs/dev/MCP.md](../../docs/dev/MCP.md).

## How it reaches the app

Every tool answers from the **live instance** when one is running, else from a
headless fallback. Results say which path answered: `"source": "live"` or
`"source": "fallback"`.

**Live attach.** The app's control server is a unix socket `control.sock` in a
control dir with a pointer file `instance.json` (`{pid, socket, started,
version}`) beside it. Discovery order: `IMGSLI_MCP_CONTROL_SOCKET` →
`IMGSLI_CONTROL_DIR` → `$XDG_RUNTIME_DIR` (when set and writable), else the app
data dir's `run/`. One newline-delimited JSON request
`{"id", "method", "params"}` per call, answered by
`{"id", "ok": true, "result"}` or `{"id", "ok": false, "error", "hint"}`. On
this path the tools act on the window the user is driving (`open_folder` really
routes, `set_theme`/`set_language` apply now, `press_keys` injects keys); a
stale pointer or a socket nobody listens on is "no live instance", and a
refused/closed connection just falls back — never a user-visible error.
Mutations with no fallback analogue carry `live: true`.

**Fallback (no live instance)** uses the primitives the app already ships:

| Need | Path |
|---|---|
| action catalog, Store slices, sessions | `python src/__main__.py --dump-app-snapshot <json>` (read-only, ~4 s, cached 30 s) |
| widget tree | `python src/__main__.py --open-tab <tab> --dump-ui-layout <json>` |
| log / tracer | `$XDG_DATA_HOME/ImproveImgSLI/{log.txt,trace.jsonl}` read directly |
| tabs / actions | detached `python src/__main__.py --open-tab <tab> --run-action <id>` |
| screenshots | `python src/devtools/capture_surface.py <surface> --out <dir>` (private Xvfb) |
| theme / language | the app's own QSettings keys (`theme`, `language`) via a headless Qt subprocess |

Fallback safety rules (`app/process_policy.py`):

- **Headless by default.** `QT_QPA_PLATFORM=offscreen` with `DISPLAY`,
  `WAYLAND_DISPLAY` and `XDG_SESSION_TYPE` scrubbed, so a boot cannot land a
  window on the user's desktop; `IMGSLI_MCP_DISPLAY` (a private `:97` Xvfb) is
  the explicit opt-in for a visible window.
- **No duplicate windows.** `open_tab` reuses the tab's live fallback process
  (`reused: true`) instead of spawning a second one.
- **The live log survives.** A boot truncates `log.txt`, so it is copied to the
  artifacts dir (`live-log.txt`) before any boot while a live instance is
  attached, and `read_log` serves that copy.

**Fallback limits:** reads boot a throwaway app and can be ~30 s stale;
mutations start a *new* process (they reach a running window only via live
attach); `open_folder` reports `routed: false`; `press_keys` has no fallback and
errors honestly.

## Security model

- **Local only.** stdio subprocess; never TCP/HTTP. No network code exists.
- **Allowlisted actions.** On the fallback path `run_action` rejects any id not
  present in the headless ActionRegistry snapshot *before* launching, and
  suggests the closest ids; on the live path the app validates its own ids. No
  arbitrary command, path, or Python evaluation is possible.
- **Existing directories only** for `open_folder`; no path traversal.
- **No file contents.** Only the app's own log, tracer, catalog, and layout
  artifacts are returned — never user images or arbitrary files.
- **Read-only default.** Every mutating tool is a distinct, explicitly named
  tool with honest `annotations` (`run_action` advertises
  `destructiveHint: true`; `press_keys` is destructive-free but not idempotent).
- **Keyboard input is live-only.** `press_keys` injects combos into the running
  app through the control socket (key names allowlisted app-side); with no
  instance it answers an honest error instead of pretending.

## The optional MCP SDK

`requirements.txt` pins the official Python SDK (`mcp>=2.3`, which supports
`2026-07-28`). It is **not required**: the transport in `app/protocol.py` is
stdlib-only and is what runs here. The SDK is not installable in an environment
whose Python is PEP 668 externally-managed with root-owned site-packages — the
shipped transport is the spec's sanctioned fallback. The catalog/backend are
transport-agnostic, so a future install can register them with the SDK's
low-level `Server` unchanged.
