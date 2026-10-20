"""The single input of a producer: one item, already decoded.

Producers NEVER decode. Decoding is per item and expensive, and it used to be
repeated per consumer (the proxy builder exists because the artifact, fidelity
and camera paths each decoded the same image). A producer that opens a file or
builds a pixel store would multiply that work, hide its own decode policy from
the plan, and make "how many decodes did this folder cost?" unanswerable.

So the engine hands every producer an ``AnalysisContext`` instead — the
context analogue of the render pipeline's frame context: what was decoded, what
the item is, and which capabilities its inputs actually provide. A capability
that is absent is reported by ``require()`` as a human-readable reason, which a
producer stores on a ``status="gap"`` value rather than fabricating a number.

Same rule for the ``raw`` source bytes and the network transport: the executor
reads the file once (``image_bytes``) and resolves the model through the catalog
(``backend``), then injects a closure for the request (``call``). A producer
therefore opens nothing and knows no endpoint — the two ways a "local" analyzer
used to become a hidden network path with its own decode and its own model id.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from .contracts import BackendRef, freeze_mapping


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """One item's inputs: identity, mode, decoded images and capabilities.

    ``proxy_image`` / ``source_image`` / ``tiled_store`` are opaque here on
    purpose — the engine owns the context, not the image types, so this module
    stays importable without an imaging library.

    Capability fields added for the AI scorecard producer (plan §4 path 1):

    - ``backend`` — the ``BackendRef`` the catalog resolved for this run. A
      producer reads the model/endpoint/params from it and never spells a model
      id itself (invariant I2).
    - ``call`` — payload → raw reply text. The executor closes over the real
      transport **and the credentials**, so an api key never enters the context,
      a record or a producer: there is nothing here to leak into a repr or a
      cache key. A function is hashable, but see the note below.
    - ``image_bytes`` — the item's raw bytes, read once by the executor. This is
      what keeps "no producer decodes" true for an upload as well (G11).

    Hashability decision, stated rather than assumed: this record is NOT
    hashable and never was — ``extra`` is a frozen ``MappingProxyType``
    (``freeze_mapping``), which raises ``TypeError`` on ``hash()``. The new
    ``call`` field does not change that (functions are hashable); nothing in
    the engine keys a cache by a context, cache identity takes the
    ``BackendRef``. The tests pin both halves so a future "make it hashable"
    refactor has to change the decision on purpose.
    """

    item_path: str
    mtime_ns: int
    mode: str | None = None
    proxy_image: object | None = None
    source_image: object | None = None
    tiled_store: object | None = None
    capabilities: frozenset[str] = frozenset()
    extra: Mapping[str, object] = MappingProxyType({})
    backend: BackendRef | None = None
    call: Callable[[dict], str] | None = None
    image_bytes: bytes | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_path", str(self.item_path))
        object.__setattr__(self, "mtime_ns", int(self.mtime_ns))
        object.__setattr__(
            self,
            "capabilities",
            frozenset(str(capability) for capability in (self.capabilities or ())),
        )
        object.__setattr__(self, "extra", freeze_mapping(self.extra))

    def has(self, capability: str) -> bool:
        """True when the item's inputs actually provide *capability*."""
        return str(capability) in self.capabilities

    def require(self, *capabilities: str) -> str | None:
        """Reason the context cannot satisfy *capabilities*, or ``None`` if it can.

        Producers use the return value verbatim as ``AxisValue.reason`` on a
        ``status="gap"`` value, so an unavailable input is visible with its
        cause instead of raising or being filled from another producer.

        Accepts either varargs (``require("reference", "camera_scalars")``) or a
        single iterable of names, because a capability set is usually passed
        through as a tuple.
        """
        wanted: list[str] = []
        for item in capabilities:
            if isinstance(item, str):
                candidates = (item,)
            elif isinstance(item, Iterable):
                candidates = tuple(str(part) for part in item)
            else:
                candidates = (str(item),)
            for name in candidates:
                name = name.strip()
                if name and name not in wanted:
                    wanted.append(name)
        missing = [name for name in wanted if not self.has(name)]
        if not missing:
            return None
        if len(missing) == 1:
            return f"missing capability: {missing[0]}"
        return "missing capabilities: " + ", ".join(missing)


__all__ = ["AnalysisContext"]
