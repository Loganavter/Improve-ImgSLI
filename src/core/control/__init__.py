"""In-app control channel (Phase 2, ``IMGSLI_CONTROL=1``).

The running app's end of the MCP live channel: a private unix socket plus a
discovery pointer (``discovery``), a ``QLocalServer`` that dispatches
newline-delimited JSON requests (``server``), and one handler per MCP tool
(``handlers``). The host MCP server attaches to this socket — see
``docs/dev/MCP.md`` — and can then read live state, run real actions, and grab
the live window without spawning throwaway processes.

Nothing here imports the MCP server package; the contract is the JSON wire
protocol and the shared discovery artifacts.
"""

from __future__ import annotations

from .discovery import pointer_path, read_pointer, runtime_dir, socket_path
from .server import ControlServer

__all__ = [
    "ControlServer",
    "pointer_path",
    "read_pointer",
    "runtime_dir",
    "socket_path",
]
