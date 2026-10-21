"""The scorecard's numeric normalizer: ``{axis: 0-100}`` with a known key set.

Split out of ``ai_client.parse`` (file-size policy; one concern): the parser
decides WHAT the reply means, this module decides which axis keys are real and
what a score value is. Both halves of the judged axis set live here
(plan-gallery-ai-judgement P7-B):

- a REGISTRY id (``metric_scores.SCORECARD_AXIS_IDS``) — a local detector can
  produce it, provenance ``measured-locally``;
- a name the JUDGE named for THIS series (``allowed``, the profile's
  ``axis_entries``) — the scorecard prompt asked for it by name, so its number is
  a model measurement, provenance ``measured-by-judge``.

Before P7-B the filter kept only registry ids: the judge named an axis and the
parser silently threw its number away, so the ranker never saw it.

Pure: no Qt, no HTTP, no state.
"""

from __future__ import annotations


def _parse_score(value) -> int:
    """Parse a 0-100 score, clamped; -1 when unparsable."""
    try:
        return max(0, min(100, int(float(str(value).strip().rstrip("%")))))
    except Exception:
        return -1


def _parse_axes(value, *, allowed=()) -> dict[str, int]:
    """Normalize the open per-axis scorecard: known ids → 0-100.

    ``allowed`` is the judge's free-name set the caller KNOWS the prompt asked
    for (``parse_response`` from the profile, a cache read from the entries
    stored in the payload). A key that is neither a registry id nor in *allowed*
    is dropped (never fabricated); an unparsable value is dropped.
    """
    out: dict[str, int] = {}
    if not isinstance(value, dict):
        return out
    try:
        from tabs.image_gallery.services.metric_scores import SCORECARD_AXIS_IDS

        registry = SCORECARD_AXIS_IDS
    except Exception:
        registry = frozenset()
    judged = {
        str(name).strip().lower(): str(name)
        for name in (allowed or ())
        if str(name).strip()
    }
    for k, v in value.items():
        try:
            key = str(k).strip().lower()
        except Exception:
            continue
        if key not in registry and key not in judged:
            continue
        score = _parse_score(v)
        if score >= 0:
            out[judged.get(key, key)] = score
    return out


__all__ = ["_parse_axes", "_parse_score"]
