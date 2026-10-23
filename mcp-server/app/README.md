# Improve-ImgSLI app MCP server

A **local stdio MCP server** that lets an LLM agent drive and inspect the
Improve-ImgSLI desktop app: list/run Find Actions, open tabs, read Store
settings and workspace sessions, dump the widget tree, tail the log, query the
causal tracer, screenshot devtool surfaces, and inventory / click / hover /
focus UI elements by id in the live window.

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

**Tools** (31 — 12 read-only, 19 mutating; reads and writes never share a tool):
`list_actions`, `list_sessions`, `get_state`, `read_log`, `query_trace`,
`dump_ui_layout`, `list_surfaces`, `ui_elements`, `ui_nav_state`, `jobs_list`,
`wait_for` ·
`open_tab`, `run_action`, `set_scene_commands`, `open_folder`, `open_file`, `open_properties`,
`set_theme`, `set_language`, `set_setting`, `capture_surface`, `press_keys`,
`nav_key`, `ui_click`, `ui_hover`, `ui_focus`, `ui_press`, `ui_wheel`, `ui_batch`,
`jobs_cancel`. The four
element-targeting tools (`ui_elements`, `ui_click`, `ui_hover`, `ui_focus`),
`ui_press`, `ui_wheel`, the keyboard pair (`nav_key` + `ui_nav_state`), the two job tools
(`jobs_list`, `jobs_cancel`), `wait_for` and `open_properties` are live-only
(`open_file` refuses without a running tab; `set_setting` still persists the
value for the next start; `ui_batch` answers per item and is as live-only as the
items it runs).

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
control dir with a pointer file `instance.json` (`{pid, socket, version, uid}`)
beside it. Discovery order: `IMGSLI_MCP_CONTROL_SOCKET` →
`IMGSLI_CONTROL_DIR` → `$XDG_RUNTIME_DIR` only when it is private (owned by you,
no group/other access — a `0755` runtime dir is refused by both sides), else the
app data dir's `run/`; a pointer carrying a foreign `uid` counts as "no live
instance". One newline-delimited JSON request
`{"id", "method", "params"}` per call, answered by
`{"id", "ok": true, "result"}` or `{"id", "ok": false, "error", "hint"}`. On
this path the tools act on the window the user is driving (`open_folder` really
routes, `set_theme`/`set_language` apply now, `press_keys` injects keys, and
`ui_elements`/`ui_click`/`ui_hover`/`ui_focus` inventory and target the live
widgets); a stale pointer or a socket nobody listens on is "no live instance",
and a refused/closed connection just falls back — never a user-visible error.
Mutations with no fallback analogue carry `live: true`.

**Mutation contract (reads retry once, edits never).** Reads retry exactly once
on a transport timeout; mutations never auto-retry. The two failure kinds stay
distinguishable in the text — **"not sent"** (nothing left the process) vs
**"sent, no reply"** (the request was written, the deadline expired). A mutating
tool whose request was already on the wire is *not* retried and does not fall
back to a fresh process: it answers `isError` with "the operation may have
completed" so an agent re-reads state instead of double-applying the edit.
`list_actions` rows carry `enabled` + `reason` (degrading to `true`/`null` when
the app omits them) so a precondition can be planned around.

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
attach); `open_folder` reports `routed: false` (it opens `--open-tab <tab>` when
one was named); `press_keys` has no fallback and
errors honestly, and so do the element-targeting tools (`ui_elements`,
`ui_click`, `ui_hover`, `ui_focus`) and the job tools (`jobs_list`,
`jobs_cancel`) — element ids and in-flight jobs only exist in a running app.

## Jobs (long work)

`jobs_list` reads the app's in-flight long passes and `jobs_cancel` stops one
where a real cancel exists. Both are **live-only**, and both report only what
the app already knows — no invented percentage.

| kind | progress from | cancel |
|---|---|---|
| `gallery_pool` | `GalleryController.sched_stats()` (active/pending/queued) + per-item `thumbnail_status` | no |
| `metrics_pass` | the controller's own `_proxy_done` / `_proxy_total` chunk counters | no |
| `ai_analysis` | per-item `analysis_status` (aggregated) | no |
| `export` | the save task's toast progress bar, when the toast manager is materialized | **yes** |

`jobs_cancel {id}` sets the export task's own `threading.Event` — the same
handle the toast's Cancel button sets, honored by `ExportService` and by
`write_pil_image_cancelable` (atomic tmp+replace, the tmp is removed on abort, so
no partial artifact reaches the output path). Every other kind answers a named
refusal; an unknown or already-settled id is an error.

**`notifications/progress` is not carried.** This server is stdio
request/response (`app/protocol.py`) and emits no server→client notifications,
so it cannot push progress without faking it. The honest substitute is to poll
`jobs_list` while a long tool call is pending. (Recorded as a gap, not a
feature.)

**`elapsed_s` is a lower bound.** The app does not stamp a start time for these
passes, so it measures from the first `jobs_list` that observed the job running;
`null` means "not yet observed running". It is never back-dated.

## Security model

- **Local only.** stdio subprocess; never TCP/HTTP. No network code exists.
- **Allowlisted actions.** On the fallback path `run_action` rejects any id not
  present in the headless ActionRegistry snapshot *before* launching, and
  suggests the closest ids; on the live path the app validates its own ids. No
  arbitrary command, path, or Python evaluation is possible.
- **Existing directories only** for `open_folder`; no path traversal. Pass
  `tab=<kind>` to target one tab (it is opened if absent); a file-only tab
  (`multi_compare`) receives the folder's images as files, which is the
  supported way to load images there — its "add images" dialog is not
  drivable by a client.
- **No file contents.** Only the app's own log, tracer, catalog, and layout
  artifacts are returned — never user images or arbitrary files.
- **Read-only default.** Every mutating tool is a distinct, explicitly named
  tool with honest `annotations` (`run_action` advertises
  `destructiveHint: true`; `press_keys` and `ui_click` are destructive-free but
  not idempotent).
- **Keyboard input is live-only.** `press_keys` injects combos into the running
  app through the control socket (key names allowlisted app-side); with no
  instance it answers an honest error instead of pretending.
  `target=<element id from ui_elements>` aims the keys at one widget — a live
  canvas is not in the window's focus chain, so its zoom/pan keys
  (`=`, `-`, `0` in multi-compare) only arrive when the canvas id is named.
- **Element targeting is live-only.** `ui_elements` inventories the running
  window's interactive widgets and `ui_click`/`ui_hover`/`ui_focus` act on them
  by session-scoped id; with no instance they answer an honest error — they
  never boot a throwaway app to fake a target.
- **Keyboard reachability is measurable (live-only).** `ui_nav_state` reads the
  app's own keyboard-navigation model (ordered sections, focus, and each open
  overlay's focusable children with `owned_by_section`), and `nav_key` presses a
  key through that model, reporting which layer took it (`section:<name>` /
  `focus` / `unhandled`). Use them instead of judging reachability from
  `ui_click`, which delivers in-process and therefore fires handlers for widgets
  a real mouse or keyboard cannot reach.
- **Job state is live-only.** `jobs_list`/`jobs_cancel` read the running app's
  own counters and its one real cancel (export); with no instance they answer an
  honest error instead of an empty list that would read as "nothing running".
- **Cancel is never faked.** `jobs_cancel` may only stop kinds with a
  cooperative cancel (today: `export`); anything else is a named refusal — the
  gallery pool, the metrics pass and the AI pass have no cancel to call.
- **Refusals are named, never truncated.** Unknown MCP method (`-32601`) and an
  over-cap request line (`-32600`, 1 MiB) are refused by the transport; an
  unknown control method, a foreign-uid peer (closed before a byte is read), and
  a not-open surface are refused by the live app; a non-live `press_keys` / `ui_*`
  / `jobs_*` and an unknown action id / tab / state path / surface / job id or an
  uncancellable job kind are refused by the server with close-match hints. Full
  table in [docs/dev/MCP.md](../../docs/dev/MCP.md).
- **Annotations audited (2026-10-17; counts refreshed 2026-10-21).** The twelve
  read-only tools really read (no state touched, `readOnlyHint: true`,
  `jobs_list` and `get_canvas_scene` included); the seventeen
  mutating tools are honestly marked (`run_action` = `destructiveHint: true`;
  `press_keys`/`ui_click`/`ui_press`/`jobs_cancel` = non-destructive but
  non-idempotent; `ui_hover`/`ui_focus` idempotent). No over- or under-statement
  was found; the suite pins the classification.

## Known limitations

- **`ui_click {button: right}` hides the menu it just opened (P1 tool defect).**
  A right-click by element id sends the mouse button event *plus* an extra
  `QContextMenuEvent`, which consumes the menu manager's open-click grace and
  collapses the menu ~150 ms later. The handler still runs; only the visible
  menu life is wrong. The fix belongs to the gallery / control-element lane.
- A **live** capture composites each visible canvas frame (the swapchain
  surface is in neither grab path), so a canvas does show its content; a
  devtool-booted surface still cannot grab the live QRhi/GL canvas.

## The optional MCP SDK

`requirements.txt` pins the official Python SDK (`mcp>=2.3`, which supports
`2026-07-28`). It is **not required**: the transport in `app/protocol.py` is
stdlib-only and is what runs here. The SDK is not installable in an environment
whose Python is PEP 668 externally-managed with root-owned site-packages — the
shipped transport is the spec's sanctioned fallback. The catalog/backend are
transport-agnostic, so a future install can register them with the SDK's
low-level `Server` unchanged.
