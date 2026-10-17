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
- the catalog stays small (≤ ~24 tools — a review prompt, not a magic number:
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


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

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
                    _object({"name": _STR, "description": _STR, "isolated": _BOOL}, ["name", "description"]),
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
        "title": "Run a Find Action",
        "description": (
            "Run one registered Find Action by id. With a live instance "
            "attached it runs in the running window ('ran': true, result key "
            "'live': true); without one it validates against the headless "
            "ActionRegistry and launches a fresh process. Use it to open "
            "dialogs (platform.settings) or trigger commands. Some actions are "
            "destructive (save, quit, export) — confirm intent first."
        ),
        "inputSchema": _params(
            {
                "action_id": {
                    **_STR,
                    "description": "Exact ActionRegistry id, e.g. platform.settings (see list_actions).",
                },
                "tab": {
                    **_STR,
                    "enum": list(TAB_KINDS),
                    "description": "Optionally target this tab first, so tab-scoped actions register before the action runs.",
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
                "ran": {"type": "boolean", "description": "True when the live instance ran the action."},
                "live": _live_flag(),
                "source": _source(),
            },
            ["action_id"],
        ),
        "annotations": MUTATING_RISKY,
        "handler": "run_action",
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
        "name": "capture_surface",
        "title": "Capture a surface PNG",
        "description": (
            "Screenshot one named app surface to a PNG and return its path. With a live "
            "instance attached the running window is captured ('live': true) and each visible "
            "canvas frame is composited in, so the QRhi/GL canvas shows its content; otherwise "
            "the devtool boots the app on a private Xvfb. Use it for visual checks and Help figures."
        ),
        "inputSchema": _params(
            {
                "surface": {
                    **_STR,
                    "description": "Surface name from list_surfaces, e.g. settings or gallery-populated.",
                },
                "theme": {
                    **_STR,
                    "enum": list(THEMES),
                    "description": "Theme for the capture; defaults to the devtool's dark.",
                },
                "out": {
                    **_STR,
                    "description": "Output directory for the PNG; defaults to the server's artifacts directory.",
                },
            },
            ["surface"],
        ),
        "outputSchema": _object(
            {
                "surface": _STR,
                "path": _STR,
                "theme": _STR,
                "live": _live_flag(),
                "source": _source(),
            },
            ["surface", "path"],
        ),
        "annotations": MUTATING,
        "handler": "capture_surface",
    },
    {
        "name": "press_keys",
        "title": "Press keys in the running app",
        "description": (
            "Inject keyboard input into a running instance: one combo such as "
            "ctrl+shift+p, or comma-separated combos applied in order such as "
            "Down,Down,Enter. Pass target=<element id from ui_elements> to aim "
            "them at a widget the window focus never reaches (e.g. a canvas). "
            "Live-only; key names are allowlisted (letters, digits, punctuation, "
            "named keys); modifiers are ctrl/shift/alt/meta."
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
                    "description": "Element id from ui_elements to type into (e.g. a canvas). Default: the focused widget.",
                },
            },
            ["keys"],
        ),
        "outputSchema": _object(
            {
                "pressed": _array(_STR),
                "count": _INT,
                "target": _STR,
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
                    "description": "Element id from ui_elements to focus first (with the app's own focus reason); omit to use whatever holds focus now.",
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
            "Flattened inventory of the live window's interactive elements: "
            "stable id, role, label, rect, screen_rect, enabled, visible, and "
            "bound Find Action id. Call it FIRST to get an id for ui_click / "
            "ui_hover / ui_focus; ids are session-scoped, so re-read instead of "
            "caching across starts. Live-only. rect is widget-local, "
            "screen_rect is screen-space (best-effort on Wayland). Do NOT use it "
            "to run anything."
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
            }
        ),
        "outputSchema": _object(
            {
                "count": _INT,
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
                        },
                        ["id"],
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
                    "description": "Element id from ui_elements (session-scoped).",
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
            {"id": {**_STR, "description": "Element id from ui_elements (session-scoped)."}},
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
            {"id": {**_STR, "description": "Element id from ui_elements (session-scoped)."}},
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
]

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
