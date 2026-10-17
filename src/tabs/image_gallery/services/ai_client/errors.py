"""Typed errors raised by the image-gallery AI client."""

from __future__ import annotations


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


class AiServerError(AiNetworkError):
    """5xx — the API host answered but failed (overloaded / broken deploy).

    Subclasses :class:`AiNetworkError` so legacy ``except AiNetworkError``
    handlers keep working; callers that need the distinction catch this type
    first. A 5xx is *not* proof the network is down — surfacing it as a plain
    network error sends users to check their Wi-Fi instead of retrying later.
    """

    def __init__(self, message: str, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class AiResponseError(AiClientError):
    """Malformed/unexpected response body."""
