"""TilePolicy extraction: one policy value, one fallback entry, same behaviour.

Companion of ``test_tile_policy_matrix.py`` (which pins values). This module
pins the *extraction* itself:

1. the three surfaces (image compare, multi compare, the engine's
   ``TiledImageView``) build a ``TilePolicy`` with the exact matrix values --
   one positive assert per knob per tab, never ``ic != mc``;
2. ``resolve_frame_fallback`` is truth-table identical to
   ``resolve_fallback_lod(..., atomic=...)`` for every combination of the three
   transition booleans under each real policy, with and without a pending mip
   cascade -- i.e. the extraction changed no branch outcome;
3. ``engine.cache.tile_policy`` has no Qt/QRhi in its transitive import graph
   (the contract tier must be able to read it without a Qt import, and a value
   type must not drag a renderer in).

The policies are read from the real modules with the AST resolver in
``test_tile_policy_matrix`` -- the tab modules import PySide6 at module scope,
so they cannot be imported here.
"""

from __future__ import annotations

import ast
import itertools

import pytest

from engine.cache.fallback_lod import resolve_fallback_lod, resolve_frame_fallback
from engine.cache.tile_policy import TilePolicy

from ._framework import SRC
from .test_tile_policy_matrix import (
    HOST_TEXTURE_CACHE,
    IC_POLICY_SITE,
    MC_POLICY_SITE,
    QL_POLICY_SITE,
    TILE_POLICY,
    TILED_IMAGE_VIEW,
    _const,
    _import_target,
    _module_file,
    _tree,
    policy_fields,
)

POLICY_SITES = (IC_POLICY_SITE, MC_POLICY_SITE, QL_POLICY_SITE)

_ATOMIC_FLAGS = (
    "atomic_on_content_swap",
    "atomic_on_hires_flip",
    "atomic_on_level_change",
)


def _policy(site: str) -> TilePolicy:
    """The surface's real policy, rebuilt from its AST-read field values."""
    fields = policy_fields(site)
    return TilePolicy(**fields)


# ---------------------------------------------------------------------------
# 1. Three policies, exact matrix values.
# ---------------------------------------------------------------------------


def test_image_compare_policy_matches_matrix():
    policy = _policy(IC_POLICY_SITE)
    assert policy.lod_mode == "settle"
    assert policy.settle_ms == 100.0
    assert policy.atomic_on_content_swap is True
    assert policy.atomic_on_hires_flip is True
    assert policy.atomic_on_level_change is True
    assert policy.first_paint_hold is True
    assert policy.pin_coarsest is True
    assert policy.tile_budget_bytes == 2 * 1024**3
    assert policy.host_cache_budget_bytes == 3 * 1024**3
    assert policy.array_capacity == 867


def test_multi_compare_policy_matches_matrix():
    policy = _policy(MC_POLICY_SITE)
    assert policy.lod_mode == "immediate"
    assert policy.settle_ms is None
    assert policy.atomic_on_content_swap is False
    assert policy.atomic_on_hires_flip is False
    assert policy.atomic_on_level_change is True
    assert policy.first_paint_hold is False
    assert policy.pin_coarsest is False
    assert policy.tile_budget_bytes == 512 * 1024**2
    assert policy.host_cache_budget_bytes == 512 * 1024**2
    assert policy.array_capacity == 508


def test_engine_view_policy_opts_into_no_atomic_transition():
    """``TiledImageView`` keeps its progressive reveal for every transition."""
    policy = _policy(QL_POLICY_SITE)
    assert policy.lod_mode == "settle"
    assert policy.settle_ms is None
    assert policy.atomic_on_content_swap is False
    assert policy.atomic_on_hires_flip is False
    assert policy.atomic_on_level_change is False
    assert policy.first_paint_hold is False
    assert policy.pin_coarsest is False
    assert policy.tile_budget_bytes == _const(
        TILED_IMAGE_VIEW, "_TILE_CACHE_BUDGET_BYTES"
    )
    assert policy.host_cache_budget_bytes == _const(
        HOST_TEXTURE_CACHE, "DEFAULT_HOST_TEXTURE_CACHE_BUDGET_BYTES"
    )
    assert policy.array_capacity == 508


def test_all_three_surfaces_use_the_one_policy_type():
    """No second policy type: every site imports ``TilePolicy`` from the engine
    value module and builds exactly the declared fields."""
    for site in POLICY_SITES:
        tree = _tree(site)
        imported = {
            (node.module or "")
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and any(alias.name == "TilePolicy" for alias in node.names)
        }
        assert imported == {TILE_POLICY}, (
            f"{site} must import TilePolicy from {TILE_POLICY}, got {imported}"
        )
        assert set(policy_fields(site)) == set(TilePolicy.__dataclass_fields__), (
            f"{site}.TILE_POLICY fields drifted from TilePolicy's declared "
            f"fields"
        )


# ---------------------------------------------------------------------------
# 2. Truth table: resolve_frame_fallback == resolve_fallback_lod(atomic=...).
# ---------------------------------------------------------------------------

_CURRENT = ("current_a", "current_b")
_FALLBACK = ("fallback_a", "fallback_b")


def _run(*, policy, booleans, cascade, more_pending):
    """Invoke the entry and record every callback/result it produced."""
    calls: list[tuple] = []

    def build_fallback_items(prior_key):
        calls.append(("build", prior_key))
        return list(_FALLBACK)

    def drop_covered(items, current):
        calls.append(("drop", tuple(items), tuple(current)))
        return list(items)

    kwargs = dict(
        key="new",
        current_items=list(_CURRENT),
        more_pending=more_pending,
        last_good_key="old",
        build_fallback_items=build_fallback_items,
        drop_covered=drop_covered,
        cascade_pending=cascade,
    )
    if policy is None:
        result = resolve_fallback_lod(**kwargs, atomic=booleans)
    else:
        result = resolve_frame_fallback(policy, **kwargs, **booleans)
    return result, tuple(calls)


def _expected_atomic(policy: TilePolicy, booleans: dict[str, bool]) -> bool:
    """The pre-extraction ``atomic`` expression, written out literally."""
    return bool(
        (policy.atomic_on_content_swap and booleans["is_content_swap"])
        or (policy.atomic_on_hires_flip and booleans["is_hires_flip"])
        or (policy.atomic_on_level_change and booleans["is_level_hold"])
    )


def _boolean_cases() -> list[dict[str, bool]]:
    return [
        dict(zip(("is_content_swap", "is_hires_flip", "is_level_hold"), combo))
        for combo in itertools.product((False, True), repeat=3)
    ]


@pytest.mark.parametrize("site", POLICY_SITES)
def test_resolve_frame_fallback_matches_resolve_fallback_lod(site):
    """Every policy x 8 bool combos x cascade x promotion gate: identical."""
    policy = _policy(site)
    observed_atomic: set[bool] = set()
    for booleans in _boolean_cases():
        expected_atomic = _expected_atomic(policy, booleans)
        observed_atomic.add(expected_atomic)
        for cascade in (False, True):
            for more_pending in (True, False):
                got = _run(
                    policy=policy,
                    booleans=booleans,
                    cascade=cascade,
                    more_pending=more_pending,
                )
                want = _run(
                    policy=None,
                    booleans=expected_atomic,
                    cascade=cascade,
                    more_pending=more_pending,
                )
                assert got == want, (
                    f"{site} policy diverged from resolve_fallback_lod for "
                    f"{booleans}, cascade_pending={cascade}, "
                    f"more_pending={more_pending}: "
                    f"got {got!r}, want {want!r}"
                )
    # Both sides positive where the policy opts into anything: the table is
    # not vacuous (a policy that answered True or False everywhere would pass
    # the equality above trivially). A policy that opts into nothing can only
    # ever answer False -- that IS its behaviour, and the progressive branch
    # equality below pins it.
    opts_in = any(getattr(policy, flag) for flag in _ATOMIC_FLAGS)
    expected_answers = {False, True} if opts_in else {False}
    assert observed_atomic == expected_answers, (
        f"{site}'s policy atomic answers {observed_atomic} do not match its "
        f"flags (opts into any transition: {opts_in})"
    )


def test_policy_flags_actually_gate_the_transition():
    """A transition the policy does not opt into is NOT held atomically.

    Falsification for the table above: MC opts into the level hold only, so a
    content swap there must take the progressive branch even though IC's
    identical call would be atomic.
    """
    ic = _policy(IC_POLICY_SITE)
    mc = _policy(MC_POLICY_SITE)

    swap = {
        "is_content_swap": True,
        "is_hires_flip": False,
        "is_level_hold": False,
    }
    ic_result, _ = _run(policy=ic, booleans=swap, cascade=False, more_pending=True)
    mc_result, _ = _run(policy=mc, booleans=swap, cascade=False, more_pending=True)
    mc_progressive, _ = _run(
        policy=None, booleans=False, cascade=False, more_pending=True
    )
    mc_atomic, _ = _run(
        policy=None, booleans=True, cascade=False, more_pending=True
    )

    assert ic_result == mc_atomic, (
        f"IC content swap must stay atomic (got {ic_result!r}, "
        f"expected {mc_atomic!r})"
    )
    assert mc_result == mc_progressive and mc_result != mc_atomic, (
        f"MC content swap must stay progressive (got {mc_result!r})"
    )


# ---------------------------------------------------------------------------
# 3. The value type is Qt-free, transitively.
# ---------------------------------------------------------------------------


def _imported_modules(tree: ast.Module, module: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = _import_target(node, module)
            names.add(target)
            names.update(f"{target}.{alias.name}" for alias in node.names)
    return names


def test_tile_policy_import_graph_has_no_qt_or_qrhi():
    seen: set[str] = set()
    todo = [TILE_POLICY]
    qt_hits: list[tuple[str, str]] = []
    while todo:
        module = todo.pop()
        if module in seen:
            continue
        seen.add(module)
        for name in _imported_modules(_tree(module), module):
            if name.startswith("PySide6") or "QRhi" in name:
                qt_hits.append((module, name))
            elif _module_file(name) is not None:
                todo.append(name)

    assert TILE_POLICY in seen
    assert not qt_hits, (
        f"{TILE_POLICY} import graph reaches Qt/QRhi: {qt_hits} -- the policy "
        f"is a pure value; the contract tier must read it without Qt"
    )
    assert all(
        module == TILE_POLICY or module.startswith("engine.")
        for module in seen
    ), f"{TILE_POLICY} reaches outside the engine: {sorted(seen)}"
    # A sanity anchor: the engine's own module file is under src/engine/, so
    # this check is not passing on an empty file list.
    assert (SRC / "engine" / "cache" / "tile_policy.py").is_file()
