"""Cross-series priority via Jev — "which series needs a human first".

Task ``task-gallery-ai-routing-jev-2026-10-09``. This is an **additive hint**:
from the conflicting per-series measured signals it produces
``{series_id: priority 1..N}`` (1 = needs attention first). It never touches a
series' internal rank, the selection or the store, and it is a *routing* signal,
never a re-rank (plan ``plan-gallery-rank-backends-2026-10-15`` §Non-goals —
cross-series ordering is out of that epic).

Transport, decision parsing and the pin store are **reused from the R3 Jev
seam** (:mod:`tabs.image_gallery.services.jev_client` /
:mod:`tabs.image_gallery.services.jev_cache`) so the gallery keeps one AI
transport and one cache idiom. The request is text-only: the payload carries
per-series *aggregate* numbers + opaque aliases (``series_N``), never a path,
an image or a prose instruction. Non-deterministic by design; the pin makes a
re-run over unchanged series+signals stable.

**Whose numbers** (ADR 009 wave A3): the aggregate is the AI backend's own
measurement — the judge's mean over the ACTIVE AI profile's axes
(``backends.ai.measure.series_quality``). It used to be
``rank_fusion.item_quality(mode=…)`` with no profile, i.e. the LOCAL fusion
aggregate, so detector numbers travelled into an AI-domain payload. The profile
is an argument, never a default: an absent/empty one is ``NoProfileYet``, which
this seam reports as :data:`PRIORITY_REASON_NO_PROFILE` before it spends a call
(a series with no axis set has no signals to route).

No Qt; the transport (``client``) is injectable so tests are network-free.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.jev_client import (
    JEV_MIN_CONFIDENCE,
    JEV_MODEL,
    _choice_of,
    _is_noul,
    _mode_token,
    _ranking_of,
    _response_dict,
    _score_of,
    make_client,
)
from tabs.image_gallery.backends.errors import BackendContractError
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Visible degrade reasons (English defaults; the caller logs / surfaces them).
PRIORITY_REASON_EMPTY = "AI (Jev) series priority: nothing to route"
PRIORITY_REASON_NOUL = "AI (Jev) series priority abstained (Noul)"
PRIORITY_REASON_LOW_CONFIDENCE = "AI (Jev) series priority was not confident enough"
PRIORITY_REASON_ERROR = "AI (Jev) series priority request failed"
PRIORITY_REASON_MALFORMED = "AI (Jev) series priority returned an unusable response"
#: No AI axis set yet: the routing payload has no signals to send, so the pass
#: degrades by name instead of sending local aggregates (ADR 009 A3).
PRIORITY_REASON_NO_PROFILE = "AI (Jev) series priority: no axis set yet"

#: Output contract (system message); aliases are ``series_N``. See the rank seam
#: ``jev_client.JEV_SYSTEM_PROMPT`` for why the shape must be constrained.
PRIORITY_SYSTEM_PROMPT = (
    "You order series by which needs a human first. Reply with ONLY a JSON "
    'object {"ranking": ["<alias>", ...]} most-attention-first — a full ranking '
    "whenever at least two series carry signals (break near ties by your best "
    'judgement). Reply {"noul": true} only when fewer than two series carry '
    "signals. No prose."
)

#: A transport takes the chat/completions request and returns the parsed JSON.
PriorityClient = Callable[[dict], dict]


@dataclass(frozen=True)
class PriorityOutcome:
    """One cross-series priority attempt.

    ``priorities`` is ``{series_id: priority 1..N}`` when decisive, else
    ``None``; ``reason`` is set whenever ``priorities`` is ``None``.
    ``cached`` reports whether the pin served it (no transport call).
    """

    priorities: dict[str, int] | None
    reason: str | None = None
    cached: bool = False

    @property
    def decided(self) -> bool:
        return bool(self.priorities)


def _series_id(series) -> str:
    try:
        return str(getattr(series, "id", "") or "")
    except Exception:
        return ""


def _ready_series(series_list) -> list[tuple[str, list]]:
    """``[(series_id, members)]`` for series worth routing (>= 2 members)."""
    planned: list[tuple[str, list]] = []
    for series in sorted(list(series_list or ()), key=_series_id):
        members = list(getattr(series, "members", ()) or ())
        if len(members) < 2:
            continue
        planned.append((_series_id(series), members))
    return planned


def _signal_entry(alias: str, members: list, *, profile) -> dict:
    """Aggregate the AI backend's own measured signals for one series.

    One number per member: the judge's mean over *profile*'s axes
    (``AIBackend.series_quality``). No paths, no images — and no
    LOCAL aggregate: ``rank_fusion.item_quality(mode=…)`` without a profile is
    the Algorithms fusion's number and must never enter this payload (ADR 009
    A3). ``NoProfileYet`` when *profile* carries no axis (the caller reports
    :data:`PRIORITY_REASON_NO_PROFILE` before spending).
    """
    from tabs.image_gallery.backends.composition import backend as _gallery_backend
    from tabs.image_gallery.services.metric_profile import DOMAIN_AI

    ai_backend = _gallery_backend(DOMAIN_AI)

    quals = [
        quality
        for quality in (
            ai_backend.series_quality(m, profile=profile) for m in members
        )
        if quality is not None
    ]
    entry: dict[str, Any] = {"alias": alias, "members": len(members)}
    if quals:
        entry["quality_mean"] = round(sum(quals) / len(quals), 2)
        entry["quality_min"] = round(min(quals), 2)
        entry["quality_max"] = round(max(quals), 2)
        entry["quality_spread"] = round(max(quals) - min(quals), 2)
    return entry


def _aliased(
    series_list, *, mode: str, profile
) -> tuple[str, list[tuple[str, str, dict]]]:
    """``(mode_token, [(alias, series_id, signal_entry)])`` — deterministic."""
    mid = _mode_token(mode)
    planned = _ready_series(series_list)
    return mid, [
        (
            f"series_{i}",
            sid,
            _signal_entry(f"series_{i}", members, profile=profile),
        )
        for i, (sid, members) in enumerate(planned, start=1)
    ]


def build_series_signals(series_list, *, mode: str, profile) -> list[dict]:
    """Per-series aggregate signal entries (payload shape, deterministic)."""
    _mid, aliased = _aliased(series_list, mode=mode, profile=profile)
    return [entry for _alias, _sid, entry in aliased]


def build_priority_request(series_list, *, mode: str, profile) -> dict:
    """OpenAI-compatible priority request for Jev (text-only aggregate signals).

    Same output contract as the rank seam (:data:`PRIORITY_SYSTEM_PROMPT`) plus
    ``response_format={"type": "json_object"}``: the bare user-only request made
    the live router answer a narrative object with no ordering (probe 2026-10-15),
    so the reply shape must be constrained. ``profile`` is the AI backend's own
    axis set (``NoProfileYet`` when it has none — no payload is built from
    another backend's numbers).
    """
    mid, aliased = _aliased(series_list, mode=mode, profile=profile)
    vector = {"mode": mid, "series": [entry for _alias, _sid, entry in aliased]}
    text = json.dumps(vector, sort_keys=True, separators=(",", ":"))
    return {
        "model": JEV_MODEL,
        "messages": [
            {"role": "system", "content": PRIORITY_SYSTEM_PROMPT},
            {"role": "user", "content": [{"type": "text", "text": text}]},
        ],
        "response_format": {"type": "json_object"},
    }


def _normalize_alias(value: Any, aliases: dict[str, str]) -> str | None:
    """Map a response token to a known ``series_N`` alias (or ``None``)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        candidate = f"series_{value}"
        return candidate if candidate in aliases else None
    text = str(value or "").strip()
    if not text:
        return None
    if text in aliases:
        return text
    low = text.lower()
    if low in aliases:
        return low
    if low.startswith("series_"):
        low = low[len("series_"):]
    try:
        candidate = f"series_{int(low)}"
    except Exception:
        return None
    return candidate if candidate in aliases else None


def _by_id_order(aliases: dict[str, str]) -> list[str]:
    """Deterministic fallback order: by ``series_id`` (never arrival order)."""
    return [a for a, _sid in sorted(aliases.items(), key=lambda kv: kv[1])]


def _decide(raw: dict, aliases: dict[str, str]) -> PriorityOutcome:
    """Turn one Jev decision into a decisive priority map or a degrade."""
    if _is_noul(raw):
        return PriorityOutcome(None, reason=PRIORITY_REASON_NOUL)

    score = _score_of(raw)
    if score is not None and score < JEV_MIN_CONFIDENCE:
        return PriorityOutcome(None, reason=PRIORITY_REASON_LOW_CONFIDENCE)

    alias_to_id = dict(aliases)

    raw_order = _ranking_of(raw)
    if raw_order is not None:
        seq: list[str] = []
        seen: set[str] = set()
        for entry in raw_order:
            alias = _normalize_alias(entry, aliases)
            if alias and alias not in seen:
                seq.append(alias)
                seen.add(alias)
        for alias in _by_id_order(aliases):
            if alias not in seen:
                seq.append(alias)
                seen.add(alias)
        return PriorityOutcome({alias_to_id[a]: i for i, a in enumerate(seq, start=1)})

    winner = _normalize_alias(_choice_of(raw), aliases)
    if winner is None:
        return PriorityOutcome(None, reason=PRIORITY_REASON_MALFORMED)
    rest = [a for a in _by_id_order(aliases) if a != winner]
    seq = [winner, *rest]
    return PriorityOutcome({alias_to_id[a]: i for i, a in enumerate(seq, start=1)})


def priority_cache_key(series_list, payload: dict, *, base_url: str = "") -> str:
    """Stable key: ``hash(series_ids + endpoint + canonical payload)``.

    Order-independent by construction (ids sorted, payload ``sort_keys``). The
    payload's model is the constant ``JEV_MODEL``, so the ENDPOINT is what
    separates two providers serving the same id: it is normalized through the
    ONE gallery normalizer (``ai_providers._url_key``), keeping two spellings of
    one provider on one pin while a provider switch is a MISS.
    """
    from tabs.image_gallery.services.ai_providers import _url_key

    ids = sorted(sid for sid, _members in _ready_series(series_list))
    try:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        canonical = repr(payload)
    raw = "|".join([*ids, f"base_url={_url_key(base_url)}", canonical])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def route_series_priority_detailed(
    series_list,
    *,
    mode: str,
    client: PriorityClient,
    cache=None,
    base_url: str = "",
    profile,
) -> PriorityOutcome:
    """Jev-route the series list, returning the full :class:`PriorityOutcome`.

    Cache-first (a pinned abstain included); a transport exception is caught and
    **not** pinned; never raises. Fewer than two routable series degrades empty.
    ``base_url`` is part of the pin identity (normalized endpoint) so one
    provider's priority map is never served for another; ``""`` keeps storeless
    callers/tests working.

    ``profile`` is the AI backend's own axis set (from its adapter). Without one
    the pass reports :data:`PRIORITY_REASON_NO_PROFILE` and spends nothing —
    there are no signals it may send (ADR 009 A3: no local aggregate here).
    """
    try:
        _mid, aliased = _aliased(series_list, mode=mode, profile=profile)
    except BackendContractError:
        return PriorityOutcome(None, reason=PRIORITY_REASON_NO_PROFILE)
    if len(aliased) < 2:
        return PriorityOutcome(None, reason=PRIORITY_REASON_EMPTY)
    aliases = {alias: sid for alias, sid, _entry in aliased}

    try:
        payload = build_priority_request(series_list, mode=mode, profile=profile)
    except BackendContractError:
        return PriorityOutcome(None, reason=PRIORITY_REASON_NO_PROFILE)
    except Exception:
        logger.debug("series priority payload build failed", exc_info=True)
        return PriorityOutcome(None, reason=PRIORITY_REASON_MALFORMED)

    cache_obj = cache if cache is not None else jev_cache.default_cache()
    try:
        key = priority_cache_key(series_list, payload, base_url=base_url)
    except Exception:
        key = ""
    if key:
        try:
            hit = cache_obj.get(key)
        except Exception:
            hit = None
        if hit is not None:
            stored = hit.get("ranks")
            if stored:
                return PriorityOutcome({str(k): int(v) for k, v in stored.items()}, cached=True)
            return PriorityOutcome(None, reason=hit.get("reason") or PRIORITY_REASON_NOUL, cached=True)

    try:
        raw = client(payload)
    except Exception as exc:
        logger.debug("series priority call failed: %s", exc, exc_info=True)
        return PriorityOutcome(None, reason=f"{PRIORITY_REASON_ERROR}: {exc}")

    decision = _response_dict(raw)
    if decision is None:
        return PriorityOutcome(None, reason=PRIORITY_REASON_MALFORMED)
    try:
        outcome = _decide(decision, aliases)
    except Exception:
        logger.debug("series priority decision failed", exc_info=True)
        return PriorityOutcome(None, reason=PRIORITY_REASON_MALFORMED)

    if key and outcome.reason != PRIORITY_REASON_MALFORMED:
        try:
            cache_obj.put(key, outcome.priorities, reason=outcome.reason)
        except Exception:
            logger.debug("series priority pin failed", exc_info=True)
    return outcome


def route_series_priority(
    series_list,
    *,
    mode: str,
    client: PriorityClient,
    cache=None,
    base_url: str = "",
    profile,
):
    """``{series_id: priority 1..N}`` or ``None`` when it must degrade. Never raises."""
    return route_series_priority_detailed(
        series_list,
        mode=mode,
        client=client,
        cache=cache,
        base_url=base_url,
        profile=profile,
    ).priorities


__all__ = [
    "PRIORITY_REASON_EMPTY",
    "PRIORITY_REASON_ERROR",
    "PRIORITY_REASON_LOW_CONFIDENCE",
    "PRIORITY_REASON_MALFORMED",
    "PRIORITY_REASON_NOUL",
    "PRIORITY_REASON_NO_PROFILE",
    "PriorityOutcome",
    "build_priority_request",
    "build_series_signals",
    "make_client",
    "priority_cache_key",
    "route_series_priority",
    "route_series_priority_detailed",
]
