"""Disk cache for AI analysis results — keyed like ``thumbnail_cache`` (sha256 of
``path:mtime_ns``), so re-opening a folder never re-spends API credits and an
edited file is correctly treated as not-yet-analyzed.

Stage 3: VLM tie-breaks / compare briefs are cached alongside this file via
``tabs.image_gallery.services.vlm_cache`` (key = hash(paths+mtime), one per
pair). Filtering (``filtering.py``) now searches both analysis tags and brief
tags — see ``vlm_cache.find_briefs_for_path``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from tabs.image_gallery.models import AiAnalysisResult, ai_scored_axes
from tabs.image_gallery.services.thumbnail_cache import cache_key_for

logger = logging.getLogger("ImproveImgSLI")

#: Cache format version. v2 = the open per-axis scorecard (``axes``,
#: plan-gallery-ai-backend-owns-quality): the VLM's OWN numbers. A v1 entry
#: (pre-scorecard) stored ``sharpness``/``noise``/``exposure`` written by the old
#: ``controller._merge_measured_metrics`` — i.e. LOCAL DETECTOR values, not the
#: VLM's. Serving those as the AI-domain read would be a provenance lie (and the
#: reason a stale entry reads as "the VLM measured only 3 axes"), so a v1 entry
#: is treated as a cache MISS and the AI domain re-analyzes it with the full
#: per-axis prompt.
AI_CACHE_VERSION = 2


def ai_cache_dir() -> Path:
    from services.io.project_package import _cache_root

    root = _cache_root() / "gallery_ai_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_path(path: Path, mtime_ns: int) -> Path:
    return ai_cache_dir() / f"{cache_key_for(path, mtime_ns)}.json"


def load_cached_analysis(path: Path, mtime_ns: int) -> AiAnalysisResult | None:
    cache_path = _cache_path(path, mtime_ns)
    if not cache_path.is_file():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))

        def _score(key: str) -> int:
            try:
                v = int(data.get(key, -1))
            except Exception:
                return -1
            return v if 0 <= v <= 100 else -1

        try:
            verdict = str(data.get("verdict", "unknown") or "unknown").lower()
        except Exception:
            verdict = "unknown"
        if verdict not in ("keep", "reject"):
            verdict = "unknown"
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
            # Pre-scorecard entry: its named scores are the local detectors'
            # (the old ``_merge_measured_metrics``), never the VLM's. Do not
            # reconstruct a scorecard from them — treat the entry as a miss so
            # the AI domain re-analyzes with the full per-axis prompt.
            return None
        # Open per-axis scorecard (the VLM's own numbers).
        try:
            from tabs.image_gallery.services.ai_client import _parse_axes

            axes: dict[str, int] = _parse_axes(data.get("axes"))
        except Exception:
            axes = {}
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
            verdict=verdict,
            verdict_reason=str(data.get("verdict_reason", "") or ""),
            defects=tuple(defects),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            axis_notes={
                str(k): str(v)
                for k, v in (data.get("axis_notes", {}) or {}).items()
                if str(v).strip()
            },
        )
    except Exception:
        logger.debug("Gallery AI cache read failed for %s", path, exc_info=True)
        return None


def hydrate_item(item) -> bool:  # type: ignore[no-untyped-def]
    """Fill ``item.analysis`` from the disk cache only (no worker, no settings).

    Marks ``item._ai_cache_checked`` so repeated calls are free (callers
    invoke this on every overlay populate). Returns True when the item now
    carries an analysis. Never raises.
    """
    try:
        if getattr(item, "analysis", None) is not None:
            return True
        if bool(getattr(item, "_ai_cache_checked", False)):
            return False
        try:
            item._ai_cache_checked = True
        except Exception:
            pass
        cached = load_cached_analysis(item.path, item.mtime_ns)
        if cached is None:
            return False
        try:
            from tabs.image_gallery.models import AnalysisStatus

            item.analysis = cached
            item.analysis_status = AnalysisStatus.DONE
            item.analysis_error = None
        except Exception:
            return False
        return True
    except Exception:
        return False


def clear_cached_analysis(path: Path, mtime_ns: int) -> bool:
    """Delete the disk scorecard for one ``(path, mtime_ns)``. Never raises.

    True when a file was removed; a miss returns False (not an error).
    """
    try:
        cache_path = _cache_path(path, mtime_ns)
    except Exception:
        return False
    try:
        cache_path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        logger.debug("Gallery AI cache delete failed for %s", path, exc_info=True)
        return False


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


def save_analysis(path: Path, mtime_ns: int, result: AiAnalysisResult) -> None:
    cache_path = _cache_path(path, mtime_ns)
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
                    "verdict": result.verdict,
                    "verdict_reason": result.verdict_reason,
                    "defects": [
                        {"kind": d.kind, "severity": d.severity, "note": d.note}
                        for d in (result.defects or ())
                    ],
                    "confidence": result.confidence,
                    "axis_notes": dict(result.axis_notes or {}),
                    #: The MERGED per-axis scorecard (``axes`` + the named
                    #: aliases, so a directly-built result's composition is not
                    #: lost) — the AI domain's read. Plus the format version
                    #: (v2 = scorecard contract).
                    "axes": dict(ai_scored_axes(result)),
                    "version": AI_CACHE_VERSION,
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.debug("Gallery AI cache write failed for %s", path, exc_info=True)