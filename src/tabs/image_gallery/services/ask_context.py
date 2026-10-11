"""Scope → structured context builder for the gallery "Ask AI" surface (A1).

The single seam between the UI scopes (a whole series, or the current
selection) and every AI backend. It assembles the measured table ONCE via
``metric_scores`` (the canonical metric registry) + ``use_cases.quality``
(the canonical severity reader) plus item names/counts/mode/source. No surface
re-derives metrics from raw ``item.metrics`` ad hoc, and the router never
touches ``GalleryItem`` — it only consumes the dict this module returns.

Pure-ish: no Qt, no network, no writes. Reads controller state and GalleryItem
fields only. See ``plan-gallery-ask-ai`` (Payload schema frozen for the epic).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tabs.image_gallery.services.metric_scores import SPECS, measured_scores
from tabs.image_gallery.use_cases import quality as _quality

#: Scope kinds the builder recognizes.
ASK_SERIES = "series"
ASK_SELECTION = "selection"


@dataclass(frozen=True)
class AskScope:
    """Which slice of the pool the question is about.

    ``kind`` is ``"series"`` (a whole clustered series, identified by
    ``series_id`` and/or the explicit ``paths``) or ``"selection"`` (the
    current manual selection; falls back to ``controller.state.selected_paths``
    when ``paths`` is empty).
    """

    kind: str = ASK_SELECTION
    paths: tuple[Path, ...] = ()
    label: str = ""
    series_id: str | None = None


def _state(controller) -> Any:
    return getattr(controller, "state", None)


def _find_item(controller, path) -> Any:
    """Resolve one GalleryItem for *path* (controller ``_find_item`` first)."""
    try:
        fn = getattr(controller, "_find_item", None)
        if callable(fn):
            item = fn(path)
            if item is not None:
                return item
    except Exception:
        pass
    want = str(path)
    try:
        for item in list(getattr(_state(controller), "items", None) or []):
            if str(getattr(item, "path", "")) == want:
                return item
    except Exception:
        pass
    return None


def _series_members(controller, series_id) -> list:
    if not series_id:
        return []
    try:
        for ser in list(getattr(_state(controller), "series", None) or []):
            if getattr(ser, "id", None) == series_id:
                return list(getattr(ser, "members", None) or [])
    except Exception:
        pass
    return []


def _selection_paths(controller) -> list:
    state = _state(controller)
    try:
        ordered = list(getattr(state, "selected_order", None) or [])
        if ordered:
            return ordered
    except Exception:
        pass
    try:
        return list(getattr(state, "selected_paths", None) or [])
    except Exception:
        return []


def _resolve_items(scope: AskScope, controller) -> tuple[list, str]:
    """Resolve the items + a human label for *scope* (fail-open to empty)."""
    kind = scope.kind if scope.kind in (ASK_SERIES, ASK_SELECTION) else ASK_SELECTION
    paths: list = [Path(p) for p in (scope.paths or ())]
    label = str(scope.label or "")
    if kind == ASK_SERIES:
        members = _series_members(controller, scope.series_id)
        if members:
            items = members
        else:
            items = [it for it in (_find_item(controller, p) for p in paths) if it is not None]
        if not label:
            label = f"Series {scope.series_id}" if scope.series_id else "Series"
    else:
        if not paths:
            paths = [Path(p) for p in _selection_paths(controller)]
        items = [it for it in (_find_item(controller, p) for p in paths) if it is not None]
        if not label:
            label = "Selection"
    return items, label


def _item_context(item, alias: str) -> dict:
    """One item's structured context (measured scores + severities + badge).

    ``name`` is the real filename (kept for the app); ``alias`` is the opaque
    label the model is asked to use, so a descriptive filename ("...soft...")
    cannot bias it into a conclusion the metrics contradict.
    """
    raw_metrics = getattr(item, "metrics", None)
    if not isinstance(raw_metrics, dict):
        raw_metrics = {}
    scores = {mid: int(score) for mid, _label, _raw, score in measured_scores(raw_metrics)}
    try:
        severities = dict(_quality.severities(item))
    except Exception:
        severities = {}
    try:
        name = item.path.name
    except Exception:
        name = str(getattr(item, "path", ""))
    return {
        "name": name,
        "alias": alias,
        "path": str(getattr(item, "path", "")),
        "metrics": scores,
        "severities": severities,
        "badge": str(getattr(item, "badge", "") or ""),
    }


def deanonymize_answer(text: str, names: dict | None) -> str:
    """Replace alias tokens (``img_1``, …) with their real item names.

    Alias→real substitution runs longest-alias-first so ``img_1`` never eats
    ``img_10``, and is case-insensitive (models often recapitalize).
    """
    if not text or not names:
        return text
    out = str(text)
    try:
        pairs = sorted(
            ((str(a), str(b)) for a, b in dict(names).items() if a and b),
            key=lambda kv: -len(kv[0]),
        )
    except Exception:
        return out
    for alias, real in pairs:
        try:
            out = re.sub(re.escape(alias), real, out, flags=re.IGNORECASE)
        except Exception:
            continue
    return out


def build_ask_context(scope: AskScope, *, controller) -> dict:
    """Assemble the frozen context dict for *scope*.

    Shape::

        { 'kind': 'series'|'selection', 'label': str, 'count': int,
          'mode': str, 'source': str|None,
          'items': [{'name','path','metrics':{id:score},
                     'severities':{name:severity},'badge':str}, ...] }
    """
    if not isinstance(scope, AskScope):
        scope = AskScope()
    kind = scope.kind if scope.kind in (ASK_SERIES, ASK_SELECTION) else ASK_SELECTION
    items, label = _resolve_items(scope, controller)
    ctx_items = []
    names: dict[str, str] = {}
    for index, item in enumerate(items):
        alias = f"img_{index + 1}"
        entry = _item_context(item, alias)
        names[alias] = entry["name"]
        ctx_items.append(entry)

    state = _state(controller)
    try:
        mode = _quality.normalize_mode(getattr(state, "mode", None))
    except Exception:
        mode = "fidelity"
    source = getattr(state, "source_path", None)
    source_str: str | None
    try:
        source_str = str(source) if source is not None else None
    except Exception:
        source_str = None

    return {
        "kind": kind,
        "label": label,
        "count": len(ctx_items),
        "mode": mode,
        "source": source_str,
        "items": ctx_items,
        # alias → real filename; the app uses this to de-anonymize answers.
        "names": names,
        # metric id → human label (same wording the report shows), so the
        # model never has to guess what e.g. "typicality" means.
        "metric_labels": {spec.id: spec.label for spec in SPECS},
    }


__all__ = [
    "ASK_SELECTION",
    "ASK_SERIES",
    "AskScope",
    "build_ask_context",
    "deanonymize_answer",
]
