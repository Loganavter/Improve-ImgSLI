"""Id → ``Element`` resolution with retry-until-rendered semantics.

An unknown/not-yet-realized element is retried for ~3 s (rescanning the
inventory, pumping the event loop) before failing — so an agent need not sleep
between "open" and "click". A failure raises ``MethodError`` listing close
matches and a hint to call ``ui_elements``.
"""

from __future__ import annotations

import difflib
import time
from typing import Any

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from ..discovery import MethodError
from .inventory import (
    Element,
    _is_popup_window,
    _make_element,
    _top_level_widgets,
    _window_keys,
    collect_elements,
)
from .roles import _label_of, _role_of


def _window_key_for(widget: QWidget) -> str:
    """Window identity of *widget*'s top-level, matching ``collect_elements``."""
    windows = _top_level_widgets()
    keys = _window_keys(windows)
    try:
        top = widget.window()
    except Exception:
        top = widget
    for window, key in zip(windows, keys):
        if window is top:
            return key
    try:
        return str(top.objectName() or type(top).__name__ or "window")
    except Exception:
        return "window"


def _resolve_via_action(registry: Any, needle: str) -> Element | None:
    """Action-first fallback: the registry's bound widget for ``@<action id>``."""
    if "@" not in needle:
        return None
    action_id = needle.rsplit("@", 1)[-1]
    try:
        action = registry.get(action_id)
    except Exception:
        action = None
    if action is None:
        return None
    target = getattr(action, "target", None)
    try:
        widget = target.resolve_widget_instance() if target is not None else None
    except Exception:
        widget = None
    if not isinstance(widget, QWidget):
        return None
    return _make_element(
        widget=widget,
        element_id=needle,
        role=_role_of(widget) or "action",
        label=_label_of(widget, action),
        rect=widget.rect(),
        window=_window_key_for(widget),
        surface="popup" if _is_popup_window(widget.window()) else "window",
        action=action,
    )


def resolve_element(
    registry: Any, needle: Any, *, timeout_ms: int | None = None
) -> Element:
    """Resolve *needle* to an element, retrying until the UI realizes it.

    Raises ``MethodError`` (with close matches + a ``ui_elements`` hint) when
    the id never appears within the retry budget. The event loop is pumped
    between rescans, so a widget created by a queued/timer callback is found.
    """
    from core.control import elements as package

    if not isinstance(needle, str) or not needle.strip():
        raise MethodError(
            "ui_* needs a non-empty 'id'",
            "call ui_elements and pass one of the returned ids verbatim",
        )
    budget = package.RETRY_TIMEOUT_MS if timeout_ms is None else int(timeout_ms)
    step = int(getattr(package, "RETRY_STEP_MS", 25))
    deadline = time.monotonic() + max(0, budget) / 1000.0
    elements: list[Element] = []
    while True:
        elements = collect_elements(registry=registry)
        for element in elements:
            if element.id == needle:
                return element
        fallback = _resolve_via_action(registry, needle)
        if fallback is not None:
            return fallback
        if time.monotonic() >= deadline:
            break
        try:
            QTest.qWait(step)
        except Exception:
            time.sleep(step / 1000.0)
    candidates = [element.id for element in elements]
    close = difflib.get_close_matches(needle, candidates, n=5, cutoff=0.5)
    hint = "call ui_elements to list the current ids"
    if close:
        hint = "did you mean: " + ", ".join(close) + "? (" + hint + ")"
    raise MethodError(f"no element with id {needle!r}", hint)
