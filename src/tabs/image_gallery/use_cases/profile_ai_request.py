"""The request-assembly half of the VLM metric-profile selector (P2/P3/P7-A).

Prompt text and the chat-completions payload for the ONE profile call, split out
of ``use_cases/profile_ai`` so that module stays under the file-size limit
(docs/dev/FILE_SIZE_POLICY.md). ``profile_ai`` re-exports every name here that
callers use, so the frozen import surface (and ``profile_ai.__all__``) is
unchanged.

The prompt contract is unchanged by the move (plan-gallery-ai-judgement
§OWNER REVISION 2026-10-22): EXAMPLES of what an axis can be (never a menu), the
salience summary, and the 3..8 free-form rule. ``_as_list`` and ``_attr`` live
here because the request builder is their widest consumer; ``profile_ai``
imports them back.

Pure at import time — no Qt, no HTTP, no state. ``vlm`` / ``ask_router`` are
imported inside the functions that need them and fail open.
"""

from __future__ import annotations


#: Example axes for the selector prompt: ``(name, one-line meaning)``.
#:
#: SHAPE, not a menu (plan-gallery-ai-judgement §OWNER REVISION 2026-10-22). The
#: owner's own examples ("чистота, галлюцинации, бандинг, баланс белого, JPEG шум")
#: are here as the English equivalents the app's prompts are written in, and the
#: prompt says in one clause that none of them has to be taken. Each one names
#: WHAT it measures, so the model copies the shape (a dimension, not a label)
#: rather than picking from a list.
AXIS_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("clarity", "how clean the picture reads — residual grain, blotches and smudge"),
    ("hallucination", "detail the processing invented that the source cannot support"),
    ("banding", "stepped tone transitions in smooth gradients (sky, skin, walls)"),
    ("white_balance", "a colour cast that pushes every neutral warm or cool"),
    ("jpeg_noise", "8x8 block edges and mosquito noise around high-contrast edges"),
    ("halation", "a red or orange glow bleeding past bright edges"),
    ("posterization", "tones flattened into visible bands, lost micro-contrast"),
)


def _as_list(items) -> list:
    try:
        return list(items or ())
    except Exception:
        return []


def _attr(obj, name, default=""):
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    return value


def _estimate_budget(count: int, effort: str) -> int:
    try:
        from tabs.image_gallery.services.ask_router import estimate_ask_max_tokens

        return int(estimate_ask_max_tokens({"count": int(count)}, effort=effort))
    except Exception:
        return 0


def _selector_text(salience) -> str:
    """The single text part: axis EXAMPLES, the salience summary, the 3..8 rule.

    The pool listing that used to open this text ("METRIC POOL — choose axis ids
    ONLY from this list") is gone (plan-gallery-ai-judgement P7-A): the judge
    names the axes in free form. The salience summary stays — it is the concrete
    "most differentiating" evidence for THIS series, and a registry id named there
    is an axis a local detector can measure too, so the judge is told to reuse the
    id when its own axis is that dimension.
    """
    lines = [
        "The pictures below are variants of ONE picture (upscalers, restorations, "
        "denoisers). The content is identical across them, so an axis about the "
        "scene or the subject cannot separate them — axes about TECHNICAL "
        "quality and artefacts can.",
        "",
        "EXAMPLES of what an axis can be — the SHAPE of a good axis, NOT A MENU. "
        "You are not obliged to take any of these: name your own if they fit "
        "these pictures better. Each example is a NAME and one line saying what "
        "it measures:",
    ]
    for name, meaning in AXIS_EXAMPLES:
        lines.append(f"- {name} — {meaning}")
    lines.append("")
    lines.append("SALIENCE SUMMARY (members, adaptive probe size k, axes by spread):")
    lines.append(_summary_text(salience))
    lines.append("")
    lines.append(
        "INSTRUCTION: look at THESE pictures and name FROM 3 TO 8 axes, in free "
        "form — the ones that most differentiate these variants, i.e. the axes "
        "whose value actually MOVES between them (an axis every variant shares "
        "equally is useless here). The salience summary above already names the "
        "measurable axes whose spread separates this series; if your axis IS one "
        "of those, answer with its id so the local detector scores it too."
    )
    lines.append(
        'Reply with ONLY a JSON object: {"axes": [{"name": "<short id, e.g. '
        'jpeg_noise>", "definition": "<one line: what it measures, 0 = …, 100 = '
        '…>", "scale": "0-100", "direction": "higher-is-better|'
        'lower-is-better"}]}'
    )
    lines.append(
        'A bare id (e.g. "noise") is also accepted for an axis the summary lists. '
        "No prose, no code fences."
    )
    return "\n".join(lines)


def _summary_text(salience) -> str:
    try:
        members = int((salience or {}).get("members", 0) or 0)
        k = int((salience or {}).get("k", 0) or 0)
        rows = list((salience or {}).get("axes", []) or [])
    except Exception:
        return "members=0 k=0 axes=-"
    parts = []
    for row in rows:
        try:
            parts.append(f"{row.get('id')}:{float(row.get('spread', 0.0)):g}")
        except Exception:
            continue
    return f"members={members} k={k} axes=" + (", ".join(parts) or "-")


#: Probe edge for the PROFILE SELECTOR, independent of the per-card setting.
#: The selector asks a coarse question over a few variants; its probe used to
#: ride the user's full-resolution preference (measured 2026-10-22: an 11.3 MB
#: request and a 6.9 s round trip held the AI/Jev tails on the critical path
#: before ANY card was analyzed). 512 px + JPEG keeps the salience answer and
#: cuts the payload by an order of magnitude.
PROFILE_PROBE_MAX_EDGE = 512


def build_profile_request(probe_items, *, model, salience, effort: str = "auto", max_tokens: int = 0) -> dict:
    """The one user message: axis examples + salience text, then one image each.

    Returns a chat-completions payload with response_format pinned to
    ``{"type": "json_object"}`` (reasoning models must not answer in prose) and
    a budget from ``estimate_ask_max_tokens`` unless a positive *max_tokens* is
    passed. Probe images are downscaled through ``vlm._encode_image``; an
    unreadable image is skipped, never fatal.
    """
    probes = _as_list(probe_items)
    content: list[dict] = [{"type": "text", "text": _selector_text(salience)}]
    try:
        from tabs.image_gallery.services.vlm import _encode_image
    except Exception:
        _encode_image = None
    if _encode_image is not None:
        for item in probes:
            try:
                _probe_path = str(getattr(item, "path", ""))
                try:
                    mime, data = _encode_image(
                        _probe_path,
                        max_edge=PROFILE_PROBE_MAX_EDGE,
                        prefer_jpeg=True,
                    )
                except TypeError:
                    # A one-arg encoder is a legacy double (tests / a patched
                    # seam): keep it working, just without the cost cap.
                    mime, data = _encode_image(_probe_path)
            except Exception:
                continue
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{mime};base64,{data}"},
                }
            )
    budget = 0
    try:
        budget = int(max_tokens or 0)
    except Exception:
        budget = 0
    if budget <= 0:
        budget = _estimate_budget(len(probes), effort)
    return {
        "model": str(model or ""),
        "messages": [{"role": "user", "content": content}],
        "max_tokens": budget,
        "response_format": {"type": "json_object"},
    }
