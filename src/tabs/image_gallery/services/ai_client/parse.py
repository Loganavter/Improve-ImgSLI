"""Response parsing + normalization for the AI client (scorecard/defects).

Also home to :func:`parse_response`, the public parse entry point.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from tabs.image_gallery.models import AiAnalysisResult

from .errors import AiResponseError, AiTruncatedError
from .prompt import _ai_debug, _ai_snippet


def _finish_of(raw) -> str | None:
    """``finish_reason`` of the first choice (None when absent)."""
    try:
        return (raw.get("choices") or [{}])[0].get("finish_reason")
    except Exception:
        return None


_DEFECT_KINDS = (
    "halo",
    "banding",
    "blocking",
    "chroma_fringing",
    "noise",
    "over_smoothing",
    "invented_texture",
    "clipping",
    "other",
)

def _parse_score(value) -> int:
    """Parse a 0-100 score, clamped; -1 when unparsable."""
    try:
        return max(0, min(100, int(float(str(value).strip().rstrip("%")))))
    except Exception:
        return -1

def _parse_verdict(value) -> str:
    """Normalize to keep | reject | unknown."""
    try:
        v = str(value).strip().lower()
    except Exception:
        return "unknown"
    if v.startswith("keep"):
        return "keep"
    if v.startswith("reject"):
        return "reject"
    return "unknown"

def _parse_confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0

_AXIS_IDS = (
    "sharpness",
    "exposure",
    "clipping",
    "noise",
    "white_balance",
    "ssim",
    "detail_gain",
    "color_accuracy",
    "typicality",
    "aesthetic",
    "composition",
    "banding",
    "halo",
    "blocking",
    "over_smoothing",
    "invented_texture",
    "chroma_fringing",
)

def _parse_axis_notes(value) -> dict:
    """Normalize the axis_notes map: canonical ids only, short non-empty."""
    out: dict[str, str] = {}
    if not isinstance(value, dict):
        return out
    for k, v in value.items():
        try:
            key = str(k).strip().lower()
        except Exception:
            continue
        if key not in _AXIS_IDS:
            continue
        try:
            note = str(v).strip()
        except Exception:
            continue
        if note:
            out[key] = note[:120]
    return out

def _parse_axes(value) -> dict[str, int]:
    """Normalize the open per-axis scorecard: canonical ids → 0-100.

    Unknown ids are dropped (never fabricated), unparsable values dropped.
    """
    out: dict[str, int] = {}
    if not isinstance(value, dict):
        return out
    try:
        from tabs.image_gallery.services.metric_scores import SCORECARD_AXIS_IDS

        allowed = SCORECARD_AXIS_IDS
    except Exception:
        allowed = None
    for k, v in value.items():
        try:
            key = str(k).strip().lower()
        except Exception:
            continue
        if allowed is not None and key not in allowed:
            continue
        score = _parse_score(v)
        if score >= 0:
            out[key] = score
    return out

def _parse_defects(value) -> tuple:
    """Normalize a defects list into ``AiDefect`` tuples (kind/severity)."""
    from tabs.image_gallery.models import AiDefect

    out = []
    if not isinstance(value, list):
        return ()
    for item in value:
        if isinstance(item, str):
            kind, severity, note = item, "mild", ""
        elif isinstance(item, dict):
            kind = str(item.get("kind", "") or "").strip().lower().replace(" ", "_")
            severity = str(item.get("severity", "") or "mild").strip().lower()
            note = str(item.get("note", "") or "").strip()
        else:
            continue
        if not kind:
            continue
        if kind not in _DEFECT_KINDS:
            kind = "other"
        if severity not in ("clean", "mild", "flagged"):
            severity = "mild"
        if severity == "clean":
            continue  # a "clean" defect is not a defect
        out.append(AiDefect(kind=kind, severity=severity, note=note))
    return tuple(out)

def _axis_flags_from_defects(defects) -> tuple:
    """Map AI-reported defects to AI-sourced candidate axes (never numbers).

    Uses ``axis_policy.degrade_unknown`` so an observation that maps to a known
    axis id gets it; anything else degrades to ``flag-for-review``. These are
    candidate flags (text; see plan-gallery-two-domain-axes) — the numeric
    per-axis answer is the scorecard (``AiAnalysisResult.axes``), never a flag.
    """
    from tabs.image_gallery.models import AiAxisFlag
    from tabs.image_gallery.services.axis_policy import degrade_unknown

    out = []
    for d in defects or ():
        try:
            axis = degrade_unknown(getattr(d, "kind", "") or getattr(d, "note", ""))
            out.append(
                AiAxisFlag(
                    id=axis,
                    label=str(getattr(d, "kind", "") or ""),
                    kind="candidate",
                    note=str(getattr(d, "note", "") or ""),
                )
            )
        except Exception:
            continue
    return tuple(out)

_REASONING_BLOCK_RE = re.compile(
    r"<(think|thinking|reasoning|analysis)>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)

def _strip_reasoning(text: str) -> str:
    """Remove chain-of-thought wrappers many reasoning models emit.

    `` thinking…<｜end▁of▁thinking｜>`` / ``<reasoning>…</reasoning>`` blocks are dropped so
    the JSON extractor only sees the answer, not the model's scratchpad.
    """
    try:
        return _REASONING_BLOCK_RE.sub("", str(text)).strip()
    except Exception:
        return text

def _extract_json(content: str) -> dict | None:
    """Best-effort JSON object out of a model reply (fences/prose tolerated)."""
    s = _strip_reasoning(content)
    if s.startswith("```"):
        s = s.strip("`").strip()
        if s[:4].lower() == "json":
            s = s[4:].strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    try:
        i, j = s.find("{"), s.rfind("}")
        if 0 <= i < j:
            obj = json.loads(s[i : j + 1])
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return None

def _parse_axis_proposals(value):
    """Normalize the reply's proposed axes into ``(accepted, refusals)``.

    plan-gallery-ai-judgement P3-B: a proposed axis is a first-class entry
    (``ai.models.AiAxisProposal``, ``producer="vlm"`` / ``kind="candidate"``)
    only when it carries a usable name, a measurable definition, the 0-100 scale
    and a score. Everything else is REFUSED with a recorded reason — never
    silently stored as an axis (and never silently dropped either). One
    implementation of the rule: ``services.axis_proposal``.
    """
    from tabs.image_gallery.services.axis_proposal import parse_proposals

    return parse_proposals(value)

_LEGACY_LINE_RE = re.compile(
    r"^\s*(DESCRIPTION|TAGS|VERDICT|SHARPNESS|NOISE|EXPOSURE|COMPOSITION|REASON)\s*:",
    re.IGNORECASE,
)

def _looks_like_legacy_lines(content: str) -> bool:
    """True only when EVERY non-empty line is a legacy ``KEY: value`` line.

    A blanket "contains a marker" check is fooled by chain-of-thought that
    happens to write ``- Sharpness: 253 (quality 63%)`` — that must NOT be
    mistaken for the legacy format (it would dump the reasoning).
    """
    try:
        lines = [ln for ln in content.splitlines() if ln.strip()]
    except Exception:
        return False
    if not lines:
        return False
    hits = sum(1 for ln in lines if _LEGACY_LINE_RE.match(ln))
    return hits == len(lines)

def _parse_lines(content: str, model: str) -> AiAnalysisResult:
    """Legacy line-order fallback (DESCRIPTION/TAGS/VERDICT lines)."""
    description = content.strip()
    tags: tuple[str, ...] = ()
    sharpness = noise = exposure = composition = -1
    verdict, reason = "unknown", ""
    for line in content.splitlines():
        line = line.strip()
        upper = line.upper()
        if upper.startswith("DESCRIPTION:"):
            description = line.split(":", 1)[1].strip()
        elif upper.startswith("TAGS:"):
            raw_tags = line.split(":", 1)[1]
            tags = tuple(t.strip() for t in raw_tags.split(",") if t.strip())
        elif upper.startswith("SHARPNESS:"):
            sharpness = _parse_score(line.split(":", 1)[1])
        elif upper.startswith("NOISE:"):
            noise = _parse_score(line.split(":", 1)[1])
        elif upper.startswith("EXPOSURE:"):
            exposure = _parse_score(line.split(":", 1)[1])
        elif upper.startswith("COMPOSITION:"):
            composition = _parse_score(line.split(":", 1)[1])
        elif upper.startswith("VERDICT:"):
            verdict = _parse_verdict(line.split(":", 1)[1])
        elif upper.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    axes = {
        key: value
        for key, value in (
            ("sharpness", sharpness),
            ("noise", noise),
            ("exposure", exposure),
            ("composition", composition),
        )
        if value >= 0
    }
    return AiAnalysisResult(
        description=description,
        tags=tags,
        model=model,
        analyzed_at_iso=datetime.now(timezone.utc).isoformat(),
        sharpness=sharpness,
        noise=noise,
        exposure=exposure,
        composition=composition,
        verdict=verdict,
        verdict_reason=reason,
        axes=axes,
    )

def merge_samples(results) -> AiAnalysisResult:
    """Merge k independent scorecards of ONE image into one measured read.

    plan-gallery-ai-judgement P3-D/M4: one draw of a stochastic judge is not a
    measurement. With ``AiSettings.sample_count > 1`` the analyze path repeats
    the call and lands here:

    - every AXIS becomes the MEDIAN over the samples that scored it (a single
      wild draw cannot decide a variant);
    - a PROPOSED axis survives only when at least half the samples proposed it
      (a one-off invention is not a dimension), its score the median too;
    - ``verdict``/``reason``/``defects``/axis notes come from the FIRST sample —
      they are prose about the picture, not a measurement to average;
    - ``confidence`` is the median.

    An empty sequence returns the caller's single result unchanged (k=1 never
    reaches here). Never raises: a malformed entry is skipped.
    """
    sampled = [r for r in (results or ()) if r is not None]
    if not sampled:
        raise AiResponseError("no samples to merge")
    if len(sampled) == 1:
        return sampled[0]

    def _median(values: list[int]) -> int:
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return int(ordered[middle])
        return int(round((ordered[middle - 1] + ordered[middle]) / 2.0))

    per_axis: dict[str, list[int]] = {}
    for result in sampled:
        for axis, value in (getattr(result, "axes", None) or {}).items():
            try:
                per_axis.setdefault(str(axis), []).append(int(value))
            except Exception:
                continue
    axes = {axis: _median(values) for axis, values in per_axis.items()}

    needed = max(1, (len(sampled) + 1) // 2)
    proposals: dict[str, list] = {}
    for result in sampled:
        seen: set[str] = set()
        for proposal in getattr(result, "axis_proposals", ()) or ():
            name = str(getattr(proposal, "name", "") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            proposals.setdefault(name, []).append(proposal)
    merged_proposals = []
    for name, group in proposals.items():
        if len(group) < needed:
            continue
        first = group[0]
        scores = []
        for proposal in group:
            try:
                scores.append(int(getattr(proposal, "score", -1)))
            except Exception:
                continue
        merged_proposals.append(
            type(first)(
                name=name,
                definition=first.definition,
                scale=first.scale,
                score=_median(scores) if scores else -1,
            )
        )
    refusals: list[tuple[str, str]] = []
    for result in sampled:
        for name, reason in getattr(result, "axis_proposal_refusals", ()) or ():
            pair = (str(name), str(reason))
            if pair not in refusals:
                refusals.append(pair)

    head = sampled[0]
    confidence = _median(
        [int(round(float(getattr(r, "confidence", 0.0) or 0.0) * 100.0)) for r in sampled]
    )
    return AiAnalysisResult(
        description=head.description,
        tags=head.tags,
        model=head.model,
        analyzed_at_iso=head.analyzed_at_iso,
        sharpness=axes.get("sharpness", -1),
        noise=axes.get("noise", -1),
        exposure=axes.get("exposure", -1),
        composition=axes.get("composition", -1),
        verdict=head.verdict,
        verdict_reason=head.verdict_reason,
        defects=head.defects,
        confidence=round(confidence / 100.0, 2),
        axis_notes=dict(head.axis_notes or {}),
        axis_flags=head.axis_flags,
        axes=axes,
        axis_proposals=tuple(merged_proposals),
        axis_proposal_refusals=tuple(refusals),
    )


def parse_response(raw: dict, *, model: str) -> AiAnalysisResult:
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        _ai_debug(
            "parse SHAPE error: %s raw_keys=%s",
            exc,
            list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__,
        )
        raise AiResponseError(f"unexpected response shape: {exc}") from exc

    if not isinstance(content, str) or not content.strip():
        _ai_debug(
            "parse EMPTY content type=%s finish=%s",
            type(content).__name__,
            _finish_of(raw),
        )
        if _finish_of(raw) == "length":
            raise AiTruncatedError("answer cut off at max_tokens (empty content)")
        raise AiResponseError("empty response content")

    obj = _extract_json(content)
    _ai_debug(
        "parse content_chars=%d after_reasoning=%d json_found=%s think=%s fence=%s",
        len(content),
        len(_strip_reasoning(content)),
        obj is not None,
        bool(_REASONING_BLOCK_RE.search(content)),
        content.lstrip().startswith("```"),
    )
    if obj is None:
        # Accept the legacy KEY: value format, but NOT free-form prose /
        # chain-of-thought: dumping the model's reasoning into the block is
        # worse than an honest parse error (surfaced as "Could not parse…").
        if _looks_like_legacy_lines(content):
            _ai_debug("parse fallback=legacy_lines")
            return _parse_lines(content, model)
        _ai_debug(
            "parse NO-JSON -> AiResponseError finish=%s content=%s",
            _finish_of(raw),
            _ai_snippet(content),
        )
        if _finish_of(raw) == "length":
            raise AiTruncatedError(
                "model answer cut off at max_tokens — raise the reasoning "
                "effort/budget (finish_reason=length)"
            )
        raise AiResponseError("model did not return the required JSON object")

    # Open per-axis scorecard (new prompt) with the legacy named fields merged
    # in, so an old reply / old prompt still fills the same scorecard.
    axes = _parse_axes(obj.get("axes"))
    for key in ("sharpness", "noise", "exposure", "composition"):
        if key in axes or obj.get(key) is None:
            continue
        score = _parse_score(obj.get(key))
        if score >= 0:
            axes[key] = score
    defects = _parse_defects(obj.get("defects"))
    proposals, proposal_refusals = _parse_axis_proposals(obj.get("axis_proposals"))
    if proposal_refusals:
        _ai_debug(
            "axis proposals refused: %s (a proposal with no measurable meaning is "
            "recorded, never stored)",
            ", ".join(f"{name}={reason}" for name, reason in proposal_refusals),
        )
    return AiAnalysisResult(
        description="",
        tags=(),
        model=model,
        analyzed_at_iso=datetime.now(timezone.utc).isoformat(),
        sharpness=axes.get("sharpness", -1),
        noise=axes.get("noise", -1),
        exposure=axes.get("exposure", -1),
        composition=axes.get("composition", -1),
        verdict=_parse_verdict(obj.get("verdict", "")),
        verdict_reason=str(obj.get("reason", "") or "").strip(),
        defects=defects,
        confidence=_parse_confidence(obj.get("confidence")),
        axis_notes=_parse_axis_notes(obj.get("axis_notes")),
        axis_flags=_axis_flags_from_defects(defects),
        axes=axes,
        axis_proposals=proposals,
        axis_proposal_refusals=proposal_refusals,
    )
