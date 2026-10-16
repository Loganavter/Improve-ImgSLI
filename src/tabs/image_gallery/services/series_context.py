"""Series AI context (plan-gallery-two-domain-axes W3). Pure; no Qt/HTTP.

The **AI unit is the series, not the individual image**: the source (reference)
plus up to ``max_variants`` variants, so an artifact becomes *attributable*
("B introduced it, A did not") — a relative comparison, which is what a VLM is
comparatively good at, rather than a reference-less per-image guess.

Numbers here are the Algorithms domain's local detector readings
(``measured_scores``); this module only assembles the comparison context and
never invents an axis. The live Ask-AI context is ``ask_context``.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.services.metric_scores import measured_scores
from tabs.image_gallery.use_cases import quality as _quality

#: Default comparison window: source + 2 variants (decided 2026-10-11).
DEFAULT_MAX_VARIANTS = 2


def _state(controller):
    return getattr(controller, "state", None)


def _members_of(series) -> list:
    """Series members (Series dataclass or a plain list/tuple), fail-open."""
    try:
        if series is None:
            return []
        if isinstance(series, (list, tuple)):
            return list(series)
        return list(getattr(series, "members", None) or ())
    except Exception:
        return []


def _item_entry(item, alias: str) -> dict:
    metrics = getattr(item, "metrics", None)
    if not isinstance(metrics, dict):
        metrics = {}
    try:
        name = Path(str(getattr(item, "path"))).name
    except Exception:
        name = str(getattr(item, "path", ""))
    scores = {mid: score for mid, _label, _raw, score in measured_scores(metrics)}
    try:
        severities = dict(_quality.severities(item))
    except Exception:
        severities = {}
    return {
        "alias": alias,
        "name": name,
        "path": str(getattr(item, "path", "")),
        "metrics": scores,
        "severities": severities,
        "badge": str(getattr(item, "badge", "") or ""),
    }


def build_series_context(controller, series, *, max_variants: int = DEFAULT_MAX_VARIANTS) -> dict:
    """Assemble the series comparison context.

    Shape::

        { 'source': str|None, 'count': int,
          'variants': [ {'alias','name','path','metrics':{id:score},
                         'severities':{name:severity},'badge':str}, ... ] }

    ``variants`` is capped at ``max_variants`` (source + up to 2 by default);
    aliases are opaque (``img_1`` …) so a descriptive name cannot bias the
    model. ``source`` is the reference path when a hub/source was resolved.
    """
    st = _state(controller)
    source = getattr(st, "source_path", None) if st is not None else None
    try:
        source_str = str(source) if source is not None else None
    except Exception:
        source_str = None

    members = _members_of(series)
    try:
        cap = max(0, int(max_variants))
    except Exception:
        cap = DEFAULT_MAX_VARIANTS
    variants = [_item_entry(it, f"img_{i + 1}") for i, it in enumerate(members[:cap])]
    return {"source": source_str, "count": len(members), "variants": variants}


__all__ = ["DEFAULT_MAX_VARIANTS", "build_series_context"]
