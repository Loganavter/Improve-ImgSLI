"""Root pytest configuration: tier markers assigned by file location.

Every test file gets its tier marker from *where it lives* (one table below),
not from an `pytestmark` line in each of the ~440 test modules. A new test
inherits its tier by being created in the right folder, and a moved test
cannot keep a stale marker.

The tiers answer "which slice of the suite does this edit need?" — see
`docs/dev/TESTING.md` § Tiers. `slow` is NOT assigned here: it is a duration
property carried per-file by files that scan the whole tree, and duration
cannot be derived from a path.

`qt` is registered by pytest-qt itself and stays where it is — no row here.
"""
from __future__ import annotations

import os

import pytest

# (path prefix, marker). First match wins; paths are repo-root-relative POSIX.
TIER_MARKERS: tuple[tuple[str, str], ...] = (
    ("tests/contracts/", "contracts"),
    ("tests/devtools/", "devtools"),
    ("tests/plugins/", "plugins"),
    ("tests/runtime/", "runtime"),
    ("tests/render/", "render"),
    ("tests/ui/", "ui"),
    ("tests/video/", "video"),
    ("tests/target_bug/", "target_bug"),
    ("src/tabs/", "tabs"),
)

# Tab tests live under `src/tabs/<tab>/tests/**` — the `tabs` row only applies
# to that `/tests/` leg, never to tab production code that happens to be
# collected by a shared contract scan.
_TABS_PREFIX = "src/tabs/"
_TABS_REQUIRES = "/tests/"


def tier_for_path(rel_path: str) -> str | None:
    """Return the tier marker for a repo-root-relative POSIX path, or None.

    Paths with no tier (top-level `tests/*.py` and helpers) return None: they
    belong to the full run and must not be silently claimed by a neighbour's
    marker.
    """
    rel_path = rel_path.replace(os.sep, "/").lstrip("./")
    for prefix, marker in TIER_MARKERS:
        if not rel_path.startswith(prefix):
            continue
        if prefix == _TABS_PREFIX and _TABS_REQUIRES not in rel_path:
            continue
        return marker
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Attach the tier marker of each collected item's file (idempotent)."""
    rootdir = str(config.rootpath)
    for item in items:
        path = getattr(item, "path", None)
        if path is None:  # pragma: no cover - pytest < 7 fallback
            continue
        try:
            rel = os.path.relpath(str(path), rootdir)
        except ValueError:  # pragma: no cover - different drive on Windows
            continue
        marker = tier_for_path(rel)
        if marker is None:
            continue
        existing = {m.name for m in item.iter_markers()}
        if marker in existing:
            continue
        item.add_marker(getattr(pytest.mark, marker))
