"""Auto-discovered producer registry — one directory scan, no central wiring.

Mirrors the canvas feature registry on purpose (``ui/canvas_infra/scene/
registry.py``): a package per analyzer, ``manifest.py`` exporting metadata,
discovery by directory scan, removal-safe. The plan copies that shape because
it already proved itself: deleting a feature package leaves the app booting.

Discovery rules (deliberately narrow):

- only ``manifest`` is imported, never ``producer``. Discovery runs on every
  start, and a manifest that pulls in a heavy backend (``torch`` + Qt share
  OpenMP and segfault at teardown) would load it for everyone — that is why
  ``quality_models`` imports its backend lazily inside the worker path. The
  manifest is metadata only; heavy imports belong inside ``run()``.
- packages starting with ``_`` are private scratch and skipped.
- a missing or raising manifest is logged at debug and skipped: one broken
  analyzer must degrade its own axes to gaps, never take the app down.

The registry answers "who provides this axis" so no surface has to guess, and
so removing a producer leaves its axes as explicit gaps (plan G8).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from types import ModuleType
from typing import Iterable

from .contracts import ProducerSpec

#: Module name inside a producer package that discovery imports.
PRODUCER_ENTRY = "manifest"
#: Attribute a manifest must export.
PRODUCER_ATTR = "PRODUCER"

logger = logging.getLogger("ImproveImgSLI")


class ProducerRegistry:
    """An immutable-by-convention set of discovered producers, sorted by id.

    Stable order matters: the axis vocabulary (``axes()``), the journal and the
    plan are all rendered from it, so discovery order (directory order, which
    differs between filesystems) must never leak into user-visible ordering.
    """

    def __init__(self, producers: Iterable[ProducerSpec] = ()) -> None:
        by_id: dict[str, ProducerSpec] = {}
        for spec in producers:
            if not isinstance(spec, ProducerSpec):
                raise TypeError(
                    f"ProducerRegistry accepts ProducerSpec, got {type(spec).__name__}"
                )
            if spec.id in by_id:
                raise ValueError(f"duplicate analysis producer id {spec.id!r}")
            by_id[spec.id] = spec
        self._producers: tuple[ProducerSpec, ...] = tuple(
            sorted(by_id.values(), key=lambda spec: spec.id)
        )
        per_axis: dict[str, list[ProducerSpec]] = {}
        for spec in self._producers:
            for axis in spec.provides:
                per_axis.setdefault(str(axis), []).append(spec)
        self._by_axis: dict[str, tuple[ProducerSpec, ...]] = {
            axis: tuple(specs) for axis, specs in per_axis.items()
        }
        #: Union of ``provides`` in registry order (first-seen across producers).
        self._axes: tuple[str, ...] = tuple(self._by_axis)

    @property
    def producers(self) -> tuple[ProducerSpec, ...]:
        """Every discovered producer, sorted by ``spec.id``."""
        return self._producers

    def get(self, producer_id: str) -> ProducerSpec | None:
        """The producer with *producer_id*, or ``None`` when it is not installed."""
        key = str(producer_id)
        for spec in self._producers:
            if spec.id == key:
                return spec
        return None

    def axes(self) -> tuple[str, ...]:
        """The axis vocabulary: the union of ``provides``, in registry order.

        This is the single axis vocabulary (plan §Pool): the hand-written pool
        constants drifted (16/17/17 ids) and a producer's removal could not
        shrink them. Here a removed producer takes its axes with it.
        """
        return self._axes

    def by_axis(self, axis: str) -> tuple[ProducerSpec, ...]:
        """Producers that may produce *axis*, in registry order."""
        return self._by_axis.get(str(axis), ())

    def for_axis(self, axis: str) -> ProducerSpec | None:
        """The single non-automatic producer for *axis*, else ``None``.

        ``None`` covers both "nothing registered" and "several candidates": the
        registry never guesses between producers (that choice is the resolver's,
        and it is recorded in the plan). An automatic producer is never returned
        here — it runs only inside a plan that lists it.
        """
        candidates = [spec for spec in self.by_axis(axis) if not spec.automatic]
        return candidates[0] if len(candidates) == 1 else None

    def __len__(self) -> int:
        return len(self._producers)

    def __contains__(self, producer_id: object) -> bool:
        key = str(producer_id)
        return any(spec.id == key for spec in self._producers)

    def __repr__(self) -> str:
        return f"ProducerRegistry({', '.join(spec.id for spec in self._producers)})"


#: Process-wide cache keyed by package name: discovery scans the filesystem and
#: imports manifests, so it must not run per call site. ``force=True`` bypasses
#: it (tests, and a future "reload producers" action).
_CACHE: dict[str, ProducerRegistry] = {}


def discover(package: str, *, force: bool = False) -> ProducerRegistry:
    """Discover every producer package under *package*.

    *package* is a dotted package name (the analyzers root, e.g.
    ``image_gallery.analysis.producers``). Discovery is fail-soft: a missing or
    raising manifest is skipped with a debug log, never raised, because one
    broken analyzer must not keep the app from booting.

    Cached for the process; pass ``force=True`` to rescan.
    """
    key = str(package or "").strip().strip(".")
    if not key:
        raise ValueError("discover() needs a package name")
    if not force:
        cached = _CACHE.get(key)
        if cached is not None:
            return cached
    registry = ProducerRegistry(_discover_specs(key))
    _CACHE[key] = registry
    return registry


def _discover_specs(package: str) -> list[ProducerSpec]:
    specs: list[ProducerSpec] = []
    seen: set[str] = set()
    for name in _producer_package_names(package):
        module = _import_manifest(package, name)
        if module is None:
            continue
        spec = getattr(module, PRODUCER_ATTR, None)
        if not isinstance(spec, ProducerSpec):
            logger.debug(
                "analysis producer %s.%s.%s exports no %s; skipped",
                package,
                name,
                PRODUCER_ENTRY,
                PRODUCER_ATTR,
            )
            continue
        if spec.id in seen:
            # Two directories claiming one id: keep the first (sorted) so the
            # result does not depend on directory order, and keep booting.
            logger.debug(
                "analysis producer id %r declared twice under %s; keeping the first",
                spec.id,
                package,
            )
            continue
        seen.add(spec.id)
        specs.append(spec)
    return specs


def _producer_package_names(package: str) -> list[str]:
    """Sub-package names under *package*, sorted, ``_``-prefixed excluded."""
    try:
        found = importlib.util.find_spec(package)
    except (ImportError, ValueError) as exc:
        logger.debug("analysis discovery: cannot resolve package %r (%s)", package, exc)
        return []
    locations = list(getattr(found, "submodule_search_locations", None) or ())
    names: set[str] = set()
    for location in locations:
        try:
            entries = os.listdir(location)
        except OSError as exc:
            logger.debug(
                "analysis discovery: cannot list %r (%s)", location, exc
            )
            continue
        for entry in entries:
            if entry.startswith("_") or entry in names:
                continue
            path = os.path.join(location, entry)
            if not os.path.isdir(path):
                continue
            # Only a real sub-package is a producer candidate; checking for
            # ``__init__.py`` keeps sibling data dirs (``resources``, docs) out
            # of the scan instead of relying on import failures to prune them.
            if not os.path.isfile(os.path.join(path, "__init__.py")):
                continue
            names.add(entry)
    return sorted(names)


def _import_manifest(package: str, name: str) -> ModuleType | None:
    module_name = f"{package}.{name}.{PRODUCER_ENTRY}"
    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - fail-soft is the contract here
        logger.debug(
            "analysis producer manifest %s failed to import (%s: %s); skipped",
            module_name,
            type(exc).__name__,
            exc,
        )
        return None


__all__ = [
    "PRODUCER_ATTR",
    "PRODUCER_ENTRY",
    "ProducerRegistry",
    "discover",
]
