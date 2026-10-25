"""Analysis prompt construction + gated AI debug tracing."""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: The ``[ai]`` trace's own level (plan-gallery-ai-judgement P5, P4 leftover).
#: The channel is already opt-in (``IMGSLI_AI_DEBUG`` gates every line), so when
#: it IS on its lines are *information*, not alarms: WARNING made a normal debug
#: run read like a cascade of failures. A normal run logs nothing here at all.
AI_TRACE_LEVEL = logging.INFO


def _ai_debug(msg: str, *args) -> None:
    """``IMGSLI_AI_DEBUG=1``-gated AI client trace ([ai] prefix).

    Logs the request shape, response status and ``x-ratelimit-*`` headers
    (429 diagnosis) — never the API key or image bytes. Emitted at
    :data:`AI_TRACE_LEVEL` (INFO), not WARNING: the env key is the toggle, and
    a normal run (key unset) stays silent.
    """
    if _env_flag("IMGSLI_AI_DEBUG"):
        logger.log(AI_TRACE_LEVEL, "[ai] " + msg, *args)

def _ai_debug_enabled() -> bool:
    """True when the ``IMGSLI_AI_DEBUG`` trace gate is on."""
    return bool(_env_flag("IMGSLI_AI_DEBUG"))


def _ai_snippet(text, *, head: int = 600, tail: int = 240) -> str:
    """One-line, bounded preview of a model reply for the ``[ai]`` trace.

    Shows length + head…tail: a truncated answer loses its TAIL
    (``finish_reason=length``), a reasoning-only answer shows a long head —
    both visible without dumping the whole body into the log.
    """
    try:
        s = str(text or "")
    except Exception:
        return "<unprintable>"
    s = s.replace("\r", " ").replace("\n", " ")
    n = len(s)
    if n <= head + tail:
        return f"({n}c) {s}"
    return f"({n}c) {s[:head]} … {s[-tail:]}"


def _ratelimit_headers(headers) -> str:
    """Compact x-ratelimit-* + retry-after summary for one response."""
    try:
        out = []
        for k, v in (headers or {}).items():
            lk = str(k).lower()
            if lk.startswith("x-ratelimit") or lk in ("retry-after", "x-request-id"):
                out.append(f"{lk}={v}")
        return " ".join(out)
    except Exception:
        return ""

_PROMPT_CORE = (
    "You assess TECHNICAL image quality for a gallery that compares many "
    "processing variants (upscalers, restorations) of the SAME picture. "
    "Judge quality and DEFECTS only — never describe the scene, objects or "
    "content: they are identical across variants and add nothing.\n"
    "Score EVERY applicable axis listed below from 0 (worst) to 100 (best) in "
    "the \"axes\" object, as YOUR OWN read of this picture.\n"
)

#: Default prompt for the no-mode / legacy case (all untagged measured axes).
PROMPT_TEMPLATE = _PROMPT_CORE

def _scorecard_axes(mode=None, *, profile=None) -> tuple[tuple[str, str], ...]:
    """``(axis_id, label)`` for every axis the AI must score.

    One set, two provenances (plan-gallery-ai-judgement P7-A):

    - the profile's REGISTRY axes (``measured_axes_for(mode, profile=profile)``) —
      single source of truth, labeled by their registry label, exactly as before;
    - the axes the JUDGE NAMED for this series (``judged_axis_entries(profile)``) —
      requested BY NAME with their own definition, which is what makes a free axis
      measurable: the model is told what moves between 0 and 100 instead of
      guessing from an id.

    ``profile`` (any object with ``.axis_ids`` / ``.axis_entries``, canonically
    ``MetricProfile``) wins when given; ``profile=None`` is the mode mapping
    (fail-open). Order = registry, then the judge's entries in profile order.

    A profile that carries ONLY judge axes has no registry set to narrow, and the
    mode mapping is the fallback for an ABSENT profile — not for a judge that
    answered with no registry axis. So in that case the registry half is empty and
    the scorecard asks exactly the judge's axes.
    """
    try:
        from tabs.image_gallery.services.metric_scores import spec_for
        from tabs.image_gallery.services.profile_judged import (
            judged_axis_entries,
            scorecard_axis_ids,
        )

        out: list[tuple[str, str]] = []
        judge_entries = judged_axis_entries(profile)
        judge_definition = {
            str(getattr(entry, "name", "") or "").strip(): str(
                getattr(entry, "definition", "") or ""
            ).strip()
            for entry in judge_entries
        }
        for axis_id in scorecard_axis_ids(mode, profile=profile):
            if axis_id in judge_definition:
                out.append((axis_id, judge_definition[axis_id] or axis_id))
                continue
            spec = spec_for(axis_id)
            out.append((axis_id, spec.label if spec is not None else axis_id))
        return tuple(out)
    except Exception:
        return ()

def attach_measured_context(text: str, measured_block: str, *, mode=None, profile=None) -> str:
    """Append the local measurement block, minus every axis the model must judge.

    plan-gallery-ai-judgement P3-E: the analyze prompt used to hand the model the
    LOCAL number for the same axes it was asked to score ("LOCAL MEASUREMENTS
    (Algorithms domain, context only)"). A constant ``exposure = 82`` on five of
    six cards is consistent with anchoring on that number, and a model score for
    a reference-relative axis can be an echo of a detector instead of a
    judgement — which is the one thing the AI domain must not report.

    So the block is filtered by the ONE axis resolver
    (``measured_axes_for(mode, profile=profile)``): a line whose label resolves
    to an axis the model is asked to score is dropped (the echo), and an
    unreadable line is dropped too (fail closed — a number whose axis is
    unknown cannot be checked for an echo). When nothing remains there is no
    block at all, which is the normal case: the profile IS the asked set.
    ``text`` is returned unchanged when there is nothing to attach.
    """
    block = str(measured_block or "").strip()
    if not block:
        return text
    keep = _unechoed_measurement_lines(block, mode=mode, profile=profile)
    if not keep:
        return text
    return f"{text}\n\nLOCAL MEASUREMENTS (axes the model is NOT asked to score):\n{keep}"


def _label_to_axis() -> dict[str, str]:
    """``{label (normalized): axis_id}`` for the measured registry."""
    try:
        from tabs.image_gallery.services.metric_scores import SPECS

        return {str(spec.label).strip().lower(): spec.id for spec in SPECS}
    except Exception:
        return {}


def _unechoed_measurement_lines(block: str, *, mode=None, profile=None) -> str:
    """The block's lines that do NOT state a number for an asked axis."""
    try:
        from tabs.image_gallery.services.rank_fusion import measured_axes_for

        asked = {str(axis) for axis in measured_axes_for(mode, profile=profile)}
    except Exception:
        asked = set()
    labels = _label_to_axis()
    keep: list[str] = []
    for line in str(block).splitlines():
        body = line.strip().lstrip("-").strip()
        if not body:
            continue
        head = body.split(":", 1)[0].strip().lower()
        axis = labels.get(head) or (head if head in asked else "")
        if not axis or axis in asked:
            continue
        keep.append(line.rstrip())
    return "\n".join(keep)


def build_prompt(mode=None, *, profile=None, measured_block: str = "") -> str:
    """The analysis prompt: a per-axis scorecard for *mode* / *profile*.

    Every applicable axis is requested by canonical id with its positive label;
    an axis the JUDGE NAMED (no registry id, no registry label) is requested by
    its own name with its definition as the label, so the model measures the
    dimension it was asked for rather than guessing what an id means
    (``plan-gallery-ai-judgement`` P7-A). ``profile`` is the active metric
    profile (``measured_axes_for`` wins the registry half, ``axis_entries`` adds
    the judge's half); ``profile=None`` reproduces the mode mapping byte-for-byte.
    ``measured_block`` (local detector numbers) is attached as *context*,
    explicitly NOT authoritative.
    """
    axes = _scorecard_axes(mode, profile=profile)
    axis_parts = ", ".join(f'"{axis_id}": <0-100 {label}>' for axis_id, label in axes)
    # A judge-named axis carries its own 0..100 meaning in the definition ("0 =
    # none, 100 = everywhere"), which is NOT always "100 = best quality". Say so
    # only for such a profile: a registry-only prompt stays byte-identical (its
    # cached scorecards keep answering the same question), and a prompt that does
    # carry judge axes is already a new identity in the analyze cache.
    axes_rule = (
        "axes: one 0-100 score per axis listed above; for an axis whose definition "
        "names its own scale (0 = …, 100 = …), score exactly that scale — do not "
        "re-read it as quality; omit an axis you cannot judge (never invent a "
        "number you did not see).\n"
        if bool(getattr(profile, "axis_entries", ()) or ())
        else "axes: one 0-100 score per axis listed above; omit an axis you cannot "
        "judge (never invent a number you did not see).\n"
    )
    text = (
        _PROMPT_CORE
        + "Reply with ONLY a JSON object, no prose and no code fences:\n"
        + '{"axes": {' + (axis_parts or '"<axis_id>": <0-100>') + "}, "
        + '"reason": "practical assessment", '
        '"defects": [{"kind": "halo|banding|blocking|chroma_fringing|noise|'
        'over_smoothing|invented_texture|clipping|other", '
        '"severity": "mild|flagged", "note": "short visual description"}], '
        '"axis_proposals": [{"name": "<snake_case id>", '
        '"definition": "<what it measures, 0 = …, 100 = …>", '
        '"scale": "0-100", "score": <0-100>}], '
        '"composition": <0-100>, "confidence": <0.0-1.0>}\n'
        + axes_rule
        + "axis_proposals: AT MOST 2 technical dimensions the list above is "
        "missing AND you can actually SEE in this image (e.g. halation, sepia "
        "drift, jpeg blocking). Each needs a snake_case name, a one-sentence "
        "definition naming what moves between 0 and 100, and this image's score "
        "on that scale. Never propose an axis for scene content, an opinion "
        "without a measurable dimension, or a renamed axis from the list above. "
        "Omit the field (or send []) when the list already covers the image — "
        "an invented axis is worse than no axis.\n"
        "defects: report only artifacts you actually SEE; prefer an empty list "
        "when the image is clean. These are top-level observations.\n"
        "reason: 2-4 sentences — a PRACTICAL read of this image. Say what the "
        "processing actually did to it, whether the result is usable, and what "
        "a human should watch for. Base it on what you SEE.\n"
        "composition is your subjective framing/quality score.\n"
        "Output the JSON object ONLY: no reasoning, no analysis steps, no "
        "preamble, no prose before or after the JSON."
    )
    return attach_measured_context(text, measured_block, mode=mode, profile=profile)
