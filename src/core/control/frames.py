"""Wire framing for the app-side control channel.

A reply becomes ONE newline-terminated JSON frame, or explicitly ``None`` when
it cannot be framed (not serialisable, or above ``MAX_REPLY_BYTES``): the caller
sends a named error frame instead of a broken/truncated frame that would desync
the client's line reader. The request-line cap lives beside it — it is the same
wire-boundary refusal contract on the other direction of the wire.

Split out of ``core/control/server.py`` (docs/dev/FILE_SIZE_POLICY.md): pure
framing helpers with no transport, no Qt, no state.
"""

from __future__ import annotations

import json
from typing import Any

#: Hard cap on one request line (1 MiB). A larger line is refused by name
#: (``"request line too large"``) instead of being buffered/truncated silently.
MAX_REQUEST_LINE_BYTES = 1024 * 1024

#: Sanity cap on one serialized reply (8 MiB). A bigger (or unserialisable)
#: result is reported as an error frame, never emitted as a broken frame.
MAX_REPLY_BYTES = 8 * 1024 * 1024



def encode_reply(payload: dict[str, Any]) -> bytes | None:
    """Serialize one reply into a newline-terminated frame, or ``None``.

    ``None`` means the payload cannot be framed — either it is not
    JSON-serialisable (e.g. a circular structure, which ``json.dumps`` raises
    on) or it exceeds ``MAX_REPLY_BYTES``. The caller then sends a named error
    frame instead of writing a broken/truncated frame that would desync the
    client's line reader.
    """
    try:
        blob = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    except Exception:
        return None
    if len(blob) > MAX_REPLY_BYTES:
        return None
    return blob + b"\n"



def _reply_error_frame(request_id: Any) -> bytes:
    """The fallback frame written when ``encode_reply`` refuses a payload."""
    payload = {
        "id": request_id,
        "ok": False,
        "error": "reply could not be framed",
        "hint": (
            f"the result was not JSON-serialisable or exceeded {MAX_REPLY_BYTES} "
            "bytes; check the app log via read_log"
        ),
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"


def send_frame(owner: Any, socket: Any, payload: Any) -> None:
    """Write one reply frame; a payload that cannot be framed gets the named error.

    ``owner`` supplies ``_drop_client``: a write failure means the peer is gone.
    This is the ONE write path, so a broken or truncated frame is never emitted
    (the client's line reader would desync on one).
    """
    request_id = payload.get("id") if isinstance(payload, dict) else None
    frame = encode_reply(payload) if isinstance(payload, dict) else None
    if frame is None:
        frame = _reply_error_frame(request_id)
    try:
        socket.write(frame)
        socket.flush()
    except Exception:
        owner._drop_client(socket)
