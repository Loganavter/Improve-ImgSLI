"""Call-time handle on the ``preview_canvas_host`` package namespace.

Split from ``preview_canvas_host.py`` (plan-gallery-split-2026-10-17, Part
C2). The moved bodies resolve every cross-concern call through the package
namespace (``preview_canvas_host.<name>``) rather than through direct
submodule imports. The package is the single patch point: tests
monkeypatch the package (``monkeypatch.setattr(preview_canvas_host,
"_ensure_preview_canvas", ...)``) and the moved bodies must keep observing
those patches — direct submodule imports would bind the original objects
once and silently bypass them. Resolved at call time (never at import), so
there is no import cycle during package init.
"""

from __future__ import annotations


def host():
    """Return the ``preview_canvas_host`` package module (call-time)."""
    from tabs.image_gallery.ui.quick_look import preview_canvas_host

    return preview_canvas_host
