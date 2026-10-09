"""Quick look filename meta + brief — plain functions (no owner state).

Meta line (dims via ``_fast_image_size`` + metrics cache), upscale suffix,
VLM brief with deterministic local ``vs #N`` fallback. Extracted verbatim
from ``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.ui.quick_look.headers import series_size_note
from tabs.image_gallery.ui.quick_look.preview import _fast_image_size, _source_dimensions


def populate_filename_meta(overlay, item, is_fidelity: bool, owner=None) -> None:
    """Filename + dims/format/size meta line (sidebar top row).

    S4 mockup meta order: dims · format · size (+ upscale suffix), then the
    series size note (``same size WxH`` / ``mixed sizes`` / upscales label
    for multi-item series). *owner* is the explicit triage owner (threaded
    from the overlay's ``show_for``); None keeps the overlay fallback
    inside ``_item_smaller_than_source`` for direct unit calls."""
    try:
        overlay._filename_label.setText(str(getattr(item, "name", Path(getattr(item, "path", "")).name)))
    except Exception:
        pass
    try:
        # S4 mockup meta order: dims · format · size (+ upscale suffix).
        # Perf: dims via QImageReader.size (no full decode) + metrics cache.
        dims_txt: str | None = None
        fmt_txt: str | None = None
        size_txt: str | None = None
        upscale_n = None
        p = Path(getattr(item, "path", ""))
        try:
            if p.is_file():
                sz = p.stat().st_size
                if sz < 1024:
                    size_txt = f"{sz} B"
                elif sz < 1024 * 1024:
                    size_txt = f"{sz/1024:.1f} KB"
                else:
                    size_txt = f"{sz/1024/1024:.1f} MB"
                fmt_txt = p.suffix.lstrip(".").upper() or "IMG"
            dims = None
            try:
                metrics_pre = getattr(item, "metrics", None)
                if isinstance(metrics_pre, dict) and metrics_pre.get("width") and metrics_pre.get("height"):
                    dims = (int(metrics_pre["width"]), int(metrics_pre["height"]))
            except Exception:
                dims = None
            if dims is None:
                dims = _fast_image_size(p)
                if dims is not None:
                    try:
                        metrics_pre = getattr(item, "metrics", None)
                        if isinstance(metrics_pre, dict):
                            metrics_pre.setdefault("width", dims[0])
                            metrics_pre.setdefault("height", dims[1])
                    except Exception:
                        pass
            if dims is not None:
                dims_txt = f"{dims[0]} × {dims[1]}"
        except Exception:
            pass
        metrics = getattr(item, "metrics", None) or {}
        if isinstance(metrics, dict) and metrics.get("upscale_factor"):
            try:
                upscale_n = int(metrics.get("upscale_factor"))
            except Exception:
                upscale_n = None
        meta_parts = [t for t in (dims_txt, fmt_txt, size_txt) if t]
        if is_fidelity and overlay._source_path is not None:
            if upscale_n is not None and upscale_n > 1:
                meta_parts.append(f"upscale ×{upscale_n} from source")
            elif upscale_n == 1:
                # W4 item 7: explicit same-size text when truly ×1.
                # W5: factor 1 also covers item-smaller-than-source (the
                # max(1, ...) clamp) — only claim "same size" when the
                # item is not genuinely smaller; else say so honestly.
                # Falls back to the old text whenever either side's dims
                # are unknown (never a fabricated comparison).
                if _item_smaller_than_source(overlay, dims_txt, owner):
                    meta_parts.append("smaller than source")
                else:
                    meta_parts.append("same size as source")
            else:
                meta_parts.append("upscale from source")
        elif upscale_n is not None and upscale_n > 1:
            meta_parts.append(f"upscale ×{upscale_n}")
        try:
            _series_note = series_size_note(overlay)
        except Exception:
            _series_note = ""
        if _series_note:
            meta_parts.append(_series_note)
        overlay._meta_label.setText(" · ".join(meta_parts))
    except Exception:
        pass


def _item_smaller_than_source(overlay, dims_txt: str | None, owner=None) -> bool:
    """True only when the item's long side is known-smaller than the source's.

    Compares the already-formatted item dims (``"W × H"``) against
    ``_source_dimensions`` (metrics first, QPixmap fallback). False on any
    unknown side — callers keep the neutral text instead of guessing.

    *owner* is the explicit triage owner (threaded from the overlay's
    ``show_for``); when None, falls back to the overlay's stored owner for
    direct unit calls (back-compat — production always passes it).
    """
    try:
        if not dims_txt or "×" not in dims_txt:
            return False
        iw, ih = (int(p.strip()) for p in dims_txt.split("×"))
        src = getattr(overlay, "_source_path", None)
        src_item = None
        try:
            if owner is None:
                try:
                    owner = overlay._owner
                except Exception:
                    owner = None
            items = list(getattr(getattr(owner, "state", None), "items", []) or [])
            if src is not None:
                for it2 in items:
                    if Path(getattr(it2, "path", "")) == Path(src):
                        src_item = it2
                        break
        except Exception:
            pass
        sdims = _source_dimensions(src_item, src)
        if sdims is None:
            return False
        return max(iw, ih) < max(sdims[0], sdims[1])
    except Exception:
        return False


def local_brief_fallback(item, series_items) -> str:
    """Deterministic ``vs #N`` brief from local metrics when VLM is absent.

    Same shape as the mockup teaser (``vs #2: …``) but every number comes
    from ``item.metrics`` — no invented detail, no region claims. Returns ""
    when there is nothing comparative to say (caller hides the label).
    """
    try:
        mates = [m for m in (series_items or []) if m is not item]
        if not mates:
            return ""

        def _rank_of(m, default):
            r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
            try:
                return int(r) if r is not None else default
            except Exception:
                return default

        viewing_rank = _rank_of(item, 0)
        other = None
        other_rank = None
        for m in mates:
            r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
            try:
                r = int(r) if r is not None else None
            except Exception:
                r = None
            if r is not None and r > viewing_rank and (other_rank is None or r < other_rank):
                other, other_rank = m, r
        if other is None:
            # No worse-ranked mate: fall back to the best-ranked other.
            best = None
            for m in mates:
                r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
                try:
                    r = int(r) if r is not None else None
                except Exception:
                    r = None
                if r is not None and (best is None or r < best[0]):
                    best = (r, m)
            if best is not None:
                other_rank, other = best
            else:
                other, other_rank = mates[0], _rank_of(mates[0], 2)

        def _f(metrics, *keys):
            for k in keys:
                v = metrics.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except Exception:
                        continue
            return None

        ma = getattr(item, "metrics", None) or {}
        mb = getattr(other, "metrics", None) or {}
        if not isinstance(ma, dict):
            ma = {}
        if not isinstance(mb, dict):
            mb = {}
        ssim_a, ssim_b = _f(ma, "ssim"), _f(mb, "ssim")
        hf_a = _f(ma, "hf_ratio", "detail_gain")
        hf_b = _f(mb, "hf_ratio", "detail_gain")
        if ssim_a is None and ssim_b is None and hf_a is None and hf_b is None:
            return ""
        clauses: list[str] = []
        if ssim_a is not None and ssim_b is not None:
            clauses.append(f"SSIM {ssim_a:.2f} vs {ssim_b:.2f}")
        elif ssim_a is not None:
            clauses.append(f"SSIM {ssim_a:.2f}")
        if hf_a is not None and hf_b is not None:
            clauses.append(f"detail {int(hf_a * 100):+d}% vs {int(hf_b * 100):+d}%")
        elif hf_a is not None:
            clauses.append(f"detail {int(hf_a * 100):+d}%")
        # Banding note for the *other* item only, severity-only (no regions).
        banding = None
        try:
            raw = getattr(other, "artifacts", None)
            if isinstance(raw, dict):
                from tabs.image_gallery.models import Artifact as _Artifact

                sev = raw.get(_Artifact.BANDING, raw.get("banding"))
                banding = (sev.value if hasattr(sev, "value") else sev)
            if banding is None and isinstance(mb, dict):
                artm = mb.get("artifacts")
                if isinstance(artm, dict):
                    banding = artm.get("banding", artm.get("BANDING"))
                    banding = banding.value if hasattr(banding, "value") else banding
        except Exception:
            banding = None
        try:
            banding = str(banding).lower() if banding is not None else None
        except Exception:
            banding = None
        tail = ""
        if banding in ("mild", "flagged"):
            tail = f"#{other_rank} shows banding" + (" (flagged)" if banding == "flagged" else "")
        head = " · ".join(clauses)
        text = f"vs #{other_rank}: {head}" if head else f"vs #{other_rank}"
        if tail:
            text += f"; {tail}"
        return text
    except Exception:
        return ""


def populate_brief(overlay, item) -> None:
    try:
        # Fidelity report is decluttered: no bottom "vs #N" brief at all —
        # the metric rows already carry the comparison (the source included).
        # Batch (no source) keeps the brief.
        try:
            if getattr(overlay, "_source_path", None) is not None:
                overlay._brief_label.setText("")
                overlay._brief_label.setVisible(False)
                div = getattr(overlay, "_div_series", None)
                if div is not None:
                    div.setVisible(False)
                return
        except Exception:
            pass
        brief = ""
        vlm_brief = getattr(item, "vlm_brief", None)
        status = getattr(item, "vlm_brief_status", "none")
        if vlm_brief is not None:
            try:
                summary = getattr(vlm_brief, "summary", "") or ""
                diffs = getattr(vlm_brief, "differences", ()) or ()
                if summary:
                    brief = summary
                    if diffs:
                        brief += " — " + "; ".join(list(diffs)[:2])
                else:
                    brief = "; ".join(list(diffs)[:2]) if diffs else ""
                if status == "pending":
                    brief = "AI brief…"
            except Exception:
                brief = ""
            if not brief and status == "pending":
                brief = "AI brief…"
        if not brief:
            # Deterministic local fallback (no VLM): vs-#N from metrics.
            try:
                brief = local_brief_fallback(item, getattr(overlay, "_series_items", []))
            except Exception:
                brief = ""
        if brief:
            overlay._brief_label.setText(brief)
            overlay._brief_label.setVisible(True)
        else:
            overlay._brief_label.setText("")
            overlay._brief_label.setVisible(False)
        # The section divider belongs to the brief block: an empty brief
        # with a dangling rule reads as two dividers in a row next to the
        # analysis divider below.
        try:
            div = getattr(overlay, "_div_series", None)
            if div is not None:
                div.setVisible(bool(brief))
        except Exception:
            pass
    except Exception:
        try:
            overlay._brief_label.setVisible(False)
        except Exception:
            pass
        try:
            div = getattr(overlay, "_div_series", None)
            if div is not None:
                div.setVisible(False)
        except Exception:
            pass


def _defect_chips(defects) -> str:
    """Compact defect chips: 'kind (severity)' joined by ' · '.

    The free-text per-defect note is deliberately NOT shown — the model
    only repeated the measured metrics with it; the chip is the signal.
    """
    out = []
    try:
        for d in defects or ():
            kind = str(getattr(d, "kind", "") or "").replace("_", " ").strip()
            if not kind:
                continue
            sev = str(getattr(d, "severity", "") or "").strip()
            out.append(f"{kind} ({sev})" if sev else kind)
    except Exception:
        return ""
    return " · ".join(out)


def populate_analysis(overlay, item) -> None:
    """Fill the sidebar AI-analysis block (quality verdict + defects).

    The model output lives here, not in the card tooltip. DONE shows a
    compact structured line (verdict · Composition · confidence), then a
    PRACTICAL conclusion (reason: what the processing did, whether the
    result is usable, what to watch — no metric restatement), then defect
    chips (kind · severity). Sharpness/noise/exposure are NOT repeated —
    the metric rows above carry the measured values.
    Legacy caption-only cache entries fall back to the plain description.
    PENDING shows a running line; ERROR shows the error and keeps the
    Analyze trigger for retry; NOT_ANALYZED shows the header + trigger
    only. A disk-cached analysis is hydrated first (via the owner hook),
    so the block shows it the moment the overlay opens instead of waiting
    for an Analyze click. Never raises.
    """
    try:
        try:
            if getattr(item, "analysis", None) is None:
                owner = getattr(overlay, "_owner", None)
                hydrate = getattr(owner, "hydrate_cached_analysis", None)
                if callable(hydrate):
                    hydrate(item)
        except Exception:
            pass
        try:
            _st = getattr(item, "analysis_status", None)
            status_val = str(getattr(_st, "value", _st) or "")
        except Exception:
            status_val = ""
        try:
            analysis = getattr(item, "analysis", None)
        except Exception:
            analysis = None
        try:
            err = getattr(item, "analysis_error", None)
        except Exception:
            err = None
        desc_text, tags_text = "", ""
        show_btn = False
        verdict_text, verdict_color = "", None
        if analysis is not None and status_val == "done":
            show_btn = True
            try:
                verdict = str(getattr(analysis, "verdict", "unknown") or "unknown")
                reason = str(getattr(analysis, "verdict_reason", "") or "")
                defects = list(getattr(analysis, "defects", ()) or ())
                legacy_desc = str(getattr(analysis, "description", "") or "")
            except Exception:
                verdict, reason, defects, legacy_desc = "unknown", "", [], ""
            defects_text = _defect_chips(defects)
            # No summary line: verdict is a colored badge in the header, the
            # body is the practical conclusion, the chips are the defects.
            # Numbers (Composition) live in the metric rows, not here.
            if verdict in ("keep", "reject"):
                verdict_text = verdict.upper()
                try:
                    from tabs.image_gallery.ui.quick_look.helpers import _token_color as _tc

                    verdict_color = _tc(
                        "gallery.status.ok" if verdict == "keep" else "gallery.status.danger",
                        "#2e7d32" if verdict == "keep" else "#c0392b",
                    )
                except Exception:
                    verdict_color = None
                desc_text = reason
                tags_text = defects_text
            elif defects or reason:
                desc_text = reason
                tags_text = defects_text
            else:
                # Legacy caption-only cache entry: show the description.
                desc_text = legacy_desc
        elif status_val == "pending":
            desc_text = "Analyzing…"
        elif status_val == "error":
            desc_text = str(err or "Analysis failed.")
            show_btn = True
        else:
            # NOT_ANALYZED (or unknown): header + trigger only.
            show_btn = True
        try:
            div = getattr(overlay, "_div_analysis", None)
            if div is not None:
                div.setVisible(True)
        except Exception:
            pass
        try:
            head = getattr(overlay, "_analysis_head", None)
            if head is not None:
                head.setVisible(True)
        except Exception:
            pass
        try:
            vlabel = getattr(overlay, "_analysis_verdict", None)
            if vlabel is not None:
                if verdict_text:
                    vlabel.setText(verdict_text)
                    if verdict_color is not None:
                        try:
                            vlabel.setTextColor(verdict_color)
                        except Exception:
                            pass
                    vlabel.setVisible(True)
                else:
                    vlabel.setText("")
                    vlabel.setVisible(False)
        except Exception:
            pass
        try:
            btn = getattr(overlay, "_analysis_btn", None)
            if btn is not None:
                btn.setVisible(bool(show_btn))
                # DONE keeps the trigger as Re-analyze (forced re-run);
                # everything else offers the first Analyze.
                want = "Re-analyze" if status_val == "done" else "Analyze"
                try:
                    mode = getattr(overlay, "_analysis_btn_mode", None)
                except Exception:
                    mode = None
                if mode != want:
                    try:
                        from tabs.image_gallery.ui.quick_look.labels_theme import _set_colored_text

                        _set_colored_text(btn, want, None)
                    except Exception:
                        pass
                    try:
                        overlay._analysis_btn_mode = want
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            desc = getattr(overlay, "_analysis_desc", None)
            if desc is not None:
                if desc_text:
                    desc.setText(desc_text)
                    desc.setVisible(True)
                else:
                    desc.setText("")
                    desc.setVisible(False)
        except Exception:
            pass
        try:
            tags_lbl = getattr(overlay, "_analysis_tags", None)
            if tags_lbl is not None:
                if tags_text:
                    tags_lbl.setText(tags_text)
                    tags_lbl.setVisible(True)
                else:
                    tags_lbl.setText("")
                    tags_lbl.setVisible(False)
        except Exception:
            pass
    except Exception:
        pass
