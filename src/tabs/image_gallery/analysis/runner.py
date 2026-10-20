"""Execute a resolved plan over item contexts — records, never exceptions.

Why the runner is separate from the resolver (``plan-gallery-analysis-engine-
2026-10-20`` §Phases P1/P3): the resolver answers *what may run*, this module
answers *what happened*, and keeping the two apart is what makes "the plan is
not the behavior" checkable. The runner imports a producer package only when the
plan names it, so a plan that excludes a producer never loads it (manifests stay
light, plan trap 2).

Contract, stated because callers depend on it:

- one result entry per item path; each producer's records are appended in plan
  order, so the tuple order is the plan's, not the filesystem's;
- a raising producer NEVER propagates: every axis it declares becomes an
  ``AxisValue(status="error", value=None)`` with ``reason="<ExcType>: <text>"``
  and the journal gets one ``error`` entry. A broken analyzer degrades its own
  axes; it does not take the batch down (same rule as discovery, G8);
- a producer's gap records are kept exactly as returned (a gap is an answer —
  "this axis is unavailable, here is why" — not a failure to hide);
- no image I/O, no store, no controller, no policy: the contexts are the inputs
  and the records are the outputs.

The producer package lookup walks the analyzers directory and matches the
manifest's ``PRODUCER.id``, because a package directory name (banding) and a
producer id (artifact_banding) are deliberately not the same string. The
mapping is cached per process; a plan naming an uninstalled producer fails that
one producer into error records (the axes become gaps/errors, the app boots).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from collections.abc import Callable, Mapping
from typing import Any

from engine.analysis.contracts import AxisValue, JournalEntry, ProducerSpec, RunJournal
from engine.analysis.registry import PRODUCER_ATTR
from engine.analysis.resolver import Resolution

logger = logging.getLogger("ImproveImgSLI")

#: Root package whose sub-packages are the auto-discovered analyzers.
PRODUCERS_PACKAGE = "tabs.image_gallery.analysis.producers"

#: Manifest module inside every producer package (same name discovery uses).
PRODUCER_MODULE = "producer"

#: statuses that mean "no number" — a producer whose whole reply is one of
#: these is journalled as a gap, not as a successful measurement.
_NO_VALUE_STATUSES = frozenset({"gap", "error"})

#: producer id -> callable, filled on first use (a plan that excludes a producer
#: never imports it).
_RUN_FUNCS: dict[str, Callable[[Any], tuple[AxisValue, ...]]] = {}

#: producer id -> package directory name, built by one directory scan on first
#: use. ``None``-valued entries are not cached: an absent id is answered from
#: the index too, so a stale plan does not rescan per item.
_PACKAGE_INDEX: dict[str, str] | None = None


def run_plan(
    resolution: Resolution,
    contexts: Mapping[str, object],
) -> tuple[dict[str, tuple[AxisValue, ...]], RunJournal]:
    """Run *resolution*'s producers over *contexts*.

    *contexts* maps an item path (or a path-like key) to its ``AnalysisContext``.
    The returned dict is keyed by the item path string, one entry per item — an
    item whose plan has no runs still gets an (empty) entry, so "nothing ran" is
    visible as an empty tuple rather than a missing key.
    """
    runs: tuple[ProducerSpec, ...] = tuple(getattr(resolution, "runs", ()) or ())
    items = _normalize_contexts(contexts)

    out: dict[str, tuple[AxisValue, ...]] = {}
    journal: list[JournalEntry] = []
    for path in sorted(items):
        ctx = items[path]
        records: list[AxisValue] = []
        for spec in runs:
            try:
                values = tuple(_run_for(spec.id)(ctx))
            except Exception as exc:  # noqa: BLE001 - a producer failure is a record, not a crash
                reason = f"{type(exc).__name__}: {exc}"
                records.extend(_error_records(spec, reason))
                journal.append(
                    JournalEntry(
                        producer=spec.id,
                        status="error",
                        reason=reason,
                        items=len(spec.provides),
                    )
                )
                logger.debug(
                    "analysis run: producer %s failed on %s (%s)",
                    spec.id,
                    path,
                    reason,
                    exc_info=True,
                )
                continue
            records.extend(values)
            journal.append(_journal_entry(spec, values))
        out[path] = tuple(records)
    return out, RunJournal(entries=tuple(journal))


def _normalize_contexts(contexts: Mapping[str, object]) -> dict[str, object]:
    """Path-string keyed copy of *contexts* (path-like keys are accepted)."""
    if not contexts:
        return {}
    out: dict[str, object] = {}
    for key, ctx in contexts.items():
        out[str(key)] = ctx
    return out


def _error_records(spec: ProducerSpec, reason: str) -> tuple[AxisValue, ...]:
    """One ``status="error"`` record for every axis *spec* declares."""
    return tuple(
        AxisValue(
            axis=str(axis),
            value=None,
            producer=spec.id,
            status="error",
            reason=reason,
        )
        for axis in spec.provides
    )


def _journal_entry(
    spec: ProducerSpec, values: tuple[AxisValue, ...]
) -> JournalEntry:
    """Journal outcome for one producer over one item."""
    if values and all(str(value.status) in _NO_VALUE_STATUSES for value in values):
        reason = next((value.reason for value in values if value.reason), "")
        return JournalEntry(
            producer=spec.id, status="gap", reason=reason, items=len(values)
        )
    return JournalEntry(producer=spec.id, status="ok", items=len(values))


def _run_for(producer_id: str) -> Callable[[Any], tuple[AxisValue, ...]]:
    """The ``run(ctx)`` callable of *producer_id*, imported on first use.

    Raises (``LookupError``/``ImportError``) when the producer is not installed
    or has no ``run`` — the caller turns that into error records, so a stale plan
    degrades visibly instead of crashing the batch.
    """
    key = str(producer_id)
    cached = _RUN_FUNCS.get(key)
    if cached is not None:
        return cached
    package = _package_for(key)
    if package is None:
        raise LookupError(
            f"no analysis producer package declares id {key!r} under "
            f"{PRODUCERS_PACKAGE}"
        )
    module = importlib.import_module(
        f"{PRODUCERS_PACKAGE}.{package}.{PRODUCER_MODULE}"
    )
    run = getattr(module, "run", None)
    if not callable(run):
        raise LookupError(
            f"analysis producer {key!r} ({package}) exports no callable run(ctx)"
        )
    _RUN_FUNCS[key] = run
    return run


def _package_for(producer_id: str) -> str | None:
    """Directory name of the package whose manifest declares *producer_id*."""
    return _package_index().get(str(producer_id))


def _package_index() -> dict[str, str]:
    """One scan: producer id -> package directory name (cached per process).

    Built by importing manifests only — the same import weight as discovery —
    and by first-wins on a duplicate id (the registry's own rule, so the two
    scans cannot disagree).
    """
    global _PACKAGE_INDEX
    if _PACKAGE_INDEX is not None:
        return _PACKAGE_INDEX
    index: dict[str, str] = {}
    for name in _package_names():
        module_name = f"{PRODUCERS_PACKAGE}.{name}.manifest"
        try:
            manifest = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - skip = the registry's own rule
            logger.debug(
                "analysis run: manifest %s failed to import (%s: %s); skipped",
                module_name,
                type(exc).__name__,
                exc,
            )
            continue
        spec = getattr(manifest, PRODUCER_ATTR, None)
        producer_id = str(getattr(spec, "id", "") or "")
        if producer_id and producer_id not in index:
            index[producer_id] = name
    _PACKAGE_INDEX = index
    return index


def _package_names() -> list[str]:
    """Sub-package names under the analyzers root, sorted, ``_`` excluded.

    Mirrors ``engine.analysis.registry`` on purpose: the runner must resolve a
    plan spec back to the package discovery read, without hand-wiring a map.
    """
    try:
        found = importlib.util.find_spec(PRODUCERS_PACKAGE)
    except (ImportError, ValueError):
        return []
    locations = list(getattr(found, "submodule_search_locations", None) or ())
    names: set[str] = set()
    for location in locations:
        try:
            entries = os.listdir(location)
        except OSError:
            continue
        for entry in entries:
            if entry.startswith("_") or entry in names:
                continue
            path = os.path.join(location, entry)
            if not os.path.isdir(path):
                continue
            if not os.path.isfile(os.path.join(path, "__init__.py")):
                continue
            names.add(entry)
    return sorted(names)


__all__ = ["PRODUCERS_PACKAGE", "PRODUCER_MODULE", "run_plan"]
