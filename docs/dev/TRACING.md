# Runtime Tracer

A built-in causal tracer for debugging Redux dispatches, EventBus emissions,
canvas feature interactions, render pipeline activity, and input-event chains.

Solves the recurring problem of "I clicked / zoomed / panned and something
weird happened, now I need to grep across 5+ files to figure out which actor
caused it." Every input event opens a `trace_id`, and every downstream dispatch
/ emit / hit-test / render-plan-apply inherits it — so the entire causal chain
of a single user gesture is recoverable from one filter.

The tracer is **off by default**, has near-zero overhead when disabled, and
never creates Qt windows. It writes line-buffered JSON to a file under the
application's normal log directory.

## Enabling

```bash
IMGSLI_TRACE=1 python src/__main__.py
```

Output file: `~/.local/share/ImproveImgSLI/trace.jsonl` (truncated on each app
start, contains only the current session). The log line
`trace file sink active: <path>` is printed at startup.

Also enabled automatically when `--debug` mode is on.

## What gets recorded

| `kind` | Description | Carries `duration_ms`? |
|---|---|---|
| `input.{mpress,mrel,mmove,wheel,kpress,krel}` | Every Qt mouse/keyboard event. Opens a new `trace_id` (e.g. `mpress-a1b2c3d4`). | yes (in `.end`) |
| `dispatch.begin` / `dispatch.end` | Every Redux action with `diff` of `viewport` / `document` / `settings` between pre- and post-reduce. | yes |
| `store.emit_state` / `store.emit_viewport` | Every state-change notification with caller + scope + subscriber count. | no |
| `eventbus.emit` / `eventbus.end` | Every EventBus emission with subscriber count. | yes |
| `alias.command` | Each capability-alias resolve via `widget_registry.get_canvas_feature_command_by_alias`. | no |
| `render.apply_plan` / `render.apply_end` | Each `apply_canvas_render_plan` call with a snapshot diff of changed `CanvasRenderPlan` fields vs the previous frame on the same canvas. | yes |
| `video.preview.*` | Video editor preview request/apply sizes, selected render target, fit-content state, and prepared-frame debug payload. | no |
| `video.render.*` | Snapshot renderer prescale/layout/plan sizes, interpolation method, render scene filter, diff mode, and canvas/content geometry. | no |
| `hit_test` | Each `find_scene_object_at_position` result (kind + id). | no |

Each record carries:
- `seq` — monotonic insertion index
- `ts` — `time.monotonic()` timestamp
- `kind`, `trace_id`, `depth` — categorization and tree position
- `summary` — one-line human-readable description
- `caller` — `module:function:line` of the call site
- `payload` — structured fields specific to the kind

## Filtering categories

By default `input.mmove` is excluded (hover-only mouse moves spam the log
without informational value). Two env vars control the filter, both accept
comma-separated patterns with `*` as suffix wildcard:

```bash
# Whitelist (allow only these)
IMGSLI_TRACE_KINDS="dispatch.*,render.apply_plan,hit_test,input.mpress"

# Blacklist (skip these)
IMGSLI_TRACE_SKIP="alias.command,input.mmove"

# Record absolutely everything (override default mmove-skip)
IMGSLI_TRACE_SKIP=""
```

## Reading the file

The raw format is JSON Lines — one record per line, append-only, line-buffered.
Survives SIGKILL: every record is on disk by the time the next line is written.

### Quick filters with `jq`

```bash
# Only action diffs
jq -c 'select(.kind=="dispatch.end") | {seq, action: .payload.action_type, diff: .payload.diff}' trace.jsonl

# All events caused by a specific user input
jq -c 'select(.trace_id=="mpress-a1b2c3d4")' trace.jsonl

# All dispatches that actually changed split_position
jq -c 'select(.payload.diff.viewport._view_state.split_position)' trace.jsonl

# Last 10 wheel-driven causal chains
jq -c 'select(.trace_id and (.trace_id | startswith("wheel-")))' trace.jsonl | tail -100
```

### LLM-friendly tree view

For pasting into a chat (e.g. asking for help with a bug), use the span-tree
exporter. It groups records by `trace_id`, sorts by `seq`, and indents by
depth, producing a flame-graph-shaped text output that's far more useful for
analysis than raw JSONL:

```bash
cd src

# List all traces with total duration, sorted slowest-first
PYTHONPATH=. python3 -m core.tracing.print_tree --list

# Render a single trace as a tree
PYTHONPATH=. python3 -m core.tracing.print_tree mpress-a1b2c3d4

# Top N slowest traces
PYTHONPATH=. python3 -m core.tracing.print_tree --top 5

# Hide spans shorter than 5ms (focus on real work)
PYTHONPATH=. python3 -m core.tracing.print_tree --top 5 --min-ms 5

# Wildcard pattern (all mouse-press traces)
PYTHONPATH=. python3 -m core.tracing.print_tree 'mpress-*'

# Read from arbitrary file
PYTHONPATH=. python3 -m core.tracing.print_tree --file /tmp/saved.jsonl mpress-a1
```

Example output:

```
=== trace_id=mpress-a1b2c3d4  (14 records) ===
[  45.20ms] input.mpress           mpress pos=(557,475) btn=1
    @ __main__:main:126
  [  38.10ms] dispatch.begin         dispatch SET_SPLIT_POSITION
      diff.viewport: {"_view_state":{"split_position":{"old":"0.5","new":"0.68"}}}
      @ ui.canvas_features.divider.commands:dispatch_viewport_action:26
    [  12.00ms] store.emit_viewport    emit_viewport subdomain=interaction
        @ ui.canvas_features.divider.commands:emit_interaction_update:32
      [   8.20ms] render.apply_plan      apply_plan canvas=4f23 changed=['source_key']
          plan changed: source_key, capture_visible
          @ ui.canvas_presentation.plan_applicator:apply_plan:178
```

## Debugging workflow

Typical loop for "X causes weird behavior":

1. Pick the narrowest category filter that still captures the suspect path.
   For canvas interaction issues, a good default is:
   ```bash
   IMGSLI_TRACE_KINDS="input.mpress,input.mrel,input.wheel,dispatch.begin,dispatch.end,hit_test,render.apply_plan,store.emit_viewport"
   ```
   For video preview/export resolution or pixelation issues:
   ```bash
   IMGSLI_TRACE=1 IMGSLI_TRACE_KINDS="video.preview.*,video.render.*,render.apply_plan,render.apply_end" python -m src
   ```
   Then reproduce one preview frame and inspect `video.preview.request`,
   `video.render.prescale.*`, `video.render.layout`, and `video.render.plan`.
   These records show the requested preview size, prescale target/result,
   content/canvas sizes, and the GL filter source used by the export scene.
2. Reproduce the bug in a minimal scenario (single click, single zoom tick).
3. `print_tree --list` to find the relevant `trace_id` (usually the slowest
   or last-by-seq).
4. `print_tree <trace_id>` to see the full causal chain.
5. Look for:
   - `dispatch.end` with empty `diff` → action fired but did nothing (probably
     no-op or a state mutation outside the reducer)
   - `diff` containing fields you didn't expect to change → unintended side
     effect from the reducer
   - `render.apply_plan` with `changed=[...]` that doesn't match the user's
     action → plan is rebuilding from a stale store
   - `hit_test` returning `None` where you expected a feature handle → hit
     zone is misplaced relative to current zoom/pan

## Adding traces to your own code

If you need to instrument a new code path:

```python
from core.tracing.tracer import Tracer

# Record a one-shot event
Tracer.instance().record(
    "myfeature.something",
    "summary line for the UI",
    {"key": value, "other": value2},
)

# Or as a span with duration (begin/end pair sharing span_id)
import time
from core.tracing.tracer import Tracer

tracer = Tracer.instance()
if Tracer.enabled():
    span_id = f"sp{tracer.next_span_id()}"
    t0 = time.monotonic()
    tracer.record("myfeature.work", "doing X", {"span_id": span_id})
    tracer._push_depth()
    try:
        do_the_work()
    finally:
        tracer._pop_depth()
        tracer.record(
            "myfeature.work.end",
            "did X",
            {"span_id": span_id, "duration_ms": (time.monotonic() - t0) * 1000.0},
        )
```

Wrap calls in `Tracer.enabled()` to avoid building payload dicts when tracing
is off.

## Architecture

Files in `src/core/tracing/`:

- `tracer.py` — singleton with thread-local trace_id/depth, ring buffer, env
  filter parsing, recording API.
- `records.py` — `TraceRecord` dataclass.
- `instrumentation.py` — install-time monkey patches for `Dispatcher.dispatch`,
  `Store.emit_state_change`, `Store.emit_viewport_change`, `EventBus.emit`,
  `widget_registry.get_canvas_feature_command_by_alias`,
  `apply_canvas_render_plan`, `find_scene_object_at_position`, and all
  `CanvasWidget` mouse/wheel/key handlers (`src/tabs/image_compare/canvas/widget.py`).
- `file_sink.py` — subscribes to Tracer and appends JSON lines to the log
  directory file.
- `print_tree.py` — CLI for reading the file and rendering trees.

Activation order at startup (`src/core/bootstrap.py:_maybe_install_tracer`):

1. If `IMGSLI_TRACE=1` or debug mode: install instrumentation patches at the
   class level (single global effect, no per-instance work).
2. Install file sink (subscribes to Tracer, opens log file).
3. Normal application initialization proceeds; from this point every relevant
   class method is wrapped, including those of objects that haven't been
   instantiated yet.

Records flow:

```
Qt event ──> patched handler ──> Tracer.begin_trace("mpress")
                                       │
                                       v
                              Tracer.record(...) ──> ring buffer
                                       │                  │
                                       │                  └──> notify subscribers
                                       │                              │
                                       v                              v
                              tracer._push_depth()              file_sink writes
                                       │                        JSON line
                                       v
                              call original handler
                              (which dispatches, emits, etc.
                              — each inherits trace_id via
                              thread-local)
                                       │
                                       v
                              Tracer.end_trace()
```

## When NOT to use the tracer

- **Production-perf-sensitive paths under load**: although disabled tracer is
  near-zero cost, enabled tracer with default filter adds visible overhead
  (~5–15% on heavy interactive scenes). Don't ship with `IMGSLI_TRACE=1`.
- **Memory leaks or async-thread issues**: tracer captures call sites and
  cross-thread events but doesn't track object lifetimes or Qt signal/slot
  graph. Use `objgraph` or Qt's own debug builds.
- **GL state / shader bugs**: tracer sees CPU-side render-plan, not GL calls.
  Use `apitrace`, `RenderDoc`, or the `qt.qpa.gl=true` logging category.
