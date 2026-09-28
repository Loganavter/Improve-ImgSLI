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
Unknown values degrade to ``clean`` (fail-open: never invent a flag).
"""

from __future__ import annotations

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
    """Canonical severity string; unknown → ``clean`` (fail-open)."""
    try:
        if hasattr(value, "value"):
            text = str(value.value).lower()  # type: ignore[union-attr]
        else:
            text = str(value).lower()
    except Exception:
        return "clean"
    return text if text in _SEVERITIES else "clean"


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
    """One artifact's severity: catalog map, then metric fallbacks, else clean."""
    name = normalize_key(artifact)
    if not name:
        return "clean"
    hit = severities(item).get(name)
    if hit is not None:
        return hit
    try:
        metrics = getattr(item, "metrics", None) or {}
        if not isinstance(metrics, dict):
            return "clean"
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
                    return "flagged" if sc > 0.7 else "mild" if sc > 0.3 else "clean"
            except Exception:
                pass
    except Exception:
        pass
    return "clean"


def aggregate_severity(item) -> str:
    """Legacy no-catalog fallback: worst of artifact_level/sharp/ssim signals."""
    outlier = False
    mild_found = False
    try:
        metrics = getattr(item, "metrics", None) or {}
        if isinstance(metrics, dict):
            mild_vals = [metrics.get("artifact_level"), metrics.get("artifact"), metrics.get("artifact_score")]
            if any(normalize_severity(v) == "mild" for v in mild_vals if v is not None):
                mild_found = True
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
        except Exception:
            pass
    except Exception:
        pass
    if outlier:
        return "flagged"
    if mild_found:
        return "mild"
    return "clean"


def mode_triplet(item, mode: object) -> tuple[str, str, str]:
    """Dots triple severities for *mode*; empty catalog → aggregate ×3."""
    names = MODE_ARTIFACTS[normalize_mode(mode)]
    catalog = severities(item)
    if catalog:
        resolved = []
        for art_name in names:
            sev = catalog.get(art_name, "clean")
            if sev == "clean" and art_name not in catalog:
                # Underscore/hyphen-insensitive alias (over_smoothing et al).
                want = art_name.replace("_", "").replace("-", "")
                for kk, vv in catalog.items():
                    if kk.replace("_", "").replace("-", "") == want:
                        sev = vv
                        break
            resolved.append(sev)
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
            if name:
                normalized[name] = normalize_severity(v)
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


def artifacts_equal(item, mapping: dict) -> bool:
    """True when the normalized write would change nothing (skip repaints)."""
    try:
        wanted: dict[str, str] = {}
        for k, v in dict(mapping).items():
            name = normalize_key(k)
            if name:
                wanted[name] = normalize_severity(v)
    except Exception:
        return True
    try:
        return severities(item) == wanted
    except Exception:
        return False
