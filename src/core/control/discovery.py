r"""Local primitives + discovery artifacts for the in-app control channel.

A running app publishes where to reach it, and the host MCP server finds it
without any registry service: a unix socket (``control.sock``) plus a small
JSON pointer (``instance.json``) in a **private** runtime directory. The
channel is local-only — no TCP, no network code anywhere in ``core.control``.

Security is discovery-level and best-effort:
* the runtime directory is created/enforced ``0o700``,
* the socket and pointer are chmodded ``0o600``,
* every inbound connection's peer uid (``SO_PEERCRED``) must equal
  ``os.getuid()`` — a foreign uid is refused before a byte is read.

The pointer carries the owning pid so a *stale* pointer (crashed app) can be
detected and cleaned by the next starter (:func:`stale_pointer_alive`), and
``read_pointer``/``clear_pointer`` are what the MCP server side polls.

Directory precedence: ``IMGSLI_CONTROL_DIR`` (tests / explicit override) →
``$XDG_RUNTIME_DIR`` when it exists, is writable, and is private → the app data
dir's ``run/`` subdirectory (``~/.local/share/ImproveImgSLI/run``).

The MCP server re-derives the same dir with its own copy of the rule
(``mcp-server/app/live.py`` — its ``_is_private_dir`` and its control_dirs
list; that package is stdlib-only and cannot import this one, which pulls in
PySide6).
Two copies of one rule drifted once already (a ``0755`` runtime dir was refused
here but accepted there, so the client silently fell back to headless):
``tests/devtools/test_control_discovery.py`` pins both sides to the same answer
over an env matrix. Change one, change the other.

This module also owns the small host-side primitives the transport and the
handlers share, so neither has to import the other: the request error type
(``MethodError``), the ``press_keys`` allowlist + parser, the artifacts-dir
convention, the live surface listing, and the live window grab.

The ``press_keys`` grammar is unchanged — ``+`` joins a combo, ``,`` separates
combos — but both are real app keys (``Ctrl+,``, ``+``), so they are nameable
as ``comma`` / ``plus`` or escaped as ``\,`` / ``\+``.
"""

from __future__ import annotations

import json
import os
import re
import socket
import stat
import string
import struct
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt

from .surfaces import (  # noqa: F401 — re-exported for handlers/tests
    devtool_surfaces,
    live_surfaces,
)

#: Socket filename inside the runtime directory.
SOCKET_NAME = "control.sock"

#: Pointer filename inside the runtime directory.
POINTER_NAME = "instance.json"

#: Private mode we enforce on our runtime directory.
_DIR_MODE = 0o700

#: Owner-only mode for the socket and the pointer.
_FILE_MODE = 0o600


def app_data_dir() -> Path:
    """Per-OS app data dir (``~/.local/share/ImproveImgSLI`` on Linux).

    Mirrors ``sli_ui_toolkit.core.logging`` / ``mcp-server/app/live.py``
    (``app_data_dir`` — the one copy the MCP server derives discovery from).
    """
    if sys.platform.startswith("linux"):
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:  # pragma: no cover - Windows
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "ImproveImgSLI"


def artifacts_dir() -> Path:
    """Where live artifacts (layout dumps, captures) are written.

    Reuses the MCP convention — ``IMGSLI_MCP_ARTIFACTS`` when set, else
    ``$XDG_CACHE_HOME/ImproveImgSLI/mcp`` — so the MCP server can read back the
    paths this channel returns.
    """
    override = os.environ.get("IMGSLI_MCP_ARTIFACTS", "").strip()
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "ImproveImgSLI" / "mcp"


def _is_private_dir(path: Path) -> bool:
    """True iff *path* is a directory we own with no group/other access."""
    try:
        info = path.stat()
    except OSError:
        return False
    if not stat.S_ISDIR(info.st_mode):
        return False
    if info.st_uid != os.getuid():
        return False
    return stat.S_IMODE(info.st_mode) & 0o077 == 0


def _ensure_private_dir(path: Path) -> Path:
    """Create *path* (and parents) and enforce ``0o700``.

    Raises ``OSError`` when the directory cannot be created or its mode cannot
    be tightened — the caller (:meth:`ControlServer.start`) treats that as
    "control channel unavailable" rather than crashing the app.
    """
    path.mkdir(parents=True, exist_ok=True)
    current = stat.S_IMODE(path.stat().st_mode)
    if current & 0o077:
        os.chmod(path, _DIR_MODE)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise OSError(f"control runtime dir is not private: {path}")
    return path


def runtime_dir() -> Path:
    """Private runtime directory holding the socket + pointer.

    ``IMGSLI_CONTROL_DIR`` wins unconditionally (tests / explicit override);
    otherwise ``$XDG_RUNTIME_DIR`` is used when it exists, is writable, and is
    already private; otherwise the app data dir's ``run/`` subdir is created.
    """
    override = os.environ.get("IMGSLI_CONTROL_DIR", "").strip()
    if override:
        return _ensure_private_dir(Path(override).expanduser())

    xdg = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if xdg:
        candidate = Path(xdg)
        if candidate.is_dir() and os.access(candidate, os.W_OK) and _is_private_dir(
            candidate
        ):
            return candidate

    return _ensure_private_dir(app_data_dir() / "run")


def socket_path(dir: Path | str | None = None) -> Path:
    """Path of the control unix socket (``<dir>/control.sock``)."""
    return Path(dir) / SOCKET_NAME if dir is not None else runtime_dir() / SOCKET_NAME


def pointer_path(dir: Path | str | None = None) -> Path:
    """Path of the discovery pointer (``<dir>/instance.json``)."""
    return Path(dir) / POINTER_NAME if dir is not None else runtime_dir() / POINTER_NAME


def write_pointer(*, pid: int, socket: Path | str, version: str) -> Path:
    """Atomically publish the discovery pointer; returns its path.

    Written to a sibling temp file then ``os.replace``-d, so a concurrent
    reader sees either the previous pointer or the complete new one — never a
    half-written JSON document.
    """
    target = pointer_path()
    payload = {
        "pid": int(pid),
        "socket": str(socket),
        "version": str(version or ""),
        "uid": os.getuid(),
    }
    tmp = target.with_name(target.name + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(tmp, _FILE_MODE)
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def read_pointer() -> dict[str, Any] | None:
    """Read the discovery pointer, or ``None`` when absent/unreadable/corrupt."""
    try:
        raw = pointer_path().read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def clear_pointer() -> None:
    """Remove the discovery pointer; missing is a no-op."""
    try:
        pointer_path().unlink(missing_ok=True)
    except OSError:
        pass


def peer_uid_ok(socket_descriptor: int) -> bool:
    """True iff the connected peer's uid equals ``os.getuid()``.

    ``SO_PEERCRED`` on the raw descriptor (Linux). The descriptor is *wrapped,
    not owned*: ``detach()`` is mandatory so garbage collection cannot close
    Qt's own socket fd. Any failure (bad fd, no ``SO_PEERCRED``, unsupported
    platform) returns ``False`` — refuse, never raise.
    """
    if not hasattr(socket, "SO_PEERCRED"):
        return False  # pragma: no cover - non-Linux
    try:
        wrapper = socket.socket(fileno=int(socket_descriptor))
    except Exception:
        return False
    try:
        raw = wrapper.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
        )
        _pid, uid, _gid = struct.unpack("3i", raw)
        return uid == os.getuid()
    except Exception:
        return False
    finally:
        try:
            wrapper.detach()
        except Exception:
            pass


def stale_pointer_alive() -> bool:
    """True iff the pointer names a live pid (liveness only, no handshake).

    ``False`` when there is no pointer, it is corrupt, or the pid is dead
    (``os.kill(pid, 0)`` → ``ProcessLookupError``). Callers use this to decide
    whether a leftover pointer may be cleaned up / a socket reused.
    """
    data = read_pointer()
    if not data:
        return False
    try:
        pid = int(data.get("pid"))
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


#: Max key combos a single ``press_keys`` request may inject.
_MAX_KEY_COMBOS = 32

#: Key names accepted by ``press_keys`` → ``Qt.Key`` attribute (lowercased).
_KEY_ALIASES = {
    "up": "Key_Up",
    "down": "Key_Down",
    "left": "Key_Left",
    "right": "Key_Right",
    "home": "Key_Home",
    "end": "Key_End",
    "pageup": "Key_PageUp",
    "pagedown": "Key_PageDown",
    "tab": "Key_Tab",
    "enter": "Key_Return",
    "return": "Key_Return",
    "escape": "Key_Escape",
    "esc": "Key_Escape",
    "space": "Key_Space",
    "backspace": "Key_Backspace",
    "delete": "Key_Delete",
    "del": "Key_Delete",
    "menu": "Key_Menu",
    "comma": "Key_Comma",
    "plus": "Key_Plus",
}

#: Punctuation → Qt key, so a client can type a *path* or any other text
#: field keystroke by keystroke (``/,t,m,p,/,a,.,p,n,g``). Qt names these
#: keys, so without this map a path is untransmittable -- the one gap that
#: made headless file dialogs undriveable. ``','`` and ``'+'`` are absent on
#: purpose: they are the separators (see ``_ESCAPED_SEPARATORS``).
_PUNCTUATION_KEYS = {
    "/": "Key_Slash",
    ".": "Key_Period",
    "-": "Key_Minus",
    "_": "Key_Underscore",
    "~": "Key_AsciiTilde",
    "=": "Key_Equal",
    ":": "Key_Colon",
    ";": "Key_Semicolon",
    "(": "Key_ParenLeft",
    ")": "Key_ParenRight",
    "[": "Key_BracketLeft",
    "]": "Key_BracketRight",
    "@": "Key_At",
    "#": "Key_NumberSign",
    "$": "Key_Dollar",
    "%": "Key_Percent",
    "!": "Key_Exclam",
    "?": "Key_Question",
    "*": "Key_Asterisk",
    "\\": "Key_Backslash",
}

#: The separator characters as *keys*: ``\,`` / ``\+`` are rewritten to these.
_ESCAPED_SEPARATORS = {",": "comma", "+": "plus"}

#: Modifier names accepted by ``press_keys`` → ``Qt.KeyboardModifier``.
_MODIFIERS = {
    "ctrl": Qt.KeyboardModifier.ControlModifier,
    "control": Qt.KeyboardModifier.ControlModifier,
    "shift": Qt.KeyboardModifier.ShiftModifier,
    "alt": Qt.KeyboardModifier.AltModifier,
    "meta": Qt.KeyboardModifier.MetaModifier,
}


class MethodError(Exception):
    """A client-visible failure ⇒ ``{"ok": false, "error", "hint"}``.

    Defined here (the channel's primitive module) so both the transport and the
    handlers share one error type without a circular import.
    """

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


def valid_key_names() -> list[str]:
    """Every key name ``press_keys`` accepts (for an actionable hint)."""
    names = sorted(_KEY_ALIASES)
    names += [f"f{i}" for i in range(1, 13)]
    names += list(string.ascii_lowercase) + list(string.digits)
    names += sorted(_PUNCTUATION_KEYS)
    names += [f"\\{char}" for char in sorted(_ESCAPED_SEPARATORS)]
    return names


def _resolve_key(name: str) -> Any:
    if name in _KEY_ALIASES:
        return getattr(Qt, _KEY_ALIASES[name])
    if name in _PUNCTUATION_KEYS:
        return getattr(Qt, _PUNCTUATION_KEYS[name])
    if len(name) == 1 and name.isalpha():
        return getattr(Qt, "Key_" + name.upper())
    if len(name) == 1 and name.isdigit():
        return getattr(Qt, "Key_" + name)
    if re.fullmatch(r"f(?:[1-9]|1[0-2])", name):
        return getattr(Qt, "Key_F" + name[1:])
    raise MethodError(
        f"unknown key {name!r}", "valid names: " + ", ".join(valid_key_names())
    )


def parse_key_sequence(keys: str | None) -> list[tuple[Any, Any, str]]:
    """Parse ``'ctrl+shift+p'`` / ``'Down,Down,Enter'`` → (key, modifiers, label).

    The separators are also real keys, so a key is written ``comma`` / ``plus``
    or escaped (``ctrl+\\,`` / ``ctrl+\\+``); the escape is rewritten to the
    name first, leaving the split rule untouched. Raises ``MethodError`` (with
    the valid-name list) on any unknown key or modifier, so the client learns
    the allowlist instead of silently typing.
    """
    if not isinstance(keys, str) or not keys.strip():
        raise MethodError(
            "press_keys needs a non-empty 'keys' string",
            "e.g. keys='Down,Down,Enter' or keys='ctrl+shift+p'",
        )
    for char, name in _ESCAPED_SEPARATORS.items():
        keys = keys.replace("\\" + char, name)
    combos = [part.strip() for part in keys.split(",") if part.strip()]
    if not combos:
        raise MethodError("press_keys got no key combos", "e.g. keys='Enter'")
    if len(combos) > _MAX_KEY_COMBOS:
        raise MethodError(
            f"too many key combos ({len(combos)} > {_MAX_KEY_COMBOS})",
            f"send at most {_MAX_KEY_COMBOS} combos",
        )
    parsed: list[tuple[Any, Any, str]] = []
    for combo in combos:
        parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
        if not parts:
            raise MethodError(f"empty key combo {combo!r}", "plus key: 'plus' or '\\+'")
        modifiers = Qt.KeyboardModifier.NoModifier
        for modifier in parts[:-1]:
            flag = _MODIFIERS.get(modifier)
            if flag is None:
                raise MethodError(
                    f"unknown modifier {modifier!r}", "modifiers: ctrl, shift, alt, meta"
                )
            modifiers |= flag
        parsed.append((_resolve_key(parts[-1]), modifiers, combo))
    return parsed


def resolve_capture_target(app: Any, window: Any, what: Any) -> tuple[Any, str]:
    """The widget ``capture_live`` grabs: a named tab page, else the active window."""
    from PySide6.QtWidgets import QApplication, QWidget

    if what:
        label = str(what)
        try:
            from tabs.registry import TabRegistry

            registry = TabRegistry()
            page = registry.get_page(label)
        except Exception:
            registry, page = None, None
        if page is None:
            # A name the client saw in ``list_surfaces`` is KNOWN but may simply
            # not be open yet — saying "unknown surface" there is a lie the
            # client cannot act on (live proof 2026-10-17: the list advertises
            # every registered kind, while a page only exists once opened).
            known_kind = False
            try:
                known_kind = bool(registry is not None and label in set(registry.registered_types))
            except Exception:
                known_kind = False
            if known_kind:
                raise MethodError(
                    f"surface {label!r} is not open in the live app",
                    "open it first (open_tab) or omit 'what' to capture the active window",
                )
            raise MethodError(
                f"unknown surface {label!r}",
                "call list_surfaces to see live surface names (only rows with capturable=true "
                "can be grabbed right now)",
            )
        return page, label
    active = None
    instance = app or QApplication.instance()
    if instance is not None:
        try:
            active = instance.activeWindow()
        except Exception:
            active = None
    if active is None and isinstance(window, QWidget):
        active = window
    label = ""
    if active is not None:
        # ``objectName`` is a *method* on PySide6 widgets, not an attribute.
        getter = getattr(active, "objectName", None)
        label = getter() if callable(getter) else str(getter or "")
        if not label:
            label = type(active).__name__
    return active, label or "window"
