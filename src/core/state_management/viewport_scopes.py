"""Viewport store-change subdomains that bypass the generic chrome batch.

A store change emitted with the bare ``"viewport"`` domain falls through
``on_store_state_changed`` (``ui/presenters/main_window/state.py``) and its
IC twin ``chrome_sync._on_store_state_changed`` into ``handle_store_domain``,
which schedules the FULL chrome batch (``file_names`` / ``combobox`` /
``ratings`` / ``resolution`` / ``zoom_indicator`` / ``window_schedule`` — the
last two drive the InfoHUD glass grab+blur).

For a continuous, purely-visual canvas update that batch is pure waste: it
runs every tick of a split-line drag, a pan, or a font/label slider. The
owners of those updates must emit with one of these lightweight subdomains
(``"viewport.<sub>"``) instead — both handlers skip them and the owning
feature re-renders the canvas directly.

This constant is the SINGLE SOURCE OF TRUTH for that skip set so the two
handlers cannot drift apart (one skipping a subdomain the other still routes
through the batch was a real regression class).

Members:

* ``interaction`` — pan / zoom / split-line drag (divider, magnifier).
* ``geometry`` — layout / letterbox / viewport-rect recompute.
* ``overlay`` — on-canvas text/label settings (``filename_overlay``).
"""

from __future__ import annotations

LIGHTWEIGHT_VIEWPORT_SUBDOMAINS: frozenset[str] = frozenset(
    {"interaction", "geometry", "overlay"}
)

__all__ = ["LIGHTWEIGHT_VIEWPORT_SUBDOMAINS"]
