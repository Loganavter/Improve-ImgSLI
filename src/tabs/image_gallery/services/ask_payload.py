"""Ask AI payload + context assembly (split out of ask_router for size).

Owns the measured-context block, the system/few-shot/user message assembly, and
the chat payload builders. :mod:`ask_router` re-exports the public builders so
the frozen seam stays ``ask_router.answer`` + ``ask_router.build_*_payload``.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.services.ask_prompt import (
    ASK_SYSTEM_PROMPT,
    FEWSHOT_ANSWER,
    FEWSHOT_CONTEXT,
    FEWSHOT_QUESTION,
)
from tabs.image_gallery.services.metric_scores import fallback_note
from tabs.image_gallery.services.vlm import _encode_image
#: Fallback answer-token budget when the caller passes none.
DEFAULT_ASK_MAX_TOKENS = 4096


def _metric_text(metric_id: str, score, labels: dict) -> str:
    """One metric as ``<Label> <score>% — <band note>`` (never a bare id)."""
    label = str((labels or {}).get(metric_id, metric_id))
    text = f"{label} {score}%"
    try:
        note = fallback_note(metric_id, int(score))
    except Exception:
        note = ""
    return f"{text} — {note}" if note else text


#: Severity string → a representative quality score for ``fallback_note``.
_SEVERITY_SCORE = {"clean": 100, "mild": 50, "flagged": 10}


def _severity_text(name: str, severity) -> str:
    """One artifact as ``name:severity (meaning)`` so the model sees the axis."""
    sev = str(severity or "").lower()
    text = f"{name}:{sev}"
    try:
        note = fallback_note(name, _SEVERITY_SCORE.get(sev, 50))
    except Exception:
        note = ""
    return f"{text} ({note})" if note else text


#: Legend shown only when at least one item carries an AI flag.
_KIND_LEGEND = (
    "Axis kinds: measured = authoritative number; 'possible …' and "
    "'AI judgment: …' = unverified AI flag (text only, no number)."
)


def _flag_text(flag: dict) -> str:
    """One AI flag as ``possible <label>`` or ``AI judgment: <label>`` (no number)."""
    label = str(flag.get("label") or flag.get("id") or "")
    if str(flag.get("kind") or "") == "judgment":
        return f"AI judgment: {label}"
    return f"possible {label}"


def _context_block(context: dict) -> str:
    """Compact measured-context block handed to the model."""
    try:
        ctx = context or {}
        labels = ctx.get("metric_labels") or {}
        items = list(ctx.get("items", []) or [])
        lines = [
            f"Scope: {ctx.get('label', '')} ({ctx.get('kind', '')}), "
            f"{int(ctx.get('count', 0) or 0)} item(s), mode={ctx.get('mode', '')}"
        ]
        src = ctx.get("source")
        if src:
            lines.append(f"Source: {src}")
        if any(it.get("flags") for it in items):
            lines.append(_KIND_LEGEND)
        for it in items:
            metrics = it.get("metrics") or {}
            sev = it.get("severities") or {}
            met_txt = "; ".join(
                _metric_text(k, v, labels) for k, v in metrics.items()
            )
            sev_txt = ", ".join(_severity_text(k, v) for k, v in sev.items())
            flag_txt = "; ".join(_flag_text(f) for f in it.get("flags") or [])
            line = f"- {it.get('alias') or it.get('name', '')}"
            badge = it.get("badge")
            if badge:
                line += f" [{badge}]"
            if met_txt:
                line += f" {met_txt}"
            if sev_txt:
                line += f" | {sev_txt}"
            if flag_txt:
                line += f" | AI flags: {flag_txt}"
            lines.append(line)
        region = ctx.get("region")
        if isinstance(region, dict):
            try:
                l, t, r, b = (float(v) for v in (region.get("box") or ()))
                lines.append(
                    "Selected region (fractions of the image, left/top/right/"
                    f"bottom): {l:.3f}, {t:.3f}, {r:.3f}, {b:.3f}"
                )
            except Exception:
                pass
        return "\n".join(lines)
    except Exception:
        return ""


def _metric_labels(context: dict) -> tuple[str, ...]:
    """Human metric labels (for the guard's metric-name check)."""
    try:
        return tuple(
            str(v) for v in (context or {}).get("metric_labels", {}).values() if v
        )
    except Exception:
        return ()


def _user_text(question: str, context: dict, *, correction: str = "") -> str:
    """The user turn: question + measured context (+ optional rewrite feedback)."""
    text = (
        f"QUESTION: {str(question or '').strip()}\n\n"
        f"MEASURED CONTEXT (authoritative):\n{_context_block(context)}"
    )
    if correction:
        text += f"\n\nREVISION REQUEST:\n{correction}"
    return text


def _base_messages(system_prompt: str | None = None) -> list[dict]:
    """System turn + one canonical few-shot exemplar as real chat turns."""
    prompt = str(system_prompt or "").strip() or ASK_SYSTEM_PROMPT
    return [
        {"role": "system", "content": [{"type": "text", "text": prompt}]},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": FEWSHOT_QUESTION
                    + "\n\nMEASURED CONTEXT (authoritative):\n"
                    + FEWSHOT_CONTEXT,
                }
            ],
        },
        {"role": "assistant", "content": [{"type": "text", "text": FEWSHOT_ANSWER}]},
    ]


def build_text_payload(
    question: str,
    context: dict,
    *,
    model: str,
    max_tokens: int = DEFAULT_ASK_MAX_TOKENS,
    correction: str = "",
    system_prompt: str | None = None,
) -> dict:
    """Text-only chat payload — NO image bytes (asserted by tests)."""
    messages = _base_messages(system_prompt) + [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _user_text(question, context, correction=correction)}
            ],
        }
    ]
    return {
        "model": model,
        "messages": messages,
        "max_tokens": int(max_tokens),
    }


def build_vision_payload(
    question: str,
    context: dict,
    *,
    model: str,
    max_tokens: int = DEFAULT_ASK_MAX_TOKENS,
    correction: str = "",
    system_prompt: str | None = None,
) -> dict:
    """Vision chat payload: text + one downscaled image per scope item.

    When ``context['region']`` is present, the crop of the selected region is
    appended after the full images with a leading label, so the model sees both
    the whole picture and the magnified area.
    """
    content: list[dict] = [
        {"type": "text", "text": _user_text(question, context, correction=correction)},
    ]
    for it in list((context or {}).get("items", []) or []):
        try:
            path = Path(str(it.get("path")))
            mime, data = _encode_image(path)
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{data}"}}
            )
        except Exception:
            continue
    region = (context or {}).get("region")
    if isinstance(region, dict):
        try:
            from tabs.image_gallery.services.vlm import encode_region

            enc = None
            path = region.get("path")
            box = region.get("box")
            if path and box:
                enc = encode_region(path, box)
            if enc:
                mime, data = enc
                label = str(region.get("label") or "SELECTED REGION (crop)")
                content.append({"type": "text", "text": f"{label}:"})
                content.append(
                    {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{data}"}}
                )
        except Exception:
            pass
    return {
        "model": model,
        "messages": _base_messages(system_prompt) + [{"role": "user", "content": content}],
        "max_tokens": int(max_tokens),
    }


__all__ = [
    "DEFAULT_ASK_MAX_TOKENS",
    "build_text_payload",
    "build_vision_payload",
]
