"""Per-domain quality read — the primitives whose numbers a surface shows.

Two judgment domains exist (``models.JUDGMENT_DOMAINS``):

- **Algorithms** — the local detectors: ``item.metrics`` read through the metric
  registry (``metric_scores``) and ``item.artifacts`` severities.
- **AI** — the VLM's own read: the per-axis scorecard on ``item.analysis``
  (``AiAnalysisResult.axes``) and the defect severities it reported.

The seam ``plan-gallery-ai-backend-owns-quality-2026-10-16`` introduced lives
here; since W3 of ``plan-gallery-analysis-engine-2026-10-20`` the *provenance*
read path is ``tabs.image_gallery.analysis.read.read_axes``, which wraps the two
score primitives below into ``AxisValue`` records (producer + status + reason).
``domain_axis_scores`` stays as the dict view those records back, so a caller
that only needs ``{axis: score}`` (the Jev vector, tests) keeps one answer.

Each side reads ONLY its own store, so the AI domain never silently falls back
to detector numbers and vice versa. The Algorithms domain reads exactly what it
did before.
"""

from __future__ import annotations

AI_DOMAIN = "ai"
ALGORITHMS_DOMAIN = "algorithms"

#: VLM defect kind → gallery artifact id (the artifact catalog the dots/rows
#: use). ``clipping``/``other`` have no artifact row and are dropped.
_DEFECT_TO_ARTIFACT = {
    "banding": "banding",
    "halo": "halo",
    "over_smoothing": "over_smoothing",
    "invented_texture": "invented_texture",
    "blocking": "blocking",
    "chroma_fringing": "chroma_fringing",
    "noise": "noise_amplification",
}

_SEVERITY_RANK = {"clean": 0, "mild": 1, "flagged": 2}


def normalize_domain(domain) -> str:
    """``"ai"`` or ``"algorithms"`` — anything unknown degrades to Algorithms."""
    try:
        text = str(domain or "").strip().lower()
    except Exception:
        text = ""
    return AI_DOMAIN if text == AI_DOMAIN else ALGORITHMS_DOMAIN


def _spread_of_draws(draws) -> float | None:
    """Widest per-axis ``max − min`` across *draws* of ONE item (``None`` when
    fewer than two draws scored a shared axis). Never raises."""
    per_axis: dict[str, list[float]] = {}
    for draw in draws or ():
        try:
            pairs = dict(draw or {}).items()
        except Exception:
            continue
        for axis, value in pairs:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            per_axis.setdefault(str(axis), []).append(number)
    spreads = [
        max(values) - min(values)
        for values in per_axis.values()
        if len(values) >= 2
    ]
    return max(spreads) if spreads else None


def axis_noise_floor(domain=None, *, samples=None) -> float:
    """The noise floor of the instrument that produced *domain*'s scores.

    "Inside the noise" is only meaningful relative to the instrument (plan
    ``plan-gallery-ai-judgement`` M3), and with k draws it is MEASURED: the
    spread BETWEEN the variants can only order them when it is larger than the
    spread WITHIN one variant — the same picture scored k times. ``samples``
    carries that knowledge (P7-B):

    - an analysis result whose ``axis_samples`` holds its k draw scorecards;
    - or the k draw scorecards of one item directly (``[{axis: score}, ...]``).

    The floor is then the widest per-axis ``max − min`` those draws show over
    the whole series (the instrument's own worst movement here), and the
    constants stay the FALLBACK for a single draw, where no within-item spread
    exists: ``rank_fusion.AXIS_NOISE_FLOOR`` (the stochastic judge) or
    ``DETECTOR_NOISE_FLOOR`` (the deterministic detectors). ONE resolver: the
    rows, the Jev vector and any report ask here instead of picking a number.
    """
    try:
        items = list(samples or ())
    except Exception:
        items = []
    measured: list[float] = []
    if items and all(isinstance(sample, dict) for sample in items):
        # The raw draw scorecards of ONE item: that IS the within-item spread.
        spread = _spread_of_draws(items)
        if spread is not None:
            measured.append(spread)
    else:
        for sample in items:
            spread = _spread_of_draws(getattr(sample, "axis_samples", None) or ())
            if spread is not None:
                measured.append(spread)
    if measured:
        return max(measured)
    try:
        from tabs.image_gallery.services.rank_fusion import (
            AXIS_NOISE_FLOOR,
            DETECTOR_NOISE_FLOOR,
        )
    except Exception:  # pragma: no cover - defensive: never block a read
        return 0.0
    return AXIS_NOISE_FLOOR if normalize_domain(domain) == AI_DOMAIN else DETECTOR_NOISE_FLOOR


def ai_axis_scores(item) -> dict[str, int]:
    """The VLM's per-axis scorecard (``{axis_id: 0-100}``) for *item*; {} when
    unanalyzed. Reads ONLY ``item.analysis``, never the detectors. The AI
    primitive behind ``analysis.read.read_axes``."""
    try:
        from tabs.image_gallery.models import ai_scored_axes

        return dict(ai_scored_axes(getattr(item, "analysis", None)))
    except Exception:
        return {}


def detector_axis_scores(item) -> dict[str, int]:
    """The local detectors' quality read (``{axis_id: 0-100}``) for *item*; {}
    when nothing measured. Reads ONLY ``item.metrics``, never the VLM. The
    Algorithms primitive behind ``analysis.read.read_axes``."""
    try:
        from tabs.image_gallery.services.metric_scores import measured_scores

        metrics = getattr(item, "metrics", None)
        if not isinstance(metrics, dict):
            return {}
        return {str(sid): int(score) for sid, _label, _raw, score in measured_scores(metrics)}
    except Exception:
        return {}


def domain_axis_scores(item, *, domain) -> dict[str, int]:
    """The quality read for *domain* as ``{axis_id: 0-100}``.

    Compatibility view over ``tabs.image_gallery.analysis.read.read_axes``: the
    per-axis records are the read path (they carry producer/status/reason), and
    this dict keeps the callers that only need a number (the Jev vector). Only
    ``status == "ok"`` contributes — a gap has no number, so it is absent rather
    than ``0`` (a fabricated value).
    """
    from tabs.image_gallery.analysis.read import read_axes

    return {
        record.axis: int(record.value)
        for record in read_axes(item, domain=domain)
        if record.status == "ok"
    }


def ai_artifact_severities(item) -> dict[str, str]:
    """Artifact id → severity from the VLM's reported defects (AI domain read).

    Only artifacts the model actually reported appear; an absent artifact is
    ``clean`` by the caller's ``.get``. Worst severity wins per artifact. Reads
    ONLY ``item.analysis``.
    """
    out: dict[str, str] = {}
    try:
        analysis = getattr(item, "analysis", None)
        for defect in getattr(analysis, "defects", ()) or ():
            kind = str(getattr(defect, "kind", "") or "").strip().lower().replace(" ", "_")
            artifact_id = _DEFECT_TO_ARTIFACT.get(kind)
            if not artifact_id:
                continue
            severity = str(getattr(defect, "severity", "") or "mild").strip().lower()
            if severity not in _SEVERITY_RANK:
                severity = "mild"
            if _SEVERITY_RANK[severity] > _SEVERITY_RANK.get(out.get(artifact_id, "clean"), 0):
                out[artifact_id] = severity
    except Exception:
        pass
    return out


def detector_artifact_severities(item) -> dict[str, str]:
    """The local artifact severities (Algorithms domain read)."""
    try:
        from tabs.image_gallery.use_cases import quality

        return dict(quality.severities(item))
    except Exception:
        return {}


def domain_artifact_severity(item, artifact, *, domain) -> str:
    """One artifact's severity for *domain* (``clean`` when nothing fired)."""
    try:
        from tabs.image_gallery.use_cases import quality

        name = quality.normalize_key(artifact)
    except Exception:
        name = str(artifact or "").strip().lower()
    if not name:
        return "clean"
    if normalize_domain(domain) == AI_DOMAIN:
        return ai_artifact_severities(item).get(name, "clean")
    try:
        from tabs.image_gallery.use_cases import quality

        return quality.severity(item, name)
    except Exception:
        return "clean"


def domain_artifact_severities(item, *, domain) -> dict[str, str]:
    """All artifact severities for *domain*."""
    if normalize_domain(domain) == AI_DOMAIN:
        return ai_artifact_severities(item)
    return detector_artifact_severities(item)


__all__ = [
    "AI_DOMAIN",
    "ALGORITHMS_DOMAIN",
    "normalize_domain",
    "axis_noise_floor",
    "ai_axis_scores",
    "detector_axis_scores",
    "domain_axis_scores",
    "ai_artifact_severities",
    "detector_artifact_severities",
    "domain_artifact_severity",
    "domain_artifact_severities",
]
