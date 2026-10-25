"""Declarative MCP surface for the Improve-ImgSLI app server.

Single source of truth for the three MCP primitives — **tools**, **resources**,
**prompts** — as plain stdlib dicts. ``protocol.py`` turns them into wire
messages; ``backend.py`` implements the handlers. Keeping the declaration
separate means ``tests/devtools/test_mcp_server.py`` can lint the whole catalog
(names, descriptions, annotations, JSON Schemas) without a transport.

Design rules (MCP spec revision ``2026-07-28`` + 2026 tool-design consensus):

- names are ``verb_noun`` snake_case, 1–64 chars, ``[A-Za-z0-9_.-]``;
- descriptions are 200–400 chars and say *what + when to use + when NOT to*;
- ``inputSchema`` is flat JSON Schema, enums/defaults + a ``description`` per
  property, ``additionalProperties: false``;
- reads and writes never share a tool;
- every tool carries an ``outputSchema`` and its handler returns matching
  ``structuredContent``;
- all four ``annotations`` hints are explicit on every tool;
- the catalog stays small (≤ ~28 tools — a review prompt, not a magic number:
  the surface grows with the app's own subsystems, one read + one write per
  concern; large payloads live in resources).
"""

from __future__ import annotations

#: Protocol revision this server speaks (stateless per-request envelope era).
PROTOCOL_VERSION = "2026-07-28"

#: Revisions accepted on the per-request ``_meta`` envelope path.
MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)

#: Revisions accepted on the legacy ``initialize`` handshake path, so today's
#: clients (which still handshake) interoperate without special-casing.
HANDSHAKE_PROTOCOL_VERSIONS = (
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
)

SUPPORTED_PROTOCOL_VERSIONS = (*HANDSHAKE_PROTOCOL_VERSIONS, *MODERN_PROTOCOL_VERSIONS)

SERVER_NAME = "improve-imgsli-app"
SERVER_VERSION = "0.1.0"

INSTRUCTIONS = (
    "Drives the local Improve-ImgSLI desktop app. When a running instance is "
    "attached over its in-app control socket every tool acts on that live "
    "window (results carry source='live'); otherwise the server falls back to "
    "headless operation: reads boot a throwaway snapshot and mutations start a "
    "fresh, invisible process (source='fallback'). Read-only tools inspect the "
    "ActionRegistry, Store slices, widget tree, log, tracer, and capture "
    "surfaces. press_keys and the element-targeting tools (ui_elements, "
    "ui_click, ui_hover, ui_focus) need a live instance. On the fallback path, "
    "treat cached artifacts as possibly stale."
)

#: Freshness hint applied to the static list methods (ms).
STATIC_TTL_MS = 60_000
#: Freshness hint for results that reflect live process state (ms).
DYNAMIC_TTL_MS = 0

# Tabs that expose a ``workspace.new_<tab>`` action and can be opened headlessly.
TAB_KINDS = ("image_compare", "multi_compare", "image_gallery")

THEMES = ("light", "dark")
LANGUAGES = ("en", "ru", "zh", "pt_BR")

#: The long-work kinds ``jobs_list`` reports (mirrors ``core/control/jobs.py``;
#: the catalog stays app-import-free, so the vocabulary is repeated here).
JOB_KINDS = ("gallery_pool", "metrics_pass", "ai_analysis", "export")
#: Lifecycle states a listed job can be in (idle/settled jobs are not listed).
JOB_STATUSES = ("running", "paused")
#: The kinds ``jobs_cancel`` may actually stop today.
CANCELLABLE_JOB_KINDS = ("export",)

#: The only settings ``set_setting`` may write (mirrors the app's
#: ``core/control/live_verbs.SETTING_WHITELIST``; the catalog stays
#: app-import-free, so the vocabulary is repeated here). ``theme``/``language``
#: keep ``set_theme``/``set_language``.
SETTING_WHITELIST = ("rhi_backend",)
#: Values ``rhi_backend`` accepts (the app's own render-backend choice list).
RHI_BACKENDS = ("opengl", "vulkan")
#: Settings whose own verb owns them — ``set_setting`` names that verb.
DEDICATED_SETTING_VERBS = {"theme": "set_theme", "language": "set_language"}



def _annotations(read_only: bool, destructive: bool, idempotent: bool) -> dict:
    """All four annotation hints; ``openWorldHint`` is always false (local app)."""
    return {
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }


READ_ONLY = _annotations(True, False, True)
MUTATING = _annotations(False, False, True)
#: ``run_action`` can trigger any registered action — including destructive
#: ones — so it advertises ``destructiveHint`` honestly.
MUTATING_RISKY = _annotations(False, True, True)
#: ``press_keys`` / ``ui_click`` inject input: not destructive, but repeating the
#: same combo/click twice is not a no-op (focus/state move), so it is explicitly
#: non-idempotent. ``ui_hover``/``ui_focus`` settle to the same state, so they
#: keep the plain ``MUTATING`` hints.
MUTATING_INPUT = _annotations(False, False, False)

_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}


def _source() -> dict:
    """Schema for the additive ``source`` key every tool result carries.

    ``live`` = proxied to an attached running instance; ``fallback`` = the
    headless Phase-1 path (fresh process or on-disk artifact). Callers can tell
    the two modes apart without guessing.
    """
    return {
        "type": "string",
        "enum": ["live", "fallback"],
        "description": "Which answering path produced this result.",
    }


def _live_flag() -> dict:
    """Schema for ``live: true`` on mutations with no Phase-1 analogue key."""
    return {
        "type": "boolean",
        "description": "True when the live instance performed the mutation (no fresh process was launched).",
    }


def _object(properties: dict, required: list[str] | None = None) -> dict:
    schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _array(items: dict) -> dict:
    return {"type": "array", "items": items}


def _rect(description: str) -> dict:
    """Schema for an element geometry as a 4-number ``[x, y, w, h]`` array."""
    return {
        "type": "array",
        "items": _INT,
        "minItems": 4,
        "maxItems": 4,
        "description": description,
    }


def _params(properties: dict | None = None, required: list[str] | None = None) -> dict:
    """Tool input schema: flat object, no extra properties."""
    return _object(properties or {}, required)


#: One widget row as ``ui_nav_state`` / ``nav_key`` report it: identity, the
#: element id a client can pass back, its focus policy, and — the signal that
#: matters for keyboard reach — the navigation section that owns it (``null``
#: means Qt could focus it but no section drives it).
_ROW_PROPERTIES: dict = {
    "widget": _STR,
    "object_name": _STR,
    "label": _STR,
    "role": {"type": ["string", "null"]},
    "element_id": {"type": ["string", "null"]},
    "focus_policy": _STR,
    "keyboard_ring": {"type": ["boolean", "null"]},
    "owned_by_section": {"type": ["string", "null"]},
    "enabled": {"type": ["boolean", "null"]},
    "visible": {"type": ["boolean", "null"]},
    "screen_rect": {"type": ["array", "null"], "items": _INT},
}


def _row_or_null(description: str) -> dict:
    """Nullable widget-row schema (``null`` = nothing is focused/delivered to)."""
    return {"type": ["object", "null"], "description": description, "properties": dict(_ROW_PROPERTIES)}


def _bool_or_null(description: str) -> dict:
    """Nullable boolean: ``null`` = the app did not report the field at all."""
    return {"type": ["boolean", "null"], "description": description}


#: Fields of the control channel's **own** answer to a request still running.
#: A handler that overruns ``MODAL_ACK_BUDGET_MS`` (2 s — normally a chord or a
#: click that opened one of the app's modal dialogs, whose nested event loop is
#: what lets the watchdog timer fire) is answered on the channel's initiative:
#: ``ok: true``, none of the tool's own result fields
#: (``core/control/server.py:_arm_early_answer``).
_EARLY_ANSWER_PROPERTIES: dict = {
    "accepted": {"const": True},
    "answered_early": {"const": True},
    "still_running": {"const": True},
    "modal_open": _BOOL,
    "method": _STR,
    "budget_ms": _INT,
}


def _early_answer() -> dict:
    """Schema for the transport's early answer to a request it still runs."""
    return _object(
        {name: dict(spec) for name, spec in _EARLY_ANSWER_PROPERTIES.items()},
        list(_EARLY_ANSWER_PROPERTIES),
    )


def _also_early_answer(schema: dict) -> dict:
    """*schema*, widened to accept the transport's early answer as well.

    ``anyOf`` rather than a few more optional properties: the two frames share
    no field, so the normal result's own ``required`` would still reject the
    early one. ``type``/``properties`` stay on the outer object (the union of
    both) so a host expecting an object schema still sees one, and ``required``
    lives in the branches because it differs per shape.
    """
    normal = {
        "properties": schema["properties"],
        "additionalProperties": False,
    }
    if schema.get("required"):
        normal["required"] = list(schema["required"])
    return {
        "type": "object",
        "properties": {
            **schema["properties"],
            **{name: dict(spec) for name, spec in _EARLY_ANSWER_PROPERTIES.items()},
        },
        "additionalProperties": False,
        "anyOf": [normal, _early_answer()],
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

#: Batch-able tools and their argument contract: ``tool -> (required, allowed)``.
#: Explicit, never reflective: a batch may only name a verb whose single-call
#: contract is already published, and an unknown key is refused with the list.
#: ``ui_batch`` is absent on purpose — nesting would hide the ordering and the
#: per-item results the caller reads.
BATCH_TOOLS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "ui_click": (frozenset({"id"}), frozenset({"id", "button", "count"})),
    "ui_hover": (frozenset({"id"}), frozenset({"id"})),
    "ui_focus": (frozenset({"id"}), frozenset({"id"})),
    "ui_press": (frozenset({"id"}), frozenset({"id", "hold_ms", "release"})),
    "ui_wheel": (
        frozenset({"id"}),
        frozenset({"id", "delta", "phase", "count", "raw", "ctrl", "shift", "alt"}),
    ),
    "press_keys": (frozenset({"keys"}), frozenset({"keys", "target"})),
    "wait_for": (
        frozenset(),
        frozenset(
            {"timeout_ms", "poll_ms", "element", "role", "label", "job_settled", "job_kind"}
        ),
    ),
    "run_action": (
        frozenset({"action_id"}),
        frozenset({"action_id", "params", "expect", "tab"}),
    ),
    "set_setting": (frozenset({"key", "value"}), frozenset({"key", "value"})),
}

#: ``ui_batch`` bounds, mirrored by the backend guard. One call must stay
#: readable and must not occupy the request channel for minutes: 64 items and
#: at most 30 s of accumulated settle time.
MAX_BATCH_ACTIONS = 64
MAX_BATCH_SETTLE_MS = 1000
MAX_BATCH_SETTLE_TOTAL_MS = 30_000

TOOLS: list[dict] = [
    {
        "name": "list_actions",
        "title": "List Find Action catalog",
        "description": (
            "List the app's registered Find Actions (id, label, owner tab, "
            "shortcut, enabled, reason). Use it to discover exact ids before "
            "run_action, or to check a tab's catalog. Answers from the live "
            "instance when one is attached; otherwise it boots a headless "
            "snapshot (a few seconds). Do NOT use it to run anything, and do "
            "NOT invent ids — only ids returned here are accepted by run_action."
        ),
        "inputSchema": _params(
            {
                "query": {
                    **_STR,
                    "description": "Case-insensitive substring filter over action id, label, and label key.",
                },
                "owner_tab": {
                    **_STR,
                    "description": "Restrict to actions owned by this tab id (e.g. image_compare); omit for all.",
                },
            }
        ),
        "outputSchema": _object(
            {
                "count": _INT,
                "actions": _array(
                    _object(
                        {
                            "action_id": _STR,
                            "label": _STR,
                            "owner_tab": {"type": ["string", "null"]},
                            "topic": {"type": ["string", "null"]},
                            "shortcut": {"type": ["string", "null"]},
                            "enabled": {
                                "type": "boolean",
                                "description": "Whether the action is runnable right now (false when a precondition is unmet; read reason).",
                            },
                            "reason": {
                                "type": ["string", "null"],
                                "description": "Why the action is not runnable now, or null when it is.",
                            },
                        },
                        ["action_id", "label", "enabled", "reason"],
                    )
                ),
                "source": _source(),
            },
            ["count", "actions"],
        ),
        "annotations": READ_ONLY,
        "handler": "list_actions",
    },
    {
        "name": "list_sessions",
        "title": "List workspace sessions",
        "description": (
            "List the workspace sessions the app currently has open (id, type, "
            "title, active flag). Use it to see which tab kinds exist and which "
            "one is active. Answers from the live instance when one is "
            "attached, so it reflects the window the user is driving; otherwise "
            "it reads a fresh headless snapshot and may lag. Do NOT use it to "
            "switch tabs — that is open_tab."
        ),
        "inputSchema": _params(),
        "outputSchema": _object(
            {
                "count": _INT,
                "sessions": _array(
                    _object(
                        {
                            "id": _STR,
                            "session_type": _STR,
                            "title": _STR,
                            "active": _BOOL,
                        },
                        ["id", "session_type", "title", "active"],
                    )
                ),
                "source": _source(),
            },
            ["count", "sessions"],
        ),
        "annotations": READ_ONLY,
        "handler": "list_sessions",
    },
    {
        "name": "get_state",
        "title": "Read Redux Store slice",
        "description": (
            "Return a slice of the Redux Store (settings, workspace sessions, "
            "active document summary) as JSON; pass a dotted path such as "
            "settings.theme to narrow it. Answers from the live instance when "
            "one is attached, so it shows the user's current DOM; otherwise it "
            "reads a cached headless snapshot. Do NOT use it for pixel data or "
            "image contents — it never returns file bytes."
        ),
        "inputSchema": _params(
            {
                "path": {
                    **_STR,
                    "description": "Dotted slice path into the state, e.g. settings.theme; omit for the whole state.",
                }
            }
        ),
        "outputSchema": _object(
            {
                "path": {"type": ["string", "null"]},
                "state": {"description": "JSON value at path (whole state when path is omitted)."},
                "source": _source(),
            },
            ["path", "state"],
        ),
        "annotations": READ_ONLY,
        "handler": "get_state",
    },
    {
        "name": "get_canvas_scene",
        "title": "Read the canvas scene",
        "description": (
            "Read a tab's canvas scene as deterministic JSON: panes, dividers, "
            "every magnifier instance (hidden ones flagged), canvas size, and "
            "the camera/projection transform. Every geometry field names its "
            "coordinate space (canvas_px or composition_px) and its source. Use "
            "it before scene work to learn where the split and loupes are. "
            "Live-only; not Store state (get_state) or widgets (dump_ui_layout)."
        ),
        "inputSchema": _params(
            {
                "tab": {
                    **_STR,
                    "description": "Tab kind to read (e.g. image_compare); omit to read the active session's tab.",
                }
            }
        ),
        "outputSchema": _object(
            {
                "schema": _STR,
                "tab": _STR,
                "scene_source": {
                    "type": ["string", "null"],
                    "description": "ic_scene (Image Compare scene graph) / mc_projection (Multi Compare projection), or null when the tab has no canvas.",
                },
                "has_canvas": {
                    "type": "boolean",
                    "description": "Whether a live canvas widget was found for that tab right now.",
                },
                "tab_has_canvas_concept": {
                    "type": "boolean",
                    "description": "Whether the tab kind owns a canvas at all (false separates 'never has one' from 'not open yet').",
                },
                "reason": {
                    "type": ["string", "null"],
                    "description": "Why there is no scene when has_canvas is false; null otherwise.",
                },
                "space": {
                    "type": ["string", "null"],
                    "description": "The scene's primary coordinate space: canvas_px, composition_px, or null.",
                },
                "canvas": {
                    "type": ["object", "null"],
                    "description": "Canvas size with its space and source, or null when it is not known yet.",
                    "properties": {
                        "w": _INT,
                        "h": _INT,
                        "space": _STR,
                        "source": _STR,
                    },
                },
                "panes": _array(
                    _object(
                        {
                            "slot": _INT,
                            "path": {"type": ["string", "null"]},
                            "rect": {"type": "array", "items": {"type": "number"}},
                            "space": _STR,
                            "z": {"type": ["integer", "null"]},
                            "visible": {"type": "boolean"},
                            "painted": {"type": "boolean"},
                            "in_composition": {"type": "boolean"},
                            "reason": {"type": ["string", "null"]},
                            "rect_source": _STR,
                        },
                        ["slot", "rect", "space", "painted", "in_composition"],
                    )
                ),
                "dividers": _array(
                    _object(
                        {
                            "axis": _STR,
                            "pos": {"type": "number"},
                            "thickness": {"type": "number"},
                            "visible": {"type": "boolean"},
                            "space": _STR,
                            "thickness_space": _STR,
                            "source": _STR,
                        },
                        ["axis", "pos", "space", "visible"],
                    )
                ),
                "magnifiers": _array(
                    _object(
                        {
                            "id": _STR,
                            "visible": {"type": "boolean"},
                            "active": {"type": "boolean"},
                            "geometry_source": {
                                "type": ["string", "null"],
                                "description": "scene_graph when canvas geometry exists; null for a hidden instance (it has none in the render path).",
                            },
                            "space": {"type": ["string", "null"]},
                            "capture": {"type": ["object", "null"]},
                            "circles": _array({"type": "object", "additionalProperties": True}),
                            "geometry_unavailable_reason": {"type": ["string", "null"]},
                        },
                        ["id", "visible", "active", "geometry_source", "circles"],
                    )
                ),
                "transform": {
                    "type": ["object", "null"],
                    "description": "Camera (zoom/pan) plus the canvas→view or composition→framebuffer projection, or null without a canvas.",
                },
                "focus": {"type": ["object", "null"]},
                "sources": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Per-field provenance map: which source produced each block.",
                },
                "unavailable": _array(
                    _object(
                        {"field": _STR, "reason": _STR}, ["field", "reason"]
                    )
                ),
                "source": _source(),
            },
            [
                "schema",
                "tab",
                "has_canvas",
                "panes",
                "dividers",
                "magnifiers",
                "unavailable",
                "source",
            ],
        ),
        "annotations": READ_ONLY,
        "handler": "get_canvas_scene",
    },
    {
        "name": "read_log",
        "title": "Tail the app log file",
        "description": (
            "Return the last N lines of the app log, optionally filtered by "
            "minimum level. Use it to see recent app errors or lifecycle events "
            "without a terminal. Do NOT use it to read arbitrary files — the "
            "path is fixed to the app's own log. The app truncates the log on "
            "every start, so with a live instance the server serves the copy "
            "preserved before any fallback boot."
        ),
        "inputSchema": _params(
            {
                "n": {
                    **_INT,
                    "minimum": 1,
                    "maximum": 5000,
                    "default": 200,
                    "description": "How many trailing lines to return (most recent last).",
                },
                "level": {
                    **_STR,
                    "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    "description": "Only return lines at this level or above; omit for all levels.",
                },
            }
        ),
        "outputSchema": _object(
            {
                "path": _STR,
                "total_lines": _INT,
                "returned": _INT,
                "lines": _array(
                    _object({"n": _INT, "level": {"type": ["string", "null"]}, "text": _STR})
                ),
                "source": _source(),
            },
            ["path", "total_lines", "returned", "lines"],
        ),
        "annotations": READ_ONLY,
        "handler": "read_log",
    },
    {
        "name": "query_trace",
        "title": "Query the causal tracer",
        "description": (
            "Search the causal tracer (Redux dispatches, EventBus publishes, "
            "render frames) by substring, trace id, or kind, newest first. Use "
            "it to explain 'weird after click/zoom' chains when plain logs are "
            "not enough. Answers from the live instance when one is attached, "
            "else from trace.jsonl on disk. Do NOT use it as a general log — it "
            "only holds records written while IMGSLI_TRACE was on."
        ),
        "inputSchema": _params(
            {
                "filter": {
                    **_STR,
                    "description": "Substring matched against each record's JSON text; omit to return the newest records regardless.",
                },
                "n": {
                    **_INT,
                    "minimum": 1,
                    "maximum": 2000,
                    "default": 100,
                    "description": "Maximum records to return, newest first.",
                },
            }
        ),
        "outputSchema": _object(
            {
                "path": _STR,
                "total_records": _INT,
                "returned": _INT,
                "records": _array({"type": "object", "additionalProperties": True}),
                "source": _source(),
            },
            ["path", "total_records", "returned", "records"],
        ),
        "annotations": READ_ONLY,
        "handler": "query_trace",
    },
    {
        "name": "dump_ui_layout",
        "title": "Dump the widget tree",
        "description": (
            "Dump the widget tree (class, geometry, colors, bound Find Action "
            "ids) to JSON, returning a summary. Use it for layout/spacing/"
            "visibility questions instead of a screenshot. Pass tab to target a "
            "tab's chrome. Answers from the live window when an instance is "
            "attached, else boots the app headlessly; either way it is geometry "
            "and color values, never pixels."
        ),
        "inputSchema": _params(
            {
                "tab": {
                    **_STR,
                    "enum": list(TAB_KINDS),
                    "description": "Open this tab before dumping, so its own chrome appears in the tree.",
                },
                "out": {
                    **_STR,
                    "description": "Destination JSON path; defaults to the server's artifacts directory.",
                },
            }
        ),
        "outputSchema": _object(
            {
                "path": _STR,
                "tab": {"type": ["string", "null"]},
                "windows": _INT,
                "node_count": _INT,
                "source": _source(),
            },
            ["path", "windows", "node_count"],
        ),
        "annotations": READ_ONLY,
        "handler": "dump_ui_layout",
    },
    {
        "name": "list_surfaces",
        "title": "List capture surfaces",
        "description": (
            "List the named surfaces the capture_surface devtool can screenshot "
            "(e.g. settings, gallery-populated), with a description and whether "
            "each runs isolated. Use it before capture_surface to get a valid "
            "name. Answers from the live instance when one is attached, else "
            "from the devtool registry. Do NOT guess surface names, and note it "
            "never captures anything itself."
        ),
        "inputSchema": _params(),
        "outputSchema": _object(
            {
                "count": _INT,
                "surfaces": _array(
                    _object(
                        {
                            "name": _STR,
                            "description": _STR,
                            "isolated": _BOOL,
                            "live": _BOOL,
                            "capturable": _BOOL,
                        },
                        ["name", "description"],
                    ),
                ),
                "source": _source(),
            },
            ["count", "surfaces"],
        ),
        "annotations": READ_ONLY,
        "handler": "list_surfaces",
    },
    {
        "name": "open_tab",
        "title": "Open a workspace tab",
        "description": (
            "Open or focus a workspace tab of the given kind. With a live "
            "instance attached it switches the running window (no new process, "
            "'ran': true). Without one it launches a fresh app process, reusing "
            "the tab's live fallback process when there is one ('reused': "
            "true). Do NOT use it when you only need to inspect a tab — "
            "dump_ui_layout with tab does that without opening a window."
        ),
        "inputSchema": _params(
            {
                "tab": {
                    **_STR,
                    "enum": list(TAB_KINDS),
                    "description": "Tab kind to create and switch to.",
                }
            },
            ["tab"],
        ),
        "outputSchema": _object(
            {
                "launched": _BOOL,
                "pid": {"type": ["integer", "null"]},
                "tab": _STR,
                "ran": {"type": "boolean", "description": "True when the live instance switched to the tab."},
                "reused": {"type": "boolean", "description": "True when a live fallback process for this tab was reused."},
                "source": _source(),
            },
            ["tab"],
        ),
        "annotations": MUTATING,
        "handler": "open_tab",
    },
    {
        "name": "run_action",
        "title": "Run a Find Action or a scene command",
        "description": (
            "Run one registered Find Action by id (a bare action_id), or a scene "
            "command by name with typed params — e.g. magnifier.set_visible, "
            "divider.set_thickness, layout.set_split_weights. A scene command is "
            "value-taking and idempotent; pass expect (scene path → value) and the "
            "scene is re-read afterwards to prove the change ('verified'). Unknown "
            "params are refused with the schema in the hint."
        ),
        "inputSchema": _params(
            {
                "action_id": {
                    **_STR,
                    "description": "Exact ActionRegistry id (e.g. platform.settings, see list_actions) or a scene command name (see set_scene_commands).",
                },
                "params": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Typed params for a scene command (e.g. {\"id\": \"loupe-a\", \"visible\": false}); refuse-with-schema on an unknown key. Omit for Find Actions.",
                },
                "expect": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Scene post-conditions for a scene command: {\"magnifiers[0].visible\": true}. With it the scene is re-read and verified; a command that changed nothing fails.",
                },
                "tab": {
                    **_STR,
                    "enum": list(TAB_KINDS),
                    "description": "Optionally target this tab first, so tab-scoped actions register before the action runs (or the scene command resolves the right canvas).",
                },
            },
            ["action_id"],
        ),
        "outputSchema": _object(
            {
                "launched": _BOOL,
                "pid": {"type": ["integer", "null"]},
                "action_id": _STR,
                "tab": {"type": ["string", "null"]},
                "ran": {"type": "boolean", "description": "True when the live instance ran the action (or the scene command executed)."},
                "scene_command": {
                    "type": "boolean",
                    "description": "True when action_id named a scene command instead of a Find Action.",
                },
                "params": {"type": "object", "additionalProperties": True},
                "changed": _array(_STR),
                "verified": {"type": ["boolean", "null"], "description": "Verification verdict when expect was given; null otherwise."},
                "failure": {
                    "type": ["object", "null"],
                    "description": "Why verification failed (problems + changed paths), null when verified or unverified.",
                },
                "live": _live_flag(),
                "source": _source(),
            },
            ["action_id"],
        ),
        "annotations": MUTATING_RISKY,
        "handler": "run_action",
    },
    {
        "name": "set_scene_commands",
        "title": "Run an ordered scene command list",
        "description": (
            "Set a canvas scene by running an ordered list of value-taking commands "
            "(magnifier visible/position/size/combined, divider visible/thickness, "
            "Multi Compare split weights). Stops at the first error; nothing after "
            "it runs. With verify=true (default) each command declares expect scene "
            "paths and the scene is re-read: a command that changed nothing, or "
            "changed undeclared state, fails."
        ),
        "inputSchema": _params(
            {
                "commands": {
                    **_array(
                        _object(
                            {
                                "action": {
                                    **_STR,
                                    "description": "Scene command name, e.g. magnifier.set_visible.",
                                },
                                "params": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "description": "Typed params for that command (unknown keys are refused with the schema).",
                                },
                                "expect": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "description": "Scene path → expected value, checked by re-reading the scene (required when verify=true).",
                                },
                            },
                            ["action"],
                        )
                    ),
                    "description": "Ordered commands; each item is {action, params, expect}. Execution stops at the first failure.",
                },
                "verify": {
                    "type": "boolean",
                    "default": True,
                    "description": "Re-read the scene after each command and check expect; a no-op or undeclared change fails.",
                },
                "tab": {
                    **_STR,
                    "enum": list(TAB_KINDS),
                    "description": "Tab kind whose canvas is commanded; omit to use the active session's tab.",
                },
            },
            ["commands"],
        ),
        "outputSchema": _object(
            {
                "ok": _BOOL,
                "verified": {"type": ["boolean", "null"]},
                "count": _INT,
                "applied": _array({"type": "object", "additionalProperties": True}),
                "stopped_at": {"type": ["integer", "null"], "description": "Index of the first failing command, null when every command ran and verified."},
                "error": {
                    "type": ["object", "null"],
                    "description": "The first failure: index, action, kind (invalid_command / verification_failed / command_crashed), message, hint.",
                },
                "tab": {"type": ["string", "null"]},
                "scene": {
                    "type": ["object", "null"],
                    "description": "The scene as re-read through get_canvas_scene after the run.",
                },
                "source": _source(),
            },
            ["ok", "count", "applied", "stopped_at", "error"],
        ),
        "annotations": MUTATING,
        "handler": "set_scene_commands",
    },
    {
        "name": "open_folder",
        "title": "Open an image folder",
        "description": (
            "Validate an existing directory and hand it to a tab. With a live "
            "instance attached the running app routes it ('routed': true); pass "
            "tab=<kind> (e.g. multi_compare) to target that tab — it is opened "
            "if absent, and a file-only tab receives the folder's images as "
            "files. Without a live instance the folder cannot be injected, so "
            "routed stays false. The path must be a real directory."
        ),
        "inputSchema": _params(
            {
                "path": {
                    **_STR,
                    "description": "Absolute (or ~-prefixed) path to an existing directory of images.",
                },
                "tab": {
                    **_STR,
                    "description": "Tab kind to hand the folder to (e.g. multi_compare, image_compare); opened if absent. Omit to auto-route to the first tab that accepts a directory.",
                },
                "slot": {
                    "type": "integer",
                    "enum": [1, 2],
                    "description": (
                        "Image Compare target slot: 1 = left, 2 = right. Two "
                        "calls, one per slot, compose a pair without a mouse "
                        "drop. Mutually exclusive with side=."
                    ),
                },
                "side": {
                    **_STR,
                    "enum": ["left", "right", "top", "bottom"],
                    "description": (
                        "Multi Compare placement axis for the folder's images "
                        "after the first ('right' composes a row, 'bottom' a "
                        "column). Mutually exclusive with slot=."
                    ),
                },
            },
            ["path"],
        ),
        "outputSchema": _object(
            {
                "launched": _BOOL,
                "pid": {"type": ["integer", "null"]},
                "path": _STR,
                "routed": _BOOL,
                "tab": {
                    "type": ["string", "null"],
                    "description": "Session kind that accepted the folder.",
                },
                "images": {
                    "type": ["integer", "null"],
                    "description": "Files handed over when the tab takes files, not a directory.",
                },
                "ran": {"type": "boolean", "description": "True when the live instance routed the folder."},
                "live": _live_flag(),
                "source": _source(),
            },
            ["path", "routed"],
        ),
        "annotations": MUTATING,
        "handler": "open_folder",
    },
    {
        "name": "open_file",
        "title": "Open one image file in a tab",
        "description": (
            "Load one file into the tab that accepts it, through that tab's own "
            "drag-and-drop hook. With a live instance an image goes to Image "
            "Compare when that tab is open, else to the gallery; pass tab=<kind> "
            "to force the target. slot=<1|2> / side=<axis> place it like a mouse "
            "drop — two calls, one per slot, compose a pair. A video is refused "
            "by name. Live-only."
        ),
        "inputSchema": _params(
            {
                "path": {
                    **_STR,
                    "description": "Absolute (or ~-prefixed) path to an existing image file.",
                },
                "tab": {
                    **_STR,
                    "description": (
                        "Tab kind to hand the file to (validated against the "
                        "registered kinds); omit to auto-route. A kind that does "
                        "not accept the file is an error, never a fallback."
                    ),
                },
                "slot": {
                    "type": "integer",
                    "enum": [1, 2],
                    "description": (
                        "Image Compare target slot: 1 = left, 2 = right. Two "
                        "calls, one per slot, compose a pair without a mouse "
                        "drop. Mutually exclusive with side=."
                    ),
                },
                "side": {
                    **_STR,
                    "enum": ["left", "right", "top", "bottom"],
                    "description": (
                        "Multi Compare placement axis for the file ('right' "
                        "composes a row, 'bottom' a column). Mutually exclusive "
                        "with slot=."
                    ),
                },
            },
            ["path"],
        ),
        "outputSchema": _object(
            {
                "opened": _BOOL,
                "path": _STR,
                "tab": {
                    **_STR,
                    "description": "Session kind whose own drop hook took the file.",
                },
                "count": _INT,
                "source": _source(),
            },
            ["opened", "path", "tab", "count"],
        ),
        "annotations": MUTATING,
        "handler": "open_file",
    },
    {
        "name": "open_properties",
        "title": "Show image properties for a file",
        "description": (
            "Show the app's own image-properties dialog for an existing file, "
            "through the plugin the Image Compare context menu uses. The dialog "
            "is shown non-modally, so the call answers while it is on screen, "
            "and it returns the dialog class name. Use it to read metadata no "
            "screenshot shows. A missing path is rejected before any dialog "
            "opens, and there is no headless analogue: it needs a running app."
        ),
        "inputSchema": _params(
            {
                "path": {
                    **_STR,
                    "description": "Absolute (or ~-prefixed) path to an existing image file.",
                }
            },
            ["path"],
        ),
        "outputSchema": _object(
            {
                "opened": _BOOL,
                "path": _STR,
                "dialog": _STR,
                "source": _source(),
            },
            ["opened", "path", "dialog"],
        ),
        "annotations": MUTATING,
        "handler": "open_properties",
    },
    {
        "name": "set_theme",
        "title": "Set persisted theme",
        "description": (
            "Set the app theme. With a live instance attached the running "
            "window restyles immediately ('live': true, applies_on 'now'); "
            "otherwise it persists the choice for the next launch. Idempotent — "
            "setting the same theme twice is a no-op. Do NOT use it to capture "
            "a themed screenshot (pass theme to capture_surface)."
        ),
        "inputSchema": _params(
            {
                "theme": {
                    **_STR,
                    "enum": list(THEMES),
                    "description": "Theme to apply or persist.",
                }
            },
            ["theme"],
        ),
        "outputSchema": _object(
            {
                "theme": _STR,
                "persisted": _BOOL,
                "applies_on": _STR,
                "live": _live_flag(),
                "source": _source(),
            },
            ["theme", "applies_on"],
        ),
        "annotations": MUTATING,
        "handler": "set_theme",
    },
    {
        "name": "set_language",
        "title": "Set persisted UI language",
        "description": (
            "Set the app UI language. With a live instance attached the running "
            "window retranslates immediately ('live': true, applies_on 'now'); "
            "otherwise it persists the choice for the next launch. Idempotent. "
            "Do NOT use it to translate text yourself — read app://theme for "
            "the active language."
        ),
        "inputSchema": _params(
            {
                "language": {
                    **_STR,
                    "enum": list(LANGUAGES),
                    "description": "Language code to apply or persist.",
                }
            },
            ["language"],
        ),
        "outputSchema": _object(
            {
                "language": _STR,
                "persisted": _BOOL,
                "applies_on": _STR,
                "live": _live_flag(),
                "source": _source(),
            },
            ["language", "applies_on"],
        ),
        "annotations": MUTATING,
        "handler": "set_language",
    },
    {
        "name": "set_setting",
        "title": "Write one whitelisted setting",
        "description": (
            "Write one whitelisted scalar setting and report the value it "
            "replaced. The whitelist is rhi_backend (opengl|vulkan); theme and "
            "language keep their own verbs and are refused by name. The value is "
            "persisted through the app's settings scope; applied says whether the "
            "running store took it now — rhi_backend applies at restart. Without "
            "a live instance it persists for the next start, with previous null."
        ),
        "inputSchema": _params(
            {
                "key": {
                    **_STR,
                    "description": (
                        "Setting key; only rhi_backend is accepted (theme and "
                        "language belong to set_theme/set_language)."
                    ),
                },
                "value": {
                    **_STR,
                    "description": "New value; rhi_backend accepts only opengl or vulkan.",
                },
            },
            ["key", "value"],
        ),
        "outputSchema": _object(
            {
                "key": _STR,
                "value": _STR,
                "applied": {
                    "type": "boolean",
                    "description": "True when the running store adopted the value now (rhi_backend applies at restart).",
                },
                "persisted": {
                    "type": "boolean",
                    "description": "True when the value was written to the app's settings.",
                },
                "previous": {
                    "type": ["string", "null"],
                    "description": "The value it replaced, or null when unset/unknown.",
                },
                "source": _source(),
            },
            ["key", "value", "applied", "persisted", "previous"],
        ),
        "annotations": MUTATING,
        "handler": "set_setting",
    },
    {
        "name": "capture_surface",
        "title": "Capture a surface PNG",
        "description": (
            "Screenshot the live app's active window (omit surface) or one named surface to a PNG; "
            "a live capture reports what it grabbed (what), the grab method (method) and how many "
            "canvas frames were composited (rhi_layers). With no live instance the devtool boots "
            "headless and surface is required. Use it for visual checks and Help figures."
        ),
        "inputSchema": _params(
            {
                "surface": {
                    **_STR,
                    "description": (
                        "Surface name from list_surfaces. Omit to capture the live active window "
                        "(refused if there is no live instance or no window)."
                    ),
                },
                "theme": {
                    **_STR,
                    "enum": list(THEMES),
                    "description": (
                        "Fallback capture theme (headless devtool boot); a live capture keeps the "
                        "running window's own theme. See options_applied."
                    ),
                },
                "out": {
                    **_STR,
                    "description": (
                        "Fallback output directory; a live capture always writes to the app's "
                        "artifacts directory. See options_applied."
                    ),
                },
            },
        ),
        "outputSchema": _object(
            {
                "surface": _STR,
                "what": {
                    **_STR,
                    "description": "What was actually grabbed (surface name, or the live window's label).",
                },
                "path": _STR,
                "method": {
                    "type": ["string", "null"],
                    "description": "Live grab method (grabWindow/widget_grab); null on the fallback path.",
                },
                "size": {
                    "type": ["array", "null"],
                    "items": _INT,
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[width, height] in pixels; null when the path cannot report it.",
                },
                "rhi_layers": {
                    "type": ["integer", "null"],
                    "description": (
                        "Canvas frames composited into the live grab (0 = no presenting canvas); "
                        "null on the fallback path."
                    ),
                },
                "theme": {
                    "type": ["string", "null"],
                    "description": "Theme the fallback capture applied; null for a live capture (as-is).",
                },
                "live": _live_flag(),
                "source": _source(),
                "options_applied": {
                    **_array(_STR),
                    "description": "Request parameters that took effect (theme/out are fallback-only).",
                },
                "unavailable": {
                    **_array(_STR),
                    "description": "Provenance fields this path cannot report (named, never invented).",
                },
            },
            ["surface", "what", "path", "source"],
        ),
        "annotations": MUTATING,
        "handler": "capture_surface",
    },
    {
        "name": "press_keys",
        "title": "Press keys in the running app",
        "description": (
            "Inject keyboard input into a running instance: one combo "
            "(ctrl+shift+p) or comma-separated combos in order. "
            "target=<ui_elements id> aims at a widget the focus chain never "
            "reaches (a canvas). The window is activated first and the result "
            "reports activated/focus_is_ours; with no active window the call is "
            "refused — focus it (xdotool windowfocus <window-id>) and retry. "
            "Live-only, allowlisted keys."
        ),
        "inputSchema": _params(
            {
                "keys": {
                    **_STR,
                    "description": "One combo (ctrl+shift+p) or comma-separated combos applied in order (Down,Down,Enter).",
                }
                ,
                "target": {
                    **_STR,
                    "description": "Element id from ui_elements to type into (e.g. a canvas), or property:<name>=<value>. Default: the focused widget.",
                },
            },
            ["keys"],
        ),
        "outputSchema": _object(
            {
                "pressed": _array(_STR),
                "count": _INT,
                "target": _STR,
                "activated": _bool_or_null(
                    "True when this call had to bring the app window forward; "
                    "false when it already held focus; null when the app did not report it."
                ),
                "focus_is_ours": _bool_or_null(
                    "True when the key went to the window that holds OS focus — "
                    "false means it went elsewhere, so read the key as not delivered."
                ),
                "source": _source(),
            },
            ["pressed", "count"],
        ),
        "annotations": MUTATING_INPUT,
        "handler": "press_keys",
    },
    {
        "name": "nav_key",
        "title": "Press keys through the app's keyboard navigation",
        "description": (
            "Deliver keys through the app's own keyboard navigation — the "
            "ordered sections (title bar, tab strip, section rows) and each "
            "surface's key handler — instead of aiming one event at one widget: "
            "the honest way to judge whether a control is reachable by "
            "keyboard. Each step reports which layer took the key and how focus "
            "moved. anchor=<element id> focuses it first. Live-only."
        ),
        "inputSchema": _params(
            {
                "keys": {
                    **_STR,
                    "description": "One combo or comma-separated combos applied in order (Down,Enter,Tab).",
                },
                "anchor": {
                    **_STR,
                    "description": "Element id from ui_elements to focus first (with the app's own focus reason), or property:<name>=<value>; omit to keep current focus.",
                },
            },
            ["keys"],
        ),
        "outputSchema": _object(
            {
                "keys": _array(_STR),
                "count": _INT,
                "anchor": _row_or_null("Where the keys were delivered (null if nothing holds focus)."),
                "activated": _BOOL,
                "focus_is_ours": _BOOL,
                "focus_after": _row_or_null("Focus widget after the last key."),
                "steps": _array(_object(
                    {
                        "key": _STR,
                        "delivered_to": _row_or_null("Widget this key reached."),
                        "handled": _STR,
                        "accepted": _BOOL,
                        "focus_before": _row_or_null("Focus before this key."),
                        "focus_after": _row_or_null("Focus after this key."),
                        "owner_before": {"type": ["string", "null"]},
                        "owner_after": {"type": ["string", "null"]},
                    },
                    ["key", "handled"],
                )),
                "source": _source(),
            },
            ["keys", "count", "steps"],
        ),
        "annotations": MUTATING_INPUT,
        "handler": "nav_key",
    },
    {
        "name": "ui_nav_state",
        "title": "Read the keyboard-navigation model",
        "description": (
            "The live keyboard-navigation model: ordered sections (section, "
            "owner, extra keys), the Qt focus widget, the last "
            "keyboard-granted widget, input modality, and every open in-window "
            "overlay with the children Qt could focus but no section owns — the "
            "honest 'a key cannot reach this' signal. Read it before blaming a "
            "control, and pair it with nav_key. Read-only and live-only."
        ),
        "inputSchema": _params(),
        "outputSchema": _object(
            {
                "modality": _object(
                    {
                        "last_input_was_keyboard": {"type": ["boolean", "null"]},
                        "focus_reason": {"type": ["string", "null"]},
                    },
                    ["last_input_was_keyboard", "focus_reason"],
                ),
                "focus": _row_or_null("Widget holding Qt focus right now."),
                "last_keyboard_focus": _row_or_null("Last widget the app granted focus to by keyboard."),
                "owner_section": {"type": ["string", "null"]},
                "sections": _array(_object(
                    {
                        "index": _INT,
                        "section": _STR,
                        "owner": _STR,
                        "extra_keys": _array(_STR),
                    },
                    ["index", "section", "owner"],
                )),
                "sections_count": _INT,
                "overlays": _array(_object(
                    {
                        "widget": _STR,
                        "object_name": _STR,
                        "label": _STR,
                        "role": {"type": ["string", "null"]},
                        "element_id": {"type": ["string", "null"]},
                        "focus_policy": _STR,
                        "keyboard_ring": {"type": ["boolean", "null"]},
                        "owned_by_section": {"type": ["string", "null"]},
                        "enabled": {"type": ["boolean", "null"]},
                        "visible": {"type": ["boolean", "null"]},
                        "screen_rect": {"type": ["array", "null"], "items": _INT},
                        "children_total": _INT,
                        "children_shown": _INT,
                        "children_truncated": _BOOL,
                        "focused_child": _row_or_null("Child of this overlay that holds focus, if any."),
                        "children": _array(_object(
                            {
                                "widget": _STR,
                                "object_name": _STR,
                                "label": _STR,
                                "role": {"type": ["string", "null"]},
                                "element_id": {"type": ["string", "null"]},
                                "focus_policy": _STR,
                                "keyboard_ring": {"type": ["boolean", "null"]},
                                "owned_by_section": {"type": ["string", "null"]},
                                "enabled": {"type": ["boolean", "null"]},
                                "visible": {"type": ["boolean", "null"]},
                                "screen_rect": {"type": ["array", "null"], "items": _INT},
                            },
                            ["widget"],
                        )),
                    },
                    ["widget"],
                )),
                "source": _source(),
            },
            ["sections", "sections_count", "overlays"],
        ),
        "annotations": READ_ONLY,
        "handler": "ui_nav_state",
    },
    {
        "name": "ui_elements",
        "title": "Inventory interactive elements",
        "description": (
            "Flattened inventory of the live window's interactive elements: id, "
            "role, label, rects, enabled, visible, bound action, and a properties "
            "bag. Narrow with role (exact), label (case-insensitive substring), "
            "properties (exact matches) and limit. Call it FIRST for ui_click / "
            "ui_hover / ui_focus ids; they are session-scoped — re-read, do not "
            "cache across starts. Live-only. Do NOT use it to run anything."
        ),
        "inputSchema": _params(
            {
                "scope": {
                    **_STR,
                    "description": "Only inventory elements under this scope (e.g. a window or tab id); omit for the whole app.",
                },
                "include_disabled": {
                    **_BOOL,
                    "description": "Include disabled elements too; omit to list only enabled ones.",
                },
                "role": {
                    **_STR,
                    "description": "Only elements with exactly this role (e.g. button, card, tab, menu-row). Omit for every role.",
                },
                "label": {
                    **_STR,
                    "description": "Only elements whose label contains this text, case-insensitively. Omit for every label.",
                },
                "properties": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "integer", "number", "boolean"]},
                    "description": "Only elements whose own properties bag matches every name→value pair exactly (e.g. {\"gallery_path\": \"/a.png\"}).",
                },
                "limit": {
                    **_INT,
                    "minimum": 1,
                    "maximum": 2000,
                    "description": "Return at most this many rows, in tree order; report the pre-limit match count in total. Default: unlimited.",
                },
            }
        ),
        "outputSchema": _object(
            {
                "count": _INT,
                "total": _INT,
                "window_count": _INT,
                "elements": _array(
                    _object(
                        {
                            "id": _STR,
                            "role": _STR,
                            "label": _STR,
                            "rect": _rect("Widget-local [x, y, w, h] geometry."),
                            "screen_rect": _rect(
                                "Screen-space [x, y, w, h] (best-effort on Wayland)."
                            ),
                            "window": _STR,
                            "owner_tab": {"type": ["string", "null"]},
                            "action_id": {"type": ["string", "null"]},
                            "enabled": _BOOL,
                            "visible": _BOOL,
                            "properties": {
                                "type": "object",
                                "additionalProperties": {"type": ["string", "integer", "number", "boolean"]},
                                "description": "The widget's own serialisable dynamic properties (e.g. gallery_path). Address one with property:<name>=<value>.",
                            },
                        },
                        ["id", "properties"],
                    )
                ),
                "source": _source(),
            },
            ["count", "window_count", "elements"],
        ),
        "annotations": READ_ONLY,
        "handler": "ui_elements",
    },
    {
        "name": "ui_batch",
        "title": "Run an ordered batch of UI actions",
        "description": (
            "Run an ordered list of UI actions in ONE call instead of one call "
            "per action: each item is {tool, arguments}, the same object the "
            "single tool takes (an unknown tool or key is refused with the "
            "allowed list). Stops at the first failure unless "
            "stop_on_error=false. No rollback: earlier items stay applied and "
            "results say what ran. One call costs one agent turn; N calls cost N."
        ),
        "inputSchema": _params(
            {
                "actions": {
                    **_array(
                        _object(
                            {
                                "tool": {
                                    **_STR,
                                    "enum": sorted(BATCH_TOOLS),
                                    "description": "A single-action tool name; ui_batch itself is not batchable.",
                                },
                                "arguments": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "description": "The arguments object that tool takes on its own (e.g. {id} for ui_click).",
                                },
                            },
                            ["tool"],
                        )
                    ),
                    "minItems": 1,
                    "maxItems": MAX_BATCH_ACTIONS,
                    "description": "Ordered actions; each runs through the same handler as the single tool.",
                },
                "stop_on_error": {
                    **_BOOL,
                    "default": True,
                    "description": "Stop at the first failing item (default) or continue and report every failure.",
                },
                "settle_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": MAX_BATCH_SETTLE_MS,
                    "default": 0,
                    "description": "Pause between items for animations/settle. Prefer wait_for inside the batch when the expectation is observable.",
                },
            },
            ["actions"],
        ),
        "outputSchema": _object(
            {
                "ok": _BOOL,
                "count": _INT,
                "ok_count": _INT,
                "results": _array(
                    _object(
                        {
                            "index": _INT,
                            "tool": _STR,
                            "ok": _BOOL,
                            "result": {"type": ["object", "null"], "additionalProperties": True},
                            "error": {"type": ["object", "null"], "additionalProperties": True},
                        },
                        ["index", "tool", "ok"],
                    )
                ),
                "stopped_at": {"type": ["integer", "null"], "description": "Index of the first failing item, null when every item ran."},
                "error": {
                    "type": ["object", "null"],
                    "description": "The first failure: index, tool, kind (invalid_item / tool_error / crashed), message, hint.",
                },
                "settle_ms": _INT,
                "source": {
                    "type": "string",
                    "enum": ["live", "fallback", "mixed"],
                    "description": "live/fallback when every item agreed, mixed when the batch crossed both paths.",
                },
            },
            ["ok", "count", "ok_count", "results", "stopped_at", "error"],
        ),
        "annotations": MUTATING_INPUT,
        "handler": "ui_batch",
    },
    {
        "name": "ui_click",
        "title": "Click an element by id",
        "description": (
            "Click one interactive element by its id from ui_elements, delivered "
            "in-process at the element's centre. Call ui_elements first. Unknown "
            "ids are retried about 3 s and then fail with close matches. "
            "In-process delivery fires the handler even when the element is "
            "off-screen, but the visible effect still needs it on screen. "
            "rect is widget-local, screen_rect is screen-space (Wayland "
            "best-effort)."
        ),
        "inputSchema": _params(
            {
                "id": {
                    **_STR,
                    "description": "Element id from ui_elements (session-scoped), or a stable property:<name>=<value> reference.",
                },
                "button": {
                    **_STR,
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button to click; defaults to left (right opens context menus).",
                },
                "count": {
                    **_INT,
                    "minimum": 1,
                    "description": "Click count; omit for a single click.",
                },
            },
            ["id"],
        ),
        "outputSchema": _object(
            {
                "clicked": _BOOL,
                "id": _STR,
                "rect": _rect("Widget-local rect the click resolved to."),
                "screen_rect": _rect("Screen-space rect (best-effort on Wayland)."),
                "target": _STR,
                "surface": _STR,
                "source": _source(),
            },
            ["clicked", "id", "rect", "screen_rect"],
        ),
        "annotations": MUTATING_INPUT,
        "handler": "ui_click",
    },
    {
        "name": "ui_hover",
        "title": "Hover an element by id",
        "description": (
            "Hover one interactive element by its id from ui_elements, delivered "
            "in-process. Call ui_elements first; ids are session-scoped. Unknown "
            "ids are retried about 3 s then fail with close matches. Idempotent. "
            "In-process delivery needs no on-screen visibility, but the visible "
            "hover effect does. rect is widget-local; screen_rect is screen-space "
            "(best-effort on Wayland)."
        ),
        "inputSchema": _params(
            {"id": {**_STR, "description": "Element id from ui_elements (session-scoped), or a stable property:<name>=<value> reference."}},
            ["id"],
        ),
        "outputSchema": _object(
            {
                "hovered": _BOOL,
                "id": _STR,
                "rect": _rect("Widget-local rect the hover resolved to."),
                "target": _STR,
                "source": _source(),
            },
            ["hovered", "id", "rect"],
        ),
        "annotations": MUTATING,
        "handler": "ui_hover",
    },
    {
        "name": "ui_focus",
        "title": "Focus an element by id",
        "description": (
            "Give keyboard focus to one interactive element by its id from "
            "ui_elements, delivered in-process. Call ui_elements first; ids are "
            "session-scoped. Unknown ids are retried about 3 s then fail with "
            "close matches. Idempotent. In-process delivery needs no on-screen "
            "visibility, but the visible focus effect does. rect is widget-local; "
            "screen_rect is screen-space (best-effort on Wayland)."
        ),
        "inputSchema": _params(
            {"id": {**_STR, "description": "Element id from ui_elements (session-scoped), or a stable property:<name>=<value> reference."}},
            ["id"],
        ),
        "outputSchema": _object(
            {
                "focused": _BOOL,
                "id": _STR,
                "rect": _rect("Widget-local rect the focus resolved to."),
                "target": _STR,
                "focus_widget": _STR,
                "source": _source(),
            },
            ["focused", "id", "rect"],
        ),
        "annotations": MUTATING,
        "handler": "ui_focus",
    },
    {
        "name": "ui_wheel",
        "title": "Send wheel events to an element (phase-aware)",
        "description": (
            "Deliver `count` wheel events to one element by id, in-process, one 120"
            "-unit step each. `phase` picks the scroll phase: `none` (plain notch) "
            "or `begin`/`update`/`end` (touchpads mark every event `begin`). `ctrl`"
            "/`shift`/`alt` carry modifiers — a canvas zooms on Ctrl+wheel only. `r"
            "aw=true` keeps the event on the element; a canvas always keeps it. Liv"
            "e-only."
        ),
        "inputSchema": _params(
            {
                "id": {
                    **_STR,
                    "description": "Element id from ui_elements (session-scoped), or a stable property:<name>=<value> reference.",
                },
                "delta": {
                    **_INT,
                    "default": 120,
                    "description": "Angle delta per event in Qt units (120 = one mouse-wheel notch); negative scrolls the other way.",
                },
                "phase": {
                    **_STR,
                    "enum": ["none", "begin", "update", "end"],
                    "default": "none",
                    "description": "Qt scroll phase: none | begin | update | end.",
                },
                "count": {
                    **_INT,
                    "minimum": 1,
                    "maximum": 200,
                    "default": 1,
                    "description": "How many wheel events to send (1..200).",
                },
                "raw": {
                    **_BOOL,
                    "default": False,
                    "description": "Keep the event on the element instead of routing to its owning scroll area (a canvas always keeps it).",
                },
                "ctrl": {**_BOOL, "default": False, "description": "Hold Ctrl (canvases zoom on Ctrl+wheel)."},
                "shift": {**_BOOL, "default": False, "description": "Hold Shift."},
                "alt": {**_BOOL, "default": False, "description": "Hold Alt."},
            },
            ["id"],
        ),
        "outputSchema": _object(
            {
                "sent": {
                    **_INT,
                    "description": "How many wheel events this call delivered.",
                },
                "delta": _INT,
                "phase": _STR,
                "modifiers": {"type": "array", "items": _STR},
                "raw": _BOOL,
                "id": _STR,
                "surface": _source(),
            },
            ["sent", "delta", "phase", "id"],
        ),
        "annotations": MUTATING_INPUT,
        "handler": "ui_wheel",
    },
    {
        "name": "ui_press",
        "title": "Press an element and optionally hold it",
        "description": (
            "Press one element's left mouse button by id from ui_elements, "
            "in-process. release=true (default) is one press and release with "
            "hold_ms of waiting between (clamped to 5000); release=false parks "
            "the press and answers, and the next call with that id releases the "
            "same widget — pressing another element releases the parked one too, "
            "so a button is never left down. Live-only, session-scoped ids."
        ),
        "inputSchema": _params(
            {
                "id": {
                    **_STR,
                    "description": "Element id from ui_elements (session-scoped), or a stable property:<name>=<value> reference.",
                },
                "hold_ms": {
                    **_INT,
                    "minimum": 0,
                    "maximum": 5000,
                    "default": 0,
                    "description": "Milliseconds to hold between press and release of one press+release; clamped to 0..5000.",
                },
                "release": {
                    **_BOOL,
                    "default": True,
                    "description": "True presses and releases; false leaves the button held until a later ui_press.",
                },
            },
            ["id"],
        ),
        "outputSchema": _object(
            {
                "pressed": {
                    **_STR,
                    "description": "Element id whose press this call delivered (or the parked press it released).",
                },
                "held_ms": {
                    **_INT,
                    "description": "The hold this call waited between press and release (0 when it released an earlier hold).",
                },
                "released": _BOOL,
                "source": _source(),
            },
            ["pressed", "held_ms", "released"],
        ),
        "annotations": MUTATING_INPUT,
        "handler": "ui_press",
    },
    {
        "name": "jobs_list",
        "title": "List in-flight long jobs",
        "description": (
            "Read the app's in-flight long passes: the gallery "
            "thumbnail/proxy pool, the per-folder metrics pass, the AI analysis "
            "pass, and running exports. Each row has id, kind, status, progress, "
            "elapsed_s, message. Poll it to watch minute-long work; an empty list "
            "means nothing is running, not an error. Live-only: with no running "
            "app it errors instead of a false empty list. Not for cancelling."
        ),
        "inputSchema": _params(),
        "outputSchema": _object(
            {
                "count": _INT,
                "jobs": _array(
                    _object(
                        {
                            "id": _STR,
                            "kind": {
                                **_STR,
                                "enum": list(JOB_KINDS),
                                "description": "Which pass this job is.",
                            },
                            "status": {
                                **_STR,
                                "enum": list(JOB_STATUSES),
                                "description": "Lifecycle state; only non-idle jobs are listed.",
                            },
                            "progress": {
                                "type": ["object", "null"],
                                "description": "{done, total} when the app reports a total; JSON null when it does not (never an invented percentage).",
                            },
                            "elapsed_s": {
                                "type": ["number", "null"],
                                "description": "Seconds continuously observed running, or null; a lower bound, never a guess.",
                            },
                            "message": _STR,
                        },
                        ["id", "kind", "status", "message"],
                    )
                ),
                "source": _source(),
            },
            ["count", "jobs"],
        ),
        "annotations": READ_ONLY,
        "handler": "jobs_list",
    },
    {
        "name": "jobs_cancel",
        "title": "Cancel an in-flight job",
        "description": (
            "Cancel one running job by its id from jobs_list. Only kind 'export' "
            "has a safe cancel today: it sets the save task's own cancel event, "
            "so the encoder aborts atomically and leaves no partial file behind. "
            "Every other kind answers a named refusal — cancellation is not "
            "invented. An unknown or already-settled id is an error. Not "
            "idempotent: re-sending an id after it settles fails."
        ),
        "inputSchema": _params(
            {
                "id": {
                    **_STR,
                    "description": "Job id from jobs_list (per-run; ids disappear when the job settles).",
                }
            },
            ["id"],
        ),
        "outputSchema": _object(
            {
                "cancelled": {"type": "boolean", "description": "True when the cancel was delivered."},
                "id": _STR,
                "kind": {
                    **_STR,
                    "enum": list(CANCELLABLE_JOB_KINDS),
                    "description": "The kind that was cancelled.",
                },
                "source": _source(),
            },
            ["cancelled", "id", "kind"],
        ),
        "annotations": MUTATING_INPUT,
        "handler": "jobs_cancel",
    },
    {
        "name": "wait_for",
        "title": "Wait for one asynchronous expectation",
        "description": (
            "Block until exactly one expectation holds, then return what was "
            "observed. Selectors: element=<id> (resolves and is visible+enabled), "
            "role+label (an element with that exact role and label exists), or "
            "job_settled=true (no listed job of job_kind remains). A timeout is a "
            "normal result (ok:false, reason timeout) carrying the last observed "
            "row, so do not hand-poll. Read-only, live-only, one selector."
        ),
        "inputSchema": _params(
            {
                "timeout_ms": {
                    **_INT,
                    "minimum": 1,
                    "maximum": 60000,
                    "default": 5000,
                    "description": "Longest wait before answering timeout; hard cap 60000.",
                },
                "poll_ms": {
                    **_INT,
                    "minimum": 25,
                    "default": 100,
                    "description": "Floor between observations; a slow observation adds its own duration.",
                },
                "element": {
                    **_STR,
                    "description": "Element id from ui_elements; waits until it is present, visible, and enabled.",
                },
                "role": {
                    **_STR,
                    "description": "Exact role (ui_elements' role) to pair with label; pass both.",
                },
                "label": {
                    **_STR,
                    "description": "Exact, case-sensitive label to pair with role; pass both.",
                },
                "job_settled": {
                    **_BOOL,
                    "description": "True waits until no running/paused job remains (optionally of job_kind).",
                },
                "job_kind": {
                    **_STR,
                    "enum": list(JOB_KINDS),
                    "description": "Restrict job_settled to one job kind; omit to wait for all rows to clear.",
                },
            }
        ),
        "outputSchema": _object(
            {
                "ok": {
                    "type": "boolean",
                    "description": "True only when the predicate held; a timeout is never ok.",
                },
                "reason": {
                    "type": ["string", "null"],
                    "description": "'timeout' when the predicate never held; null on success.",
                },
                "waited_ms": _INT,
                "predicate": _object(
                    {
                        "selector": {
                            **_STR,
                            "enum": ["element", "role_label", "job_settled"],
                            "description": "Which selector was waited on.",
                        },
                        "element": {"type": ["string", "null"]},
                        "role": {"type": ["string", "null"]},
                        "label": {"type": ["string", "null"]},
                        "job_kind": {"type": ["string", "null"]},
                    },
                    ["selector"],
                ),
                "observed": {
                    "description": (
                        "Last observed state: the element row for element/role+label, "
                        "the job rows for job_settled; null when nothing matched."
                    )
                },
                "hint": {
                    "type": ["string", "null"],
                    "description": "What to read next when the predicate timed out; null on success.",
                },
                "source": {
                    "type": "string",
                    "enum": ["live"],
                    "description": "Always live: an asynchronous expectation has no headless analogue.",
                },
            },
            ["ok", "waited_ms", "predicate", "observed", "source"],
        ),
        "annotations": READ_ONLY,
        "handler": "wait_for",
    },
]

#: Tools whose handler can be answered *early* by the control channel: each one
#: drives the app in a way that can park inside a modal dialog's nested event
#: loop (any action, chord or button press can open one). That nested loop is
#: what lets the channel's ack watchdog fire, so the declared output has to
#: accept the early frame too. A read that merely blocks has no nested loop —
#: its timer cannot run and its reply is written normally.
EARLY_ANSWER_TOOLS = ("run_action", "press_keys", "ui_click", "ui_press")

for _tool in TOOLS:
    if _tool["name"] in EARLY_ANSWER_TOOLS:
        _tool["outputSchema"] = _also_early_answer(_tool["outputSchema"])
del _tool

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

RESOURCES: list[dict] = [
    {
        "uri": "app://actions",
        "name": "Action catalog",
        "description": "Every registered Find Action with id, label, owner tab, and shortcut (JSON).",
        "mimeType": "application/json",
    },
    {
        "uri": "app://state",
        "name": "Store snapshot",
        "description": "Redux Store slices: settings, workspace sessions, active document summary (JSON).",
        "mimeType": "application/json",
    },
    {
        "uri": "app://sessions",
        "name": "Workspace sessions",
        "description": "Workspace sessions with id, type, title, and active flag (JSON).",
        "mimeType": "application/json",
    },
    {
        "uri": "app://log",
        "name": "Log tail",
        "description": "The most recent app log lines (plain text).",
        "mimeType": "text/plain",
    },
    {
        "uri": "app://ui-layout",
        "name": "UI layout dump",
        "description": "The widget tree from the most recent dump_ui_layout call, if any (JSON).",
        "mimeType": "application/json",
    },
    {
        "uri": "app://theme",
        "name": "Theme and language",
        "description": "Active theme, UI language, and scale from the app snapshot (JSON).",
        "mimeType": "application/json",
    },
]

RESOURCE_TEMPLATES: list[dict] = [
    {
        "uriTemplate": "app://action/{id}",
        "name": "One action",
        "description": "A single action catalog row by its exact action id (JSON).",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "app://tab/{name}/layout",
        "name": "Tab layout dump",
        "description": "The most recent widget-tree dump for a tab opened by dump_ui_layout (JSON).",
        "mimeType": "application/json",
    },
]

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PROMPTS: list[dict] = [
    {
        "name": "diagnose_gallery",
        "title": "Diagnose a gallery issue",
        "description": "Workflow for investigating an Image Gallery rendering or behavior problem.",
        "arguments": [
            {
                "name": "symptom",
                "description": "What the user observes, e.g. 'thumbnails stay blank after drop'.",
                "required": False,
            },
        ],
    },
    {
        "name": "capture_and_inspect",
        "title": "Capture and inspect a surface",
        "description": "Workflow for screenshotting a surface and summarizing what changed visually.",
        "arguments": [
            {
                "name": "surface",
                "description": "Surface to capture, from list_surfaces.",
                "required": True,
            },
        ],
    },
]
