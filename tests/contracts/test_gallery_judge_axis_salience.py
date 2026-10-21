"""GA5 contract: an axis inside the noise floor carries no rank weight.

``plan-gallery-ai-judgement-2026-10-21`` §Gates GA5 / §Invariants M3
("discriminating": an axis whose spread across the series is inside the
instrument's noise contributes nothing and must not be displayed as if it
ranked anything) and verified defect **J4**: the camera profile offers
``white_balance`` / ``aesthetic`` / ``brisque``, the model emitted a constant
``exposure = 82`` for 5 of 6 cards and ``sharpness ∈ {68,74,78}``, yet
``rank_fusion.measured_axes_for`` (``rank_fusion.py:77``) feeds every measured
axis into the fusion mean and every axis row renders as a bare number.

The gate is written against the DECLARED P2 helper (plan §Interface):

    axis_salience(vectors, *, noise_floor) -> dict[str, str]
        axis -> "discriminating" | "inside-noise"

``vectors`` is one ``{axis: score}`` mapping per member of the series (the JEV
vector's ``items[*].scores`` unwrapped — the shape both the fusion and the Jev
path already hold).

It fails for two independent reasons until P2 lands, and both are asserted, so
"the helper exists but nothing applies it" stays red:

* the helper is absent from ``services/rank_fusion`` (import/attribute check);
* no rank or vector path consults salience — every measured axis therefore
  contributes weight regardless of its spread (AST scan of the rank/vector
  modules for a reference outside the helper's own definition).

Red-before: no ``axis_salience`` anywhere under ``src/tabs/image_gallery``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ._framework import SRC, parse

from tabs.image_gallery.services import rank_fusion

GATE = "GA5"
PLAN = "plan-gallery-ai-judgement-2026-10-21"

GALLERY = SRC / "tabs" / "image_gallery"
RANK_FUSION_PATH = GALLERY / "services" / "rank_fusion.py"
#: Modules that may consume the salience verdict: the deterministic fusion and
#: the Jev vector path (``build_measured_vector`` / rank dispatch).
CONSUMER_PATHS = (
    RANK_FUSION_PATH,
    GALLERY / "services" / "jev_client.py",
)

_ALLOWLIST = Path(__file__).with_name("gallery_judge_allowlist.txt")

#: Declared vocabulary (plan §Interface) — values are part of the contract.
DISCRIMINATING = "discriminating"
INSIDE_NOISE = "inside-noise"
VERDICTS = (DISCRIMINATING, INSIDE_NOISE)


def _allowlisted(gate: str) -> bool:
    """True while *gate* still has a line in the shrink-only ledger."""
    for raw in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
        gate_id = raw.split("#", 1)[0].split("|", 1)[0].strip()
        if gate_id == gate:
            return True
    return False


def _axis_salience():
    """The declared P2 helper, or ``None`` while it does not exist."""
    helper = getattr(rank_fusion, "axis_salience", None)
    return helper if callable(helper) else None


def _series_semantics_problems(helper) -> list[str]:  # type: ignore[no-untyped-def]
    """The helper must separate a wide axis from a within-noise one."""
    vectors = (
        {"ssim": 90, "noise": 70},
        {"ssim": 40, "noise": 71},
        {"ssim": 65, "noise": 70},
    )
    try:
        verdicts = helper(vectors, noise_floor=5.0)
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        return [f"axis_salience(vectors, noise_floor=5.0) raised {error!r}"]
    if not isinstance(verdicts, dict):
        return [f"axis_salience returned {type(verdicts).__name__}, not dict[str, str]"]
    problems: list[str] = []
    # ssim spans 40..90 across the series: it separates them.
    if verdicts.get("ssim") != DISCRIMINATING:
        problems.append(
            f"ssim (spread 50 > floor 5) classified {verdicts.get('ssim')!r}, "
            f"expected {DISCRIMINATING!r}"
        )
    # noise spans 70..71: inside the instrument's noise.
    if verdicts.get("noise") != INSIDE_NOISE:
        problems.append(
            f"noise (spread 1 <= floor 5) classified {verdicts.get('noise')!r}, "
            f"expected {INSIDE_NOISE!r}"
        )
    unknown = sorted(set(verdicts.values()) - set(VERDICTS))
    if unknown:
        problems.append(
            f"axis_salience emitted verdict(s) outside the declared vocabulary "
            f"{VERDICTS}: {unknown}"
        )
    return problems


def _consumer_path_problems() -> list[str]:
    """Some rank/vector path must consult salience, not just define it."""
    consumers: list[str] = []
    for path in CONSUMER_PATHS:
        tree = parse(path)
        if tree is None:
            continue
        definition: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "axis_salience":
                # The helper's own body is not a consumer of itself.
                definition.update(id(child) for child in ast.walk(node))
        for node in ast.walk(tree):
            if id(node) in definition:
                continue
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            if name == "axis_salience":
                consumers.append(f"{path.relative_to(GALLERY).as_posix()}:{node.lineno}")
    if consumers:
        return []
    return [
        "no rank/vector path consults axis_salience "
        f"({', '.join(p.relative_to(GALLERY).as_posix() for p in CONSUMER_PATHS)}): "
        "an axis whose spread is inside the noise floor still contributes "
        "weight to the applied order (plan P2)"
    ]


@pytest.mark.xfail(
    condition=_allowlisted(GATE),
    reason="P2 not landed yet",
    strict=True,
    raises=AssertionError,
)
def test_an_axis_inside_the_noise_floor_carries_no_rank_weight() -> None:
    helper = _axis_salience()
    problems: list[str] = []
    if helper is None:
        problems.append(
            "services/rank_fusion has no axis_salience(vectors, *, noise_floor) "
            "-> dict[str, str] — the declared P2 interface"
        )
    else:
        problems += _series_semantics_problems(helper)
    problems += _consumer_path_problems()
    assert not problems, (
        "GA5 (M3 discriminating): an axis whose spread across the series is "
        "inside the noise floor must carry no rank weight and must be rendered "
        "with that reason, not as a bare score:\n"
        + "\n".join(f"- {problem}" for problem in problems)
    )


def test_the_declared_axis_resolver_stays_the_single_one() -> None:
    """P2 adds salience ON TOP of the one resolver, never as a second list.

    ``measured_axes_for(mode=None, *, profile=None)`` is the declared only
    axis-set resolver (plan §Interface); the salience verdict may drop axes from
    the weights, but a private axis list beside it would re-open the drift this
    plan closes.
    """
    resolver = getattr(rank_fusion, "measured_axes_for", None)
    assert callable(resolver), "rank_fusion.measured_axes_for is the declared resolver"
    axes = resolver("fidelity")
    assert isinstance(axes, tuple) and all(isinstance(axis, str) for axis in axes)
    assert callable(getattr(rank_fusion, "rank_series", None)), (
        "rank_fusion.rank_series is the deterministic order (plan §Interface)"
    )
