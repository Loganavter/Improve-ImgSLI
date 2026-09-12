"""Test support: build a UnifiedFlyout pre-wired with the app's rating row."""

from __future__ import annotations

from ui.widgets.rating_item import make_rating_row_factory


def _stub_rating_callbacks():
    return dict(
        get_rating=lambda *args, **kwargs: 0,
        increment_rating=lambda *args, **kwargs: None,
        decrement_rating=lambda *args, **kwargs: None,
        create_rating_gesture=lambda *args, **kwargs: None,
    )


def wire_rating_factory(flyout):
    """Set the app's rating row as the flyout's row factory (stub callbacks)."""
    flyout.set_row_factory(make_rating_row_factory(**_stub_rating_callbacks()))
    return flyout
