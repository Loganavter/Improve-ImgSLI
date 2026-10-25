"""One filesystem-path identity per file — the single source for path-keyed keys.

Why this module exists: a cache keyed on ``os.path.normpath`` alone splits one
file into two entries when the same file reaches the app under two spellings
the *platform* considers equal — ``C:\\A\\x.png`` vs ``c:\\a\\x.png`` on
Windows, or any case-insensitive mount (APFS default, SMB/NAS shares).
Symptoms are duplicate decodes (two full-frame stores for one file) and stale
lookups (a crop/preview/embedded entry written under the other spelling is
invisible). ``shared/clipboard_images`` already used ``normcase(normpath(...))``
for paste dedupe; this module is that pattern, once, for every cache.

``os.path.normcase`` is the identity function on POSIX, so behaviour there is
unchanged. On a case-sensitive filesystem two genuinely different files stay
different — exact-case identity is the correct semantics, not a bug.

Do not grow this module into path *utilities*. It owns one thing: the text
identity of a path.
"""

from __future__ import annotations

import os
from typing import Any

__all__ = ["fs_path_key"]


def fs_path_key(path: Any) -> str:
    """Canonical text identity for ``path``: ``fspath`` → ``normpath`` → ``normcase``.

    Never raises. Callers are cache-key builders on hot paths (per-frame
    ``get_pixel`` probes), and a raise there would turn a lookup miss into a
    crash; a non-path-like value is therefore coerced with ``str()`` instead
    of propagating ``TypeError``. ``bytes`` paths decode through
    ``os.fsdecode`` so the key is always ``str`` (tuple keys must be hashable
    and comparable across call sites, and ``b"/x"`` and ``"/x"`` are the same
    file).
    """
    try:
        text = os.fsdecode(os.fspath(path))
    except Exception:
        try:
            text = str(path)
        except Exception:  # pragma: no cover - str() of a broken object
            text = ""
    try:
        return os.path.normcase(os.path.normpath(text))
    except Exception:  # pragma: no cover - normpath/normcase are total for str
        return text
