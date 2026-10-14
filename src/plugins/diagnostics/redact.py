"""Redaction for the diagnostics report.

Rules (privacy-first, **fail-closed**):

* the user's home directory → ``~``;
* the username token → ``<user>``;
* secret-looking tokens (``sk-…``, ``Bearer …``, ``api_key: …`` /
  ``token=…`` / ``password=…`` …) → ``***``;
* any other absolute path (POSIX ``/…`` or Windows ``C:\\…``) →
  ``<path:hhhhhhhh>/<basename>`` (directory hashed, basename kept for
  readability);
* on any internal error the value is *dropped* (never emitted raw).

This module never reads file contents — it only rewrites strings it is given.
"""

from __future__ import annotations

import getpass
import hashlib
import os
import re
from pathlib import Path
from typing import Any

MASK = "***"
USER_MASK = "<user>"
REDACTION_FAILED = "<redaction-failed>"

#: Keys whose values must never appear in the report (defence in depth; the
#: schema has no such field by construction — see ``report.FORBIDDEN_FIELDS``).
FORBIDDEN_FIELD_NAMES = frozenset(
    {"image", "pixmap", "screenshot", "thumbnail", "preview", "window_shot", "pixels"}
)

_SK_TOKEN_RE = re.compile(r"\bsk-[A-Za-z0-9._\-]{6,}\b")
_BEARER_RE = re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._\-]{6,})")
# api_key: value / api_key=value / token="value" / password='value'
_SECRET_KV_RE = re.compile(
    r"(?i)"
    r"(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|secret|password|passwd|token)\b\s*[:=]\s*)"
    r"(['\"]?)"
    r"([^\s'\",]{3,})"
)
# POSIX absolute path: leading ``/`` not preceded by word/:/~ characters
# (so ``http://`` and already-``~``-relative paths are left alone).
_ABS_POSIX_RE = re.compile(r"(?<![\w:/~])/(?:[^\s\"'()\[\]{}<>,;|]*)")
# Windows absolute path ``C:\…``.
_ABS_WIN_RE = re.compile(r"(?<![\w:])[A-Za-z]:\\(?:[^\s\"'()\[\]{}<>,;|]*)")


def home_dir() -> str:
    try:
        return str(Path.home())
    except Exception:
        return ""


def username() -> str:
    candidates = (
        lambda: getpass.getuser(),
        lambda: os.environ.get("USER"),
        lambda: os.environ.get("USERNAME"),
    )
    for getter in candidates:
        try:
            value = getter()
        except Exception:
            continue
        if value:
            return str(value)
    return ""


def _hash_path(path: str) -> str:
    """Hash a path's directory, keep the basename for readability."""
    normalized = path.replace("\\", "/")
    trimmed = normalized.rstrip("/")
    if not trimmed:
        return path
    digest = hashlib.sha256(trimmed.encode("utf-8", "replace")).hexdigest()[:8]
    base = trimmed.rsplit("/", 1)[-1]
    if base:
        return f"<path:{digest}>/{base}"
    return f"<path:{digest}>"


def _redact_str(text: str, *, home: str, user: str) -> str:
    out = text
    if home and home in out:
        out = out.replace(home, "~")
    if user and len(user) >= 3:
        out = re.sub(
            rf"(?<![A-Za-z0-9_.\-]){re.escape(user)}(?![A-Za-z0-9_\-])",
            USER_MASK,
            out,
        )
    out = _SK_TOKEN_RE.sub(MASK, out)
    out = _BEARER_RE.sub(lambda m: m.group(1) + MASK, out)
    out = _SECRET_KV_RE.sub(
        lambda m: m.group(1) + (m.group(2) or "") + MASK, out
    )
    out = _ABS_WIN_RE.sub(lambda m: _hash_path(m.group(0)), out)
    out = _ABS_POSIX_RE.sub(lambda m: _hash_path(m.group(0)), out)
    return out


def redact_text(text: Any, *, home: str | None = None, user: str | None = None) -> str:
    """Redact a single string. Non-strings are stringified safely.

    On any internal error the value becomes :data:`REDACTION_FAILED` — it is
    never returned raw (fail-closed).
    """
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return REDACTION_FAILED
    try:
        return _redact_str(text, home=home_dir() if home is None else home, user=username() if user is None else user)
    except Exception:
        return REDACTION_FAILED


def redact_value(value: Any, *, home: str | None = None, user: str | None = None) -> Any:
    """Recursively redact strings inside dicts/lists/tuples."""
    if isinstance(value, str):
        return redact_text(value, home=home, user=user)
    if isinstance(value, dict):
        return {
            redact_text(k, home=home, user=user): redact_value(v, home=home, user=user)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_value(v, home=home, user=user) for v in value]
    return value
