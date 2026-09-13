"""OpenAI-compatible (OpenRouter et al.) chat-vision client for AI image tagging.

Stdlib ``urllib.request`` only (matches the project's one existing HTTP
precedent, ``shared.clipboard_images``) — no new dependency. ``call_sync`` must
only ever run on a worker thread (see ``controller.GalleryController``, which
wraps it in a ``GenericWorker``), never on the UI thread.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tabs.image_gallery.models import AiAnalysisResult

PROMPT_TEMPLATE = (
    "Describe this image in one short sentence, then list a handful of "
    "single-word or short-phrase tags. Respond in exactly this format:\n"
    "DESCRIPTION: <one sentence>\n"
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


class AiClientError(Exception):
    """Base for all typed errors raised by this module."""


class AiAuthError(AiClientError):
    """401/403 — bad or missing API key."""


class AiRateLimitError(AiClientError):
    """429 — too many requests."""

    def __init__(self, message: str, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class AiNetworkError(AiClientError):
    """Connection failure, timeout, DNS error, etc."""


class AiResponseError(AiClientError):
    """Malformed/unexpected response body."""


def build_request(image_path: Path, *, model: str, prompt: str = PROMPT_TEMPLATE) -> dict:
    image_path = Path(image_path)
    mime = _EXT_TO_MIME.get(image_path.suffix.lower(), "png")
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{mime};base64,{data}"},
                    },
                ],
            }
        ],
        "max_tokens": 400,
    }


def call_sync(base_url: str, api_key: str, payload: dict, *, timeout: float = 30.0) -> dict:
    """Blocking HTTP POST — call only from a worker thread."""
    url = base_url.rstrip("/") + "/chat/completions"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        if exc.code in (401, 403):
            raise AiAuthError(f"HTTP {exc.code}: {body}") from exc
        if exc.code == 429:
            raise AiRateLimitError(f"HTTP 429: {body}", retry_after=exc.headers.get("Retry-After")) from exc
        raise AiNetworkError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise AiNetworkError(str(exc.reason)) from exc
    except TimeoutError as exc:
        raise AiNetworkError("request timed out") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AiResponseError(f"invalid JSON in response: {exc}") from exc


def parse_response(raw: dict, *, model: str) -> AiAnalysisResult:
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiResponseError(f"unexpected response shape: {exc}") from exc

    if not isinstance(content, str) or not content.strip():
        raise AiResponseError("empty response content")

    description = content.strip()
    tags: tuple[str, ...] = ()
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("DESCRIPTION:"):
            description = line.split(":", 1)[1].strip()
        elif line.upper().startswith("TAGS:"):
            raw_tags = line.split(":", 1)[1]
            tags = tuple(t.strip() for t in raw_tags.split(",") if t.strip())

    return AiAnalysisResult(
        description=description,
        tags=tags,
        model=model,
        analyzed_at_iso=datetime.now(timezone.utc).isoformat(),
    )


def analyze_image_sync(
    image_path: Path, *, base_url: str, api_key: str, model: str
) -> AiAnalysisResult:
    """Full request→parse pipeline. Call only from a worker thread."""
    payload = build_request(image_path, model=model)
    raw = call_sync(base_url, api_key, payload)
    return parse_response(raw, model=model)
