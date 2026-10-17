"""Minimal, spec-conformant MCP JSON-RPC 2.0 loop over stdio.

Why hand-written: the MCP spec revision ``2026-07-28`` is what this server
speaks, but the official Python SDK (``mcp==2.3.0``) is **not installable in
this environment** (system Python is PEP 668 externally-managed and
site-packages is root-owned — see ``README.md`` / ``DONE.md``). The task's
fallback path therefore applies: this module implements the transport and the
methods the server advertises, with no third-party dependency. The optional
SDK is declared in ``mcp-server/requirements.txt`` for a writable-venv install;
the catalog/backend are transport-agnostic and could be registered with the SDK
low-level ``Server`` unchanged.

Implemented surface: ``initialize`` (legacy handshake, for today's clients),
``server/discover`` (modern stateless envelope), ``ping``, ``tools/list`` /
``tools/call``, ``resources/list`` / ``resources/templates/list`` /
``resources/read``, ``prompts/list`` / ``prompts/get``, and the
``notifications/initialized`` / ``notifications/cancelled`` no-ops.

Conventions kept from the spec: newline-delimited JSON on stdin/stdout, logs on
stderr, deterministic list order, ``ttlMs``/``cacheScope`` freshness hints on
cacheable results, ``resultType: "complete"`` on modern-era results, and errors
split correctly — protocol errors (``-32602`` invalid params, ``-32022``
unsupported protocol version) vs tool-execution failures inside the result
(``isError: true`` with an actionable hint).
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, IO

from . import catalog
from .backend import ToolError

JSONRPC_VERSION = "2.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
UNSUPPORTED_PROTOCOL_VERSION = -32022

SERVER_INFO = {"name": catalog.SERVER_NAME, "version": catalog.SERVER_VERSION}

CAPABILITIES = {
    "tools": {"listChanged": False},
    "resources": {"subscribe": False, "listChanged": False},
    "prompts": {"listChanged": False},
}

#: Cap on one inbound request line (bytes). A longer line is refused with a
#: named error — the request-line bound from plan P2 (no silent truncation).
MAX_REQUEST_LINE_BYTES = 1 << 20  # 1 MiB


def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def _result(request_id: Any, result: dict, *, modern: bool) -> dict:
    payload = dict(result)
    if modern:
        payload.setdefault("resultType", "complete")
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": payload}


def _check_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


class MCPProtocol:
    """Dispatches decoded JSON-RPC messages against the catalog + backend."""

    def __init__(self, backend: Any, *, log: Callable[[str], None] | None = None) -> None:
        self.backend = backend
        self._log = log or (lambda message: print(message, file=sys.stderr, flush=True))
        self._protocol_version = catalog.PROTOCOL_VERSION

    # -- catalog views (deterministic order) -------------------------------

    def tools(self) -> list[dict]:
        return [
            {
                "name": tool["name"],
                "title": tool.get("title"),
                "description": tool["description"],
                "inputSchema": tool["inputSchema"],
                "outputSchema": tool.get("outputSchema"),
                "annotations": tool["annotations"],
            }
            for tool in catalog.TOOLS
        ]

    def resources(self) -> list[dict]:
        return sorted(
            (
                {
                    "uri": item["uri"],
                    "name": item["name"],
                    "title": item.get("title", item["name"]),
                    "description": item.get("description"),
                    "mimeType": item.get("mimeType"),
                }
                for item in catalog.RESOURCES
            ),
            key=lambda item: item["uri"],
        )

    def resource_templates(self) -> list[dict]:
        return sorted(
            (
                {
                    "uriTemplate": item["uriTemplate"],
                    "name": item["name"],
                    "title": item.get("title", item["name"]),
                    "description": item.get("description"),
                    "mimeType": item.get("mimeType"),
                }
                for item in catalog.RESOURCE_TEMPLATES
            ),
            key=lambda item: item["uriTemplate"],
        )

    def prompts(self) -> list[dict]:
        return [
            {
                "name": prompt["name"],
                "title": prompt.get("title", prompt["name"]),
                "description": prompt.get("description"),
                "arguments": prompt.get("arguments") or [],
            }
            for prompt in catalog.PROMPTS
        ]

    # -- entry point -------------------------------------------------------

    def handle(self, message: Any) -> dict | None:
        """Decode one JSON-RPC message → response dict, or ``None`` for a notification."""
        if not isinstance(message, dict):
            return _error(None, INVALID_REQUEST, "each message must be a JSON object")
        request_id = message.get("id")
        method = message.get("method")
        if message.get("jsonrpc") != JSONRPC_VERSION or not isinstance(method, str):
            return _error(request_id, INVALID_REQUEST, "malformed JSON-RPC request")
        params = message.get("params")
        params = params if isinstance(params, dict) else {}

        # Notifications carry no id and expect no response.
        if request_id is None and method.startswith("notifications/"):
            return None

        modern = "_meta" in params
        meta, meta_error = self._validate_envelope(params, modern)
        if meta_error is not None:
            return _error(request_id, meta_error[0], meta_error[1], meta_error[2])

        try:
            handler = getattr(self, "_handle_" + method.replace("/", "_").replace("-", "_"), None)
            if handler is None:
                return _error(request_id, METHOD_NOT_FOUND, f"unknown method {method!r}")
            result = handler(params, modern=modern)
        except _InvalidParams as exc:
            return _error(
                request_id,
                INVALID_PARAMS,
                exc.message,
                {"hint": exc.hint} if exc.hint else None,
            )
        except ToolError as exc:  # tool-author signalling, not a protocol fault
            return _error(request_id, INTERNAL_ERROR, f"{exc.message} — {exc.hint or 'no hint'}")
        except Exception as exc:  # pragma: no cover - defensive
            self._log(f"[mcp] handler {method} crashed: {exc!r}")
            return _error(request_id, INTERNAL_ERROR, f"internal error in {method}")
        if result is None:
            return None
        return _result(request_id, result, modern=modern)

    # -- envelope validation (modern stateless era) -------------------------

    def _validate_envelope(
        self, params: dict, modern: bool
    ) -> tuple[dict, tuple[int, str, Any] | None]:
        if not modern:
            return {}, None
        meta = params["_meta"]
        if not isinstance(meta, dict):
            return {}, (
                INVALID_PARAMS,
                "params._meta must be an object carrying the required "
                "'protocolVersion' and 'clientCapabilities' envelope keys",
                None,
            )
        missing = [key for key in ("protocolVersion", "clientCapabilities") if key not in meta]
        if missing:
            return {}, (
                INVALID_PARAMS,
                "params._meta is missing the required envelope key(s): " + ", ".join(missing),
                None,
            )
        version = meta["protocolVersion"]
        if not isinstance(version, str):
            return {}, (INVALID_PARAMS, "the protocol-version envelope value must be a string", None)
        if version not in catalog.MODERN_PROTOCOL_VERSIONS:
            return {}, (
                UNSUPPORTED_PROTOCOL_VERSION,
                f"unsupported protocol version {version!r}",
                {"supported": list(catalog.MODERN_PROTOCOL_VERSIONS), "requested": version},
            )
        return meta, None

    # -- method handlers ---------------------------------------------------

    def _handle_ping(self, params: dict, *, modern: bool) -> dict:
        return {}

    def _handle_initialize(self, params: dict, *, modern: bool) -> dict:
        offered = params.get("protocolVersion")
        if isinstance(offered, str) and offered in catalog.SUPPORTED_PROTOCOL_VERSIONS:
            negotiated = offered
        else:
            negotiated = catalog.HANDSHAKE_PROTOCOL_VERSIONS[-1]
        self._protocol_version = negotiated
        return {
            "protocolVersion": negotiated,
            "capabilities": CAPABILITIES,
            "serverInfo": dict(SERVER_INFO),
            "instructions": catalog.INSTRUCTIONS,
        }

    def _handle_server_discover(self, params: dict, *, modern: bool) -> dict:
        return {
            "supportedVersions": list(catalog.MODERN_PROTOCOL_VERSIONS),
            "capabilities": CAPABILITIES,
            "serverInfo": dict(SERVER_INFO),
            "instructions": catalog.INSTRUCTIONS,
            "ttlMs": catalog.STATIC_TTL_MS,
            "cacheScope": "private",
        }

    def _handle_tools_list(self, params: dict, *, modern: bool) -> dict:
        return {"tools": self.tools(), "ttlMs": catalog.STATIC_TTL_MS, "cacheScope": "private"}

    def _handle_resources_list(self, params: dict, *, modern: bool) -> dict:
        return {"resources": self.resources(), "ttlMs": catalog.DYNAMIC_TTL_MS, "cacheScope": "private"}

    def _handle_resources_templates_list(self, params: dict, *, modern: bool) -> dict:
        return {
            "resourceTemplates": self.resource_templates(),
            "ttlMs": catalog.STATIC_TTL_MS,
            "cacheScope": "private",
        }

    def _handle_prompts_list(self, params: dict, *, modern: bool) -> dict:
        return {"prompts": self.prompts(), "ttlMs": catalog.STATIC_TTL_MS, "cacheScope": "private"}

    def _handle_prompts_get(self, params: dict, *, modern: bool) -> dict:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise _InvalidParams("prompts/get requires a 'name'", "call prompts/list first")
        known = {prompt["name"] for prompt in catalog.PROMPTS}
        if name not in known:
            raise _InvalidParams(f"unknown prompt {name!r}", "call prompts/list for valid names")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        rendered = self.backend.get_prompt(name, arguments)
        return {
            "description": rendered.get("description"),
            "messages": [
                {"role": "user", "content": {"type": "text", "text": rendered["text"]}}
            ],
        }

    def _handle_resources_read(self, params: dict, *, modern: bool) -> dict:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise _InvalidParams("resources/read requires a 'uri'", "call resources/list first")
        contents = self.backend.read_resource(uri)
        return {"contents": [contents], "ttlMs": catalog.DYNAMIC_TTL_MS, "cacheScope": "private"}

    def _handle_tools_call(self, params: dict, *, modern: bool) -> dict:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise _InvalidParams("tools/call requires a 'name'", "call tools/list first")
        spec = next((tool for tool in catalog.TOOLS if tool["name"] == name), None)
        if spec is None:
            # Spec: an unknown tool name is -32602 (invalid params), not a result.
            raise _InvalidParams(f"unknown tool {name!r}", "call tools/list for the catalog")
        raw_args = params.get("arguments")
        raw_args = raw_args if isinstance(raw_args, dict) else {}
        arguments, issues = self._validate_arguments(spec, raw_args)
        if issues:
            # Invalid arguments are a *protocol* error, not a tool result.
            raise _InvalidParams("; ".join(issues), "see the tool's inputSchema")
        handler = getattr(self.backend, spec["handler"], None)
        if handler is None:  # pragma: no cover - catalog/backend mismatch is a bug
            raise ToolError(f"tool {name!r} has no handler", "report a server bug")
        try:
            structured = handler(**arguments)
        except ToolError as exc:
            return self._tool_error(exc.message, exc.hint)
        except Exception as exc:  # pragma: no cover - defensive
            self._log(f"[mcp] tool {name} crashed: {exc!r}")
            return self._tool_error(f"tool {name} failed: {exc}", "check read_log for details")
        return self._tool_ok(structured)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _tool_ok(structured: Any) -> dict:
        return {
            "content": [
                {"type": "text", "text": json.dumps(structured, ensure_ascii=False, indent=2)}
            ],
            "structuredContent": structured,
            "isError": False,
        }

    @staticmethod
    def _tool_error(message: str, hint: str | None) -> dict:
        text = message if not hint else f"{message}\nHint: {hint}"
        return {"content": [{"type": "text", "text": text}], "isError": True}

    @staticmethod
    def _validate_arguments(spec: dict, raw: dict) -> tuple[dict, list[str]]:
        schema = spec.get("inputSchema") or {}
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        issues: list[str] = []
        arguments: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in properties:
                issues.append(f"unexpected parameter {key!r}")
                continue
            expected = properties[key].get("type")
            if isinstance(expected, str) and not _check_type(value, expected):
                issues.append(f"parameter {key!r} must be a {expected}")
                continue
            if "enum" in properties[key] and value not in properties[key]["enum"]:
                issues.append(
                    f"parameter {key!r} must be one of: "
                    + ", ".join(map(str, properties[key]["enum"]))
                )
                continue
            if expected == "integer":
                if "minimum" in properties[key] and value < properties[key]["minimum"]:
                    issues.append(f"parameter {key!r} must be >= {properties[key]['minimum']}")
                    continue
                if "maximum" in properties[key] and value > properties[key]["maximum"]:
                    issues.append(f"parameter {key!r} must be <= {properties[key]['maximum']}")
                    continue
            arguments[key] = value
        for key in required:
            if key not in arguments:
                issues.append(f"missing required parameter {key!r}")
        for key, prop in properties.items():
            if key not in arguments and "default" in prop:
                arguments[key] = prop["default"]
        return arguments, issues


class _InvalidParams(ToolError):
    """Raised for invalid tool arguments — mapped to a JSON-RPC -32602 error."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message, hint)
        self.code = INVALID_PARAMS


def serve_stdio(protocol: MCPProtocol, stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> int:
    """Newline-delimited JSON-RPC loop; returns a process exit code."""
    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stdout
    for line in in_stream:
        line = line.strip()
        if not line:
            continue
        if len(line) > MAX_REQUEST_LINE_BYTES:
            # Refuse rather than decode an over-cap line (plan P2 bound).
            response = _error(
                None,
                INVALID_REQUEST,
                f"request line exceeds the {MAX_REQUEST_LINE_BYTES} byte cap",
            )
        else:
            try:
                message = json.loads(line)
            except ValueError as exc:
                response = _error(None, PARSE_ERROR, f"invalid JSON: {exc}")
            else:
                response = protocol.handle(message)
        if response is None:
            continue
        out_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
        out_stream.flush()
    return 0
