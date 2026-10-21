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

from ._framework import ROOT, parse, rel

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
    "tests/runtime/test_ql_source_canvas.py": (
        "cross-surface ENGINE-CANVAS contract: the Quick Look source inset must "
        "be the same QuickLookCanvasWidget/host/ViewportState implementation the "
        "main preview uses, so the test drives the real gallery overlay + two "
        "live canvases (a double would not prove the reuse or the shared viewport)"
    ),
    "tests/runtime/test_dialog_title_bar_nav.py": (
        "host-level CSD title-bar navigation contract spanning Help, the "
        "colour picker and the video editor (the modal-ceiling example); the "
        "video editor dialog is the fixture, not the behavior under test"
    ),
    "tests/test_nav_coverage_contract.py": (
        "app-wide keyboard-coverage contract: every registered window's "
        "controls must be nav-owned or reasoned-exempt. It deliberately spans "
        "host dialogs AND the tab-owned surfaces (Clean Review, Quick Look, "
        "video editor) — a per-tab split would let one tab's surface drop out "
        "of the app-wide guarantee, which is the whole point of the contract. "
        "The tab windows are fixtures, not behavior under test (their own "
        "tests live under src/tabs/<tab>/tests/)"
    ),
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
    "tests/test_session_state.py": (
        "generic tabs/use_cases SessionState facade (shared host helper, not a "
        "tab's behavior); fake store only, no tab import"
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
    "tests/runtime/test_noop_dispatch_dropped.py": (
        "generic reducer no-op identity contract (identical object on "
        "no-change, which Dispatcher depends on), image_compare reducers "
        "as fixture alongside core ones"
    ),
    "tests/runtime/test_magnifier_geometry_dispatch_gate.py": (
        "generic source-side no-op dispatch gate contract (skip the call "
        "entirely when values are unchanged), image_compare magnifier "
        "geometry as the exercised call site"
    ),
    "tests/runtime/test_dialog_activation_parenting.py": (
        "cross-cutting Wayland activation contract (transient parents, no "
        "deferred activation ticks) spanning host plugins, palette, and the "
        "image_compare video editor; splitting per-tab would defeat the "
        "single-contract purpose"
    ),
    "tests/render/test_pyramid_stale_guard.py": (
        "cross-tab pyramid stale-guard parity contract (LOD-resolve + "
        "fallback call sites in image_compare and multi_compare over the "
        "shared engine seam); splitting per-tab would defeat the "
        "single-contract purpose"
    ),
    "tests/devtools/test_control_elements.py": (
        "host-level control-channel element contract (ui_elements/ui_click); "
        "the image_gallery card is the real toolkit-widget fixture proving a "
        "gallery card is inventoried as role 'card' and right-click reaches "
        "the tab's own context-menu handler — stock-Qt stand-ins cannot "
        "exercise the toolkit path"
    ),
    "tests/devtools/test_control_scene.py": (
        "host-level control-channel scene contract (get_canvas_scene): the read "
        "verb must serialize the REAL canvases — the Image Compare scene graph "
        "is built by the tab's own magnifier builder and the Multi Compare "
        "composition by the tab's own _rebuild_composition — because a stand-in "
        "scene object could not prove the two-loupe-truths or the projection "
        "reuse the contract exists to pin"
    ),
    "tests/runtime/test_ui_metrics_parity.py": (
        "cross-cutting UI-metrics parity contract (one change channel + owned "
        "derived-geometry refresh); ScaledIconLabel is the image_compare "
        "layout site fixture proving the migrated site re-derives — the "
        "surface table spans host chrome and session_picker too, so the tab "
        "import is fixture data, not the tab's own behavior"
    ),
    "tests/contracts/test_capacity_agreement.py": (
        "cross-tab capacity contract (C1): the image_compare pool's array "
        "capacity must equal the shared TileTextureService default, and every "
        "TileTextureService call site in BOTH tabs must pass that capacity "
        "explicitly. The pool module is the measured subject, not a tab-owned "
        "behavior; a per-tab copy would let one tab's allocator drift from the "
        "service again, which is the failure this contract exists for"
    ),
    "tests/contracts/test_gallery_judge_complete.py": (
        "plan-gallery-ai-judgement-2026-10-21 §Gates GA1 (M2 completeness): the "
        "rank-dispatch invariant spans the controller readiness loop and the "
        "declared rank_completeness interface. It lives in the contracts tier "
        "because the gate must exist BEFORE the behaviour wave that fixes it and "
        "must not be owned by it (P0 gates run in parallel with P1); the "
        "controller/models imports are the measured subject, not gallery UI "
        "behavior (those stay under src/tabs/image_gallery/tests/)"
    ),
    "tests/contracts/test_gallery_judge_profile_stamp.py": (
        "same P0 gate wave (§Gates GA3, defect J3): the profile-freeze invariant "
        "is driven through the REAL GalleryController.analyze → ai_analyze entry "
        "with an all-HIT cache seam — a fake entry cannot prove the stamp is "
        "unreachable before a payload is built, and the gate must stay independent "
        "of the P2 wave that fixes it"
    ),
    "tests/contracts/test_gallery_judge_cache_identity.py": (
        "same P0 gate wave (§Gates GA4, defect J5): the analysis-cache identity "
        "is a data contract (declared field tuple + normalizer), asserted by AST "
        "and runtime over services/ai_cache; the tab-internal import is the "
        "declaration under measurement"
    ),
    "tests/contracts/test_gallery_judge_axis_salience.py": (
        "same P0 gate wave (§Gates GA5, defect J4): written against the DECLARED "
        "P2 helper axis_salience / measured_axes_for in services/rank_fusion so the "
        "interface cannot be invented differently by the wave that implements it"
    ),
}


def _iter_test_files() -> list[Path]:
    return sorted(
        p
        for p in TESTS_ROOT.rglob("test_*.py")
        if "__pycache__" not in p.parts
    )


def _deep_tab_import_candidates(path: Path) -> set[str]:
    tree = parse(path)
    if tree is None:
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