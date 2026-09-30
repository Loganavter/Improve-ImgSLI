"""Marquee gesture snapshot for the gallery context-menu trace.

Single fail-open helper shared by the card context-menu open/hide log lines:
reports ``gesture active/filter/idle/none`` + band visibility/geometry so
the ``IMGSLI_GALLERY_DEBUG`` stream shows whether a marquee band survived the
popup. Never raises, never imports gallery modules (leaf module, no cycles).
"""


def marquee_snapshot(owner, card) -> str:  # type: ignore[no-untyped-def]
    """Fail-open one-liner: gesture state + band visibility/geometry."""
    try:
        candidates = []
        for cand in (owner,):
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
                    filt = "?"
                state = "active" if active is True else ("filter" if filt else "idle")
                band_vis: object = False
                band_geom: object = "-"
                try:
                    band = getattr(gv, "_marquee_band", None)
                    band_vis = bool(band.isVisible()) if band is not None else False
                    band_geom = repr(band.geometry()) if (band is not None and band_vis) else "-"
                except Exception:
                    band_vis, band_geom = "?", "?"
                return f"{state} band_vis={band_vis} geom={band_geom}"
            except Exception:
                continue
    except Exception:
        pass
    return "none"
