"""Disk pin for VLM-selected metric profiles — plan P2/P3.

Key = ``sha256(sorted(path:mtime_ns) + mode + model + base_url + effort + pool
ids + prompt revision)`` — an edited member (mtime), a changed series membership
(path), a different mode/model, the SAME model id on another endpoint, a
different reasoning effort, a re-shaped pool or a bumped analyze prompt revision
all invalidate; an unchanged folder-generation is served from disk with **no
second VLM call**.

WHY the endpoint and the effort are part of the key (the bug this fixes): the
key used to stop at members+mode+model+pool, so pointing the same model id at a
different ``base_url`` (a provider switch — ``services/ai_providers``) silently
reused the PREVIOUS endpoint's selection: a pin earned from provider A's answer
was served as if provider B had chosen it. Both are inputs the VLM actually
sees, so both define "the same selection".

EVERY resolved profile is pinned, including the HEURISTIC / SERIES OFFER
(2026-10-26, ``task-profile-freeze-before-vlm-answer``). Before this, only the
judge's answer was written and the offer was re-derived on every pass, so the
same folder could resolve a different axis set from one run to the next — and
with the axis set in the analysis cache identity, every difference re-analyzed
the folder (measured 3 HIT / 7 MISS on 10 images with 10 entries on disk). One
folder now resolves ONE profile: the first pass pins whatever it resolved (with
its source), every later pass reads it back.

Consequence, stated as the contract: a pinned OFFER is not upgraded to a VLM
answer by a policy change — that is an EXPLICIT invalidation
(:meth:`ProfileCache.invalidate` / :func:`clear_default_cache`, wired to the
gallery's "Reset metrics cache"), never an accidental churn of the whole folder.

Old pins are MISSES, deliberately with no migration: a file written before the
endpoint/effort reached the key, or before the record carried the profile's
source, hashes/validates differently, so it is simply never read again. It stays
on disk until ``clear`` / the gallery's "Reset metrics cache" deletes it.

The AI domain is *explicitly non-deterministic* (the same request may answer
differently on a second identical run): the pin makes one run reproducible — a
folder is profiled once and every later pass over the same paths+mtimes+mode+
model+endpoint+effort+pool reuses that pinned selection, so flipping between
tabs/domains never re-rolls the dice. This mirrors
:mod:`tabs.image_gallery.services.jev_cache`
(one JSON file per key, version-gated, **no TTL**, malformed replies
deliberately **not** pinned as a VLM answer — the offer they fall back to IS
pinned, with its own source). Pure — no Qt, no HTTP. Small JSON IO, safe from
worker threads.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

from tabs.image_gallery.services.ai_providers import _url_key
from tabs.image_gallery.services.metric_profile import MEASURED_POOL, MetricProfile, mode_id
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Bump when the cached record shape changes (old pins stop matching). v2 adds
#: the judge's own axes (``axis_entries``, plan-gallery-ai-judgement P7-A): a
#: selection is name + definition + scale + direction, and a v1 record has no way
#: to carry a free axis — it is therefore an honest MISS, not a lossy read. The
#: endpoint/effort keying (queue ``task-ai-cache-identity-truth-2026-10-20``)
#: deliberately did NOT bump it: the record shape was unchanged and the key itself
#: already made old pins unreachable.
#: v3 (2026-10-26) records WHICH kind of answer was pinned — the judge's own axis
#: set (``vlm``) or the resolved offer (``series`` / ``heuristic``) — plus when
#: and why, because an offer is now pinned too. A v2 record cannot say whether
#: it is a paid answer or a fallback, so it is not served as one.
#: The analysis-backend adapter that OWNS this store (ADR 009 wave A4) — see
#: ``services.ai_cache.CACHE_NAMESPACE``.
CACHE_NAMESPACE = "ai"

PROFILE_CACHE_VERSION = 3

#: Cache directory name, stored alongside the Jev cache directory.
CACHE_DIR_NAME = "gallery_profile_cache"


def profile_cache_dir() -> Path:
    from services.io.project_package import cache_kind_dir

    root = cache_kind_dir(CACHE_DIR_NAME)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _item_path(item) -> str:
    try:
        return str(getattr(item, "path", ""))
    except Exception:
        return ""


def _item_mtime(item) -> int:
    try:
        return int(getattr(item, "mtime_ns", 0) or 0)
    except Exception:
        return 0


def _effort_token(effort) -> str:
    """A stable lowercase effort token (``""`` → ``auto``, as ``ai_cache`` does).

    ``reasoning_effort`` reaches the request, so it is part of the pin identity;
    an unset value and ``"auto"`` are the same configuration.
    """
    try:
        value = getattr(effort, "value", effort)
        return str(value or "").strip().lower() or "auto"
    except Exception:
        return "auto"


def profile_cache_key(
    items, *, mode, model, pool=None, base_url="", reasoning_effort=""
) -> str:
    """Stable pin identity: ``sha256(members + mode + model + endpoint + effort + pool
    + prompt revision)``.

    Members are sorted by path so the key is independent of the caller's member
    order; the mode is normalized to a registry id (``Mode.FIDELITY`` and
    ``"fidelity"`` pin the same profile); the pool defaults to the immutable
    ``MEASURED_POOL`` so a caller never has to pass it.

    ``base_url`` is normalized with the SAME key as the provider presets
    (``ai_providers._url_key``: trailing slashes, scheme/host case), so two
    spellings of one endpoint share a pin while a provider switch to a
    different endpoint cannot serve the old one. ``reasoning_effort`` is
    normalized to ``auto`` when unset. Both default to "" / "auto" for callers
    that legitimately have no backend in hand (tests, ``profile_fingerprint``
    defaults) — a production caller always passes the live settings.

    The ANALYZE prompt revision is part of the key (2026-10-26): a profile names
    axes that the scorecard prompt asks about, so a prompt change that alters what
    an axis means must not be paired with a pin earned under the old question. It
    is read from ``services.ai_cache`` (the one place that owns the revision), not
    passed in, so no caller can forget it and split the folder into two pins.
    """
    pool_ids = tuple(pool) if pool is not None else MEASURED_POOL
    try:
        ordered = sorted(list(items or ()), key=_item_path)
    except Exception:
        ordered = list(items or ())
    parts = [f"{_item_path(item)}:{_item_mtime(item)}" for item in ordered]
    parts.append(f"mode={mode_id(mode)}")
    parts.append(f"model={str(model or '')}")
    parts.append(f"base_url={_url_key(base_url)}")
    parts.append(f"effort={_effort_token(reasoning_effort)}")
    parts.append("pool=" + ",".join(str(p) for p in pool_ids))
    parts.append(f"prompt={_prompt_revision()}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _prompt_revision() -> int:
    """The analyze prompt/schema revision a pinned profile was earned under."""
    try:
        from tabs.image_gallery.services.ai_cache import PROMPT_SCHEMA_VERSION

        return int(PROMPT_SCHEMA_VERSION)
    except Exception:
        return 0


def _entries_to_record(entries) -> list:
    """JSON rows for the judge's axes (name + definition + scale + direction).

    The selector chose these axes; their per-image score is ``-1`` by definition
    (nothing has been scored yet), so it is not stored. One shape for ``put`` and
    ``get``, so a cached selection is trivially equal to the fresh one.
    """
    out: list = []
    for entry in entries or ():
        try:
            name = str(getattr(entry, "name", "") or "").strip()
        except Exception:
            continue
        if not name:
            continue
        out.append(
            {
                "name": name,
                "definition": str(getattr(entry, "definition", "") or ""),
                "scale": str(getattr(entry, "scale", "") or "0-100"),
                "direction": str(getattr(entry, "direction", "") or ""),
            }
        )
    return out


def _entries_from_record(rows):
    """``AiAxisProposal`` entries from a cached record (never raises)."""
    try:
        from tabs.image_gallery.models import AiAxisProposal

        out = []
        for row in list(rows or ()):
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "") or "").strip()
            if not name:
                continue
            out.append(
                AiAxisProposal(
                    name=name,
                    definition=str(row.get("definition", "") or ""),
                    scale=str(row.get("scale", "") or "0-100"),
                    score=-1,
                    direction=str(row.get("direction", "") or ""),
                )
            )
        return tuple(out)
    except Exception:
        return ()


class ProfileCache:
    """One-file-per-folder JSON pin for VLM-selected metric profiles.

    ``get`` returns the stored :class:`MetricProfile` or ``None`` on a miss
    (absent/corrupt file, a version mismatch, or an empty axis set — an empty
    profile is not a usable selection). ``put`` stores the full value object so
    a re-read is trivially equal to the fresh one. Transient failures (transport
    error, malformed reply) are deliberately **not** pinned — a later pass may
    retry.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = Path(directory) if directory is not None else None

    def _dir(self) -> Path:
        if self._directory is not None:
            return self._directory
        return profile_cache_dir()

    def _path(self, key: str) -> Path:
        return self._dir() / f"profile_{key}.json"

    def get(self, key: str) -> MetricProfile | None:
        try:
            p = self._path(key)
        except Exception:
            return None
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("profile cache read failed %s", p, exc_info=True)
            return None
        if not isinstance(data, dict):
            return None
        try:
            if int(data.get("version", 0) or 0) != PROFILE_CACHE_VERSION:
                return None
        except Exception:
            return None
        axis_ids = data.get("axis_ids")
        if not isinstance(axis_ids, list):
            return None
        entries = _entries_from_record(data.get("axis_entries"))
        try:
            profile = MetricProfile(
                axis_ids=tuple(str(a) for a in axis_ids),
                mode=data.get("mode", ""),
                source=data.get("source", "vlm"),
                salient_axes=tuple(data.get("salient_axes") or ()),
                axis_entries=entries,
            )
        except Exception:
            return None
        # A free-only selection IS a usable profile (no registry id required) —
        # truthiness, not ``axis_ids``, decides (P7-A).
        return profile if profile else None

    def put(self, key: str, profile) -> None:
        if profile is None or not profile:
            return
        try:
            p = self._path(key)
        except Exception:
            return
        record = {
            "version": PROFILE_CACHE_VERSION,
            "axis_ids": [str(a) for a in profile.axis_ids],
            "mode": str(getattr(profile, "mode", "") or ""),
            "source": str(getattr(profile, "source", "vlm") or "vlm"),
            "salient_axes": [str(a) for a in (getattr(profile, "salient_axes", ()) or ())],
            "axis_entries": _entries_to_record(getattr(profile, "axis_entries", ()) or ()),
            # WHEN it was pinned. Informational only — a pin has no TTL: the key
            # carries every input the answer depends on, so time cannot stale it.
            "pinned_at": round(time.time(), 3),
        }
        try:
            p.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        except OSError:
            logger.debug("profile cache write failed %s", p, exc_info=True)

    def pinned_record(self, key: str) -> dict | None:
        """The stored record for *key* (``None`` on a miss) — for the trace.

        A caller that wants to say WHERE a profile came from (a paid judge answer
        vs. the pinned offer) reads ``pinned_record()["source"]`` instead of
        guessing from the profile object, which is the same either way. Named
        ``pinned_record`` on purpose: a method called ``record`` is read by
        ``tests/contracts/test_pass_reads_only_ctx.py`` as a render-pass draw
        step. Never raises.
        """
        try:
            p = self._path(key)
        except Exception:
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def invalidate(self, key: str) -> bool:
        """Delete the pin for *key* — the explicit upgrade seam. Never raises.

        Dropping a pin is an EXPLICIT decision (the gallery's "Reset metrics
        cache", a script, a test): the next pass resolves the profile afresh, which
        is the only way a pinned heuristic/series OFFER becomes a paid VLM answer
        (``task-profile-freeze-before-vlm-answer``). It is deliberately not
        triggered by a policy change, a settings edit or a re-open — that is the
        churn the pin exists to stop. True when a file was removed.
        """
        try:
            self._path(key).unlink()
            return True
        except FileNotFoundError:
            return False
        except Exception:
            logger.debug("profile pin invalidate failed %s", key, exc_info=True)
            return False

    def clear(self) -> int:
        """Delete every pin file in this cache's directory; return the count.

        The gallery's "Reset metrics cache" entry point: the VLM selection is
        pinned per folder-generation, so a stale pin would keep serving the old
        axis set to the re-derived pipeline. A missing directory / an
        unreadable entry contributes 0; never raises.
        """
        try:
            directory = self._dir()
        except Exception:
            return 0
        try:
            entries = sorted(Path(directory).glob("profile_*.json"))
        except Exception:
            return 0
        deleted = 0
        for path in entries:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                logger.debug("profile pin delete failed %s", path, exc_info=True)
        return deleted


_default_cache: ProfileCache | None = None


def default_cache() -> ProfileCache:
    """Process-wide default cache (lazy, disk-backed)."""
    global _default_cache
    if _default_cache is None:
        _default_cache = ProfileCache()
    return _default_cache


def clear_default_cache() -> int:
    """Clear the process-wide default cache (drop every disk pin). Never raises."""
    try:
        return int(default_cache().clear())
    except Exception:
        return 0


__all__ = [
    "CACHE_DIR_NAME",
    "PROFILE_CACHE_VERSION",
    "ProfileCache",
    "clear_default_cache",
    "default_cache",
    "profile_cache_dir",
    "profile_cache_key",
]
