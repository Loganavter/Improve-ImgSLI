"""OpenAI-compatible model discovery + per-provider cache (gallery AI settings).

The settings picker must offer the models a provider actually serves, not a
list baked into the app: providers do not share catalogs, and a stale tuple is
worse than no tuple. The source of truth is ``GET {base_url}/models`` with the
usual OpenAI-compatible envelope (``data[].id``).

Three layers, in this order (``models_for``):

1. **network** — a successful fetch is remembered per provider (QSettings JSON +
   ``fetched_at`` stamp) and reused;
2. **cache** — a list fetched less than :data:`MODEL_CACHE_TTL_S` ago is used
   WITHOUT a second call; a stale list is still used when a refresh fails
   (offline is not a reason to lose the catalog);
3. **curated** — the provider preset's short fallback tuple
   (``services/ai_providers``), marked as a fallback in the UI.

Nothing here raises: a broken QSettings value, a dead socket, a 401 and an HTML
error page all degrade to the next layer. The failure is NAMED (see the
``REASON_*`` tokens) so the settings status line can say *why* it fell back
instead of showing an empty picker.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from PySide6.QtCore import QSettings

from tabs.image_gallery.services.ai_providers import (
    AiProvider,
    provider_by_id,
)

_QS_ORG = "improve-imgsli"
_QS_APP = "improve-imgsli"
_QS_GROUP = "image_gallery_ai_models"

#: How long a fetched catalog stays fresh (no second call inside this window).
MODEL_CACHE_TTL_S = 24 * 60 * 60

SOURCE_NETWORK = "network"
SOURCE_CACHE = "cache"
SOURCE_CURATED = "curated"
SOURCES: tuple[str, ...] = (SOURCE_NETWORK, SOURCE_CACHE, SOURCE_CURATED)

#: Named failure tokens (stable; the UI maps them to i18n text). "" = success.
REASON_OK = ""
REASON_NO_BASE_URL = "no_base_url"
REASON_AUTH = "auth"
REASON_HTTP = "http"
REASON_NETWORK = "network"
REASON_PARSE = "parse"
REASONS: tuple[str, ...] = (
    REASON_OK,
    REASON_NO_BASE_URL,
    REASON_AUTH,
    REASON_HTTP,
    REASON_NETWORK,
    REASON_PARSE,
)

_AUTH_STATUS = (401, 403)


def _settings() -> QSettings:
    settings = QSettings(_QS_ORG, _QS_APP)
    settings.beginGroup(_QS_GROUP)
    return settings


def _clean_models(values) -> tuple[str, ...]:
    """Deduped, stripped, non-empty model ids in provider order."""
    out: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return tuple(out)


def publisher_of(model_id: str) -> str:
    """The publisher (vendor) part of a model id: text before the FIRST ``/``.

    ``a/b/c`` -> ``a``; an id without a ``/`` has no publisher (``""``). Case is
    preserved — comparison code casefolds. Never raises.
    """
    text = str(model_id or "").strip()
    head, separator, _rest = text.partition("/")
    return head if separator else ""


def sorted_models(models) -> tuple[str, ...]:
    """Model ids deduped and ordered publisher-first, then by model name.

    The picker is a FLAT list (no group headers), so the ordering is the only
    thing that groups a vendor's models together. The sort key is
    ``(publisher.casefold(), model_rest.casefold(), original)``:

    * ``publisher`` is :func:`publisher_of` (text before the first ``/``);
    * the model rest is what follows it (``a/b/c`` -> ``b/c``);
    * a bare id (no ``/``) is its own publisher with an empty rest, so
      ``gpt-6-luna`` sorts by its own name among the vendor-prefixed ids.

    Comparison is case-insensitive; the trailing ``original`` makes the result
    deterministic for ids that differ only in case. Dedupe is exact (same
    string), matching :func:`_clean_models` — case variants are distinct ids a
    provider can genuinely serve. Never raises.
    """

    def _key(model: str) -> tuple[str, str, str]:
        publisher = publisher_of(model)
        if not publisher:
            return (model.casefold(), "", model)
        return (publisher.casefold(), model[len(publisher) + 1 :].casefold(), model)

    return tuple(sorted(_clean_models(models), key=_key))


def parse_models(payload) -> tuple[str, ...]:
    """The ids inside an OpenAI-compatible ``{"data": [{"id": ...}]}`` body.

    Tolerant by design: a bare list is accepted, rows that are plain strings
    are accepted, anything else is skipped. An unrecognisable body is an empty
    tuple (the caller treats that as a parse failure).
    """
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("data")
    if isinstance(rows, dict):
        rows = rows.get("models")
    if not isinstance(rows, (list, tuple)):
        return ()
    ids: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            value = row.get("id")
        else:
            value = row
        text = str(value or "").strip()
        if text:
            ids.append(text)
    return _clean_models(ids)


def http_get_models(
    base_url, api_key, timeout: float = 5
) -> tuple[tuple[str, ...], str]:
    """GET ``{base_url}/models`` → ``(models, reason)``. Never raises.

    No key is still tried (many local/self-hosted endpoints need none); the
    failure of an unauthenticated call is a named reason, not a silent "" list.
    """
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        return (), REASON_NO_BASE_URL
    try:
        request = urllib.request.Request(
            url + "/models", headers={"Accept": "application/json"}
        )
        if str(api_key or "").strip():
            request.add_header("Authorization", f"Bearer {str(api_key).strip()}")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        if int(getattr(exc, "code", 0) or 0) in _AUTH_STATUS:
            return (), REASON_AUTH
        return (), REASON_HTTP
    except (urllib.error.URLError, TimeoutError, OSError):
        return (), REASON_NETWORK
    except Exception:
        return (), REASON_PARSE
    try:
        payload = json.loads(body.decode("utf-8", "replace") or "{}")
    except Exception:
        return (), REASON_PARSE
    models = parse_models(payload)
    if not models:
        return (), REASON_PARSE
    return models, REASON_OK


#: Injection seam: tests replace this with a fake transport.
HTTP_GET = http_get_models


def fetch_models(
    base_url, api_key, timeout: float = 5, *, http=None
) -> tuple[tuple[str, ...], str]:
    """``(models, reason)`` from the provider — ``http`` overrides the seam."""
    getter = http if http is not None else HTTP_GET
    try:
        models, reason = getter(base_url, api_key, timeout=timeout)
    except Exception:
        return (), REASON_NETWORK
    return _clean_models(models), str(reason or REASON_OK)


def cached_models(provider_id) -> tuple[tuple[str, ...], float]:
    """``(models, fetched_at)`` remembered for this provider; ``((), 0.0)``.

    A malformed/foreign stored value reads as "no cache" — never raises.
    """
    key = str(provider_id or "").strip()
    if not key:
        return (), 0.0
    try:
        settings = _settings()
        try:
            raw = str(settings.value(f"models/{key}", "") or "")
        finally:
            settings.endGroup()
    except Exception:
        return (), 0.0
    if not raw:
        return (), 0.0
    try:
        payload = json.loads(raw)
    except Exception:
        return (), 0.0
    if not isinstance(payload, dict):
        return (), 0.0
    models = _clean_models(payload.get("models"))
    try:
        fetched_at = float(payload.get("fetched_at") or 0.0)
    except (TypeError, ValueError):
        fetched_at = 0.0
    return models, max(0.0, fetched_at)


def remember_models(provider_id, models, *, fetched_at: float | None = None) -> None:
    """Persist the fetched catalog for one provider. Never raises."""
    key = str(provider_id or "").strip()
    cleaned = _clean_models(models)
    if not key or not cleaned:
        return
    stamp = float(fetched_at if fetched_at is not None else time.time())
    payload = json.dumps({"models": list(cleaned), "fetched_at": stamp})
    try:
        settings = _settings()
        try:
            settings.setValue(f"models/{key}", payload)
        finally:
            settings.endGroup()
            settings.sync()
    except Exception:
        pass


def _provider(value) -> AiProvider:
    return provider_by_id(value) if isinstance(value, str) else value


def models_for(
    provider,
    api_key,
    *,
    refresh: bool = False,
    http=None,
    now: float | None = None,
    timeout: float = 5,
    report: dict | None = None,
) -> tuple[tuple[str, ...], str]:
    """Resolve the model list for *provider*: ``(models, source)``.

    ``source`` is one of ``network|cache|curated``. ``refresh=True`` skips the
    freshness shortcut (the explicit "refresh from provider" action). A fresh
    cache is used WITHOUT a network call; a failed refresh keeps a stale cache;
    a provider with no catalog at all falls back to its curated tuple (possibly
    empty — the caller then lets the user type a model).

    ``report`` (optional dict) receives the named failure under ``"reason"`` so
    the UI can explain a fallback. Never raises.
    """
    prov = _provider(provider)
    pid = str(getattr(prov, "id", "") or "")
    base_url = str(getattr(prov, "base_url", "") or "")
    curated = _clean_models(getattr(prov, "curated_models", ()) or ())
    stamp = float(now if now is not None else time.time())
    if report is not None:
        report["reason"] = REASON_OK
    try:
        cached, fetched_at = cached_models(pid)
    except Exception:
        cached, fetched_at = (), 0.0
    if cached and not refresh and (stamp - fetched_at) < MODEL_CACHE_TTL_S:
        return cached, SOURCE_CACHE
    if base_url:
        models, reason = fetch_models(base_url, api_key, timeout=timeout, http=http)
    else:
        # No endpoint to ask (fresh ``custom`` preset): do not spawn a request
        # the transport can only fail — the reason is known up front.
        models, reason = (), REASON_NO_BASE_URL
    if models:
        remember_models(pid, models, fetched_at=stamp)
        if report is not None:
            report["reason"] = REASON_OK
        return models, SOURCE_NETWORK
    if report is not None:
        report["reason"] = reason or REASON_NETWORK
    if cached:
        return cached, SOURCE_CACHE
    return curated, SOURCE_CURATED


__all__ = [
    "HTTP_GET",
    "MODEL_CACHE_TTL_S",
    "REASONS",
    "REASON_AUTH",
    "REASON_HTTP",
    "REASON_NETWORK",
    "REASON_NO_BASE_URL",
    "REASON_OK",
    "REASON_PARSE",
    "SOURCES",
    "SOURCE_CACHE",
    "SOURCE_CURATED",
    "SOURCE_NETWORK",
    "cached_models",
    "fetch_models",
    "http_get_models",
    "models_for",
    "parse_models",
    "publisher_of",
    "remember_models",
    "sorted_models",
]
