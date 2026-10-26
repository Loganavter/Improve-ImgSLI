"""Disk cache for AI analysis results.

Keyed like ``thumbnail_cache`` (sha256 of ``path:mtime_ns``) **plus the analysis
identity** — the AI configuration that produced the scorecard — so re-opening a
folder never re-spends API credits and an edited file is correctly treated as
not-yet-analyzed, while switching the backend (model / base_url / mode /
reasoning effort / prompt schema / sampling) is a MISS instead of a stale result.

WHY the identity is part of the key (the bug this fixes): the key used to be
``(path, mtime_ns)`` only, so after switching model or base_url
``use_cases/ai_analysis.analyze_item`` served the PREVIOUS backend's scorecard
from disk before it had even read ``AiSettings`` — the gallery showed another
model's judgment against the new one.

The PROFILE is deliberately NOT part of the key any more (queue rows
``task-analysis-phase-state`` / ``task-profile-freeze-before-vlm-answer``,
2026-10-26). It used to be, and that inverted the pipeline: opening a folder paid
a VLM axis-set call FIRST, the answer became part of the cache identity, and
because the heuristic offer was never pinned the same image keyed differently on
the next run — measured 3 HIT / 7 MISS over 10 images whose 10 entries were
already on disk. The identity now describes the QUESTION ("which backend, which
mode, which sampling, which prompt revision") and the entry RECORDS the answer it
was built with (``"profile"``: the axes + their source), so a reader knows which
instrument produced the numbers without the axis set re-keying the file.

Consequence, stated as the contract: changing the axis set is served from the
existing entry (the recorded profile says which axes it answered). Turning the
heuristic offer into a VLM-chosen one is therefore an EXPLICIT invalidation
(``use_cases/cache_reset`` — "Reset metrics cache"), never an accidental churn.

Defence in depth: the identity is ALSO written into the JSON payload and validated
on load, so a key collision, a hand-copied file or a truncated write can still
never return a foreign result.

Old entries are MISSES, deliberately with no migration: a file written before the
identity was part of the key carries no ``identity`` field (and an older
``version``), and new entries use identity-suffixed filenames — so such a file is
never read, and reading one never raises. It simply stays on disk (invisible)
until ``clear_all`` / the gallery's "Reset metrics cache" deletes it.

The identity never contains secrets: ``api_key`` is excluded from the key and
from the cached JSON (the scorecard is not a credential store).

Sampling depth (``effective_k``) is part of the identity but NOT of the filename
discriminator: a REQUEST's identity carries its full budget in ``effective_k``
(the declared cap), while a STORED payload carries the number of draws that
actually produced the scorecard (the adaptive stop may settle early). A stored
entry thinner than the request's budget is a MISS — a 1-draw scorecard is never
served for a cap-3 request — while the same configuration at the same or a
larger depth is a HIT. ``k`` stays the declared cap, so the two are never
conflated.

Stage 3: VLM tie-breaks / compare briefs are cached alongside this file via
``tabs.image_gallery.services.vlm_cache`` (key = hash(paths+mtime), one per
pair). Filtering (``filtering.py``) now searches both analysis tags and brief
tags — see ``vlm_cache.find_briefs_for_path``.

Audit-Meta: pattern=wire-cache size=exempt reason="one cache contract: the analysis identity (model/base_url/mode/profile/effort + the P3 sampling config) and the payload that must carry it cannot be split without letting one side drift — the file grew past 500 lines with the sampling fields + proposed-axis persistence of plan-gallery-ai-judgement P3 and stays cohesive"
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from tabs.image_gallery.models import (
    AXIS_DIRECTION_DEFAULT,
    AiAnalysisResult,
    ai_scored_axes,
)
from tabs.image_gallery.services.thumbnail_cache import cache_key_for
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Payload format version. v3 = the analysis identity is part of the file key AND
#: stored/validated inside the payload (plan-gallery-ai-backend-owns-quality).
#: History: v2 = the open per-axis scorecard (``axes``), the VLM's OWN numbers;
#: a v1 entry (pre-scorecard) stored ``sharpness``/``noise``/``exposure`` written
#: by the old ``controller._merge_measured_metrics`` — i.e. LOCAL DETECTOR values,
#: not the VLM's. Serving those as the AI-domain read would be a provenance lie,
#: so an older-than-current entry is treated as a cache MISS and re-analyzed.
#: v4 = the identity carries ``effective_k`` (how many draws actually produced
#: the scorecard, vs the request's declared cap): a pre-v4 entry cannot say its
#: depth, so it must not be served for a budgeted request.
#: v5 = the profile LEFT the identity and is recorded in the payload instead
#: (``"profile"``: axes + judged names + source). A v4 entry has its axis set
#: baked into the FILE NAME, so it is unreachable by construction; the version
#: bump states the shape change (a payload without the recorded profile could
#: not answer "which axes do these numbers describe").
AI_CACHE_VERSION = 5

#: Prompt/schema revision of the analyze request. Bump this whenever the prompt
#: text or the expected response schema changes: every cached scorecard becomes a
#: MISS (it answered a different question), which is the intended invalidation of
#: the AI disk cache. Part of :func:`analysis_cache_identity`.
#: History: v1 = the per-axis scorecard; v2 (P3) = the scorecard plus
#: ``axis_proposals`` and no local-measurement echo in the prompt (P3-B/P3-E);
#: v3 (P4) = the keep/reject verdict field is gone and the assessment prose is
#: stored as ``reason`` (plan-gallery-ai-judgement P4/D4); v4 (P7-B) = the
#: scorecard keeps the axes the JUDGE named (free names) and carries the k draw
#: scorecards — an entry written by the pre-P7-B parser answered the same
#: question but lost every free axis' number, so it must not be served.
PROMPT_SCHEMA_VERSION = 4

#: The identity fields that define "the same analysis". Order is the canonical
#: JSON order. Anything else on a passed mapping (notably ``api_key``) is dropped:
#: the identity is compared, hashed into the filename and stored in the payload,
#: so it must never carry a secret.
#:
#: ``k`` / ``temperature`` / ``seed`` are the SAMPLING configuration (plan P3-D /
#: gate GA4): one sample of a stochastic judge is not a measurement, so a k=1
#: scorecard and the median of k=3 must never share an entry — "reproducible
#: within a stated tolerance" is only checkable if the draw is identified.
#:
#: ``effective_k`` is the DEPTH of that sampling: the request declares its full
#: budget there (the cap), a stored payload records how many draws actually
#: produced the scorecard. It is compared directionally (a stored depth thinner
#: than the request's budget is a MISS) and deliberately excluded from the
#: filename digest, so ONE entry per configuration is re-used at the depth it
#: actually reached.
#:
#: The PROFILE is NOT here (2026-10-26, ``task-analysis-phase-state``): the axis
#: set is the ANSWER this cache stores, not part of the question. A profile that
#: is resolved after the probe (or re-rolled by an unpinned heuristic offer) must
#: not re-key an entry that already answers "what does this backend see in this
#: file". The entry carries the producing profile in ``"profile"`` instead (see
#: :func:`profile_record` / :func:`recorded_profile`).
_IDENTITY_FIELDS = (
    "model",
    "base_url",
    "mode",
    "reasoning_effort",
    "k",
    "effective_k",
    "temperature",
    "seed",
    "prompt_schema_version",
)

#: Fields that are textual; the rest are normalized per-field below.
_TEXT_IDENTITY_FIELDS = (
    "model",
    "base_url",
    "mode",
    "reasoning_effort",
    "k",
    "effective_k",
    "temperature",
    "seed",
)

#: Public name of the KEY fields (what defines "the same analysis"). A reader that
#: needs to show/compare the identity without the recorded profile uses this
#: instead of hard-coding the list (the payload stores exactly these keys).
IDENTITY_FIELDS: tuple[str, ...] = _IDENTITY_FIELDS

#: Default draw count when the caller DOES read settings but the field is
#: missing: the user's declared ceiling (``AiSettings.sample_count``). One
#: sample of a stochastic judge is not a measurement, so the multiplier is
#: never taken silently — k>1 is a declared setting and the trace states its
#: cost.
DEFAULT_SAMPLE_COUNT = 3

#: Declared draw budget when the caller passes NO settings at all. The identity
#: must not claim a budget nobody read: a fabricated k=3 would key its own entry
#: shape and would declare a need the request never had. ONE is the only honest
#: claim, and as a *request* it accepts any scorecard that at least one draw
#: produced.
UNKNOWN_SAMPLE_COUNT = 1

#: Defaults for the optional sampling knobs (0 = "not sent", the backend's own
#: default draw). They are part of the identity even when unset, so the shape of
#: an identity never depends on whether a value was passed.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEED = 0


def _number_token(value, default, *, cast=float) -> str:
    """Canonical text for a numeric identity field (``str(default)`` when bad)."""
    try:
        number = cast(value)
    except (TypeError, ValueError):
        number = cast(default)
    if cast is float:
        return f"{float(number):.2f}"
    return str(int(number))



def ai_cache_dir() -> Path:
    from services.io.project_package import cache_kind_dir

    root = cache_kind_dir("gallery_ai_cache")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _clean_text(value) -> str:  # type: ignore[no-untyped-def]
    """``str(value)`` stripped, or ``""`` — never raises."""
    try:
        return str(value or "").strip()
    except Exception:
        return ""


def _identity_token(value) -> str:  # type: ignore[no-untyped-def]
    """A stable lowercase token for a str-backed enum / plain string.

    ``state.mode`` is a ``Mode(str, Enum)`` (its ``str()`` is ``"Mode.CAMERA"``)
    while restored/legacy state may hold the plain ``"camera"`` — both must map
    to the same token, or the same configuration would key two entries (measured
    2026-10-26 while wiring the folder probe: one side built ``"mode.camera"``
    and the other ``"camera"``, so a fully cached folder looked empty to the
    probe). So a str-SUBCLASS carrying a ``value`` uses that value; a plain
    ``str`` keeps itself.
    """
    try:
        enum_value = getattr(value, "value", None)
        if enum_value is not None and (
            not isinstance(value, str) or type(value) is not str
        ):
            value = enum_value
    except Exception:
        pass
    return _clean_text(value).lower()


def _profile_axis_ids(profile) -> tuple[str, ...]:  # type: ignore[no-untyped-def]
    """The profile's axis SET, in profile order — never raises.

    Accepts a ``MetricProfile``, a bare sequence of axis ids, or ``None``. This is
    the SET a scorecard answers (registry ids, then the axes the JUDGE NAMED as
    ``name~<digest>``, the digest covering the definition/scale/direction the
    prompt TEXT carries).

    It is RECORDED with the entry (:func:`profile_record`), never keyed: see the
    module docstring for why the profile left the cache identity on 2026-10-26.
    """
    try:
        ids = getattr(profile, "axis_ids", None)
        if ids is None:
            ids = profile if isinstance(profile, (tuple, list, set, frozenset)) else ()
        out: list[str] = []
        for axis in ids:
            token = _identity_token(axis)
            if token and token not in out:
                out.append(token)
        for entry in getattr(profile, "axis_entries", ()) or ():
            name = _identity_token(getattr(entry, "name", ""))
            if not name:
                continue
            text = "|".join(
                _identity_token(getattr(entry, field, ""))
                for field in ("definition", "scale", "direction")
            )
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
            token = f"{name}~{digest}"
            if token not in out:
                out.append(token)
        return tuple(out)
    except Exception:
        return ()


def profile_record(profile) -> dict[str, object] | None:  # type: ignore[no-untyped-def]
    """The profile a scorecard was built with, as READABLE metadata.

    NOT part of the cache key (see :data:`_IDENTITY_FIELDS`): stored BESIDE the
    identity so a reader can say which axes the numbers describe and which
    instrument produced the axis set. Two halves, two lists, exactly as
    ``metric_profile`` splits them:

    - ``axes`` — the registry ids a local detector can also produce;
    - ``judged`` — the names the judge itself gave to this series;
    - ``definitions`` — ``{name: definition}`` for those names (the axis'
      MEANING is what the prompt carried, so a redefinition is visible);
    - ``source`` — where the axis set came from (``vlm`` | ``series`` |
      ``heuristic``, the profile vocabulary — not a second one);
    - ``mode`` — the normalized mode the profile was derived for.

    ``None`` for an absent/unusable profile, so a provenance-free entry says so
    instead of inventing an axis list. Never raises.
    """
    if profile is None:
        return None
    try:
        if isinstance(profile, dict):
            return dict(profile) or None
    except Exception:
        return None
    try:
        ids = getattr(profile, "axis_ids", None)
        if ids is None:
            # A bare sequence of ids (tests / a legacy caller) is still a profile
            # worth recording — same tolerance as ``_profile_axis_ids``.
            ids = profile if isinstance(profile, (tuple, list, set, frozenset)) else ()
        ids = [
            str(axis).strip().lower()
            for axis in (ids or ())
            if str(axis).strip()
        ]
        judged = [
            str(getattr(entry, "name", "") or "").strip().lower()
            for entry in (getattr(profile, "axis_entries", ()) or ())
        ]
        judged = [name for name in judged if name]
        if not (ids or judged):
            return None
        definitions: dict[str, str] = {}
        for entry in getattr(profile, "axis_entries", ()) or ():
            name = str(getattr(entry, "name", "") or "").strip().lower()
            if not name:
                continue
            text = str(getattr(entry, "definition", "") or "").strip()
            if text:
                # Truncated: the record answers "which axis", not "quote the
                # prompt" — the full definition lives in the scorecard payload.
                definitions[name] = text[:160]
        return {
            "axes": ids,
            "judged": judged,
            "definitions": definitions,
            "source": _identity_token(getattr(profile, "source", "")),
            "mode": _identity_token(getattr(profile, "mode", "")),
        }
    except Exception:
        return None


def recorded_profile(identity) -> dict[str, object] | None:  # type: ignore[no-untyped-def]
    """The profile record carried by *identity* (``None`` when it carries none).

    The mapping returned by :func:`analysis_cache_identity` carries the producing
    profile under ``"profile"`` for the key-independent reasons in the module
    docstring; this is the ONE reader (``save_analysis`` stores what it returns).
    Never raises.
    """
    try:
        return profile_record(identity.get("profile"))  # type: ignore[union-attr]
    except Exception:
        return None


def analysis_cache_identity(
    settings=None,  # type: ignore[no-untyped-def]
    *,
    mode=None,  # type: ignore[no-untyped-def]
    profile=None,  # type: ignore[no-untyped-def]
    reasoning_effort=None,  # type: ignore[no-untyped-def]
    schema_version: int | None = None,
    k: int | None = None,
    temperature=None,  # type: ignore[no-untyped-def]
    seed=None,  # type: ignore[no-untyped-def]
    effective_k: int | None = None,
) -> dict[str, object]:
    """The cache identity of one analysis: "what produced this scorecard".

    ``settings`` is an ``AiSettings`` (or ``None``); ``mode`` the gallery mode the
    request was built for, ``profile`` the active ``MetricProfile``,
    ``reasoning_effort`` the effort sent with the request (defaults to
    ``settings.reasoning_effort``), ``schema_version`` the prompt revision
    (defaults to :data:`PROMPT_SCHEMA_VERSION`).

    The returned mapping has two kinds of keys, and the difference is the
    contract:

    - the KEY fields (:data:`_IDENTITY_FIELDS`) — model, base_url, mode, effort,
      sampling (k/temperature/seed), the sampling depth and the prompt revision.
      They are compared and hashed into the filename, so they define "the same
      analysis".
    - ``"profile"`` — the axis set this request asks about, as a RECORD
      (:func:`profile_record`). It is NOT compared, NOT hashed and NOT part of
      the payload identity: the axis set is the ANSWER, and re-rolling it must
      not re-key an entry (see the module docstring). It travels here because the
      identity is the ONE object every cache touch already carries, so the entry
      can record what page it answered without a second parameter through
      ``ai_analysis``.

    ``k`` / ``temperature`` / ``seed`` are the sampling configuration (plan P3-D,
    gate GA4). They default to the ``AiSettings`` values and are always PRESENT
    in the returned mapping, so "how many draws produced this scorecard" can
    never be unknown. ``k`` is the DECLARED CAP (the user's picker); with no
    settings passed the cap is unknown and declared as
    :data:`UNKNOWN_SAMPLE_COUNT` (ONE) rather than fabricated.

    ``effective_k`` is the sampling depth: a REQUEST's identity carries the full
    budget it needs there (default = the cap), while :func:`save_analysis`
    rewrites it in the stored payload to the number of draws that actually
    produced the scorecard (the adaptive stop may settle early). A stored depth
    thinner than the request's budget is a MISS — see the module docstring.
    Both tokens are canonicalized the same way (``k`` semantics), so a caller
    can never smuggle "3 draws" past the comparison as ``3.0``/``" 3"``.

    Stable, JSON-serializable and comparable: the same request configuration
    yields an equal dict. **``api_key`` is never part of it** — the identity is
    hashed into the filename and stored in the cache payload, so a secret would
    leak into both. Never raises; unknown fields are treated as absent.
    """
    effort = reasoning_effort
    if effort is None:
        effort = getattr(settings, "reasoning_effort", None)
    try:
        version = int(
            PROMPT_SCHEMA_VERSION if schema_version is None else schema_version
        )
    except Exception:
        version = PROMPT_SCHEMA_VERSION
    draws = k if k is not None else getattr(settings, "sample_count", DEFAULT_SAMPLE_COUNT)
    if k is None and settings is None:
        # No settings were read: declare the minimum depth instead of inventing
        # the user's cap (see UNKNOWN_SAMPLE_COUNT).
        draws = UNKNOWN_SAMPLE_COUNT
    heat = (
        temperature
        if temperature is not None
        else getattr(settings, "sampling_temperature", DEFAULT_TEMPERATURE)
    )
    drawn_seed = seed if seed is not None else getattr(settings, "sampling_seed", DEFAULT_SEED)
    try:
        draws = max(1, int(draws))
    except (TypeError, ValueError):
        draws = DEFAULT_SAMPLE_COUNT
    try:
        needed = max(1, int(draws if effective_k is None else effective_k))
    except (TypeError, ValueError):
        needed = draws
    identity: dict[str, object] = {
        "model": _clean_text(getattr(settings, "model", "")),
        "base_url": _clean_text(getattr(settings, "base_url", "")),
        "mode": _identity_token(mode),
        "reasoning_effort": _identity_token(effort) or "auto",
        "k": _number_token(draws, DEFAULT_SAMPLE_COUNT, cast=int),
        "effective_k": _number_token(needed, draws, cast=int),
        "temperature": _number_token(heat, DEFAULT_TEMPERATURE),
        "seed": _number_token(drawn_seed, DEFAULT_SEED, cast=int),
        "prompt_schema_version": version,
    }
    record = profile_record(profile)
    if record is not None:
        # Recorded, never keyed (see the docstring above and _IDENTITY_FIELDS).
        identity["profile"] = record
    return identity


def _effective_k_int(identity) -> int:  # type: ignore[no-untyped-def]
    """The declared/stored sampling depth of *identity*; ``0`` when unknown.

    ``0`` is deliberately THINNER than any request (every request declares at
    least 1 draw), so a payload that cannot state its depth is a miss rather
    than a silent hit. Never raises.
    """
    try:
        token = _clean_text(identity.get("effective_k"))  # type: ignore[union-attr]
    except Exception:
        return 0
    try:
        return max(1, int(float(token)))
    except (TypeError, ValueError):
        return 0


def _identity_dimensions(identity: dict[str, object]) -> dict[str, object]:
    """The identity WITHOUT ``effective_k`` — the request dimensions.

    ``effective_k`` is a depth claim, not a configuration: it is compared
    directionally in :func:`load_cached_analysis` (stored depth >= request
    budget) instead of for equality, and it is excluded from the filename
    digest for the same reason.
    """
    return {field: value for field, value in identity.items() if field != "effective_k"}


def _canonical_identity(identity) -> dict[str, object] | None:  # type: ignore[no-untyped-def]
    """Normalize an identity mapping to exactly ``_IDENTITY_FIELDS`` or ``None``.

    Used on BOTH sides (the expected identity and the stored payload), so the
    comparison is a plain ``==`` over the same normalization — a missing field, a
    non-mapping or an out-of-range version is "not this identity".
    """
    if not isinstance(identity, dict):
        return None
    out: dict[str, object] = {}
    for field in _TEXT_IDENTITY_FIELDS:
        out[field] = _clean_text(identity.get(field))
    try:
        out["prompt_schema_version"] = int(identity.get("prompt_schema_version"))
    except Exception:
        return None
    return out


def _identity_fingerprint(identity: dict[str, object], *, exclude=()) -> str:
    """Short stable digest of a canonical identity (the filename discriminator).

    ``exclude`` drops fields from the DIGEST only (they stay validated in the
    payload). ``effective_k`` is excluded: one configuration has ONE cached
    scorecard, and whether that entry is deep enough for the current request is
    decided by :func:`load_cached_analysis`, not by the filename.
    """
    canonical = {
        field: value for field, value in identity.items() if field not in exclude
    }
    dumped = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:16]


def _cache_path(path: Path, mtime_ns: int, identity) -> Path:  # type: ignore[no-untyped-def]
    """``<path:mtime hash>-<identity digest>.json``.

    The identity suffix keeps one entry per backend for the same image, so
    switching back to a previously used model hits its own scorecard again
    instead of overwriting the other one. ``effective_k`` is not in the digest
    (see :func:`_identity_fingerprint`) so a settled-thin entry and a full-depth
    request for the same configuration land on the SAME file and the payload
    check decides. A non-canonical identity raises ``ValueError`` — callers fail
    open to a miss / skip the write.
    """
    canonical = _canonical_identity(identity)
    if canonical is None:
        raise ValueError("incomplete analysis cache identity")
    return ai_cache_dir() / (
        f"{cache_key_for(path, mtime_ns)}-"
        f"{_identity_fingerprint(canonical, exclude=('effective_k',))}.json"
    )


def load_cached_analysis(
    path: Path, mtime_ns: int, identity  # type: ignore[no-untyped-def]
) -> AiAnalysisResult | None:
    """The cached scorecard for ``(path, mtime_ns)`` under ``identity``.

    A different identity is a MISS — never another backend's result. The payload
    must also carry the same identity (defence in depth), a current ``version``,
    and at least the sampling depth this request declares: a scorecard produced
    by fewer draws (the adaptive stop settled early, or an entry written before
    ``effective_k`` existed) is too thin to answer a deeper request and is a
    MISS. A pre-identity entry is a miss with no migration attempt. Never
    raises: any problem degrades to ``None`` (re-analyze).
    """
    try:
        cache_path = _cache_path(path, mtime_ns, identity)
    except Exception:
        return None
    if not cache_path.is_file():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        expected_identity = _canonical_identity(identity)
        stored_identity = _canonical_identity(data.get("identity"))
        if expected_identity is None or stored_identity is None:
            return None
        if _identity_dimensions(stored_identity) != _identity_dimensions(
            expected_identity
        ):
            # A foreign / legacy entry: the file key says it is ours, the payload
            # does not. Treat it exactly like a miss.
            return None
        if _effective_k_int(stored_identity) < _effective_k_int(expected_identity):
            # Adaptive sampling: a thin scorecard (e.g. one draw) must never be
            # served for a request that declared a larger budget.
            return None

        def _score(key: str) -> int:
            try:
                v = int(data.get(key, -1))
            except Exception:
                return -1
            return v if 0 <= v <= 100 else -1

        from tabs.image_gallery.models import AiDefect

        defects = []
        for d in data.get("defects", []) or []:
            try:
                if isinstance(d, dict):
                    defects.append(AiDefect(
                        kind=str(d.get("kind", "") or "other"),
                        severity=str(d.get("severity", "") or "mild"),
                        note=str(d.get("note", "") or ""),
                    ))
            except Exception:
                continue
        try:
            version = int(data.get("version", 1))
        except Exception:
            version = 1
        if version < AI_CACHE_VERSION:
            # Older format (v1 = detector values mislabelled as the AI read,
            # v2 = pre-identity keying): treat as a miss so the AI domain
            # re-analyzes with the current prompt and backend.
            return None
        # Open per-axis scorecard (the VLM's own numbers). The judge's free
        # names are validated against the entries stored WITH the payload
        # (P7-B): a cache HIT must keep every axis a MISS parsed, and a name
        # that was never asked is still dropped.
        from tabs.image_gallery.models import AXIS_DIRECTION_DEFAULT, AiAxisProposal

        judged: list[AiAxisProposal] = []
        for entry in data.get("axis_entries", []) or []:
            try:
                judged.append(
                    AiAxisProposal(
                        name=str(entry.get("name", "") or ""),
                        definition=str(entry.get("definition", "") or ""),
                        scale=str(entry.get("scale", "") or ""),
                        score=-1,
                        direction=str(entry.get("direction") or AXIS_DIRECTION_DEFAULT),
                    )
                )
            except Exception:
                continue
        try:
            from tabs.image_gallery.services.ai_client import _parse_axes

            axes: dict[str, int] = _parse_axes(
                data.get("axes"), allowed=tuple(e.name for e in judged)
            )
        except Exception:
            axes = {}
        samples: list[dict[str, int]] = []
        for draw in data.get("axis_samples", []) or []:
            try:
                samples.append({str(k): int(v) for k, v in dict(draw).items()})
            except Exception:
                continue

        proposals: list[AiAxisProposal] = []
        for entry in data.get("axis_proposals", []) or []:
            try:
                proposals.append(
                    AiAxisProposal(
                        name=str(entry.get("name", "") or ""),
                        definition=str(entry.get("definition", "") or ""),
                        scale=str(entry.get("scale", "") or ""),
                        score=int(entry.get("score", -1)),
                        # A v3 payload written before the direction field has no
                        # value: the owner default is the honest read, and a HIT
                        # must not hand the ranker a different axis than a MISS.
                        direction=str(
                            entry.get("direction") or AXIS_DIRECTION_DEFAULT
                        ),
                    )
                )
            except Exception:
                continue
        refusals: list[tuple[str, str]] = []
        for entry in data.get("axis_proposal_refusals", []) or []:
            try:
                refusals.append((str(entry[0]), str(entry[1])))
            except Exception:
                continue
        return AiAnalysisResult(
            description=data["description"],
            tags=tuple(data.get("tags", ())),
            model=data["model"],
            analyzed_at_iso=data["analyzed_at_iso"],
            sharpness=axes.get("sharpness", -1),
            noise=axes.get("noise", -1),
            exposure=axes.get("exposure", -1),
            composition=axes.get("composition", -1),
            axes=axes,
            reason=str(data.get("reason", "") or ""),
            defects=tuple(defects),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            axis_notes={
                str(k): str(v)
                for k, v in (data.get("axis_notes", {}) or {}).items()
                if str(v).strip()
            },
            axis_proposals=tuple(proposals),
            axis_proposal_refusals=tuple(refusals),
            axis_entries=tuple(judged),
            axis_samples=tuple(samples),
        )
    except Exception:
        logger.debug("Gallery AI cache read failed for %s", path, exc_info=True)
        return None


def _identity_signature(identity) -> str | None:  # type: ignore[no-untyped-def]
    """The canonical fingerprint of *identity*, or ``None`` when incomplete.

    Used to scope the "already checked" memo to the identity that produced it —
    never raises.
    """
    try:
        canonical = _canonical_identity(identity)
        return None if canonical is None else _identity_fingerprint(canonical)
    except Exception:
        return None


def _remember_checked(item, signature) -> None:  # type: ignore[no-untyped-def]
    """Memoize "hydrate was tried" on *item*, scoped to *signature*.

    Both attributes move together: ``_ai_cache_checked_identity`` is what makes
    a later populate re-read after an identity switch. Never raises.
    """
    try:
        item._ai_cache_checked = True
        item._ai_cache_checked_identity = signature
    except Exception:
        pass


def folder_cache_probe(items, identity) -> dict:  # type: ignore[no-untyped-def]
    """Which cards of ONE folder already answer *identity* — the folder gate.

    The measured defect this closes (2026-10-26, ``task-analysis-phase-state``):
    opening a folder paid a VLM profile call FIRST and only then asked the
    per-card cache, so a fully analyzed folder still spent a probe image and a
    round trip on every open (and, with the profile in the key, re-analyzed the
    whole folder). The question "is this folder done under this identity" is
    answerable BEFORE any paid step — the identity names the backend, the mode,
    the sampling and the prompt revision, never the profile — so the caller can
    stop at the probe.

    Returns ``{total, cached, complete, missing, results}``:

    - ``results`` maps ``str(path)`` → :class:`AiAnalysisResult` for every card
      that has an entry (loaded through the ONE acceptance rule, so the probe can
      never say "done" about an entry :func:`load_cached_analysis` would refuse);
    - ``missing`` lists the items without one (in input order);
    - ``complete`` is True only when every item has an entry (an empty folder is
      NOT complete: there is no analysis to be done).

    Never raises: any failure degrades to a miss (the caller re-analyzes).
    """
    try:
        members = list(items or ())
    except Exception:
        members = []
    results: dict[str, object] = {}
    missing: list = []
    for item in members:
        try:
            path = getattr(item, "path", None)
        except Exception:
            path = None
        hit = None
        try:
            hit = load_cached_analysis(path, int(getattr(item, "mtime_ns", 0) or 0), identity)
        except Exception:
            hit = None
        if hit is None:
            missing.append(item)
            continue
        try:
            results[str(path)] = hit
        except Exception:
            missing.append(item)
    return {
        "total": len(members),
        "cached": len(results),
        "complete": bool(members) and not missing,
        "missing": missing,
        "results": results,
    }


def recorded_profile_for(path: Path, mtime_ns: int, identity) -> dict | None:  # type: ignore[no-untyped-def]
    """The profile record of the cached entry for ``(path, mtime_ns)``, if any.

    The reader for "which axes do these numbers describe": the payload's
    ``"profile"`` record (axes + judged names + source + mode), independent of
    the current profile. ``None`` on a miss / an entry written before v5 or by a
    caller that passed no profile. Never raises.
    """
    try:
        cache_path = _cache_path(path, mtime_ns, identity)
    except Exception:
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        record = data.get("profile")
    except Exception:
        return None
    return profile_record(record) if isinstance(record, dict) else None


def hydrate_item(item, identity) -> bool:  # type: ignore[no-untyped-def]
    """Fill ``item.analysis`` from the disk cache only (no worker, no settings).

    ``identity`` is the caller's :func:`analysis_cache_identity` for the CURRENT
    AI configuration — a cached scorecard from another backend is a miss.

    The "already checked" memo (``_ai_cache_checked``) is scoped to the identity
    it was earned under (``_ai_cache_checked_identity``): a miss under a stale
    identity (domain/profile switch, re-pointed backend) must NOT poison a later
    read under the current one, while a repeat under the SAME identity stays
    free — callers invoke this on every overlay populate. Returns True when the
    item now carries an analysis. Never raises.
    """
    try:
        if getattr(item, "analysis", None) is not None:
            return True
        signature = _identity_signature(identity)
        if bool(getattr(item, "_ai_cache_checked", False)):
            if getattr(item, "_ai_cache_checked_identity", None) == signature:
                return False
            # Checked under a different identity: that verdict says nothing
            # about THIS configuration, so drop it and read again.
            try:
                item._ai_cache_checked = False
                item._ai_cache_checked_identity = None
            except Exception:
                pass
        cached = load_cached_analysis(item.path, item.mtime_ns, identity)
        if cached is None:
            _remember_checked(item, signature)
            return False
        try:
            from tabs.image_gallery.models import AnalysisStatus

            item.analysis = cached
            item.analysis_status = AnalysisStatus.DONE
            item.analysis_error = None
        except Exception:
            # Not a usable hit: leave the memo unset so a later populate retries
            # (a half-assigned item must not freeze the miss forever).
            return False
        _remember_checked(item, signature)
        return True
    except Exception:
        return False


def clear_cached_analysis(path: Path, mtime_ns: int, identity=None) -> bool:  # type: ignore[no-untyped-def]
    """Delete the disk scorecard(s) for one ``(path, mtime_ns)``. Never raises.

    With an ``identity`` only that backend's entry goes; without one every
    identity variant (plus a legacy pre-identity file) for the pair goes — the
    "Reset metrics cache" call site has no backend in hand and wants them all
    gone. True when at least one file was removed; a miss returns False (not an
    error).
    """
    try:
        if identity is not None:
            targets = [_cache_path(path, mtime_ns, identity)]
        else:
            base = cache_key_for(path, mtime_ns)
            directory = ai_cache_dir()
            targets = [
                directory / f"{base}.json",
                *sorted(directory.glob(f"{base}-*.json")),
            ]
    except Exception:
        return False
    removed = False
    for cache_path in targets:
        try:
            cache_path.unlink()
            removed = True
        except FileNotFoundError:
            continue
        except OSError:
            logger.debug("Gallery AI cache delete failed for %s", path, exc_info=True)
            continue
    return removed


def clear_all() -> int:
    """Delete every AI scorecard file; return the count deleted. Never raises.

    The gallery's "Reset metrics cache" default (whole pool): the AI domain
    re-analyzes from scratch instead of serving a stale scorecard. A missing
    directory contributes 0.
    """
    try:
        directory = ai_cache_dir()
    except Exception:
        return 0
    try:
        entries = sorted(Path(directory).glob("*.json"))
    except Exception:
        return 0
    deleted = 0
    for p in entries:
        try:
            p.unlink()
            deleted += 1
        except OSError:
            logger.debug("Gallery AI cache delete failed for %s", p, exc_info=True)
    return deleted


def save_analysis(
    path: Path,
    mtime_ns: int,
    result: AiAnalysisResult,
    identity,  # type: ignore[no-untyped-def]
) -> None:
    """Persist ``result`` under ``(path, mtime_ns, identity)``. Never raises.

    An incomplete identity skips the write (no entry is better than one that
    cannot be validated on load). ``api_key`` is not accepted by the identity, so
    it never reaches the JSON.

    ``identity`` is the REQUEST's identity (its ``effective_k`` is the declared
    budget). The stored payload records the depth actually reached instead: the
    number of draw scorecards the result was merged from (``axis_samples``, one
    row per draw; a single-draw result carries none and is depth 1). That stored
    depth is what :func:`load_cached_analysis` compares against a request.
    """
    try:
        canonical = _canonical_identity(identity)
        if canonical is None:
            logger.debug("Gallery AI cache write skipped: incomplete identity")
            return
        record = recorded_profile(identity)
        try:
            produced = len(getattr(result, "axis_samples", ()) or ())
        except Exception:
            produced = 0
        if produced:
            # The draws themselves say the depth: a merged k-draw result carries
            # one row per draw, and the adaptive stop may have spent fewer than
            # the request's cap.
            canonical["effective_k"] = _number_token(produced, 1, cast=int)
        # A result carrying NO draw rows states no depth (``merge_samples`` keeps
        # ``axis_samples`` empty for a single draw, which only happens when the
        # cap itself is 1): the request's declared budget — already in
        # ``effective_k`` — is the only claim available, so it is kept as-is.
        cache_path = _cache_path(path, mtime_ns, canonical)
    except Exception:
        logger.debug("Gallery AI cache write failed for %s", path, exc_info=True)
        return
    try:
        cache_path.write_text(
            json.dumps(
                {
                    "description": result.description,
                    "tags": list(result.tags),
                    "model": result.model,
                    "analyzed_at_iso": result.analyzed_at_iso,
                    "sharpness": result.sharpness,
                    "noise": result.noise,
                    "exposure": result.exposure,
                    "composition": result.composition,
                    "reason": result.reason,
                    "defects": [
                        {"kind": d.kind, "severity": d.severity, "note": d.note}
                        for d in (result.defects or ())
                    ],
                    "confidence": result.confidence,
                    "axis_notes": dict(result.axis_notes or {}),
                    #: The MERGED per-axis scorecard (``axes`` + the named
                    #: aliases, so a directly-built result's composition is not
                    #: lost) — the AI domain's read. Plus the format version
                    #: (v3 = identity-keyed scorecard contract) and the identity
                    #: itself, re-validated on load.
                    "axes": dict(ai_scored_axes(result)),
                    #: Axes the model proposed beyond the pool (P3-B): kept in
                    #: the payload so a cache HIT reaches the Jev vector with the
                    #: same named axes a fresh call would (and the refusals stay
                    #: visible as a recorded loss).
                    "axis_proposals": [
                        {
                            "name": p.name,
                            "definition": p.definition,
                            "scale": p.scale,
                            "score": p.score,
                            # The direction travels with the entry (P7-A): it is
                            # what stops a ranker from guessing which end is good.
                            "direction": getattr(p, "direction", ""),
                        }
                        for p in (getattr(result, "axis_proposals", ()) or ())
                    ],
                    "axis_proposal_refusals": [
                        [str(name), str(reason)]
                        for name, reason in (
                            getattr(result, "axis_proposal_refusals", ()) or ()
                        )
                    ],
                    #: The JUDGE-named axes this card answered (P7-B): name +
                    #: definition + scale + direction. Kept beside the numbers so
                    #: a HIT can re-validate the free names (and reach the ranker
                    #: with the same axis set a fresh call would).
                    "axis_entries": [
                        {
                            "name": p.name,
                            "definition": p.definition,
                            "scale": p.scale,
                            "direction": getattr(p, "direction", ""),
                        }
                        for p in (getattr(result, "axis_entries", ()) or ())
                    ],
                    #: The k draw scorecards the result was merged from (P3-D /
                    #: P7-B): the measured within-item spread, which the noise
                    #: floor reads. Empty for a single draw.
                    "axis_samples": [
                        {str(axis): int(score) for axis, score in dict(draw).items()}
                        for draw in (getattr(result, "axis_samples", ()) or ())
                    ],
                    "version": AI_CACHE_VERSION,
                    "identity": canonical,
                    #: The profile this scorecard was BUILT WITH (2026-10-26):
                    #: its registry axes, the judge's own names, the source that
                    #: chose them and the mode. NOT part of ``identity`` — the
                    #: axis set is the answer, not the question (module
                    #: docstring), so an entry stays valid when the profile is
                    #: re-derived; this record is what tells a reader which axes
                    #: the numbers describe.
                    "profile": record,
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.debug("Gallery AI cache write failed for %s", path, exc_info=True)
