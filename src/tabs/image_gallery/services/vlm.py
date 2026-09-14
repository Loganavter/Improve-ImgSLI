"""Stage 3 VLM API layer: tie-break + compare briefs.

Uses existing ``ai_client`` transport (urllib, OpenAI-compatible /chat/completions)
but only for top-2 tie-break when local metrics within epsilon, and for finalists
briefs. One structured report per pair, cached via ``vlm_cache``.

All sync functions must run on GenericWorker, never on UI thread.

Design.md 47-54: Pass 2 — VLM API (optional, targeted):
- tie-break: top-2 of a series when local metrics are within epsilon
  (badge ``AI tie-break…`` on both candidates until resolved)
- compare briefs for finalists: one structured difference report per pair,
  cached like ``ai_cache`` results today.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from tabs.image_gallery.models import CompareBrief, TieBreakResult
from tabs.image_gallery.services.ai_client import AiClientError, AiResponseError, call_sync

# Stage 3 prompts — visibly targeted, never whole-folder scan
TIE_BREAK_PROMPT_TEMPLATE = (
    "You are an image quality arbiter for fidelity batches. "
    "Two images A and B are upscales/variants of the same source. "
    "Compare sharpness, detail faithfulness, and visible artifacts. "
    "Pick the better one and explain briefly.\n"
    "Respond in exactly this format:\n"
    "WINNER: A|B\n"
    "CONFIDENCE: <0.0-1.0>\n"
    "REASON: <one short sentence>"
)

COMPARE_BRIEF_PROMPT_TEMPLATE = (
    "Compare these two images as finalists. "
    "Summarize the visible difference in one sentence, "
    "list 2-5 bullet differences, and 3-6 single-word tags.\n"
    "Respond in exactly this format:\n"
    "SUMMARY: <one sentence>\n"
    "DIFFERENCES: <semicolon-separated short phrases>\n"
    "TAGS: <comma-separated tags>"
)

_EXT_TO_MIME = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".tif": "tiff",
    ".webp": "webp",
}


def _encode_image(path: Path) -> tuple[str, str]:
    p = Path(path)
    mime = _EXT_TO_MIME.get(p.suffix.lower(), "png")
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return mime, data


def build_tie_break_request(
    path_a: Path,
    path_b: Path,
    source: Path | None,
    *,
    model: str,
    prompt: str = TIE_BREAK_PROMPT_TEMPLATE,
) -> dict:
    mime_a, data_a = _encode_image(path_a)
    mime_b, data_b = _encode_image(path_b)
    content: list[dict] = [
        {"type": "text", "text": prompt + f"\nA: {Path(path_a).name}\nB: {Path(path_b).name}"},
        {"type": "image_url", "image_url": {"url": f"data:image/{mime_a};base64,{data_a}"}},
        {"type": "image_url", "image_url": {"url": f"data:image/{mime_b};base64,{data_b}"}},
    ]
    if source is not None and Path(source).is_file():
        try:
            mime_s, data_s = _encode_image(source)
            content.insert(1, {"type": "text", "text": f"Source (reference): {Path(source).name}"})
            content.append({"type": "image_url", "image_url": {"url": f"data:image/{mime_s};base64,{data_s}"}})
        except Exception:
            pass
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 300,
    }


def build_compare_brief_request(
    path_a: Path,
    path_b: Path,
    *,
    model: str,
    prompt: str = COMPARE_BRIEF_PROMPT_TEMPLATE,
) -> dict:
    mime_a, data_a = _encode_image(path_a)
    mime_b, data_b = _encode_image(path_b)
    content: list[dict] = [
        {"type": "text", "text": prompt + f"\nPair: {Path(path_a).name} vs {Path(path_b).name}"},
        {"type": "image_url", "image_url": {"url": f"data:image/{mime_a};base64,{data_a}"}},
        {"type": "image_url", "image_url": {"url": f"data:image/{mime_b};base64,{data_b}"}},
    ]
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 400,
    }


def parse_tie_break_response(raw: dict, *, model: str, path_a: Path, path_b: Path) -> TieBreakResult:
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiResponseError(f"unexpected response shape: {exc}") from exc
    if not isinstance(content, str) or not content.strip():
        raise AiResponseError("empty tie-break response")

    winner = None
    confidence = 0.6
    reason = content.strip().splitlines()[0].strip() if content else ""
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("WINNER:"):
            val = line.split(":", 1)[1].strip().upper()
            if val.startswith("A"):
                winner = Path(path_a)
            elif val.startswith("B"):
                winner = Path(path_b)
        elif line.upper().startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except Exception:
                pass
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()

    # Default to A if ambiguous — caller treats low confidence as silent degrade
    if winner is None:
        winner = Path(path_a)
    loser = Path(path_b) if winner == Path(path_a) else Path(path_a)
    return TieBreakResult(
        winner_path=str(winner.resolve()) if winner.exists() else str(winner),
        loser_path=str(loser.resolve()) if loser.exists() else str(loser),
        reason=reason or content.strip()[:200],
        confidence=max(0.0, min(1.0, float(confidence))),
        model=model,
        decided_at_iso=datetime.now(timezone.utc).isoformat(),
    )


def parse_compare_brief_response(raw: dict, *, model: str, path_a: Path, path_b: Path) -> CompareBrief:
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiResponseError(f"unexpected response shape: {exc}") from exc
    if not isinstance(content, str) or not content.strip():
        raise AiResponseError("empty brief response")

    summary = ""
    differences: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
        elif line.upper().startswith("DIFFERENCES:"):
            raw_diffs = line.split(":", 1)[1]
            differences = tuple(s.strip() for s in raw_diffs.split(";") if s.strip())
        elif line.upper().startswith("TAGS:"):
            raw_tags = line.split(":", 1)[1]
            tags = tuple(t.strip() for t in raw_tags.split(",") if t.strip())
    if not summary:
        summary = content.strip().splitlines()[0][:300]
    if not differences:
        # fallback: split tags line as differences if no explicit
        differences = tags[:3] if tags else ()
    return CompareBrief(
        pair=(str(Path(path_a).resolve()), str(Path(path_b).resolve())),
        summary=summary,
        differences=differences,
        tags=tags,
        model=model,
        created_at_iso=datetime.now(timezone.utc).isoformat(),
    )


# -- sync entry points (worker thread only) --------------------------

def tie_break_sync(
    path_a: Path,
    path_b: Path,
    *,
    base_url: str,
    api_key: str,
    model: str,
    source: Path | None = None,
) -> TieBreakResult:
    """Blocking tie-break: compare top-2. Call only from GenericWorker."""
    payload = build_tie_break_request(Path(path_a), Path(path_b), source, model=model)
    raw = call_sync(base_url, api_key, payload)
    return parse_tie_break_response(raw, model=model, path_a=Path(path_a), path_b=Path(path_b))


def compare_brief_sync(
    path_a: Path,
    path_b: Path,
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> CompareBrief:
    """Blocking brief for finalist pair. One per pair, cached. Worker thread only."""
    payload = build_compare_brief_request(Path(path_a), Path(path_b), model=model)
    raw = call_sync(base_url, api_key, payload)
    return parse_compare_brief_response(raw, model=model, path_a=Path(path_a), path_b=Path(path_b))


# -- backwards-compatible wrappers matching task signature --------------

def tie_break(
    series_top2: list[Path] | list,
    source: Path | None = None,
    *,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
) -> TieBreakResult:
    """Task-specified signature: tie_break(series_top2, source?) -> TieBreakResult.

    ``series_top2`` is expected to be a 2-element list of Paths (or GalleryItems
    with .path). This wrapper extracts paths and delegates to ``tie_break_sync``.
    """
    if len(series_top2) != 2:
        raise AiClientError("tie_break requires exactly 2 items")
    def _as_path(x) -> Path:
        if isinstance(x, Path):
            return x
        if hasattr(x, "path"):
            return Path(getattr(x, "path"))
        return Path(str(x))
    a = _as_path(series_top2[0])
    b = _as_path(series_top2[1])
    return tie_break_sync(a, b, base_url=base_url, api_key=api_key, model=model, source=source)


def compare_brief(
    pair_paths: list[Path] | tuple[Path, Path],
    *,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
) -> CompareBrief:
    """Task-specified signature: compare_brief(pair_paths) -> CompareBrief (one per pair)."""
    if len(pair_paths) != 2:
        raise AiClientError("compare_brief requires exactly 2 paths")
    def _as_path(x) -> Path:
        if isinstance(x, Path):
            return x
        if hasattr(x, "path"):
            return Path(getattr(x, "path"))
        return Path(str(x))
    a = _as_path(pair_paths[0])
    b = _as_path(pair_paths[1])
    return compare_brief_sync(a, b, base_url=base_url, api_key=api_key, model=model)
