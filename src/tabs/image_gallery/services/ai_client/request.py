"""Chat-completion request payload for the AI client.

ONE payload policy (defect B2: a size setting applied to one upload path only):
:func:`build_request_from_bytes` encodes the wire copy through
:func:`encode_wire_image` — the single ceiling + mime decision — so every
producer (per-card analysis, the engine's scorecard producer, the probe) ships
the same bounded image.

Why the ceiling and the gate (owner 2026-10-22: 40 wheel notches cost 6.6 s idle
vs 21.4 s during an analysis, 288-514 ms GUI-loop gaps): each card built its
payload from the FULL-RESOLUTION file (``read_bytes`` → ``b64encode`` →
``json.dumps``) three times, on a 4-8 thread pool that must also land the
scroll's thumbnails. The wire copy is capped at the user's VLM edge (default
``decode_policy.VLM_DEFAULT_MAX_EDGE_PX``); at most
:data:`DEFAULT_WIRE_ENCODE_SLOTS` builders encode at once.

Audit-Meta: pattern=wire-policy size=525 reason="one payload/ceiling/mime contract: build_request_from_bytes, the byte and PIL entry points and the re-encode gate must agree on ONE policy; splitting the PIL entry away would let the gallery's R6 reuse ship a different ceiling or mime than the file path (the exact B2 defect class)."
"""

from __future__ import annotations

import base64
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from tabs.image_gallery.services.ask_prompt import language_directive

from .prompt import _ai_debug, attach_measured_context, build_prompt

#: How many payload builders may decode+encode at once. The gallery pool has 4-8
#: threads (``scheduler._scheduler_thread_count``) and up to
#: ``controller._AI_VISIBLE_CAP`` = 12 cards queue k draws each: ungated, every
#: thread sits in a ``b64encode``/``json.dumps`` and a visible thumbnail has
#: nowhere to run. Two leaves the rest of the pool for scroll decodes.
DEFAULT_WIRE_ENCODE_SLOTS = 2

#: Env override for the gate width (tests use 1 to make the bound observable).
WIRE_ENCODE_SLOTS_ENV = "IMGSLI_GALLERY_WIRE_ENCODE_SLOTS"


class WireImage(NamedTuple):
    """One wire copy; ``edge`` = longest edge of the ENCODED image, named in the trace."""

    mime: str
    data_b64: str
    edge: int
    source_bytes: int
    wire_bytes: int


class _WireEncodeGate:
    """Bounded admission for a payload's decode+encode; ``peak`` is instrumented."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sem: threading.Semaphore | None = None
        self._slots = 0
        self._active = 0
        self._peak = 0

    def _ensure(self) -> threading.Semaphore:
        with self._lock:
            if self._sem is None:
                self._slots = _configured_wire_slots()
                self._sem = threading.Semaphore(self._slots)
            return self._sem

    def reset(self) -> None:
        """Drop the sized semaphore so the next use re-reads the env knob."""
        with self._lock:
            self._sem = None
            self._slots = 0
            self._active = 0
            self._peak = 0

    def stats(self) -> dict:
        self._ensure()
        with self._lock:
            return {"slots": self._slots, "active": self._active, "peak": self._peak}

    @contextmanager
    def slot(self):
        sem = self._ensure()
        sem.acquire()
        try:
            with self._lock:
                self._active += 1
                if self._active > self._peak:
                    self._peak = self._active
            yield
        finally:
            with self._lock:
                self._active = max(0, self._active - 1)
            sem.release()


_WIRE_GATE = _WireEncodeGate()


def _configured_wire_slots() -> int:
    """Gate width from the env knob, defaulting to the declared constant."""
    raw = os.environ.get(WIRE_ENCODE_SLOTS_ENV)
    if raw is None or not str(raw).strip():
        return DEFAULT_WIRE_ENCODE_SLOTS
    try:
        return max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        return DEFAULT_WIRE_ENCODE_SLOTS


def wire_encode_gate_stats() -> dict:
    """Gate introspection: ``slots`` / ``active`` / ``peak`` (never raises)."""
    return _WIRE_GATE.stats()


def reset_wire_encode_gate() -> None:
    """Re-size the gate from the env knob (tests only — not called in app flow)."""
    _WIRE_GATE.reset()


#: Suffix -> MIME **subtype** for the one table every upload path reads.
#: Values are bare subtypes because :func:`build_request_from_bytes` composes
#: ``data:image/<subtype>;base64,`` — a value carrying ``image/`` itself would
#: produce an unparseable ``data:image/image/...`` URL, and a value that names
#: the wrong format makes the endpoint reject or misread the bytes (the reason
#: ``.jxl`` must not be labelled ``png``).
#:
#: Coverage is the ``shared/image_extensions`` canon: every accepted suffix has
#: an entry here, and ``tests/contracts/test_accepted_formats_match_decoders.py``
#: fails on a missing or malformed one, so :func:`mime_for_path`'s ``png``
#: fallback is unreachable from accepted input. Unregistered types use the
#: ``x-`` convention that VLM endpoints treat as opaque image bytes; only
#: ``.ico``/``.cur`` deliberately pick ``x-icon`` over the IANA-registered
#: ``vnd.microsoft.icon`` -- both are equally unrecognised as *content* by a
#: model, and ``x-icon`` is the form providers, browsers and ``file(1)`` agree
#: on, so one spelling is better than two.
_EXT_TO_MIME = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".tif": "tiff",
    ".webp": "webp",
    ".jxl": "jxl",
    ".avif": "avif",
    # AVIF image sequence: same codec, the container only adds frames.
    ".avifs": "avif",
    ".qoi": "qoi",
    ".tga": "x-tga",
    ".dds": "x-dds",
    ".pcx": "x-pcx",
    ".sgi": "x-sgi",
    # ImageMagick MIFF ("IM" in Pillow's registry).
    ".im": "x-miff",
    # A DIB is a BMP without the 14-byte file header.
    ".dib": "bmp",
    ".ico": "x-icon",
    ".cur": "x-icon",
    ".icns": "x-icns",
    # Netpbm family: one registered type covers ppm/pgm/pbm/pnm.
    ".ppm": "x-portable-pixmap",
    ".pgm": "x-portable-pixmap",
    ".pbm": "x-portable-pixmap",
    ".pnm": "x-portable-pixmap",
    # JPEG 2000 family (jp2 container and the raw codestream suffixes).
    ".jp2": "jp2",
    ".j2k": "jp2",
    ".jpx": "jp2",
    ".j2c": "jp2",
    ".jpc": "jp2",
    ".jpf": "jp2",
    ".ras": "x-ras",
    ".msp": "x-msp",
    ".xpm": "x-xpixmap",
    ".xbm": "x-xbitmap",
    ".blp": "x-blp",
    ".pxr": "x-pxr",
    ".gbr": "x-gbr",
    # SGI raster variants (bw/rgb/rgba differ only in channel depth).
    ".bw": "x-rgb",
    ".rgb": "x-rgb",
    ".rgba": "x-rgb",
    # OpenGL FTEX textures (streamed .ftc / mipmapped .ftu).
    ".ftc": "x-ftex",
    ".ftu": "x-ftex",
    ".gif": "gif",
    ".apng": "apng",
    ".mpo": "mpo",
    ".fli": "x-flic",
    ".flc": "x-flic",
    ".dcx": "x-dcx",
    ".psd": "vnd.adobe.photoshop",
}

# OpenRouter-only fallback chain (tried in order when the primary model's
# provider is exhausted/overloaded). Cheap, vision, structured-output-capable.
# Only used when the base_url is OpenRouter; not valid on plain OpenAI APIs.
DEFAULT_FALLBACK_MODELS: tuple[str, ...] = (
    "z-ai/glm-5.3-flash",
    "openai/gpt-6-luna",
)

#: Floor for one scorecard answer: the prompt asks for a per-axis scorecard +
#: reason + defects, so it needs more than a one-line tie-break answer. The
#: shared estimator (``ask_router.estimate_ask_max_tokens``) adds the reasoning
#: headroom for the chosen effort; this floor keeps the old 900-token budget
#: from regressing while the effort is capped.
_ANALYZE_MIN_TOKENS = 1024


def _resolve_effort(effort: str) -> str:
    """Normalize the configured reasoning effort (the shared Ask-AI rule)."""
    try:
        from tabs.image_gallery.services.ask_router import resolve_reasoning_effort

        return resolve_reasoning_effort(effort)
    except Exception:
        return "low"


def _analyze_budget(effort: str, configured: int) -> int:
    """Answer-token budget for one scorecard call (shared Ask-AI estimator)."""
    try:
        from tabs.image_gallery.services.ask_router import estimate_ask_max_tokens

        budget = int(
            estimate_ask_max_tokens({"count": 1}, configured=configured, effort=effort)
        )
    except Exception:
        budget = 0
    return max(_ANALYZE_MIN_TOKENS, budget)


def mime_for_path(image_path) -> str:
    """Content type of *image_path* by suffix.

    Returns a MIME **subtype** (the payload composes ``data:image/<subtype>``),
    parsed from the suffix only — no filesystem access. Exposed so a producer
    that already holds the bytes (``AnalysisContext.image_bytes``) names the
    same mime as the file-path path instead of growing a second suffix table.

    Every suffix in the ``shared/image_extensions`` canon has an entry (the
    contract gate enforces it), so the ``png`` fallback only covers paths
    outside the canon — it is not a silent mislabel of an accepted format.
    """
    return _EXT_TO_MIME.get(Path(image_path).suffix.lower(), "png")


def resolve_wire_max_edge(explicit: int | None = None) -> int:
    """Longest edge on the wire: ``explicit``, else the user setting.

    The setting is ``vlm_max_edge_px`` (``services/vlm.get_vlm_max_edge``,
    default ``decode_policy.VLM_DEFAULT_MAX_EDGE_PX``); ``0`` = "send the
    original bytes" and is honored. Imported lazily: ``vlm`` imports this
    package, so a module-level import would cycle.
    """
    if explicit is not None:
        try:
            return max(0, int(explicit))
        except (TypeError, ValueError):
            pass
    try:
        from tabs.image_gallery.services import vlm

        return max(0, int(vlm.get_vlm_max_edge()))
    except Exception:
        from tabs.image_gallery.services.decode_policy import (
            VLM_DEFAULT_MAX_EDGE_PX,
        )

        return int(VLM_DEFAULT_MAX_EDGE_PX)


def _reencode_within_edge(
    raw: bytes, mime: str, cap: int, prefer_jpeg: bool
) -> tuple[bytes | None, str, int]:
    """``(new_bytes | None, mime, longest_edge)`` for *raw*, bounded by *cap*.

    ``None`` = "keep the original bytes": the image already fits, Pillow could
    not decode it (fail-open — an exotic format must not fail a request), or the
    re-encode came out no smaller. Never raises.
    """
    try:
        import io

        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(raw)) as im:
            try:
                width, height = im.size
            except Exception:
                return (None, mime, 0)
            edge = max(width, height)
            if edge <= cap or edge <= 0:
                return (None, mime, edge)
            # EXIF first: a re-encode drops the orientation tag, so a rotated
            # photo would reach the model sideways (the original bytes carried
            # the tag, which the endpoint honors).
            out = ImageOps.exif_transpose(im.convert("RGB"))
            out.thumbnail((cap, cap), Image.LANCZOS)
            fmt = "JPEG" if (mime == "jpeg" or prefer_jpeg) else "PNG"
            buf = io.BytesIO()
            if fmt == "JPEG":
                out.save(buf, format=fmt, quality=85, optimize=True)
            else:
                out.save(buf, format=fmt)
            data = buf.getvalue()
            sent_edge = max(out.size)
    except Exception:
        return (None, mime, 0)
    if len(data) >= len(raw):
        # A small, highly compressed source can re-encode larger: keep the
        # original bytes rather than ship a bigger payload.
        return (None, mime, edge)
    return (data, "jpeg" if fmt == "JPEG" else "png", sent_edge)


def encode_wire_image(
    image_bytes: bytes,
    mime: str,
    *,
    max_edge: int | None = None,
    prefer_jpeg: bool = True,
) -> WireImage:
    """Encode *image_bytes* into the wire copy the model receives.

    THE per-card encoder seam: the ceiling (:func:`resolve_wire_max_edge`), the
    re-encode and the admission gate live here, so no caller ships
    full-resolution bytes by building its own payload. ``prefer_jpeg`` is the
    format of a RE-ENCODED image (a downscaled PNG is still large); a source
    that already fits the cap goes byte-identical, so the setting means "cap",
    not "transcode".
    """
    raw = bytes(image_bytes or b"")
    cap = resolve_wire_max_edge(max_edge)
    wire_bytes = raw
    wire_mime = str(mime or "png")
    edge = 0
    if cap > 0 and raw:
        with _WIRE_GATE.slot():
            recoded, recoded_mime, seen_edge = _reencode_within_edge(
                raw, wire_mime, cap, prefer_jpeg
            )
        edge = seen_edge
        if recoded is not None:
            wire_bytes, wire_mime = recoded, recoded_mime
    data = base64.b64encode(wire_bytes).decode("ascii")
    _ai_debug(
        "wire image mime=%s edge=%s cap=%d source_bytes=%d wire_bytes=%d b64_chars=%d gate=%s",
        wire_mime,
        edge or "unknown",
        cap,
        len(raw),
        len(wire_bytes),
        len(data),
        wire_encode_gate_stats(),
    )
    return WireImage(
        mime=wire_mime,
        data_b64=data,
        edge=int(edge or 0),
        source_bytes=len(raw),
        wire_bytes=len(wire_bytes),
    )


def encode_wire_path(
    image_path,
    *,
    max_edge=None,
    prefer_jpeg: bool = True,
    image=None,
) -> WireImage:
    """Encode the wire copy of *image_path* — from decoded pixels when given.

    ``image`` (a PIL image) is the Stage-2 proxy the gallery already decoded at
    ``PROXY_MAX_EDGE`` (1024). Reusing it removes a second full-file read +
    decode per analyzed card (audit R6); the pixels are re-serialized in memory
    and then pass through the ONE ceiling/re-encode seam, so the wire policy is
    unchanged. Without ``image`` the historical path reads the file once.
    """
    if image is not None:
        import io

        try:
            buf = io.BytesIO()
            image.convert("RGB").save(buf, format="PNG")
            return encode_wire_image(
                buf.getvalue(),
                "image/png",
                max_edge=max_edge,
                prefer_jpeg=prefer_jpeg,
            )
        except Exception:
            # Fail-open to the historical read: a broken pixel view must not
            # drop the analysis.
            pass
    path = Path(image_path)
    return encode_wire_image(
        path.read_bytes(),
        mime_for_path(path),
        max_edge=max_edge,
        prefer_jpeg=prefer_jpeg,
    )


def build_request_from_bytes(
    image_bytes: bytes,
    mime: str,
    *,
    model: str,
    prompt: str | None = None,
    mode=None,
    profile=None,
    metrics: dict | None = None,
    openrouter: bool = False,
    fallback_models: tuple[str, ...] | None = None,
    reasoning_effort: str = "auto",
    max_tokens: int = 0,
    temperature: float = 0.0,
    seed: int = 0,
    wire: WireImage | None = None,
    max_edge: int | None = None,
) -> dict:
    """Chat-completion payload for already-read *image_bytes* (no file I/O).

    The ONE payload shape: :func:`build_request` reads the file and delegates
    here, and a producer holding executor-provided bytes calls this directly.
    Two builders would mean two payload policies — the defect this plan removes
    (B2: ``vlm_max_edge_px`` applied to one upload path only).

    ``wire`` is an already-encoded :class:`WireImage` (the k-draw loop encodes
    ONCE and re-uses it: only the seed differs per draw); without it the bytes
    are encoded here through the same ceiling and gate.
    """
    raw_bytes = bytes(image_bytes or b"")
    wire = (
        wire
        if wire is not None
        else encode_wire_image(raw_bytes, mime, max_edge=max_edge)
    )
    data = wire.data_b64
    # Local (Algorithms-domain) numbers ride along as CONTEXT only — the AI's
    # own per-axis scorecard is the answer (plan-gallery-ai-backend-owns-quality).
    block = ""
    if metrics:
        try:
            from tabs.image_gallery.services.metric_scores import (
                format_measured_for_prompt,
            )

            block = format_measured_for_prompt(metrics)
        except Exception:
            block = ""
    if prompt is None:
        # Default prompt: request every applicable axis for this mode/profile.
        text = build_prompt(mode, profile=profile, measured_block=block)
    else:
        # A custom prompt goes through the SAME echo filter as the scorecard
        # prompt (plan-gallery-ai-judgement P3-E): the local numbers for an axis
        # the model is asked to judge are an echo, not an independent read.
        text = attach_measured_context(prompt, block, mode=mode, profile=profile)
    # Steer the prose fields (the assessment reason / defect notes) into the
    # current UI language; the JSON envelope itself is unchanged.
    text = f"{text}\n{language_directive()}"
    resolved_effort = _resolve_effort(reasoning_effort)
    payload: dict = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{wire.mime};base64,{data}"
                        },
                    },
                ],
            }
        ],
        "max_tokens": _analyze_budget(reasoning_effort, max_tokens),
        # Force a JSON object so reasoning models cannot answer in prose.
        "response_format": {"type": "json_object"},
    }
    # Sampling knobs (plan-gallery-ai-judgement P3-D): sent only when the user
    # declared them — a default (0.0 / 0) means "the backend's own draw", and
    # leaving the field out keeps every existing payload byte-identical.
    if temperature and float(temperature) > 0:
        payload["temperature"] = float(temperature)
    if seed:
        payload["seed"] = int(seed)
    if openrouter:
        # OpenRouter extensions:
        # - reasoning.exclude: keep the chain-of-thought out of `content`.
        # - provider routing: a cheap model's default host can be an overloaded
        #   shared pool (429 upstream_provider_shared_pool, e.g. DeepInfra);
        #   pick a healthy provider that actually supports response_format.
        payload["reasoning"] = {"effort": resolved_effort, "exclude": True}
        payload["provider"] = {
            "require_parameters": True,
            "sort": "throughput",
            "allow_fallbacks": True,
        }
        # Model fallback chain: if the primary is exhausted (429 upstream),
        # OpenRouter tries the next one in order instead of failing outright.
        chain = [model] + [m for m in (fallback_models or DEFAULT_FALLBACK_MODELS) if m and m != model]
        if len(chain) > 1:
            payload["models"] = chain
            payload["route"] = "fallback"
    _ai_debug(
        "build_request model=%s openrouter=%s metrics=%d response_format=json_object "
        "reasoning_exclude=%s provider_routing=%s chain=%s prompt_chars=%d "
        "image_bytes=%d b64_chars=%d mime=%s wire_edge=%s effort=%s max_tokens=%s",
        model,
        openrouter,
        len(metrics or {}),
        "reasoning" in payload,
        "provider" in payload,
        payload.get("models"),
        len(text),
        wire.source_bytes,
        len(data),
        wire.mime,
        wire.edge or "unknown",
        resolved_effort,
        payload.get("max_tokens"),
    )
    return payload


def build_request(
    image_path: Path,
    *,
    model: str,
    prompt: str | None = None,
    mode=None,
    profile=None,
    metrics: dict | None = None,
    openrouter: bool = False,
    fallback_models: tuple[str, ...] | None = None,
    reasoning_effort: str = "auto",
    max_tokens: int = 0,
    temperature: float = 0.0,
    seed: int = 0,
    wire: WireImage | None = None,
    max_edge: int | None = None,
) -> dict:
    """Payload for one image on disk — reads it once, then delegates.

    Signature and behaviour are unchanged for every existing caller; the file
    read stays here (the caller owns the path) and the payload comes from
    :func:`build_request_from_bytes`, so there is one payload policy.

    ``wire`` (optional) is a wire copy already encoded by the caller — the
    k-draw loop of ``ai_client.analyze_image_sync`` reads and encodes once and
    passes it here, so the multi-MB read+b64 is not repeated per draw.
    """
    image_path = Path(image_path)
    if wire is not None:
        return build_request_from_bytes(
            b"",
            wire.mime,
            model=model,
            prompt=prompt,
            mode=mode,
            profile=profile,
            metrics=metrics,
            openrouter=openrouter,
            fallback_models=fallback_models,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
            wire=wire,
        )
    return build_request_from_bytes(
        image_path.read_bytes(),
        mime_for_path(image_path),
        model=model,
        prompt=prompt,
        mode=mode,
        profile=profile,
        metrics=metrics,
        openrouter=openrouter,
        fallback_models=fallback_models,
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
        temperature=temperature,
        seed=seed,
        max_edge=max_edge,
    )
