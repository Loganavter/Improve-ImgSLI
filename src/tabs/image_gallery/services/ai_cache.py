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

from tabs.image_gallery.models import AiAnalysisResult
from tabs.image_gallery.services.thumbnail_cache import cache_key_for

logger = logging.getLogger("ImproveImgSLI")


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
        return AiAnalysisResult(
            description=data["description"],
            tags=tuple(data.get("tags", ())),
            model=data["model"],
            analyzed_at_iso=data["analyzed_at_iso"],
            sharpness=_score("sharpness"),
            noise=_score("noise"),
            exposure=_score("exposure"),
            composition=_score("composition"),
            verdict=verdict,
            verdict_reason=str(data.get("verdict_reason", "") or ""),
        )
    except Exception:
        logger.debug("Gallery AI cache read failed for %s", path, exc_info=True)
        return None


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
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.debug("Gallery AI cache write failed for %s", path, exc_info=True)