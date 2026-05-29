"""Gesture resolution behavior (no event transport).

The shared ``gesture_resolver`` walks feature-declared gesture bindings to pick
the winning gesture on press and the in-progress gesture on move/release. This
is pure dispatch — it is tested here with synthetic bindings and a fake store,
without any real Qt event delivery or GL context.

Two things this guards:
  * resolver semantics: lowest ``priority`` wins, ``button`` filtering, and the
    deliberate ``except Exception: continue`` swallow (a raising predicate must
    not crash the resolver — it is simply skipped);
  * the silent-death risk that swallow creates: every *real* feature binding's
    ``matches``/``is_active`` must return cleanly (not raise) on a neutral
    store, otherwise its gesture would be silently dead in production.

Dogma source: docs/dev/CANVAS_FEATURES.md §"Gesture Bindings (Mouse Routing)".
"""

from __future__ import annotations

import pytest

import ui.canvas_infra.scene.gesture_resolver as gr
from core.store_viewport import ViewportState
from ui.canvas_infra.scene.gesture_resolver import (
    GesturePressContext,
    iter_active,
    resolve_active,
    resolve_press,
)
from ui.canvas_infra.scene.widget_contract import CanvasFeatureGestureBinding
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_gesture_bindings

LEFT = 1
RIGHT = 2

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeInputSession:
    def __init__(self, owners=()):
        self._owners = set(owners)

    def has_owner(self, owner) -> bool:
        return owner in self._owners

    def is_active(self) -> bool:
        return bool(self._owners)

class _FakeHandler:
    def __init__(self):
        self.input_session = _FakeInputSession()

class _FakeStore:
    def __init__(self, viewport=None):
        self.viewport = viewport if viewport is not None else ViewportState()

def _ctx(store=None, button=LEFT, modifiers=0):
    return GesturePressContext(
        store=store if store is not None else _FakeStore(),
        handler=_FakeHandler(),
        local_pos=(0.0, 0.0),
        button=button,
        modifiers=modifiers,
    )

def _binding(gesture_id, *, button=LEFT, matches=None, is_active=None, priority=100):
    return CanvasFeatureGestureBinding(
        gesture_id=gesture_id,
        button=button,
        matches=matches if matches is not None else (lambda ctx: True),
        is_active=is_active if is_active is not None else (lambda store: False),
        priority=priority,
    )

@pytest.fixture
def fake_bindings(monkeypatch):
    """Replace the registry's gesture bindings with a caller-supplied tuple."""

    def _install(bindings):
        monkeypatch.setattr(gr, "get_canvas_feature_gesture_bindings", lambda: tuple(bindings))

    return _install

# ---------------------------------------------------------------------------
# resolve_press semantics
# ---------------------------------------------------------------------------

def test_resolve_press_lowest_priority_wins(fake_bindings):
    fake_bindings([
        _binding("low_wins", priority=10),
        _binding("loses", priority=999),
    ])
    # Registry returns them sorted by priority already; resolver returns first match.
    winner = resolve_press(_ctx(button=LEFT))
    assert winner is not None and winner.gesture_id == "low_wins"

def test_resolve_press_filters_by_button(fake_bindings):
    fake_bindings([
        _binding("left_only", button=LEFT),
        _binding("right_only", button=RIGHT),
    ])
    assert resolve_press(_ctx(button=RIGHT)).gesture_id == "right_only"
    assert resolve_press(_ctx(button=LEFT)).gesture_id == "left_only"

def test_resolve_press_skips_non_matching(fake_bindings):
    fake_bindings([
        _binding("declines", matches=lambda ctx: False),
        _binding("accepts", matches=lambda ctx: True),
    ])
    assert resolve_press(_ctx()).gesture_id == "accepts"

def test_resolve_press_swallows_raising_matches(fake_bindings):
    def _boom(ctx):
        raise RuntimeError("predicate exploded")

    fake_bindings([
        _binding("raiser", matches=_boom),
        _binding("survivor", matches=lambda ctx: True),
    ])
    # The raising predicate must be skipped, not crash the resolver.
    assert resolve_press(_ctx()).gesture_id == "survivor"

def test_resolve_press_returns_none_when_no_match(fake_bindings):
    fake_bindings([_binding("nope", matches=lambda ctx: False)])
    assert resolve_press(_ctx()) is None

# ---------------------------------------------------------------------------
# resolve_active / iter_active semantics
# ---------------------------------------------------------------------------

def test_resolve_active_picks_active_binding(fake_bindings):
    fake_bindings([
        _binding("idle", is_active=lambda store: False),
        _binding("driving", is_active=lambda store: True),
    ])
    assert resolve_active(_FakeStore()).gesture_id == "driving"

def test_resolve_active_respects_button_filter(fake_bindings):
    fake_bindings([
        _binding("left_active", button=LEFT, is_active=lambda store: True),
        _binding("right_active", button=RIGHT, is_active=lambda store: True),
    ])
    assert resolve_active(_FakeStore(), button=RIGHT).gesture_id == "right_active"

def test_iter_active_returns_all_active(fake_bindings):
    fake_bindings([
        _binding("a", is_active=lambda store: True),
        _binding("b", is_active=lambda store: False),
        _binding("c", is_active=lambda store: True),
    ])
    ids = {b.gesture_id for b in iter_active(_FakeStore())}
    assert ids == {"a", "c"}

def test_iter_active_swallows_raising_is_active(fake_bindings):
    def _boom(store):
        raise RuntimeError("is_active exploded")

    fake_bindings([
        _binding("raiser", is_active=_boom),
        _binding("ok", is_active=lambda store: True),
    ])
    ids = {b.gesture_id for b in iter_active(_FakeStore())}
    assert ids == {"ok"}

# ---------------------------------------------------------------------------
# Real feature bindings must not silently die
# ---------------------------------------------------------------------------

REAL_BINDINGS = list(get_canvas_feature_gesture_bindings())
REAL_IDS = [b.gesture_id for b in REAL_BINDINGS]

def test_some_real_bindings_exist():
    assert REAL_BINDINGS, "expected at least one registered gesture binding"

@pytest.mark.parametrize("binding", REAL_BINDINGS, ids=REAL_IDS)
def test_real_binding_matches_does_not_raise(binding):
    ctx = _ctx(button=binding.button)
    result = binding.matches(ctx)
    assert isinstance(result, bool), (
        f"{binding.gesture_id}.matches returned {result!r}, expected bool"
    )

@pytest.mark.parametrize("binding", REAL_BINDINGS, ids=REAL_IDS)
def test_real_binding_is_active_does_not_raise(binding):
    result = binding.is_active(_FakeStore())
    assert isinstance(result, bool), (
        f"{binding.gesture_id}.is_active returned {result!r}, expected bool"
    )
