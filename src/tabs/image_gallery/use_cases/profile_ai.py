"""The VLM metric-profile selector — plan P2/P3/P7-A (one pinned call).

The content-aware half of the adaptive-profile pipeline: from the probe members
chosen by ``use_cases/profile_probe`` and a compact salience summary, ask a
vision model to **name the axes that most differentiate THIS series** (plan-
gallery-ai-judgement §OWNER REVISION 2026-10-22).

The model is an AUTHOR, not a selector from a closed menu:

- the prompt offers EXAMPLES of what an axis can be (each with a one-line
  meaning) and says explicitly that none of them has to be taken;
- it asks for **3 to 8 axes in free form** — the most differentiating ones for
  these pictures — and keeps the salience summary, because that summary is the
  "most differentiating" instruction made concrete (which measurable axes
  already separate this series);
- an axis that IS a registry id is kept as that id (a local detector can score
  it too); any other name becomes a first-class
  ``models.AiAxisProposal`` entry (name + definition + scale + direction).

The pool/mode filter that used to drop every non-registry name and every
registry id the mode could not measure is GONE: a free name with a definition is
the normal case. What is still refused (with a recorded reason) is an axis that
is NOT MEASURABLE — an unusable/empty name, a name with no definition, a name
repeated inside the reply (``services/axis_choice.parse_axis_choices``).

One call per unchanged folder-generation: the selection is pinned
(``services/profile_cache``, keyed on member fingerprint + mode + model + pool),
and a re-run over unchanged inputs is served from disk with no second HTTP
call. A reply cut off at the token cap (``finish_reason=length``) is retried
ONCE with a doubled budget (``profile_ai_request.retry_profile_budget``) before
the selector gives up; a selection that still yields no axis is logged at
WARNING with finish_reason/budget/model, so a quality drop is visible
without ``IMGSLI_AI_DEBUG``. Every failure (AI off, no probe members, transport
raise, junk reply) degrades to the series-derived offer
(``profile_select.derive_profile`` → ``metric_profile.profile_for_series``) —
the control always yields a usable axis set. The judge's own choice, when it
answers, WINS over that offer (P5 precedence). Malformed replies are
deliberately not pinned (a later pass may retry), mirroring
``services/jev_cache``.

Reuse, not rebuild: the transport is the shared ``services.ai_client.call_sync``
seam, the JSON envelope is forced with ``response_format={"type":
"json_object"}`` (the single-image ``ai_client.build_request`` idiom), the
answer budget comes from ``ask_router.estimate_ask_max_tokens``, image bytes
are downscaled by ``vlm._encode_image`` and the reply is extracted with the
tolerant ``ai_client.parse._extract_json``.

Pure at import time — no Qt, no HTTP, no state. Every heavy import happens
inside the function that needs it and fails open.

The REQUEST side (prompt text + chat payload) lives in the sibling
``use_cases/profile_ai_request`` and is re-exported here, so ``profile_ai``
stays the one import surface its callers and tests pin (``__all__`` below).
"""

from __future__ import annotations

import json
import logging

from tabs.image_gallery.use_cases.profile_ai_request import (  # noqa: F401
    AXIS_EXAMPLES,
    PROFILE_PROBE_MAX_EDGE,
    _as_list,
    _attr,
    build_profile_request,
    retry_profile_budget,
)
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def ai_selector_available(settings) -> bool:
    """True when a profile call can even be attempted. Never raises.

    The same gate the rest of the gallery uses: AI enabled, an API key, and an
    endpoint to reach (a model id or a custom base URL).
    """
    try:
        enabled = bool(_attr(settings, "enabled", False))
        api_key = str(_attr(settings, "api_key", "") or "")
        model = str(_attr(settings, "model", "") or "")
        base_url = str(_attr(settings, "base_url", "") or "")
        return bool(enabled and api_key and (model or base_url))
    except Exception:
        return False


def profile_fingerprint(
    items, *, mode, model, pool=None, base_url="", reasoning_effort=""
) -> str:
    """The pin identity for one folder-generation (delegates to the cache key).

    ``sha256`` over sorted ``str(path):mtime_ns`` plus the mode, the model, the
    normalized ``base_url``, the reasoning effort and the pool ids — one
    definition, in ``services/profile_cache`` (this is the ``use_cases``-side
    name, so the wiring lane never imports the cache layer for it).
    """
    from tabs.image_gallery.services import profile_cache

    return profile_cache.profile_cache_key(
        items,
        mode=mode,
        model=model,
        pool=pool,
        base_url=base_url,
        reasoning_effort=reasoning_effort,
    )


def _bare_list(text) -> list | None:
    """A bare JSON array in a reply (fences/reasoning tolerated)."""
    source = str(text or "")
    try:
        from tabs.image_gallery.services.ai_client.parse import _strip_reasoning

        source = _strip_reasoning(source)
    except Exception:
        pass
    candidates = [source.strip().strip("`").strip()]
    i, j = source.find("["), source.rfind("]")
    if 0 <= i < j:
        candidates.append(source[i : j + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, list):
            return parsed
    return None


def _reply_axes(text) -> list | None:
    """The axis list a reply carries: ``{"axes": [...]}`` or a bare array.

    An element may be a bare id string (terse/older answers) or an object with
    ``name``/``definition``/``scale``/``direction`` (the free-form answer this
    prompt asks for) — ``axis_choice.parse_axis_choices`` classifies them.
    """
    obj = None
    try:
        from tabs.image_gallery.services.ai_client.parse import _extract_json

        obj = _extract_json(text)
    except Exception:
        obj = None
    axes = None
    if isinstance(obj, dict):
        candidate = obj.get("axes")
        if isinstance(candidate, list):
            axes = candidate
    if axes is None:
        axes = _bare_list(text)
    if axes is None:
        return None
    return list(axes) or None


def parse_profile_reply(text, *, mode=None):
    """Tolerant parse of a selector reply → ``MetricProfile`` | ``None``.

    Accepts ``{"axes": [{"name": …, "definition": …, "scale": …, "direction": …}]}``
    (also bare ids, also a bare array), through the shared tolerant JSON extractor
    and the ONE classifier (``axis_choice.parse_axis_choices``):

    - a name that IS a registry id is the registry axis (``axis_ids``) — a local
      detector can score it;
    - any other name WITH a definition is a first-class entry
      (``axis_entries``: name + definition + scale + direction) — the normal
      answer of the free-form selector, no filter, no mode availability check;
    - a name with NO definition, an unusable name or a repeat is refused with a
      recorded reason (logged, never stored).

    Returns ``None`` when nothing usable was found (no JSON, an empty list, every
    pick refused): never a guess, and never a hollow ``vlm`` profile — the caller
    falls back to the series-derived offer (``profile_for_series``), fail-open
    with its own debug line.
    """
    axes = _reply_axes(text)
    if not axes:
        return None
    try:
        from tabs.image_gallery.services.axis_choice import parse_axis_choices
        from tabs.image_gallery.services.metric_profile import MetricProfile

        choices = parse_axis_choices(axes)
        if choices.refusals:
            logger.debug(
                "profile select refused axes: %s (a pick with no measurable "
                "meaning is recorded, never stored)",
                ", ".join(f"{name}={reason}" for name, reason in choices.refusals),
            )
        if not (choices.registry_ids or choices.entries):
            return None
        profile = MetricProfile(
            axis_ids=choices.registry_ids,
            mode=mode,
            source="vlm",
            axis_entries=choices.entries,
        )
    except Exception:
        logger.debug("profile select parse failed", exc_info=True)
        return None
    return profile if profile else None


def _reply_text(raw) -> str:
    try:
        content = raw["choices"][0]["message"]["content"]
    except Exception:
        return ""
    if isinstance(content, list):
        parts = [
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)


def _reply_finish(raw) -> str:
    """finish_reason of the first choice ("" when absent/unreadable)."""
    try:
        return str((raw.get("choices") or [{}])[0].get("finish_reason") or "")
    except Exception:
        return ""


def _reply_reasoning_chars(raw) -> int:
    """Length of the hidden chain-of-thought in the reply (0 when none).

    The starved-budget signature is ``content_chars=0`` next to a large
    ``reasoning_chars``: the model reasoned through the whole completion and
    never started the answer.
    """
    try:
        message = (raw.get("choices") or [{}])[0].get("message") or {}
        return len(str(message.get("reasoning") or ""))
    except Exception:
        return 0


def _default_client_call():
    try:
        from tabs.image_gallery.services import ai_client

        return ai_client.call_sync
    except Exception:
        return None


def choose_profile_sync(
    items,
    *,
    mode,
    settings,
    folder_key=None,
    salience=None,
    reference_path=None,
    cache=None,
    client_call=None,
):
    """The single entry the wiring lane calls → a usable ``MetricProfile``.

    Order (plan P2 §Select):

    1. AI not configured → the series-derived offer
       (``profile_select.derive_profile`` → ``profile_for_series``) — **no** call;
    2. a pin hit for this folder-generation → the pinned profile (source
       ``vlm`` preserved) — **no** call;
    3. otherwise probe the K most-deviant members, build the free-form
       axis-naming request, call the transport, parse, pin and return.

    Any failure — no probe members, no transport, a raising transport, a junk
    reply — degrades to the series offer. Never raises. ``client_call``
    defaults to ``ai_client.call_sync`` and is invoked as
    client_call(base_url, api_key, payload). folder_key is accepted for
    call-site symmetry; the pin identity is the member fingerprint.
    """
    from tabs.image_gallery.use_cases import profile_select

    members = _as_list(items)

    def _offer():
        try:
            return profile_select.derive_profile(members, mode=mode)
        except Exception:
            from tabs.image_gallery.services.metric_profile import profile_for_mode

            return profile_for_mode(mode)

    if not ai_selector_available(settings):
        return _offer()

    from tabs.image_gallery.services import profile_cache
    from tabs.image_gallery.use_cases import profile_probe

    model = str(_attr(settings, "model", "") or "")
    base_url = str(_attr(settings, "base_url", "") or "")
    api_key = str(_attr(settings, "api_key", "") or "")
    effort = str(_attr(settings, "reasoning_effort", "auto") or "auto")

    try:
        key = profile_cache.profile_cache_key(
            members,
            mode=mode,
            model=model,
            base_url=base_url,
            reasoning_effort=effort,
        )
    except Exception:
        key = ""

    cache_obj = cache if cache is not None else profile_cache.default_cache()
    if key:
        try:
            hit = cache_obj.get(key)
        except Exception:
            hit = None
        if hit is not None:
            return hit

    try:
        probes = profile_probe.probe_members(members, reference_path=reference_path)
    except Exception:
        probes = ()
    if not probes:
        return _offer()

    summary = salience if salience is not None else profile_probe.salience_summary(members)
    try:
        payload = build_profile_request(
            probes,
            model=model,
            salience=summary,
            effort=effort,
            base_url=base_url,
        )
    except Exception:
        return _offer()

    call = client_call or _default_client_call()
    if call is None:
        return _offer()
    try:
        raw = call(base_url, api_key, payload)
    except Exception:
        logger.debug("profile select call failed", exc_info=True)
        return _offer()

    attempts = 1
    profile = parse_profile_reply(_reply_text(raw), mode=mode)
    if profile is None and _reply_finish(raw) == "length":
        # finish=length with no axes means the completion was spent before the
        # answer existed (measured 2026-10-26: 560-token budget, reasoning=560,
        # content=0). The first request already asked to exclude the reasoning;
        # a provider that ignores that can only be rescued by a bigger cap, so
        # retry ONCE with the doubled budget instead of dropping to the offer.
        retry_budget = retry_profile_budget(payload.get("max_tokens"))
        try:
            retry_payload = build_profile_request(
                probes,
                model=model,
                salience=summary,
                effort=effort,
                max_tokens=retry_budget,
                base_url=base_url,
            )
        except Exception:
            retry_payload = None
        if retry_payload is not None:
            try:
                raw = call(base_url, api_key, retry_payload)
                payload = retry_payload
                attempts += 1
            except Exception:
                logger.debug("profile select retry call failed", exc_info=True)
            else:
                profile = parse_profile_reply(_reply_text(raw), mode=mode)

    if profile is None:
        # A WARN, not a DEBUG: the run silently loses its VLM axes and falls
        # back to the series offer, which looks like a working profile. Without
        # IMGSLI_AI_DEBUG the owner had no way to see this.
        logger.warning(
            "profile select: no usable axis — finish_reason=%s max_tokens=%s "
            "attempts=%d reasoning_chars=%d model=%s mode=%s; series offer "
            "kept (this run has no VLM-named axes)",
            _reply_finish(raw) or "unknown",
            payload.get("max_tokens"),
            attempts,
            _reply_reasoning_chars(raw),
            model,
            mode,
        )
        return _offer()
    if key:
        try:
            cache_obj.put(key, profile)
        except Exception:
            pass
    return profile


__all__ = [
    "AXIS_EXAMPLES",
    "ai_selector_available",
    "build_profile_request",
    "choose_profile_sync",
    "parse_profile_reply",
    "profile_fingerprint",
]
