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

18 tools — 8 read-only, 10 mutating (reads and writes never share a tool):

| Tool | Kind | What it does |
|---|---|---|
| `list_actions` | read | ActionRegistry catalog (id, label, owner tab, shortcut) |
| `list_sessions` | read | workspace sessions (id, type, title, active) |
| `get_state` | read | Redux Store slice by dotted path |
| `read_log` | read | tail `log.txt`, optional level filter |
| `query_trace` | read | search `trace.jsonl` newest-first |
| `dump_ui_layout` | read | widget tree JSON (geometry, colors, bound action ids) |
| `list_surfaces` | read | capture-surface names for `capture_surface` |
| `ui_elements` | read | live inventory of interactive elements (id, role, label, rects, enabled) |
| `open_tab` | write | open/focus a tab kind (live) or launch it (fallback) |
| `run_action` | write | run one ActionRegistry id |
| `open_folder` | write | hand a folder to the gallery (live: routed) |
| `set_theme` | write | set `theme` (light/dark); live-now or persisted |
| `set_language` | write | set `language` (en/ru/zh/pt_BR) |
| `capture_surface` | write | screenshot a named surface to PNG |
| `press_keys` | write | inject keyboard combos into the running app (live-only) |
| `ui_click` | write | click an element by id, in-process (live-only) |
| `ui_hover` | write | hover an element by id, in-process (live-only) |
| `ui_focus` | write | focus an element by id, in-process (live-only) |

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
keyboard combos the Find Action catalog does not cover. `ui_elements` inventories
the live window's interactive widgets (id, role, label, widget `rect` and
screen-space `screen_rect`, `enabled`, bound action id) and
`ui_click` / `ui_hover` / `ui_focus` act on one by its session-scoped id —
in-process, at the element's centre, with an unknown id retried ~3 s and then
failed with close matches. In-process delivery fires the handler even when the
element is off-screen; only the human-visible effect needs it on screen. Both
rects are 4-number arrays; `rect` is widget-local and `screen_rect` is
screen-space (best-effort on Wayland). Mutations with no Phase-1 analogue carry
`live: true` (there is no fresh `pid` to report).

Staleness and failure are non-events for the caller: a pointer whose socket is
unusable is stale, a socket nobody listens on is "no live instance", and a
connection the app refuses or closes surfaces as a fallback — never as a
user-visible error. The pointer's `pid` is only a *hint*: a Flatpak app runs in
its own PID namespace, so the host's `kill(pid, 0)` can call a live app dead —
the server probes the socket instead and only declares staleness when nothing
answers (see [Flatpak sandbox](#flatpak-installed-app-p0)). After a transport
failure the server pauses re-attaching for a couple of seconds so a dead socket
is not retried on every call. The app refuses connections from another uid (its
own `SO_PEERCRED` check); this client only has to degrade cleanly.

### Flatpak-installed app (P0)

A host-side `mcp-server/app/server.py` **cannot attach to the app installed as a
Flatpak with the current defaults**, and no protocol change fixes that — the
blocker is the path. Inside the sandbox `$XDG_RUNTIME_DIR` is a private per-app
tmpfs mounted at the *same string* (`/run/user/1000`, observed as
`tmpfs[/.flatpak/io.github.Loganavter.Improve-ImgSLI/xdg-run]`, mode 700), so
host and app write two different `control.sock` files that happen to share a
name. Unix sockets themselves cross a *granted* path fine in both directions
(verified: a sandbox-created socket connected from the host, `SO_PEERCRED` uid
1000 on both sides).

Two things make route **A** work today with no rebuild — `flatpak override
--user --env=…` on the app, `IMGSLI_MCP_CONTROL_SOCKET` on the server:

```bash
# app side: keep the channel on and point it at the per-app data dir, whose path
# and inode are the same on both sides (Flatpak maps ~/.var/app/<id>/data into
# the sandbox; observed identical inode host vs sandbox).
flatpak override --user \
  --env=IMGSLI_CONTROL=1 \
  --env=IMGSLI_CONTROL_DIR="$HOME/.var/app/io.github.Loganavter.Improve-ImgSLI/data/ImproveImgSLI/run" \
  io.github.Loganavter.Improve-ImgSLI

# server side: name the socket explicitly (or set this env in the MCP client's
# `environment` block, next to IMGSLI_REPO_ROOT).
IMGSLI_MCP_CONTROL_SOCKET="$HOME/.var/app/io.github.Loganavter.Improve-ImgSLI/data/ImproveImgSLI/run/control.sock" \
  python3 mcp-server/app/server.py
```

The user restarts the Flatpak app with the channel enabled and sets the server
env var (or adds it to the MCP client config). No manifest change, no rebuild.

**PID namespace caveat (handled server-side).** The pointer's `pid` is
sandbox-local: a host `os.kill(pid, 0)` can raise `ProcessLookupError` for a live
sandboxed app (or `PermissionError` for an alien pid), which would make a
pid-only staleness check report "no live instance" while the socket is
connectable. `mcp-server/app/live.py` therefore treats the pid as a hint: a
pointer is stale only when the pid looks dead **and** a probe connect to the
socket fails; a socket that answers is used. The app-side
`src/core/control/discovery.py:stale_pointer_alive()` (startup single-instance
guard) is still pid-only — a leftover pointer from a crashed sandbox instance
can still make the next launch refuse, which is why route A wants an explicit
control dir and remains a documented fallback rather than the default.

Route **B** is the future zero-config end state: grant
`--filesystem=xdg-run/improve-imgsli:create` in `finish-args`, point the control
dir at `$XDG_RUNTIME_DIR/improve-imgsli`, and add that path as a discovery
candidate on both sides. The grant mechanism is verified on an installed app
(Discord's `xdg-run/pipewire-0` shows the host node at the same path with the
same inode); the app-created `:create` subdir is **not** verified yet — it needs
the manifest change and a real build. Route **C** (run the MCP server inside the
sandbox) is rejected: `build/Flatpak-template/io.github.Loganavter.Improve-ImgSLI.yaml`
installs `src/` only, so `mcp-server/` is absent from `/app`.

**Re-verify on the next Flatpak build** (recipe; nothing here builds): (1) inside
the sandbox, `findmnt -T "$XDG_RUNTIME_DIR"` must still show a private per-app
tmpfs and `$XDG_DATA_HOME`/`~/.var/app/<id>/data` the same inode as the host;
(2) with route A set, the host must see
`~/.var/app/io.github.Loganavter.Improve-ImgSLI/data/ImproveImgSLI/run/control.sock`
and `IMGSLI_MCP_CONTROL_SOCKET=… python3 mcp-server/app/server.py --check` must
answer; (3) for route B, grant the subdir and confirm a socket the sandbox
creates at `$XDG_RUNTIME_DIR/improve-imgsli` is present on the host at the same
string, then a host connect must succeed.

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
element-targeting tools (`ui_elements`, `ui_click`, `ui_hover`, `ui_focus`) are
live-only too: ids exist only in a running app, so with no instance they answer
an honest error rather than booting a throwaway app. The
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
  `annotations` (`run_action` sets `destructiveHint: true`; `press_keys` and
  `ui_click` are non-destructive but non-idempotent).
- **Keyboard input is live-only.** `press_keys` injects into the running app
  through the control socket; with no instance it answers an honest error
  rather than pretending. Key names are allowlisted app-side.
- **Element targeting is live-only.** `ui_elements` reads the running window's
  widget inventory; `ui_click`/`ui_hover`/`ui_focus` act on an id from it. With
  no instance they answer an honest error — no throwaway app is booted to fake a
  target.

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
