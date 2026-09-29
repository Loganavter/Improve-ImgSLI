"""Marquee gesture snapshot for the gallery context-menu trace.

Single fail-open helper shared by the card context-menu open/hide log lines:
reports ``gesture active/filter/idle/none`` + overlay visibility/geometry so
the ``IMGSLI_GALLERY_DEBUG`` stream shows whether a marquee band survived the
popup. Never raises, never imports gallery modules (leaf module, no cycles).
"""


def marquee_snapshot(owner, card) -> str:  # type: ignore[no-untyped-def]
    """Fail-open one-liner: gesture state + overlay visibility/geometry."""
    try:
        candidates = []
        for cand in (owner, getattr(card, "_gallery_owner", None)):
            try:
                if cand is None:
                    continue
                # The candidate itself may own the gesture (grid view passed
                # as owner) — check it directly, not only via delegation.
                candidates.append(cand)
                gv = getattr(cand, "grid_view", None) or getattr(cand, "widget", None)
                gv = getattr(gv, "_grid_view", gv)
                if gv is not None and gv is not cand:
                    candidates.append(gv)
            except Exception:
                continue
        seen = set()
        for gv in candidates:
            try:
                if id(gv) in seen:
                    continue
                seen.add(id(gv))
                gesture = getattr(gv, "_marquee_gesture", None)
                if gesture is None:
                    continue
                active: object = "?"
                filt: object = "?"
                try:
                    active = bool(getattr(gesture, "active", False))
                except Exception:
                    pass
                try:
                    filt = bool(getattr(gesture, "app_filter_installed", False))
                except Exception:
                    pass
                state = "active" if active is True else ("filter" if filt else "idle")
                ov_vis: object = False
                ov_geom: object = "-"
                try:
                    ov = getattr(gesture, "overlay", None)
                    ov_vis = bool(ov.isVisible()) if ov is not None else False
                    ov_geom = repr(ov.geometry()) if (ov is not None and ov_vis) else "-"
                except Exception:
                    ov_vis, ov_geom = "?", "?"
                return f"{state} overlay_vis={ov_vis} geom={ov_geom}"
            except Exception:
                continue
    except Exception:
        pass
    return "none"
