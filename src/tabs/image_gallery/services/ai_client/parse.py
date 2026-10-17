"""Response parsing + normalization for the AI client (scorecard/defects).

Also home to :func:`parse_response`, the public parse entry point.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from tabs.image_gallery.models import AiAnalysisResult

from .errors import AiResponseError
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
    )
