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
call. EVERY resolved answer is pinned, including the series-derived offer
(2026-10-26, ``task-profile-freeze-before-vlm-answer``): one folder resolves one
profile, so the axis set the scorecards on disk were built with is the axis set
the next pass reports — a policy change cannot silently re-roll it.
``refresh=True`` is the ONE explicit invalidation seam (a pinned offer only
becomes a paid judge answer through it / the gallery's "Reset metrics cache").
A reply cut off at the token cap (``finish_reason=length``) is retried ONCE with
a doubled budget (``profile_ai_request.retry_profile_budget``) before the
selector gives up; a selection that still yields no usable axis is logged at
WARNING with finish_reason/budget/model, so a quality drop is visible without
``IMGSLI_AI_DEBUG``. Every failure (AI off, no probe members, transport raise,
junk reply) degrades to the series-derived offer
(``profile_select.derive_profile`` → ``metric_profile.profile_for_series``) —
the control always yields a usable axis set. The judge's own choice, when it
answers, WINS over that offer (P5 precedence).

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
stays the one import surface its callers and tests pin (``__all__`` below). The
per-SERIES resolution (``per_series_profile`` / ``per_series_profiles``) rides
with the probe evidence it consumes, in ``use_cases/profile_probe``, and is
re-exported here too.

Audit-Meta: pattern=compound-module size=exempt reason="one selector decision chain: parse → the 3..8/`why` acceptance gate → the ONE retry → the pin with its source → the offer fallback. Splitting the gate from the retry (or the pin from the answer) lets one side accept a profile the other refuses — the 2026-10-26 defect was exactly a thin answer accepted silently"
"""

from __future__ import annotations

import json
import logging

from tabs.image_gallery.use_cases.profile_probe import (  # noqa: F401
    per_series_profile,
    per_series_profiles,
)
from tabs.image_gallery.use_cases.profile_ai_request import (  # noqa: F401
    PROFILE_PROBE_MAX_EDGE,
    REPLY_RETRY_NOTE,
    _as_list,
    _attr,
    build_profile_request,
    retry_profile_budget,
)
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: The owner's count rule ("from 3 to 8 axes"): a profile outside it is a thin,
#: unusable answer — it is retried ONCE and then refused with a WARN + fallback,
#: never accepted silently (measured 2026-10-26: a 1-axis reply ranked the whole
#: folder on one axis while three paid axes only labelled cards).
MIN_PROFILE_AXES = 3
MAX_PROFILE_AXES = 8

#: Shortest `why` that counts as evidence ("moves" is not a reason). The retry
#: note and the WARN both say the axis was left unexplained.
MIN_WHY_CHARS = 8


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


def profile_axis_count(profile) -> int:
    """How many axes the profile carries: registry ids + the judge's own names.

    The count the 3..8 rule is about. A free-only answer counts fully (P7-A: a
    judge that names only its own axes is a complete profile), and an unusable
    profile counts 0. Never raises.
    """
    try:
        return len(tuple(getattr(profile, "axis_ids", ()) or ())) + len(
            tuple(getattr(profile, "axis_entries", ()) or ())
        )
    except Exception:
        return 0


def missing_evidence_rows(text) -> int:
    """How many axis rows of a selector reply carry NO ``why`` evidence.

    Owner design (2026-10-26): every named axis must be tied to an observed
    difference ("which variants differ on it and how"). A row without that tie is
    an unanchored label, so it is counted here and the reply is refused with a
    retry (then the WARN + fallback) — the same path the 3..8 rule uses.

    A BARE id row is not counted: naming an axis the evidence lists IS the tie
    (the axis' spread is the observed difference), and the terse answer shape is
    explicitly accepted by the prompt. Only an explicit row that left ``why``
    empty/blank is a loss. Never raises.
    """
    axes = _reply_axes(text)
    if not axes:
        return 0
    missing = 0
    for row in axes:
        if not isinstance(row, dict):
            continue
        try:
            why = str(row.get("why", "") or "").strip()
        except Exception:
            why = ""
        if len(why) < MIN_WHY_CHARS:
            missing += 1
    return missing


def _profile_rejection(text, profile) -> str:
    """Why a selector answer is unusable (``""`` when it is fine).

    ONE gate for every reason a paid answer may not become the folder's profile:
    nothing usable parsed, a count outside 3..8, or an axis with no evidence tie.
    The caller retries once, then WARNs and falls back to the series offer.
    """
    if profile is None:
        return "no usable axis"
    count = profile_axis_count(profile)
    if count < MIN_PROFILE_AXES:
        return f"only {count} axe(s) named (the rule is {MIN_PROFILE_AXES}..{MAX_PROFILE_AXES})"
    if count > MAX_PROFILE_AXES:
        return f"{count} axes named (the rule is {MIN_PROFILE_AXES}..{MAX_PROFILE_AXES})"
    missing = missing_evidence_rows(text)
    if missing:
        return f"{missing} axe(s) with no `why` evidence (which variants differ, and how)"
    return ""


def axis_count_report(profile=None) -> dict:
    """Honest axis accounting for one profile: judge vs local, never a guess.

    - ``judged`` — axes the judge NAMED (``axis_entries``; no local producer);
    - ``judged_with_local_detector`` — of those, the ones a registry spec can also
      produce (a judge that named a pool id the profile did not already carry);
    - ``registry`` — the registry half (locally measurable axes);
    - ``total`` — ``judged`` + ``registry`` (what the order is computed over).

    Plan-gallery-ai-judgement P7-C asked for the count to be stated instead of
    implied; ``task-profile-granularity-and-axis-reporting`` (2026-10-26) makes it
    the log/UI sentence "N axes from the judge, M of them also have a local
    detector". Never raises.
    """
    try:
        entries = tuple(getattr(profile, "axis_entries", ()) or ())
    except Exception:
        entries = ()
    try:
        registry = tuple(getattr(profile, "axis_ids", ()) or ())
    except Exception:
        registry = ()
    with_local = 0
    for entry in entries:
        try:
            from tabs.image_gallery.services.metric_scores import spec_for

            if spec_for(str(getattr(entry, "name", "") or "")) is not None:
                with_local += 1
        except Exception:
            continue
    return {
        "judged": len(entries),
        "judged_with_local_detector": with_local,
        "registry": len(registry),
        "total": len(entries) + len(registry),
    }


def describe_axis_provenance(profile=None) -> str:
    """One honest sentence naming the axes that actually drive the order.

    Owner, 2026-10-26: reconciling the judge's free-form names against the local
    registry is meaningless in the AI backend mode — there the local half is at
    most SSIM (and only with a reference), so "M of them also have a local
    detector" almost always reads 0 and says nothing. The sentence therefore
    NAMES the axes instead of counting a registry that is not in play:
    ``"4 axes from the judge: contrast, color_saturation, grain, sharpness"`` plus
    ``"; 2 measured locally"`` only when the profile really carries registry axes.
    """
    counts = axis_count_report(profile)
    names: list[str] = []
    try:
        for entry in getattr(profile, "axis_entries", ()) or ():
            name = str(getattr(entry, "name", "") or "").strip()
            if name:
                names.append(name)
    except Exception:
        names = []
    if not names:
        for axis in getattr(profile, "axis_ids", ()) or ():
            names.append(str(axis))
    sentence = (
        f"{counts['judged']} axes from the judge"
        + (f": {', '.join(names)}" if names else "")
    )
    if counts["registry"]:
        sentence += f"; {counts['registry']} measured locally"
    return sentence


def axis_evidence_split(profile, evidence_axes) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(from_evidence, added_beyond)`` registry axes of *profile*.

    "From evidence" = the axis' spread in THIS series was measured (it is in
    *evidence_axes*, ``profile_probe.evidence_axis_ids``); "added beyond" = the
    model named a registry axis nobody measured a difference on here. The judge's
    own free names are neither (they have no local spread by construction) and are
    reported separately by :func:`axis_count_report`. Deterministic (profile
    order). Never raises.
    """
    try:
        evidence = {str(axis) for axis in (evidence_axes or ())}
    except Exception:
        evidence = set()
    try:
        axes = tuple(str(axis) for axis in (getattr(profile, "axis_ids", ()) or ()))
    except Exception:
        axes = ()
    from_evidence = tuple(axis for axis in axes if axis in evidence)
    added = tuple(axis for axis in axes if axis not in evidence)
    return from_evidence, added


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
    refresh: bool = False,
):
    """The single entry the wiring lane calls → a usable ``MetricProfile``.

    Order (plan P2 §Select):

    1. AI not configured → the series-derived offer
       (``profile_select.derive_profile`` → ``profile_for_series``) — **no** call;
    2. a pin hit for this folder-generation → the pinned profile (its source
       preserved) — **no** call;
    3. otherwise probe the K most-deviant members, build the free-form
       axis-naming request, call the transport, parse, pin and return.

    EVERY answer is pinned, including the offer (2026-10-26,
    ``task-profile-freeze-before-vlm-answer``): one folder resolves ONE profile,
    so a later pass reads the axis set the entries on disk were built with instead
    of re-deriving it and (with the axis set in the analysis identity) paying to
    re-analyze the folder. ``refresh=True`` is the EXPLICIT invalidation seam —
    it drops this folder's pin before resolving, which is the only way a pinned
    offer becomes a paid judge answer. Nothing else invalidates it.

    Any failure — no probe members, no transport, a raising transport, a junk
    reply, an axis count outside 3..8 after one retry — degrades to the series
    offer (which is then pinned as such). Never raises. ``client_call`` defaults
    to ``ai_client.call_sync`` and is invoked as client_call(base_url, api_key,
    payload). folder_key is accepted for call-site symmetry; the pin identity is
    the member fingerprint.
    """
    from tabs.image_gallery.use_cases import profile_select

    members = _as_list(items)

    def _offer():
        try:
            return profile_select.derive_profile(members, mode=mode)
        except Exception:
            from tabs.image_gallery.services.metric_profile import profile_for_mode

            return profile_for_mode(mode)

    from tabs.image_gallery.services import profile_cache

    try:
        key = profile_cache.profile_cache_key(
            members,
            mode=mode,
            model=str(_attr(settings, "model", "") or ""),
            base_url=str(_attr(settings, "base_url", "") or ""),
            reasoning_effort=str(_attr(settings, "reasoning_effort", "auto") or "auto"),
        )
    except Exception:
        key = ""

    cache_obj = cache if cache is not None else profile_cache.default_cache()

    def _pin(profile, *, why: str):
        """Persist the resolved profile (whatever its source). Never raises."""
        if profile is None or not key:
            return profile
        try:
            cache_obj.put(key, profile)
        except Exception:
            logger.debug("profile pin write failed", exc_info=True)
        try:
            # Deferred: this module stays import-pure (no ai_client at import).
            from tabs.image_gallery.services.ai_client import _ai_debug
            from tabs.image_gallery.services.metric_profile import format_profile

            _ai_debug(
                "profile pin: %s — %s",
                why,
                format_profile(profile),
            )
        except Exception:
            pass
        return profile

    if refresh and key:
        try:
            cache_obj.invalidate(key)
        except Exception:
            logger.debug("profile pin invalidate failed", exc_info=True)

    if not ai_selector_available(settings):
        return _pin(_offer(), why="resolved without an AI call (AI unavailable)")

    from tabs.image_gallery.use_cases import profile_probe

    model = str(_attr(settings, "model", "") or "")
    base_url = str(_attr(settings, "base_url", "") or "")
    api_key = str(_attr(settings, "api_key", "") or "")
    effort = str(_attr(settings, "reasoning_effort", "auto") or "auto")

    if key:
        try:
            hit = cache_obj.get(key)
        except Exception:
            hit = None
        if hit is not None:
            try:
                from tabs.image_gallery.services.ai_client import _ai_debug
                from tabs.image_gallery.services.metric_profile import format_profile

                _ai_debug(
                    "profile pin hit: %s — no profile request",
                    format_profile(hit),
                )
            except Exception:
                pass
            return hit

    try:
        probes = profile_probe.probe_members(members, reference_path=reference_path)
    except Exception:
        probes = ()
    if not probes:
        return _pin(_offer(), why="resolved without an AI call (no probe members)")

    # The EVIDENCE is the request's ground truth (owner design 2026-10-26): the
    # per-axis spread of THIS series plus each probe's own score, so every named
    # axis can be tied to an observed difference. No evidence ⇒ no call: a paid
    # guess anchored on nothing is worse than the free local offer.
    if salience is None:
        try:
            summary = profile_probe.salience_summary(members, probes=probes)
        except Exception:
            summary = {}
    else:
        summary = salience
    evidence_axes = ()
    try:
        evidence_axes = profile_probe.evidence_axis_ids(summary)
    except Exception:
        evidence_axes = ()
    if not evidence_axes:
        logger.warning(
            "profile select skipped: no salience evidence — no measured axis "
            "separates this series (members=%d mode=%s); series offer kept and "
            "pinned",
            len(members),
            mode,
        )
        return _pin(_offer(), why="skipped the call: no salience evidence")

    try:
        payload = build_profile_request(
            probes,
            model=model,
            salience=summary,
            effort=effort,
            base_url=base_url,
        )
    except Exception:
        return _pin(_offer(), why="resolved without an AI call (request build failed)")

    call = client_call or _default_client_call()
    if call is None:
        return _pin(_offer(), why="resolved without an AI call (no transport)")

    try:
        raw = call(base_url, api_key, payload)
    except Exception:
        logger.debug("profile select call failed", exc_info=True)
        return _pin(_offer(), why="resolved after a transport failure")

    attempts = 1
    text = _reply_text(raw)
    profile = parse_profile_reply(text, mode=mode)
    reason = _profile_rejection(text, profile)
    # ONE retry, and only when the reply argues for one: a completion cut off at
    # the token cap was starved before its answer existed (a bigger cap can rescue
    # it), and an answer that PARSED but broke the rule (count outside 3..8, an
    # axis with no `why`) is worth exactly one correction. A junk reply with
    # finish=stop is a different failure and is not re-asked.
    starved = profile is None and _reply_finish(raw) == "length"
    if reason and (starved or profile is not None):
        retry_budget = retry_profile_budget(payload.get("max_tokens"))
        retry_payload = None
        try:
            retry_payload = build_profile_request(
                probes,
                model=model,
                salience=summary,
                effort=effort,
                max_tokens=retry_budget,
                base_url=base_url,
                corrective=REPLY_RETRY_NOTE,
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
                text = _reply_text(raw)
                profile = parse_profile_reply(text, mode=mode)
                reason = _profile_rejection(text, profile)

    if reason:
        # A WARN, not a DEBUG: the run loses its VLM axes and falls back to the
        # series offer, which LOOKS like a working profile. A thin or unexplained
        # answer must never become the folder's order silently.
        logger.warning(
            "profile select: %s — finish_reason=%s max_tokens=%s attempts=%d "
            "reasoning_chars=%d model=%s mode=%s; series offer kept and pinned "
            "(this run has no VLM-named axes)",
            reason,
            _reply_finish(raw) or "unknown",
            payload.get("max_tokens"),
            attempts,
            _reply_reasoning_chars(raw),
            model,
            mode,
        )
        return _pin(_offer(), why=f"resolved after an unusable answer ({reason})")

    # (e) The trace says where the axes came from: the measured evidence vs. the
    # model's own additions — plus the judge/local count, so "the judge named 3 and
    # 1 has a local detector too" is readable without opening the payload.
    try:
        from_evidence, added = axis_evidence_split(profile, evidence_axes)
        logger.debug(
            "profile select: %d from evidence (%s), %d added beyond it (%s); %s",
            len(from_evidence),
            ",".join(from_evidence) or "-",
            len(added),
            ",".join(added) or "-",
            describe_axis_provenance(profile),
        )
        from tabs.image_gallery.services.ai_client import _ai_debug
        from tabs.image_gallery.services.metric_profile import format_profile

        _ai_debug(
            "profile select: %s — %s; from evidence: %s; added by the judge: %s",
            describe_axis_provenance(profile),
            format_profile(profile),
            ",".join(from_evidence) or "-",
            ",".join(added) or "-",
        )
    except Exception:
        pass

    return _pin(profile, why="resolved by the judge")


__all__ = [
    "MAX_PROFILE_AXES",
    "MIN_PROFILE_AXES",
    "ai_selector_available",
    "axis_count_report",
    "axis_evidence_split",
    "build_profile_request",
    "choose_profile_sync",
    "describe_axis_provenance",
    "missing_evidence_rows",
    "parse_profile_reply",
    "per_series_profile",
    "per_series_profiles",
    "profile_axis_count",
    "profile_fingerprint",
]
