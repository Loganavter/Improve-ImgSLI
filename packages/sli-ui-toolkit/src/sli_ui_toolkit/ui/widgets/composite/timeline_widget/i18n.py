from __future__ import annotations

from typing import Callable

_localize_token_fn: Callable[[str], str] | None = None
_localize_value_fn: Callable[[object], str] | None = None

def set_localize_token(fn: Callable[[str], str] | None) -> None:
    global _localize_token_fn
    _localize_token_fn = fn

def set_localize_value(fn: Callable[[object], str] | None) -> None:
    global _localize_value_fn
    _localize_value_fn = fn

def localize_token(token: str) -> str:
    if _localize_token_fn is not None:
        return _localize_token_fn(token)
    return str(token)

def localize_value(value) -> str:
    if _localize_value_fn is not None:
        return _localize_value_fn(value)
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
