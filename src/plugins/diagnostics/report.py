"""Diagnostics report assembly (text + structured payload).

The report is a **fixed schema**: there is deliberately no image / pixmap /
screenshot field, and the builder never reads file contents — it only
transforms the plain data it is handed. All string leaves pass through
:mod:`plugins.diagnostics.redact` (fail-closed: a value that cannot be
redacted is dropped, never emitted raw).
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from . import redact

SCHEMA_VERSION = 1

#: The prefilled GitHub issue target (same project as the app).
ISSUE_URL_BASE = "https://github.com/Loganavter/BlinkTable/issues/new"

#: Any payload key with one of these names is dropped defensively. The schema
#: itself has no such field (asserted by tests) — this is defence in depth.
FORBIDDEN_FIELDS = redact.FORBIDDEN_FIELD_NAMES

_DROP = object()

NOTES = (
    "This report is generated locally.",
    "Nothing is uploaded automatically - you choose Copy / Save / Open issue.",
    "No screenshots, images, or file contents are included.",
)


@dataclass(frozen=True)
class DiagnosticsReport:
    payload: dict[str, Any]
    text: str

    def summary(self) -> str:
        failure = self.payload.get("failure") or {}
        if failure:
            return f"{failure.get('type', 'Error')}: {failure.get('message', '')}".strip()
        return "Diagnostics report"

    def issue_url(self, *, max_body: int = 6000) -> str:
        return build_issue_url(self.text, title=self._issue_title(), max_body=max_body)

    def _issue_title(self) -> str:
        version = (self.payload.get("app") or {}).get("version") or "?"
        failure = self.payload.get("failure") or {}
        kind = failure.get("type", "Problem")
        return f"[diagnostics] {kind} - BlinkTable {version}"


# --------------------------------------------------------------------------
# Failure capture (pure)
# --------------------------------------------------------------------------

def format_failure(
    exc_type: Any,
    exc_value: Any,
    exc_traceback: Any,
    *,
    source: str = "main",
    thread_name: str | None = None,
) -> dict[str, Any]:
    """Structure an exception without redaction (redaction happens later)."""
    type_name = getattr(exc_type, "__name__", None) or str(exc_type)
    message = ""
    try:
        message = str(exc_value)
    except Exception:
        message = "<unprintable>"
    try:
        tb_text = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
    except Exception:
        tb_text = "<traceback unavailable>"
    return {
        "type": type_name,
        "message": message,
        "traceback": tb_text,
        "source": source,
        "thread": thread_name,
    }


# --------------------------------------------------------------------------
# Redaction tree (fail-closed)
# --------------------------------------------------------------------------

def _stringify(value: Any) -> str | None:
    try:
        return str(value)
    except Exception:
        return None


def _clean(node: Any) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            name = _stringify(key)
            if name is None or name.lower() in FORBIDDEN_FIELDS:
                continue
            cleaned = _clean(value)
            if cleaned is _DROP:
                continue
            out[name] = cleaned
        return out
    if isinstance(node, (list, tuple, set, frozenset)):
        out_list: list[Any] = []
        for item in node:
            cleaned = _clean(item)
            if cleaned is not _DROP:
                out_list.append(cleaned)
        return out_list
    if node is None or isinstance(node, bool):
        return node
    if isinstance(node, (int, float)):
        return node
    if isinstance(node, str):
        text = node
    else:
        text = _stringify(node)
        if text is None:
            return _DROP
    try:
        redacted = redact.redact_text(text)
    except Exception:
        return _DROP
    if redacted == redact.REDACTION_FAILED:
        return _DROP
    return redacted


# --------------------------------------------------------------------------
# Payload / text
# --------------------------------------------------------------------------

def build_payload(
    *,
    failure: dict[str, Any] | None = None,
    app: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    breadcrumbs: Iterable[dict[str, Any]] = (),
    logs: Iterable[str] = (),
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble + redact the structured payload.

    Contains no file I/O whatsoever — the caller supplies every field.
    """
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or _now_iso(),
        "failure": failure or {},
        "app": app or {},
        "environment": environment or {},
        "runtime": runtime or {},
        "breadcrumbs": list(breadcrumbs),
        "logs": list(logs),
        "notes": list(NOTES),
    }
    cleaned = _clean(payload)
    # ``_clean`` always returns a dict for a dict root.
    return cleaned if isinstance(cleaned, dict) else {}


def _now_iso() -> str:
    try:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return "unknown"


def _fmt_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return ", ".join(_fmt_scalar(v) for v in value) if isinstance(value, list) else "…"
    return str(value)


def render_text(payload: dict[str, Any]) -> str:
    """Render the payload as a readable plain-text report."""
    lines: list[str] = []
    app = payload.get("app") or {}
    environment = payload.get("environment") or {}
    machine = environment  # environment already merged with machine by caller
    failure = payload.get("failure") or {}
    runtime = payload.get("runtime") or {}

    lines.append("BlinkTable - diagnostics report")
    lines.append("=" * 40)
    lines.append(f"Generated: {payload.get('generated_at', 'unknown')}")
    lines.append(f"Schema:    v{payload.get('schema_version', SCHEMA_VERSION)}")
    lines.append("")

    lines.append("## Failure")
    if failure:
        lines.append(f"Source:    {failure.get('source', 'unknown')}")
        lines.append(f"Thread:    {failure.get('thread') or '-'}")
        lines.append(f"Type:      {failure.get('type', 'unknown')}")
        lines.append(f"Message:   {failure.get('message', '')}")
        lines.append("")
        lines.append("Traceback:")
        lines.append(str(failure.get("traceback", "")).rstrip())
    else:
        lines.append("(no exception captured; manual report)")
    lines.append("")

    lines.append("## Build")
    for key in ("name", "version", "commit", "channel", "install_source", "frozen"):
        lines.append(f"{key:>14}: {_fmt_scalar(app.get(key))}")
    lines.append("")

    lines.append("## Environment")
    for key in ("os", "os_version", "kernel", "arch", "cpu", "cpu_count", "ram"):
        lines.append(f"{key:>14}: {_fmt_scalar(machine.get(key))}")
    gpus = machine.get("gpu") or []
    if gpus:
        for index, gpu in enumerate(gpus):
            label = "gpu" if index == 0 else ""
            name = gpu.get("name") if isinstance(gpu, dict) else gpu
            driver = gpu.get("driver") if isinstance(gpu, dict) else None
            lines.append(f"{label:>14}: {_fmt_scalar(name)}" + (f" (driver {driver})" if driver else ""))
    else:
        lines.append(f"{'gpu':>14}: -")
    lines.append(f"{'rhi_backend':>14}: {_fmt_scalar(machine.get('rhi_backend'))}")
    lines.append(f"{'session_type':>14}: {_fmt_scalar(machine.get('session_type'))}")
    lines.append(f"{'display_server':>14}: {_fmt_scalar(machine.get('display_server'))}")
    lines.append(f"{'compositor':>14}: {_fmt_scalar(machine.get('compositor'))}")
    lines.append(f"{'compositor_ver':>14}: {_fmt_scalar(machine.get('compositor_version'))}")
    screens = machine.get("screens") or []
    if screens:
        for index, screen in enumerate(screens):
            size = screen.get("size") if isinstance(screen, dict) else None
            scale = screen.get("dpi_scale") if isinstance(screen, dict) else None
            label = "screen" if index == 0 else ""
            lines.append(f"{label:>14}: {size} @ {scale}x")
    else:
        lines.append(f"{'screen':>14}: -")
    lines.append(f"{'theme':>14}: {_fmt_scalar(machine.get('theme'))}")
    lines.append(f"{'locale':>14}: {_fmt_scalar((machine.get('locale') or {}).get('lang'))}")
    lines.append("")

    lines.append("## Runtime")
    lines.append(f"{'python':>14}: {_fmt_scalar((runtime.get('python') or {}).get('python_version'))}")
    lines.append(f"{'qt':>14}: {_fmt_scalar((runtime.get('python') or {}).get('qt'))}")
    lines.append(f"{'active_tab':>14}: {_fmt_scalar(runtime.get('active_tab'))}")
    lines.append(f"{'uptime_s':>14}: {_fmt_scalar(runtime.get('uptime_seconds'))}")
    settings = runtime.get("settings") or {}
    if settings:
        lines.append("")
        lines.append("Settings (sanitized):")
        for key in sorted(settings):
            lines.append(f"  {key} = {_fmt_scalar(settings[key])}")
    plugins = runtime.get("plugins") or []
    if plugins:
        lines.append("")
        lines.append("Plugins:")
        for plugin in plugins:
            if isinstance(plugin, dict):
                lines.append(
                    f"  {plugin.get('name')} v{plugin.get('version')} ({plugin.get('tier')})"
                )
    stacks = runtime.get("thread_stacks")
    if stacks:
        lines.append("")
        lines.append("Thread stacks:")
        lines.append(str(stacks))
    qt_messages = runtime.get("qt_messages") or []
    if qt_messages:
        lines.append("")
        lines.append(f"Qt messages (last {len(qt_messages)}):")
        for message in qt_messages:
            lines.append(f"  {message}")
    lines.append("")

    breadcrumbs = payload.get("breadcrumbs") or []
    lines.append(f"## Recent actions (last {len(breadcrumbs)})")
    for crumb in breadcrumbs:
        if isinstance(crumb, dict):
            lines.append(
                f"  {_fmt_scalar(crumb.get('timestamp'))}  {crumb.get('kind')}  {crumb.get('label')}"
            )
    lines.append("")

    logs = payload.get("logs") or []
    lines.append(f"## Log tail (last {len(logs)})")
    lines.extend(str(line) for line in logs)
    lines.append("")
    lines.append("## Notes")
    for note in payload.get("notes") or []:
        lines.append(f"- {note}")
    return "\n".join(lines)


def assemble(
    *,
    failure: dict[str, Any] | None = None,
    app: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
    machine: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    breadcrumbs: Iterable[dict[str, Any]] = (),
    logs: Iterable[str] = (),
    generated_at: str | None = None,
) -> DiagnosticsReport:
    """Build a :class:`DiagnosticsReport` from ready-made fields."""
    merged_env = dict(environment or {})
    if machine:
        merged_env.update(machine)
    payload = build_payload(
        failure=failure,
        app=app,
        environment=merged_env,
        runtime=runtime,
        breadcrumbs=breadcrumbs,
        logs=logs,
        generated_at=generated_at,
    )
    return DiagnosticsReport(payload=payload, text=render_text(payload))


def build_issue_url(text: str, *, title: str, max_body: int = 6000) -> str:
    """Build a prefilled GitHub "new issue" URL (length-capped)."""
    from urllib.parse import quote

    body = text
    if len(body) > max_body:
        body = body[:max_body] + "\n\n…(truncated; use Copy for the full report)"
    query = f"title={quote(title, safe='')}&body={quote(body, safe='')}"
    return f"{ISSUE_URL_BASE}?{query}"
