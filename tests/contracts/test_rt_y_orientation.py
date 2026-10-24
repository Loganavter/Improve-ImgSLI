"""One source of truth for Y-orientation corrections (anti-recurrence gate).

Why this exists (plan-tile-policy-reliability-2026-10-24, P0 verdict): the mip
cascade hardcoded a Y flip for a *sampled* offscreen target -- right on
OpenGL/Vulkan, wrong on D3D11, and it cost a full diagnosis cycle. The first
correction then gated on ``rhi.isYUpInFramebuffer()``, which Vulkan answers
like D3D11 while needing the flip, and flipped every tile on Vulkan within the
hour. Two backends answering the same query still need opposite corrections,
so a convention may never be decided locally again: it lives in
``engine/gpu/rt_y_orientation.py`` behind three render-target cases
(COMPOSITED / SAMPLED_RT / NONE) plus the two legacy one-bit cases the
allowlist migration closed (WIDGET_TEXTURE / COMPOSITED_SCISSOR), and this
contract keeps it the only place that decides.

The gate is mechanical (AST, no runtime):

1. no module outside the helper may CALL ``isYUpInFramebuffer`` /
   ``clipSpaceCorrMatrix`` / ``isYUpInNDC``;
2. no module outside the helper may build a 16-float Y-flip matrix literal;
3. every allowlisted legacy site must still exist, still contain the flagged
   call, and still carry a reason -- so the ratchet can shrink but cannot rot.

Allowlisted sites were the ones that predate the helper and needed a visual
validation pass per backend before they could be migrated (tracked by
``task-render-rt-y-convention-audit-2026-10-24``). That ratchet is now CLOSED:
both legacy sites (``glass_panel``'s widget-texture copy and
``rhi_feature_common``'s composited scissor) are named cases of the helper
(``widget_texture_needs_y_flip`` / ``composited_scissor_needs_y_flip``), so
the allowlist is empty and stays empty. New code has no reason to decide a
convention locally.
"""

from __future__ import annotations

import ast
from pathlib import Path

from engine.gpu import rt_y_orientation

from ._framework import SRC, iter_py, parse, rel

HELPER = "src/engine/gpu/rt_y_orientation.py"

#: Legacy sites that still decide a convention locally. The ratchet is closed
#: (both migrated into the helper); it must stay empty, and growing it needs a
#: reason that names the backend validation.
ALLOWED_LOCAL_DECISIONS: dict[str, str] = {}

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


_DIAGONAL_ONES = (0, 10, 15)
_OFF_DIAGONAL_ZEROS = (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14)


def _numeric(node: ast.AST) -> float | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _numeric(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    return None


def _is_y_flip_literal(node: ast.AST) -> bool:
    """A strict 16-element Y-flip diagonal: diag(1, -1, 1, 1), rest zero.

    Strict on purpose: a vertex array or a UI transform that merely has -1.0
    at index 5 must not trip the gate (the first draft did, on
    ``canvas/state.py``'s quad vertices).
    """
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 16:
        return False
    values = [_numeric(element) for element in node.elts]
    if any(value is None for value in values):
        return False
    if values[5] != -1.0:
        return False
    if any(values[index] != 0.0 for index in _OFF_DIAGONAL_ZEROS):
        return False
    return all(values[index] == 1.0 for index in _DIAGONAL_ONES)


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
    path = SRC.parent / HELPER
    tree = parse(path)
    assert tree is not None, f"cannot parse {HELPER}"
    literals = [node for node in ast.walk(tree) if _is_y_flip_literal(node)]
    assert literals, (
        f"{HELPER} no longer carries the Y-flip literal: if the table moved, "
        "move this contract with it"
    )


def test_helper_cases_are_named_and_documented():
    """The cases are the contract: a new one must be added deliberately."""
    text = (SRC.parent / HELPER).read_text(encoding="utf-8")
    for case in (
        "COMPOSITED",
        "SAMPLED_RT",
        "NONE",
        "WIDGET_TEXTURE",
        "COMPOSITED_SCISSOR",
    ):
        assert case in text, (
            f"{HELPER} lost its {case} case doc -- the cases are how a "
            "pass picks its correction; do not replace them with a backend "
            "special-case"
        )
    for symbol in (
        "def sampled_rt_correction(",
        "def composited_clip_correction(",
        "def sampled_rt_needs_y_flip(",
        "def widget_texture_needs_y_flip(",
        "def composited_scissor_needs_y_flip(",
    ):
        assert symbol in text, f"{HELPER} must keep {symbol}"


# ---------------------------------------------------------------------------
# Migration proof for the two closed allowlist sites.
#
# Both predicates used to live at their call sites (``glass_panel``'s copy
# description and ``rhi_feature_common``'s scissor). These tests state those
# old expressions as an ORACLE and require the named helper cases to agree for
# every reachable input, so a truth table change cannot hide as a refactor.
# ---------------------------------------------------------------------------


class _FakeRhi:
    """Minimal QRhi stub answering both documented convention queries."""

    def __init__(self, y_up_framebuffer: bool, y_up_ndc: bool) -> None:
        self._y_up_framebuffer = y_up_framebuffer
        self._y_up_ndc = y_up_ndc

    def isYUpInFramebuffer(self) -> bool:
        return self._y_up_framebuffer

    def isYUpInNDC(self) -> bool:
        return self._y_up_ndc


class _RaisingQueryRhi:
    """Stub whose origin query raises, as a not-yet-implemented backend would."""

    def isYUpInFramebuffer(self) -> bool:
        raise RuntimeError("query unavailable")

    def isYUpInNDC(self) -> bool:
        return True


class _MissingQueryRhi:
    """Stub written before the query existed: the attribute is simply absent."""

    def isYUpInNDC(self) -> bool:
        return True


#: (isYUpInFramebuffer, isYUpInNDC) for every backend shape the rule can meet.
#: The last row is not a shipped backend; it keeps the table exhaustive so a
#: predicate that silently starts reading NDC fails here.
_QUERY_SHAPES = (
    (True, True),  # OpenGL / GLES2
    (False, False),  # Vulkan (answers the origin query like D3D11)
    (False, True),  # D3D11 / Metal / D3D12
    (True, False),
)


def _legacy_widget_texture_flip(rhi) -> bool:
    """ORACLE: the expression this migration deleted from ``glass_panel``."""
    flip_y = False
    if hasattr(rhi, "isYUpInFramebuffer"):
        try:
            flip_y = bool(rhi.isYUpInFramebuffer())
        except RuntimeError:
            flip_y = False
    return flip_y


def _legacy_composited_scissor_flip(rhi, never_shown: bool) -> bool:
    """ORACLE: the expression this migration deleted from ``rhi_feature_common``."""
    y_up = rhi.isYUpInFramebuffer()
    return bool(y_up or never_shown)


def test_widget_texture_truth_table_matches_the_old_glass_panel_expression():
    """``isYUpInFramebuffer()`` only -- NDC must not participate.

    Vulkan is the discriminating row: it reports ``False`` for the framebuffer
    origin exactly like D3D11 and stores ``colorTexture()`` top-down, so the
    copy must NOT flip there (this is where ``sampled_rt_needs_y_flip`` would
    wrongly flip).
    """
    expected_by_shape = {
        (True, True): True,
        (False, False): False,
        (False, True): False,
        (True, False): True,
    }
    for y_up_framebuffer, y_up_ndc in _QUERY_SHAPES:
        rhi = _FakeRhi(y_up_framebuffer, y_up_ndc)
        actual = rt_y_orientation.widget_texture_needs_y_flip(rhi)
        assert actual == expected_by_shape[(y_up_framebuffer, y_up_ndc)]
        assert actual == _legacy_widget_texture_flip(rhi), (
            "WIDGET_TEXTURE migrated with a different truth table: "
            f"y_up_fb={y_up_framebuffer} y_up_ndc={y_up_ndc}"
        )


def test_widget_texture_ignores_ndc_within_the_same_origin():
    """Two backends differing only in NDC get the same copy decision."""
    for y_up_framebuffer in (True, False):
        up = rt_y_orientation.widget_texture_needs_y_flip(
            _FakeRhi(y_up_framebuffer, True)
        )
        down = rt_y_orientation.widget_texture_needs_y_flip(
            _FakeRhi(y_up_framebuffer, False)
        )
        assert up == down == y_up_framebuffer


def test_widget_texture_unqueryable_keeps_the_shipped_no_flip():
    """No query -> False (the behaviour glass_panel shipped with)."""
    for rhi in (_RaisingQueryRhi(), _MissingQueryRhi()):
        assert rt_y_orientation.widget_texture_needs_y_flip(rhi) is False
        assert _legacy_widget_texture_flip(rhi) is False


def test_composited_scissor_truth_table_matches_the_old_local_expression():
    """``isYUpInFramebuffer() or never_shown``, for both widget shapes."""
    for y_up_framebuffer, y_up_ndc in _QUERY_SHAPES:
        for never_shown in (False, True):
            rhi = _FakeRhi(y_up_framebuffer, y_up_ndc)
            actual = rt_y_orientation.composited_scissor_needs_y_flip(
                rhi, never_shown=never_shown
            )
            assert actual == (y_up_framebuffer or never_shown), (
                "COMPOSITED_SCISSOR must be the framebuffer origin OR the "
                f"never-shown bit: y_up_fb={y_up_framebuffer} "
                f"never_shown={never_shown}"
            )
            assert actual == _legacy_composited_scissor_flip(rhi, never_shown), (
                "COMPOSITED_SCISSOR migrated with a different truth table: "
                f"y_up_fb={y_up_framebuffer} never_shown={never_shown}"
            )


def test_composited_scissor_ignores_ndc_within_the_same_origin():
    """NDC is irrelevant to a scissor: only origin + never-shown matter."""
    for y_up_framebuffer in (True, False):
        for never_shown in (False, True):
            up = rt_y_orientation.composited_scissor_needs_y_flip(
                _FakeRhi(y_up_framebuffer, True), never_shown=never_shown
            )
            down = rt_y_orientation.composited_scissor_needs_y_flip(
                _FakeRhi(y_up_framebuffer, False), never_shown=never_shown
            )
            assert up == down == (y_up_framebuffer or never_shown)


def test_composited_scissor_unqueryable_falls_back_to_never_shown():
    """No query -> ``never_shown``: a raw grab keeps its raw scissor flip."""
    for rhi in (_RaisingQueryRhi(), _MissingQueryRhi()):
        assert (
            rt_y_orientation.composited_scissor_needs_y_flip(rhi, never_shown=True)
            is True
        )
        assert (
            rt_y_orientation.composited_scissor_needs_y_flip(rhi, never_shown=False)
            is False
        )


def test_new_case_signatures_are_stable():
    """The interface other modules import: one positional rhi, keyword-only bit."""
    import inspect

    widget_params = list(
        inspect.signature(rt_y_orientation.widget_texture_needs_y_flip).parameters.values()
    )
    assert [param.name for param in widget_params] == ["rhi"]

    scissor_params = list(
        inspect.signature(
            rt_y_orientation.composited_scissor_needs_y_flip
        ).parameters.values()
    )
    assert [param.name for param in scissor_params] == ["rhi", "never_shown"]
    assert scissor_params[1].kind is inspect.Parameter.KEYWORD_ONLY
