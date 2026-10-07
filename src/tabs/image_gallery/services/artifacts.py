"""Stage 2 artifact catalog — 7 local detectors + severity.
Audit-Meta: pattern=tiled-pipeline size=679 reason="7 pure detectors sharing PIL/numpy helpers + source-anchor delta — single catalog lifecycle"

Pure PIL/numpy, no Qt (so workers can run off the main thread and tests
stay headless).  Each detector is a pure function:

    detect_{artifact}(pil_image, source_image=None) -> Severity

Heuristics are intentionally simple — histogram / Laplacian / DCT-ish /
gradient approximations — and only need to be directionally correct for
the triage pipeline (warm/red dots + quick look report). When a source is
available, the absolute detectors are anchored to it (see ``_ANCHORED`` /
``_anchor_severity``): only a severity worse than the source's own counts,
so a constant content bias cancels in the delta.

Public API:
    Severity enum  — clean / mild / flagged
    Artifact enum  — 7 catalog entries
    detect_banding, detect_halo, detect_over_smoothing,
    detect_invented_texture, detect_blocking,
    detect_chroma_fringing, detect_noise_amplification
    analyze_artifacts(path, source_path=None) -> dict[Artifact, Severity]
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

# Re-use Severity/Artifact from models when available so controller/widget
# see the same Enum class (no Qt at import time — models guards QPixmap
# behind TYPE_CHECKING).
try:
    from tabs.image_gallery.models import Artifact as _ModelArtifact  # type: ignore
    from tabs.image_gallery.models import Severity as _ModelSeverity  # type: ignore

    Severity = _ModelSeverity  # type: ignore[no-redef,assignment]
    Artifact = _ModelArtifact  # type: ignore[no-redef,assignment]
except Exception:  # pragma: no cover — fallback when models not importable

    class Severity(str, Enum):
        CLEAN = "clean"
        MILD = "mild"
        FLAGGED = "flagged"

    class Artifact(str, Enum):
        BANDING = "banding"
        HALO = "halo"
        OVER_SMOOTHING = "over_smoothing"
        INVENTED_TEXTURE = "invented_texture"
        BLOCKING = "blocking"
        CHROMA_FRINGING = "chroma_fringing"
        NOISE_AMPLIFICATION = "noise_amplification"

# Backwards compat aliases for enum members as lowercase values.
# str Enum already allows value compare, but expose lowercase helpers.
_SEV_CLEAN = Severity.CLEAN if hasattr(Severity, "CLEAN") else Severity("clean")  # type: ignore
_SEV_MILD = Severity.MILD if hasattr(Severity, "MILD") else Severity("mild")  # type: ignore
_SEV_FLAGGED = Severity.FLAGGED if hasattr(Severity, "FLAGGED") else Severity("flagged")  # type: ignore

_SEV_RANK = {_SEV_CLEAN: 0, _SEV_MILD: 1, _SEV_FLAGGED: 2}

# Absolute (no-reference) detectors carry a constant content bias — crisp cel
# art reads as "halo", a clean sky can read as "banding". A gallery compares
# variants of the SAME source, so that bias is identical across variants and
# cancels in the delta. When a source image is available these four are
# anchored: only a severity *worse than the source's own* counts. The three
# source-relative detectors (over_smoothing / invented_texture /
# noise_amplification) already compare against the source — never anchor them.
_ANCHORED: tuple = (
    Artifact.BANDING,
    Artifact.HALO,
    Artifact.BLOCKING,
    Artifact.CHROMA_FRINGING,
)


def _coerce_severity(value) -> "Severity":
    """Normalize a detector return (Enum or plain str) to ``Severity``."""
    if isinstance(value, str):
        try:
            return Severity(value.lower())  # type: ignore[call-arg]
        except Exception:
            return _SEV_CLEAN
    return value if value in _SEV_RANK else _SEV_CLEAN


def _anchor_severity(cand, source) -> "Severity":
    """Candidate severity relative to the source's own severity (the delta).

    ``cand == source`` (self-pair) ⇒ ``clean``: a constant content bias cannot
    manufacture an artifact. Only a candidate genuinely worse than its source
    flags (one level worse ⇒ ``mild``, two+ ⇒ ``flagged``).
    """
    delta = _SEV_RANK.get(_coerce_severity(cand), 0) - _SEV_RANK.get(_coerce_severity(source), 0)
    if delta >= 2:
        return _SEV_FLAGGED
    if delta == 1:
        return _SEV_MILD
    return _SEV_CLEAN

# ---------------------------------------------------------------------------
# numpy helpers — imported lazily so the module still imports on systems
# without numpy (detectors will then return CLEAN).
# ---------------------------------------------------------------------------

def _np():
    try:
        import numpy as np  # type: ignore

        return np
    except Exception:
        return None


def _to_gray_array(im: Image.Image, max_edge: int = 512):
    """Return float32 grayscale array 0..255, downscaled for speed."""
    np = _np()
    if np is None:
        return None
    try:
        # Downscale large images to bound work.
        w, h = im.size
        max_e = max(w, h)
        if max_e > max_edge:
            scale = max_edge / max_e
            nw, nh = int(w * scale), int(h * scale)
            try:
                resample = Image.Resampling.BILINEAR  # type: ignore[attr-defined]
            except AttributeError:
                resample = Image.BILINEAR  # type: ignore
            im = im.resize((max(nw, 1), max(nh, 1)), resample)
        gray = im.convert("L")
        arr = np.asarray(gray, dtype=np.float32)
        return arr
    except Exception:
        return None


def _to_rgb_arrays(im: Image.Image, max_edge: int = 512):
    """Return tuple of R,G,B float32 arrays or None."""
    np = _np()
    if np is None:
        return None
    try:
        w, h = im.size
        max_e = max(w, h)
        if max_e > max_edge:
            scale = max_edge / max_e
            nw, nh = int(w * scale), int(h * scale)
            try:
                resample = Image.Resampling.BILINEAR  # type: ignore[attr-defined]
            except AttributeError:
                resample = Image.BILINEAR  # type: ignore
            im = im.resize((max(nw, 1), max(nh, 1)), resample)
        rgb = im.convert("RGB")
        arr = np.asarray(rgb, dtype=np.float32)  # HxWx3
        if arr.ndim != 3 or arr.shape[2] != 3:
            return None
        return arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    except Exception:
        return None


def _laplacian(arr):
    """Laplacian 4-neighbour kernel [[0,1,0],[1,-4,1],[0,1,0]]."""
    np = _np()
    if np is None or arr is None:
        return None
    try:
        h, w = arr.shape
        if h < 3 or w < 3:
            return np.zeros_like(arr)
        lap = np.zeros_like(arr, dtype=np.float32)
        # Vectorised inner region.
        lap[1:-1, 1:-1] = arr[0:-2, 1:-1] + arr[2:, 1:-1] + arr[1:-1, 0:-2] + arr[1:-1, 2:] - 4.0 * arr[1:-1, 1:-1]
        return lap
    except Exception:
        return None


def _hf_energy(arr) -> float:
    """High-frequency energy as mean absolute Laplacian."""
    np = _np()
    if np is None or arr is None:
        return 0.0
    try:
        lap = _laplacian(arr)
        if lap is None:
            return 0.0
        # Use inner region only to avoid border zeros.
        inner = lap[1:-1, 1:-1] if lap.shape[0] >= 3 and lap.shape[1] >= 3 else lap
        return float(np.mean(np.abs(inner)))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def detect_banding(pil_image: Image.Image, source_image: Image.Image | None = None) -> Severity:
    """Banding — comb spikes in gradient histogram (sky/gradients).

    Heuristic: histogram of luma values inside a smooth-gradient image
    should be densely filled. Banding/posterization leaves many zero bins
    between min..max (“comb”).
    """
    try:
        arr = _to_gray_array(pil_image)
        np = _np()
        if arr is None or np is None:
            return _SEV_CLEAN
        # Histogram 256 bins for 0..255.
        hist, _ = np.histogram(arr, bins=256, range=(0, 255))
        # Find occupied range.
        nonzero = np.where(hist > 0)[0]
        if len(nonzero) < 2:
            return _SEV_CLEAN
        lo, hi = int(nonzero[0]), int(nonzero[-1])
        span = hi - lo + 1
        if span < 16:
            return _SEV_CLEAN
        inner_hist = hist[lo : hi + 1]
        zero_bins = int(np.sum(inner_hist == 0))
        zero_ratio = zero_bins / float(span)
        # Also inspect gradient histogram sparsity: quantized gradients
        # produce sparse diff histogram.
        try:
            # Horizontal diffs.
            dh = np.abs(np.diff(arr, axis=1)).ravel()
            # Histogram of diffs 0..50 (banding shows quantized steps).
            dh_hist, _ = np.histogram(dh, bins=32, range=(0, 32))
            # Count how many bins are zero inside occupied span.
            dh_nz = np.where(dh_hist > 0)[0]
            if len(dh_nz) >= 4:
                dh_lo, dh_hi = int(dh_nz[0]), int(dh_nz[-1])
                dh_span = dh_hi - dh_lo + 1
                dh_zero = int(np.sum(dh_hist[dh_lo : dh_hi + 1] == 0))
                dh_zero_ratio = dh_zero / float(dh_span) if dh_span else 0.0
                # Combine: max of zero ratios.
                zero_ratio = max(zero_ratio, dh_zero_ratio * 0.9)
        except Exception:
            pass
        # thresholds derived empirically: uniform gradients ~0.05, banded >0.35
        if zero_ratio >= 0.45:
            return _SEV_FLAGGED
        if zero_ratio >= 0.25:
            return _SEV_MILD
        return _SEV_CLEAN
    except Exception:
        return _SEV_CLEAN


def detect_halo(pil_image: Image.Image, source_image: Image.Image | None = None) -> Severity:
    """Halo / edge overshoot — gradient overshoot ratio at strong edges.

    Oversharpening produces bright/dark halos near strong edges:
    Laplacian magnitude spikes near high-gradient pixels.
    """
    try:
        arr = _to_gray_array(pil_image)
        np = _np()
        if arr is None or np is None:
            return _SEV_CLEAN
        h, w = arr.shape
        if h < 8 or w < 8:
            return _SEV_CLEAN
        # Gradient magnitude via abs diff.
        gx = np.zeros_like(arr)
        gy = np.zeros_like(arr)
        gx[:, :-1] = np.abs(arr[:, 1:] - arr[:, :-1])
        gy[:-1, :] = np.abs(arr[1:, :] - arr[:-1, :])
        grad = np.maximum(gx, gy)
        # Strong edge mask: top 8% of gradient.
        try:
            thr = float(np.percentile(grad, 92))
        except Exception:
            thr = 30.0
        thr = max(thr, 18.0)
        edge_mask = grad >= thr
        edge_count = int(np.sum(edge_mask))
        if edge_count < 20:
            return _SEV_CLEAN
        lap = _laplacian(arr)
        if lap is None:
            return _SEV_CLEAN
        # Dilate edge mask 1px to include halo ring.
        # Approximate dilation by OR with shifted copies (numpy).
        try:
            dilated = np.copy(edge_mask)
            dilated[1:, :] |= edge_mask[:-1, :]
            dilated[:-1, :] |= edge_mask[1:, :]
            dilated[:, 1:] |= edge_mask[:, :-1]
            dilated[:, :-1] |= edge_mask[:, 1:]
            # Ring = dilated & ~edge_mask
            ring = dilated & (~edge_mask)
            ring_count = int(np.sum(ring))
            if ring_count < 10:
                return _SEV_CLEAN
            # Overshoot ratio: mean |lap| in ring vs edge.
            mean_lap_ring = float(np.mean(np.abs(lap[ring]))) if ring_count else 0.0
            mean_lap_edge = float(np.mean(np.abs(lap[edge_mask]))) if edge_count else 1.0
            # Normalize by local contrast: divide by mean gradient at edges.
            mean_grad_edge = float(np.mean(grad[edge_mask])) if edge_count else 1.0
            # Overshoot score: halo ringing gives high lap in ring relative to gradient.
            # Heuristic: ring lap / (grad_edge+1)
            score = mean_lap_ring / (mean_grad_edge + 8.0)
            # Alternatively use ratio ring/edge lap.
            ratio = mean_lap_ring / (mean_lap_edge + 1e-6) if mean_lap_edge > 1e-6 else 0.0
            # Combine.
            combined = max(score * 3.0, ratio * 0.5)
            if combined >= 0.55:
                return _SEV_FLAGGED
            if combined >= 0.30:
                return _SEV_MILD
            return _SEV_CLEAN
        except Exception:
            return _SEV_CLEAN
    except Exception:
        return _SEV_CLEAN


def detect_over_smoothing(pil_image: Image.Image, source_image: Image.Image | None = None) -> Severity:
    """Over-smoothing — HF energy loss vs source ("plastic" regions)."""
    try:
        arr = _to_gray_array(pil_image)
        if arr is None:
            return _SEV_CLEAN
        hf = _hf_energy(arr)
        if source_image is not None:
            try:
                src_arr = _to_gray_array(source_image)
                src_hf = _hf_energy(src_arr)
                if src_hf < 1e-6:
                    # Source flat — cannot judge smoothing; use absolute low hf.
                    if hf < 2.0:
                        return _SEV_FLAGGED
                    if hf < 4.0:
                        return _SEV_MILD
                    return _SEV_CLEAN
                ratio = hf / (src_hf + 1e-6)
                # Lower ratio = more smoothing.
                if ratio <= 0.45:
                    return _SEV_FLAGGED
                if ratio <= 0.75:
                    return _SEV_MILD
                return _SEV_CLEAN
            except Exception:
                pass
        # No source: absolute HF low → likely over-smoothed/plastic.
        if hf < 2.5:
            return _SEV_FLAGGED
        if hf < 5.0:
            return _SEV_MILD
        return _SEV_CLEAN
    except Exception:
        return _SEV_CLEAN


def detect_invented_texture(pil_image: Image.Image, source_image: Image.Image | None = None) -> Severity:
    """Invented texture — HF gain uncorrelated with source high-freq."""
    try:
        arr = _to_gray_array(pil_image)
        if arr is None:
            return _SEV_CLEAN
        np = _np()
        hf = _hf_energy(arr)
        if source_image is None:
            return _SEV_CLEAN
        try:
            src_arr = _to_gray_array(source_image)
            if src_arr is None or np is None:
                return _SEV_CLEAN
            src_hf = _hf_energy(src_arr)
            if src_hf < 1e-6:
                # Source HF near zero but target HF high → invented.
                if hf > 6.0:
                    return _SEV_FLAGGED
                if hf > 3.0:
                    return _SEV_MILD
                return _SEV_CLEAN
            ratio = hf / (src_hf + 1e-6)
            # Correlation of Laplacians.
            lap = _laplacian(arr)
            src_lap = _laplacian(src_arr)
            if lap is None or src_lap is None:
                # Fallback to ratio only.
                if ratio >= 1.8:
                    return _SEV_FLAGGED
                if ratio >= 1.35:
                    return _SEV_MILD
                return _SEV_CLEAN
            # Align shapes (downscale may give different sizes): crop to min.
            h = min(lap.shape[0], src_lap.shape[0])
            w = min(lap.shape[1], src_lap.shape[1])
            a = lap[:h, :w].ravel()
            b = src_lap[:h, :w].ravel()
            # Normalized cross-correlation.
            try:
                am, bm = float(np.mean(a)), float(np.mean(b))
                a0 = a - am
                b0 = b - bm
                denom = float(np.sqrt(np.sum(a0 * a0) * np.sum(b0 * b0)) + 1e-9)
                corr = float(np.sum(a0 * b0) / denom) if denom else 0.0
                # Clamp.
                corr = max(-1.0, min(1.0, corr))
            except Exception:
                corr = 0.0
            # Invented: high gain + low correlation.
            if ratio >= 1.6 and corr < 0.35:
                return _SEV_FLAGGED
            if ratio >= 1.3 and corr < 0.50:
                return _SEV_MILD
            # Very high gain even with moderate corr → mild.
            if ratio >= 2.2:
                return _SEV_MILD
            return _SEV_CLEAN
        except Exception:
            return _SEV_CLEAN
    except Exception:
        return _SEV_CLEAN


def detect_blocking(pil_image: Image.Image, source_image: Image.Image | None = None) -> Severity:
    """Blocking — 8×8 DCT block-boundary energy (JPEG re-save chains)."""
    try:
        arr = _to_gray_array(pil_image)
        np = _np()
        if arr is None or np is None:
            return _SEV_CLEAN
        h, w = arr.shape
        if h < 16 or w < 16:
            return _SEV_CLEAN
        # Horizontal & vertical diffs.
        dh = np.abs(np.diff(arr, axis=1))  # H x (W-1)
        dv = np.abs(np.diff(arr, axis=0))  # (H-1) x W
        # Block-boundary positions.
        # dh columns: crossing between x and x+1 is boundary if (x+1)%8==0
        w1 = dh.shape[1]
        h1 = dv.shape[0]
        # Horizontal boundaries.
        try:
            # Build boundary mask for dh.
            cols = np.arange(w1)
            h_bound = (cols + 1) % 8 == 0
            v_bound_rows = (np.arange(h1) + 1) % 8 == 0
            if np.sum(h_bound) == 0 or np.sum(~h_bound) == 0:
                return _SEV_CLEAN
            # Means.
            h_boundary_mean = float(np.mean(dh[:, h_bound])) if np.any(h_bound) else 0.0
            h_interior_mean = float(np.mean(dh[:, ~h_bound])) if np.any(~h_bound) else 1.0
            v_boundary_mean = float(np.mean(dv[v_bound_rows, :])) if np.any(v_bound_rows) else 0.0
            v_interior_mean = float(np.mean(dv[~v_bound_rows, :])) if np.any(~v_bound_rows) else 1.0
            # Ratios.
            h_ratio = h_boundary_mean / (h_interior_mean + 1e-6) if h_interior_mean > 1e-6 else 0.0
            v_ratio = v_boundary_mean / (v_interior_mean + 1e-6) if v_interior_mean > 1e-6 else 0.0
            ratio = max(h_ratio, v_ratio)
            # Also consider absolute boundary energy for very blocky images.
            # thresholds: clean <1.25, mild 1.25..1.75, flagged >1.75
            if ratio >= 1.75:
                return _SEV_FLAGGED
            if ratio >= 1.30:
                return _SEV_MILD
            return _SEV_CLEAN
        except Exception:
            return _SEV_CLEAN
    except Exception:
        return _SEV_CLEAN


def detect_chroma_fringing(pil_image: Image.Image, source_image: Image.Image | None = None) -> Severity:
    """Chroma fringing — channel-edge misalignment (cheap demosaic/scalers)."""
    try:
        rgb = _to_rgb_arrays(pil_image)
        np = _np()
        if rgb is None or np is None:
            return _SEV_CLEAN
        r, g, b = rgb
        # Edge masks per channel via gradient magnitude threshold.
        def _edge_mask(ch):
            gx = np.zeros_like(ch)
            gy = np.zeros_like(ch)
            gx[:, :-1] = np.abs(ch[:, 1:] - ch[:, :-1])
            gy[:-1, :] = np.abs(ch[1:, :] - ch[:-1, :])
            grad = np.maximum(gx, gy)
            # Threshold ~ 28 on 0..255 scale.
            return grad >= 28.0

        re = _edge_mask(r)
        ge = _edge_mask(g)
        be = _edge_mask(b)
        union = re | ge | be
        union_cnt = int(np.sum(union))
        if union_cnt < 200:
            return _SEV_CLEAN
        # Agreement: at least 2 channels share edge.
        agree = (re & ge) | (ge & be) | (re & be)
        agree_cnt = int(np.sum(agree & union))
        overlap = agree_cnt / float(union_cnt) if union_cnt else 1.0
        misalignment = 1.0 - overlap
        if misalignment >= 0.60:
            return _SEV_FLAGGED
        if misalignment >= 0.36:
            return _SEV_MILD
        return _SEV_CLEAN
    except Exception:
        return _SEV_CLEAN


def detect_noise_amplification(pil_image: Image.Image, source_image: Image.Image | None = None) -> Severity:
    """Noise amplification — HF gain in flat areas (naive sharpeners)."""
    try:
        arr = _to_gray_array(pil_image)
        np = _np()
        if arr is None or np is None:
            return _SEV_CLEAN
        h, w = arr.shape
        if h < 8 or w < 8:
            return _SEV_CLEAN
        # Flat mask: low gradient.
        gx = np.zeros_like(arr)
        gy = np.zeros_like(arr)
        gx[:, :-1] = np.abs(arr[:, 1:] - arr[:, :-1])
        gy[:-1, :] = np.abs(arr[1:, :] - arr[:-1, :])
        grad = np.maximum(gx, gy)
        flat = grad < 12.0  # flat areas have very low gradient
        # Erode flat by 1px to avoid edge bleed (optional).
        flat_cnt = int(np.sum(flat))
        if flat_cnt < 100:
            # Mostly textured image — not flat → cannot judge, treat as clean.
            return _SEV_CLEAN
        lap = _laplacian(arr)
        if lap is None:
            return _SEV_CLEAN
        flat_hf = float(np.mean(np.abs(lap[flat]))) if flat_cnt else 0.0
        overall_hf = float(np.mean(np.abs(lap[1:-1, 1:-1]))) if lap.size else 0.0
        if source_image is not None:
            try:
                src_arr = _to_gray_array(source_image)
                if src_arr is None:
                    raise ValueError("no src")
                # Compute flat mask from source (flat defined on source).
                sgx = np.zeros_like(src_arr)
                sgy = np.zeros_like(src_arr)
                sgx[:, :-1] = np.abs(src_arr[:, 1:] - src_arr[:, :-1])
                sgy[:-1, :] = np.abs(src_arr[1:, :] - src_arr[:-1, :])
                sgrad = np.maximum(sgx, sgy)
                sflat = sgrad < 12.0
                # Align sizes: crop to min.
                hh = min(lap.shape[0], src_arr.shape[0])
                ww = min(lap.shape[1], src_arr.shape[1])
                # Recompute flat HF on aligned crops.
                # Use source flat mask cropped.
                sflat_c = sflat[:hh, :ww]
                lap_c = np.abs(lap[:hh, :ww])
                src_lap = _laplacian(src_arr)
                if src_lap is None:
                    raise ValueError("no src lap")
                src_lap_c = np.abs(src_lap[:hh, :ww])
                sflat_cnt = int(np.sum(sflat_c))
                if sflat_cnt < 50:
                    return _SEV_CLEAN
                flat_hf_src = float(np.mean(src_lap_c[sflat_c])) if sflat_cnt else 0.0
                flat_hf_tgt = float(np.mean(lap_c[sflat_c])) if sflat_cnt else 0.0
                if flat_hf_src < 1e-6:
                    if flat_hf_tgt > 4.0:
                        return _SEV_FLAGGED
                    if flat_hf_tgt > 2.0:
                        return _SEV_MILD
                    return _SEV_CLEAN
                ratio = flat_hf_tgt / (flat_hf_src + 1e-6)
                if ratio >= 2.0:
                    return _SEV_FLAGGED
                if ratio >= 1.45:
                    return _SEV_MILD
                return _SEV_CLEAN
            except Exception:
                pass
        # No source fallback: high HF in flat areas → noise.
        # thresholds on absolute flat HF.
        if flat_hf > 7.0:
            return _SEV_FLAGGED
        if flat_hf > 3.5:
            return _SEV_MILD
        # Also ratio flat vs overall.
        if overall_hf > 1e-6:
            r = flat_hf / (overall_hf + 1e-6)
            if r > 1.2 and flat_hf > 2.5:
                return _SEV_MILD
        return _SEV_CLEAN
    except Exception:
        return _SEV_CLEAN


# ---------------------------------------------------------------------------
# Entry point for paths
# ---------------------------------------------------------------------------

_DETECTORS: dict[Artifact, object] = {
    Artifact.BANDING: detect_banding,
    Artifact.HALO: detect_halo,
    Artifact.OVER_SMOOTHING: detect_over_smoothing,
    Artifact.INVENTED_TEXTURE: detect_invented_texture,
    Artifact.BLOCKING: detect_blocking,
    Artifact.CHROMA_FRINGING: detect_chroma_fringing,
    Artifact.NOISE_AMPLIFICATION: detect_noise_amplification,
}


def analyze_images(
    pil_image: Image.Image | None,
    source_image: Image.Image | None = None,
) -> dict[Artifact, Severity]:
    """Run all 7 detectors over already-decoded images (no file I/O).

    Shared proxy entry: pass the ``services/proxy.proxy_for`` bytes (or any
    PIL images) instead of decoding per stage. Never mutates or closes the
    inputs (they may be shared cached proxies). Returns all 7 keys, clean
    on error or when *pil_image* is None (fail-closed).

    When *source_image* is given, the absolute detectors in ``_ANCHORED`` are
    reported as a delta vs the source (self-pair ⇒ clean) so a constant content
    bias cannot manufacture an artifact; the source-relative detectors already
    compare against the source and are left as-is. With no source the old
    absolute severities are returned unchanged.
    """
    result: dict[Artifact, Severity] = {}
    for art in Artifact:
        result[art] = _SEV_CLEAN
    if pil_image is None:
        return result
    for art, fn in _DETECTORS.items():
        try:
            if source_image is not None and art in _ANCHORED:
                cand = _coerce_severity(fn(pil_image, None))  # type: ignore[arg-type]
                src = _coerce_severity(fn(source_image, None))  # type: ignore[arg-type]
                sev = _anchor_severity(cand, src)
            else:
                sev = _coerce_severity(fn(pil_image, source_image))  # type: ignore[arg-type]
            result[art] = sev  # type: ignore[assignment]
        except Exception:
            result[art] = _SEV_CLEAN
    return result


def analyze_artifacts(path: Path | str, source_path: Path | str | None = None) -> dict[Artifact, Severity]:
    """Analyze *path* for all 7 artifacts.

    Returns ``dict[Artifact, Severity]`` with all 7 keys (clean on error).
    ``source_path`` when provided is used for the three source-relative
    detectors (over-smoothing, invented texture, noise amplification).

    Proxy-shared (Phase 1): item + source come from the bounded
    ``services/proxy`` cache — cold path decodes each file once total no
    matter how many stages run, warm path decodes nothing.
    """
    from tabs.image_gallery.services.proxy import proxy_for

    try:
        p = Path(path)
    except Exception:
        p = Path(str(path))
    proxy = proxy_for(p)
    if proxy is None:
        result: dict[Artifact, Severity] = {}
        for art in Artifact:
            result[art] = _SEV_CLEAN
        return result
    source_image = None
    if source_path is not None:
        try:
            sp = Path(source_path)
            if sp.resolve() != p.resolve():
                src_proxy = proxy_for(sp)
                source_image = src_proxy.image if src_proxy is not None else None
        except Exception:
            source_image = None
    return analyze_images(proxy.image, source_image)
