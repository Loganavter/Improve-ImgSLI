"""Gallery filtering — filename primary, AI + VLM tags as fallback (Stage 3).

Stage 1: filename primary, AiAnalysisResult tags as fallback.
Stage 3: VLM brief tags / tie-break reason / cached briefs become functional —
filter by VLM tags stored alongside analysis cache (brief cache + item fields).

Pure — no Qt (disk reads for brief cache are small JSON, not UI-blocking).
"""

from __future__ import annotations

from tabs.image_gallery.models import AnalysisStatus, GalleryItem


def _vlm_haystack(item: GalleryItem) -> str:
    parts: list[str] = []
    # In-memory brief (controller populates after request_compare_brief)
    brief = getattr(item, "vlm_brief", None)
    if brief is not None:
        try:
            parts.append(str(getattr(brief, "summary", "")))
            parts.extend(list(getattr(brief, "differences", ()) or ()))
            parts.extend(list(getattr(brief, "tags", ()) or ()))
        except Exception:
            pass
    # Tie-break reason
    tie = getattr(item, "vlm_tie_result", None)
    if tie is not None:
        try:
            parts.append(str(getattr(tie, "reason", "")))
            parts.append(str(getattr(tie, "winner_path", "")))
        except Exception:
            pass
    # Fallback: try disk cache briefs for this path when in-memory not yet loaded
    # (filtering is pure + cheap; reading a few small JSON files is not UI-blocking)
    if not parts:
        try:
            from tabs.image_gallery.services.vlm_cache import find_briefs_for_path

            briefs = find_briefs_for_path(item.path, getattr(item, "mtime_ns", 0))
            for b in briefs:
                parts.append(b.summary)
                parts.extend(b.differences)
                parts.extend(b.tags)
        except Exception:
            pass
    return " ".join(parts).lower()


def filter_items(items: list[GalleryItem], query: str) -> list[GalleryItem]:
    """Return items matching ``query`` (case-insensitive substring).

    Stage 1 rules: filename primary, analysis tags as fallback.
    Stage 3 extension: also search VLM brief tags / tie-break reasons
    (item.vlm_brief + vlm_tie_result + cached briefs). This makes the
    semantic search field functional when Stage 3 briefs are present —
    filter by VLM tags stored alongside analysis cache.
    """
    query = query.strip().lower()
    if not query:
        return list(items)

    matched: list[GalleryItem] = []
    for item in items:
        name_lower = item.name.lower()
        path_name_lower = item.path.name.lower()
        if query in name_lower or query in path_name_lower:
            matched.append(item)
            continue
        hay_found = False
        if item.analysis_status == AnalysisStatus.DONE and item.analysis is not None:
            haystack = item.analysis.description.lower() + " " + " ".join(item.analysis.tags).lower()
            if query in haystack:
                matched.append(item)
                hay_found = True
                continue
        # Stage 3: VLM brief / tie-break tags (semantic search)
        vlm_hay = _vlm_haystack(item)
        if vlm_hay and query in vlm_hay:
            matched.append(item)
            continue
        # Also consider analysis tags even when status not DONE? keep Stage1 strict for those,
        # but VLM haystack is independent.
        _ = hay_found
    return matched


def match_fast_items(items: list[GalleryItem], query: str) -> list[GalleryItem]:
    """Filename + in-memory analysis match only — no disk IO, safe on UI thread.

    The VLM brief disk lookup (``find_briefs_for_path`` globs the brief cache
    per item) stays off the UI thread: callers run :func:`match_brief_items`
    in a worker and merge the two sets (see controller filter debounce).
    """
    query = query.strip().lower()
    if not query:
        return list(items)
    matched: list[GalleryItem] = []
    for item in items:
        if query in item.name.lower() or query in item.path.name.lower():
            matched.append(item)
            continue
        if item.analysis_status == AnalysisStatus.DONE and item.analysis is not None:
            haystack = item.analysis.description.lower() + " " + " ".join(item.analysis.tags).lower()
            if query in haystack:
                matched.append(item)
                continue
        brief = getattr(item, "vlm_brief", None)
        tie = getattr(item, "vlm_tie_result", None)
        if brief is not None or tie is not None:
            try:
                parts: list[str] = []
                if brief is not None:
                    parts.append(str(getattr(brief, "summary", "")))
                    parts.extend(list(getattr(brief, "differences", ()) or ()))
                    parts.extend(list(getattr(brief, "tags", ()) or ()))
                if tie is not None:
                    parts.append(str(getattr(tie, "reason", "")))
                if query in " ".join(parts).lower():
                    matched.append(item)
            except Exception:
                pass
    return matched


def match_brief_items(items: list[GalleryItem], query: str) -> list[GalleryItem]:
    """Disk-brief match for a query — worker thread only (does cache-dir IO).

    The mtime check inside ``find_briefs_for_path`` drops stale briefs, so a
    renamed-over/edited file never matches another file's old brief text.
    Returns the subset of *items* whose on-disk briefs contain *query*.
    """
    query = query.strip().lower()
    if not query:
        return []
    try:
        from tabs.image_gallery.services.vlm_cache import find_briefs_for_path
    except Exception:
        return []
    matched: list[GalleryItem] = []
    for item in items:
        try:
            briefs = find_briefs_for_path(item.path, getattr(item, "mtime_ns", 0))
        except Exception:
            continue
        for b in briefs:
            try:
                hay = (b.summary + " " + " ".join(b.differences) + " " + " ".join(b.tags)).lower()
            except Exception:
                continue
            if query in hay:
                matched.append(item)
                break
    return matched
