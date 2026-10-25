"""The in-flight request note for the app-side control channel.

A note is written next to the discovery pointer *before* a handler runs and
removed once the reply is sent, so a note that outlives the process is where the
app died — the only trace a sibling process can read after a segfault (no
teardown, no reply). The MCP client mirrors the name and the digest rule
(``mcp-server/app/live.py``, stdlib-only, so it cannot import this module).

The note is ONE slot and a handler parked in a modal loop still re-enters the
server (the nested loop serves a new connection's first line), so a request's
write is owned by a caller-side token: a late finisher must not erase a newer
request's record — that record may be all that explains a death.

Split out of ``core/control/server.py`` (docs/dev/FILE_SIZE_POLICY.md): pure
filesystem and string helpers with one caller — no transport, no Qt, no thread.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Owner-only mode for the note (the same mode the socket and the pointer use).
_NOTE_MODE = 0o600

#: Name of the in-flight request note, written next to the pointer. It is
#: written *before* a handler runs and removed once the reply is sent (for a
#: request the ack watchdog answered early: once its handler returns), so a note
#: that outlives the process is where the app died — the only trace a sibling
#: process can read after a segfault (no teardown, no reply). The MCP client
#: mirrors this name (`mcp-server/app/live.py`, stdlib-only, cannot import here).
INFLIGHT_NOTE_NAME = "inflight.json"

#: Cap on the redacted params digest kept in the note.
_PARAM_SUMMARY_LIMIT = 400
#: Per-value cap inside the digest.
_PARAM_VALUE_LIMIT = 48

#: Parameter NAMES whose value is never written down. ``run_action`` forwards
#: free-form params, so a token can sit in the request that kills the app.
_SECRET_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|passw|credential|authori[sz]|cookie|bearer|private[_-]?key)"
)

#: Values that *look* like a credential, whatever their parameter is called.
_SECRET_VALUE_RE = re.compile(
    r"(?i)^(sk-|pk-|ghp_|gho_|ghs_|github_pat_|xox[abp]-|bearer[ =:]|ey[A-Za-z0-9_-]{8,}\.)"
)



def _param_value(value: Any) -> str:
    """One digest fragment: short scalars verbatim, secrets and shapes masked."""
    if isinstance(value, str):
        if _SECRET_VALUE_RE.match(value.strip()):
            return "<redacted>"
        shown = (
            value
            if len(value) <= _PARAM_VALUE_LIMIT
            else value[:_PARAM_VALUE_LIMIT] + "…"
        )
        return repr(shown)
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    if isinstance(value, (list, tuple, set)):
        return f"[{len(value)} items]"
    if isinstance(value, (bool, int, float)) or value is None:
        return repr(value)
    return f"<{type(value).__name__}>"



def summarize_request_params(params: Any) -> str:
    r"""A bounded, secret-free digest of one request's params (``k=v, ...``).

    Identifies the request after the fact without echoing what it carried:
    secret-named parameters become ``<redacted>``, credential-shaped values are
    masked wherever they appear, strings are truncated, and containers are
    reduced to their shape. ``mcp-server/app/live.py`` carries the same rule for
    the request *it* sent (it cannot import this module — stdlib only).
    """
    if not isinstance(params, dict) or not params:
        return ""
    parts: list[str] = []
    for key, value in params.items():
        name = str(key)
        if _SECRET_KEY_RE.search(name):
            parts.append(f"{name}=<redacted>")
        else:
            parts.append(f"{name}={_param_value(value)}")
    summary = ", ".join(parts)
    if len(summary) > _PARAM_SUMMARY_LIMIT:
        summary = summary[:_PARAM_SUMMARY_LIMIT] + "…"
    return summary


def note_inflight(
    path: Path | None, *, method: str, request_id: Any, params: dict[str, Any]
) -> None:
    """Record the request about to run, atomically, at *path*.

    Written to a sibling temp file then ``os.replace``-d so a reader never sees a
    half-written note. Best-effort: a read-only runtime dir must not stop the
    request from running. The *ownership token* stays with the caller: this
    module only writes the slot (see the module docstring).
    """
    if path is None:
        return
    payload = {
        "method": method,
        "summary": summarize_request_params(params),
        "request_id": request_id if isinstance(request_id, (int, float, str)) else None,
        "pid": os.getpid(),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(tmp, _NOTE_MODE)
        os.replace(tmp, path)
    except OSError:
        logger.debug("control channel: could not record the in-flight request")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def clear_inflight(
    path: Path | None, *, token: int | None = None, current_token: int = 0
) -> None:
    """Drop the in-flight record: the app answered, or is shutting down.

    ``token`` (the writer's ownership stamp) makes the clear conditional: a
    request that finishes after a nested one took the note over must leave that
    newer record alone — it may be all that explains a death.
    """
    if path is None:
        return
    if token is not None and token != current_token:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
