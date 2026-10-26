"""Response parsing + normalization for the AI client (scorecard/defects).

Also home to :func:`parse_response`, the public parse entry point.
"""

# Audit-Meta: pattern=response-parse reason="one parser per answer shape (scorecard, sampling merge, pairwise verdict) sharing the error/truncation vocabulary and the finish-reason rules — splitting would duplicate the shape contract the client and its tests rely on; grew past 500 lines with the pairwise A/B verdict parser (board 2026-10-25)"

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from statistics import median

from tabs.image_gallery.models import AiAnalysisResult

from .errors import AiResponseError, AiTruncatedError
from .prompt import _ai_debug, _ai_snippet
from .scorecard import _parse_axes, _parse_score


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

_PARSE_PAIRWISE_BARE = {"A": "A", "B": "B", "TIE": "TIE", "EQUAL": "TIE"}


def parse_pairwise_verdict(text) -> str | None:
    """``"A" | "B" | "TIE" | None`` from one pairwise answer.

    The pairwise prompt (``prompt.build_pairwise_prompt``) asks for exactly
    ``WINNER: A|B|TIE``; a JSON ``{"winner": ...}`` is accepted too so a model
    that wraps it stays usable. ``None`` means NO usable verdict — the caller
    must treat the pair as unresolved, never default to a side (a defaulted
    winner is how position bias would sneak back in). Bounded and pure.
    """
    try:
        body = str(text or "").strip()
    except Exception:
        return None
    if not body:
        return None
    # Code fences are common even when the prompt forbids them.
    if body.startswith("```"):
        lines = [ln for ln in body.splitlines() if not ln.strip().startswith("```")]
        body = "\n".join(lines).strip()
    if not body:
        return None
    if body.startswith("{"):
        try:
            payload = json.loads(body)
        except Exception:
            payload = None
        if isinstance(payload, dict) and "winner" in payload:
            try:
                token = str(payload.get("winner") or "").strip().upper()
            except Exception:
                token = ""
            return _PARSE_PAIRWISE_BARE.get(token) or (
                "A" if token.startswith("A") else "B" if token.startswith("B") else None
            )
    for line in body.splitlines():
        stripped = line.strip().strip("*").strip()
        if not stripped.upper().startswith("WINNER"):
            continue
        if ":" not in stripped:
            continue
        value = stripped.split(":", 1)[1].strip().strip("*").strip().upper()
        if value.startswith("A"):
            return "A"
        if value.startswith("B"):
            return "B"
        if value.startswith("TIE") or value.startswith("EQUAL"):
            return "TIE"
        return None
    return _PARSE_PAIRWISE_BARE.get(body.upper())


def parse_pairwise_response(raw) -> str | None:
    """``"A" | "B" | "TIE" | None`` from one raw chat-completion reply."""
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return parse_pairwise_verdict(content)


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
    r"^\s*(DESCRIPTION|TAGS|SHARPNESS|NOISE|EXPOSURE|COMPOSITION|REASON)\s*:",
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
    """Legacy line-order fallback (DESCRIPTION/TAGS/REASON lines)."""
    description = content.strip()
    tags: tuple[str, ...] = ()
    sharpness = noise = exposure = composition = -1
    reason = ""
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
        reason=reason,
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
    - ``reason``/``defects``/axis notes come from the FIRST sample — they are
      prose about the picture, not a measurement to average;
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
    # The DRAWS themselves are carried (P7-B): the merged median is one number,
    # but how far the same picture moved between draws is the instrument's own
    # measured noise — the only honest floor for "inside the noise"
    # (``quality_read.axis_noise_floor``). Two or more draws are required; a
    # single draw cannot say anything about its own spread.
    draws: list[dict[str, int]] = []
    for result in sampled:
        row: dict[str, int] = {}
        for axis, value in (getattr(result, "axes", None) or {}).items():
            try:
                row[str(axis)] = int(value)
            except Exception:
                continue
        draws.append(row)
    # The judge half is the same question for every draw: the first sample's
    # asked set is the card's set (a draw cannot add an axis the profile did not
    # ask for).
    judge_entries = tuple(getattr(sampled[0], "axis_entries", ()) or ())

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
        reason=head.reason,
        defects=head.defects,
        confidence=round(confidence / 100.0, 2),
        axis_notes=dict(head.axis_notes or {}),
        axis_flags=head.axis_flags,
        axes=axes,
        axis_proposals=tuple(merged_proposals),
        axis_proposal_refusals=tuple(refusals),
        axis_entries=judge_entries,
        axis_samples=tuple(draws),
        # The routed model can differ per draw; the FIRST answer names the card
        # (the same convention as reason/defects) — record it, never key on it.
        answered_model=getattr(head, "answered_model", ""),
    )


def median_drift(draws, axes=None) -> dict[str, float]:
    """How far the NEWEST draw row moved the per-axis median (pure, total).

    ``draws`` = the ``{axis: score}`` rows ``merge_samples`` carries, in draw
    order; per axis scored twice, ``|median(all) - median(all but the newest)|``
    = the movement just made. ``axes`` filters names; <2 rows or no twice-scored
    axis ⇒ ``{}``. Never raises (a non-numeric / missing score is skipped).
    """
    rows = [row for row in (draws or ()) if isinstance(row, dict)]
    if len(rows) < 2: return {}  # no earlier row to compare = no movement
    wanted = None if axes is None else {str(a).strip().lower() for a in axes}
    drift: dict[str, float] = {}
    for axis, latest in rows[-1].items():
        if wanted is not None and str(axis).strip().lower() not in wanted:
            continue
        try:
            seen = [float(row[axis]) for row in rows[:-1] if axis in row]
            drift[str(axis)] = abs(median(seen + [float(latest)]) - median(seen))
        except (KeyError, TypeError, ValueError):
            continue
    return drift


def _answered_model(raw) -> str:
    """The model id the provider actually served (wire ``model``), or ``""``.

    Provenance only: the REQUEST named the primary model, but OpenRouter's
    fallback chain (``request.DEFAULT_FALLBACK_MODELS``) may answer with
    another id. Keying on it would multiply one configured backend into one
    entry per routed id, so the analyze cache identity keeps the REQUESTED
    model and the entry records this one beside it. Never raises.
    """
    try:
        return str(raw.get("model") or "").strip()
    except Exception:
        return ""


def parse_response(raw: dict, *, model: str, profile=None) -> AiAnalysisResult:
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
    # in, so an old reply / old prompt still fills the same scorecard. The judge
    # half of *profile* is the set of FREE names the prompt asked for — without
    # it the scorecard would keep the registry numbers and lose the axes the
    # judge named (P7-B).
    try:
        from tabs.image_gallery.services.profile_judged import judged_axis_entries

        judge_entries = judged_axis_entries(profile)
    except Exception:
        judge_entries = ()
    axes = _parse_axes(
        obj.get("axes"),
        allowed=tuple(str(getattr(e, "name", "") or "") for e in judge_entries),
    )
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
        reason=str(obj.get("reason", "") or "").strip(),
        defects=defects,
        confidence=_parse_confidence(obj.get("confidence")),
        axis_notes=_parse_axis_notes(obj.get("axis_notes")),
        axis_flags=_axis_flags_from_defects(defects),
        axes=axes,
        axis_proposals=proposals,
        axis_proposal_refusals=proposal_refusals,
        axis_entries=judge_entries,
        answered_model=_answered_model(raw),
    )
