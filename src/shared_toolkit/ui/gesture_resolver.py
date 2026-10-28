"""Placeholder ``RatingGestureTransaction`` the app configures into the toolkit.

This module used to try an ``importlib.import_module("ui.gesture_resolver")`` and
then fall back to loading ``src/ui/gesture_resolver.py`` **by file path**, all
inside ``try/except`` blocks that swallowed every failure. There is no such
module (the resolver that exists is ``ui.canvas_infra.scene.gesture_resolver``,
which has no ``RatingGestureTransaction``), so the fallback could never succeed —
it only did a filesystem probe on every import, mutated ``sys.path``, and carried
a *path-based* load that a frozen build cannot follow (the same class of defect
that made the packaged Windows gallery unopenable, owner log 2026-10-28).

What the app has always used is the no-argument class below: the toolkit stores
it as ``rating_gesture_factory`` and never calls it. If a real transaction is
ever implemented, import it statically here.
"""

from __future__ import annotations


class RatingGestureTransaction:
    """No-op transaction placeholder (the toolkit only stores the factory)."""
