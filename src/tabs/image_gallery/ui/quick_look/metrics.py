"""Quick look metrics — plain functions taking overlay as first arg.
Audit-Meta: pattern=thin-owner-target size=exempt reason="one metrics-rows concern: rebuild + row-container cache + hidden-parent warm share one fingerprint contract"
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px

#: Bound for the metrics row-container cache (fingerprints → row widgets).
_METRICS_ROW_CACHE_MAX = 8


def _is_dark_theme() -> bool:
    try:
        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _bars_is_dark

        return bool(_bars_is_dark())
    except Exception:
        pass
    return True


def _token_qcolor(token: str, fallback_hex: str, fallback_dark_hex: str | None = None) -> QColor:
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    if fallback_dark_hex is None:
        return QColor(fallback_hex)
    return QColor(fallback_hex if not _is_dark_theme() else fallback_dark_hex)


def _metrics_series_snapshot(overlay) -> tuple:
    """Series-wide inputs of ``ssim_subline`` (re-rank/reject neighbor flips)."""
    try:
        series = list(getattr(overlay, "_series_items", None) or [])
    except Exception:
        return ()
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
        parts.append((p, rk, s, rej))
    return tuple(parts)


def _metrics_fingerprint(overlay, item, is_fidelity: bool, mode_str: str) -> tuple:
    """Identity of everything ``rebuild_metrics`` renders.

    Rows are already seated for this exact item/series/theme/scale state on
    a match, so the caller returns early (relayout skipped too). ``rank_txt``
    falls back to ``current_idx+1`` for rankless items — that equals the
    item's own stable position, covered by the item path + series snapshot
    (a reorder changes the snapshot); the index is also stored outright.
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
        # Metric rows depend on the AI-only Composition axis (a row) — include
        # the analysis identity so a late analysis still rebuilds the row set.
        # Per-axis AI notes are NOT part of the rows anymore (plan UX contract).
        try:
            _a = getattr(item, "analysis", None)
            analysis_part = (
                int(getattr(_a, "composition", -1) or -1),
                str(getattr(_a, "verdict", "") or ""),
                tuple(
                    sorted(str(getattr(d, "kind", "")) for d in (getattr(_a, "defects", ()) or ()))
                ),
            )
        except Exception:
            analysis_part = ()
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
        return (item_path, metrics_part, analysis_part, bool(is_fidelity), str(mode_str), series_len, current_idx, series_part, dark, sp)
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


def warm_metrics_for(overlay, item) -> None:
    """Pre-build (hidden) the metric row set for *item* into the row cache.

    Computes the fingerprint for the target's own series position (the walk
    rebuild runs with ``_current_idx`` on the target, and the fingerprint
    bakes the index in — resolved by identity so the warmed key matches the
    walk's rebuild exactly), returns at once when already cached or live,
    else builds the row set under a hidden staging parent (never inserted
    visible: no paint, no visible relayout) and stores it with the same LRU
    discipline. Never raises; any surprise is a no-op (fail-open: the walk
    builds synchronously as today).
    """
    try:
        is_fidelity, mode_str = _mode_str_for(overlay)
        try:
            series = list(getattr(overlay, "_series_items", None) or [])
        except Exception:
            series = []
        target_idx = None
        try:
            for _i, _m in enumerate(series):
                if _m is item:
                    target_idx = int(_i)
                    break
        except Exception:
            target_idx = None
        try:
            cur_idx = int(getattr(overlay, "_current_idx", 0) or 0)
        except Exception:
            cur_idx = 0
        if target_idx is None:
            target_idx = cur_idx
        try:
            overlay._current_idx = int(target_idx)
        except Exception:
            pass
        try:
            fp = _metrics_fingerprint(overlay, item, is_fidelity, mode_str)
        finally:
            try:
                overlay._current_idx = int(cur_idx)
            except Exception:
                pass
        if not fp:
            return
        try:
            cache = getattr(overlay, "_metrics_row_cache", None)
        except Exception:
            cache = None
        if isinstance(cache, dict) and fp in cache:
            return  # already cached.
        try:
            if getattr(overlay, "_metrics_fingerprint", None) == fp and len(getattr(overlay, "_metric_rows", None) or []):
                return  # a live build for it exists.
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QWidget as _QWidget
        except Exception:
            return
        try:
            staging = getattr(overlay, "_metrics_warm_staging", None)
            try:
                if staging is None:
                    raise ValueError("no staging")
                staging.objectName()  # raises on C++-deleted stubs.
            except Exception:
                staging = None
            if staging is None:
                staging = _QWidget()
                try:
                    staging.hide()
                except Exception:
                    pass
                try:
                    overlay._metrics_warm_staging = staging
                except Exception:
                    pass
            if staging is None:
                return
        except Exception:
            return
        saved_rows = getattr(overlay, "_metric_rows", None)
        saved_fp = getattr(overlay, "_metrics_fingerprint", None)
        saved_shown = getattr(overlay, "_metrics_shown_key", None)
        saved_host = getattr(overlay, "_report_host", None)
        saved_lay = getattr(overlay, "_right_lay", None)
        try:
            overlay._metric_rows = []
        except Exception:
            pass
        try:
            overlay._report_host = staging
        except Exception:
            pass
        try:
            overlay._right_lay = None  # relayout no-ops: never visible.
        except Exception:
            pass
        try:
            overlay._metrics_fingerprint = None
        except Exception:
            pass
        try:
            overlay._current_idx = int(target_idx)
        except Exception:
            pass
        built: list = []
        try:
            rebuild_metrics(overlay, item, is_fidelity, mode_str)
            built = list(getattr(overlay, "_metric_rows", None) or [])
        except Exception:
            built = []
        finally:
            try:
                overlay._metric_rows = saved_rows if isinstance(saved_rows, list) else []
            except Exception:
                pass
            try:
                overlay._report_host = saved_host
            except Exception:
                pass
            try:
                overlay._right_lay = saved_lay
            except Exception:
                pass
            try:
                overlay._metrics_fingerprint = saved_fp
            except Exception:
                pass
            try:
                overlay._metrics_shown_key = saved_shown
            except Exception:
                pass
            try:
                overlay._current_idx = int(cur_idx)
            except Exception:
                pass
        if not built:
            return
        try:  # keep hidden on the staging parent until a hit re-parents.
            for w in built:
                try:
                    if w.parent() is not staging:
                        w.setParent(staging)
                except Exception:
                    pass
                try:
                    w.hide()
                except Exception:
                    pass
        except Exception:
            pass
        _metrics_cache_store(overlay, fp, built)
    except Exception:
        pass


def rebuild_metrics(overlay, item, is_fidelity: bool, mode_str: str) -> None:
    # Row-container cache: any cached fingerprint swaps in with zero
    # rebuild. Checked FIRST (broader than the W2 memo below: any cached
    # item, not just the exact last one); the W2 single-fingerprint
    # early-return stays as the fast path for exact revisits.
    try:
        _mfp_now = _metrics_fingerprint(overlay, item, is_fidelity, mode_str)
    except Exception:
        _mfp_now = ()
    if _mfp_now:
        try:
            _cache_now = getattr(overlay, "_metrics_row_cache", None)
            if isinstance(_cache_now, dict) and _mfp_now in _cache_now:
                if _metrics_cache_hit(overlay, _mfp_now, _cache_now):
                    return
        except Exception:
            pass
    # Memo skip: rows already show this exact item/series/theme/scale state
    # (they are recreated deterministically from it), so rebuilding would
    # produce identical widgets. Any input change falls through to today's
    # rebuild bit-for-bit.
    if _mfp_now:
        try:
            _mfp_stored = getattr(overlay, "_metrics_fingerprint", None)
            _rows = getattr(overlay, "_metric_rows", None) or []
            if _mfp_stored == _mfp_now and len(_rows):
                return
        except Exception:
            pass
    # Full rebuild: drop the stored fingerprint first so a mid-rebuild
    # failure can never leave a stale match behind (fail-open).
    try:
        overlay._metrics_fingerprint = None
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.quick_look.helpers import _make_label
    except Exception:
        from sli_ui_toolkit.widgets import Label as _Label

        def _make_label(text="", parent=None, pixel_size=10, pt=None, **kwargs):  # type: ignore
            return _Label(text, pixel_size=pixel_size, parent=parent, **kwargs)

    # Rows live flat in right_lay (see helpers.relayout_report_rows); the
    # report host is their visible ancestor (falls back to parentless for
    # bare stubs like the truth-test harness, which only reads _metric_rows).
    # Miss: detach the currently shown set (it stays cached, hidden) instead
    # of destroying it; uncached rows are destroyed as before. The builders
    # below then run bit-for-bit as today into a fresh _metric_rows.
    try:
        _miss_shown = getattr(overlay, "_metrics_shown_key", None)
    except Exception:
        _miss_shown = None
    try:
        _miss_cache = getattr(overlay, "_metrics_row_cache", None)
    except Exception:
        _miss_cache = None
    _miss_keep = False
    try:
        _miss_cur = list(getattr(overlay, "_metric_rows", None) or [])
        _miss_cached = list((_miss_cache.get(_miss_shown) or []) if isinstance(_miss_cache, dict) and _miss_shown is not None else [])
        _miss_keep = bool(_miss_cur) and len(_miss_cur) == len(_miss_cached) and all(c is k for c, k in zip(_miss_cur, _miss_cached))
    except Exception:
        _miss_keep = False
    host = getattr(overlay, "_report_host", None)
    lay = getattr(overlay, "_right_lay", None)
    for w in list(overlay._metric_rows):
        try:
            if lay is not None:
                lay.removeWidget(w)
            if _miss_keep:
                w.hide()
            else:
                # Hide before orphaning (stillborn-toplevel guard).
                w.hide()
                w.setParent(None)
                w.deleteLater()
        except Exception:
            pass
    overlay._metric_rows.clear()
    metrics = getattr(item, "metrics", None) or {}
    if not isinstance(metrics, dict):
        metrics = {}
    def _titled(label: str, spec_id: str, score: int) -> str:
        # Local band descriptor only. The VLM does not own per-axis notes
        # (plan-gallery-ai-quality UX contract): its read lives in the AI
        # block (verdict/reason/defect chips), never on a measured row — so
        # the row reads as one measured answer, not two competing systems.
        note = _fallback_note(spec_id, score)
        return f"{label} — {note}" if note else label

    def _add_metric_row(title: str, value_text: str, fraction: float, color=None, value_color=None, value_elide: bool = True) -> None:
        row = QWidget(host)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(scaled_px(2))  # W5: fit budget (helpers outer note)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scaled_px(6))
        t = _make_label(title, parent=row, pixel_size=11, pt=11.5)
        header.addWidget(t)
        # W7: no spacer here — the value below is horizontal-Ignored (it
        # contributes no sizeHint so the min-296px column never h-scrolls) and
        # an Ignored label beside a spacer would collapse to its 40px
        # minimum and elide EVERYTHING ("+0…"). The value takes the free
        # row width via stretch and end-aligns per the mockup (svg:84
        # text-anchor=end); it elides only when the title genuinely
        # leaves no room.
        vc = _ok_color() if value_color is None else value_color
        if value_elide:
            v = _make_label(value_text, parent=row, pixel_size=11, pt=11.5, color=vc, elide=True, minimum_width=40)
        else:
            v = _make_label(value_text, parent=row, pixel_size=11, pt=11.5, color=vc)
        try:
            v.setAlignment(Qt.AlignmentFlag.AlignRight)
        except Exception:
            pass
        header.addWidget(v, 1)
        rl.addLayout(header)
        # Lazy import bar widget
        from tabs.image_gallery.ui.quick_look.bars import _BarWidget

        bar = _BarWidget(fraction=fraction, fill_color=color, parent=row)
        rl.addWidget(bar)
        overlay._metric_rows.append(row)

    def _ok_color():
        # NOTE: was #3fbf5f (dark-only) — now gallery.status.ok light/dark chain.
        return _token_qcolor("gallery.status.ok", "#2e7d32", "#43a047")

    def _warn_color():
        # NOTE: was #e8b64c (dark-only) — now gallery.status.warn light/dark chain.
        return _token_qcolor("gallery.status.warn", "#b77900", "#d9a441")

    def _bad_color():
        # NOTE: was dark-only reds before — now gallery.status.danger light/dark chain.
        return _token_qcolor("gallery.status.danger", "#c0392b", "#d64545")

    def _muted_color():
        return _token_qcolor("gallery.status.neutral", "#8a8a8a")

    def _add_unmeasured_row(title: str) -> None:
        """Unmeasured state: an explicit 'not measured' row, never a plausible
        constant. Fabricated values (0.94 SSIM, 120 sharpness, …) made missing
        data look measured; gaps must read as gaps. The value is a fixed
        short constant that always fits the column, so it skips elision
        (W5: keeps .text() verbatim for readers that match on it)."""
        _add_metric_row(title, "— · not measured", 0.0, _muted_color(), value_color=_muted_color(), value_elide=False)

    # Canonical scores drive both the text and the bar: every metric reads
    # as "NN%" where higher is always better (see services.metric_scores).
    from tabs.image_gallery.services.metric_scores import (
        fallback_note as _fallback_note,
        raw_for as _raw_for,
        score_band as _score_band,
        score_for as _score_for,
        spec_for as _spec_for,
    )

    def _band_color(score: int):
        band = _score_band(score)
        if band == "good":
            return _ok_color()
        if band == "bad":
            return _bad_color()
        return _warn_color()

    def _add_score_row(spec_id: str, *, extra: str = "", gap: bool = True) -> bool:
        """One measured metric as ``NN%`` (+ optional suffix). A missing
        measurement stays an explicit gap row when ``gap`` (matching the
        historical per-metric behavior: noise/WB hide instead). Returns
        True when measured."""
        spec = _spec_for(spec_id)
        if spec is None:
            return False
        got = _raw_for(spec, metrics)
        if got is None:
            if gap:
                _add_unmeasured_row(spec.label)
            return False
        _key, raw = got
        score = _score_for(spec, raw)
        col = _band_color(score)
        value = f"{score}%" + (f" · {extra}" if extra else "")
        _add_metric_row(_titled(spec.label, spec_id, score), value, score / 100.0, col, value_color=col)
        return True

    if is_fidelity:
        rank = getattr(item, "rank", None) or getattr(item, "crown_rank", None)
        rank_txt = f"#{rank} of {len(overlay._series_items)}" if rank is not None else f"#{overlay._current_idx+1} of {len(overlay._series_items)}"
        _add_score_row("ssim", extra=rank_txt)
        subline = ssim_subline(overlay, item)
        if subline:
            sub_row = QWidget(host)
            sub_lay = QVBoxLayout(sub_row)
            sub_lay.setContentsMargins(0, 0, 0, 0)
            sub_lay.setSpacing(0)
            sub_lay.addWidget(_make_label(subline, parent=sub_row, pixel_size=11, pt=11.0, color_token="list_item.text.rating", elide=True, minimum_width=40))
            overlay._metric_rows.append(sub_row)
        # Detail keeps its dual restored/invented bar (special widget) but the
        # header value is the canonical quality score.
        _spec = _spec_for("detail_gain")
        _hf = _raw_for(_spec, metrics) if _spec is not None else None
        if _hf is None:
            _add_unmeasured_row(_spec.label if _spec is not None else "Detail")
        else:
            _key, hf_f = _hf
            score = _score_for(_spec, hf_f)
            row = QWidget(host)
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(scaled_px(2))  # W5: fit budget (helpers outer note)
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(scaled_px(6))
            t = _make_label(_titled(_spec.label, "detail_gain", score), parent=row, pixel_size=11, pt=11.5)
            header.addWidget(t)
            # W7: value takes free row width via stretch (see _add_metric_row).
            v = _make_label(f"{score}%", parent=row, pixel_size=11, pt=11.5, color=_band_color(score), elide=True, minimum_width=40)
            try:
                v.setAlignment(Qt.AlignmentFlag.AlignRight)
            except Exception:
                pass
            header.addWidget(v, 1)
            rl.addLayout(header)
            from tabs.image_gallery.ui.quick_look.bars import _DualRestoredInventedBar

            dual = _DualRestoredInventedBar(hf_ratio=hf_f, parent=row)
            rl.addWidget(dual)
            sub = QHBoxLayout()
            sub.setContentsMargins(0, 0, 0, 0)
            sub.setSpacing(scaled_px(6))
            lab_l = _make_label("restored texture", parent=row, pixel_size=11, pt=11.0)
            sub.addWidget(lab_l)
            sub.addStretch(1)
            lab_r = _make_label("invented / hallucinated", parent=row, pixel_size=11, pt=11.0)
            sub.addWidget(lab_r)
            rl.addLayout(sub)
            overlay._metric_rows.append(row)
        _add_score_row("color_accuracy")
        # Optional learned perceptual closeness (LPIPS/DISTS): rendered only
        # when the backend is installed (the keys are absent otherwise), so no
        # empty row ever appears.
        if "dists" in metrics:
            _add_score_row("dists", gap=False)
        if "lpips" in metrics:
            _add_score_row("lpips", gap=False)
    elif "CAMERA" in mode_str:
        _add_score_row("sharpness")
        _add_score_row("exposure")
        _add_score_row("clipping")
        # Noise/WB have no "not measured" placeholder by design: when absent
        # the rows simply hide (unchanged historical behavior).
        _add_score_row("noise", gap=False)
        _add_score_row("white_balance", gap=False)
        # Optional no-reference overall quality (BRISQUE) when the learned
        # backend is installed; absent backend adds no row.
        if "brisque" in metrics:
            _add_score_row("brisque", gap=False)
    else:
        _add_score_row("typicality")
        _add_score_row("aesthetic")
    # AI-only Composition axis (no local detector) as a normal row so the
    # block stays text-free — numbers live in rows.
    try:
        _comp = int(getattr(getattr(item, "analysis", None), "composition", -1) or -1)
    except Exception:
        _comp = -1
    if _comp >= 0:
        _ccol = _band_color(_comp)
        _add_metric_row(_titled("Composition", "composition", _comp), f"{_comp}%", _comp / 100.0, _ccol, value_color=_ccol)

    # Flat placement (rows + uniform spacers) is owned by the coordinator —
    # it also re-seats the artifact rows, so either rebuild order converges.
    try:
        from tabs.image_gallery.ui.quick_look.helpers import relayout_report_rows

        relayout_report_rows(overlay)
    except Exception:
        pass
    try:
        overlay._metrics_fingerprint = _mfp_now or _metrics_fingerprint(overlay, item, is_fidelity, mode_str)
    except Exception:
        pass
    # Miss store: a COPY of the container list under the fingerprint (the
    # live list stays the caller's own), then record the shown key so the
    # next hit hides exactly this set. Shown set pinned via the LRU guard.
    try:
        _stored_fp = getattr(overlay, "_metrics_fingerprint", None)
    except Exception:
        _stored_fp = None
    try:
        overlay._metrics_shown_key = _stored_fp
    except Exception:
        pass
    try:
        if _stored_fp and list(getattr(overlay, "_metric_rows", None) or []):
            _metrics_cache_store(overlay, _stored_fp, list(overlay._metric_rows))
    except Exception:
        pass


def ssim_subline(overlay, item) -> str:
    """Build the fidelity SSIM subline from series items (S4-5)."""
    try:
        def _ssim_of(m):
            mt = getattr(m, "metrics", None) or {}
            try:
                return float(mt.get("ssim"))
            except Exception:
                return None

        def _rank_of(m, default):
            r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
            try:
                return int(r) if r is not None else default
            except Exception:
                return default

        parts: list[str] = []
        viewing_rank = _rank_of(item, overlay._current_idx + 1)
        others = [m for m in overlay._series_items if m is not item]
        next_item = None
        best = None
        for m in others:
            r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
            try:
                r = int(r) if r is not None else None
            except Exception:
                r = None
            if r is not None and r > viewing_rank:
                if next_item is None or r < next_item[0]:
                    next_item = (r, m)
            if r is not None and (best is None or r < best[0]):
                best = (r, m)
        pick = next_item if next_item is not None else best
        if pick is not None:
            s = _ssim_of(pick[1])
            if s is not None:
                parts.append(f"#{pick[0]} scores {s:.2f}")
        rejected = [m for m in others if bool(getattr(m, "rejected", False))]
        tail = [v for v in (_ssim_of(m) for m in rejected) if v is not None]
        if tail:
            parts.append(f"rejected tail ≤ {min(tail):.2f}")
        return " · ".join(parts)
    except Exception:
        return ""
