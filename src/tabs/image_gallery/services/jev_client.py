"""AI-domain ranker: Jev (``typesafe/jev-router``) over the MEASURED vector.

On the *AI* judgment domain Jev **is** the ranker for a series (plan
``plan-gallery-rank-backends-2026-10-15`` §Goal 3). Jev is reachable over the
gallery's **existing** OpenAI-compatible seam — ``ai_client.call_sync`` posting
to ``<base_url>/chat/completions`` on OpenRouter — under the model id
``typesafe/jev-router`` ("TypeSafe: Jev Router"). There is deliberately **no
bespoke HTTP client** here: one transport, one retry/fallback idiom for the
whole gallery.

The request is a chat/completions call with a fixed **output contract** (a
system message: rank aliases or abstain) and a *user message* that is the
measured vector: the mode plus, per variant, an opaque alias (``img_N``) and the
0..100 score of every applicable MEASURED axis — **no image bytes, no paths**.
Jev answers with a Ranking / Choice / Noul decision (JSON in the assistant message).

Determinism (design, not a bug): the AI domain is explicitly non-deterministic;
reproducibility is bought by the **pin** (:mod:`tabs.image_gallery.services.jev_cache`).

Degrade contract (never silent, never partial):

- a decisive Choice/Ranking sets a full 1..N rank for the series when the
  confidence is acceptable — a *present* ``score >= JEV_MIN_CONFIDENCE``, or **no
  ``score`` at all when the decision itself is explicit** (the live
  ``typesafe/jev-router`` reply carries ``best``/``ranking`` but no confidence
  number — probe 2026-10-15);
- ``Noul`` / low confidence / HTTP error / malformed body / empty series returns
  ``None`` and a human-readable :attr:`JevRankOutcome.reason`; a vector that does
  not score every member of the series is refused the same way
  (:data:`JEV_REASON_INCOMPLETE`, plan-gallery-ai-judgement P1/M2) — a member
  the model was never shown cannot be ranked;
- the caller then keeps the Algorithms (fusion) rank and surfaces the reason. A
  failed Jev rank never fabricates a number and never re-ranks a subset.

No Qt; the transport (``client``) is injectable so tests are network-free. All
sync calls must run on a ``GenericWorker``, never the UI thread.
"""

# Audit-Meta: pattern=wire-client size=523 reason="one Jev rank seam: measured-vector request + decision parser + degrade contract + pin belong together — splitting scatters the wire contract"

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.ai_client import _ai_debug
from tabs.image_gallery.services.quality_read import AI_DOMAIN, normalize_domain
from tabs.image_gallery.services.rank_fusion import measured_axes_for, rank_series
from tabs.image_gallery.use_cases.pipeline_stages import rank_completeness

logger = logging.getLogger("ImproveImgSLI")

#: The Jev model id (OpenRouter), single definition for the whole tree. The
#: rank call is a plain chat/completions request with this model; the transport
#: stays :func:`ai_client.call_sync` (no second client, no bespoke endpoint).
JEV_MODEL = "typesafe/jev-router"

#: Idle-timeout (s) for a Jev rank call. The transport streams (idle, not total),
#: but the opaque router can still stall between steps (observed 7–37 s).
JEV_TIMEOUT_S = 60.0

#: Confidence gate: a *present* Score below this is indecisive. A decision with
#: no ``score`` is still decisive when explicit — the live router omits any
#: number (probe 2026-10-15), so requiring one degraded every real call.
JEV_MIN_CONFIDENCE = 0.5

#: Visible degrade reasons (English defaults; the caller logs / surfaces them).
JEV_REASON_NOT_CONFIGURED = "AI (Jev) is not configured — kept the Algorithms rank"
JEV_REASON_EMPTY = "AI (Jev): nothing to rank"
#: A vector that does not score EVERY member of the series: a rank built from it
#: would place a member that was never scored (live 2026-10-21: the last VLM
#: score arrived during the rank and ``img_6`` was ranked anyway). Benign — the
#: caller keeps the Algorithms rank; the next arriving score re-triggers.
JEV_REASON_INCOMPLETE = "AI (Jev): the series is incomplete — kept the Algorithms rank"
JEV_REASON_NOUL = "AI (Jev) abstained (Noul) — kept the Algorithms rank"
JEV_REASON_LOW_CONFIDENCE = "AI (Jev) was not confident enough — kept the Algorithms rank"
JEV_REASON_ERROR = "AI (Jev) request failed — kept the Algorithms rank"
JEV_REASON_MALFORMED = "AI (Jev) returned an unusable response — kept the Algorithms rank"

#: Degrade reasons that are a genuine FAULT, not a benign non-answer: a transport
#: error or an unconfigured client (plan §J1.4). A fault paints the per-card error
#: chip and keeps the readiness gate retryable (``ok=False``); a benign non-answer
#: (``Noul`` / low confidence / nothing to rank / malformed) clears the activity
#: and records completion — malformed is a deterministic "no usable answer", not
#: a transport fault, so it must not re-introduce the mass false-error chip.
JEV_FAULT_REASONS = (JEV_REASON_ERROR, JEV_REASON_NOT_CONFIGURED)


def reason_is_fault(reason: str | None) -> bool:
    """True when *reason* is a genuine fault (error chip + gate retry), not a
    benign non-answer. Prefix match: transport errors append the exception text
    after :data:`JEV_REASON_ERROR`."""
    text = str(reason or "")
    return any(text.startswith(prefix) for prefix in JEV_FAULT_REASONS)

#: A transport takes the chat/completions request and returns the parsed JSON
#: response. Injectable so tests never touch the network.
RankClient = Callable[[dict], dict]


@dataclass(frozen=True)
class JevRankOutcome:
    """One Jev series-rank attempt.

    ``ranks`` is ``{path: rank 1..N}`` when decisive, else ``None``.
    ``reason`` is a human-readable degrade cause (``None`` on a decisive
    answer); it is *always* set when ``ranks`` is ``None``. ``cached`` reports
    whether the pin served this attempt (no transport call).
    """

    ranks: dict[str, int] | None
    reason: str | None = None
    cached: bool = False
    #: Which tail completed a short model reply (J2, plan-gallery-ai-judgement
    #: P1): ``"model"`` = the reply itself named every alias, ``"deterministic"``
    #: = the remaining aliases were ordered by the measured fusion
    #: (``_tail_order``), ``""`` = no decision was consulted (cache hit /
    #: degrade). The controller traces it so the applied order states its source.
    tail: str = ""

    @property
    def decided(self) -> bool:
        return bool(self.ranks)


def _mode_token(mode: Any) -> str:
    """Normalize a ``Mode`` / str / None to the registry mode token."""
    value = getattr(mode, "value", mode)
    try:
        return str(value or "").strip().lower()
    except Exception:
        return ""


def _path_of(item) -> str:
    try:
        return str(getattr(item, "path", ""))
    except Exception:
        return ""


def _aliased(items) -> list[tuple[str, Any]]:
    """``[(alias, item)]`` — opaque ``img_N`` aliases, sorted by ``str(path)`` so
    the alias assignment (and thus the payload, cache key and ranks) never
    depends on caller order; one helper so :func:`build_rank_request` and the
    decision code cannot drift.
    """
    ordered = sorted(list(items or ()), key=_path_of)
    return [(f"img_{i}", item) for i, item in enumerate(ordered, start=1)]


def build_measured_vector(items, *, mode: str, domain: str = "algorithms", profile=None) -> dict:
    """The scoring vector: ``{"mode", "items": [{"alias","scores"}]}``.

    Each entry's ``scores`` holds exactly the applicable axes for *mode*
    (``rank_fusion.measured_axes_for``) that *item* actually carries a score for
    under *domain* — an unscored axis is omitted, never fabricated. On the AI
    domain the scores are the VLM's scorecard (``item.analysis``); on Algorithms
    they are the local detectors (``item.metrics``), via the single per-domain
    read (``services.quality_read``, plan-gallery-ai-backend-owns-quality). Only
    the mode, the opaque aliases and the numbers — never paths or images.

    ``profile`` (a ``metric_profile.MetricProfile``) overrides the mode-implied
    axes when given — the salience-derived subset (plan P1). ``None`` keeps the
    mode mapping, so every existing caller is unchanged (backward compatible).
    """
    mid = _mode_token(mode)
    axes = measured_axes_for(mid, profile=profile)
    entries: list[dict] = []
    for alias, item in _aliased(items):
        read: dict[str, int] = {}
        try:
            from tabs.image_gallery.services.quality_read import domain_axis_scores

            read = domain_axis_scores(item, domain=domain)
        except Exception:
            read = {}
        scores: dict[str, int] = {}
        for axis_id in axes:
            score = read.get(axis_id)
            if score is None:
                continue
            try:
                scores[axis_id] = int(score)
            except Exception:
                continue
        entries.append({"alias": alias, "scores": scores})
    return {"mode": mid, "items": entries}


#: Output contract, sent as the system message. The live ``typesafe/jev-router``
#: currently routes to a *chat* model that free-forms a narrative
#: ("summary/observations/next_steps") with no ranking at all when asked only for
#: a JSON object (probe 2026-10-15) — so the output shape must be constrained.
#: Carries no image bytes, no paths, no measured values: a format contract only.
JEV_SYSTEM_PROMPT = (
    "You rank items by their measured quality scores. Reply with ONLY a JSON "
    'object {"ranking": ["<alias>", ...]} ordering the aliases best to worst — '
    "a full ranking whenever at least two aliases carry scores (break near ties "
    'by your best judgement). Reply {"noul": true} only when fewer than two '
    "aliases carry scores. No prose."
)


def _request_from_vector(vector: dict) -> dict:
    """The chat/completions body for a prebuilt measured vector (one shape).

    Split out so :func:`rank_series_jev_detailed` can build the vector ONCE
    (readiness check + payload) and the contract shape is defined in a single
    place — the payload test and the wire call cannot drift.
    """
    text = json.dumps(vector, sort_keys=True, separators=(",", ":"))
    return {
        "model": JEV_MODEL,
        "messages": [
            {"role": "system", "content": JEV_SYSTEM_PROMPT},
            {"role": "user", "content": [{"type": "text", "text": text}]},
        ],
        "response_format": {"type": "json_object"},
    }


def build_rank_request(items, *, mode: str, domain: str = "algorithms", profile=None) -> dict:
    """OpenAI-compatible rank request for Jev (text-only, measured vector).

    A chat/completions body: ``model = JEV_MODEL``, ONE system message carrying
    the output contract (:data:`JEV_SYSTEM_PROMPT`) and ONE user message whose
    text part is the canonical JSON measured vector
    (:func:`build_measured_vector`) — no image parts, no file paths
    (``tests/test_jev_rank.py``). ``response_format={"type": "json_object"}`` **and**
    the contract pin the reply shape: without the contract the live router's chat
    model answered a narrative object with no ranking, so every call degraded as
    unusable (probe 2026-10-15); the parser still tolerates key/shape variance.
    ``profile`` (plan P1) forwards the salience-derived axis subset; ``None``
    keeps the mode mapping.
    """
    return _request_from_vector(
        build_measured_vector(items, mode=mode, domain=domain, profile=profile)
    )


def _normalize_alias(value: Any, aliases: dict[str, str]) -> str | None:
    """Map a response token to a known ``img_N`` alias (or ``None``).

    Tolerates ``"img_3"`` and a bare 1-based index (``3`` / ``"3"``); anything
    else (a path, free text, an unknown alias) is rejected so the rank can never
    be keyed to something outside the request.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        candidate = f"img_{value}"
        return candidate if candidate in aliases else None
    text = str(value or "").strip()
    if not text:
        return None
    if text in aliases:
        return text
    low = text.lower()
    if low in aliases:
        return low
    if low.startswith("img_"):
        low = low[4:]
    try:
        candidate = f"img_{int(low)}"
    except Exception:
        return None
    return candidate if candidate in aliases else None


def _coerce_content(value: Any) -> str:
    """Assistant message content as text (str or a list of text parts)."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for part in value:
            try:
                if isinstance(part, dict):
                    if part.get("type") in (None, "text", "output_text"):
                        parts.append(str(part.get("text", "")))
                    elif part.get("text"):
                        parts.append(str(part["text"]))
                elif isinstance(part, str):
                    parts.append(part)
            except Exception:
                continue
        return "".join(parts).strip()
    return ""


def _extract_object(text: str) -> dict | None:
    """Best-effort JSON object out of Jev's reply (fences / stray prose tolerated)."""
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw[:4].lower() == "json":
            raw = raw[4:].strip()
    start, end = raw.find("{"), raw.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None


def _response_dict(raw: Any) -> dict | None:
    """The decision object, from a chat/completions envelope or a bare decision."""
    if not isinstance(raw, dict):
        return None
    if any(
        key in raw
        for key in ("choice", "noul", "is_noul", "score", "ranking", "order", "ranks")
    ):
        return raw
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return _extract_object(_coerce_content(content))


def _score_of(raw: dict) -> float | None:
    """The decision's confidence number, or ``None`` when missing/unparseable."""
    for key in ("score", "confidence", "certainty"):
        if key not in raw:
            continue
        value = raw.get(key)
        if isinstance(value, bool) or value is None:
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def _is_noul(raw: dict) -> bool:
    """True when Jev explicitly abstained (``Noul``) rather than chose."""
    for key in ("noul", "is_noul", "abstain", "abstained"):
        if key in raw and bool(raw.get(key)):
            return True
    for key in ("choice", "winner", "best", "selected", "pick", "recommended"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip().lower() in ("noul", "none", "null"):
            return True
    return False


def _ranking_of(raw: dict) -> list[str] | None:
    """Explicit ordering from the decision, or ``None`` when absent: a list
    of aliases, a list of ``{"alias": ...}`` entries (the live "Jev Router"
    shape, probe 2026-10-15) or an ``alias -> rank`` mapping. The reply may name
    only the leading aliases (the live probe answered 2 of 6): unknown/duplicate
    entries are dropped by the caller, which completes the tail from the
    measured fusion — never from alias/path order (J2, plan P1).
    """
    for key in ("ranking", "order", "ordered", "ranked", "ranks"):
        value = raw.get(key)
        if isinstance(value, (list, tuple)):
            seq: list[str] = []
            for entry in value:
                if isinstance(entry, (str, int)) and not isinstance(entry, bool):
                    seq.append(str(entry))
                elif isinstance(entry, dict):
                    alias = entry.get("alias", entry.get("id"))
                    if isinstance(alias, (str, int)) and not isinstance(alias, bool):
                        seq.append(str(alias))
            if seq:
                return seq
        if isinstance(value, dict):
            pairs: list[tuple[int, str]] = []
            for alias, rank in value.items():
                try:
                    pairs.append((int(rank), str(alias)))
                except Exception:
                    continue
            if pairs:
                pairs.sort(key=lambda p: (p[0], p[1]))
                return [alias for _rank, alias in pairs]
    return None


def _choice_of(raw: dict) -> Any:
    for key in ("choice", "winner", "best", "selected", "pick", "recommended"):
        if key in raw:
            value = raw.get(key)
            if value not in (None, ""):
                return value
    return None


def _tail_order(members, *, mode: str, domain: str = "algorithms", profile=None) -> list[str]:
    """Deterministic score-ordered tail (aliases below the winner).

    BY SCORE, never by alias/``str(path)`` (J2, plan-gallery-ai-judgement P1).
    On the Algorithms domain the order is the fusion aggregate
    (``rank_fusion.rank_series``). The AI domain reads its numbers from
    ``item.analysis`` — the fusion aggregate reads ``item.metrics``, which the
    AI domain never fills, so it would degenerate to path order (the exact
    alphabetical tail this replaced); there the order comes from the same
    measured vector the request was built from (mean applicable score, path as
    the tie-break, unscored members last).
    """
    paths = sorted(_path_of(m) for m in members)
    if normalize_domain(domain) != AI_DOMAIN:
        try:
            fusion = rank_series(members, mode=mode, profile=profile)
        except Exception:
            fusion = {}
        return sorted(paths, key=lambda p: (fusion.get(p, 1 << 30), p))
    try:
        vector = build_measured_vector(
            members, mode=mode, domain=domain, profile=profile
        )
    except Exception:
        vector = {"items": []}
    alias_paths = {alias: _path_of(item) for alias, item in _aliased(members)}
    measured: list[tuple[float, str]] = []
    unmeasured: list[str] = []
    for entry in vector.get("items", ()) or ():
        try:
            path = alias_paths.get(str(entry.get("alias")), "")
            scores = list((entry.get("scores") or {}).values())
        except Exception:
            continue
        if not path:
            continue
        if not scores:
            unmeasured.append(path)
            continue
        measured.append((sum(scores) / len(scores), path))
    measured.sort(key=lambda pair: (-pair[0], pair[1]))
    return [p for _q, p in measured] + sorted(unmeasured)


def _decide(
    raw: dict, member_list, *, mode: str, domain: str = "algorithms", profile=None
) -> JevRankOutcome:
    """Turn one Jev decision into a decisive outcome or a degrade."""
    aliases = {alias: _path_of(item) for alias, item in _aliased(member_list)}
    if _is_noul(raw):
        return JevRankOutcome(None, reason=JEV_REASON_NOUL)

    # A confidence number is optional: gate only when Jev actually reports one.
    # An explicit decision (ranking/best) with no ``score`` is still decisive —
    # the live ``typesafe/jev-router`` reply omits ``score`` (probe 2026-10-15).
    score = _score_of(raw)
    if score is not None and score < JEV_MIN_CONFIDENCE:
        return JevRankOutcome(None, reason=JEV_REASON_LOW_CONFIDENCE)

    by_path = {alias: path for alias, path in aliases.items()}

    # Preferred: an explicit ranking from Jev. A reply that names only the top
    # aliases (the live probe answered 2 of 6) is completed by the measured
    # fusion (``_tail_order``), NEVER by alias/path order (J2, live 2026-10-21:
    # ``["img_5","img_4"]`` applied as ``1..6`` with the tail in ``str(path)``
    # order, i.e. an alphabetical tail promoted to a full ranking). The tail
    # used is recorded on the outcome so the trace can state it.
    raw_order = _ranking_of(raw)
    if raw_order is not None:
        seen: set[str] = set()
        order_paths: list[str] = []
        for entry in raw_order:
            alias = _normalize_alias(entry, aliases)
            if alias and alias not in seen:
                seen.add(alias)
                order_paths.append(by_path[alias])
        rest = [path for alias, path in aliases.items() if alias not in seen]
        tail = "model"
        if rest:
            tail = "deterministic"
            rest_paths = set(rest)
            order_paths.extend(
                p
                for p in _tail_order(
                    member_list, mode=mode, domain=domain, profile=profile
                )
                if p in rest_paths
            )
        ranks = {path: i for i, path in enumerate(order_paths, start=1)}
        return JevRankOutcome(ranks, tail=tail)

    # Otherwise: Jev picked the winner (Choice); the tail keeps the deterministic
    # measured order. This is still a COMPLETE 1..N assignment (never partial).
    winner = _normalize_alias(_choice_of(raw), aliases)
    if winner is None:
        return JevRankOutcome(None, reason=JEV_REASON_MALFORMED)
    winner_path = by_path[winner]
    tail_paths = [
        p
        for p in _tail_order(member_list, mode=mode, domain=domain, profile=profile)
        if p != winner_path
    ]
    ranks = {winner_path: 1}
    for i, path in enumerate(tail_paths, start=2):
        ranks[path] = i
    return JevRankOutcome(ranks, tail="deterministic")


def _pin(cache_obj, key: str, ranks: dict[str, int] | None, reason: str | None) -> None:
    try:
        cache_obj.put(key, ranks, reason=reason)
    except Exception:
        logger.debug("jev rank pin failed", exc_info=True)


def rank_series_jev_detailed(
    items, *, mode: str, client: RankClient, cache=None, domain: str = "algorithms", profile=None
) -> JevRankOutcome:
    """Jev-rank one series, returning the full :class:`JevRankOutcome`.

    This is the seam :func:`rank_series_jev` wraps: it carries the degrade
    *reason* the caller surfaces when the Algorithms rank is kept. Cache-first:
    a hit (including a pinned abstain) is returned without calling ``client``.
    A transport exception is caught, is **not** pinned (a later pass may retry),
    and degrades to ``None``.

    Precondition (plan §J1.3): a series is only a valid Jev question when **at
    least two members carry a non-empty applicable MEASURED vector**. A vector
    with fewer scored aliases degrades with :data:`JEV_REASON_EMPTY` and is
    **NOT pinned** — pinning a non-answer that arose from missing inputs would
    poison the cache and hide a later, complete run. ``profile`` (plan P1)
    selects the axes of that vector; ``None`` keeps the mode mapping. Never raises.
    """
    member_list = list(items or ())
    if len(member_list) < 2:
        return JevRankOutcome(None, reason=JEV_REASON_EMPTY)
    try:
        vector = build_measured_vector(member_list, mode=mode, domain=domain, profile=profile)
    except Exception:
        logger.debug("jev rank vector build failed", exc_info=True)
        return JevRankOutcome(None, reason=JEV_REASON_MALFORMED)
    scored, total, why = rank_completeness(member_list, vector)
    if scored < 2:
        _ai_debug("jev rank skip: measured vector has %d scored aliases (<2)", scored)
        return JevRankOutcome(None, reason=JEV_REASON_EMPTY)
    if scored < total:
        # Plan P1/M2: the ONE completeness decision (the same helper the
        # controller's dispatcher uses). A vector that does not score every
        # member must never become a rank — Jev would place a member it was
        # never shown (live 2026-10-21: img_6 ranked while its score arrived).
        _ai_debug(
            "jev rank skip: partial vector %d/%d scored (%s) — not ranked",
            scored, total, why,
        )
        return JevRankOutcome(None, reason=JEV_REASON_INCOMPLETE)
    payload = _request_from_vector(vector)

    cache_obj = cache if cache is not None else jev_cache.default_cache()
    try:
        key = jev_cache.rank_cache_key(member_list, payload)
    except Exception:
        key = ""
    if key:
        try:
            hit = cache_obj.get(key)
        except Exception:
            hit = None
        if hit is not None:
            _ai_debug("jev rank cache HIT items=%d", len(member_list))
            ranks = hit.get("ranks")
            if ranks:
                return JevRankOutcome({str(p): int(r) for p, r in ranks.items()}, cached=True)
            return JevRankOutcome(None, reason=hit.get("reason") or JEV_REASON_NOUL, cached=True)

    try:
        _vec = payload["messages"][-1]["content"][0]["text"]
    except Exception:
        _vec = "?"
    _ai_debug("jev rank vector: %.400s", _vec)
    _ai_debug("jev rank mode=%s items=%d (call)", _mode_token(mode), len(member_list))
    try:
        raw = client(payload)
    except Exception as exc:
        logger.debug("jev rank call failed: %s", exc, exc_info=True)
        _ai_debug("jev rank call failed: %s", exc)
        return JevRankOutcome(None, reason=f"{JEV_REASON_ERROR}: {exc}")

    decision = _response_dict(raw)
    if decision is None:
        _ai_debug("jev rank unusable response (no decision object)")
        return JevRankOutcome(None, reason=JEV_REASON_MALFORMED)

    try:
        outcome = _decide(
            decision, member_list, mode=mode, domain=domain, profile=profile
        )
    except Exception:
        logger.debug("jev rank decision failed", exc_info=True)
        return JevRankOutcome(None, reason=JEV_REASON_MALFORMED)

    # Pin both a decisive rank and an explicit abstain (stable re-runs); do not
    # pin a malformed response — it may be a transient backend glitch.
    _ai_debug("jev rank => decided=%s reason=%s", outcome.decided, outcome.reason)
    if key and outcome.reason != JEV_REASON_MALFORMED:
        _pin(cache_obj, key, outcome.ranks, outcome.reason)
    return outcome


def rank_series_jev(
    items, *, mode: str, client: RankClient, cache=None, domain: str = "algorithms", profile=None
) -> dict[str, int] | None:
    """``path -> rank 1..N`` from Jev, or ``None`` when it must degrade.

    ``None`` covers every non-decisive case (empty series, ``Noul``, confidence
    below :data:`JEV_MIN_CONFIDENCE`, HTTP error, malformed body) — the caller
    then keeps the Algorithms (fusion) rank and surfaces the reason from
    :func:`rank_series_jev_detailed`. ``profile`` (plan P1) forwards the
    selected axis subset. Never raises.
    """
    return rank_series_jev_detailed(
        items, mode=mode, client=client, cache=cache, domain=domain, profile=profile
    ).ranks


def make_client(base_url: str, api_key: str) -> RankClient:
    """Bind the rank transport to the **existing** ``ai_client.call_sync`` seam.

    Jev is OpenAI-compatible on OpenRouter (``typesafe/jev-router``): the request
    goes over ``<base_url>/chat/completions`` like every gallery AI call (one
    transport), but with ``JEV_TIMEOUT_S`` — router latency is opaque and observed
    over 30 s. Resolved via the module attr so tests monkeypatch ``call_sync``.
    """

    def _client(payload: dict) -> dict:
        from tabs.image_gallery.services import ai_client

        return ai_client.call_sync(base_url, api_key, payload, timeout=JEV_TIMEOUT_S)

    return _client


__all__ = [
    "JEV_FAULT_REASONS",
    "JEV_MIN_CONFIDENCE",
    "JEV_MODEL",
    "JEV_TIMEOUT_S",
    "JEV_REASON_EMPTY",
    "JEV_REASON_ERROR",
    "JEV_REASON_INCOMPLETE",
    "JEV_REASON_LOW_CONFIDENCE",
    "JEV_REASON_MALFORMED",
    "JEV_REASON_NOT_CONFIGURED",
    "JEV_REASON_NOUL",
    "JevRankOutcome",
    "build_measured_vector",
    "build_rank_request",
    "make_client",
    "rank_series_jev",
    "rank_series_jev_detailed",
    "reason_is_fault",
]
