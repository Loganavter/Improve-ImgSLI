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

23 tools — 11 read-only, 12 mutating (reads and writes never share a tool):

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
| `ui_nav_state` | read | live keyboard-navigation model: sections + focus + overlay children no section owns (live-only) |
| `jobs_list` | read | live in-flight long passes (kind, status, progress, elapsed_s, message) |
| `wait_for` | read | block until one expectation holds (element id visible+enabled, role+label exists, or jobs settle); a timeout returns the last observed state (live-only) |
| `open_tab` | write | open/focus a tab kind (live) or launch it (fallback) |
| `run_action` | write | run one ActionRegistry id |
| `open_folder` | write | hand a folder to a tab (`tab=` targets one; live: routed) |
| `set_theme` | write | set `theme` (light/dark); live-now or persisted |
| `set_language` | write | set `language` (en/ru/zh/pt_BR) |
| `capture_surface` | write | screenshot a named surface or the live active window to PNG |
| `press_keys` | write | inject keyboard combos (`target=` aims them at one element) |
| `nav_key` | write | press keys through the app's own navigation sections and report what took them (live-only) |
| `ui_click` | write | click an element by id, in-process (live-only) |
| `ui_hover` | write | hover an element by id, in-process (live-only) |
| `ui_focus` | write | focus an element by id, in-process (live-only) |
| `jobs_cancel` | write | cancel a running job by id — real cancel, or a named refusal (live-only) |

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

### Judging keyboard reachability (`ui_nav_state` + `nav_key`)

The app's keyboard cursor is **not** `QApplication.focusWidget()`. Arrow keys
belong to `sli_ui_toolkit`'s `NavigationManager`, which keeps an ordered list of
*sections* (title bar → tab strip → session picker → a tab's toolbar/grid rows)
and hands a key to the section whose `owns()` accepts the focused widget; whole
surfaces (the Quick Look overlay, flyouts) instead handle keys in their own
`keyPressEvent` and are owned by no section. `press_keys` cannot judge that
model: it aims one event at one widget (right for a canvas, whose shortcuts are
not in the focus chain) and its events carry no focus attribution, so the
sections never engage and "the key reached the control" is indistinguishable
from "the key went nowhere".

Two tools close that gap; both are **live-only**:

| Call | What it answers |
|---|---|
| `ui_nav_state {}` | the model itself: ordered `sections` (section + owner + `extra_keys`), `focus`, `last_keyboard_focus`, `modality`, and every open in-window `overlays` entry with its focusable `children` — each child carrying `owned_by_section` (`null` = Qt could focus it, no section drives it: the honest "a key cannot reach this" signal) and `keyboard_ring` (the toolkit's own cursor-visibility flag) |
| `nav_key {keys, anchor?}` | what a key *does*: the event goes to the widget a user's key would reach (optionally focusing `anchor=<element id>` first, with the app's own focus-reason policy) and travels through the app's real filters; each `steps[]` entry reports `handled` — `section:<name>` (a navigation section acted), `focus` (Qt moved focus, no section), `surface` (the widget/surface's own `keyPressEvent` took it without moving focus), `unhandled` (the key was lost) — plus `accepted`, `focus_before`/`focus_after` and the owner before/after. `activated: false` means the app window could not be made OS-active, so the measurement describes an app a real keyboard could not reach either |

Reachability is therefore *measured*, not assumed: `ui_nav_state` shows which
controls no section owns, and `nav_key` shows whether a key aimed at one of
them changes anything (an `unhandled` step is the evidence, not a guess). Do not
substitute `ui_click` for this judgement — it delivers in-process, so it fires
a handler even for a widget a real mouse or keyboard cannot reach. Conversely,
`ui_click`'s in-process path cannot *reveal* a keyboard gap: after the 2026-10-17
gallery session, `nav_key` is the only honest instrument for it (20/20 Quick
Look children unowned, `Down` unhandled at the action row, `Tab` moving focus
without a section).

`nav_key` measures the anchor's **window**, not always the main one. When an
`anchor` (also accepted as `from` / `element_id`) is given, the keys are
delivered in that widget's own top-level window — a dialog such as Settings or
Help registers its own sections and keeps its own focus chain, so a
dialog-anchored `Down` reports the *dialog's* section, where delivering to the
main window reported `section:SessionPickerSection` and moved focus inside the
main window instead. `window_source` in the result says which window was driven:
`"anchor"` (the anchor's own top-level), `"main"` (no anchor — the historical
target, unchanged for existing callers), or `"main-fallback"` (the anchor's
window disappeared mid-call). The `window` field describes that window in the
same row shape as `anchor`/`focus`, so a `handled` verdict is always attributable
to one window; an id that resolves to no widget in this instance still fails the
way it always has rather than falling back to the main window.

### Jobs: watching and stopping the long passes (P3)

`jobs_list` and `jobs_cancel` expose the passes that take minutes. Both are
**live-only** (in-flight work is in-memory state of a running app) and both
report only what the app already keeps — never a fabricated percentage.

`jobs_list` returns `{count, jobs: [{id, kind, status, progress, elapsed_s,
message}]}` with one row per *active* pass (an idle pass is absent — an empty
list really means nothing is running). Kinds, in priority order:

| kind | progress from | cancel safe? |
|---|---|---|
| `gallery_pool` | `GalleryController.sched_stats()` (`active`/`pending`/`queued`) + each item's `thumbnail_status` (`{done, total}`) | no |
| `metrics_pass` | the controller's own `_proxy_done` / `_proxy_total` chunk counters (`{done, total}` — the same numbers the app feeds `widget.set_background_scanning`) | no |
| `ai_analysis` | per-item `analysis_status` aggregated (`{done, total}` — there is no batch object) | no |
| `export` | the save task's toast progress bar (0–1 float) when the toast manager is already materialized; `null` otherwise | **yes** |

`status` is `running` or `paused` (the gallery's background thumb lane pauses
while the page is hidden). `progress` is `{done, total}` or a 0–1 float, or
`null` when the app reports no total — the honest alternative to inventing one.

**`elapsed_s` is a lower bound.** The app stamps no start time for these passes,
so it measures from the first `jobs_list` that saw the job running (app-process
scoped) and is `null` until then. It is never back-dated.

**`jobs_cancel {id}` — the real cancel, or a named refusal.** Only `export` has
a cooperative cancel today: the id names one in-flight save task, and the cancel
sets that task's own `threading.Event` — the same handle the toast's Cancel
button sets. `ExportService` checks it at each checkpoint and
`write_pil_image_cancelable` writes atomically (tmp + `os.replace`), removing
its tmp file on abort, so a cancelled export leaves **no partial artifact** at
the output path. A cancel-requested entry is then dropped from `jobs_list`
immediately rather than lingering as a "cancelling" zombie (the coordinator's
own registry entry survives until shutdown on the one worker shape that swallows
the cancel sentinel and returns `None` — an app-side follow-up, tracked in
`TODO.md`-style notes, not a lie in the API).

Every other kind answers a *named* refusal, because no safe cancel exists: the
gallery pool is a `QThreadPool` (`clear()` would silently drop queued thumbnails
and leave items unloaded), and the metrics and AI passes carry no cooperative
token. Cancelling there would be a fake, so it is refused:

```
jobs_cancel {id: "metrics:image_gallery"} →
  ok: false · "cancel is not supported for kind 'metrics_pass'"
  hint: "only exports expose a safe cancel today …"
```

**`notifications/progress` is deliberately not carried.** The transport
(`protocol.py`) is stdio request/response and emits no server→client
notifications, so progress cannot be pushed without faking it. The honest
substitute is `wait_for` (below) or a `jobs_list` poll while a long tool call is
pending. Recorded as a gap, not a feature.

### Waiting for an asynchronous expectation (`wait_for`)

Hand-written "poll `ui_elements` until the row appears / poll `jobs_list` until
the pass ends" loops are the expensive part of driving the app: the canonical
gallery scenario spent 3–5 of its 8–12 calls on bare polls. `wait_for` replaces
them. It is **read-only and live-only** (it observes an in-memory app, so with no
instance it refuses exactly like `ui_elements`).

Pass **exactly one** selector:

| Selector | Holds when |
|---|---|
| `element: <id>` | that id resolves **and** the row is `visible` and `enabled` (the inventory is read with disabled rows included, so "present but disabled" is observable rather than invisible) |
| `role: <role>` + `label: <label>` | an element with that exact role and exact, case-sensitive label exists (matched against the reported label) |
| `job_settled: true` (`job_kind:` optional) | no listed (running or paused) job remains; with `job_kind` only rows of that kind count |

`timeout_ms` defaults to 5000 and is hard-capped at 60000; `poll_ms` defaults to
100 with a 25 ms floor. Every observation goes through the same machinery the
read tools use (`ui_elements` / `jobs_list`), so `wait_for` invents neither a
second resolver nor a second job view. Sleeps are clamped to the remaining
budget, so the call does not overshoot `timeout_ms` by more than one poll
interval (a slow observation adds its own duration).

A success and a timeout are both **normal results**, never a tool error:

```
wait_for {element: "gallery.thumb.12", timeout_ms: 4000} →
  ok: true · waited_ms: 214 · source: "live"
  observed: {id: "gallery.thumb.12", role: "cell", visible: true, enabled: true, …}

wait_for {job_settled: true, job_kind: "export"} →
  ok: false · reason: "timeout" · waited_ms: 60000
  observed: [{id: "export:image_compare:3", kind: "export", status: "running", …}]
  hint: "a job of kind 'export' was still listed as running/paused; …"
```

`observed` is the last observed state — the element row, or the job rows (`[]`
when everything settled; `null` when a role+label pair never appeared) — so a
caller never needs a follow-up read just to see *why* the predicate missed.
Zero or more than one selector, a lone `role` or `label`, `job_settled: false`,
and a `job_kind` without `job_settled` are named validation errors; an
out-of-range budget is `-32602` from the input schema.

### Mutation contract: reads retry once, edits never

The control transport is local, so this is honest labelling more than
resilience — but it is what stops an agent from double-applying an edit:

- **Reads retry exactly once** when the wire times out (`list_actions`,
  `list_sessions`, `get_state`, `read_log`, `query_trace`, `dump_ui_layout`,
  `list_surfaces`, `ui_elements`, `ui_nav_state`, `jobs_list`); a second timeout
  falls back like any other transport failure.
- **Mutations never auto-retry** (`open_tab`, `run_action`, `open_folder`,
  `set_theme`, `set_language`, `capture_surface`, `press_keys`, `nav_key`,
  `ui_click`, `ui_hover`, `ui_focus`, `jobs_cancel`). A retry could double-apply
  the edit.
- **The two failure kinds stay distinguishable in the message text**: a
  transport failure *before* the request left the process says **"not sent"**
  (connect/write); one *after* the request was written says **"sent, no
  reply"** (read timeout, EOF, read error).
- **A mutating tool's timeout says the operation may have completed.** When a
  live edit was already on the wire and the deadline expired, the server does
  *not* fall back to a fresh process (that would risk applying the edit twice);
  it answers `isError` with the wire message plus "the operation may have
  completed", and the hint tells the caller to re-read state rather than retry.
  `list_actions` rows carry `enabled` + `reason` for exactly this: plan around a
  precondition instead of failing into it.

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
`routed: false`, so the folder must be dropped on the gallery (it opens
`--open-tab <tab>` when one was named). `press_keys` is
**live-only** — with no instance it errors honestly, it never fakes input. The
element-targeting tools (`ui_elements`, `ui_click`, `ui_hover`, `ui_focus`) are
live-only too: ids exist only in a running app, so with no instance they answer
an honest error rather than booting a throwaway app. A **live** capture
composites each visible canvas frame into the PNG (the swapchain surface is
in neither grab path), so the QRhi/GL canvas does show its content; a
devtool-booted surface still cannot grab it (see
[SCREENSHOTS.md](SCREENSHOTS.md) §Known limitation).

### Capture provenance (`capture_surface`)

`surface` is **optional**: omitting it captures the live instance's active
window (the app's own `resolve_capture_target` path). With no live instance the
fallback devtool has nothing to grab, so the call is refused — "surface is
required when no live instance is attached" — never answered with a different
surface. With a live instance but no window to grab, the app refuses with
"no live window to capture".

A live result keeps the app's provenance instead of flattening it: `what`
(what was actually grabbed), `method` (`grabWindow` / `widget_grab`), `size`
`[w, h]`, and `rhi_layers` (composited canvas frames; `0` = no presenting
canvas). Read `method`/`rhi_layers` before judging pixels — the
live-verification runbook makes them mandatory for exactly this reason.

`theme` and `out` are **fallback-only** parameters: the live handler takes only
`what`, writes to the app's artifacts directory and captures the running
window's own theme. A live result therefore reports `theme: null` and lists
nothing in `options_applied`; a fallback result names the applied ones
(`theme`, `out`) and puts `method`/`rhi_layers` in `unavailable` rather than
inventing values. (Fallback `size` is parsed from the devtool's own
`saved <path> <w>x<h>` line, `null` if absent.)

## Security model

- **Local only.** stdio subprocess, never TCP/HTTP; no network code.
- **Allowlisted actions.** `run_action` rejects ids absent from the
  ActionRegistry snapshot *before* launching, with close-match suggestions.
- **Existing directories only** for `open_folder`; no traversal. `tab=<kind>`
  targets that tab instead of the first tab that accepts a directory (the tab
  is opened if absent); a file-only tab (`multi_compare`, `image_compare`)
  cannot accept a directory, so it receives the folder's images as files
  (non-recursive, shared extension set) — that is the supported way to load
  images into those tabs, whose own "add images" dialog a client cannot drive.
- **No file contents.** Only the app's own log/tracer/catalog/layout artifacts
  are returned — never user images or arbitrary files.
- **Read-only default**; mutations are distinct named tools with honest
  `annotations` (`run_action` sets `destructiveHint: true`; `press_keys` and
  `ui_click` are non-destructive but non-idempotent).
- **Keyboard input is live-only.** `press_keys` injects into the running app
  through the control socket; with no instance it answers an honest error
  rather than pretending. Key names are allowlisted app-side: named keys,
  single letters/digits, and the punctuation a path or text field needs
  (`/`, `.`, `-`, `_`, `~`, `=`, `:`, …) — one combo per key, e.g.
  `/,t,m,p,/,a,.,p,n,g` types `/tmp/a.png` (`','` and `'+'` are the
  separator characters and stay unavailable). `target=<id from ui_elements>`
  aims the sequence at that element: a live canvas is not in the window's
  focus chain, so canvas shortcuts (`=`, `-`, `0` in multi-compare) only
  arrive when the canvas id is named.
- **Element targeting is live-only.** `ui_elements` reads the running window's
  widget inventory; `ui_click`/`ui_hover`/`ui_focus` act on an id from it. With
  no instance they answer an honest error — no throwaway app is booted to fake a
  target.

### Refusals (no silent truncation)

Every refusal below is a named, actionable answer — never a truncated or
fabricated result:

| Refused | Enforced by | Answer |
|---|---|---|
| unknown MCP method | this server (`protocol.py`) | JSON-RPC `-32601` |
| request line over the 1 MiB cap | this server (stdio) | JSON-RPC `-32600` "request line exceeds the … byte cap" |
| unknown control-channel method | live app | `ok: false` + hint, connection survives |
| foreign uid | live app (`SO_PEERCRED`, before reading a byte) | connection closed → the call falls back |
| non-live `press_keys` / `nav_key` / `ui_elements` / `ui_nav_state` / `ui_click` / `ui_hover` / `ui_focus` | this server | `isError` "needs a running app" (never a throwaway app faking a target) |
| non-live `jobs_list` / `jobs_cancel` | this server | `isError` "no live instance; job state needs a running app" (never a fake empty list) |
| non-live `wait_for` | this server | `isError` "no live instance; waiting for app state needs a running app" (never a silent 5 s timeout) |
| `jobs_cancel` on a kind with no cooperative cancel | live app | `ok: false` "cancel is not supported for kind …" + hint; never a fake cancel |
| `jobs_cancel` on an unknown or settled id | live app | `ok: false` "no running job with id …" + `jobs_list` hint |
| unknown action id / tab / state path | this server (fallback) | `isError` + close-match suggestions |
| unknown surface | live app (`capture_live`) or this server (`capture_surface` fallback) | `isError` "unknown surface" + `list_surfaces` hint |
| surface known but not open in the live app | live app | `isError` "surface … is not open in the live app" |
| no `surface` and no live instance | this server (`capture_surface` fallback) | `isError` "surface is required when no live instance is attached" + `list_surfaces` hint |
| no active window for a live capture (no `surface`) | live app (`capture_live`) | `ok: false` "no live window to capture" + "pass what=<tab> … or focus a window first" |
| more than 32 key combos in one `press_keys` | live app | `ok: false` "too many key combos" |

### Annotation audit (2026-10-17)

The `annotations` hints were checked against what each handler actually does,
because that is what lets a client auto-approve reads:

- **Read-only tools really read.** All eleven (`list_actions`, `list_sessions`,
  `get_state`, `read_log`, `query_trace`, `dump_ui_layout`, `list_surfaces`,
  `ui_elements`, `ui_nav_state`, `jobs_list`, `wait_for`) carry
  `readOnlyHint: true, destructiveHint: false`
  and touch no app state — `ui_elements` only *inventories* the live window,
  `jobs_list` only reads the app's own counters (it never resolves a lazy tab
  service, which would materialize a tab as a side effect of listing), and
  `wait_for` only repeats those two observations until a predicate holds. Reads
  may retry once (above); none mutate.
- **Mutating tools are honestly marked.** All twelve carry `readOnlyHint: false`.
  `run_action` alone advertises `destructiveHint: true` (it can run any
  registered action, including `platform.quit_app`). `press_keys`, `nav_key`,
  `ui_click` and
  `jobs_cancel` are `destructiveHint: false` but `idempotentHint: false`
  (repeating the same combo/click is not a no-op; re-sending a settled job id is
  an error, not a second success). `ui_hover`/`ui_focus` settle to the same
  state, so they keep `idempotentHint: true`.
  `open_tab`/`open_folder`/`set_theme`/`set_language`/`capture_surface` are
  non-destructive and idempotent.
- `openWorldHint: false` on every tool (the app is local). **Result: no
  annotation was found to over- or under-state what its tool does.** The test
  suite pins the classification (`test_read_and_write_tools_do_not_mix_annotations`,
  `test_element_tool_annotations_are_audited`,
  `test_job_tool_annotations_are_audited`).

The live channel is the in-app control server: a unix socket in the control dir
(env-gated, no TCP), refusing connections from other uids. Reads and mutations
on a live instance are the same tools — the answering path is visible in every
result as `source`.

## Known limitations

- **`ui_click {button: right}` hides the menu it just opened (P1 tool defect,
  recorded 2026-10-17).** A right-click by element id delivers the mouse button
  event *and* an extra `QContextMenuEvent`. The app's menu manager treats that
  second event as the "click that opened me", which consumes its open-click
  grace window, so the context menu collapses ~150 ms after opening. The click
  itself reaches the handler; only the visible menu life is wrong. **Not fixed
  here** — the fix belongs to the gallery / control-element lane (the same
  surface as the collapsed-card-menu bug).
- A live QRhi/GL canvas capture is composited from the canvas's own last
  frame (see [SCREENSHOTS.md](SCREENSHOTS.md) §Known limitation) — a canvas
  that has not rendered yet contributes nothing.

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
- Private `improve-imgsli-internal-docs` repo →
  `docs/dev/RUNBOOK_LIVE_MCP_VERIFICATION.md` — copy-paste recipe for driving and
  *reading* a live instance on a private Xvfb: private display + isolated
  `XDG_*`, the RHI-is-live proof steps, the window-on-screen check, and the
  capture-artifact checklist (which of `method`/`rhi_layers` to trust). Its §0
  checklist is the blindness list referenced from the private
  `docs/dev/DEBUGGING.md` rule 7.
