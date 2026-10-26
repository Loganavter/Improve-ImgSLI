"""Quick-look host glue — dwell-gated tiled kick + settle-time neighbor warm.

Split from ``preview_canvas_host.py`` (plan-gallery-split-2026-10-17, Part
C2). Bodies moved verbatim; names/signatures unchanged. Plain functions
taking the overlay as their first argument (``CODE_PATTERNS.md``).

``_arm_tiled_dwell`` stages the tiled full-store kick (dwell-fire or
zoom>1.0); the settle singleShot runs the token-gated neighbor
prefetch/coarse memo warm. No new timers — all reuse the existing
``_ql_prefetch_token`` / ``_ql_gen`` guards.
"""

from __future__ import annotations

from ._refs import host as _host


def _arm_tiled_dwell(overlay, canvas, path, key) -> None:
    """Stage the tiled full-store kick for dwell-fire or zoom>1 (never raises).

    Dwell-gate: a plain show stages the kick but starts NO decode — the
    tiled memo stays empty and the bounded coarse store keeps driving 1.0
    frames. The canvas fires the staged kick on dwell (``_ql_on_dwell``,
    same ``_ql_gen`` retirement as the pyramid pre-warm — no second timer)
    or immediately on wheel-zoom past 1.0. On dwell the demand/pyramid
    decode is preferred (I2, audit R4): one full decode of the file, and
    the staged kick is served from THAT store once it lands; the uncapped
    kick below still fires when the demand path cannot serve (source over
    ``_QL_FULL_EDGE_CAP`` → coarse-only). A tiled memo hit still installs
    synchronously (zero decode, same as before). Any miss fails open with
    the staged kick dropped. Never raises.
    """
    try:
        path_s = str(path or "")
        if not path_s:
            return
        if key is None:
            key = path_s  # stat-failed memo key: still a stable identity.
        setter = getattr(canvas, "set_tiled_source", None)
        if not callable(setter):
            return
        memo = _host()._tiled_store_cache_lookup(overlay, key)
        if memo is not None:
            try:
                setter(key, memo)
            except Exception:
                pass
            return
        try:
            z = float(getattr(canvas, "_zoom", 1.0))
        except Exception:
            z = 1.0
        if z > 1.0:
            # Already zoomed past 1.0: dwell is bypassed, kick now.
            _host()._populate_tiled_source(overlay, canvas, path_s, key)
            return
        try:
            import weakref

            canvas._ql_tiled_pending = {
                "overlay": weakref.ref(overlay),
                "path": path_s,
                "key": key,
            }
        except Exception:
            pass
    except Exception:
        pass


def _schedule_prefetch(overlay, item) -> None:
    """Defer the neighbor prefetch past show settle (never raises).

    Posted as ``singleShot(0)`` so the live coarse build owns the thread
    pool + disk while ``show_for``/``_populate`` are still settling; the
    fire re-checks the prefetch token, so a walk that landed in between
    supersedes this schedule (its own populate scheduled a fresh one).
    Without an event loop the fire runs inline — still token-guarded.
    Never raises.
    """
    try:
        token = int(getattr(overlay, "_ql_prefetch_token", 0) or 0)
    except Exception:
        token = 0
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda _t=token: _host()._fire_scheduled_prefetch(overlay, item, _t))
    except Exception:
        try:
            _host()._fire_scheduled_prefetch(overlay, item, token)
        except Exception:
            pass


def _fire_scheduled_prefetch(overlay, item, token) -> None:
    """Settle-time prefetch fire: token-gated ``_prefetch_neighbors`` + metrics warm."""
    try:
        try:
            live = int(getattr(overlay, "_ql_prefetch_token", 0) or 0)
        except Exception:
            return
        if int(live) != int(token):
            return  # superseded by a newer show/walk — its schedule covers it.
        _host()._prefetch_neighbors(overlay, item)
        _host()._warm_metrics_neighbors(overlay, token)
    except Exception:
        pass


def _warm_metrics_neighbors(overlay, token) -> None:
    """Settle-time metrics warm: pre-build prev/next row sets (fail-open).

    Runs inside the existing settle singleShot (no new timers): prev/next of
    ``overlay._series_items`` around ``overlay._current_idx``, NEXT-FIRST,
    via ``metrics.warm_metrics_for`` (hidden-parent pre-build, cache store).
    ``_ql_prefetch_token`` is re-checked between the two warms — any
    walk/show/hide bump retires the pending warms. Total warm budget
    ~40ms for both (``perf_counter``; stop when exceeded). Never raises,
    never touches prefetch/dwell/tiled paths.
    """
    try:
        try:
            series = list(getattr(overlay, "_series_items", None) or [])
        except Exception:
            return
        if len(series) < 2:
            return
        try:
            idx = int(getattr(overlay, "_current_idx", 0) or 0)
        except Exception:
            return
        targets = []
        for cand in (idx + 1, idx - 1):  # NEXT-FIRST.
            if 0 <= cand < len(series):
                try:
                    targets.append(series[cand])
                except Exception:
                    pass
        if not targets:
            return
        try:
            from tabs.image_gallery.ui.quick_look.metrics import warm_metrics_for as _warm
        except Exception:
            return
        try:
            import time as _time

            _start = _time.perf_counter()
        except Exception:
            _start = None
            _time = None
        for target in targets:
            try:
                live = int(getattr(overlay, "_ql_prefetch_token", 0) or 0)
            except Exception:
                return
            if int(live) != int(token):
                return  # bumped mid-settle — pending warms retired.
            if _start is not None:
                try:
                    if (_time.perf_counter() - _start) > 0.040:
                        return
                except Exception:
                    pass
            try:
                _warm(overlay, target)
            except Exception:
                pass
    except Exception:
        pass


def _prefetch_neighbors(overlay, item) -> None:
    """Background coarse+memo prefetch for walk neighbors (fail-open).

    Bounds: prev/next of ``overlay._series_items`` around
    ``overlay._current_idx`` only (at most two workers). Each neighbor gets
    the bounded coarse build (``_coarse_store_for`` — NEVER the uncapped
    full decode) whose result installs the materialized store in
    ``_preview_store_cache`` plus the sampled pixmap in ``_stash_cache``
    under the SAME ``_stash_cache_key`` the walk path reads — so a revisit
    is a memo hit with zero source decodes. Guarded by
    ``overlay._ql_prefetch_token`` (bumped on every show/walk populate and
    on walk/hide release): stale workers close their store via
    ``_close_store_quiet`` and never install. Never touches the live
    ``_preview_store`` / ``_preview_full`` / canvas source — memos only.
    Any miss leaves existing behavior bit-for-bit. Never raises.
    """
    try:
        try:
            series = list(getattr(overlay, "_series_items", None) or [])
        except Exception:
            return
        if len(series) < 2:
            return
        try:
            idx = int(getattr(overlay, "_current_idx", 0) or 0)
        except Exception:
            return
        targets = []
        for cand in (idx - 1, idx + 1):
            if 0 <= cand < len(series):
                try:
                    targets.append(series[cand])
                except Exception:
                    pass
        if not targets:
            return
        try:
            token = int(getattr(overlay, "_ql_prefetch_token", 0) or 0)
        except Exception:
            token = 0
        try:
            from tabs.image_gallery.ui.quick_look.preview import _stash_cache_key, _stash_cache_lookup
        except Exception:
            return
        try:
            from PySide6.QtCore import QThreadPool

            from sli_ui_toolkit.workers import GenericWorker

            pool = QThreadPool.globalInstance()
        except Exception:
            pool = None
        if pool is None:
            return
        for target in targets:
            try:
                path_s = str(getattr(target, "path", "") or "")
                if not path_s:
                    continue
                try:
                    key = _stash_cache_key(path_s)
                except Exception:
                    key = None
                if key is None:
                    key = path_s  # stat-failed memo key: stable identity.
                # Already memoized (store or pixmap): zero work. A pixmap
                # hit with a store miss is left to the walk path, which
                # materializes it synchronously with no source decode.
                if _host()._preview_store_cache_lookup(overlay, key) is not None:
                    continue
                try:
                    if _stash_cache_lookup(overlay, key) is not None:
                        continue
                except Exception:
                    pass
            except Exception:
                continue

            def _on_prefetch_ready(store, _t=token, _k=key) -> None:
                try:
                    live = int(getattr(overlay, "_ql_prefetch_token", -1) or 0) == int(_t)
                except Exception:
                    live = False
                if not live:
                    # Walked/hid away — close the private result, keep memos.
                    _host()._close_store_quiet(store)
                    return
                try:
                    ok = store is not None and bool(store.is_open)
                except Exception:
                    ok = False
                if not ok:
                    return
                # The walk may have populated meanwhile — keep its memo.
                if _host()._preview_store_cache_lookup(overlay, _k) is not None:
                    _host()._close_store_quiet(store)
                    return
                _host()._preview_store_cache_store(overlay, _k, store)
                try:
                    from tabs.image_gallery.ui.quick_look.preview import (
                        _sample_coarse_pixmap,
                        _stash_cache_store,
                    )

                    pm = _sample_coarse_pixmap(store)
                    try:
                        _pm_ok = pm is not None and not pm.isNull()
                    except Exception:
                        _pm_ok = False
                    if _pm_ok:
                        _stash_cache_store(overlay, _k, pm)
                except Exception:
                    pass

            try:
                worker = GenericWorker(_host()._coarse_store_for, path_s)
                worker.signals.result.connect(_on_prefetch_ready)
                pool.start(worker)
            except Exception:
                pass
    except Exception:
        pass
