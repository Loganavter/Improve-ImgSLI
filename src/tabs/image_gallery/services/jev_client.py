"""AI-domain ranker: Jev (``typesafe/jev-router``) over the MEASURED vector.

On the *AI* judgment domain Jev **is** the ranker for a series (plan
``plan-gallery-rank-backends-2026-10-15`` §Goal 3). Jev is reachable over the
gallery's **existing** OpenAI-compatible seam — ``ai_client.call_sync`` posting
to ``<base_url>/chat/completions`` on OpenRouter — under the model id
``typesafe/jev-router`` ("TypeSafe: Jev Router"). There is deliberately **no
bespoke HTTP client** here: one transport, one retry/fallback idiom for the
whole gallery.

The request is a normal chat/completions call whose *user message* is the
measured vector: the mode plus, per variant, an opaque alias (``img_N``) and the
0..100 score of every applicable MEASURED axis — **no image bytes, no file
paths, no prose instruction**. Jev answers with a Choice / Noul / Score decision
(JSON in the assistant message).

Determinism note (design, not a bug): the AI domain is explicitly
non-deterministic — the same vector may get a different Choice. Reproducibility
is bought by the **pin** (:mod:`tabs.image_gallery.services.jev_cache`).

Degrade contract (never silent, never partial):

- a decisive Choice/Ranking sets a full 1..N rank for the series when the
  confidence is acceptable — a *present* ``score >= JEV_MIN_CONFIDENCE``, or **no
  ``score`` at all when the decision itself is explicit** (the live
  ``typesafe/jev-router`` reply carries ``best``/``ranking`` but no confidence
  number — probe 2026-10-15);
- ``Noul`` / low confidence / HTTP error / malformed body / empty series returns
  ``None`` and a human-readable :attr:`JevRankOutcome.reason`;
- the caller then keeps the Algorithms (fusion) rank and surfaces the reason. A
  failed Jev rank never fabricates a number and never re-ranks a subset.

No Qt; the transport (``client``) is injectable so tests are network-free. All
sync calls must run on a ``GenericWorker``, never the UI thread.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.metric_scores import raw_for, score_for, spec_for
from tabs.image_gallery.services.rank_fusion import measured_axes_for, rank_series

logger = logging.getLogger("ImproveImgSLI")

#: The Jev model id (OpenRouter), single definition for the whole tree. The
#: rank call is a plain chat/completions request with this model; the transport
#: stays :func:`ai_client.call_sync` (no second client, no bespoke endpoint).
JEV_MODEL = "typesafe/jev-router"

#: Transport timeout (s) for one Jev rank call: the router's latency is opaque
#: and observed 7–37 s (probe 2026-10-15) — over the 30 s ``call_sync`` default.
JEV_TIMEOUT_S = 60.0

#: Confidence gate: a *present* Score below this is indecisive. A decision with
#: no ``score`` is still decisive when explicit — the live router omits any
#: number (probe 2026-10-15), so requiring one degraded every real call.
JEV_MIN_CONFIDENCE = 0.5

#: Visible degrade reasons (English defaults; the caller logs / surfaces them).
JEV_REASON_NOT_CONFIGURED = "AI (Jev) is not configured — kept the Algorithms rank"
JEV_REASON_EMPTY = "AI (Jev): nothing to rank"
JEV_REASON_NOUL = "AI (Jev) abstained (Noul) — kept the Algorithms rank"
JEV_REASON_LOW_CONFIDENCE = "AI (Jev) was not confident enough — kept the Algorithms rank"
JEV_REASON_ERROR = "AI (Jev) request failed — kept the Algorithms rank"
JEV_REASON_MALFORMED = "AI (Jev) returned an unusable response — kept the Algorithms rank"

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
    """``[(alias, item)]`` — opaque ``img_N`` aliases in a deterministic order.

    Sorted by ``str(path)`` so the alias assignment (and therefore the payload,
    the cache key and the ranks) never depends on the caller's member order.
    One shared helper so :func:`build_rank_request` and the decision code cannot
    drift.
    """
    ordered = sorted(list(items or ()), key=_path_of)
    return [(f"img_{i}", item) for i, item in enumerate(ordered, start=1)]


def build_measured_vector(items, *, mode: str) -> dict:
    """The measured-only vector: ``{"mode", "items": [{"alias","scores"}]}``.

    Each entry's ``scores`` holds exactly the applicable MEASURED axes for
    *mode* (``rank_fusion.measured_axes_for``) that the item actually carries a
    raw value for — an unmeasured axis is omitted, never fabricated. Contains
    only the mode, the opaque aliases and the measured numbers.
    """
    mid = _mode_token(mode)
    axes = measured_axes_for(mid)
    entries: list[dict] = []
    for alias, item in _aliased(items):
        metrics = getattr(item, "metrics", None)
        scores: dict[str, int] = {}
        if isinstance(metrics, dict):
            for axis_id in axes:
                spec = spec_for(axis_id)
                if spec is None:
                    continue
                got = raw_for(spec, metrics)
                if got is None:
                    continue
                _key, raw = got
                try:
                    scores[axis_id] = int(score_for(spec, raw))
                except Exception:
                    continue
        entries.append({"alias": alias, "scores": scores})
    return {"mode": mid, "items": entries}


def build_rank_request(items, *, mode: str) -> dict:
    """OpenAI-compatible rank request for Jev (text-only, measured vector).

    A normal chat/completions body: ``model = JEV_MODEL`` and ONE user message
    whose text part is the canonical JSON measured vector
    (:func:`build_measured_vector`). No system prompt (no prose instruction), no
    image parts, no file paths — asserted by ``tests/test_jev_rank.py``.

    ``response_format={"type": "json_object"}`` pins the reply shape: without it
    the live ``typesafe/jev-router`` alternates prose / fenced-JSON / bare object
    (probe 2026-10-15); the parser still tolerates the key/shape variance.
    """
    vector = build_measured_vector(items, mode=mode)
    text = json.dumps(vector, sort_keys=True, separators=(",", ":"))
    return {
        "model": JEV_MODEL,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": text}]}
        ],
        "response_format": {"type": "json_object"},
    }


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
    """Explicit full ordering from the decision, or ``None`` when absent.

    Accepts a list of aliases, a list of ``{"alias": ...}`` entries (the live
    "Jev Router" shape, probe 2026-10-15), or an ``alias -> rank`` mapping.
    Unknown/duplicate entries are dropped by the caller, which appends any
    missing alias so the result is always a complete 1..N ordering.
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


def _tail_order(members, *, mode: str) -> list[str]:
    """Deterministic tail order (measured fusion) for aliases below the winner."""
    try:
        fusion = rank_series(members, mode=mode)
    except Exception:
        fusion = {}
    paths = sorted(_path_of(m) for m in members)
    return sorted(paths, key=lambda p: (fusion.get(p, 1 << 30), p))


def _decide(raw: dict, member_list, *, mode: str) -> JevRankOutcome:
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

    # Preferred: an explicit full ranking from Jev.
    raw_order = _ranking_of(raw)
    if raw_order is not None:
        seq: list[str] = []
        seen: set[str] = set()
        for entry in raw_order:
            alias = _normalize_alias(entry, aliases)
            if alias and alias not in seen:
                seq.append(alias)
                seen.add(alias)
        for alias in aliases:
            if alias not in seen:
                seq.append(alias)
                seen.add(alias)
        ranks = {by_path[alias]: i for i, alias in enumerate(seq, start=1)}
        return JevRankOutcome(ranks)

    # Otherwise: Jev picked the winner (Choice); the tail keeps the deterministic
    # measured order. This is still a COMPLETE 1..N assignment (never partial).
    winner = _normalize_alias(_choice_of(raw), aliases)
    if winner is None:
        return JevRankOutcome(None, reason=JEV_REASON_MALFORMED)
    winner_path = by_path[winner]
    tail = [p for p in _tail_order(member_list, mode=mode) if p != winner_path]
    ranks = {winner_path: 1}
    for i, path in enumerate(tail, start=2):
        ranks[path] = i
    return JevRankOutcome(ranks)


def _pin(cache_obj, key: str, ranks: dict[str, int] | None, reason: str | None) -> None:
    try:
        cache_obj.put(key, ranks, reason=reason)
    except Exception:
        logger.debug("jev rank pin failed", exc_info=True)


def rank_series_jev_detailed(
    items, *, mode: str, client: RankClient, cache=None
) -> JevRankOutcome:
    """Jev-rank one series, returning the full :class:`JevRankOutcome`.

    This is the seam :func:`rank_series_jev` wraps: it carries the degrade
    *reason* the caller surfaces when the Algorithms rank is kept. Cache-first:
    a hit (including a pinned abstain) is returned without calling ``client``.
    A transport exception is caught, is **not** pinned (a later pass may retry),
    and degrades to ``None``. Never raises.
    """
    member_list = list(items or ())
    if len(member_list) < 2:
        return JevRankOutcome(None, reason=JEV_REASON_EMPTY)
    try:
        payload = build_rank_request(member_list, mode=mode)
    except Exception:
        logger.debug("jev rank payload build failed", exc_info=True)
        return JevRankOutcome(None, reason=JEV_REASON_MALFORMED)

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
            ranks = hit.get("ranks")
            if ranks:
                return JevRankOutcome({str(p): int(r) for p, r in ranks.items()}, cached=True)
            return JevRankOutcome(None, reason=hit.get("reason") or JEV_REASON_NOUL, cached=True)

    try:
        raw = client(payload)
    except Exception as exc:
        logger.debug("jev rank call failed: %s", exc, exc_info=True)
        return JevRankOutcome(None, reason=f"{JEV_REASON_ERROR}: {exc}")

    decision = _response_dict(raw)
    if decision is None:
        return JevRankOutcome(None, reason=JEV_REASON_MALFORMED)

    try:
        outcome = _decide(decision, member_list, mode=mode)
    except Exception:
        logger.debug("jev rank decision failed", exc_info=True)
        return JevRankOutcome(None, reason=JEV_REASON_MALFORMED)

    # Pin both a decisive rank and an explicit abstain (stable re-runs); do not
    # pin a malformed response — it may be a transient backend glitch.
    if key and outcome.reason != JEV_REASON_MALFORMED:
        _pin(cache_obj, key, outcome.ranks, outcome.reason)
    return outcome


def rank_series_jev(items, *, mode: str, client: RankClient, cache=None) -> dict[str, int] | None:
    """``path -> rank 1..N`` from Jev, or ``None`` when it must degrade.

    ``None`` covers every non-decisive case (empty series, ``Noul``, confidence
    below :data:`JEV_MIN_CONFIDENCE`, HTTP error, malformed body) — the caller
    then keeps the Algorithms (fusion) rank and surfaces the reason from
    :func:`rank_series_jev_detailed`. Never raises.
    """
    return rank_series_jev_detailed(items, mode=mode, client=client, cache=cache).ranks


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
    "JEV_MIN_CONFIDENCE",
    "JEV_MODEL",
    "JEV_TIMEOUT_S",
    "JEV_REASON_EMPTY",
    "JEV_REASON_ERROR",
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
]
