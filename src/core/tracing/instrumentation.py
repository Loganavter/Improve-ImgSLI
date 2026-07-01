from __future__ import annotations

import logging
from dataclasses import fields, is_dataclass
from typing import Any

import time

from .tracer import Tracer, diff_dataclass

logger = logging.getLogger("ImproveImgSLI")

_PATCHED = False

def install_instrumentation() -> None:
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    _patch_dispatcher()
    _patch_store()
    _patch_event_bus()
    _patch_widget_registry()
    _patch_render_plan()
    _patch_hit_test()
    _patch_gl_canvas_input()

    logger.info("ImgSLI tracer instrumentation installed")

def _patch_dispatcher() -> None:
    from core.state_management import dispatcher as dispatcher_mod

    orig_dispatch = dispatcher_mod.Dispatcher.dispatch
    orig_reduce_name = "_reducer"
    tracer = Tracer.instance()

    def traced_dispatch(self, action, scope: str = "viewport"):
        if not Tracer.enabled():
            return orig_dispatch(self, action, scope)

        action_type = getattr(action, "type", type(action).__name__)
        payload = {}
        try:
            payload["action"] = _action_payload(action)
        except Exception:
            payload["action"] = "<unrepr>"
        payload["scope"] = scope

        old_viewport = self._store.viewport
        old_document = self._store.document
        old_settings = self._store.settings

        owns_trace = tracer.current_trace_id() is None
        if owns_trace:
            tracer.begin_trace("dispatch")

        span_id = f"sp{tracer.next_span_id()}"
        payload["span_id"] = span_id
        t0 = time.monotonic()
        tracer.record(
            "dispatch.begin",
            f"dispatch {action_type}",
            payload,
            caller_skip=1,
        )
        tracer._push_depth()
        try:
            result = orig_dispatch(self, action, scope)
        finally:
            tracer._pop_depth()
            try:
                diff_payload = {
                    "viewport": diff_dataclass(old_viewport, self._store.viewport),
                    "document": diff_dataclass(old_document, self._store.document),
                    "settings": diff_dataclass(old_settings, self._store.settings),
                }
                tracer.record(
                    "dispatch.end",
                    f"dispatched {action_type}",
                    {
                        "action_type": action_type,
                        "diff": diff_payload,
                        "scope": scope,
                        "span_id": span_id,
                        "duration_ms": (time.monotonic() - t0) * 1000.0,
                    },
                    caller_skip=1,
                )
            except Exception:
                logger.debug("dispatch trace failed", exc_info=True)
            if owns_trace:
                tracer.end_trace()
        return result

    dispatcher_mod.Dispatcher.dispatch = traced_dispatch

def _action_payload(action) -> dict[str, Any]:
    if hasattr(action, "get_payload"):
        try:
            return _shallow(action.get_payload())
        except Exception:
            pass
    if is_dataclass(action):
        return {f.name: _short(getattr(action, f.name, None)) for f in fields(action)}
    return {"repr": _short(action)}

def _shallow(d: dict[str, Any]) -> dict[str, Any]:
    return {k: _short(v) for k, v in d.items()}

def _short(value, limit: int = 160) -> str:
    try:
        text = repr(value)
    except Exception:
        text = "<unrepr>"
    if len(text) > limit:
        text = text[:limit] + "…"
    return text

def _patch_store() -> None:
    from core import store as store_mod

    orig_emit_state = store_mod.Store.emit_state_change
    orig_emit_viewport = store_mod.Store.emit_viewport_change
    tracer = Tracer.instance()

    def traced_emit_state(self, scope: str = "viewport"):
        if not Tracer.enabled():
            return orig_emit_state(self, scope)
        subs = len(getattr(self, "_change_callbacks", []) or [])
        tracer.record(
            "store.emit_state",
            f"emit_state_change scope={scope} subs={subs}",
            {"scope": scope, "subscribers": subs},
            caller_skip=1,
        )
        tracer._push_depth()
        try:
            return orig_emit_state(self, scope)
        finally:
            tracer._pop_depth()

    def traced_emit_viewport(self, subdomain: str | None = None):
        if not Tracer.enabled():
            return orig_emit_viewport(self, subdomain)
        tracer.record(
            "store.emit_viewport",
            f"emit_viewport subdomain={subdomain}",
            {"subdomain": subdomain},
            caller_skip=1,
        )
        tracer._push_depth()
        try:
            return orig_emit_viewport(self, subdomain)
        finally:
            tracer._pop_depth()

    store_mod.Store.emit_state_change = traced_emit_state
    store_mod.Store.emit_viewport_change = traced_emit_viewport

def _patch_event_bus() -> None:
    from core.plugin_system import event_bus as bus_mod

    orig_emit = bus_mod.EventBus.emit
    tracer = Tracer.instance()

    def traced_emit(self, event):
        if not Tracer.enabled():
            return orig_emit(self, event)
        event_type = type(event).__name__
        subs = self._subscribers.get(type(event), [])
        n_subs = len(subs)
        owns_trace = tracer.current_trace_id() is None
        if owns_trace:
            tracer.begin_trace("evt")
        span_id = f"sp{tracer.next_span_id()}"
        t0 = time.monotonic()
        tracer.record(
            "eventbus.emit",
            f"emit {event_type} subs={n_subs}",
            {"event": event_type, "subscribers": n_subs, "span_id": span_id},
            caller_skip=1,
        )
        tracer._push_depth()
        try:
            return orig_emit(self, event)
        finally:
            tracer._pop_depth()
            tracer.record(
                "eventbus.end",
                f"emitted {event_type}",
                {
                    "event": event_type,
                    "span_id": span_id,
                    "duration_ms": (time.monotonic() - t0) * 1000.0,
                },
                caller_skip=1,
            )
            if owns_trace:
                tracer.end_trace()

    bus_mod.EventBus.emit = traced_emit

def _patch_widget_registry() -> None:
    try:
        from ui.canvas_infra.scene import widget_registry as reg_mod
    except Exception:
        logger.debug("widget_registry patch skipped", exc_info=True)
        return

    tracer = Tracer.instance()

    orig_cmd_alias = reg_mod.get_canvas_feature_command_by_alias

    def traced_cmd_alias(capability_id: str):
        result = orig_cmd_alias(capability_id)
        if Tracer.enabled():
            target = reg_mod.get_canvas_feature_command_aliases().get(capability_id)
            tracer.record(
                "alias.command",
                f"alias {capability_id} -> {target}",
                {"capability_id": capability_id, "target": target, "resolved": bool(result)},
                caller_skip=1,
            )
        return result

    reg_mod.get_canvas_feature_command_by_alias = traced_cmd_alias

_LAST_PLAN_BY_CANVAS: "dict[int, dict]" = {}

def _patch_render_plan() -> None:
    try:
        from ui.canvas_presentation import plan_applicator as pa_mod
    except Exception:
        logger.debug("plan_applicator patch skipped", exc_info=True)
        return

    orig_apply = pa_mod.apply_canvas_render_plan
    tracer = Tracer.instance()

    def traced_apply(canvas, plan, *, store=None, clip_overlays_to_image_bounds: bool = False):
        if not Tracer.enabled():
            return orig_apply(canvas, plan, store=store,
                              clip_overlays_to_image_bounds=clip_overlays_to_image_bounds)
        new_snapshot = _plan_snapshot(plan)
        canvas_key = id(canvas)
        prev_snapshot = _LAST_PLAN_BY_CANVAS.get(canvas_key)
        changed = _snapshot_diff(prev_snapshot, new_snapshot) if prev_snapshot else {"<first>": True}
        _LAST_PLAN_BY_CANVAS[canvas_key] = new_snapshot
        span_id = f"sp{tracer.next_span_id()}"
        t0 = time.monotonic()
        tracer.record(
            "render.apply_plan",
            f"apply_plan canvas={canvas_key & 0xFFFF:x} changed={list(changed.keys())[:6]}",
            {"changed": changed, "canvas_id": canvas_key, "span_id": span_id},
            caller_skip=1,
        )
        tracer._push_depth()
        try:
            return orig_apply(canvas, plan, store=store,
                              clip_overlays_to_image_bounds=clip_overlays_to_image_bounds)
        finally:
            tracer._pop_depth()
            tracer.record(
                "render.apply_end",
                f"apply_plan done",
                {
                    "span_id": span_id,
                    "duration_ms": (time.monotonic() - t0) * 1000.0,
                    "canvas_id": canvas_key,
                },
                caller_skip=1,
            )

    pa_mod.apply_canvas_render_plan = traced_apply

def _plan_snapshot(plan) -> dict:
    snap: dict = {}
    for name in (
        "canvas_w", "canvas_h", "source_key", "capture_visible",
        "guides_enabled", "guides_thickness", "fill_rgba",
        "display_cache_key", "output_scale", "preserve_zoom",
    ):
        try:
            snap[name] = _short(getattr(plan, name, None))
        except Exception:
            snap[name] = "<err>"
    try:
        overlay = getattr(plan, "overlay_layout", None)
        snap["overlay_layout"] = _short(overlay)
    except Exception:
        snap["overlay_layout"] = "<err>"
    return snap

def _snapshot_diff(old: dict, new: dict) -> dict:
    diff: dict = {}
    for k in new.keys() | old.keys():
        if old.get(k) != new.get(k):
            diff[k] = {"old": old.get(k), "new": new.get(k)}
    return diff

def _patch_hit_test() -> None:
    try:
        from ui.canvas_infra.scene import hit_test as ht_mod
    except Exception:
        logger.debug("hit_test patch skipped", exc_info=True)
        return

    orig = ht_mod.find_scene_object_at_position
    tracer = Tracer.instance()

    def traced_find(scene, point):
        result = orig(scene, point)
        if Tracer.enabled():
            kind = type(result).__name__ if result is not None else "None"
            ident = getattr(result, "object_id", None) or getattr(result, "id", None)
            tracer.record(
                "hit_test",
                f"hit {kind} id={ident} at={_short(point)}",
                {"point": _short(point), "result_kind": kind, "result_id": _short(ident)},
                caller_skip=1,
            )
        return result

    ht_mod.find_scene_object_at_position = traced_find

    try:
        from ui.canvas_infra import scene as scene_pkg
        scene_pkg.find_scene_object_at_position = traced_find
    except Exception:
        pass

    try:
        from events.image_label import geometry as geom_mod
        geom_mod.find_scene_object_at_position = traced_find
    except Exception:
        pass

def _patch_gl_canvas_input() -> None:
    try:
        from ui.widgets.canvas import widget as gl_mod
    except Exception:
        logger.debug("gl_canvas patch skipped", exc_info=True)
        return

    tracer = Tracer.instance()

    def wrap(method_name: str, label: str):
        orig = getattr(gl_mod.GLCanvas, method_name, None)
        if orig is None:
            return
        def traced(self, event, _orig=orig, _label=label):
            if not Tracer.enabled():
                return _orig(self, event)
            tracer.begin_trace(_label)
            span_id = f"sp{tracer.next_span_id()}"
            t0 = time.monotonic()
            try:
                tracer.record(
                    f"input.{_label}",
                    f"{_label} {_event_summary(event)}",
                    {"event": _event_summary(event), "span_id": span_id},
                    caller_skip=1,
                )
                tracer._push_depth()
                try:
                    return _orig(self, event)
                finally:
                    tracer._pop_depth()
            finally:
                tracer.record(
                    f"input.{_label}.end",
                    f"{_label} done",
                    {
                        "span_id": span_id,
                        "duration_ms": (time.monotonic() - t0) * 1000.0,
                    },
                    caller_skip=1,
                )
                tracer.end_trace()
        setattr(gl_mod.GLCanvas, method_name, traced)

    for method, label in [
        ("mousePressEvent", "mpress"),
        ("mouseReleaseEvent", "mrel"),
        ("mouseMoveEvent", "mmove"),
        ("wheelEvent", "wheel"),
        ("keyPressEvent", "kpress"),
        ("keyReleaseEvent", "krel"),
    ]:
        wrap(method, label)

def _event_summary(event) -> str:
    parts = []
    try:
        pos = event.position()
        parts.append(f"pos=({pos.x():.0f},{pos.y():.0f})")
    except Exception:
        pass
    try:
        btn = event.button()
        if btn is not None:
            parts.append(f"btn={int(btn)}")
    except Exception:
        pass
    try:
        btns = event.buttons()
        if btns is not None:
            parts.append(f"btns={int(btns)}")
    except Exception:
        pass
    try:
        mods = event.modifiers()
        if mods is not None:
            parts.append(f"mods={int(mods)}")
    except Exception:
        pass
    try:
        key = event.key()
        parts.append(f"key={key}")
    except Exception:
        pass
    try:
        delta = event.angleDelta()
        parts.append(f"dy={delta.y()}")
    except Exception:
        pass
    return " ".join(parts) if parts else type(event).__name__
