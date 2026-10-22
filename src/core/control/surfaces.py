"""The live/devtool surface list a control client can drive.

One question — "what can this running app expose right now?" — answered from the
tab contracts the caller already discovered plus the headless devtool's demo
surfaces. ``tabs`` is a parameter so this module never imports the tab registry.

Split out of ``core/control/discovery.py`` (docs/dev/FILE_SIZE_POLICY.md): pure,
Qt-free helpers with no state.
"""

from __future__ import annotations

from typing import Any


def devtool_surfaces() -> dict[str, Any]:
    """Demo capture surfaces the headless devtool exposes (``live: false``)."""
    try:
        from devtools.capture_surface import SURFACES

        return dict(SURFACES)
    except Exception:
        return {}


def live_surfaces(tabs: list[tuple[str, Any]], *, page_of: Any = None) -> dict[str, Any]:
    """The surface list a client can drive: live tabs + devtool demos.

    ``tabs`` is ``(session_type, TabContract)`` pairs the caller discovered;
    taken as a parameter so this module never imports the tab registry.
    ``page_of(session_type) -> bool`` (optional) reports whether that tab is
    OPEN right now — a registered kind whose page does not exist yet is
    drivable (``open_tab`` first) but NOT capturable, which is exactly the
    distinction a capture client needs; every live-tab row therefore carries
    ``capturable``. Devtool demo surfaces are ``live: false`` fallback-only
    names and are never capturable on the live path.
    """
    rows: dict[str, dict[str, Any]] = {}
    for session_type, tab in tabs:
        name = getattr(tab, "display_name", None)
        try:
            capturable = bool(page_of(session_type)) if callable(page_of) else False
        except Exception:
            capturable = False
        rows[session_type] = {
            "name": session_type,
            "description": str(name or session_type),
            "isolated": False,
            "live": True,
            "capturable": capturable,
        }
    for name, surface in devtool_surfaces().items():
        rows.setdefault(
            name,
            {
                "name": name,
                "description": getattr(surface, "description", ""),
                "isolated": bool(getattr(surface, "isolated", False)),
                "live": False,
                "capturable": False,
            },
        )
    ordered = [rows[key] for key in sorted(rows)]
    return {"count": len(ordered), "surfaces": ordered}
