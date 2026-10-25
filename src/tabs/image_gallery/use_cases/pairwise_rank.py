"""Pairwise ordering of a near-tie top set (board: pointwise cannot order near-ties).

Measured context (do not re-derive): across near-identical variants the
POINTWISE order flips 54-68% of the time depending on k, so more pointwise
draws are the wrong spend. Multimodal judges agree with humans far better in
PAIR comparisons (MLLM-as-a-Judge, ICML 2024) and the ORDER of the two items
changes the verdict (position bias, Shi et al. 2025) — hence every pair is asked
in BOTH orders and a swap disagreement is a TIE, never a win for either side.

Shape of the pass:

* only the top ``N`` (``AiSettings.pairwise_top_n``, default 5) take part, so the
  cost bound is ``N x (N-1)`` calls (each unordered pair asked twice);
* a DECIDED series spends zero calls — when the pointwise spread across the top
  set already exceeds ``AiSettings.pairwise_near_tie_threshold`` the pass is
  skipped entirely (item 3);
* the FREE gates (flag off / fewer than two measured members / undecided
  spread / decided) live in ONE function (:func:`precheck`), which the
  GUI-thread wiring asks before it schedules a worker: "start a thread or not"
  and the pass itself can never disagree about who may spend (the skip reason
  tokens are disabled, too_small, unmeasured and decided);
* the whole pass is one atomic ceiling reservation through
  ``judge_budget.reserve_pairwise_calls`` (the SAME run counter and ceiling as
  the pointwise cards) — a partial comparison set never produces an order;
* verdicts are cached under an UNORDERED pair of content keys plus the model,
  the prompt version and BOTH wire edges (the image is downscaled before
  sending), so ``(A,B)`` and ``(B,A)`` share one entry and two different pairs
  can never collide (item 4);
* the resulting order comes ONLY from complete comparisons (Copeland wins over
  the pairs; a swap disagreement scores half), and it is handed to
  ``rank_fusion.rank_series`` as an opt-in rank source, so the pointwise
  numbers stay visible and every caller that does not ask for pairwise keeps
  today's exact ordering (items 1-2).

Pure: no Qt, no HTTP on the default path. The judge is an injected callable
(``judge(a_item, b_item) -> "A" | "B" | "TIE" | None``), so the orchestration is
provable offscreen with a scripted judge; :class:`PairwiseClientJudge` is the
production adapter over the existing AI client transport.
"""

# Audit-Meta: pattern=pairwise-rank reason="one pairwise subsystem: the unordered verdict cache key, the swap verdict and the pass that spends against the shared judge ceiling cannot be split without letting the key and the reservation drift apart — a second module would recreate the same seam this task was scoped to have ONE of (board 2026-10-25)"

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from tabs.image_gallery.services.ai_client.prompt import (
    PAIRWISE_PROMPT_VERSION,
    _ai_debug,
)
from tabs.image_gallery.services.ai_settings_store import (
    PAIRWISE_NEAR_TIE_THRESHOLD_DEFAULT,
    PAIRWISE_NEAR_TIE_THRESHOLD_MAX,
    PAIRWISE_NEAR_TIE_THRESHOLD_MIN,
    PAIRWISE_TOP_N_DEFAULT,
    PAIRWISE_TOP_N_MAX,
    PAIRWISE_TOP_N_MIN,
)
from tabs.image_gallery.services.rank_fusion import item_quality

# -- claim vocabulary ---------------------------------------------------------

#: What the judge answered about the FIRST image of the presentation it saw.
#: Stored verbatim per order (the trace names both), never conflated: the
#: reverse answer is mapped back through its own presentation.
ANSWER_FIRST = "first"
ANSWER_SECOND = "second"
ANSWER_TIE = "tie"

_ANSWER_WORDS = {
    "a": ANSWER_FIRST,
    "first": ANSWER_FIRST,
    "1": ANSWER_FIRST,
    "b": ANSWER_SECOND,
    "second": ANSWER_SECOND,
    "2": ANSWER_SECOND,
    "tie": ANSWER_TIE,
    "equal": ANSWER_TIE,
    "same": ANSWER_TIE,
    "draw": ANSWER_TIE,
}


def normalize_answer(value) -> str | None:
    """``"A" | "B" | "TIE" | None`` (or the stored vocabulary) → claim token.

    ``None`` means NO usable verdict (unparseable/transport failure): the pair
    is unresolved, and an unresolved pair can never produce an order.
    """
    try:
        token = str(value or "").strip().lower()
    except Exception:
        return None
    return _ANSWER_WORDS.get(token)


@dataclass(frozen=True)
class PairVerdict:
    """One unordered pair, asked in BOTH orders.

    ``first``/``second`` are CONTENT keys in canonical (sorted) order, so a
    cached verdict always describes the same presentation pair regardless of
    which order the caller asked about. ``forward`` is the answer in the
    ``(first, second)`` presentation; ``reverse`` in ``(second, first)``.
    """

    first: str
    second: str
    forward: str | None = None
    reverse: str | None = None

    @property
    def resolved(self) -> bool:
        """True when BOTH orders produced an answer (a swap needs two)."""
        return self.forward is not None and self.reverse is not None

    @property
    def forward_winner(self) -> str | None:
        """Content key the forward presentation crowned (None for tie/none)."""
        if self.forward == ANSWER_FIRST:
            return self.first
        if self.forward == ANSWER_SECOND:
            return self.second
        return None

    @property
    def reverse_winner(self) -> str | None:
        """Content key the reverse presentation crowned, mapped back."""
        if self.reverse == ANSWER_FIRST:  # the reverse presentation showed ``second`` first
            return self.second
        if self.reverse == ANSWER_SECOND:
            return self.first
        return None

    @property
    def agree(self) -> bool:
        """True when the two orders name the SAME winner (tie included)."""
        if not self.resolved:
            return False
        return self.forward_winner == self.reverse_winner

    @property
    def winner(self) -> str | None:
        """Content key of the agreed winner; ``None`` for a tie."""
        if not self.agree:
            return None
        return self.forward_winner


# -- cache: one entry per UNORDERED pair --------------------------------------


@dataclass(frozen=True, order=True)
class PairKey:
    """Cache identity of one unordered pair.

    Content keys are sorted, so ``(A,B)`` and ``(B,A)`` produce the SAME key;
    each edge travels WITH its content key (an image is downscaled to its own
    wire edge before sending), and the model + prompt version separate
    judgements that answered different questions.
    """

    first: str
    first_edge: int
    second: str
    second_edge: int
    model: str
    prompt_version: int


def pair_key(
    first,
    first_edge,
    second,
    second_edge,
    *,
    model: str = "",
    prompt_version: int = PAIRWISE_PROMPT_VERSION,
) -> PairKey:
    """Canonical :class:`PairKey` — order-independent by construction."""
    try:
        edge_a = max(0, int(first_edge or 0))
    except (TypeError, ValueError):
        edge_a = 0
    try:
        edge_b = max(0, int(second_edge or 0))
    except (TypeError, ValueError):
        edge_b = 0
    a = (str(first or ""), edge_a)
    b = (str(second or ""), edge_b)
    if a[0] > b[0]:
        a, b = b, a
    try:
        version = int(prompt_version)
    except (TypeError, ValueError):
        version = PAIRWISE_PROMPT_VERSION
    return PairKey(a[0], a[1], b[0], b[1], str(model or ""), version)


class PairwiseVerdictCache:
    """Thread-safe verdict store keyed by :class:`PairKey`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[PairKey, PairVerdict] = {}

    def get(self, key: PairKey) -> PairVerdict | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: PairKey, verdict: PairVerdict) -> None:
        with self._lock:
            self._data[key] = verdict

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


#: Process-wide cache for the live path (tests inject a fresh one).
DEFAULT_CACHE = PairwiseVerdictCache()


# -- pure helpers -------------------------------------------------------------


def content_key(item) -> str:
    """Content identity of one gallery item (``resolved_path:mtime_ns``).

    The same convention as the gallery's other caches (``ai_cache`` /
    ``vlm_cache``): an edited file gets a new identity, so a stale verdict is
    never reused for different pixels. Never raises.
    """
    try:
        raw = str(getattr(item, "path", "") or "")
        path = str(Path(raw).expanduser().resolve()) if raw else ""
        mtime = int(getattr(item, "mtime_ns", 0) or 0)
        if mtime <= 0:
            try:
                mtime = int(Path(path).stat().st_mtime_ns)
            except Exception:
                mtime = 0
        return f"{path}:{mtime}"
    except Exception:
        return str(getattr(item, "path", "") or "")


def pairwise_calls_bound(top_n: int) -> int:
    """Upper bound of one pass: each of the ``n(n-1)/2`` pairs costs 2 calls."""
    try:
        n = max(0, int(top_n))
    except (TypeError, ValueError):
        n = 0
    return n * (n - 1)


def _side_content(answer: str | None, first: str, second: str) -> str | None:
    if answer == ANSWER_FIRST:
        return first
    if answer == ANSWER_SECOND:
        return second
    return None


def compare_pair(judge, member_a, member_b, *, on_call=None) -> PairVerdict:
    """Ask *judge* about the pair in BOTH orders; keep the raw claims.

    A transport/parse failure is ``None`` (unresolved), never a defaulted
    winner: inventing a side from a silent judge is the position-bias bug in
    reverse. ``on_call`` (optional) is told about every request actually sent.
    """
    forward = _ask(judge, member_a, member_b)
    if on_call is not None:
        on_call()
    reverse = _ask(judge, member_b, member_a)
    if on_call is not None:
        on_call()
    return PairVerdict(
        first=member_a.content,
        second=member_b.content,
        forward=forward,
        reverse=reverse,
    )


def _ask(judge, member_a, member_b) -> str | None:
    try:
        return normalize_answer(judge(member_a.item, member_b.item))
    except Exception:
        return None


def copeland_order(members, verdicts) -> tuple[str, ...]:
    """Content keys ordered by WINS over the complete comparison set.

    A win scores 1, a swap-disagreement (tie) scores half for each side, so a
    cycle degrades to a deterministic score order instead of crashing or
    inventing a transitive winner. Equal scores break by content key (never by
    the pointwise number: the pairwise order may not be produced from it).
    """
    scores: dict[str, float] = {member.content: 0.0 for member in members}
    for verdict in verdicts:
        if not verdict.resolved:
            continue
        winner = verdict.winner
        if winner is None:
            scores[verdict.first] = scores.get(verdict.first, 0.0) + 0.5
            scores[verdict.second] = scores.get(verdict.second, 0.0) + 0.5
        else:
            scores[winner] = scores.get(winner, 0.0) + 1.0
    return tuple(sorted(scores, key=lambda key: (-scores[key], key)))


# -- the pass -----------------------------------------------------------------


@dataclass(frozen=True)
class PairMember:
    """One member of the compared top set (content identity + display path)."""

    content: str
    path: str
    quality: float | None
    item: object = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class PairwiseOrder:
    """Result of one pass. ``applied`` is the ONLY permission to reorder."""

    applied: bool
    reason: str
    members: tuple[PairMember, ...] = ()
    verdicts: tuple[PairVerdict, ...] = ()
    order: tuple[str, ...] = ()  # content keys, pairwise-derived (empty unless applied)
    order_paths: tuple[str, ...] = ()  # what ``rank_series(pairwise_order=...)`` takes
    calls: int = 0
    cached: int = 0
    calls_bound: int = 0

    @property
    def pointwise(self) -> tuple[tuple[str, float | None], ...]:
        """The pointwise numbers, kept VISIBLE next to the pairwise order."""
        return tuple((member.path, member.quality) for member in self.members)

    @property
    def ties(self) -> int:
        """Pairs no one won: a swap disagreement or a mutual TIE."""
        return sum(1 for verdict in self.verdicts if verdict.winner is None)


@dataclass(frozen=True)
class _PassPlan:
    """Gates resolved before a single call: who is compared, and why not.

    ``skip`` is a finished :class:`PairwiseOrder` when the pass may not spend
    anything (already traced by ``_skip``); ``None`` means it may — the caller
    then builds the judge and reserves the bound.
    """

    row: object
    members: tuple[PairMember, ...]
    top_n: int
    threshold: float
    spread: float | None
    skip: PairwiseOrder | None


def _settings_row(owner, settings=None):
    """The ``AiSettings`` row for the pairwise knobs (None for a storeless double)."""
    if settings is not None:
        return settings
    try:
        store = getattr(owner, "_ai_settings_store", None)
        if store is None:
            return None
        return store.load()
    except Exception:
        return None


def _resolve_top_n(row, top_n=None) -> int:
    value = top_n
    if value is None:
        value = getattr(row, "pairwise_top_n", PAIRWISE_TOP_N_DEFAULT)
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = PAIRWISE_TOP_N_DEFAULT
    return max(PAIRWISE_TOP_N_MIN, min(PAIRWISE_TOP_N_MAX, n))


def _resolve_threshold(row, threshold=None) -> float:
    value = threshold
    if value is None:
        value = getattr(
            row, "pairwise_near_tie_threshold", PAIRWISE_NEAR_TIE_THRESHOLD_DEFAULT
        )
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = PAIRWISE_NEAR_TIE_THRESHOLD_DEFAULT
    if number != number:  # NaN
        number = PAIRWISE_NEAR_TIE_THRESHOLD_DEFAULT
    return max(PAIRWISE_NEAR_TIE_THRESHOLD_MIN, min(PAIRWISE_NEAR_TIE_THRESHOLD_MAX, number))


def _select_top(
    items, pointwise_ranks: Mapping[str, int], top_n: int, *, mode=None, profile=None
) -> list[PairMember]:
    """The ``top_n`` items with the best pointwise rank (path breaks ties).

    Each member carries its own pointwise quality — the NUMBER stays next to
    the pairwise order, it is never replaced by it.
    """
    ranked: list[tuple[int, str, object]] = []
    fallback = 1 << 30
    for item in items or ():
        try:
            path = str(getattr(item, "path", ""))
        except Exception:
            continue
        try:
            rank = int(pointwise_ranks.get(path))
        except (TypeError, KeyError, ValueError):
            rank = fallback
        ranked.append((rank, path, item))
    ranked.sort(key=lambda row: (row[0], row[1]))
    members: list[PairMember] = []
    for _rank, path, item in ranked[: max(0, top_n)]:
        try:
            quality = item_quality(item, mode=mode, profile=profile)
        except Exception:
            quality = None
        members.append(
            PairMember(
                content=content_key(item), path=path, quality=quality, item=item
            )
        )
    return members


def _skip(reason: str, members=(), *, top_n: int = 0, detail: str = "") -> PairwiseOrder:
    _ai_debug(
        "judge_pairwise.skip reason=%s top_n=%d members=%d %s",
        reason,
        top_n,
        len(members),
        detail,
    )
    return PairwiseOrder(applied=False, reason=reason, members=tuple(members))


def build_client_judge(row, *, mode=None, profile=None):
    """The production judge for *row*, or ``None`` when AI is not configured.

    Credentials/transport only: the pairwise question is a NEW prompt variant
    (``prompt.PAIRWISE_PROMPT_TEMPLATE``), never the pointwise scorecard.
    """
    if row is None:
        return None
    try:
        if not getattr(row, "enabled", False):
            return None
        if not getattr(row, "api_key", "") or not getattr(row, "model", ""):
            return None
    except Exception:
        return None
    try:
        return PairwiseClientJudge(
            base_url=str(getattr(row, "base_url", "") or ""),
            api_key=str(getattr(row, "api_key", "") or ""),
            model=str(getattr(row, "model", "") or ""),
            mode=mode,
            profile=profile,
        )
    except Exception:
        return None


class PairwiseClientJudge:
    """Blocking pairwise judge over the existing AI client transport.

    Call from a worker thread only (``GenericWorker`` upstream): ``judge``
    performs the blocking HTTP request. One wire copy per member is encoded
    ONCE and reused by ``edge_of`` and by every request, so the cache key states
    the SAME edge the provider actually received.
    """

    def __init__(self, *, base_url: str, api_key: str, model: str, mode=None, profile=None) -> None:
        self.base_url = str(base_url or "")
        self.api_key = str(api_key or "")
        self.model = str(model or "")
        self.mode = mode
        self.profile = profile
        self._wires: dict[str, object] = {}
        self._lock = threading.Lock()

    # -- wire ------------------------------------------------------------

    def _wire(self, path):
        key = str(path)
        with self._lock:
            cached = self._wires.get(key)
        if cached is not None:
            return cached
        from tabs.image_gallery.services.ai_client.request import encode_wire_path

        wire = encode_wire_path(Path(path))
        with self._lock:
            self._wires[key] = wire
        return wire

    def edge_of(self, _content: str, path=None) -> int:
        """The wire edge the provider received for this member (0 if unknown)."""
        if path is None:
            return 0
        try:
            return int(getattr(self._wire(path), "edge", 0) or 0)
        except Exception:
            return 0

    # -- judge -----------------------------------------------------------

    def build_request(self, path_a, path_b) -> dict:
        from tabs.image_gallery.services.ai_client.prompt import build_pairwise_prompt
        from tabs.image_gallery.services.vlm import (
            _apply_vlm_openrouter_hardening,
            _vlm_max_tokens,
        )

        wire_a = self._wire(path_a)
        wire_b = self._wire(path_b)
        prompt = build_pairwise_prompt(mode=self.mode, profile=self.profile)
        content: list[dict] = [
            {
                "type": "text",
                "text": f"{prompt}\nA: {Path(path_a).name}\nB: {Path(path_b).name}",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{wire_a.mime};base64,{wire_a.data_b64}"
                },
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{wire_b.mime};base64,{wire_b.data_b64}"
                },
            },
        ]
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": _vlm_max_tokens(2),
        }
        if "openrouter" in self.base_url.lower():
            return _apply_vlm_openrouter_hardening(payload)
        return payload

    def judge(self, item_a, item_b) -> str | None:
        """``"A" | "B" | "TIE" | None`` for the presentation (a, b)."""
        from tabs.image_gallery.services.ai_client import call_sync
        from tabs.image_gallery.services.ai_client.parse import (
            parse_pairwise_response,
        )

        payload = self.build_request(item_a.path, item_b.path)
        raw = call_sync(self.base_url, self.api_key, payload)
        return parse_pairwise_response(raw)


def _plan_pass(
    owner,
    items,
    *,
    pointwise_ranks: Mapping[str, int],
    settings=None,
    top_n: int | None = None,
    threshold: float | None = None,
    mode=None,
    profile=None,
) -> _PassPlan:
    """Resolve every gate that costs NOTHING: no judge, no reservation, no call.

    ONE place decides the order the gates run in, so the wiring (which asks
    "start a worker or not" on the GUI thread) and the pass itself can never
    disagree:

    1. ``pairwise_enabled`` off → skip reason disabled (no thread, no call);
    2. fewer than two MEASURED members in the top set → skip reason too_small;
    3. a member with no pointwise number → skip reason unmeasured (no defined
       spread);
    4. a spread above the declared threshold → skip reason decided (the
       pointwise order already separates them, so a comparison could only spend
       calls).
    """
    row = _settings_row(owner, settings)
    n = _resolve_top_n(row, top_n)
    near_tie = _resolve_threshold(row, threshold)
    members = tuple(_select_top(items, pointwise_ranks, n, mode=mode, profile=profile))
    measured = [member for member in members if member.quality is not None]

    if not bool(getattr(row, "pairwise_enabled", False)):
        skip = _skip("disabled", members, top_n=n)
        return _PassPlan(row, members, n, near_tie, None, skip)
    if len(measured) < 2:
        skip = _skip(
            "too_small", members, top_n=n, detail=f"measured={len(measured)}"
        )
        return _PassPlan(row, members, n, near_tie, None, skip)
    if len(measured) < len(members):
        skip = _skip("unmeasured", members, top_n=n, detail="pointwise spread unknown")
        return _PassPlan(row, members, n, near_tie, None, skip)
    spread = max(member.quality for member in measured) - min(
        member.quality for member in measured
    )
    if spread > near_tie:
        skip = _skip(
            "decided",
            members,
            top_n=n,
            detail=f"spread={spread:.2f} threshold={near_tie:g} calls=0",
        )
        return _PassPlan(row, members, n, near_tie, spread, skip)
    return _PassPlan(row, members, n, near_tie, spread, None)


def precheck(
    owner,
    items,
    *,
    pointwise_ranks: Mapping[str, int],
    settings=None,
    mode=None,
    profile=None,
    top_n: int | None = None,
    threshold: float | None = None,
) -> PairwiseOrder | None:
    """Would the pass spend anything? The FREE gates, on the caller's thread.

    Returns a skip outcome (already traced with ``judge_pairwise.skip
    reason=...``) when the pass must not start, or ``None`` when it may.
    :func:`run_pairwise_pass` asks the same question through the same
    :func:`_plan_pass`, so a caller can decide "schedule a worker or not"
    without a second copy of the rules — and without touching the network or
    the run's call ceiling from the GUI thread.
    """
    return _plan_pass(
        owner,
        items,
        pointwise_ranks=pointwise_ranks,
        settings=settings,
        top_n=top_n,
        threshold=threshold,
        mode=mode,
        profile=profile,
    ).skip


def run_pairwise_pass(
    owner,
    items,
    *,
    pointwise_ranks: Mapping[str, int],
    mode=None,
    profile=None,
    settings=None,
    judge=None,
    cache: PairwiseVerdictCache | None = None,
    top_n: int | None = None,
    threshold: float | None = None,
    model: str | None = None,
    prompt_version: int = PAIRWISE_PROMPT_VERSION,
    on_call=None,
) -> PairwiseOrder:
    """Compare the pointwise top ``N`` in BOTH orders and derive an order.

    Parameters are the frozen integration seams: *pointwise_ranks* is
    ``rank_series``' own output (so "top N" is the displayed order, never a
    second ranking), *settings* is the ``AiSettings`` row carrying
    ``pairwise_top_n`` / ``pairwise_near_tie_threshold`` / ``pairwise_enabled``,
    and every call is admitted through
    ``judge_budget.reserve_pairwise_calls`` (the run's ONE ceiling).

    Returns a :class:`PairwiseOrder`; ``.order_paths`` is only non-empty when
    EVERY pair produced both answers (``.applied``). A decided series, an
    unmeasured top set, a ceiling refusal, a missing answer or an unconfigured
    judge all leave the pointwise order intact and state why in the trace.
    ``judge=None`` builds :class:`PairwiseClientJudge` from the settings row.
    """
    plan = _plan_pass(
        owner,
        items,
        pointwise_ranks=pointwise_ranks,
        settings=settings,
        top_n=top_n,
        threshold=threshold,
        mode=mode,
        profile=profile,
    )
    if plan.skip is not None:
        return plan.skip
    row = plan.row
    members = plan.members
    n = plan.top_n
    near_tie = plan.threshold
    spread = plan.spread

    if judge is None:
        judge = build_client_judge(row, mode=mode, profile=profile)
        if judge is None:
            return _skip("not-configured", members, top_n=n)

    pairs = len(members) * (len(members) - 1) // 2
    bound = pairwise_calls_bound(len(members))
    store = cache if cache is not None else DEFAULT_CACHE
    model_id = str(model if model is not None else getattr(row, "model", "") or "")
    edge_for = getattr(judge, "edge_of", None)

    # Plan the pairs (and their cache keys) BEFORE spending anything: a cache
    # HIT costs no call and no budget, so only the misses are reserved.
    plan: list[tuple[PairMember, PairMember, PairKey, PairVerdict | None]] = []
    misses = 0
    for index, member_a in enumerate(members):
        for member_b in members[index + 1 :]:
            # Canonical presentation order: the cached verdict always describes
            # the (lower content key, higher content key) pair.
            first, second = (
                (member_a, member_b)
                if member_a.content <= member_b.content
                else (member_b, member_a)
            )
            key = pair_key(
                first.content,
                _edge(edge_for, first),
                second.content,
                _edge(edge_for, second),
                model=model_id,
                prompt_version=prompt_version,
            )
            cached_verdict = store.get(key)
            if cached_verdict is None:
                misses += 1
            plan.append((first, second, key, cached_verdict))

    from tabs.image_gallery.use_cases.judge_budget import reserve_pairwise_calls

    if not reserve_pairwise_calls(owner, misses * 2, settings=settings):
        _ai_debug(
            "judge_pairwise.incomplete reason=ceiling pairs=%d calls=%d "
            "order_kept=pointwise",
            pairs,
            misses * 2,
        )
        return PairwiseOrder(
            applied=False,
            reason="ceiling",
            members=tuple(members),
            calls_bound=bound,
        )

    _ai_debug(
        "judge_pairwise.plan top_n=%d pairs=%d misses=%d calls<=%d spread=%.2f "
        "threshold=%g",
        len(members),
        pairs,
        misses,
        bound,
        spread,
        near_tie,
    )

    verdicts: list[PairVerdict] = []
    calls = 0
    cached = 0

    def _count_call() -> None:
        nonlocal calls
        calls += 1
        if on_call is not None:
            try:
                on_call()
            except Exception:
                pass

    for first, second, key, cached_verdict in plan:
        verdict = cached_verdict
        from_cache = verdict is not None
        if verdict is None:
            verdict = compare_pair(judge, first, second, on_call=_count_call)
            if verdict.resolved:
                # An unresolved answer is NOT a verdict: never cache a
                # transport failure as a permanent tie.
                store.put(key, verdict)
        else:
            cached += 1
        verdicts.append(verdict)
        _ai_debug(
            "judge_pairwise.pair a=%s b=%s forward=%s reverse=%s agreement=%s "
            "winner=%s cached=%s",
            first.path,
            second.path,
            verdict.forward or "none",
            verdict.reverse or "none",
            verdict.agree,
            "tie" if verdict.winner is None else verdict.winner,
            from_cache,
        )

    unresolved = [verdict for verdict in verdicts if not verdict.resolved]
    if unresolved:
        _ai_debug(
            "judge_pairwise.incomplete reason=unanswered pairs=%d unanswered=%d "
            "calls=%d order_kept=pointwise",
            pairs,
            len(unresolved),
            calls,
        )
        return PairwiseOrder(
            applied=False,
            reason="incomplete",
            members=tuple(members),
            verdicts=tuple(verdicts),
            calls=calls,
            cached=cached,
            calls_bound=bound,
        )

    order = copeland_order(members, verdicts)
    path_by_content = {member.content: member.path for member in members}
    order_paths = tuple(path_by_content[content] for content in order if content in path_by_content)
    ties = sum(1 for verdict in verdicts if verdict.winner is None)
    _ai_debug(
        "judge_pairwise.order basis=pairwise pairs=%d ties=%d calls=%d cached=%d "
        "order=%s",
        pairs,
        ties,
        calls,
        cached,
        " > ".join(order_paths),
    )
    return PairwiseOrder(
        applied=True,
        reason="pairwise",
        members=tuple(members),
        verdicts=tuple(verdicts),
        order=order,
        order_paths=order_paths,
        calls=calls,
        cached=cached,
        calls_bound=bound,
    )


def _edge(edge_for, member: PairMember) -> int:
    """The wire edge for *member* (the provider's actual downscale)."""
    if callable(edge_for):
        try:
            return int(edge_for(member.content, member.path) or 0)
        except TypeError:
            try:
                return int(edge_for(member.content) or 0)
            except Exception:
                return 0
        except Exception:
            return 0
    try:
        from tabs.image_gallery.services.ai_client.request import resolve_wire_max_edge

        return int(resolve_wire_max_edge())
    except Exception:
        return 0


__all__ = [
    "ANSWER_FIRST",
    "ANSWER_SECOND",
    "ANSWER_TIE",
    "DEFAULT_CACHE",
    "PairKey",
    "PairMember",
    "PairVerdict",
    "PairwiseClientJudge",
    "PairwiseOrder",
    "PairwiseVerdictCache",
    "build_client_judge",
    "compare_pair",
    "content_key",
    "copeland_order",
    "normalize_answer",
    "pair_key",
    "pairwise_calls_bound",
    "precheck",
    "run_pairwise_pass",
]
