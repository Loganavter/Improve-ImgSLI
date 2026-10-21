"""Wave C2: the coverage / first-paint-hold decisions read their own parameters.

Both functions used to wrap a *parameter* access in ``try: ... except
NameError:`` and fall back to a constant. The handler could never fire (the
name is bound by the function's own parameter list, verified by an AST check
over every try-block whose handler catches ``NameError``: the try body's only
loaded name is a parameter of the enclosing ``def``), so its fallback was dead
code that claimed the decision had a missing input. C2 deleted the handlers.

These tests execute the previously-guarded line through the branch that logs
it and assert the *parameter value* is what the decision and the log carry —
i.e. a "name missing -> constant" fallback cannot come back unnoticed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.frame.context import FrameContext
from tabs.image_compare.canvas.rhi_renderer.use_cases import coverage as coverage_mod
from tabs.image_compare.canvas.rhi_renderer.use_cases.coverage import (
    apply_first_paint_hold,
    evaluate_coverage,
)


def _base_image() -> SimpleNamespace:
    return SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )


def _capture_debug(monkeypatch) -> list[tuple[str, tuple]]:
    calls: list[tuple[str, tuple]] = []

    def _debug(message: str, *args) -> None:
        calls.append((message, args))

    monkeypatch.setattr(coverage_mod, "rhi_render_debug", _debug)
    monkeypatch.setattr(coverage_mod, "rhi_render_debug_enabled", lambda: True)
    monkeypatch.setattr(coverage_mod, "_ic_preview_enabled", lambda: False)
    monkeypatch.setattr(coverage_mod, "_ic_preview_log", lambda *a, **k: None)
    monkeypatch.setattr(coverage_mod, "_gap_enabled", lambda: False)
    monkeypatch.setattr(coverage_mod, "_throttle_emit", lambda *a, **k: True)
    return calls


def _gap_detected_message(calls: list[tuple[str, tuple]]) -> str:
    for message, args in calls:
        if "GAP_DETECTED" in message:
            return message % args
    raise AssertionError(f"no GAP_DETECTED log; calls={calls!r}")


def test_evaluate_coverage_logs_main_more_pending_parameter(monkeypatch):
    """The GAP_DETECTED decision reads ``main_more_pending``, not a fallback.

    ``_fallback_more_pending_snapshot`` is ``None`` here, i.e. the caller's
    ``main_more_pending`` argument IS the decision — the exact line the deleted
    ``except NameError`` used to guard.
    """
    calls = _capture_debug(monkeypatch)
    renderer = SimpleNamespace(
        _fallback_atomic_snapshot=False,
        _fallback_more_pending_snapshot=None,
    )

    covered1, covered2, _bbox = evaluate_coverage(
        renderer,
        tile_service=SimpleNamespace(),
        texture_keys=("a", "b"),
        base_image=_base_image(),
        viewport_zoom=None,
        viewport_offset=None,
        array_draw_plan=[],
        main_more_pending=True,
    )

    # Empty plan -> nothing covered in the visible rect -> the gap branch runs.
    assert covered1 < 0.999 and covered2 < 0.999
    message = _gap_detected_message(calls)
    assert "main_more_pending=True" in message, message
    assert "decision_atomic=False" in message, message


def test_evaluate_coverage_false_parameter_is_not_coerced(monkeypatch):
    """Control: ``main_more_pending=False`` logs False (no "default False" drift)."""
    calls = _capture_debug(monkeypatch)
    renderer = SimpleNamespace(
        _fallback_atomic_snapshot=False,
        _fallback_more_pending_snapshot=None,
    )

    evaluate_coverage(
        renderer,
        tile_service=SimpleNamespace(),
        texture_keys=("a", "b"),
        base_image=_base_image(),
        viewport_zoom=None,
        viewport_offset=None,
        array_draw_plan=[],
        main_more_pending=False,
    )

    message = _gap_detected_message(calls)
    assert "main_more_pending=False" in message, message


def test_first_paint_hold_reads_prev_last_good_parameter(monkeypatch):
    """``prev_last_good is None`` decides the hold — and the hold mutates state.

    ``prev_last_good`` is the parameter the deleted ``except NameError`` used to
    guard; a "False when the name is missing" fallback would silently turn the
    first-paint hold off, so this asserts the parameter drives both the return
    value and the recorded/logged fact.
    """
    calls = _capture_debug(monkeypatch)
    renderer = SimpleNamespace(_last_good_texture_keys=("tile",), _last_good_diff_key="k")
    frame_context = FrameContext()
    plan = [SimpleNamespace(rect1=(0, 0, 1, 1), rect2=(0, 0, 1, 1), bbox=(0, 0, 1, 1))]

    held = apply_first_paint_hold(
        renderer,
        plan,
        plan,
        main_more_pending=True,
        prev_last_good=None,
        covered_ok=True,
        frame_context=frame_context,
    )

    assert held == []
    assert renderer._last_good_texture_keys is None
    assert renderer._last_good_diff_key is None
    message, args = next((m, a) for m, a in calls if "FIRST_PAINT_HOLD" in m)
    assert "more_pending=True" in message % args
    decisions = [d for d in frame_context._decisions if d.pass_name == "first_paint_hold"]
    assert decisions and decisions[-1].verdict == "ran"


def test_first_paint_hold_keeps_plan_when_a_baseline_exists(monkeypatch):
    """Control: with ``prev_last_good`` set, the same input is not held."""
    _capture_debug(monkeypatch)
    renderer = SimpleNamespace()
    plan = [SimpleNamespace(rect1=(0, 0, 1, 1), rect2=(0, 0, 1, 1), bbox=(0, 0, 1, 1))]

    kept = apply_first_paint_hold(
        renderer,
        plan,
        plan,
        main_more_pending=True,
        prev_last_good=object(),
        covered_ok=True,
    )

    assert kept is plan


@pytest.mark.parametrize(
    "enclosing, guarded",
    [
        ("evaluate_coverage", "main_more_pending"),
        ("apply_first_paint_hold", "prev_last_good"),
    ],
)
def test_previously_guarded_names_are_enclosing_parameters(enclosing, guarded):
    """Pin the C2 claim: both guards were dead code over a real parameter.

    The AST half of the red-before story: the name the ``try`` body loads is in
    the enclosing ``def``'s parameter list, so ``except NameError`` could never
    fire. If a future edit moved either decision into a genuinely optional name,
    this test says so before the fallback is "fixed" by swallowing again.
    """
    import ast
    from pathlib import Path

    source = (
        Path(coverage_mod.__file__).read_text(encoding="utf-8")
    )
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == enclosing
    )
    parameters = {
        argument.arg
        for argument in (
            list(function.args.posonlyargs)
            + list(function.args.args)
            + list(function.args.kwonlyargs)
        )
    }
    assert guarded in parameters
    loads = {
        node.id
        for node in ast.walk(function)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == guarded
    }
    assert loads
