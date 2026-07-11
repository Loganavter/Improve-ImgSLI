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

import pytest

from core.store import Store
from core.store_runtime_cache import ViewportRuntimeCache
from core.store_viewport import ViewportState

from ._framework import SRC, iter_py, read, rel

ALLOWED_VIEWPORT_ATTRS = {
    "render_config",
    "session_data",
    "view_state",
    "interaction_state",
    "geometry_state",
    "_viewport_plugin_state",
    "_analysis_plugin_state",
    "viewport_plugin_state",
    "analysis_plugin_state",
}

def _viewport_attr_assignments() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for path in iter_py(SRC):
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Attribute):
                    continue
                inner = target.value
                if (
                    isinstance(inner, ast.Attribute)
                    and inner.attr == "viewport"
                ):
                    out.append((rel(path), target.lineno, target.attr))
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
