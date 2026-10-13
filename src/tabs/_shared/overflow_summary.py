"""Shared overflow-summary builder (C2).

Single source for the compact "which items were shed when a grid/queue is
full" text that the IC/MC drop queues and full-resolution staging FIFO
previously each re-derived inline (names up to a small cap, plus the
``(+N more)`` tail). Every "grid/queue full" site formats its shed list
through :func:`summarize_overflow` so the truncation rule (first 5,
count of the rest) cannot drift between callers.

The helper is intentionally pure: it never logs or reports. Callers own
their channel (``logger`` / ``controller.report_user_error`` /
``DropQueue``'s ``overflow_reporter``) and embed the returned text in
their own message — only the list formatting lives here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


#: Maximum number of shed entries rendered by default before truncation.
DEFAULT_LIMIT = 5


def _entry_name(item: Any) -> str:
    """Best-effort display name for a shed entry.

    Entries may be paths, strings, or FIFO tuples of the form
    ``(slot_id, path, ...)`` (full-res queue) — in that case the path
    component (index 1) is the human-relevant value. Never raises.
    """
    target: Any = item
    if isinstance(item, (tuple, list)) and len(item) >= 2:
        target = item[1]
    try:
        if isinstance(target, Path):
            return target.name
        return Path(target).name
    except Exception:
        try:
            return str(target)
        except Exception:
            return str(item)


def summarize_overflow(
    items: Iterable[Any] | None = None,
    *,
    limit: int = DEFAULT_LIMIT,
    extra: bool = True,
    separator: str = ", ",
) -> str:
    """Summarize a shed/overflow list as ``"a, b, c (+N more)"``.

    ``items`` may be paths/strings or FIFO tuples ``(id, path, ...)`` — the
    path component is used for display. ``limit`` caps the number of names
    rendered (``None`` renders all); ``extra=False`` omits the
    ``(+N more)`` tail (some call sites want the bare name list). Empty
    input yields the empty string. Never raises.
    """
    try:
        seq = list(items) if items is not None else []
    except Exception:
        try:
            seq = list(items)  # type: ignore[arg-type]
        except Exception:
            return ""
    count = len(seq)
    if limit is None or limit < 0:
        shown = seq
    else:
        shown = seq[:limit]
    names = [_entry_name(x) for x in shown]
    text = separator.join(names)
    if extra:
        additional = count - len(shown)
        if additional > 0:
            suffix = f" (+{additional} more)"
            text = f"{text}{suffix}" if text else suffix.lstrip()
    return text


__all__ = ["DEFAULT_LIMIT", "summarize_overflow"]
