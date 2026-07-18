"""Relative timestamps shown on recent-project cards."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable


def format_absolute_timestamp(value: str) -> str:
    """Local calendar time for properties dialogs (``YYYY-MM-DD HH:MM:SS``)."""
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        text = str(value or "").strip()
        return text[:19] if text else "-"


def format_relative_opened(
    opened_at: str,
    tr: Callable[..., str] | None = None,
) -> str:
    def _t(key: str, default: str) -> str:
        if tr is None:
            return default
        return tr(key, default)

    try:
        dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt.astimezone(timezone.utc)
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return _t("recent.relative.just_now", "just now")
        minutes = seconds // 60
        if minutes < 60:
            return _t("recent.relative.minutes", "{n}m ago").format(n=minutes)
        hours = minutes // 60
        if hours < 48:
            return _t("recent.relative.hours", "{n}h ago").format(n=hours)
        days = hours // 24
        if days < 14:
            return _t("recent.relative.days", "{n}d ago").format(n=days)
        return dt.astimezone().strftime("%Y-%m-%d")
    except Exception:
        return opened_at[:10] if opened_at else ""
