"""Single source of truth for per-item gallery quality.

Two physical fields carry artifact severities on ``GalleryItem`` — ``artifacts``
(Enum-keyed, primary, written by the background artifact worker) and
``metrics["artifacts"]`` (str-keyed mirror for persistence) — and three
readers normalized them three different ways (card dots, quick-look rows,
triage), so the dots and the report could disagree on the same item.
All severity reads and writes go through this module:

- ``set_artifacts(item, mapping)`` — the only writer (primary + mirror).
- ``severities(item)`` — merged canonical ``{name: severity}`` (primary wins).
- ``severity(item, name)`` — one artifact, metric fallbacks included.
- ``aggregate_severity(item)`` — no-data fallback (legacy aggregate rule).
- ``mode_triplet(item, mode)`` — dots triple per mode (the one mapping).

Severities are canonical lowercase strings: ``clean`` | ``mild`` | ``flagged``.
Read-boundary contract (``plan-gallery-free-axes``, owner 2026-10-27): a value
nobody measured is ``UNMEASURED`` and an unrecognized token is ``"unknown"``;
neither degrades to ``clean``. "No data" is not "clean", so a raised reader or
an absent artifact never reads as the optimistic value:

.. code-block:: python

    UNMEASURED = "unmeasured"

    severity(item, artifact) -> str   # UNMEASURED when absent/unreadable
"""

from __future__ import annotations

import math

#: The value used where no measurement exists. NEVER "clean", NEVER 0, NEVER a
#: coerced domain: a surface that cannot tell "not measured" from "measured good"
#: reports the positive one, which is the defect this token removes.
UNMEASURED = "unmeasured"
#: A severity token that is not a legal severity: the data exists but cannot be
#: read as clean/mild/flagged. Distinct from ``UNMEASURED`` (no data at all).
UNKNOWN = "unknown"

# Mode → dots triple. The single mapping (was duplicated in dots).
MODE_ARTIFACTS: dict[str, list[str]] = {
    "fidelity": ["banding", "halo", "blocking"],
    "camera": ["noise_amplification", "chroma_fringing", "halo"],
    "batch_synthetic": ["over_smoothing", "invented_texture", "blocking"],
}

_SEVERITIES = ("clean", "mild", "flagged")


def normalize_key(key: object) -> str:
    """Canonical artifact name: Enum / ``"Artifact.BANDING"`` / case → lower name."""
    try:
        if hasattr(key, "value"):
            key = key.value  # type: ignore[union-attr]
        name = str(key).lower()
        if "." in name:
            name = name.split(".")[-1].lower()
        return name
    except Exception:
        return ""


def normalize_severity(value: object) -> str:
    """Canonical severity token — two honest non-values instead of ``clean``.

    ``clean`` | ``mild`` | ``flagged`` pass through unchanged; an absent value
    (``None`` / empty) is ``UNMEASURED``; any other token is ``"unknown"``.
    "No data" and "unreadable data" are different facts, and neither is the
    positive one (fail-closed read boundary, not fail-open).
    """
    if value is None:
        return UNMEASURED
    try:
        if hasattr(value, "value"):
            text = str(value.value).strip().lower()  # type: ignore[union-attr]
        else:
            text = str(value).strip().lower()
    except Exception:
        return UNKNOWN
    if not text:
        return UNMEASURED
    return text if text in _SEVERITIES else UNKNOWN


def normalize_mode(mode: object) -> str:
    """Canonical mode key; unknown/empty → ``fidelity`` (legacy default)."""
    try:
        if mode is None:
            mode_str = ""
        elif hasattr(mode, "value"):
            mode_str = str(mode.value).lower()  # type: ignore[union-attr]
        else:
            mode_str = str(mode).lower()
    except Exception:
        mode_str = ""
    if mode_str in ("batch", "batch_synthetic", "batch-synthetic", "synthetic"):
        return "batch_synthetic"
    if mode_str in ("fidelity", "fidelity_mode"):
        return "fidelity"
    if mode_str in ("camera", "camera_mode"):
        return "camera"
    if mode_str in MODE_ARTIFACTS:
        return mode_str
    return "fidelity"


def _raw_artifact_entries(item) -> list[tuple[str, str]]:
    """Normalized ``(name, severity)`` pairs from both physical fields."""
    out: list[tuple[str, str]] = []
    try:
        raw = getattr(item, "artifacts", None)
        if isinstance(raw, dict):
            for k, v in raw.items():
                name = normalize_key(k)
                if name:
                    out.append((name, normalize_severity(v)))
    except Exception:
        pass
    try:
        metrics = getattr(item, "metrics", None)
        ma = metrics.get("artifacts") if isinstance(metrics, dict) else None
        if isinstance(ma, dict):
            for k, v in ma.items():
                name = normalize_key(k)
                if name:
                    out.append((name, normalize_severity(v)))
            # Legacy alias written by older mirrors.
            if "noise_amp" in ma and "noise_amplification" not in {n for n, _ in out}:
                try:
                    out.append(("noise_amplification", normalize_severity(ma["noise_amp"])))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def severities(item) -> dict[str, str]:
    """Merged canonical severities; primary ``artifacts`` wins per key."""
    merged: dict[str, str] = {}
    for name, sev in _raw_artifact_entries(item):
        if name not in merged:
            merged[name] = sev
    return merged


def _metric_severity(metrics: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        try:
            value = metrics.get(key)
        except Exception:
            continue
        if value is None:
            continue
        try:
            text = value.value.lower() if hasattr(value, "value") else str(value).lower()  # type: ignore[union-attr]
        except Exception:
            continue
        if text in _SEVERITIES:
            return text
    return None


def severity(item, artifact: object) -> str:
    """One artifact's severity — ``UNMEASURED`` when no data names it.

    Catalog map first, then metric fallbacks. ``"clean"`` is returned only when
    an entry/metric actually says clean; an absent artifact, a non-mapping
    ``metrics`` or an unreadable value is ``UNMEASURED`` (never the optimistic
    placeholder). An unknown stored token comes back as ``"unknown"``.
    """
    name = normalize_key(artifact)
    if not name:
        return UNMEASURED
    hit = severities(item).get(name)
    if hit is not None:
        return hit
    try:
        metrics = getattr(item, "metrics", None) or {}
        if not isinstance(metrics, dict):
            return UNMEASURED
        if name == "noise_amplification":
            alias = _metric_severity(metrics, ("noise_amp_level", "noise_amp"))
            if alias is not None:
                return alias
        fallback = _metric_severity(metrics, (f"{name}_level", name, "artifact_level"))
        if fallback is not None:
            return fallback
        if name == "banding":
            try:
                score = metrics.get("banding_score")
                if score is not None:
                    sc = float(score)
                    if not math.isfinite(sc):
                        return UNMEASURED
                    return "flagged" if sc > 0.7 else "mild" if sc > 0.3 else "clean"
            except Exception:
                pass
    except Exception:
        pass
    return UNMEASURED


def aggregate_severity(item) -> str:
    """Legacy no-catalog fallback: worst of artifact_level/sharp/ssim signals.

    ``"clean"`` only when a severity signal actually says clean; with no
    signal at all the answer is ``UNMEASURED`` (no data is not "clean").
    """
    outlier = False
    mild_found = False
    clean_found = False
    try:
        metrics = getattr(item, "metrics", None) or {}
        if isinstance(metrics, dict):
            mild_vals = [metrics.get("artifact_level"), metrics.get("artifact"), metrics.get("artifact_score")]
            if any(normalize_severity(v) == "mild" for v in mild_vals if v is not None):
                mild_found = True
            if any(normalize_severity(v) == "clean" for v in mild_vals if v is not None):
                clean_found = True
            try:
                sharp = metrics.get("sharpness")
                if sharp is not None and float(sharp) < 100:
                    outlier = True
            except Exception:
                pass
            try:
                ssim = metrics.get("ssim")
                if ssim is not None and float(ssim) < 0.8:
                    outlier = True
            except Exception:
                pass
            try:
                if normalize_severity(metrics.get("artifact_level")) == "flagged":
                    outlier = True
            except Exception:
                pass
        try:
            own = normalize_severity(getattr(item, "artifact", None))
            if own == "flagged":
                outlier = True
            elif own == "mild":
                mild_found = True
            elif own == "clean":
                clean_found = True
        except Exception:
            pass
    except Exception:
        pass
    if outlier:
        return "flagged"
    if mild_found:
        return "mild"
    return "clean" if clean_found else UNMEASURED


def mode_triplet(item, mode: object) -> tuple[str, str, str]:
    """Dots triple severities for *mode*; empty catalog → aggregate ×3.

    An artifact the catalog does not name is ``UNMEASURED`` — the mode asks
    about three artifacts, not three opportunities to print "clean".
    """
    names = MODE_ARTIFACTS[normalize_mode(mode)]
    catalog = severities(item)
    if catalog:
        resolved = []
        for art_name in names:
            sev = catalog.get(art_name)
            if sev is None:
                # Underscore/hyphen-insensitive alias (over_smoothing et al).
                want = art_name.replace("_", "").replace("-", "")
                for kk, vv in catalog.items():
                    if kk.replace("_", "").replace("-", "") == want:
                        sev = vv
                        break
            resolved.append(sev if sev is not None else UNMEASURED)
        return (resolved[0], resolved[1], resolved[2])
    agg = aggregate_severity(item)
    return (agg, agg, agg)


def set_artifacts(item, mapping: dict) -> bool:
    """The only artifact writer: Enum-keyed primary + str-keyed metrics mirror.

    Returns True when anything was written (False on unusable input).
    """
    normalized: dict[str, str] = {}
    try:
        for k, v in dict(mapping).items():
            name = normalize_key(k)
            if not name:
                continue
            sev = normalize_severity(v)
            # Never store an invented token: an unreadable/absent severity is
            # skipped, not written as "clean" (the writer is fail-closed too).
            if sev not in _SEVERITIES:
                continue
            normalized[name] = sev
    except Exception:
        return False
    if not normalized:
        return False
    try:
        from tabs.image_gallery.models import Artifact as _Artifact

        by_value = {e.value.lower(): e for e in _Artifact}
    except Exception:
        by_value = {}  # type: ignore[assignment]
    primary: dict = {}
    for name, sev in normalized.items():
        enum_key = by_value.get(name) if by_value else None
        try:
            from tabs.image_gallery.models import Severity as _Severity

            sev_value = _Severity(sev)
        except Exception:
            sev_value = sev
        primary[enum_key if enum_key is not None else name] = sev_value
    try:
        item.artifacts = primary  # type: ignore[assignment]
    except Exception:
        pass
    try:
        metrics = getattr(item, "metrics", None)
        if isinstance(metrics, dict):
            metrics["artifacts"] = dict(normalized)
    except Exception:
        pass
    return True


#: Scalar metric keys the quick-look camera report reads. Writers land
#: them here so rows stop saying "not measured" (see services/camera_metrics).
CAMERA_METRIC_KEYS = ("sharpness", "exposure", "clipping_pct")


def set_metrics(item, mapping: dict) -> bool:
    """Scalar metric writer (the artifacts counterpart): merge + change flag.

    Only float-able values land; unusable entries are skipped (fail-closed).
    Returns True when at least one key changed.
    """
    try:
        metrics = getattr(item, "metrics", None)
        if not isinstance(metrics, dict):
            return False
        entries = dict(mapping)
    except Exception:
        return False
    changed = False
    for key, value in entries.items():
        try:
            name = str(key)
            number = float(value)  # type: ignore[arg-type]
        except Exception:
            continue
        try:
            if name in metrics and metrics[name] == number:
                continue
            metrics[name] = number
            changed = True
        except Exception:
            continue
    return changed


def artifacts_equal(item, mapping: dict) -> bool:
    """True when the normalized write would change nothing (skip repaints)."""
    try:
        wanted: dict[str, str] = {}
        for k, v in dict(mapping).items():
            name = normalize_key(k)
            if not name:
                continue
            sev = normalize_severity(v)
            if sev not in _SEVERITIES:
                continue
            wanted[name] = sev
    except Exception:
        return True
    try:
        return severities(item) == wanted
    except Exception:
        return False
