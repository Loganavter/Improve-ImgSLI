"""The VLM metric-profile selector — plan P2/P3 (one pinned, pool-constrained call).

The content-aware half of the adaptive-profile pipeline: from the probe members
chosen by ``use_cases/profile_probe`` and a compact salience summary, ask a
vision model to pick the axes that discriminate THIS series **from the closed
pool** (``metric_profile.MEASURED_POOL``). The model is a *selector*, never a
source of new axes: unknown/free-form ids are dropped by ``MetricProfile``.

One call per unchanged folder-generation: the selection is pinned
(``services/profile_cache``, keyed on member fingerprint + mode + model + pool),
and a re-run over unchanged inputs is served from disk with no second HTTP
call. Every failure (AI off, no probe members, transport raise, junk reply)
degrades to the deterministic heuristic profile
(``profile_select.derive_profile``) — the control always yields a usable axis
set. Malformed replies are deliberately not pinned (a later pass may retry),
mirroring ``services/jev_cache``.

Reuse, not rebuild: the transport is the shared ``services.ai_client.call_sync``
seam, the JSON envelope is forced with ``response_format={"type":
"json_object"}`` (the single-image ``ai_client.build_request`` idiom), the
answer budget comes from ``ask_router.estimate_ask_max_tokens``, image bytes
are downscaled by ``vlm._encode_image`` and the reply is extracted with the
tolerant ``ai_client.parse._extract_json``.

Pure at import time — no Qt, no HTTP, no state. Every heavy import happens
inside the function that needs it and fails open.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("ImproveImgSLI")


def _as_list(items) -> list:
    try:
        return list(items or ())
    except Exception:
        return []


def _attr(obj, name, default=""):
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    return value


def ai_selector_available(settings) -> bool:
    """True when a profile call can even be attempted. Never raises.

    The same gate the rest of the gallery uses: AI enabled, an API key, and an
    endpoint to reach (a model id or a custom base URL).
    """
    try:
        enabled = bool(_attr(settings, "enabled", False))
        api_key = str(_attr(settings, "api_key", "") or "")
        model = str(_attr(settings, "model", "") or "")
        base_url = str(_attr(settings, "base_url", "") or "")
        return bool(enabled and api_key and (model or base_url))
    except Exception:
        return False


def profile_fingerprint(items, *, mode, model, pool=None) -> str:
    """The pin identity for one folder-generation (delegates to the cache key).

    ``sha256`` over sorted ``str(path):mtime_ns`` plus the mode, the model and
    the pool ids — one definition, in ``services/profile_cache`` (this is the
    ``use_cases``-side name, so the wiring lane never imports the cache layer
    for it).
    """
    from tabs.image_gallery.services import profile_cache

    return profile_cache.profile_cache_key(items, mode=mode, model=model, pool=pool)


def _estimate_budget(count: int, effort: str) -> int:
    try:
        from tabs.image_gallery.services.ask_router import estimate_ask_max_tokens

        return int(estimate_ask_max_tokens({"count": int(count)}, effort=effort))
    except Exception:
        return 0


def _selector_text(salience) -> str:
    """The single text part: every pool axis id + label, the salience, the rule."""
    try:
        from tabs.image_gallery.services.metric_profile import MEASURED_POOL
    except Exception:
        MEASURED_POOL = ()
    try:
        from tabs.image_gallery.services.metric_scores import spec_for
    except Exception:
        spec_for = lambda _axis_id: None  # noqa: E731

    lines = ["METRIC POOL — choose axis ids ONLY from this list:"]
    for axis_id in MEASURED_POOL:
        spec = spec_for(axis_id)
        label = str(getattr(spec, "label", "") or axis_id)
        lines.append(f"- {axis_id} — {label}")
    lines.append("")
    lines.append("SALIENCE SUMMARY (members, adaptive probe size k, axes by spread):")
    lines.append(_summary_text(salience))
    lines.append("")
    lines.append(
        'INSTRUCTION: reply with ONLY a JSON object {"axes": ["<id>", ...]} '
        "choosing the axes that discriminate THIS series, from the listed ids "
        "only, or an empty list if none."
    )
    return "\n".join(lines)


def _summary_text(salience) -> str:
    try:
        members = int((salience or {}).get("members", 0) or 0)
        k = int((salience or {}).get("k", 0) or 0)
        rows = list((salience or {}).get("axes", []) or [])
    except Exception:
        return "members=0 k=0 axes=-"
    parts = []
    for row in rows:
        try:
            parts.append(f"{row.get('id')}:{float(row.get('spread', 0.0)):g}")
        except Exception:
            continue
    return f"members={members} k={k} axes=" + (", ".join(parts) or "-")


def build_profile_request(probe_items, *, model, salience, effort: str = "auto", max_tokens: int = 0) -> dict:
    """The one user message: pool listing + salience text, then one image each.

    Returns a chat-completions payload with response_format pinned to
    ``{"type": "json_object"}`` (reasoning models must not answer in prose) and
    a budget from ``estimate_ask_max_tokens`` unless a positive *max_tokens* is
    passed. Probe images are downscaled through ``vlm._encode_image``; an
    unreadable image is skipped, never fatal.
    """
    probes = _as_list(probe_items)
    content: list[dict] = [{"type": "text", "text": _selector_text(salience)}]
    try:
        from tabs.image_gallery.services.vlm import _encode_image
    except Exception:
        _encode_image = None
    if _encode_image is not None:
        for item in probes:
            try:
                mime, data = _encode_image(str(getattr(item, "path", "")))
            except Exception:
                continue
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{mime};base64,{data}"},
                }
            )
    budget = 0
    try:
        budget = int(max_tokens or 0)
    except Exception:
        budget = 0
    if budget <= 0:
        budget = _estimate_budget(len(probes), effort)
    return {
        "model": str(model or ""),
        "messages": [{"role": "user", "content": content}],
        "max_tokens": budget,
        "response_format": {"type": "json_object"},
    }


def _bare_id_list(text) -> list | None:
    """A bare JSON array of ids in a reply (fences/reasoning tolerated)."""
    source = str(text or "")
    try:
        from tabs.image_gallery.services.ai_client.parse import _strip_reasoning

        source = _strip_reasoning(source)
    except Exception:
        pass
    candidates = [source.strip().strip("`").strip()]
    i, j = source.find("["), source.rfind("]")
    if 0 <= i < j:
        candidates.append(source[i : j + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, list):
            return parsed
    return None


def _reply_ids(text) -> list | None:
    """The id list a reply carries: ``{"axes": [...]}`` or a bare array."""
    obj = None
    try:
        from tabs.image_gallery.services.ai_client.parse import _extract_json

        obj = _extract_json(text)
    except Exception:
        obj = None
    ids = None
    if isinstance(obj, dict):
        axes = obj.get("axes")
        if isinstance(axes, list):
            ids = axes
    if ids is None:
        ids = _bare_id_list(text)
    if ids is None:
        return None
    out = [entry.strip() for entry in ids if isinstance(entry, str) and entry.strip()]
    return out or None


def parse_profile_reply(text, *, mode=None):
    """Tolerant parse of a profile reply → ``MetricProfile`` | ``None``.

    Accepts ``{"axes": ["<id>", ...]}`` (also a bare array), through the shared
    tolerant JSON extractor. Ids are coerced by ``MetricProfile`` — unknown and
    duplicated ids are dropped, order is registry order. Returns ``None`` when
    nothing usable was found (no JSON, an empty list, or ids that are all
    outside the pool): never a guess, never a free-form axis.
    """
    ids = _reply_ids(text)
    if not ids:
        return None
    try:
        from tabs.image_gallery.services.metric_profile import MetricProfile

        profile = MetricProfile(axis_ids=tuple(ids), mode=mode, source="vlm")
    except Exception:
        return None
    return profile if profile.axis_ids else None


def _reply_text(raw) -> str:
    try:
        content = raw["choices"][0]["message"]["content"]
    except Exception:
        return ""
    if isinstance(content, list):
        parts = [
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)


def _default_client_call():
    try:
        from tabs.image_gallery.services import ai_client

        return ai_client.call_sync
    except Exception:
        return None


def choose_profile_sync(
    items,
    *,
    mode,
    settings,
    folder_key=None,
    salience=None,
    reference_path=None,
    cache=None,
    client_call=None,
):
    """The single entry the wiring lane calls → a usable ``MetricProfile``.

    Order (plan P2 §Select):

    1. AI not configured → the deterministic heuristic profile
       (``profile_select.derive_profile``) — **no** call;
    2. a pin hit for this folder-generation → the pinned profile (source
       ``vlm`` preserved) — **no** call;
    3. otherwise probe the K most-deviant members, build the pool-constrained
       request, call the transport, parse, pin and return.

    Any failure — no probe members, no transport, a raising transport, a junk
    reply — degrades to the heuristic profile. Never raises. ``client_call``
    defaults to ``ai_client.call_sync`` and is invoked as
    client_call(base_url, api_key, payload). folder_key is accepted for
    call-site symmetry; the pin identity is the member fingerprint.
    """
    from tabs.image_gallery.use_cases import profile_select

    members = _as_list(items)

    def _heuristic():
        try:
            return profile_select.derive_profile(members, mode=mode)
        except Exception:
            from tabs.image_gallery.services.metric_profile import profile_for_mode

            return profile_for_mode(mode)

    if not ai_selector_available(settings):
        return _heuristic()

    from tabs.image_gallery.services import profile_cache
    from tabs.image_gallery.use_cases import profile_probe

    model = str(_attr(settings, "model", "") or "")
    base_url = str(_attr(settings, "base_url", "") or "")
    api_key = str(_attr(settings, "api_key", "") or "")

    try:
        key = profile_cache.profile_cache_key(members, mode=mode, model=model)
    except Exception:
        key = ""

    cache_obj = cache if cache is not None else profile_cache.default_cache()
    if key:
        try:
            hit = cache_obj.get(key)
        except Exception:
            hit = None
        if hit is not None:
            return hit

    try:
        probes = profile_probe.probe_members(members, reference_path=reference_path)
    except Exception:
        probes = ()
    if not probes:
        return _heuristic()

    summary = salience if salience is not None else profile_probe.salience_summary(members)
    try:
        payload = build_profile_request(
            probes,
            model=model,
            salience=summary,
            effort=str(_attr(settings, "reasoning_effort", "auto") or "auto"),
        )
    except Exception:
        return _heuristic()

    call = client_call or _default_client_call()
    if call is None:
        return _heuristic()
    try:
        raw = call(base_url, api_key, payload)
    except Exception:
        logger.debug("profile select call failed", exc_info=True)
        return _heuristic()

    profile = parse_profile_reply(_reply_text(raw), mode=mode)
    if profile is None:
        return _heuristic()
    if key:
        try:
            cache_obj.put(key, profile)
        except Exception:
            pass
    return profile


__all__ = [
    "ai_selector_available",
    "build_profile_request",
    "choose_profile_sync",
    "parse_profile_reply",
    "profile_fingerprint",
]
