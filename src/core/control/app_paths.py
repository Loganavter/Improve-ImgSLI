"""Where the running app keeps its per-user files (and where it used to).

One rule, one spelling: the app-data and cache directory names are
``core.log_names.APP_NAME``, so a rename cannot stop half-way the way the
BlinkTable rename did for the control channel, the artifact cache and the MCP's
own paths. The pre-rename directory name is imported from the same module — the
only legacy spelling in the tree.

The *fallback rule* is the second half: a fresh install uses the current names, an
upgraded install keeps reading the tree it already has, and the legacy tree is
never moved or deleted (:func:`prefer_existing`). ``mcp-server/app/live.py``
carries its own copy of this rule (that package is stdlib-only and must not
import ``core``, which pulls in PySide6) and
``tests/devtools/test_control_discovery.py`` pins both sides to the same answer.

Split out of ``discovery`` (which owns the socket/pointer transport primitives)
when the identity change pushed that module over the 500-line size policy.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.log_names import APP_NAME, LEGACY_LOG_DIR_NAME
from shared.debug_flags import env_value as _env_value

#: App-data directory name of the pre-rename build. The rename moved the log
#: directory and the app-data directory in one step, so both names are the same
#: string and ``core.log_names`` owns it — importing it keeps one spelling.
LEGACY_APP_DATA_DIR_NAME = LEGACY_LOG_DIR_NAME


def data_base() -> Path:
    """Per-OS root that holds the app-data directory.

    Mirrors ``sli_ui_toolkit.core.logging`` / ``mcp-server/app/live.py`` (their
    ``base`` — the one rule the MCP server derives discovery from).
    """
    if sys.platform.startswith("linux"):
        return Path(
            os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        )
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    # pragma: no cover - Windows
    return Path(os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming"))


def app_data_dir() -> Path:
    """Per-OS app data dir (``~/.local/share/BlinkTable`` on Linux)."""
    return data_base() / APP_NAME


def legacy_app_data_dir() -> Path:
    """Per-OS app data dir of the pre-rename build (read, never written).

    The same directory the earlier build published its control channel in, so a
    still-running instance stays discoverable across the rename.
    """
    return data_base() / LEGACY_APP_DATA_DIR_NAME


def prefer_existing(current: Path, legacy: Path) -> Path:
    """*current* when it exists, else *legacy* when it does, else *current*.

    The one fallback rule for on-disk trees: a fresh install uses the current
    name, an upgraded install keeps reading the tree it already has, and the
    legacy path is never moved or deleted.
    """
    if current.exists():
        return current
    if legacy.exists():
        return legacy
    return current


def artifacts_dir() -> Path:
    """Where live artifacts (layout dumps, captures) are written.

    Reuses the MCP convention — ``IMGSLI_MCP_ARTIFACTS`` when set, else
    ``$XDG_CACHE_HOME/<APP_NAME>/mcp`` — so the MCP server can read back the
    paths the control channel returns. Falls back to the pre-rename cache tree
    while only it exists, so an upgrade keeps earlier captures readable.
    """
    override = (_env_value("IMGSLI_MCP_ARTIFACTS", "") or "").strip()
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache"))
    return prefer_existing(
        base / APP_NAME / "mcp", base / LEGACY_APP_DATA_DIR_NAME / "mcp"
    )
