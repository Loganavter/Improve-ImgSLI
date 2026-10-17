# MCP v2 — plan (agent-control plane, second round)

Status: draft · Date: 2026-10-17 · Scope: `mcp-server/app/**` + `src/core/control/**` (app-side channel)

Related: [MCP.md](MCP.md) (the current surface + security model) ·
[CONTROL-COMPARISON](#appendix-what-photocraft--filmcraft-do-differently) (appendix below).

## Where we are (v1, shipped 2026-10-17)

A live, in-app control channel plus an MCP server that attaches to it:

- `src/core/control/**`: `QLocalServer` + `instance.json` pointer in a `0700` dir, `SO_PEERCRED` uid
  check, newline-JSON requests, 16 methods 1:1 with the MCP tools, handlers on the GUI thread, a live
  log ring, real key injection (`QTest.keyClick`), live capture (`grabWindow`), theme/language applied
  live, folder routing through the tab's own drop path. Env gate `IMGSLI_CONTROL=1`, no TCP.
- `mcp-server/app/**`: 14 tools, stdio MCP, **attach-and-proxy** when an instance is live with an
  honest `source: live|fallback` on every result; the fallback is headless-only, never on the
  session's display, reuses a live per-tab process, and preserves the running app's log.

Verified live (2026-10-17): every tool answered `source: live`; `run_action platform.settings` really
opened the dialog in the visible window; `press_keys Down,Down,Escape` landed on the focused live
widget; `open_tab` + `capture_surface` produced a PNG of the live window; **zero spawned processes**.

## What the comparison taught us (see appendix)

Three gaps stand out, in this order of value for an agent:

1. **We can move with the keyboard only.** Both peers expose pointer input and — far more useful —
   *element targeting by id*: FilmCraft's `ui.elements` (every on-screen interactive element with an
   id + rect, refreshed per frame) plus `ui.click {id}` with **retry-until-rendered**; PhotoCraft's
   `ui.pointer`/`ui.click` in screen points and `ui.menu.invoke`.
2. **A mutation's contract is honest in both peers**: reads may retry once, edits never auto-retry,
   and a timeout says "operation may have completed". We have neither the taxonomy nor per-command
   `enabled`/`reason` metadata (so an agent cannot plan around a precondition).
3. **Long work is observable in both**: FilmCraft's job model (`jobs.list` with progress, and MCP
   `notifications/progress` + cancel-with-partial-deletion for the one long command); PhotoCraft's
   progress notifications for its long filter/export operations. Our long passes (metrics, AI,
   export) are opaque until they finish.

And one lesson from our own bug hunt (the gallery card menu rendering at ~2 px, silently):
**drivability is not enough — the UI must be observable.** The menu was created (`card menu opened`
in the log, `visible=True` in-process) while nothing usable appeared on screen; no MCP tool could
tell me that, and I had to fall back to a desktop screenshot plus external `xdotool` to see it at all.
An element inventory with rects would have named the collapsed popup in one call.

## Non-goals (deliberately out of scope)

- **No HTTP, no TCP, no bearer token.** A unix socket inside a path the sandbox already grants plus a
  `SO_PEERCRED` uid check is strictly stronger than the peers' loopback TCP + token, and it needs no
  secret to distribute. Revisit only if P0 shows the socket cannot cross a Flatpak boundary.
- **No OS-level input injection** (no `xdotool`, no `/dev/uinput`): all input stays in-process.
- **No per-tool capability matrix** (PhotoCraft's is explicitly unimplemented there too); our surface
  touches no user files, which is narrower than either peer.
- **No rewrite of the UI open/build paths** in this plan. P1 makes them *observable*; fixing them is
  their own task (the card menu bug is on the board).
- **No arbitrary text typing** beyond what is needed to drive inputs (a `ui_type` equivalent is a
  candidate for a later round, not here).

## P0 — Verify the sandbox reality (1 item, blocking the transport decision)

**Goal.** Our socket lives in `$XDG_RUNTIME_DIR` (fallback `<data>/run`). Both peers are Flatpak apps
whose sandbox *denies network*, and their TCP control channel is therefore unreachable from the host
until the user grants `--share=network`. Our app also ships a Flatpak build — so before promising
"the host agent can always attach", establish the truth:

- Does a Flatpak-installed app see the host's `$XDG_RUNTIME_DIR` (or a private one)? Is a socket
  created there visible to a host-side `mcp-server/app/server.py`?
- If not: which path *is* shared, or should the MCP server run **inside** the sandbox
  (`flatpak run --command=<cli> … mcp`, the pattern FilmCraft documents)?

**Deliverable.** A short decision section appended to `MCP.md` (+ the probe recipe), and — if the
socket cannot cross the boundary — a fallback: the pointer file names the socket, so the server can be
told a path explicitly (`IMGSLI_MCP_CONTROL_SOCKET`) and can also be launched in-sandbox.
**Acceptance.** A recorded live check for both cases (host-installed, Flatpak-installed), not prose.
**Why first.** Everything else rides on the transport being reachable at all.

## P1 — Interaction parity: element inventory + click (the biggest gap)

**Goal.** An agent clicks and hovers by *element*, not by pixels, and can *see* what exists.

- **`ui_elements {scope?}`** — the live, flattened inventory of interactive elements: stable id,
  role (button/menu-row/tab/card/input), label, **screen rect**, `enabled`, and the Find-Action id it
  is bound to when it has one. Source of truth, in order: the widget tree (`devtools/ui_layout_dump`
  already carries geometry + bound action ids), the `ActionRegistry`, and the toolkit's own row ids
  where they exist. In-window and popup surfaces both included.
- **`ui_click {id, button: left|right|middle, count?}`, `ui_hover {id}`, `ui_focus {id}`** —
  in-process injection at the element's centre (`QTest.mouseClick` / `QApplication.sendEvent`),
  returning the rect used and the element it resolved to.
- **Retry-until-rendered** (FilmCraft's `RETRY` semantics): an unknown/not-yet-realized element is
  retried for ~3 s before failing, so an agent need not sleep between "open" and "click".
- Menu-element ids must be discoverable *while the menu is open* (that is the point).

**Deliverable.** Two control methods + two MCP tools (`ui_elements` read-only, `ui_click` mutating),
plus `ui_hover`/`ui_focus` if they fall out cheaply. Docs: `MCP.md` + `README.md` (tool count).
**Acceptance.**
- The reproduction I did by hand becomes a test: open the gallery card context menu **by element id**
  and assert a menu surface appears with ≥ N rows whose rects are non-degenerate. (This is exactly the
  assertion that would have caught the collapsed-menu bug.)
- A right-click by id reaches the same handler as a user's right-click (assert the menu surface
  exists and a click on a row triggers its action).
- Retry semantics: an element that appears after ~200 ms is still found; a genuinely absent id fails
  with a hint listing close matches.
**Risks.** Rect/坐标 fidelity on Wayland (the peers document exactly this: documents/point vs screen
points; PhotoCraft raises the window before screenshotting because occluded macOS windows stop
rendering). Mitigation: return both the *widget* rect and the *screen* rect, and document which is
which; never require a click to be on-screen for a *handler* to fire (in-process delivery), only for
the *human-visible* effect.

## P2 — Contract honesty (cheap, high value per line)

- **Read-retry-once / edit-never-retry**, with a distinguishable "not sent" vs "sent, no reply"
  timeout (PhotoCraft's `timeout: not run` vs `timeout: no reply in 60s`), and the phrase
  "operation may have completed" on the edit path. Our transport is local, so this is mostly
  labelling — but it is what stops an agent from double-applying an edit.
- **`enabled` + `reason`** on every `list_actions` row (why an action is not runnable *now*), so an
  agent plans instead of failing. The registry carries no such field today; add it to the descriptor
  and to the snapshot, defaulting to enabled with no reason.
- **Bounds + explicit refusals**: a request-line cap with a named error, a reply-size sanity check,
  and a documented list of what is refused (unknown method, foreign uid, non-live `press_keys`,
  unknown surface on the fallback capture path). No silent truncation anywhere.
- **Tool annotations audited** against behaviour (read-only tools really read-only; mutating ones
  honestly marked), because that is what lets a client auto-approve reads.

**Acceptance.** Unit tests for the taxonomy (a real timeout fixture), for `enabled/reason`
propagation, and for each named refusal; the annotation audit recorded in `MCP.md`.

## P3 — Long work: jobs + progress + cancel

**Goal.** An agent can watch and stop the passes that take minutes.

- **`jobs_list`** — a read view over state the app already keeps: the metrics/proxy pass per folder,
  the AI analysis pass, exports (the worker pool + activity phases + the export queue). Each entry:
  id, kind, status, progress (0–1 or done/total), elapsed, message.
- **MCP `notifications/progress`** for the same work when a tool call waits on it, and **cancel**
  only where a safe cancel exists today (start with export; extend to the metrics pass only if the
  scheduler can already cancel — not by inventing cancellation).
- Partial-output cleanup only for outputs we own (the FilmCraft rule: cancel deletes the export's own
  partial files and nothing else).

**Acceptance.** A live run that reports progress at least once for each of the three kinds, and a
cancel that leaves no partial artifact behind. **Non-goal here:** event subscriptions (`subscribe`).

## P4 — Stretch (only on request)

`subscribe`/event stream; a stability *contract* for element ids (so tests may pin them); an audit
stream of mutations with their outcomes; `ui_type` for text inputs.

## Appendix: what PhotoCraft / FilmCraft do differently

Both are Rust/egui peers read at `~/Загрузки/projects/{photocraft,filmcraft}` (read-only study,
2026-10-17). The useful deltas:

| Dimension | PhotoCraft | FilmCraft | Ours (v1) |
|---|---|---|---|
| Transport | loopback TCP, **256-bit bearer token** per connection, token file `0600`, constant-time compare | loopback TCP, **no auth** ("enable only while using") | **unix socket + `SO_PEERCRED` uid + pointer file**, no secret, no TCP |
| Discovery | port chosen by the user; `instance.json` is file hand-off only | port passed by the user | pointer file names the socket; env override |
| Live attach | `--control` **deliberately opts out** of single-instance (never the user's window) | `--control <port>`; no discovery | **attaches to the running window**, falls back headless with `source:` |
| Element targeting | coordinates + `ui.menu.invoke` | **`ui.elements` (id + rect, per frame) + `ui.click {id}` with retry** | none (keys only) |
| Screenshot | live window via egui readback; headless **full-UI render with the real GPU canvas** | live viewport screenshot (10 s give-up), CPU offscreen frame render | live `grabWindow` + devtool demo surfaces |
| Long work | progress notifications for the one long operation; `jobs.list` | **job model + `jobs.list` ETA + progress notifications + cancel deleting its own partials** | none |
| Command model | one registry (~500+) dispatched by UI/CLI/control/MCP, one undo step per edit | ~650 ids, same rule | `ActionRegistry` + `run_action` (89 ids), no `enabled/reason` metadata |
| Mutation contract | reads retry once, edits never, "operation may have completed" | same discipline + per-worker `catch_unwind` | none (a timeout is just a timeout) |
| Docs | `book/src/automation/*` + `docs/control-protocol.md` (authoritative tables), explicit "known limitations" | `docs/agents.md` + `docs/control-protocol.md`, explicit limits | `docs/dev/MCP.md` |

Kept for reference, not adopted: per-tool capability matrices (unimplemented in PhotoCraft too),
TCP+token (weaker than uid-checked unix socket), coordinate-only clicking (fragile), and
`ui.gpu.simulateLoss`-style fault injection.
