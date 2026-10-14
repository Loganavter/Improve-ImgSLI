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
| `IMGSLI_MCP_ARTIFACTS` | scratch dir for snapshots / dumps / captures | `$XDG_CACHE_HOME/Improve-ImgSLI/mcp` |
| `IMGSLI_MCP_TIMEOUT` | headless boot budget (seconds) | `120` |

## Surface

**Tools** (13 — 7 read-only, 6 mutating; reads and writes never share a tool):
`list_actions`, `list_sessions`, `get_state`, `read_log`, `query_trace`,
`dump_ui_layout`, `list_surfaces` · `open_tab`, `run_action`, `open_folder`,
`set_theme`, `set_language`, `capture_surface`.

**Resources**: `app://actions`, `app://state`, `app://sessions`, `app://log`,
`app://ui-layout`, `app://theme`; templates `app://action/{id}`,
`app://tab/{name}/layout`.

**Prompts**: `diagnose_gallery`, `capture_and_inspect`.

Full catalog with annotations: `server.py --check`, or
[docs/dev/MCP.md](../../docs/dev/MCP.md).

## How Phase 1 reaches the app

There is no live channel into a running window — that is the **Phase 2** in-app
control socket (env-gated unix socket, out of scope here). Phase 1 uses the
primitives the app already ships:

| Need | Path |
|---|---|
| action catalog, Store slices, sessions | `python src/__main__.py --dump-app-snapshot <json>` (new devtool flag, read-only, ~4 s, cached 30 s) |
| widget tree | `python src/__main__.py --open-tab <tab> --dump-ui-layout <json>` |
| log / tracer | `$XDG_DATA_HOME/ImproveImgSLI/{log.txt,trace.jsonl}` read directly |
| tabs / actions | detached `python src/__main__.py --open-tab <tab> --run-action <id>` |
| screenshots | `python src/devtools/capture_surface.py <surface> --out <dir>` (private Xvfb) |
| theme / language | the app's own QSettings keys (`theme`, `language`) via a headless Qt subprocess |

**Fresh-process limitation (documented, not hidden):** each read boots a
throwaway headless app, and each mutation starts a *new* app process. Reads can
be up to ~30 s stale (snapshot cache); mutations do not affect an app the user
already has open. `open_folder` validates the directory but reports
`routed: false` until Phase 2 can inject it into a running gallery.

## Security model

- **Local only.** stdio subprocess; never TCP/HTTP. No network code exists.
- **Allowlisted actions.** `run_action` rejects any id not present in the
  headless ActionRegistry snapshot *before* launching, and suggests the closest
  ids. No arbitrary command, path, or Python evaluation is possible.
- **Existing directories only** for `open_folder`; no path traversal.
- **No file contents.** Only the app's own log, tracer, catalog, and layout
  artifacts are returned — never user images or arbitrary files.
- **Read-only default.** Every mutating tool is a distinct, explicitly named
  tool with honest `annotations` (`run_action` advertises
  `destructiveHint: true`); `set_theme`/`set_language` write exactly one scalar
  QSettings key each.

## The optional MCP SDK

`requirements.txt` pins the official Python SDK (`mcp>=2.3`, which supports
`2026-07-28`). It is **not required**: the transport in `app/protocol.py` is
stdlib-only and is what runs here. The SDK is not installable in an environment
whose Python is PEP 668 externally-managed with root-owned site-packages — the
shipped transport is the spec's sanctioned fallback. The catalog/backend are
transport-agnostic, so a future install can register them with the SDK's
low-level `Server` unchanged.
