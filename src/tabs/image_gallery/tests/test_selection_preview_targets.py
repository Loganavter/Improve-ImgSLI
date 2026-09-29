"""Live marquee preview must reach the grid through the controller shape.

Regression: commit_preview searched only owner.grid_view/widget/_widget,
but the production controller nests the grid at widget._grid_view — every
live update silently no-op'd and selection appeared only after release
(state commit). The visual-target resolver covers the nesting.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.use_cases import selection as sel


def _controller_owner():
    applied: list[set] = []
    grid = SimpleNamespace(apply_selection=lambda paths: applied.append(set(paths)))
    widget = SimpleNamespace(_grid_view=grid)
    owner = SimpleNamespace(widget=widget)
    return owner, applied


def test_commit_preview_paints_through_controller_nesting() -> None:
    owner, applied = _controller_owner()
    sel.commit_preview(owner, {Path("a.png")}, additive=False)
    assert len(applied) == 1
    assert {str(p) for p in applied[0]} == {"a.png"}


def test_commit_preview_additive_unions_without_state() -> None:
    owner, applied = _controller_owner()
    sel.commit_preview(owner, {Path("b.png")}, additive=True)
    assert len(applied) == 1
    # No state mutation: owner has no state attr at all (would raise).
    assert not hasattr(owner, "state")


def test_notify_selection_changed_paints_nested_grid() -> None:
    owner, applied = _controller_owner()
    sel._notify_selection_changed(owner, {Path("c.png")})
    assert len(applied) == 1
    assert {str(p) for p in applied[0]} == {"c.png"}


def test_flat_shapes_still_resolve() -> None:
    applied: list[set] = []
    grid = SimpleNamespace(apply_selection=lambda paths: applied.append(set(paths)))
    sel.commit_preview(SimpleNamespace(grid_view=grid), {Path("d.png")}, additive=False)
    assert len(applied) == 1
    sel.commit_preview(SimpleNamespace(), {Path("e.png")}, additive=False)  # no target: silent
