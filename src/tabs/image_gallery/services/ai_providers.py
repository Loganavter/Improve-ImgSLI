"""Named AI provider presets for the Image Gallery settings page.

Owner decision (2026-10-20): the AI settings used to be one free ``base_url`` +
one free ``model`` string. Providers do not share model catalogs, so switching
the endpoint silently left a model the new provider may not serve — and nothing
offered to redo the analyses. Settings now name a PROVIDER, and a provider owns
a default ``base_url``, a curated fallback catalog and a default model.

**The curated tuples are a FALLBACK, not a catalog.** They go stale the moment
a provider ships or retires a model, so they stay short and are only what the
picker shows when ``GET {base_url}/models`` is unreachable (offline, no key,
401 — see ``services/ai_models.models_for``; the endpoint is the source of
truth). Never grow a list here to "cover" a provider: fix the discovery path.

``custom`` is the plain-old free-form endpoint: the user owns ``base_url`` and
``model``, there is no preset URL and no preset catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

PROVIDER_OPENROUTER = "openrouter"
PROVIDER_OPENAI = "openai"
PROVIDER_LLAMACPP = "llamacpp"
PROVIDER_CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class AiProvider:
    """One named endpoint: default URL, fallback catalog, default model.

    ``label_key`` is the tab i18n key of the on-screen name; ``base_url`` is
    empty for ``custom`` (the user types it); ``curated_models`` is a short
    offline fallback list, ``default_model`` the vision-capable pick used when
    nothing is remembered for this provider (empty when the provider has no
    honest default — a local llama.cpp server serves whatever it was started
    with, so the fetched list is the only truth there).
    """

    id: str
    label_key: str
    base_url: str
    curated_models: tuple[str, ...]
    default_model: str


#: Preset order = the picker order. ``custom`` is always last.
PROVIDERS: tuple[AiProvider, ...] = (
    AiProvider(
        id=PROVIDER_OPENROUTER,
        label_key="image_gallery.settings.provider_openrouter",
        base_url="https://openrouter.ai/api/v1",
        # Fallback only: the same three ids the request fallback chain already
        # uses (``ai_client/request.DEFAULT_FALLBACK_MODELS``) — cheap, vision,
        # structured-output capable.
        curated_models=("openrouter/auto", "z-ai/glm-5.3-flash", "openai/gpt-6-luna"),
        default_model="openrouter/auto",
    ),
    AiProvider(
        id=PROVIDER_OPENAI,
        label_key="image_gallery.settings.provider_openai",
        base_url="https://api.openai.com/v1",
        # Fallback only (offline / no key). One vision-capable id, deliberately
        # not a list: OpenAI renames models faster than any tuple stays true.
        curated_models=("gpt-6-luna",),
        default_model="gpt-6-luna",
    ),
    AiProvider(
        id=PROVIDER_LLAMACPP,
        label_key="image_gallery.settings.provider_llamacpp",
        base_url="http://127.0.0.1:8080/v1",
        # A local server serves exactly what it was loaded with — inventing
        # names here would hand the user a model the server cannot answer for.
        curated_models=(),
        default_model="",
    ),
    AiProvider(
        id=PROVIDER_CUSTOM,
        label_key="image_gallery.settings.provider_custom",
        base_url="",
        curated_models=(),
        default_model="",
    ),
)

PROVIDER_IDS: tuple[str, ...] = tuple(p.id for p in PROVIDERS)

_CUSTOM = PROVIDERS[-1]
_BY_ID = {p.id: p for p in PROVIDERS}


def _url_key(url) -> str:
    """Normalize a base URL for identity comparison — never raises.

    Strip surrounding space + trailing slash, lowercase the HOST (the part that
    is case-insensitive); the path keeps its case because URL paths are
    case-sensitive. An unparsable value falls back to a lowercase stripped
    string so two spellings of the same junk still compare equal.
    """
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path.rstrip('/')}"
    except ValueError:
        pass
    return raw.rstrip("/").lower()


def provider_by_id(provider_id) -> AiProvider:
    """The preset with this id; ``custom`` for an unknown/empty id.

    An unknown id is a stored value from a newer/older build — reading it as
    ``custom`` keeps the user's URL and model editable instead of silently
    rewriting them to a preset they never chose.
    """
    key = str(provider_id or "").strip().lower()
    return _BY_ID.get(key, _CUSTOM)


def provider_for(base_url) -> AiProvider:
    """The preset owning *base_url*, else ``custom``.

    Comparison is normalized (trailing slash, host case), so a URL the user
    typed by hand still resolves to its preset.
    """
    key = _url_key(base_url)
    if key:
        for provider in PROVIDERS:
            if provider.base_url and _url_key(provider.base_url) == key:
                return provider
    return _CUSTOM


def is_custom(provider) -> bool:
    """True for the free-form endpoint (``base_url`` stays editable)."""
    return str(getattr(provider, "id", provider) or "").strip().lower() == PROVIDER_CUSTOM


def model_for(provider, remembered: str = "") -> str:
    """The model to preselect: what was remembered, else the curated default.

    Empty for a provider with no honest default (local server / custom) — the
    caller keeps whatever the user had instead of inventing a name.
    """
    text = str(remembered or "").strip()
    if text:
        return text
    return str(getattr(provider, "default_model", "") or "").strip()


__all__ = [
    "AiProvider",
    "PROVIDERS",
    "_url_key",
    "PROVIDER_CUSTOM",
    "PROVIDER_IDS",
    "PROVIDER_LLAMACPP",
    "PROVIDER_OPENAI",
    "PROVIDER_OPENROUTER",
    "is_custom",
    "model_for",
    "provider_by_id",
    "provider_for",
]
