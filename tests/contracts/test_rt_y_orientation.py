"""One source of truth for Y-orientation corrections (anti-recurrence gate).

Why this exists (plan-tile-policy-reliability-2026-10-24, P0 verdict): the mip
cascade hardcoded a Y flip for a *sampled* offscreen target -- right on
OpenGL/Vulkan, wrong on D3D11, and it cost a full diagnosis cycle. The first
correction then gated on ``rhi.isYUpInFramebuffer()``, which Vulkan answers
like D3D11 while needing the flip, and flipped every tile on Vulkan within the
hour. Two backends answering the same query still need opposite corrections,
so a convention may never be decided locally again: it lives in
``engine/gpu/rt_y_orientation.py`` behind three named cases (COMPOSITED /
SAMPLED_RT / NONE), and this contract keeps it the only place that decides.

The gate is mechanical (AST, no runtime):

1. no module outside the helper may CALL ``isYUpInFramebuffer`` /
   ``clipSpaceCorrMatrix`` / ``isYUpInNDC``;
2. no module outside the helper may build a 16-float Y-flip matrix literal;
3. every allowlisted legacy site must still exist, still contain the flagged
   call, and still carry a reason -- so the ratchet can shrink but cannot rot.

Allowlisted sites are the ones that predate the helper and need a visual
validation pass per backend before they can be migrated (each is tracked by
``task-render-rt-y-convention-audit-2026-10-24``). New code has no reason to
be on this list.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._framework import SRC, iter_py, parse, rel

HELPER = "src/engine/gpu/rt_y_orientation.py"

#: Legacy sites that still decide a convention locally. Shrinking this dict is
#: the goal; growing it needs a reason that names the backend validation.
ALLOWED_LOCAL_DECISIONS: dict[str, str] = {
    "src/engine/gpu/glass_panel.py": (
        "reads a widget's backing texture (not a pass this module can route); "
        "needs per-backend visual validation before migration"
    ),
    "src/tabs/image_compare/canvas/rhi_feature_common.py": (
        "predates the helper; its comment claims isYUpInFramebuffer() alone is "
        "correct there -- exactly the assumption this gate exists to retire"
    ),
}

BANNED_CALLS = frozenset({"isYUpInFramebuffer", "clipSpaceCorrMatrix", "isYUpInNDC"})


def _called_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                names.add(func.attr)
            elif isinstance(func, ast.Name):
                names.add(func.id)
    return names


def _is_y_flip_literal(node: ast.AST) -> bool:
    """A 16-element numeric literal whose element 5 is ``-1.0`` (a Y flip)."""
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 16:
        return False
    element = node.elts[5]
    if not (isinstance(element, ast.UnaryOp) and isinstance(element.op, ast.USub)):
        return False
    operand = element.operand
    return isinstance(operand, ast.Constant) and operand.value == 1.0


def test_no_module_decides_the_y_convention_locally():
    offenders: list[str] = []
    for path in iter_py(SRC):
        relative = rel(path)
        if relative == HELPER:
            continue
        tree = parse(path)
        if tree is None:
            continue
        used = _called_names(tree) & BANNED_CALLS
        literal = any(
            _is_y_flip_literal(node) for node in ast.walk(tree)
        )
        if not used and not literal:
            continue
        if relative in ALLOWED_LOCAL_DECISIONS:
            continue
        offenders.append(f"{relative}: calls={sorted(used)} flip_literal={literal}")

    assert not offenders, (
        "Y-orientation decided outside engine/gpu/rt_y_orientation.py:\n  "
        + "\n  ".join(offenders)
        + "\n\nRoute the pass through the helper (COMPOSITED -> "
        "composited_clip_correction, SAMPLED_RT -> sampled_rt_correction). "
        "Both the mip-cascade D3D11 bug and the Vulkan regression came from a "
        "local decision; see plan-tile-policy-reliability-2026-10-24."
    )


def test_allowlist_entries_still_exist_and_are_still_guilty():
    """A stale allowlist entry hides the gate; fail instead of rotting."""
    for relative, reason in ALLOWED_LOCAL_DECISIONS.items():
        assert reason.strip(), f"{relative}: allowlist entry needs a reason"
        path = SRC.parent / relative
        assert path.exists(), (
            f"allowlist names {relative}, which no longer exists -- drop the "
            "entry so the gate covers the whole tree"
        )
        tree = parse(path)
        assert tree is not None, f"{relative} does not parse"
        still_guilty = bool(_called_names(tree) & BANNED_CALLS) or any(
            _is_y_flip_literal(node) for node in ast.walk(tree)
        )
        assert still_guilty, (
            f"{relative} no longer decides Y locally -- remove it from "
            "ALLOWED_LOCAL_DECISIONS (the ratchet must shrink)"
        )


def test_helper_is_the_only_flip_literal_site():
    """The helper owns the matrices; nothing else may carry the literal."""
    path = SRC / HELPER
    tree = parse(path)
    assert tree is not None, f"cannot parse {HELPER}"
    literals = [node for node in ast.walk(tree) if _is_y_flip_literal(node)]
    assert literals, (
        f"{HELPER} no longer carries the Y-flip literal: if the table moved, "
        "move this contract with it"
    )


def test_helper_cases_are_named_and_documented():
    """The three cases are the contract: a new one must be added deliberately."""
    text = (SRC / HELPER).read_text(encoding="utf-8")
    for case in ("COMPOSITED", "SAMPLED_RT", "NONE"):
        assert case in text, (
            f"{HELPER} lost its {case} case doc -- the three cases are how a "
            "pass picks its correction; do not replace them with a backend "
            "special-case"
        )
    for symbol in (
        "def sampled_rt_correction(",
        "def composited_clip_correction(",
        "def sampled_rt_needs_y_flip(",
    ):
        assert symbol in text, f"{HELPER} must keep {symbol}"
