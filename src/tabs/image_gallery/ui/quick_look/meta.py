"""Quick look filename meta + brief — plain functions (no owner state).

Meta line (dims via ``_fast_image_size`` + metrics cache), upscale suffix,
VLM brief with deterministic local ``vs #N`` fallback. Extracted verbatim
from ``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.ui.quick_look.preview import _fast_image_size, _source_dimensions


def populate_filename_meta(overlay, item, is_fidelity: bool) -> None:
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
                if _item_smaller_than_source(overlay, dims_txt):
                    meta_parts.append("smaller than source")
                else:
                    meta_parts.append("same size as source")
            else:
                meta_parts.append("upscale from source")
        elif upscale_n is not None and upscale_n > 1:
            meta_parts.append(f"upscale ×{upscale_n}")
        overlay._meta_label.setText(" · ".join(meta_parts))
    except Exception:
        pass


def _item_smaller_than_source(overlay, dims_txt: str | None) -> bool:
    """True only when the item's long side is known-smaller than the source's.

    Compares the already-formatted item dims (``"W × H"``) against
    ``_source_dimensions`` (metrics first, QPixmap fallback). False on any
    unknown side — callers keep the neutral text instead of guessing.
    """
    try:
        if not dims_txt or "×" not in dims_txt:
            return False
        iw, ih = (int(p.strip()) for p in dims_txt.split("×"))
        src = getattr(overlay, "_source_path", None)
        src_item = None
        try:
            owner = getattr(overlay, "_owner", None)
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
    except Exception:
        try:
            overlay._brief_label.setVisible(False)
        except Exception:
            pass
