"""Quick Look metric row build + hidden-parent warm.

Split out of the former ``ui/quick_look/metrics.py`` (plan-gallery-split-2026-10-17,
Part C2). Bodies moved verbatim; names/signatures unchanged. ``rebuild_metrics``
and ``warm_metrics_for`` are the only callers of the row-container cache
(``cache.py``) and share its fingerprint contract.
Audit-Meta: pattern=thin-owner-target size=exempt reason="one metric-rows concern: rebuild + hidden-parent warm share the row pipeline over the cache fingerprint contract"
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px

from .cache import (
    _metrics_cache_hit,
    _metrics_cache_store,
    _metrics_fingerprint,
    _mode_str_for,
    _overlay_metric_profile,
    _overlay_mode,
)
from .theme import (
    _metric_label,
    _metric_note,
    _overlay_judgment_domain,
    _ql_text,
    _token_qcolor,
)


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
        # Fallback for harnesses that stub `helpers` (the truth-test harness).
        # Internal module on purpose: the public `widgets.Label` export is being
        # retired (text 2b); this is a fallback, not a production consumer.
        from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label as _Label

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
    # Per-axis read (plan-gallery-analysis-engine-2026-10-20 §P2): the AI domain
    # shows the VLM's scorecard, the Algorithms domain the local detectors, and
    # every axis arrives as an AxisValue carrying its own producer/status/reason
    # from ``analysis.read.read_axes`` — the single implementation behind
    # ``services.quality_read.domain_axis_scores`` (the per-domain seam this
    # surface read before W3). Only ONE domain answers here, so a row is always
    # one answer, never two competing ones; a gap stays a gap (it never borrows
    # the other domain's number), so only ``status == "ok"`` reaches the rows.
    domain = _overlay_judgment_domain(overlay)
    try:
        from tabs.image_gallery.analysis.read import read_axes

        read = {
            record.axis: int(record.value)
            for record in read_axes(item, domain=domain)
            if record.status == "ok"
        }
    except Exception:
        read = {}
    # Raw detector keys drive the Algorithms-domain extras (raw deltas, the dual
    # Detail bar); the AI domain has no raws and never reads them.
    metrics = getattr(item, "metrics", None) or {}
    if not isinstance(metrics, dict):
        metrics = {}
    if domain == "ai":
        metrics = {}

    def _titled(label: str, spec_id: str, score: int) -> str:
        # Localized band descriptor (positive wording), same on both domains.
        note = _metric_note(overlay, spec_id, score)
        return f"{label} — {note}" if note else label

    def _add_metric_row(
        title: str,
        value_text: str,
        fraction: float,
        color=None,
        value_color=None,
        value_elide: bool = True,
        bar: bool = True,
    ) -> None:
        row = QWidget(host)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(scaled_px(6))  # label→bar gap (W5 fit budget checked)
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
        if bar:
            # Lazy import bar widget
            from tabs.image_gallery.ui.quick_look.bars import _BarWidget

            rl.addWidget(_BarWidget(fraction=fraction, fill_color=color, parent=row))
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
        _add_metric_row(
            title,
            _ql_text(overlay, "image_gallery.quick_look.not_measured", "— · not measured"),
            0.0,
            _muted_color(),
            value_color=_muted_color(),
            value_elide=False,
            # No bar for a non-measurement: a 0-fraction bar reads as a value
            # (and its 4px floor is not "0%"). The row stays one honest line.
            bar=False,
        )

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
        """One axis as ``NN%`` from the CURRENT domain's read (+ optional suffix).
        A missing score stays an explicit gap row when ``gap`` (matching the
        historical per-metric behavior: noise/WB hide instead). An axis whose
        spread across the series is inside the instrument's noise floor renders
        as that reason instead of a bare number — the row is KEPT (plan P2/D3:
        "не различает эти варианты"), only its fake authority is gone. Returns
        True when the axis has a row."""
        spec = _spec_for(spec_id)
        if spec is None:
            return False
        if _inside_noise is not None and _salience.get(spec_id) == _inside_noise:
            reason = _ql_text(
                overlay,
                "image_gallery.quick_look.axis_inside_noise",
                "does not separate these variants",
            )
            if extra:
                reason = f"{reason} · {extra}"
            _add_metric_row(
                _metric_label(overlay, spec.id, spec.label),
                reason,
                0.0,
                _muted_color(),
                value_color=_muted_color(),
                value_elide=False,
                # No bar: a fill reads as a value, and this axis ranks nothing.
                bar=False,
            )
            return True
        score = read.get(spec_id)
        if score is None:
            if gap:
                _add_unmeasured_row(_metric_label(overlay, spec.id, spec.label))
            return False
        score = int(score)
        col = _band_color(score)
        value = f"{score}%" + (f" · {extra}" if extra else "")
        _add_metric_row(_titled(_metric_label(overlay, spec_id, spec.label), spec_id, score), value, score / 100.0, col, value_color=col)
        return True

    # The ROW SET is the active metric profile — the same seam the card dots
    # read (``active_profile`` → ``measured_axes_for``), so rows, dots, rank
    # and the AI scorecard cannot disagree about which axes exist (no second
    # axis list here). Registry order is the profile's own order.
    try:
        from tabs.image_gallery.services.rank_fusion import measured_axes_for

        _mode = _overlay_mode(overlay, mode_str)
        _profile = _overlay_metric_profile(overlay, mode_str)
        axes = measured_axes_for(_mode, profile=_profile)
    except Exception:
        _profile = None
        axes = ()
    # P2 salience (plan-gallery-ai-judgement M3): an axis whose spread across
    # THIS series sits inside the judge's noise floor cannot separate these
    # variants, so its row says exactly that instead of showing a number that
    # ranked nothing. The verdict is the SAME one the rank and the Jev vector
    # apply (``axis_salience``), measured from the same domain read the rows
    # render — never a second measurement.
    _salience: dict[str, str] = {}
    _inside_noise = None
    try:
        from tabs.image_gallery.services.rank_fusion import (
            INSIDE_NOISE,
            _inside_noise_axes,
            axis_salience,
        )
        from tabs.image_gallery.services.quality_read import (
            axis_noise_floor,
            domain_axis_scores,
        )

        _series = list(getattr(overlay, "_series_items", None) or [])
        if len(_series) > 1:
            _verdicts = axis_salience(
                [domain_axis_scores(member, domain=domain) for member in _series],
                noise_floor=axis_noise_floor(domain),
            )
            # The rows render the verdict the RANK applies: when the floor cannot
            # separate anything in this series (every axis inside it), the fusion
            # keeps the full set rather than degrading to path order, so the rows
            # keep their numbers too (``_inside_noise_axes`` is that ONE rule).
            _suppressed = _inside_noise_axes(_verdicts)
            if _suppressed:
                _inside_noise = INSIDE_NOISE
                _salience = {
                    axis: verdict
                    for axis, verdict in _verdicts.items()
                    if axis in _suppressed
                }
    except Exception:
        _salience = {}
        _inside_noise = None
    # A VLM-selected profile is a deliberate report request: render exactly
    # its axes, gaps included. The wide mode/heuristic base describes the
    # measurement pool (fidelity alone carries 14 axes); rendering an empty
    # row for every optional detector would flood the no-scroll report, so
    # there only the report's core axes keep their gap row and an unscored
    # optional axis adds no row (the pre-profile rule for noise/WB/LPIPS).
    _exact_rows = str(getattr(_profile, "source", "") or "") == "vlm"

    # A source is the reference, not a variant — comparing it to itself
    # ("Source match 100%", "vs #1") is nonsense. Render a source state.
    _viewing_source = False
    try:
        from pathlib import Path as _P

        _sp = getattr(overlay, "_source_path", None)
        _viewing_source = _sp is not None and _P(getattr(item, "path", "")) == _P(_sp)
    except Exception:
        _viewing_source = False
    # Always-gap axes of each report kind (the historical placeholders): an
    # in-profile axis here stays visible as "— · not measured" even in the
    # compact mode/heuristic report, so a missing measurement never silently
    # disappears. Optional axes keep the "no empty row" rule unless the VLM
    # selected the profile (then the exact axis set is the request).
    _core_axes = ("ssim", "detail_gain", "color_accuracy") if is_fidelity else (
        ("sharpness", "exposure", "clipping") if "CAMERA" in mode_str else ("aesthetic",)
    )
    if is_fidelity and _viewing_source:
        pass  # the source is the reference — no comparison report rows
    elif is_fidelity:
        rank = getattr(item, "rank", None) or getattr(item, "crown_rank", None)
        _rank_n = rank if rank is not None else overlay._current_idx + 1
        rank_txt = _ql_text(
            overlay,
            "image_gallery.quick_look.rank_of",
            "#{rank} of {total}",
            rank=_rank_n,
            total=len(overlay._series_items),
        )
        for axis_id in axes:
            if axis_id == "ssim":
                _add_score_row("ssim", extra=rank_txt)
                subline = ssim_subline(overlay, item) if domain != "ai" else ""
                if subline:
                    sub_row = QWidget(host)
                    sub_lay = QVBoxLayout(sub_row)
                    sub_lay.setContentsMargins(0, 0, 0, 0)
                    sub_lay.setSpacing(0)
                    sub_lay.addWidget(_make_label(subline, parent=sub_row, pixel_size=11, pt=11.0, color_token="list_item.text.rating", elide=True, minimum_width=40))
                    overlay._metric_rows.append(sub_row)
                continue
            if axis_id == "detail_gain":
                # Detail keeps its dual restored/invented bar (special widget)
                # but the header value is the canonical quality score. An axis
                # inside the noise floor has no bar to draw: its row states the
                # reason instead (the dual bar would imply it separates).
                if _inside_noise is not None and _salience.get("detail_gain") == _inside_noise:
                    _add_score_row("detail_gain")
                    continue
                _spec = _spec_for("detail_gain")
                _hf = _raw_for(_spec, metrics) if _spec is not None else None
                if _hf is None:
                    # No raw (the AI domain has none, or Detail is unmeasured)
                    # — the row reads as a normal score/gap row from the read.
                    _add_score_row("detail_gain")
                    continue
                _key, hf_f = _hf
                score = _score_for(_spec, hf_f)
                row = QWidget(host)
                rl = QVBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(scaled_px(6))  # label→bar gap (W5 fit budget checked)
                header = QHBoxLayout()
                header.setContentsMargins(0, 0, 0, 0)
                header.setSpacing(scaled_px(6))
                t = _make_label(
                    _titled(_metric_label(overlay, "detail_gain", _spec.label), "detail_gain", score),
                    parent=row, pixel_size=11, pt=11.5,
                )
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
                lab_l = _make_label(
                    _ql_text(overlay, "image_gallery.ql.restored_texture", "restored texture"),
                    parent=row, pixel_size=11, pt=11.0,
                )
                sub.addWidget(lab_l)
                sub.addStretch(1)
                lab_r = _make_label(
                    _ql_text(overlay, "image_gallery.ql.invented_hallucinated", "invented / hallucinated"),
                    parent=row, pixel_size=11, pt=11.0,
                )
                sub.addWidget(lab_r)
                rl.addLayout(sub)
                overlay._metric_rows.append(row)
                continue
            # Every other profile axis: the canonical score row, with the
            # Algorithms-domain raw delta suffix where one exists. An axis the
            # current domain did not score stays an explicit "not measured"
            # row for the core axes / a VLM-selected profile (never a
            # fabricated value); an unscored optional axis in the wide
            # heuristic report adds no empty row.
            if not _exact_rows and axis_id not in _core_axes and axis_id not in read:
                continue
            _extra = ""
            try:
                if axis_id == "clipping_delta":
                    _extra = f"{float(metrics.get('clipping_delta')):+.2f}%"
                elif axis_id in ("halo_delta", "chroma_fringe_delta"):
                    _extra = f"{float(metrics.get(axis_id)):.1f}×"
            except Exception:
                _extra = ""
            _add_score_row(axis_id, extra=_extra)
    else:
        # Camera / batch reports: the profile's axes, in profile order. No
        # fixed per-mode list — an axis outside the profile never renders.
        # A core axis without a score stays an honest gap row; an optional
        # one is shown only when the current domain scored it (or the VLM
        # selected the exact set).
        for axis_id in axes:
            if not _exact_rows and axis_id not in _core_axes and axis_id not in read:
                continue
            _add_score_row(axis_id)
    # AI-only Composition axis (no local detector, not in MEASURED_POOL) is a
    # VLM judgment: it belongs to the AI domain only, never to the local
    # Algorithms report — there it would be a second, competing answer.
    try:
        _comp = int(getattr(getattr(item, "analysis", None), "composition", -1) or -1)
    except Exception:
        _comp = -1
    if domain == "ai" and _comp >= 0:
        _ccol = _band_color(_comp)
        _add_metric_row(
            _titled(_metric_label(overlay, "composition", "Composition"), "composition", _comp),
            f"{_comp}%", _comp / 100.0, _ccol, value_color=_ccol,
        )

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
    """Build the fidelity SSIM subline: the rejected tail's ceiling (S4-5).

    The old "#N scores X" part named another series member and restated an
    SSIM the rows already show — dropped (declutter).
    """
    try:
        def _ssim_of(m):
            mt = getattr(m, "metrics", None) or {}
            try:
                return float(mt.get("ssim"))
            except Exception:
                return None

        parts: list[str] = []
        others = [m for m in overlay._series_items if m is not item]
        rejected = [m for m in others if bool(getattr(m, "rejected", False))]
        tail = [v for v in (_ssim_of(m) for m in rejected) if v is not None]
        if tail:
            parts.append(
                _ql_text(
                    overlay,
                    "image_gallery.quick_look.rejected_tail",
                    "rejected tail ≤ {value}",
                    value=f"{min(tail):.2f}",
                )
            )
        return " · ".join(parts)
    except Exception:
        return ""
