"""The AXIS half of the Jev measured vector: name + MEANING + DIRECTION.

P6 of ``plan-gallery-ai-judgement`` (folded into P7-B): the ranker used to see a
bare ``{axis_id: number}`` map and had to GUESS what moved the number and which
end was good. Live evidence (owner's log, 2026-10-21): with a one-axis vector the
ranker wrote *"Noise higher = better? ... noise score likely quality, higher
better"* — it guessed the direction and was right by luck.

So every axis the vector carries is described once, at the payload's top level:

    {"name": "...", "definition": "...", "scale": "0-100",
     "direction": "higher-is-better" | "lower-is-better"}

- an axis the JUDGE named carries its own definition and the direction derived
  from that definition (``axis_proposal.direction_of``: "higher is better unless
  the definition says otherwise");
- a REGISTRY axis is a local-detector quality score by construction
  (``metric_scores``: "Quality is always higher = better"), so its meaning is the
  table below and its direction is ``higher-is-better`` — never inferred from the
  axis id.

One module for that vocabulary, so the vector and the output contract cannot
drift. Pure: no Qt, no HTTP, no registry mutation.
"""

from __future__ import annotations

from tabs.image_gallery.models import AXIS_DIRECTION_DEFAULT
from tabs.image_gallery.services.axis_proposal import direction_of
from tabs.image_gallery.services.profile_judged import judged_axis_entries

#: The only scale a vector axis may use (the scorecard's own 0-100 quality scale).
AXIS_PAYLOAD_SCALE = "0-100"

#: What a REGISTRY axis *is*, in one line with both ends of its 0-100 scale.
#: Every registry score is quality (higher = better), so each meaning is phrased
#: that way — "noise" is freedom FROM noise, not the amount of it. Extend this
#: table when a registry axis is added; an unmapped id falls back to its id (still
#: carries a direction, never a guessed one).
REGISTRY_AXIS_MEANINGS: dict[str, str] = {
    "sharpness": "fine detail and edge crispness; 0 = blurred, 100 = crisp",
    "exposure": "overall exposure balance; 0 = badly exposed, 100 = well exposed",
    "clipping": "highlight and black detail retained; 0 = crushed, 100 = fully retained",
    "noise": "freedom from visible noise and grain; 0 = heavy noise, 100 = clean",
    "white_balance": "freedom from a colour cast; 0 = strong cast, 100 = neutral",
    "ssim": "structural match to the source; 0 = unrelated, 100 = identical",
    "detail_gain": "detail fidelity vs the source, without loss or invention; 0 = badly off, 100 = faithful",
    "color_accuracy": "colour distance from the source; 0 = far, 100 = exact",
    "typicality": "closeness to this series' usual look; 0 = atypical, 100 = typical",
    "aesthetic": "aesthetic quality; 0 = poor, 100 = excellent",
    "lpips": "perceptual distance from the source (LPIPS); 0 = far, 100 = identical",
    "dists": "perceptual distance from the source (DISTS); 0 = far, 100 = identical",
    "brisque": "naturalness (BRISQUE); 0 = unnatural, 100 = natural",
    "clipping_delta": "clipping change vs the source; 0 = much worse, 100 = unchanged",
    "halo_delta": "halo change vs the source; 0 = much worse, 100 = unchanged",
    "chroma_fringe_delta": "chroma-fringing change vs the source; 0 = much worse, 100 = unchanged",
    "composition": "composition and framing quality; 0 = poor, 100 = excellent",
}


def _judged_entry(axis: str, profile):
    """The judge's entry for *axis* (``None`` when this profile did not name it)."""
    for entry in judged_axis_entries(profile):
        if str(getattr(entry, "name", "") or "") == axis:
            return entry
    return None


def axis_meaning(axis, *, profile=None) -> str:
    """What *axis* measures, in one line with both ends of its scale.

    A judge-named axis answers its own definition (the text the scorecard was
    given). A registry axis answers :data:`REGISTRY_AXIS_MEANINGS`; an unknown id
    answers the id itself — a name is still not a MEANING, but it is honest and
    never a guess about the scale.
    """
    name = str(axis or "").strip()
    if not name:
        return ""
    entry = _judged_entry(name, profile)
    if entry is not None:
        definition = str(getattr(entry, "definition", "") or "").strip()
        if definition:
            return definition
    return REGISTRY_AXIS_MEANINGS.get(name, name)


def axis_direction(axis, *, profile=None) -> str:
    """``higher-is-better`` | ``lower-is-better`` for *axis* (never a guess).

    A judge-named axis follows its definition/explicit field
    (``direction_of``); a registry axis is a quality score by construction
    (higher is better).
    """
    name = str(axis or "").strip()
    entry = _judged_entry(name, profile)
    if entry is not None:
        return direction_of(entry, getattr(entry, "definition", ""))
    return AXIS_DIRECTION_DEFAULT


def axis_payload(axis, *, profile=None) -> dict:
    """One axis description — the shape the ranker reads."""
    name = str(axis or "").strip()
    return {
        "name": name,
        "definition": axis_meaning(name, profile=profile),
        "scale": AXIS_PAYLOAD_SCALE,
        "direction": axis_direction(name, profile=profile),
    }


def payload_axes(names, *, profile=None) -> list[dict]:
    """``[axis_payload(name)]`` in *names* order, de-duplicated (deterministic)."""
    out: list[dict] = []
    seen: set[str] = set()
    for axis in names or ():
        name = str(axis or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(axis_payload(name, profile=profile))
    return out


def scored_axis_names(vector) -> tuple[str, ...]:
    """Every axis the vector actually CARRIES a number for, in payload order.

    The union of the per-item score maps and the names in the proposed axes
    list: the ranker sees both as dimensions, so the "at least two axes"
    precondition counts both. An axis listed in the axes metadata but scored by
    nobody is not a dimension (the metadata describes the question, not an
    answer).
    """
    out: list[str] = []
    try:
        entries = list((vector or {}).get("items", ()) or ())
    except Exception:
        entries = []
    for entry in entries:
        try:
            axes = (entry.get("scores") or {}).keys()
        except Exception:
            continue
        for axis in axes:
            name = str(axis)
            if name and name not in out:
                out.append(name)
    try:
        proposed = list((vector or {}).get("proposed_axes", ()) or ())
    except Exception:
        proposed = []
    for entry in proposed:
        try:
            name = str((entry or {}).get("name", "") or "")
        except Exception:
            continue
        if name and name not in out:
            out.append(name)
    return tuple(out)


__all__ = [
    "AXIS_PAYLOAD_SCALE",
    "REGISTRY_AXIS_MEANINGS",
    "axis_direction",
    "axis_meaning",
    "axis_payload",
    "payload_axes",
    "scored_axis_names",
]
