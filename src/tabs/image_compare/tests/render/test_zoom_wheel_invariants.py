"""Zoom-wheel transform invariants — property pilot for the evidence layer.

``compute_zoom_wheel_transform`` is pure: a frozen request in, a tuple out.
That makes the input domain small enough to **enumerate** — stronger than random
sampling (no seed, no flake, and a counterexample is always the exact case).
This file is the pilot for the "invariant before test" rule in
``docs/dev/EVIDENCE.md``: every claim below is about ALL bounded inputs, not an
example chosen to pass.

The function's own history is the reason to state properties rather than
examples: a "drop this tick" throttle used to sit in front of it and lost
direction/magnitude on a burst (see ``test_wheel_zoom_magnitude.py``). A
sign-only implementation passes any single-notch example and fails P1/P2.

Properties (P5 is the one the code's ``uv`` clamp exists for):

* **P1 composition** — one event of ``k`` notches equals ``k`` single-notch
  events, while the clamped zoom stays away from the bounds;
* **P2 monotonicity** — a larger ``angle_delta_y`` never zooms out relative to
  a smaller one from the same state;
* **P3 clamp** — result zoom is always in ``[0.1, 50]`` and saturates exactly at
  the bound;
* **P4 no-op** — delta 0, and any delta that cannot move the clamped zoom,
  return ``None``;
* **P5 anchor-or-edge** — the transform anchors the *clamped* content point
  under the cursor: the point ``uv`` that ends up under the cursor equals
  ``clamp(uv_before, 0, 1)``. Inside the content this is exact anchor
  preservation; outside it is the edge staying at the cursor (why the clamp
  exists). Removing the clamp anchors an out-of-content point → P5 fails;
* **P6 finiteness** — no NaN/inf escapes for bounded inputs;
* **P7 degenerate widget** — a non-positive widget size leaves the pan alone
  and still applies the zoom.

Falsification (run before the commit, recorded in the PR): a sign-only factor
fails P1+P2; a widened clamp fails P3; removing the ``uv`` clamp fails P5.
"""

from __future__ import annotations

import itertools
import math

from core.evidence import journal
from core.evidence.journal import record_evidence, verdict
from ui.canvas_infra.viewport.contract import WheelZoomRequest
from ui.canvas_infra.viewport.zoom import compute_zoom_wheel_transform

SPEC_ID = "spec.ui.zoom_wheel_composition"

#: Deliberately coarse grids around the behaviour that matters: the bounds
#: (0.1/50), the notch units Qt reports (120, with high-resolution fractions),
#: the mouse corners (where the uv clamp engages), and the degenerate widget.
ZOOMS = (0.1, 0.5, 1.0, 2.0, 10.0, 49.9, 50.0)
DELTAS = (-1200, -480, -240, -120, -15, -1, 0, 1, 15, 120, 240, 480, 1200)
PANS = ((0.0, 0.0), (0.2, -0.3), (-0.5, 0.5))
MOUSE_FRACTIONS = (0.0, 0.125, 0.5, 0.875, 1.0)
SIZES = ((100, 100), (37, 53), (0, 0), (-10, 40))


def _request(
    *,
    zoom: float,
    delta: int,
    pan: tuple[float, float] = (0.0, 0.0),
    mouse_fraction: tuple[float, float] = (0.5, 0.5),
    size: tuple[int, int] = (100, 100),
) -> WheelZoomRequest:
    width, height = size
    return WheelZoomRequest(
        widget_width=width,
        widget_height=height,
        mouse_x=mouse_fraction[0] * width,
        mouse_y=mouse_fraction[1] * height,
        current_zoom=zoom,
        current_pan_x=pan[0],
        current_pan_y=pan[1],
        angle_delta_y=delta,
    )


def _clamped_zoom(zoom: float, delta: int) -> float:
    return max(0.1, min(zoom * 1.1 ** (delta / 120.0), 50.0))


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _check_composition() -> tuple[list[str], int]:
    """P1: ``k`` notches in one event == ``k`` single-notch events."""
    broken: list[str] = []
    for zoom, delta, k in itertools.product((1.0, 2.0, 10.0), (1, 15, 30, 60, 120, -120, -60), (2, 3, 4)):
        # Keep every intermediate step away from the clamp: the property is about
        # the factor, not the bound.
        if not (0.11 <= _clamped_zoom(zoom, delta * k) <= 49.0):
            continue
        once = compute_zoom_wheel_transform(_request(zoom=zoom, delta=delta * k))
        if once is None:
            broken.append(f"zoom={zoom} delta={delta}x{k}: combined returned None")
            continue
        stepped = zoom
        for _ in range(k):
            step = compute_zoom_wheel_transform(_request(zoom=stepped, delta=delta))
            if step is None:
                broken.append(f"zoom={zoom} delta={delta}x{k}: step returned None")
                break
            stepped = step[0]
        else:
            if not _close(once[0], stepped):
                broken.append(
                    f"zoom={zoom} delta={delta}x{k}: combined={once[0]:.12f} "
                    f"stepped={stepped:.12f}"
                )
    return broken


def _check_monotonicity() -> tuple[list[str], int]:
    """P2: a larger delta never zooms out from the same state."""
    broken: list[str] = []
    for zoom, pan in itertools.product(ZOOMS, PANS):
        previous: tuple[int, float] | None = None
        for delta in sorted(DELTAS):
            result = compute_zoom_wheel_transform(_request(zoom=zoom, delta=delta, pan=pan))
            if result is None:
                continue
            if previous is not None and result[0] < previous[1] - 1e-12:
                broken.append(
                    f"zoom={zoom} pan={pan}: delta={previous[0]} -> {previous[1]:.12f} "
                    f"then delta={delta} -> {result[0]:.12f}"
                )
            previous = (delta, result[0])
    return broken


def _check_clamp() -> tuple[list[str], int]:
    """P3: the result is always inside [0.1, 50] and saturates exactly."""
    broken: list[str] = []
    for zoom, delta in itertools.product(ZOOMS, DELTAS):
        result = compute_zoom_wheel_transform(_request(zoom=zoom, delta=delta))
        if result is None:
            continue
        actual = result[0]
        if not (0.1 - 1e-12 <= actual <= 50.0 + 1e-12):
            broken.append(f"zoom={zoom} delta={delta}: out of bounds {actual!r}")
        expected = _clamped_zoom(zoom, delta)
        if not _close(actual, expected):
            broken.append(
                f"zoom={zoom} delta={delta}: expected clamped {expected:.12f}, got {actual:.12f}"
            )
    return broken


def _check_noop() -> tuple[list[str], int]:
    """P4: no movement means None, and None means no movement."""
    broken: list[str] = []
    for zoom, delta, pan in itertools.product(ZOOMS, DELTAS, PANS):
        result = compute_zoom_wheel_transform(_request(zoom=zoom, delta=delta, pan=pan))
        moves = abs(_clamped_zoom(zoom, delta) - zoom) > 1e-6
        if delta == 0 and result is not None:
            broken.append(f"delta=0 zoom={zoom}: returned a transform")
        if result is None and moves:
            broken.append(f"zoom={zoom} delta={delta}: swallowed a real move")
        if result is not None and not moves:
            broken.append(f"zoom={zoom} delta={delta}: reported a movement that is a no-op")
    return broken


def _check_anchor_or_edge() -> tuple[list[str], int]:
    """P5: the point under the cursor after the transform is clamp(uv_before).

    Inverting the code's pan update, ``uv_after = (m - 0.5) / new_zoom + 0.5 -
    new_pan`` must equal ``clamp(uv_before)`` on each axis. That is anchor
    preservation inside the content and the edge staying at the cursor outside
    it — and it is what fails if the ``uv`` clamp is removed.
    """
    broken: list[str] = []
    for zoom, delta, pan, mouse, size in itertools.product(ZOOMS, DELTAS, PANS, MOUSE_FRACTIONS, SIZES):
        width, height = size
        if width <= 0 or height <= 0:
            continue  # P7 owns the degenerate widget
        result = compute_zoom_wheel_transform(
            _request(zoom=zoom, delta=delta, pan=pan, mouse_fraction=(mouse, mouse), size=size)
        )
        if result is None:
            continue
        new_zoom, new_pan_x, new_pan_y = result
        for axis, (current_pan, new_pan) in (
            ("x", (pan[0], new_pan_x)),
            ("y", (pan[1], new_pan_y)),
        ):
            uv_before = (mouse - 0.5) / zoom + 0.5 - current_pan
            uv_after = (mouse - 0.5) / new_zoom + 0.5 - new_pan
            expected = max(0.0, min(1.0, uv_before))
            if not _close(uv_after, expected):
                broken.append(
                    f"zoom={zoom} delta={delta} pan={pan} mouse={mouse} size={size} "
                    f"axis={axis}: uv {uv_before:.6f} -> {uv_after:.6f}, "
                    f"expected clamp {expected:.6f}"
                )
    return broken


def _check_finiteness() -> tuple[list[str], int]:
    """P6: bounded inputs never produce NaN/inf."""
    broken: list[str] = []
    for zoom, delta, pan, mouse, size in itertools.product(ZOOMS, DELTAS, PANS, MOUSE_FRACTIONS, SIZES):
        result = compute_zoom_wheel_transform(
            _request(zoom=zoom, delta=delta, pan=pan, mouse_fraction=(mouse, mouse), size=size)
        )
        if result is None:
            continue
        if not all(math.isfinite(value) for value in result):
            broken.append(f"zoom={zoom} delta={delta} pan={pan} size={size}: {result!r}")
    return broken


def _check_degenerate_widget() -> tuple[list[str], int]:
    """P7: a non-positive widget leaves the pan and still applies the zoom."""
    broken: list[str] = []
    for zoom, delta, size in itertools.product(ZOOMS, DELTAS, ((0, 0), (0, 80), (-10, 40))):
        request = _request(zoom=zoom, delta=delta, pan=(0.3, -0.4), size=size)
        result = compute_zoom_wheel_transform(request)
        expected = _clamped_zoom(zoom, delta)
        if not (0.1 <= expected <= 50.0):
            continue
        if abs(expected - zoom) <= 1e-6:
            if result is not None:
                broken.append(f"zoom={zoom} delta={delta} size={size}: expected None")
            continue
        if result is None:
            broken.append(f"zoom={zoom} delta={delta} size={size}: expected a transform")
            continue
        new_zoom, new_pan_x, new_pan_y = result
        if not _close(new_zoom, expected):
            broken.append(f"zoom={zoom} delta={delta} size={size}: zoom {new_zoom} != {expected}")
        if not (_close(new_pan_x, 0.3) and _close(new_pan_y, -0.4)):
            broken.append(
                f"zoom={zoom} delta={delta} size={size}: pan moved to "
                f"({new_pan_x}, {new_pan_y})"
            )
    return broken


def test_zoom_wheel_invariants_hold_for_all_bounded_inputs():
    """The pilot's owning probe: every property over the enumerated domain."""
    journal.reset_journal()
    checks = {
        "P1_composition": _check_composition(),
        "P2_monotonicity": _check_monotonicity(),
        "P3_clamp": _check_clamp(),
        "P4_noop": _check_noop(),
        "P5_anchor_or_edge": _check_anchor_or_edge(),
        "P6_finiteness": _check_finiteness(),
        "P7_degenerate_widget": _check_degenerate_widget(),
    }
    cases = (
        len(ZOOMS) * len(DELTAS) * len(PANS) * len(MOUSE_FRACTIONS) * len(SIZES)
        + len(ZOOMS) * len(DELTAS)
        + 3 * 7 * 3
    )
    broken = {name: rows for name, rows in checks.items() if rows}
    record_evidence(
        SPEC_ID,
        kind="spec",
        verdict="ok" if not broken else "violated",
        signal=(
            f"cases={cases} properties={len(checks)} "
            f"violations=" + (",".join(f"{k}:{len(v)}" for k, v in sorted(broken.items())) or "none")
        ),
        reason=(
            "composition, monotonicity, clamp, no-op, anchor-or-edge, finiteness and "
            "degenerate-widget properties hold over the enumerated domain"
            if not broken
            else "at least one invariant has a counterexample in the enumerated domain"
        ),
        ids=tuple(f"{name}#{i}" for name, rows in sorted(broken.items()) for i in range(min(len(rows), 3))),
        area="zoom.wheel",
    )
    record = verdict(None, SPEC_ID)
    assert record is not None, "the invariant probe emitted no evidence"

    assert not broken, "\n".join(
        f"{name}: {len(rows)} counterexample(s); first: {rows[0]}"
        for name, rows in broken.items()
    )
    assert record.verdict == "ok", record.signal
