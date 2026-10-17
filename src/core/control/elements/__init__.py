"""Element inventory + in-process interaction for the control channel (MCP v2 P1).

The control channel's answer to "an agent must click by *element*, not by
pixels, and must be able to *see* what exists". Three modules, one concern each:

* :mod:`~core.control.elements.inventory` — flatten the live widget tree into
  interactive ``Element`` rows (buttons, inputs, views, cards, menu rows, tabs)
  with a stable id, role, label, rects, and the Find-Action id a widget is
  bound to.
* :mod:`~core.control.elements.resolve` — :func:`resolve_element`
  (retry-until-rendered).
* :mod:`~core.control.elements.interaction` — in-process delivery via
  ``QTest`` / ``QApplication.sendEvent``.
* here — the retry knobs, the public re-exports, and :class:`ElementMethodsMixin`
  (the four handler methods, kept next to the logic so ``handlers.py`` stays a
  thin dispatch layer).

**The id is opaque to clients.** It is derived deterministically from the
window identity + the widget's child-index path + the bound action id, so two
``ui_elements`` calls over an unchanged UI return the same ids and the other
three methods can resolve them. Do not parse it; pass it back verbatim.

**Rect semantics.** ``rect`` is *widget-local*: the clickable region in the
coordinate space of the widget that receives the event (``[0, 0, w, h]`` for a
plain widget, the row geometry inside a ``QMenu`` for a menu row).
``screen_rect`` maps that to global coordinates via ``QWidget.mapToGlobal``. On
Wayland screen coordinates are best-effort (the compositor owns global
placement); in-process delivery does **not** require the element to be on
screen, so a click still reaches its handler even when ``screen_rect`` is
wrong or off-display.

GUI thread only: every function here touches live widgets and must run where
they live (the control server dispatches on the GUI thread). No threads.
"""

from __future__ import annotations

from typing import Any

from .inventory import (
    Element,
    collect_elements,
    inventory_payload,
    rect_list,
    screen_rect_of,
)
from .interaction import click_element, focus_element, hover_element
from .resolve import resolve_element

#: Retry budget for an id that is not realized yet (FilmCraft's RETRY semantics:
#: an agent need not sleep between "open" and "click"). Read at call time by
#: ``inventory.resolve_element`` so tests can monkeypatch this attribute.
RETRY_TIMEOUT_MS = 3000

#: Step between inventory rescans inside the retry loop (event loop pumped).
RETRY_STEP_MS = 25


class ElementMethodsMixin:
    """The four element methods, mixed into ``ControlHandlers``.

    They live beside the logic they orchestrate so ``handlers.py`` stays a thin
    dispatch layer. ``self`` is a ``ControlHandlers`` (``_registry``/``_app``
    provided by the host class).
    """

    def ui_elements(self, params: dict[str, Any]) -> dict[str, Any]:
        collected = collect_elements(
            registry=self._registry(),  # type: ignore[attr-defined]
            scope=params.get("scope"),
            include_disabled=bool(params.get("include_disabled", False)),
        )
        return inventory_payload(collected)

    def ui_click(self, params: dict[str, Any]) -> dict[str, Any]:
        target = resolve_element(self._registry(), params.get("id"))  # type: ignore[attr-defined]
        click_element(
            target,
            button=str(params.get("button") or "left"),
            count=params.get("count", 1),
        )
        return {
            "clicked": True,
            "id": target.id,
            "rect": rect_list(target.rect),
            "screen_rect": rect_list(target.screen_rect),
            "target": target.target,
            "surface": target.surface,
        }

    def ui_hover(self, params: dict[str, Any]) -> dict[str, Any]:
        target = resolve_element(self._registry(), params.get("id"))  # type: ignore[attr-defined]
        hover_element(target)
        return {
            "hovered": True,
            "id": target.id,
            "rect": rect_list(target.rect),
            "target": target.target,
        }

    def ui_focus(self, params: dict[str, Any]) -> dict[str, Any]:
        target = resolve_element(self._registry(), params.get("id"))  # type: ignore[attr-defined]
        focus_element(target)
        from PySide6.QtWidgets import QApplication

        instance = getattr(self, "_app", None) or QApplication.instance()
        focused = None
        if instance is not None:
            try:
                focused = instance.focusWidget()
            except Exception:
                focused = None
        label = ""
        if focused is not None:
            try:
                label = f"{type(focused).__name__}:{focused.objectName()}"
            except Exception:
                label = type(focused).__name__
        return {
            "focused": True,
            "id": target.id,
            "rect": rect_list(target.rect),
            "target": target.target,
            "focus_widget": label,
        }


__all__ = [
    "Element",
    "ElementMethodsMixin",
    "RETRY_STEP_MS",
    "RETRY_TIMEOUT_MS",
    "click_element",
    "collect_elements",
    "focus_element",
    "hover_element",
    "inventory_payload",
    "rect_list",
    "resolve_element",
    "screen_rect_of",
]
