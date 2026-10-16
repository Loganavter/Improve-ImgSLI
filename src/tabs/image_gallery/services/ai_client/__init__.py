"""OpenAI-compatible (OpenRouter et al.) chat-vision client for AI image tagging.

Stdlib ``urllib.request`` only (matches the project's one existing HTTP
precedent, ``shared.clipboard_images``) — no new dependency. ``call_sync`` must
only ever run on a worker thread (see ``controller.GalleryController``, which
wraps it in a ``GenericWorker``), never on the UI thread.

Package split (plan-gallery-split-2026-10-17, Part C6): one concern per
submodule — ``errors`` (typed errors), ``prompt`` (prompt build + gated debug),
``parse`` (response parsing), ``request`` (payload build), ``transport``
(blocking streaming POST + retry). Every moved name is re-exported below so
``tabs.image_gallery.services.ai_client`` keeps its full surface for importers
and tests.
"""

from __future__ import annotations

import logging
# Kept package-level so ``tabs.image_gallery.services.ai_client.urllib`` stays
# the module object ``transport`` patches through — tests monkeypatch
# ``ai_client.urllib.request.urlopen``.
import urllib.error  # noqa: F401
import urllib.request  # noqa: F401
from pathlib import Path
from typing import Callable

from tabs.image_gallery.models import AiAnalysisResult

from .errors import (
    AiAuthError,
    AiClientError,
    AiNetworkError,
    AiRateLimitError,
    AiResponseError,
    AiServerError,
)
from .parse import (
    _AXIS_IDS,
    _DEFECT_KINDS,
    _LEGACY_LINE_RE,
    _REASONING_BLOCK_RE,
    _axis_flags_from_defects,
    _extract_json,
    _looks_like_legacy_lines,
    _parse_axes,
    _parse_axis_notes,
    _parse_confidence,
    _parse_defects,
    _parse_lines,
    _parse_score,
    _parse_verdict,
    _strip_reasoning,
    parse_response,
)
from .prompt import (
    _PROMPT_CORE,
    PROMPT_TEMPLATE,
    _ai_debug,
    _ratelimit_headers,
    _scorecard_axes,
    build_prompt,
)
from .request import (
    _EXT_TO_MIME,
    DEFAULT_FALLBACK_MODELS,
    build_request,
)
from .transport import (
    _RETRY_BASE_DELAY_S,
    _RETRY_MAX_ATTEMPTS,
    _RETRY_MAX_DELAY_S,
    _consume_stream_chunk,
    _finalize_stream,
    _iter_response_lines,
    _parse_json_body,
    _read_stream,
    _retry_delay_s,
    call_sync,
)

logger = logging.getLogger("ImproveImgSLI")


def _emit_phase(on_phase: Callable[[str], None] | None, phase: str) -> None:
    """Best-effort activity hook: a UI-side failure must never fail analysis."""
    if on_phase is None:
        return
    try:
        on_phase(phase)
    except Exception:
        logger.debug("activity phase hook failed", exc_info=True)

def analyze_image_sync(
    image_path: Path,
    *,
    base_url: str,
    api_key: str,
    model: str,
    mode=None,
    metrics: dict | None = None,
    fallback_models: tuple[str, ...] | None = None,
    on_phase: Callable[[str], None] | None = None,
) -> AiAnalysisResult:
    """Full request→parse pipeline. Call only from a worker thread.

    ``mode`` selects the applicable axis set the prompt requests (the AI-domain
    scorecard). ``on_phase`` (optional) receives ``"analyzing"`` before the
    request is built and ``"waiting"`` right before the blocking HTTP call.
    """
    openrouter = "openrouter" in str(base_url or "").lower()
    _ai_debug(
        "analyze start path=%s model=%s host=%s mode=%s metrics=%d",
        image_path, model, base_url, getattr(mode, "value", mode), len(metrics or {}),
    )
    _emit_phase(on_phase, "analyzing")
    payload = build_request(
        image_path,
        model=model,
        mode=mode,
        metrics=metrics,
        openrouter=openrouter,
        fallback_models=fallback_models,
    )
    _emit_phase(on_phase, "waiting")
    raw = call_sync(base_url, api_key, payload)
    return parse_response(raw, model=model)
