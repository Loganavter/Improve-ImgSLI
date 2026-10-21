"""Quick Look metric row-container cache + fingerprinting.

Split out of the former ``ui/quick_look/metrics.py`` (plan-gallery-split-2026-10-17,
Part C2). Bodies moved verbatim; names/signatures unchanged. The fingerprint
identity, the bounded row-container cache and its hit/store swaps live here.
"""

from __future__ import annotations

from sli_ui_toolkit.managers import scaled_px

from .theme import _is_dark_theme, _overlay_judgment_domain

#: Bound for the metrics row-container cache (fingerprints → row widgets).
_METRICS_ROW_CACHE_MAX = 8


def _overlay_mode(overlay, mode_str: str = ""):
    """The open report's mode object (never raises).

    Prefers the overlay's live ``_mode`` (the same value the walk renders
    with); a bare stub without one falls back to the ``"<MODE> MODE"`` string
    the caller derived, so a direct ``rebuild_metrics`` call still gets the
    right mode mapping.
    """
    try:
        mode = getattr(overlay, "_mode", None)
    except Exception:
        mode = None
    if mode is not None:
        return mode
    try:
        head = str(mode_str or "").strip().split()
        return head[0].lower() if head else None
    except Exception:
        return None


def _overlay_metric_profile(overlay, mode_str: str = ""):
    """The ACTIVE metric profile for this overlay (``profile_select`` seam).

    The SAME read the card dots use: a stored ``state.metric_profile`` wins,
    else the mode mapping (``active_profile`` fail-open). No second axis list
    lives here — the profile decides which axes the rows and the dots show.
    Never raises.
    """
    try:
        from tabs.image_gallery.use_cases.profile_select import active_profile
    except Exception:
        return None
    try:
        owner = getattr(overlay, "_owner", None)
        state = getattr(owner, "state", None) if owner is not None else None
        return active_profile(state, mode=_overlay_mode(overlay, mode_str))
    except Exception:
        return None


def _profile_fingerprint(overlay, mode_str: str = "") -> tuple:
    """Hashable identity of the active profile (part of the row cache key).

    A profile/domain change must invalidate cached rows: the same item+metrics
    under a different axis subset renders a different row set, so replaying the
    old containers would show stale labels. Never raises.
    """
    try:
        profile = _overlay_metric_profile(overlay, mode_str)
        return (
            tuple(str(a) for a in (getattr(profile, "axis_ids", ()) or ())),
            str(getattr(profile, "source", "") or ""),
            str(getattr(profile, "mode", "") or ""),
            str(getattr(profile, "domain", "") or ""),
            tuple(str(a) for a in (getattr(profile, "salient_axes", ()) or ())),
        )
    except Exception:
        return ()


def _metrics_series_snapshot(overlay) -> tuple:
    """Series-wide inputs of ``rebuild_metrics`` (subline + row salience).

    Two row readers depend on the OTHER members' numbers: ``ssim_subline`` (the
    rejected tail) and the P2 salience verdict (an axis is "inside-noise" only
    relative to the whole series). A late score on a NEIGHBOUR therefore changes
    this item's rows, so the per-member domain score map is part of the
    fingerprint — otherwise a cached row set would keep saying "separates" (or a
    stale percentage) after the series changed.
    """
    try:
        series = list(getattr(overlay, "_series_items", None) or [])
    except Exception:
        return ()
    try:
        domain = _overlay_judgment_domain(overlay)
    except Exception:
        domain = "algorithms"
    try:
        from tabs.image_gallery.services.quality_read import domain_axis_scores
    except Exception:  # pragma: no cover - defensive
        domain_axis_scores = None
    parts = []
    for m in series:
        try:
            p = str(getattr(m, "path", "") or "")
        except Exception:
            p = ""
        try:
            r = getattr(m, "rank", None)
            c = getattr(m, "crown_rank", None)
            if c is not None:
                rk = ("crown", str(c))
            elif r is not None:
                rk = ("rank", str(r))
            else:
                rk = ("best", bool(getattr(m, "is_best", False)))
        except Exception:
            rk = ("none", False)
        try:
            mt = getattr(m, "metrics", None) or {}
            s = mt.get("ssim") if isinstance(mt, dict) else None
            s = str(s) if s is not None else ""
        except Exception:
            s = ""
        try:
            rej = bool(getattr(m, "rejected", False))
        except Exception:
            rej = False
        scores: tuple = ()
        if domain_axis_scores is not None:
            try:
                scores = tuple(
                    sorted(
                        (str(k), int(v))
                        for k, v in domain_axis_scores(m, domain=domain).items()
                    )
                )
            except Exception:
                scores = ()
        parts.append((p, rk, s, rej, scores))
    return tuple(parts)


def _metrics_fingerprint(overlay, item, is_fidelity: bool, mode_str: str) -> tuple:
    """Identity of everything ``rebuild_metrics`` renders.

    Rows are already seated for this exact item/series/theme/scale/profile
    state on a match, so the caller returns early (relayout skipped too).
    ``rank_txt`` falls back to ``current_idx+1`` for rankless items — that
    equals the item's own stable position, covered by the item path + series
    snapshot (a reorder changes the snapshot); the index is also stored
    outright. ``profile_part`` makes the ACTIVE metric profile (and its pinned
    domain) part of the identity, so switching profiles can never replay the
    previous profile's cached row labels.
    """
    try:
        metrics = getattr(item, "metrics", None) or {}
        if not isinstance(metrics, dict):
            metrics = {}
        try:
            metrics_part = tuple(sorted((str(k), str(v)) for k, v in metrics.items()))
        except Exception:
            metrics_part = ()
        try:
            item_path = str(getattr(item, "path", "") or "")
        except Exception:
            item_path = ""
        # On the AI domain the VLM scorecard IS the row source — include the
        # analysis identity (axes + composition) so a late analysis and a domain
        # switch both rebuild the row set. On Algorithms the axes are ignored
        # downstream, so a changed analysis cannot force a needless rebuild.
        try:
            _a = getattr(item, "analysis", None)
            analysis_part = (
                tuple(sorted((str(k), int(v)) for k, v in (getattr(_a, "axes", {}) or {}).items())),
                int(getattr(_a, "composition", -1) or -1),
                tuple(
                    sorted(str(getattr(d, "kind", "")) for d in (getattr(_a, "defects", ()) or ()))
                ),
            )
        except Exception:
            analysis_part = ()
        try:
            domain_part = _overlay_judgment_domain(overlay)
        except Exception:
            domain_part = "algorithms"
        # The active profile decides which axes render, so its identity is a
        # fingerprint input: a profile (or pinned domain) change must rebuild
        # the rows, never replay the previous profile's cached containers.
        profile_part = _profile_fingerprint(overlay, mode_str)
        try:
            series = list(getattr(overlay, "_series_items", None) or [])
            series_len = len(series)
        except Exception:
            series_len = 0
        try:
            current_idx = int(getattr(overlay, "_current_idx", 0) or 0)
        except Exception:
            current_idx = 0
        series_part = _metrics_series_snapshot(overlay)
        try:
            dark = bool(_is_dark_theme())
        except Exception:
            dark = True
        try:
            sp = int(scaled_px(2))
        except Exception:
            sp = 2
        return (item_path, metrics_part, analysis_part, domain_part, profile_part, bool(is_fidelity), str(mode_str), series_len, current_idx, series_part, dark, sp)
    except Exception:
        return ()


def _metrics_cache_store(overlay, key, rows) -> None:
    """Store row containers under *key* (bounded LRU-8, fail-open).

    The currently shown set (``overlay._metrics_shown_key``) is pinned while
    displayed — eviction drops hidden sets only, oldest first, via
    ``removeWidget`` + ``deleteLater`` (mirrors the ``_drop_*_cache`` idiom).
    Never raises.
    """
    try:
        if not key or not rows:
            return
        try:
            cache = getattr(overlay, "_metrics_row_cache", None)
        except Exception:
            return
        if not isinstance(cache, dict):
            cache = {}
            try:
                overlay._metrics_row_cache = cache
            except Exception:
                return
        try:
            cache.pop(key, None)
            cache[key] = list(rows)
        except Exception:
            return
        try:
            shown = getattr(overlay, "_metrics_shown_key", None)
        except Exception:
            shown = None
        try:
            cur = list(getattr(overlay, "_metric_rows", None) or [])
        except Exception:
            cur = []
        try:
            lay = getattr(overlay, "_right_lay", None)
        except Exception:
            lay = None
        while len(cache) > _METRICS_ROW_CACHE_MAX:
            victim = None
            try:
                for k in list(cache.keys()):
                    if k == shown:
                        continue
                    try:
                        vrows = list(cache.get(k) or [])
                    except Exception:
                        vrows = []
                    if cur and vrows and len(vrows) == len(cur) and all(v is c for v, c in zip(vrows, cur)):
                        continue  # tracked live rows — never evict under them.
                    victim = k
                    break
            except Exception:
                break
            if victim is None:
                break
            try:
                victim_rows = cache.pop(victim, None)
            except Exception:
                break
            for w in list(victim_rows or []):
                try:
                    if lay is not None:
                        lay.removeWidget(w)
                except Exception:
                    pass
                try:
                    w.deleteLater()
                except Exception:
                    pass
    except Exception:
        pass


def _metrics_cache_hit(overlay, key, cache) -> bool:
    """Swap in the cached row set for *key* (zero rebuild).

    Hides the previously shown set (it stays cached, hidden), shows the
    cached set, and re-seats rows via ``relayout_report_rows`` — all under
    ``setUpdatesEnabled(False)`` on the report host with the relayout's own
    single layout activation. True when the swap ran (caller returns);
    False on any miss/staleness (caller falls through to the W2 memo, then
    today's rebuild). Never raises.
    """
    try:
        try:
            rows = list(cache.get(key) or [])
        except Exception:
            return False
        if not rows:
            return False
        try:  # every cached container must still be alive.
            for w in rows:
                w.parent()
        except Exception:
            try:
                cache.pop(key, None)
            except Exception:
                pass
            return False
        try:
            shown_key = getattr(overlay, "_metrics_shown_key", None)
        except Exception:
            shown_key = None
        try:
            cur = list(getattr(overlay, "_metric_rows", None) or [])
        except Exception:
            cur = []
        if shown_key == key and cur and len(cur) == len(rows) and all(c is r for c, r in zip(cur, rows)):
            try:  # already displayed — LRU-touch, restore fingerprint, done.
                cache.pop(key, None)
                cache[key] = rows
            except Exception:
                pass
            try:
                overlay._metrics_fingerprint = key
            except Exception:
                pass
            return True
        try:
            host = getattr(overlay, "_report_host", None)
        except Exception:
            host = None
        try:
            lay = getattr(overlay, "_right_lay", None)
        except Exception:
            lay = None
        try:
            if host is not None:
                host.setUpdatesEnabled(False)
        except Exception:
            pass
        try:
            for w in cur:  # hide exactly the outgoing set (cached, kept).
                try:
                    if all(w is not r for r in rows):
                        if lay is not None:
                            lay.removeWidget(w)
                        w.hide()
                except Exception:
                    pass
            overlay._metric_rows = list(rows)
            for w in rows:
                try:
                    if host is not None and w.parent() is not host:
                        w.setParent(host)
                except Exception:
                    pass
                try:
                    w.show()
                except Exception:
                    pass
            try:
                from tabs.image_gallery.ui.quick_look.helpers import relayout_report_rows

                relayout_report_rows(overlay)
            except Exception:
                pass
        finally:
            try:
                if host is not None:
                    host.setUpdatesEnabled(True)
            except Exception:
                pass
        try:  # LRU touch so eviction drops the stalest hidden set.
            cache.pop(key, None)
            cache[key] = rows
        except Exception:
            pass
        try:
            overlay._metrics_fingerprint = key
            overlay._metrics_shown_key = key
        except Exception:
            pass
        return True
    except Exception:
        return False


def _mode_str_for(overlay) -> tuple:
    """Derive ``(is_fidelity, mode_str)`` from ``overlay._mode``.

    Single derivation shared by ``warm_metrics_for`` and the host — byte
    for byte the ``_populate`` derivation (quick_look.py), so warmed keys
    match walk rebuilds exactly. Never raises.
    """
    mode_str = ""
    try:
        _mode = getattr(overlay, "_mode", None)
        if _mode is not None:
            mode_str = str(_mode.value) if hasattr(_mode, "value") else str(_mode)
        else:
            mode_str = "fidelity"
        mode_str = mode_str.upper()
        if not mode_str.endswith(" MODE"):
            mode_str = f"{mode_str} MODE"
    except Exception:
        mode_str = "FIDELITY MODE"
    try:
        is_fidelity = "FIDELITY" in mode_str
    except Exception:
        is_fidelity = True
    return (bool(is_fidelity), str(mode_str))
