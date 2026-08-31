"""Metrics triggers — extracted from _session_controller.py"""

from __future__ import annotations


def trigger_metrics_calculation_if_needed(controller):
    try:
        presenter=getattr(controller,"presenter",None)
        widget=getattr(presenter,"widget",None) if presenter is not None else None
        if widget is not None:
            is_hidden=False
            try:
                if hasattr(widget,"is_current_stack_page"): is_hidden=not widget.is_current_stack_page()
                else:
                    window=widget.window()
                    ui=getattr(window,"ui",None) if window is not None else None
                    if ui is None:
                        pp=getattr(window,"presenter",None) if window is not None else None
                        ui=getattr(pp,"ui",None) if pp is not None else None
                    stack=getattr(ui,"workspace_stack",None) if ui is not None else None
                    if stack is not None:
                        cur=stack.currentWidget()
                        is_hidden=cur is not widget and not (cur is not None and hasattr(cur,"isAncestorOf") and cur.isAncestorOf(widget))
                    else: is_hidden=not bool(widget.isVisible())
            except Exception:
                try: is_hidden=not bool(widget.isVisible())
                except Exception: is_hidden=False
            if is_hidden:
                widget._metrics_stale=True  # type: ignore
                try:
                    from core.tracing.tracer import Tracer
                    if Tracer.enabled(): Tracer.instance().record("metrics.deferred","metrics deferred - background tab",{})
                except Exception: pass
                return
    except Exception: pass
    controller.metrics_service.trigger_metrics_calculation_if_needed()

def trigger_full_diff_generation(controller):
    try:
        presenter=getattr(controller,"presenter",None)
        widget=getattr(presenter,"widget",None) if presenter is not None else None
        if widget is not None:
            is_hidden=False
            try:
                if hasattr(widget,"is_current_stack_page"): is_hidden=not widget.is_current_stack_page()
                else: is_hidden=not bool(widget.isVisible())
            except Exception: is_hidden=False
            if is_hidden:
                widget._metrics_stale=True  # type: ignore
                try:
                    from core.tracing.tracer import Tracer
                    if Tracer.enabled(): Tracer.instance().record("metrics.deferred","diff generation deferred - background tab",{})
                except Exception: pass
                return
    except Exception: pass
    if controller.diff_service is not None:
        controller.diff_service.request_generation(optimize_ssim=False)
