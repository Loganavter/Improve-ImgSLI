"""Canonical metric registry — one source of truth for metric display + LLM.

Every metric the gallery measures (camera, fidelity, default) declares, once:
a canonical id, a POSITIVE display label (``Noise`` → ``Clean``), the raw
detector keys it reads (first present wins), and a raw→quality function.

Quality is always **higher = better, 0–100 %**, so the whole report reads
the same way: a long green bar means good, a short red bar means bad. The
UI renders ``f"{score}%"`` with the bar at ``score/100``; the LLM prompt
gets label + raw + score + direction so the model reasons over measured
facts instead of re-estimating.

Only measured axes are listed here; model-only judgements (composition,
subjective defects, verdict) stay with the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from tabs.image_gallery.models import MetricKind

# Rounding helper: expose the 0–100 int the UI and prompt both use.
ScoreFn = Callable[[float], float]


def _clamp01(v: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except Exception:
        return 0.0


def _clamp_raw(v: float) -> float | None:
    try:
        f = float(v)
    except Exception:
        return None
    return f if f == f else None  # NaN guard


def _as_unit(v: float) -> float:
    """Normalize an exposure-like raw that may arrive as 0–1 or 0–100."""
    return v if v <= 1.0 else v / 100.0


@dataclass(frozen=True)
class MetricSpec:
    id: str
    label: str  # positive wording — higher % is always better
    keys: tuple[str, ...]  # raw dict keys, first present wins
    qual: ScoreFn  # raw float -> quality in [0, 1]
    unit: str = "%"
    measured: bool = True
    #: What the axis *is* (see ``MetricKind``). All registry axes today are
    #: MEASURED; candidate/judgment axes arrive via ``plan-gallery-two-domain-axes``.
    kind: MetricKind = MetricKind.MEASURED
    #: Free-form tags for the open-vocabulary relevance matcher (no closed
    #: operation/content enum). Empty = always relevant.
    tags: tuple[str, ...] = ()


def _sharpness(v: float) -> float:
    return _clamp01(_clamp_raw(v) / 400.0)  # Laplacian var, ~0–400


def _exposure(v: float) -> float:
    u = _clamp01(_as_unit(_clamp_raw(v)))
    return _clamp01(1.0 - abs(u - 0.5) / 0.5)  # 100 % at a well-exposed mean


def _lower_is_better(cap: float) -> ScoreFn:
    def _fn(v: float) -> float:
        return _clamp01(1.0 - min(_clamp_raw(v), cap) / cap)

    return _fn


def _detail_gain(v: float) -> float:
    # Target ≈ 0: negative = lost detail, large positive = invented texture.
    return _clamp01(1.0 - min(abs(_clamp_raw(v)), 1.0))


def _direct(v: float) -> float:
    return _clamp01(_clamp_raw(v))


def _aesthetic(v: float) -> float:
    r = _clamp_raw(v)
    return _clamp01(r if r <= 1.0 else r / 10.0)


def _brisque(v: float) -> float:
    """BRISQUE (piq) -> quality in [0, 1]; lower score is better.

    piq's BRISQUE is roughly in [-20, 60] and can be negative, so the generic
    ``_lower_is_better(cap)`` (which assumes [0, cap]) clamped every negative
    to 100 % — a display bug. Map the plausible range linearly instead.
    """
    return _clamp01(1.0 - (_clamp_raw(v) + 20.0) / 80.0)


def _clipping_delta(v: float) -> float:
    """Source-relative clipping (percentage points): 0 = same as source (best);
    positive = the variant added blown highlights / crushed blacks."""
    return _clamp01(1.0 - max(0.0, _clamp_raw(v)) / 5.0)


def _edge_ratio_quality(v: float) -> float:
    """Edge-artifact ratio (edge/flat diff vs source): 1 = no edge-localized
    change (best); higher = the variant added halo/fringing."""
    return _clamp01(1.0 - max(0.0, _clamp_raw(v) - 1.0) / 5.0)


# Order = report order. Positive labels: Noise→Clean, Clipping→Highlight
# detail, ΔE→Color accuracy, SSIM→Source match.
SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("sharpness", "Sharpness", ("sharpness",), _sharpness),
    MetricSpec("exposure", "Exposure", ("exposure",), _exposure),
    MetricSpec("clipping", "Highlight detail", ("clipping", "clipping_pct"), _lower_is_better(10.0)),
    MetricSpec("noise", "Clean", ("noise", "noise_estimate", "noise_level"), _lower_is_better(1.0)),
    MetricSpec("white_balance", "White balance", ("wb_shift", "white_balance"), _lower_is_better(1.0)),
    MetricSpec("ssim", "Source match", ("ssim",), _direct, tags=("reference",)),
    MetricSpec("detail_gain", "Detail", ("hf_ratio", "detail_gain"), _detail_gain),
    MetricSpec("color_accuracy", "Color accuracy", ("delta_e", "deltaE", "color_shift"), _lower_is_better(10.0), tags=("reference",)),
    MetricSpec("typicality", "Typicality", ("embedding_dist_to_centroid",), _lower_is_better(1.0)),
    MetricSpec("aesthetic", "Aesthetic", ("aesthetic", "aesthetic_score"), _aesthetic),
    # Learned perceptual metrics (optional backend): lower = closer to source.
    # Caps chosen so typical upscaler distances map to the mid band.
    MetricSpec("lpips", "Perceptual (LPIPS)", ("lpips",), _lower_is_better(0.8), tags=("reference",)),
    MetricSpec("dists", "Perceptual", ("dists",), _lower_is_better(0.6), tags=("reference",)),
    # No-reference naturalness (BRISQUE; lower is better, can be negative).
    MetricSpec("brisque", "Naturalness", ("brisque",), _brisque, tags=("photo",)),
    # Source-relative clipping delta (percentage points; 0 = same as source).
    MetricSpec("clipping_delta", "Clipping vs source", ("clipping_delta",), _clipping_delta, tags=("reference",)),
    # Source-relative edge artifacts (ratio; 1 = no edge-localized change).
    MetricSpec("halo_delta", "Halo vs source", ("halo_delta",), _edge_ratio_quality, tags=("reference",)),
    MetricSpec("chroma_fringe_delta", "Chroma vs source", ("chroma_fringe_delta",), _edge_ratio_quality, tags=("reference",)),
)

_BY_ID = {s.id: s for s in SPECS}


def spec_for(metric_id: str) -> MetricSpec | None:
    return _BY_ID.get(metric_id)


def raw_for(spec: MetricSpec, metrics: dict) -> tuple[str, float] | None:
    """Return ``(key, raw)`` for the first present raw key, or None."""
    if not isinstance(metrics, dict):
        return None
    for key in spec.keys:
        v = metrics.get(key)
        if v is None:
            continue
        f = _clamp_raw(v)
        if f is None:
            continue
        return key, f
    return None


def score_for(spec: MetricSpec, raw: float) -> int:
    """Raw measurement → integer quality 0–100 (higher always better)."""
    try:
        return int(round(_clamp01(spec.qual(raw)) * 100.0))
    except Exception:
        return 0


def measured_scores(metrics: dict) -> list[tuple[str, str, float, int]]:
    """All MEASURED metrics as ``(id, label, raw, score)`` in report order.

    Candidate/judgment axes are not numbers and are never emitted here (see
    ``plan-gallery-two-domain-axes``).
    """
    out: list[tuple[str, str, float, int]] = []
    for spec in SPECS:
        if spec.kind is not MetricKind.MEASURED:
            continue
        got = raw_for(spec, metrics)
        if got is None:
            continue
        _key, raw = got
        out.append((spec.id, spec.label, raw, score_for(spec, raw)))
    return out


def score_band(score: int) -> str:
    """Coarse quality band for coloring: good / mid / bad."""
    try:
        s = int(score)
    except Exception:
        return "bad"
    if s >= 70:
        return "good"
    if s >= 40:
        return "mid"
    return "bad"


# Band descriptors (good, mid, bad) used when the AI gave no axis note, so
# every row still carries a short meaning. English — same as the AI notes.
#
# Artifact notes follow SalArt-VQA's claim ladder: good = abstain ("no claim"),
# mid = a *possible* (uncertain) defect, bad = a committed defect. So a `mild`
# artifact reads "possible X", never a verdict.
_FALLBACK_NOTES: dict[str, tuple[str, str, str]] = {
    "sharpness": ("sharp", "slightly soft", "very soft"),
    "exposure": ("well exposed", "slightly off", "poorly exposed"),
    "clipping": ("highlights preserved", "minor clipping", "clipped highlights"),
    "noise": ("clean", "visible grain", "heavy noise/grain"),
    "white_balance": ("neutral", "slight color cast", "strong color cast"),
    "ssim": ("close to source", "some drift", "far from source"),
    "detail_gain": ("detail preserved", "slight shift", "detail lost or invented"),
    "color_accuracy": ("accurate color", "slight color shift", "off color"),
    "typicality": ("typical", "somewhat atypical", "outlier"),
    "aesthetic": ("pleasing", "ordinary", "unappealing"),
    "lpips": ("perceptually close", "slight perceptual drift", "perceptually far"),
    "dists": ("perceptually close", "slight perceptual drift", "perceptually far"),
    "brisque": ("natural", "slightly unnatural", "unnatural"),
    "clipping_delta": ("no added clipping", "slight added clipping", "added clipping"),
    "halo_delta": ("no added halo", "possible added halo", "added halo"),
    "chroma_fringe_delta": ("no added fringing", "possible added fringing", "added fringing"),
    "composition": ("well composed", "ok composition", "poor composition"),
    "banding": ("smooth gradients", "possible banding", "visible banding"),
    "halo": ("clean edges", "possible halo", "strong halo"),
    "blocking": ("no blocking", "possible blocking", "strong blocking"),
    "over_smoothing": ("detail kept", "possibly smoothed", "over-smoothed"),
    "invented_texture": ("authentic texture", "possible invented texture", "invented texture"),
    "chroma_fringing": ("no fringing", "possible fringing", "strong fringing"),
}


def fallback_note(axis_id: str, score: int) -> str:
    """Short band descriptor for an axis with no AI note (always present)."""
    try:
        row = _FALLBACK_NOTES.get(str(axis_id))
        if not row:
            return ""
        band = score_band(score)
        return row[0] if band == "good" else row[2] if band == "bad" else row[1]
    except Exception:
        return ""


def format_measured_for_prompt(metrics: dict) -> str:
    """Human/LLM-readable measured metrics block ('Label: raw (quality%)')."""
    lines = []
    for _id, label, raw, score in measured_scores(metrics):
        raw_txt = f"{raw:g}"
        lines.append(f"- {label}: {raw_txt} (quality {score}%)")
    return "\n".join(lines)
