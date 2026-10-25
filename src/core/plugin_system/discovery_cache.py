"""Per-process memo for the filesystem/AST discovery scans.

Startup asks for the same entry points repeatedly — the bootstrap tier, the
deferred tier and the session-picker tab grid each walk both package trees and
re-parse every ``plugin.py`` / ``tab.py`` (~6-7 ms per scan on the cold-launch
recon). Discovery is process-lifetime data (a newly added plugin needs a
restart, exactly like a module import), so one dict keyed by ``(kind,
src_root)`` is the whole mechanism.

The caches live here rather than in ``discovery_scan`` because that module is
at the file-size policy limit; this module owns the state, the policy says the
scanner owns the discovery.

Invalidation is explicit and test-only: ``reset_plugin_entry_scan_cache()``,
``reset_tab_entry_scan_cache()`` and ``reset_scan_cache()`` (all kinds).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

#: ``(kind, src_root) -> tuple[entry, ...]``; ``kind`` is ``"plugin"`` or ``"tab"``.
_SCANS: dict[tuple[str, Path | None], tuple[Any, ...]] = {}


def cached_scan(
    kind: str,
    src_root: Path | None,
    filesystem_scan: Callable[[Path | None], Iterable[Any]],
    import_scan: Callable[[], Iterable[Any]],
) -> tuple[Any, ...]:
    """Return the cached entries for *kind*/*src_root*, running the scan once.

    Order is the scan's own: a non-empty filesystem/AST result wins, otherwise
    the import fallback runs. The result is stored as a tuple so callers cannot
    mutate the cache through a returned list.
    """
    key = (kind, src_root)
    cached = _SCANS.get(key)
    if cached is not None:
        return cached
    entries = tuple(filesystem_scan(src_root))
    if not entries:
        entries = tuple(import_scan())
    _SCANS[key] = entries
    return entries


def _reset(kind: str) -> None:
    for key in [k for k in _SCANS if k[0] == kind]:
        _SCANS.pop(key, None)


def reset_plugin_entry_scan_cache() -> None:
    """Drop the plugin-entry scan cache (tests / a synthetic tree rewrite)."""
    _reset("plugin")


def reset_tab_entry_scan_cache() -> None:
    """Drop the tab-entry scan cache (tests / a synthetic tree rewrite)."""
    _reset("tab")


def reset_scan_cache() -> None:
    """Drop every discovery scan cache (tests)."""
    _SCANS.clear()
