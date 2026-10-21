"""``run(ctx)`` — the per-image AI scorecard (network path 1) as a producer.

This wraps the existing AI path; it does not re-implement it:

- the payload comes from ``ai_client.request.build_request_from_bytes`` — the
  SAME shape the file-path upload builds, so the two upload paths cannot drift
  (the defect B2: a payload setting applied to one path only);
- the reply goes through ``ai_client.parse.parse_response`` — the tolerant
  parser (code fences, reasoning wrappers, legacy ``KEY: value`` lines) — never
  a second JSON reader here;
- the model, endpoint and params come from ``ctx.backend``, a ``BackendRef``
  the catalog resolved. This producer names no model id and cannot pick one
  (invariant I2).

There is no file I/O and no transport in this module: ``ctx.image_bytes`` was
read once by the executor and ``ctx.call`` is the credential-bearing closure it
injected, so an api key never reaches a record, a cache key or this module
(plan trap 1 / gate G11).

A missing input, a failed call, a malformed/empty reply and an omitted axis all
become ``status="gap"`` values with their own reason — never an exception and
never a substituted number (invariant I1).
"""

from __future__ import annotations

from engine.analysis.contracts import AxisValue, BackendRef
from engine.analysis.context import AnalysisContext

from tabs.image_gallery.services.ai_client.parse import parse_response
from tabs.image_gallery.services.ai_client.request import (
    build_request_from_bytes,
    mime_for_path,
)

from . import manifest

#: Id carried by every record this producer emits. ``local`` is the local
#: detectors' family id; the model's scorecard is ``vlm`` — a surface can tell
#: "a detector measured this" from "a model judged this" without a domain flag.
PRODUCER_ID = "vlm"

NO_BACKEND_REASON = "no backend resolved for this run"
NO_TRANSPORT_REASON = "no transport for this run"
NO_BYTES_REASON = "no image bytes in the context"
NOT_SCORED_REASON = "the model did not score this axis"


def _axes(profile=None) -> tuple[str, ...]:
    """The declared axes (manifest) plus the axes the JUDGE named (P7-B).

    The manifest is the registry vocabulary; a judge-named axis has no manifest
    entry (it is not a local measurement), but the scorecard asked for it by
    name, so its record must reach the read path instead of becoming a gap.
    """
    out = list(_axes_registry())
    try:
        from tabs.image_gallery.services.profile_judged import judged_axis_entries

        for entry in judged_axis_entries(profile):
            name = str(getattr(entry, "name", "") or "").strip()
            if name and name not in out:
                out.append(name)
    except Exception:
        pass
    return tuple(out)


def _axes_registry() -> tuple[str, ...]:
    """The declared registry axes, from the manifest (single vocabulary)."""
    return tuple(manifest.PRODUCER.provides)


def _gaps(axes: tuple[str, ...], reason: str) -> tuple[AxisValue, ...]:
    return tuple(
        AxisValue(
            axis=axis,
            value=None,
            producer=PRODUCER_ID,
            status="gap",
            reason=reason,
        )
        for axis in axes
    )


def _reply_as_response(reply: object) -> dict:
    """Wrap the transport's raw text into the chat-completion dict the parser reads.

    ``ctx.call`` returns the reply TEXT (the executor owns the transport, so it
    owns SSE reassembly too); ``parse_response`` is written against the
    non-streaming response dict, and its tolerance (fences/reasoning/legacy
    lines) must not be duplicated. One wrapping point keeps that contract.
    """
    text = reply if isinstance(reply, str) else str(reply if reply is not None else "")
    return {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": None,
            }
        ]
    }


def _value(axis: str, scored: dict, backend: BackendRef) -> AxisValue:
    if axis not in scored:
        return AxisValue(
            axis=axis,
            value=None,
            producer=PRODUCER_ID,
            backend=backend,
            status="gap",
            reason=NOT_SCORED_REASON,
        )
    return AxisValue(
        axis=axis,
        value=float(scored[axis]),
        producer=PRODUCER_ID,
        backend=backend,
    )


def run(ctx: AnalysisContext) -> tuple[AxisValue, ...]:
    """The model's scorecard for *ctx*; gaps (with reasons) when it cannot answer."""
    profile = ctx.extra.get("profile")
    axes = _axes(profile)
    if ctx.backend is None:
        return _gaps(axes, NO_BACKEND_REASON)
    if ctx.call is None:
        return _gaps(axes, NO_TRANSPORT_REASON)
    if ctx.image_bytes is None:
        return _gaps(axes, NO_BYTES_REASON)

    payload = build_request_from_bytes(
        ctx.image_bytes,
        mime_for_path(ctx.item_path),
        model=ctx.backend.model,
        mode=ctx.mode,
        profile=ctx.extra.get("profile"),
        metrics=ctx.extra.get("metrics"),
        reasoning_effort=str(ctx.backend.params.get("effort", "auto")),
    )
    try:
        reply = ctx.call(payload)
    except Exception as exc:  # a transport failure is a gap with its cause
        return _gaps(
            axes, f"the AI call failed ({type(exc).__name__}: {exc})"
        )
    try:
        result = parse_response(
            _reply_as_response(reply), model=ctx.backend.model, profile=profile
        )
    except Exception as exc:
        return _gaps(
            axes, f"the AI reply could not be parsed ({type(exc).__name__}: {exc})"
        )
    scored = getattr(result, "axes", None) or {}
    return tuple(_value(axis, scored, ctx.backend) for axis in axes)


__all__ = [
    "NO_BACKEND_REASON",
    "NO_BYTES_REASON",
    "NO_TRANSPORT_REASON",
    "NOT_SCORED_REASON",
    "PRODUCER_ID",
    "run",
]
