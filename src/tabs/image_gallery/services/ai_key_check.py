"""Does the stored API key actually authenticate? — THE key probe.

``GET {base_url}/models`` is **not** a key check. On OpenRouter that endpoint is
public: it answers 200 with the whole catalog for an empty or dead key, so the
settings page displayed "464 models, source=network" next to a key the provider
rejected (live 2026-10-28: an 8-character stub in the keyring, every judge call
401, and the only trace was a WARNING in ``log.txt``). A catalog fetch proves
reachability; it says nothing about authentication.

This module answers the one question the page needs: **does an authenticated
call pass?** Two probes, cheapest first:

1. ``GET {base_url}/key`` — OpenRouter's own key endpoint. Free, no tokens, and
   a 200 there IS authentication. A 404/405/501 means the provider has no such
   endpoint; fall through instead of reporting a failure.
2. ``POST {base_url}/chat/completions`` with a 1-token ping under the configured
   model — universal on OpenAI-compatible endpoints, one negligible request.
   It needs a model id; without one the answer is no_model (unverified),
   never a fake ``ok``.

The result is ``(ok, reason, detail)``: ``reason`` is a stable machine token the
UI localizes, ``detail`` is the provider's own words ("HTTP 401: Missing
Authentication header") truncated — that sentence is what identified the
2026-10-28 outage, so it travels to the label instead of dying in a log file.

Pure transport, no Qt, no settings store: the caller owns threads and widgets.
Never raises.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

#: An authenticated call passed.
REASON_OK = "ok"
#: Nothing to authenticate with.
REASON_NO_KEY = "no_key"
#: No endpoint to call (a virgin ``custom`` preset).
REASON_NO_BASE_URL = "no_base_url"
#: The provider has no ``/key`` endpoint and no model is chosen to ping.
REASON_NO_MODEL = "no_model"
#: The provider rejected the credentials (401/403).
REASON_AUTH = "auth"
#: The endpoint answered, but not usably (400/404 after both probes/5xx).
REASON_HTTP = "http"
#: No answer at all (DNS, TLS, timeout, refused).
REASON_NETWORK = "network"

REASONS: tuple[str, ...] = (
    REASON_OK,
    REASON_NO_KEY,
    REASON_NO_BASE_URL,
    REASON_NO_MODEL,
    REASON_AUTH,
    REASON_HTTP,
    REASON_NETWORK,
)

#: Default HTTP timeout. A key ring that hangs must not hold the page: the probe
#: runs off the GUI thread, and 8 s bounds a dead endpoint without a fake "bad
#: key" verdict.
DEFAULT_TIMEOUT = 8.0

#: Statuses that mean "these credentials are not accepted".
_AUTH_STATUS = frozenset({401, 403})

#: Statuses that mean "this endpoint does not exist here" — fall through to the
#: model ping instead of blaming the key.
_NO_ENDPOINT_STATUS = frozenset({404, 405, 501})

#: A valid key answers 429 when it is rate-limited: authentication DID pass, so
#: it is an ``ok`` with a note, not a rejection.
_RATE_LIMITED_STATUS = frozenset({429})

_DETAIL_MAX = 240


def _short(body: bytes) -> str:
    """The provider's message, trimmed to one readable line (never the key)."""
    try:
        text = body.decode("utf-8", "replace")
    except Exception:
        return ""
    text = " ".join(text.split())
    return text[:_DETAIL_MAX]


def _http_detail(status: int, body: bytes) -> str:
    message = _short(body)
    return f"HTTP {status}: {message}" if message else f"HTTP {status}"


def http_request(url, *, api_key="", payload=None, timeout=DEFAULT_TIMEOUT):
    """``(status, body, failure)`` for one request — never raises.

    ``failure`` is ``""`` for any HTTP answer (including 4xx/5xx: the status and
    body carry it) and :data:`REASON_NETWORK` when no answer arrived at all.
    """
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        try:
            data = json.dumps(payload).encode("utf-8")
        except Exception:
            data = b"{}"
        headers["Content-Type"] = "application/json"
    key = str(api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        request = urllib.request.Request(str(url), data=data, headers=headers)
    except Exception:
        return 0, b"", REASON_NETWORK
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(getattr(response, "status", 200) or 200), response.read(), ""
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        return int(getattr(exc, "code", 0) or 0), body, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b"", REASON_NETWORK
    except Exception:
        return 0, b"", REASON_NETWORK


#: Injection seam: tests replace this with a fake transport.
HTTP_REQUEST = http_request

#: The 1-token ping body. ``max_tokens: 1`` keeps the cost of the probe as close
#: to zero as an OpenAI-compatible endpoint allows.
_PING_PAYLOAD = {
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 1,
}


def probe_key(
    base_url,
    api_key,
    model=None,
    timeout=DEFAULT_TIMEOUT,
    *,
    request=None,
) -> tuple[bool, str, str]:
    """``(ok, reason, detail)`` — does *api_key* authenticate against *base_url*?

    Both probes go through one seam (``request``, default :data:`HTTP_REQUEST`),
    so a test can answer ``/key`` and ``/chat/completions`` independently.
    ``model`` is only needed for the fallback ping; the ``/key`` probe answers
    without it.
    """
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        return False, REASON_NO_BASE_URL, "no endpoint is configured"
    key = str(api_key or "").strip()
    if not key:
        return False, REASON_NO_KEY, "no key is stored"
    call = request if request is not None else HTTP_REQUEST

    status, body, failure = call(url + "/key", api_key=key, payload=None, timeout=timeout)
    if failure:
        return False, REASON_NETWORK, ""
    if 200 <= int(status) < 300:
        return True, REASON_OK, ""
    if int(status) in _AUTH_STATUS:
        return False, REASON_AUTH, _http_detail(int(status), body)
    if int(status) in _RATE_LIMITED_STATUS:
        # A valid key answers 429 when it is throttled: authentication passed.
        return True, REASON_OK, _http_detail(int(status), body)
    if int(status) not in _NO_ENDPOINT_STATUS:
        return False, REASON_HTTP, _http_detail(int(status), body)

    model_id = str(model or "").strip()
    if not model_id:
        return (
            False,
            REASON_NO_MODEL,
            "this provider has no /key endpoint and no model is chosen",
        )
    payload = dict(_PING_PAYLOAD)
    payload["model"] = model_id
    status, body, failure = call(
        url + "/chat/completions", api_key=key, payload=payload, timeout=timeout
    )
    if failure:
        return False, REASON_NETWORK, ""
    if 200 <= int(status) < 300:
        return True, REASON_OK, ""
    if int(status) in _AUTH_STATUS:
        return False, REASON_AUTH, _http_detail(int(status), body)
    if int(status) in _RATE_LIMITED_STATUS:
        return True, REASON_OK, _http_detail(int(status), body)
    return False, REASON_HTTP, _http_detail(int(status), body)


__all__ = [
    "DEFAULT_TIMEOUT",
    "HTTP_REQUEST",
    "REASONS",
    "REASON_AUTH",
    "REASON_HTTP",
    "REASON_NETWORK",
    "REASON_NO_BASE_URL",
    "REASON_NO_KEY",
    "REASON_NO_MODEL",
    "REASON_OK",
    "http_request",
    "probe_key",
]
