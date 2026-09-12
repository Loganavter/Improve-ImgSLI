from __future__ import annotations

import logging
import threading
import weakref
from collections import defaultdict
from typing import Any, Callable, Type, TypeVar, Union

from core.events import Event

logger = logging.getLogger("ImproveImgSLI")

T = TypeVar("T", bound=Event)

MAX_EMIT_DEPTH = 10

class EventBusDepthExceeded(RuntimeError):
    """Raised when EventBus emissions nest deeper than ``MAX_EMIT_DEPTH``.

    A circular event chain (a subscriber re-publishing an event that leads back
    to itself) would otherwise recurse until a ``RecursionError``. This guard
    stops it early with the offending event chain in the message.
    """

class _StrongRefWrapper:
    def __init__(self, callback: Callable[[Any], None]):
        self._callback = callback

    def __call__(self) -> Callable[[Any], None] | None:
        return self._callback

class EventBus:

    def __init__(self):

        self._subscribers: dict[
            type[Event], list[Union[weakref.ref, weakref.WeakMethod, _StrongRefWrapper]]
        ] = defaultdict(list)
        self._emit_state = threading.local()

    def subscribe(self, event_type: Type[T], callback: Callable[[T], None]) -> None:
        weak_cb = None

        is_lambda = (
            hasattr(callback, "__name__") and callback.__name__ == "<lambda>"
        ) or (hasattr(callback, "__code__") and "<lambda>" in str(callback.__code__))

        if hasattr(callback, "__self__") and callback.__self__ is not None:

            if is_lambda:

                weak_cb = _StrongRefWrapper(callback)
            else:
                try:
                    weak_cb = weakref.WeakMethod(callback)
                except TypeError:
                    logger.warning(
                        f"EventBus: WeakMethod failed for {callback}, using strong reference"
                    )
                    weak_cb = _StrongRefWrapper(callback)
        else:

            if is_lambda:

                weak_cb = _StrongRefWrapper(callback)
            else:
                try:
                    weak_cb = weakref.ref(callback)
                except TypeError:
                    logger.debug(
                        f"EventBus: weakref not supported for {callback}, using strong reference"
                    )
                    weak_cb = _StrongRefWrapper(callback)

        for existing_weak_cb in self._subscribers[event_type]:
            existing_cb = existing_weak_cb()
            if existing_cb is not None and existing_cb == callback:

                return

        self._subscribers[event_type].append(weak_cb)

    def unsubscribe(self, event_type: Type[T], callback: Callable[[T], None]) -> None:
        if event_type not in self._subscribers:
            return

        to_remove = []
        for weak_cb in self._subscribers[event_type]:
            cb = weak_cb()
            if cb is None:

                to_remove.append(weak_cb)
            elif cb == callback:

                to_remove.append(weak_cb)

        for weak_cb in to_remove:
            self._subscribers[event_type].remove(weak_cb)

    def emit(self, event: Event) -> None:
        event_type = type(event)
        if event_type not in self._subscribers:
            return

        chain = getattr(self._emit_state, "chain", None)
        if chain is None:
            chain = self._emit_state.chain = []

        if len(chain) >= MAX_EMIT_DEPTH:
            trace = " -> ".join([*chain, event_type.__name__])
            raise EventBusDepthExceeded(
                f"EventBus emission exceeded max depth {MAX_EMIT_DEPTH}; "
                f"likely a circular event chain: {trace}"
            )

        chain.append(event_type.__name__)
        try:
            listeners = self._subscribers[event_type]
            alive_listeners = []

            for weak_cb in listeners:
                cb = weak_cb()
                if cb is not None:
                    try:
                        cb(event)
                        alive_listeners.append(weak_cb)
                    except EventBusDepthExceeded:
                        raise
                    except Exception as e:
                        logger.error(
                            f"EventBus error in callback for event '{event_type.__name__}': {e}",
                            exc_info=True,
                        )

                        alive_listeners.append(weak_cb)

            self._subscribers[event_type] = alive_listeners
        finally:
            chain.pop()
