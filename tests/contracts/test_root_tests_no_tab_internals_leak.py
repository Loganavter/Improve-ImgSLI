"""Root ``tests/`` must not depend on a specific tab's internals.

``tests/`` is the host-level suite: only ``session_picker`` is guaranteed to
exist there (it's the bootstrap tab). Every other tab under ``src/tabs/`` is
discovered dynamically (see ``_tab_names()``) — a test that deep-imports one
of them (``tabs.image_compare.canvas...``, ``tabs.multi_compare.widget``,
...) is testing that tab's own behavior, not host/generic behavior — it
belongs under ``src/tabs/<tab>/tests/...`` instead, mirroring the same
subfolder (contracts/plugins/render/runtime/video), where
``src/tabs/conftest.py`` already makes it runnable standalone. New tabs are
covered automatically, no edits needed here.

A handful of root tests legitimately reference a concrete tab's modules —
either as fixture data for an otherwise-generic host mechanism (tab
registry, session persistence, action registry...) or as an explicit
boundary/isolation contract asserting the *rest* of the codebase doesn't
reach into that tab. Those are named in ``ALLOWED_DEEP_TAB_IMPORTS`` below,
with the reason recorded inline — don't add to it without a real reason,
and don't leave stale entries once a file stops needing the import.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._framework import ROOT, rel

TESTS_ROOT = ROOT / "tests"
TABS_ROOT = ROOT / "src" / "tabs"

# session_picker is the bootstrap tab — the one thing root tests can always
# count on existing — so it's not held to the "own your tests" rule the way
# every other (optional/deferred) tab is.
GUARANTEED_ROOT_TAB = "session_picker"


def _tab_names() -> tuple[str, ...]:
    if not TABS_ROOT.is_dir():
        return ()
    return tuple(
        sorted(
            d.name
            for d in TABS_ROOT.iterdir()
            if d.is_dir()
            and not d.name.startswith("_")
            and d.name != "__pycache__"
            and d.name != GUARANTEED_ROOT_TAB
        )
    )

# rel path (POSIX, relative to repo root) -> why this file is allowed to
# deep-import a specific tab's internals from outside that tab's own tests/.
ALLOWED_DEEP_TAB_IMPORTS: dict[str, str] = {
    "tests/contracts/test_action_registry.py": (
        "generic ActionRegistry contract, image_compare is example fixture data"
    ),
    "tests/contracts/test_settings_contribute_service.py": (
        "generic create_service('contribute_settings', ...) capability pattern, "
        "exercised on both image_compare and multi_compare"
    ),
    "tests/runtime/test_interaction_contracts.py": (
        "shared event-layer/hit-test registry contract, image_compare is the "
        "registered example package"
    ),
    "tests/runtime/test_session_duplicate.py": (
        "generic WorkspaceSessionActions.duplicate_workspace_session mechanism, "
        "image_compare is example fixture data"
    ),
    "tests/runtime/test_session_rehydrate.py": (
        "rehydrate-hook contract tested across both ImageCompareTab and "
        "MultiCompareTab, not one tab's own behavior"
    ),
    "tests/runtime/test_shared_presentation_isolation.py": (
        "Phase-5 shared-presentation contract (no direct feature lookups "
        "outside canvas_features); alias-resolution check registers the "
        "image_compare feature package only as the registry fixture"
    ),
    "tests/contracts/test_tile_constants.py": (
        "cross-cutting tile-constant consistency contract spanning host, "
        "image_compare, and multi_compare"
    ),
    "tests/plugins/test_settings_extras_navigation.py": (
        "host-level regression: settings extras (tab-contributed) must be "
        "keyboard-reachable via NavRowBuilder.extend(); image_compare is the "
        "only tab with extras, so it's the natural fixture"
    ),
    "tests/runtime/test_dispatcher_concurrency.py": (
        "generic Dispatcher thread-safety contract, image_compare tab is fixture for store/dispatcher"
    ),
    "tests/runtime/test_fake_store_anchor.py": (
        "generic Store anchor contract, image_compare tab is fixture for document/state"
    ),
    "tests/runtime/test_reducer_purity_full.py": (
        "widened reducer purity sweep over all action types, image_compare and multi_compare as fixtures"
    ),
}


def _iter_test_files() -> list[Path]:
    return sorted(
        p
        for p in TESTS_ROOT.rglob("test_*.py")
        if "__pycache__" not in p.parts
    )


def _deep_tab_import_candidates(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()

    candidates: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                candidates.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            candidates.add(node.module)
            for alias in node.names:
                candidates.add(f"{node.module}.{alias.name}")
    return {
        c
        for c in candidates
        if any(c.startswith(f"tabs.{tab}.") for tab in _tab_names())
    }


def test_root_tests_do_not_deep_import_tab_internals():
    violations: list[str] = []
    for path in _iter_test_files():
        key = rel(path)
        deep_imports = _deep_tab_import_candidates(path)
        if deep_imports and key not in ALLOWED_DEEP_TAB_IMPORTS:
            violations.append(
                f"{key} imports tab internals directly ({', '.join(sorted(deep_imports))}); "
                "move this test under src/tabs/<tab>/tests/... or add it to "
                "ALLOWED_DEEP_TAB_IMPORTS with a reason if it's a genuine "
                "host-level/generic contract"
            )
    assert not violations, "\n  - " + "\n  - ".join(violations)


def test_allowed_deep_tab_imports_list_has_no_stale_entries():
    live_files = {rel(p) for p in _iter_test_files()}
    stale = [
        key
        for key in ALLOWED_DEEP_TAB_IMPORTS
        if key not in live_files or not _deep_tab_import_candidates(ROOT / key)
    ]
    assert not stale, (
        "ALLOWED_DEEP_TAB_IMPORTS has entries that no longer need the "
        "exception (file moved/deleted, or no longer imports tab internals): "
        + ", ".join(stale)
    )