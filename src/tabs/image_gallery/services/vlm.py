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
from tabs.image_gallery.services.ai_client import AiResponseError, call_sync

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


# API payload budget: full-resolution images are never uploaded by default. The
# VLM judges sharpness/artifacts fine at preview size; downscaling keeps requests
# small and latency predictable. The max edge is user-configurable (gallery AI
# settings); 0 sends the original bytes. Fail-open: if Pillow is missing or the
# file is not decodable, the original bytes go out rather than failing the request.
DEFAULT_VLM_MAX_EDGE_PX = 1024
#: Kept for existing importers; the live value is :func:`get_vlm_max_edge`.
VLM_MAX_EDGE_PX = DEFAULT_VLM_MAX_EDGE_PX

_vlm_max_edge_px = DEFAULT_VLM_MAX_EDGE_PX


def get_vlm_max_edge() -> int:
    """Current downscale max edge in px (0 = original bytes, no downscale)."""
    return _vlm_max_edge_px


def set_vlm_max_edge(px: int) -> None:
    """Set the downscale max edge; ``px <= 0`` disables downscaling."""
    global _vlm_max_edge_px
    try:
        value = int(px)
    except (TypeError, ValueError):
        value = DEFAULT_VLM_MAX_EDGE_PX
    _vlm_max_edge_px = max(0, value)


def _encode_image(path: Path) -> tuple[str, str]:
    p = Path(path)
    mime = _EXT_TO_MIME.get(p.suffix.lower(), "png")
    try:
        raw = p.read_bytes()
    except OSError:
        raise
    max_edge = get_vlm_max_edge()
    try:
        if max_edge > 0:
            from PIL import Image

            import io

            with Image.open(p) as im:
                w, h = im.size
                edge = max(w, h)
                if edge > max_edge and edge > 0:
                    im = im.convert("RGB")
                    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
                    buf = io.BytesIO()
                    fmt = "JPEG" if mime == "jpeg" else "PNG"
                    im.save(buf, format=fmt)
                    raw = buf.getvalue()
                    mime = "jpeg" if fmt == "JPEG" else "png"
    except Exception:
        # Fail-open: send original bytes (any PIL/import/decode problem).
        pass
    data = base64.b64encode(raw).decode("ascii")
    return mime, data


def encode_region(path, box) -> tuple[str, str] | None:
    """Crop a pixel box from an image → ``(mime, base64)``, downscaled to the
    VLM edge. Worker thread only; never raises (``None`` when unavailable).

    ``box`` is ``(left, top, right, bottom)`` in source pixels. Uses the tiled
    store (memmap-backed, no full-frame decode buffer); the base store is closed
    here — only derived state.
    """
    try:
        from engine.store.tiled_pixel_store import TiledPixelStore
    except Exception:
        return None
    store = None
    try:
        store = TiledPixelStore.from_path(Path(path))
        left, top, right, bottom = (int(v) for v in box)
        if right <= left or bottom <= top:
            return None
        im = store.crop((left, top, right, bottom))
    except Exception:
        return None
    finally:
        try:
            if store is not None:
                store.close()
        except Exception:
            pass
    if im is None:
        return None
    try:
        import io

        from PIL import Image

        out = im
        if out.mode not in ("RGB", "L"):
            out = out.convert("RGB")
        max_edge = get_vlm_max_edge()
        if max_edge > 0:
            try:
                edge = max(out.size)
            except Exception:
                edge = 0
            if edge > max_edge and edge > 0:
                out = out.convert("RGB")
                out.thumbnail((max_edge, max_edge), Image.LANCZOS)
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        return ("png", data)
    except Exception:
        return None


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


# Confidence gate: a tie-break below this confidence must not crown — the
# caller degrades to the local ranking instead (badge cleared, no winner).
TIE_BREAK_MIN_CONFIDENCE = 0.5


def is_decisive_tie_break(result: TieBreakResult) -> bool:
    """True when ``result`` is decisive enough to crown a winner."""
    try:
        return bool(result.winner_path) and float(result.confidence) >= TIE_BREAK_MIN_CONFIDENCE
    except Exception:
        return False


def parse_tie_break_response(raw: dict, *, model: str, path_a: Path, path_b: Path) -> TieBreakResult:
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiResponseError(f"unexpected response shape: {exc}") from exc
    if not isinstance(content, str) or not content.strip():
        raise AiResponseError("empty tie-break response")

    winner = None
    saw_winner = False
    confidence: float | None = None
    reason = content.strip().splitlines()[0].strip() if content else ""
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("WINNER:"):
            saw_winner = True
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

    # Ambiguous output must not crown: no WINNER line, an unparseable winner,
    # a missing confidence, or confidence below the gate all raise, so the
    # caller keeps the local ranking (silent-but-visible degrade) instead of
    # fabricating a winner. Previously this defaulted to A at 0.6.
    if not saw_winner or winner is None:
        raise AiResponseError("ambiguous tie-break response: no WINNER line")
    if confidence is None:
        raise AiResponseError("ambiguous tie-break response: no CONFIDENCE value")
    confidence = max(0.0, min(1.0, float(confidence)))
    if confidence < TIE_BREAK_MIN_CONFIDENCE:
        raise AiResponseError(f"indecisive tie-break response: confidence {confidence:.2f} below gate")
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
    result = parse_tie_break_response(raw, model=model, path_a=Path(path_a), path_b=Path(path_b))
    if not is_decisive_tie_break(result):
        raise AiResponseError("indecisive tie-break result: must not crown")
    return result


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
