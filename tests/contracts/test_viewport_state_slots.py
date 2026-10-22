"""Guard against assigning attributes that don't exist on ViewportState.

Regression: src/tabs/image_compare/plugins/video_editor/services/video_snapshot_rendering.py used
to do ``store.viewport.overlay_clip_rect = None``, but ``overlay_clip_rect``
lives on ``store.runtime_cache`` (ViewportRuntimeCache), not on ViewportState.
ViewportState uses ``__slots__``, so the typo blew up at runtime with
``AttributeError: 'ViewportState' object has no attribute 'overlay_clip_rect'
and no __dict__ for setting new attributes`` — only when the GPU preview path
actually ran.

This test scans source for ``<expr>.viewport.<attr> = ...`` assignments and
fails if ``<attr>`` is not a real field of ViewportState. It also asserts the
slotted shape of ViewportState so the runtime guard stays in place.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from core.store import Store
from core.store_runtime_cache import ViewportRuntimeCache
from core.store_viewport import ViewportState

from ._framework import SRC, iter_py, parse, read, rel

pytestmark = pytest.mark.slow

ALLOWED_VIEWPORT_ATTRS = {
    "render_config",
    "session_data",
    "view_state",
    "interaction_state",
    "geometry_state",
}


def _public_settable_attrs() -> set[str]:
    """Settable public properties of ``ViewportState`` (slots stay private).

    The private ``_render_config``/… slots are deliberately NOT allowed here:
    an in-place slot write bypasses the Dispatcher (see
    ``tests/contracts/test_no_setattr_store_bypass.py``).
    """
    names: set[str] = set()
    for name in dir(ViewportState):
        member = inspect.getattr_static(ViewportState, name)
        if isinstance(member, property) and member.fset is not None:
            names.add(name)
    return names


def _assignments_in_tree(tree: ast.AST, label: str) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Attribute):
                continue
            inner = target.value
            if isinstance(inner, ast.Attribute) and inner.attr == "viewport":
                out.append((label, target.lineno, target.attr))
    return out


def _viewport_attr_assignments() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for path in iter_py(SRC):
        tree = parse(path)
        if tree is None:
            continue
        out.extend(_assignments_in_tree(tree, rel(path)))
    return out

def test_viewport_state_is_slotted_without_dict():
    """ViewportState must stay slotted so typos fail loudly, not silently."""
    assert hasattr(ViewportState, "__slots__"), "ViewportState must define __slots__"
    inst = ViewportState()
    assert not hasattr(inst, "__dict__"), (
        "ViewportState gained a __dict__ — typo-assignments would silently succeed"
    )

def test_overlay_clip_rect_lives_on_runtime_cache():
    """The field exists on ViewportRuntimeCache, never on ViewportState."""
    cache = ViewportRuntimeCache()
    assert hasattr(cache, "overlay_clip_rect")
    cache.overlay_clip_rect = None
    store = Store()
    assert isinstance(store.runtime_cache, ViewportRuntimeCache)

def test_writing_overlay_clip_rect_on_viewport_state_raises():
    """The exact line that used to ship in production must fail fast."""
    state = ViewportState()
    with pytest.raises(AttributeError):
        state.overlay_clip_rect = None  # type: ignore[attr-defined]

def test_allowlist_matches_the_real_viewport_state():
    """The allowlist must hold no dead names and miss no settable property.

    A stale entry (attribute the class no longer has) makes the scan tolerate
    a name that cannot exist; a missing one makes it flag a live write. Both
    are caught here, so the constant cannot drift from ``ViewportState``.
    """
    real = _public_settable_attrs()
    stale = sorted(ALLOWED_VIEWPORT_ATTRS - real)
    missing = sorted(real - ALLOWED_VIEWPORT_ATTRS)
    assert not stale, (
        "ALLOWED_VIEWPORT_ATTRS names attributes ViewportState does not have "
        f"(delete them): {stale}"
    )
    assert not missing, (
        "ViewportState has settable attributes missing from ALLOWED_VIEWPORT_ATTRS "
        f"(allow them deliberately): {missing}"
    )

def test_every_allowed_viewport_attribute_is_writable():
    """Every allowlisted name must actually accept a write on ViewportState."""
    state = ViewportState()
    for name in sorted(ALLOWED_VIEWPORT_ATTRS):
        setattr(state, name, getattr(state, name))

def test_guard_rejects_unknown_viewport_attribute():
    """The scan itself must fail closed: unknown names are reported.

    Synthetic AST — proves the guard's positive case, independent of whatever
    ``src/`` happens to contain today (it currently has no such assignments).
    """
    tree = ast.parse(
        "store.viewport.not_a_real_field = 1\n"
        "store.viewport._render_config = None\n"
        "store.viewport.render_config = cfg\n"
    )
    flagged = [
        attr for _, _, attr in _assignments_in_tree(tree, "<synthetic>")
        if attr not in ALLOWED_VIEWPORT_ATTRS
    ]
    assert flagged == ["not_a_real_field", "_render_config"], (
        f"guard did not fail closed on unknown/private viewport attrs: {flagged}"
    )

def test_no_source_assigns_unknown_viewport_attribute():
    """Scan src/ for ``*.viewport.<attr> = ...`` with unknown ``<attr>``."""
    offenders = [
        f"{path}:{line} — viewport.{attr} = ..."
        for path, line, attr in _viewport_attr_assignments()
        if attr not in ALLOWED_VIEWPORT_ATTRS
    ]
    assert not offenders, (
        "Found assignments to unknown ViewportState attributes "
        "(ViewportState is slotted — these will blow up at runtime):\n  "
        + "\n  ".join(offenders)
    )
