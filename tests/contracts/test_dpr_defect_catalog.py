"""Machine gate against every known way to break DPR / Y orientation.

Why a catalog and not another fix (plan: `dpr-contract-app-2026-10-28`): the
three defects merged in #751 (drop overlay mirrored + shrunken on HiDPI), #752
(Quick Look preview mirrored on Vulkan) and #755 (live capture doubled the DPR
and cropped logical rects out of device pixmaps) were the *same few mistakes*
made in three unrelated files. Fixing each one leaves the fourth file free to
repeat it, so this module enumerates the failure modes we have actually shipped
as ``rule_id`` detectors, and pins each detector with a snippet of the real
broken code (``fixtures/dpr_bad_snippets/``).

The measured fact every rule rests on
-------------------------------------
``QPainter`` scales its commands by the ``devicePixelRatio`` of the device it
paints on: for a ``QPixmap``/``QImage`` carrying DPR *d*, ``combinedTransform``
already contains ``scale(d)`` while ``worldTransform`` is identity, and painting
coordinates are **logical**. Two consequences, which is why the rules look
redundant until you see them fail:

* a raster must be ALLOCATED in device px (``round(logical * d)``) and TAGGED
  with ``setDevicePixelRatio(d)`` — allocating logical px and tagging with *d*
  makes the painter treat the canvas as ``size / d``, so the drawing lands in
  the top-left corner (the "smaller at a larger interface scale" report);
* a manual ``painter.scale(d, d)`` on a raster that is already tagged is a
  SECOND application of the same ratio (the capture defect: device
  ``(200,100)-(600,300)`` painted at ``(400,200)-(1198,598)``).

``QPixmap.width()/height()`` are device px while widget geometry is logical, so
"a number is a number" is exactly the reasoning that produced all three
defects. Every rule id therefore names the *unit*, not the widget.

Rules (id -> what it catches)
-----------------------------
``clip-matrix-literal``
    ``stage_clip`` / ``stage_packed(clip_matrix=...)`` / any ``clip_matrix=``
    keyword fed by a 16-float literal, ``None`` or an ``IDENTITY*`` name instead
    of the one convention source (``ctx.clip_matrix``,
    ``engine/gpu/rt_y_orientation``'s ``composited_clip_correction`` /
    ``composited_clip_matrix``, ``framing.clip_matrix(...)``). This is the #752
    defect. The companion gate ``test_rt_y_orientation.py`` forbids *calling*
    the QRhi convention queries outside the helper; it cannot see an identity
    matrix standing in for the correction, which is what actually shipped.
``viewport-logical``
    a ``QRhiViewport``/``QRhiScissor`` (or the ``setViewport``/``setScissor``
    that carries one) whose size is not derived from the framebuffer
    (``pixelSize()``, ``framebuffer_size``, ``*_fb``, ``*_framebuffer``,
    ``*_device``, ``renderTarget()``). Mini-taint inside the function: names
    assigned from a device expression and parameters named ``fb_*``/``*_device``
    are sanctioned; everything else is a flag.
``double-scale``
    a function that constructs ``QPainter(<pixmap|image>)`` *and* multiplies
    geometry by a ratio name (``dpr``, ``*_dpr``, ``devicePixelRatioF()``,
    ``pixel_ratio``). Coordinates are logical; the ratio belongs to the buffer
    size, in another function.
``raster-logical-tagged``
    ``QPixmap(<expr>)`` / ``QImage(<expr>)`` in a function that then calls
    ``setDevicePixelRatio(``, where the size is not device-derived — the
    canvas-half symptom. A raster taken from ``grab()`` /
    ``grabFramebuffer()`` is exempt (it is device-sized by definition).
``ratio-dropped-on-copy``
    a new raster built from another raster's ``.size()`` without copying the
    ratio in the same function (the icon-copy defect: a DPR=2 source becomes a
    DPR=1 copy that is drawn at half size).
``ratio-rounded``
    ``int(<ratio>)`` / ``round(<ratio>)`` / ``setDevicePixelRatio(<int
    literal>)``. A fractional DPR (125%/150%) must survive as a float; rounding
    it to 1 shadows a whole class of "slightly blurry / slightly cropped".
``ratio-hardcoded``
    ``setDevicePixelRatio(2)`` and friends, and (in tests) a comparison
    against a numeric ratio literal instead of the value under test.
``uv-flip-compensation``
    a Y flip written into geometry or a shader outside the two named
    ``engine/gpu/rt_y_orientation`` cases: ``.mirrored(``, a hardcoded
    ``flip_y = True``, ``1.0 - <x>.y`` in Python, and the same in ``*.frag`` /
    ``*.vert``. A flip must be asked for (``widget_texture_needs_y_flip``,
    ``sampled_rt_correction``), never added.
``primary-screen-grab``
    a function that both calls ``.grabWindow(`` and ``primaryScreen()``: a grab
    must ask the *target's* screen (the 2026-10-27 two-monitor false "fully
    visible" verdict). ``primaryScreen()`` alone is legal — choosing a new
    window's geometry is not a grab.
``geometry-device-copy`` (behavioural)
    a logical rect sliced out of a device-pixel grab: ``capture._clip_to_visible``
    on a DPR=2 ``QPixmap`` must keep the whole visible rect, not the top-left
    ``1/DPR²``.
``silent-downsample`` (static + behavioural)
    a ``grabFramebuffer()``/``grabWindow()`` result resized to a size that is
    not device-named in the same function: a HiDPI grab quietly loses
    resolution. Behaviour is pinned on ``engine/gpu/export_tiling``.

Global suggest
--------------
Run the whole gate: ``python3 -m pytest tests/contracts/test_dpr_defect_catalog.py
-q -o addopts=""``. A new hit has exactly three dispositions: fix it; an entry in
``dpr_catalog_allowlist.py`` with the measured reason (legitimate shape); or an
entry in ``KNOWN_DEFECTS`` below with a task id (real bug, someone else's fix,
self-expiring). Then the mode table in
``docs/dev/rendering/dpr-failure-modes.md`` gains or updates its row.

The fixtures under ``fixtures/dpr_bad_snippets/`` are the gate's own proof: half
of them are the real broken code from the fix commits' parents, the rest are
legal shapes the detectors must stay silent on. A detector with no red fixture
describes nothing that happened; a detector with no green fixture is a substring
alarm.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from tests.contracts._framework import ROOT, SRC, iter_py, parse, rel
from tests.contracts.dpr_catalog_allowlist import DPR_ALLOWLIST

# ---------------------------------------------------------------------------
# Rule ids. Adding one means: a row in docs/dev/rendering/dpr-failure-modes.md,
# a fixture that only that rule catches, and a detector below.
# ---------------------------------------------------------------------------

RULE_CLIP_MATRIX_LITERAL = "clip-matrix-literal"
RULE_VIEWPORT_LOGICAL = "viewport-logical"
RULE_DOUBLE_SCALE = "double-scale"
RULE_RASTER_LOGICAL_TAGGED = "raster-logical-tagged"
RULE_RATIO_DROPPED_ON_COPY = "ratio-dropped-on-copy"
RULE_RATIO_ROUNDED = "ratio-rounded"
RULE_RATIO_HARDCODED = "ratio-hardcoded"
RULE_UV_FLIP_COMPENSATION = "uv-flip-compensation"
RULE_PRIMARY_SCREEN_GRAB = "primary-screen-grab"
RULE_GEOMETRY_DEVICE_COPY = "geometry-device-copy"
RULE_SILENT_DOWNSAMPLE = "silent-downsample"

RULE_IDS = (
    RULE_CLIP_MATRIX_LITERAL,
    RULE_VIEWPORT_LOGICAL,
    RULE_DOUBLE_SCALE,
    RULE_RASTER_LOGICAL_TAGGED,
    RULE_RATIO_DROPPED_ON_COPY,
    RULE_RATIO_ROUNDED,
    RULE_RATIO_HARDCODED,
    RULE_UV_FLIP_COMPENSATION,
    RULE_PRIMARY_SCREEN_GRAB,
    RULE_GEOMETRY_DEVICE_COPY,
    RULE_SILENT_DOWNSAMPLE,
)

#: Fixtures that document a LEGAL shape carry this id instead of a rule: the
#: gate must stay silent on them (precision half of the self-test).
NONE_RULE = "none"

#: Rules that are decided by running code, not by reading it. They have no
#: static hits and therefore no allowlist entries.
BEHAVIOURAL_RULES = frozenset({RULE_GEOMETRY_DEVICE_COPY})

#: Rules a source snippet can be judged against without a window.
STATIC_RULES = tuple(rule for rule in RULE_IDS if rule not in BEHAVIOURAL_RULES)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "dpr_bad_snippets"

#: The one module allowed to decide the Y convention (mirrors
#: ``test_rt_y_orientation.HELPER``). A uv flip is legal only as a call into it.
Y_CONVENTION_HELPER = "src/engine/gpu/rt_y_orientation.py"

#: Real defects this gate finds on the tree TODAY. They are declared, not
#: allowlisted: an allowlist entry means "this shape is legitimate here", and
#: these are not — they are known bugs with an owner. Filing them here keeps the
#: gate honest ("0 unallowlisted hits" would otherwise be "0 hits, because we
#: hid them") and keeps them visible in every run.
#:
#: `task-mc-tiled-export-dpr-2026-10-28` (parallel writer, same base): the tiled
#: export composes in LOGICAL output px against a DEVICE-px framebuffer, so at
#: DPR=2 the PNG holds the composition in the top-left quarter and the device
#: grab is silently downsampled to the logical tile.
#:
#: Shrink-only, like the allowlist: an entry that no longer matches a live hit
#: fails the suite, so the fix cannot land without deleting its declaration.
KNOWN_DEFECTS: frozenset[tuple[str, int, str]] = frozenset(
    {
        # Empty as of 2026-10-28: the four entries that lived here were the MC
        # tiled-export group, fixed by app #756 (one device px per output px,
        # no silent grab resample). They expired exactly as this ratchet
        # intends — the fix removed the shapes instead of hiding them. The
        # remaining legacy-downscale hit (image_compare's supersampled surface
        # through plugins/export/services/gpu_export_proxy.py) is a deliberate
        # policy, so it moved to the allowlist with its measurement.
    }
)


@dataclass(frozen=True)
class Hit:
    """One rule violation: what, where, and a human-readable detail."""

    rule: str
    rel: str
    function: str
    line: int
    detail: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.rel, self.function, self.rule)

    def __str__(self) -> str:  # pragma: no cover - assertion message only
        return f"{self.rel}:{self.line} {self.function}() [{self.rule}] {self.detail}"


# ---------------------------------------------------------------------------
# Vocabulary shared by the detectors
# ---------------------------------------------------------------------------

#: Expressions/attributes that mean "this is a DEVICE pixel value".
DEVICE_MARKERS = (
    "pixelSize",
    "framebuffer",
    "renderTarget",
    "devicePixelRatio",
)

#: Names that mean device px by convention: ``fb_w``, ``width_fb``,
#: ``device_size``, ``px_width`` (the scissor builder's own params),
#: ``viewport_size`` (the array-draw seam's documented "pixels").
DEVICE_NAME_RE = re.compile(
    r"^(?:fb_\w+|_\w*_?fb|.*_fb|framebuffer\w*|.*_framebuffer|device\w*|.*_device"
    r"|px_\w+|.*_pixel_size|viewport_size|.*_device_size)$"
)

#: Names that mean "device pixels per logical pixel". Deliberately NOT a bare
#: ``ratio``/``*_ratio``: this codebase uses those for aspect and progress
#: ratios (``original_ratio``, ``value/maximum``), and matching them turned the
#: first draft of every rule into a substring alarm.
RATIO_NAME_RE = re.compile(
    r"^(?:dpr|pixel_ratio|device_pixel_ratio|devicePixelRatioF?"
    r"|scale_factor|.*_dpr)$"
)

#: How a sanctioned clip matrix arrives. A call/property whose name ends with
#: one of these is the repaired form of the ``clip-matrix-literal`` defect.
CLIP_MATRIX_SUFFIXES = ("clip_matrix", "clip_correction")

PAINTER_TARGET_NAMES = frozenset({"QPixmap", "QImage"})
VIEWPORT_CTORS = frozenset({"QRhiViewport", "QRhiScissor"})
GRAB_METHODS = frozenset({"grabFramebuffer", "grabWindow"})
SCREEN_PRIMARY_METHODS = frozenset({"primaryScreen"})


# ---------------------------------------------------------------------------
# AST helpers (small, explicit, shared)
# ---------------------------------------------------------------------------


def _walk_own(node: ast.AST):
    """Walk ``node`` without descending into nested functions/classes.

    Detector hits are attributed to the *enclosing* function, so a nested
    ``def`` (a stub, a callback) must be judged on its own; otherwise its hits
    inherit the outer function's allowlist key.
    """
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        for child in ast.iter_child_nodes(current):
            if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
            ):
                continue
            stack.append(child)


def _functions(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    """Every function/method defined in ``tree``, named (nested ones included)."""
    found: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((node.name, node))
    return found


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _calls(node: ast.AST) -> list[ast.Call]:
    return [child for child in _walk_own(node) if isinstance(child, ast.Call)]


def _identifiers(expr: ast.AST) -> set[str]:
    """Names and attribute names inside ``expr`` (``ctx.framebuffer_size`` -> both)."""
    idents: set[str] = set()
    for node in ast.walk(expr):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
    return idents


def _is_ratio_name(name: str) -> bool:
    return bool(RATIO_NAME_RE.match(name))


def _has_ratio(expr: ast.AST | None) -> bool:
    if expr is None:
        return False
    return any(_is_ratio_name(ident) for ident in _identifiers(expr))


def _is_device_expr(expr: ast.AST | None, tainted: set[str]) -> bool:
    """Whether ``expr`` is a DEVICE-pixel value (by taint, marker or name)."""
    if expr is None:
        return False
    idents = _identifiers(expr)
    if idents & tainted:
        return True
    if any(marker in ident for ident in idents for marker in DEVICE_MARKERS):
        return True
    return any(DEVICE_NAME_RE.match(ident) for ident in idents)


def _assignment_targets(node: ast.AST) -> tuple[list[str], ast.expr | None]:
    """(assigned names, value) for a simple/annotated/unpacking assignment."""
    if isinstance(node, ast.Assign):
        value = node.value
        targets: list[str] = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                targets.append(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                targets.extend(
                    element.id
                    for element in target.elts
                    if isinstance(element, ast.Name)
                )
            elif isinstance(target, ast.Attribute):
                targets.append(target.attr)
        return targets, value
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        target = node.target
        if isinstance(target, ast.Name):
            return [target.id], node.value
    return [], None


def _function_params(fn: ast.AST) -> set[str]:
    args = getattr(fn, "args", None)
    if args is None:
        return set()
    names = [
        *getattr(args, "posonlyargs", []),
        *args.args,
        *args.kwonlyargs,
    ]
    return {arg.arg for arg in names}


def _device_taint(fn: ast.AST) -> set[str]:
    """Names inside ``fn`` that hold DEVICE px: params by name, values by origin.

    Fixpoint over assignments so ``fb = ctx.framebuffer_size`` and then
    ``w, h = fb`` both count; a chain longer than four hops is not a size
    derivation, it is a coincidence, and the detector should still flag it.
    """
    tainted = {name for name in _function_params(fn) if _is_device_name(name)}
    for _ in range(4):
        grew = False
        for node in _walk_own(fn):
            targets, value = _assignment_targets(node)
            if not targets or value is None:
                continue
            if not _is_device_expr(value, tainted):
                continue
            for name in targets:
                if name not in tainted:
                    tainted.add(name)
                    grew = True
        if not grew:
            break
    return tainted


def _is_device_name(name: str) -> bool:
    return bool(DEVICE_NAME_RE.match(name)) or any(
        marker in name for marker in DEVICE_MARKERS
    )


def _numeric_literal(node: ast.AST) -> float | None:
    """Value of a numeric literal (also ``-1``), else ``None``."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _numeric_literal(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    return None


def _is_matrix_literal(node: ast.AST) -> bool:
    """A 16-element numeric tuple/list, i.e. a hand-written ``mat4``."""
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 16:
        return False
    return all(_numeric_literal(element) is not None for element in node.elts)


def _local_values(fn: ast.AST) -> dict[str, list[ast.expr]]:
    values: dict[str, list[ast.expr]] = {}
    for node in _walk_own(fn):
        targets, value = _assignment_targets(node)
        if value is None:
            continue
        for name in targets:
            values.setdefault(name, []).append(value)
    return values


def _resolve(
    expr: ast.expr, values: dict[str, list[ast.expr]], depth: int = 2
) -> list[ast.expr]:
    """``expr`` plus every local value a Name in it was assigned from."""
    resolved: list[ast.expr] = [expr]
    if depth <= 0 or not isinstance(expr, ast.Name):
        return resolved
    for value in values.get(expr.id, []):
        resolved.extend(_resolve(value, values, depth - 1))
    return resolved


# ---------------------------------------------------------------------------
# clip-matrix-literal
# ---------------------------------------------------------------------------


def _clip_matrix_argument(call: ast.Call) -> ast.expr | None:
    """The matrix a stage/clip-aware call is handed, if any."""
    name = _call_name(call)
    if name == "stage_clip" and len(call.args) >= 2:
        return call.args[1]
    for keyword in call.keywords:
        if keyword.arg == "clip_matrix":
            return keyword.value
    return None


def _is_sanctioned_clip_source(expr: ast.expr) -> bool:
    if isinstance(expr, ast.Attribute):
        return expr.attr.endswith(CLIP_MATRIX_SUFFIXES)
    if isinstance(expr, ast.Name):
        return expr.id.endswith(CLIP_MATRIX_SUFFIXES)
    if isinstance(expr, ast.Call):
        name = _call_name(expr)
        if name.endswith(CLIP_MATRIX_SUFFIXES):
            return True
        # ``getattr(ctx, "clip_matrix", None)`` -- the context-carrying seam.
        if name == "getattr":
            return any(
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and arg.value.endswith(CLIP_MATRIX_SUFFIXES)
                for arg in expr.args[1:]
            )
    return False


def _clip_matrix_detail(
    candidates: list[ast.expr],
) -> str | None:
    """Why these candidates are not a sanctioned clip matrix (``None`` = fine).

    EVERY candidate must be sanctioned: the #752 shape assigned a literal on the
    ``is None`` branch of a ``getattr(ctx, "clip_matrix", None)`` fallback, so
    "one of the assignments is fine" would have missed it.
    """
    bad = [
        candidate
        for candidate in candidates
        if not _is_sanctioned_clip_source(candidate)
    ]
    if not bad:
        return None
    if any(_is_matrix_literal(candidate) for candidate in bad):
        return (
            "16-float matrix literal instead of the convention source; a "
            "literal mat4 is only correct on ONE backend (the #752 mirror)"
        )
    if any(
        isinstance(candidate, ast.Constant) and candidate.value is None
        for candidate in bad
    ):
        return (
            "identity/None clip matrix: 'no correction' is a backend claim, it "
            "must come from composited_clip_correction(rhi)"
        )
    names = [
        candidate.id for candidate in bad if isinstance(candidate, ast.Name)
    ]
    if any("IDENTITY" in name.upper() for name in names):
        return (
            "IDENTITY* matrix: the Y convention is decided by the backend, not "
            "by a local constant (use engine/gpu/rt_y_orientation)"
        )
    return (
        "matrix source not recognised as the Y-convention helper "
        f"(got {sorted(names) or 'a non-name expression'}); sanctioned: "
        "ctx.clip_matrix, composited_clip_correction(...), "
        "composited_clip_matrix(...), framing.clip_matrix(...), "
        "self._clip_matrix()"
    )


def _detect_clip_matrix_literal(fn: ast.AST) -> list[tuple[int, str]]:
    values = _local_values(fn)
    hits: list[tuple[int, str]] = []
    for call in _calls(fn):
        argument = _clip_matrix_argument(call)
        if argument is None:
            continue
        detail = _clip_matrix_detail(_resolve(argument, values))
        if detail is not None:
            hits.append((call.lineno, detail))
    return hits


# ---------------------------------------------------------------------------
# viewport-logical
# ---------------------------------------------------------------------------


def _viewport_size_args(call: ast.Call) -> list[ast.expr]:
    """The (width, height) expressions of a QRhiViewport/QRhiScissor."""
    if len(call.args) >= 4:
        return [call.args[2], call.args[3]]
    wanted = {"w", "width", "h", "height"}
    return [keyword.value for keyword in call.keywords if keyword.arg in wanted]


#: Calls that record a viewport from a caller-supplied size. The overlay shells
#: ARE the final device-px seam (see the allowlist), so a pass forwarding a
#: LOGICAL size into them is the same defect one frame up — that is exactly the
#: pre-#751 image_compare shape (`shell.draw(width=float(fb_w))` where `fb_w`
#: fell back to `ctx.width`).
_SEAM_DRAW_KEYWORDS = frozenset({"width", "height"})


def _is_viewport_source_call(call: ast.Call) -> bool:
    name = _call_name(call)
    if name in VIEWPORT_CTORS:
        return True
    return name == "draw" and bool(
        _SEAM_DRAW_KEYWORDS & {keyword.arg for keyword in call.keywords}
    )


_CONSTANT_NODE_TYPES = (
    ast.Constant,
    ast.operator,
    ast.unaryop,
    ast.cmpop,
    ast.boolop,
    ast.Tuple,
    ast.List,
    ast.Dict,
    ast.Set,
    ast.Load,
    ast.Store,
)


def _is_constant_expr(expr: ast.AST) -> bool:
    """A literal-only expression (``0``, ``(1, 1)``, ``{}``): no unit to lie about."""
    return all(isinstance(node, _CONSTANT_NODE_TYPES) for node in ast.walk(expr))


def _device_name_lies(fn: ast.AST, tainted: set[str]) -> list[tuple[int, str]]:
    """Device-named variables ASSIGNED from a logical expression.

    The pre-#751 half that a pure name check misses: `fb_w, fb_h = width, height`
    where `width`/`height` came from `ctx.width` — the name says device pixels,
    the value is logical, and the viewport then draws into 1/DPR of the target.
    Only functions that record a viewport reach here, and only names the
    vocabulary claims are device (`fb_*`, `*_device`, `px_*`, ...) are judged.
    """
    lies: list[tuple[int, str]] = []
    for node in _walk_own(fn):
        targets, value = _assignment_targets(node)
        if not targets or value is None:
            continue
        if _is_constant_expr(value):
            continue
        if _is_device_expr(value, tainted):
            continue
        for name in targets:
            if not _is_device_name(name):
                continue
            lies.append(
                (
                    getattr(node, "lineno", 0),
                    f"{name} is named as DEVICE pixels but is assigned from "
                    f"{ast.unparse(value)!r}, which is not derived from the "
                    "framebuffer — the viewport then draws into 1/DPR of the "
                    "target per axis (the pre-#751 shrink)",
                )
            )
    return lies


def _detect_viewport_logical(fn: ast.AST) -> list[tuple[int, str]]:
    calls = _calls(fn)
    if not any(_is_viewport_source_call(call) for call in calls):
        return []
    tainted = _device_taint(fn)
    hits: list[tuple[int, str]] = []
    for line, detail in _device_name_lies(fn, tainted):
        hits.append((line, detail))
    for call in calls:
        if not _is_viewport_source_call(call):
            continue
        for size in _viewport_size_args(call):
            if _is_device_expr(size, tainted):
                continue
            if all(
                _numeric_literal(node) is not None
                for node in ast.walk(size)
                if isinstance(node, ast.Constant) and isinstance(
                    node.value, (int, float)
                )
            ) and not _identifiers(size):
                continue
            hits.append(
                (
                    size.lineno,
                    "viewport/scissor sized from "
                    f"{ast.unparse(size)!r}, which is not derived from the "
                    "framebuffer (pixelSize()/framebuffer_size/*_fb/"
                    "renderTarget()); a logical size draws into 1/DPR of the "
                    "target per axis",
                )
            )
    return hits


# ---------------------------------------------------------------------------
# double-scale
# ---------------------------------------------------------------------------


def _ratio_geometry_uses(fn: ast.AST) -> list[tuple[int, str]]:
    uses: list[tuple[int, str]] = []
    for node in _walk_own(fn):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            for side in (node.left, node.right):
                if _has_ratio(side):
                    uses.append((node.lineno, ast.unparse(node)))
                    break
        elif isinstance(node, ast.Call) and _call_name(node) == "scale":
            if any(_has_ratio(argument) for argument in node.args):
                uses.append((node.lineno, ast.unparse(node)))
    return uses


def _detect_double_scale(fn: ast.AST) -> list[tuple[int, str]]:
    painter_calls = [call for call in _calls(fn) if _call_name(call) == "QPainter"]
    if not painter_calls:
        return []
    uses = _ratio_geometry_uses(fn)
    if not uses:
        return []
    if not any(_painter_target_is_dpr_aware(fn, call) for call in painter_calls):
        # A painter on a raster that carries NO devicePixelRatio (and is not a
        # widget) works in the raster's own device coordinates, so scaling by
        # the DPR there is the ONE legal application of the ratio, not a
        # second one. Both drag-overlay rasterizers do exactly that on a
        # ``ctx.framebuffer_size``-sized QImage -- see the negative fixture.
        return []
    return [
        (
            line,
            f"QPainter({ast.unparse(painter_calls[0].args[0]) if painter_calls[0].args else '...'}) "
            f"paints in LOGICAL coordinates already (target carries a device "
            f"pixel ratio) and the geometry is scaled by the ratio again "
            f"({expression}): the DPR enters twice",
        )
        for line, expression in uses[:1]
    ]


def _painter_target_is_dpr_aware(fn: ast.AST, call: ast.Call) -> bool:
    """Whether ``QPainter(<target>)`` already applies a device pixel ratio.

    Three shapes are dpr-aware and therefore make an extra ratio multiply a
    double application:

    * ``QPainter(self)`` / any widget -- a widget painter is logical-space by
      definition (Qt sets the dpr scale on it);
    * a raster TAGGED with ``setDevicePixelRatio`` in the same function;
    * a raster that came out of ``grab()``/``grabFramebuffer()``/``grabWindow()``.
    """
    if not call.args:
        return False
    target = call.args[0]
    if isinstance(target, ast.Name) and target.id == "self":
        return True
    calls = _calls(fn)
    if any(_is_grab_call(other) for other in calls):
        return True
    tagged: set[str] = set()
    for other in calls:
        if not (
            isinstance(other.func, ast.Attribute)
            and other.func.attr == "setDevicePixelRatio"
        ):
            continue
        owner = other.func.value
        if isinstance(owner, ast.Name):
            tagged.add(owner.id)
        elif isinstance(owner, ast.Attribute):
            tagged.add(owner.attr)
    if isinstance(target, ast.Name) and target.id in tagged:
        return True
    if isinstance(target, ast.Attribute) and target.attr in tagged:
        return True
    return False


# ---------------------------------------------------------------------------
# raster-logical-tagged / ratio-dropped-on-copy
# ---------------------------------------------------------------------------


def _raster_size_arguments(call: ast.Call) -> list[ast.expr]:
    """Size-bearing positional args of a QPixmap/QImage constructor."""
    sizes: list[ast.expr] = []
    for argument in call.args:
        if isinstance(argument, ast.Constant) and not isinstance(
            argument.value, (int, float)
        ):
            continue  # pixels/bytes, not a size
        if isinstance(argument, ast.Attribute) and argument.attr.startswith("Format"):
            continue  # QImage.Format.*
        if _call_name(argument) in {"bytes", "bytearray", "memoryview"}:
            continue  # the pixel payload, not a size
        sizes.append(argument)
    return sizes


def _is_raster_size_copy(expr: ast.expr) -> bool:
    """``<raster>.size()`` — a copy of another raster's DEVICE size."""
    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == "size"
        and not expr.args
    )


def _is_grab_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) in GRAB_METHODS


def _detect_raster_logical_tagged(fn: ast.AST) -> list[tuple[int, str]]:
    calls = _calls(fn)
    tagging = [
        call
        for call in calls
        if isinstance(call.func, ast.Attribute)
        and call.func.attr == "setDevicePixelRatio"
    ]
    if not tagging:
        return []
    grabed = any(_is_grab_call(call) for call in calls)
    tainted = _device_taint(fn)
    hits: list[tuple[int, str]] = []
    for call in calls:
        if _call_name(call) not in PAINTER_TARGET_NAMES:
            continue
        sizes = _raster_size_arguments(call)
        if not sizes:
            continue
        if all(_is_raster_size_copy(argument) for argument in sizes):
            continue  # ratio continuity is ratio-dropped-on-copy's job
        if grabed:
            continue  # a grab is device-sized by definition
        if all(_is_device_expr(argument, tainted) for argument in sizes):
            continue
        hits.append(
            (
                call.lineno,
                f"{_call_name(call)}(...) sized from logical px "
                f"({', '.join(ast.unparse(size) for size in sizes)}) and then "
                "tagged with setDevicePixelRatio(): the painter treats the "
                "canvas as size/dpr, so the content fills a corner",
            )
        )
    return hits


def _detect_ratio_dropped_on_copy(fn: ast.AST) -> list[tuple[int, str]]:
    calls = _calls(fn)
    if any(
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "setDevicePixelRatio"
        for call in calls
    ):
        return []
    hits: list[tuple[int, str]] = []
    for call in calls:
        if _call_name(call) not in PAINTER_TARGET_NAMES:
            continue
        if len(call.args) == 1 and _is_raster_size_copy(call.args[0]):
            source = ast.unparse(call.args[0].func.value)
            hits.append(
                (
                    call.lineno,
                    f"{_call_name(call)}({source}.size()) is a new raster with "
                    "ratio 1.0: copy the source's devicePixelRatio() in the same "
                    "function, or the copy is drawn at half size on HiDPI",
                )
            )
    return hits


# ---------------------------------------------------------------------------
# ratio-rounded / ratio-hardcoded
# ---------------------------------------------------------------------------


def _is_ratio_value(expr: ast.AST) -> bool:
    """Whether ``expr`` IS a ratio (so rounding it loses the fractional DPR).

    ``int(dpr)`` truncates the ratio itself; ``int(round(x * dpr))`` is the
    documented way to allocate a device raster and must NOT be flagged. Only
    wrapper calls (``int``/``round``/``float``/``max``/``min``/...) are stripped
    before the identifier test, so a coordinate never hides the check.
    """
    idents: set[str] = set()
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(node, ast.Call):
            # The callee matters too: ``visible.width() * dpr`` must not look
            # like "just a ratio" because the receiver hangs off the func side.
            stack.append(node.func)
            stack.extend(node.args)
        elif isinstance(
            node, (ast.operator, ast.unaryop, ast.cmpop, ast.expr_context)
        ):
            continue
        else:
            stack.extend(ast.iter_child_nodes(node))
    return bool(idents) and all(_is_ratio_name(ident) for ident in idents)


def _round_keeps_the_fraction(call: ast.Call) -> bool:
    """``round(x, n)`` with n > 0 keeps a fractional ratio (a cache key)."""
    if _call_name(call) != "round" or len(call.args) < 2:
        return False
    digits = _numeric_literal(call.args[1])
    return digits is not None and digits > 0


def _detect_ratio_rounded(fn: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for call in _calls(fn):
        name = _call_name(call)
        if name in {"int", "round", "floor", "ceil"} and call.args:
            if _round_keeps_the_fraction(call):
                continue
            if not _is_ratio_value(call.args[0]):
                continue
            hits.append(
                (
                    call.lineno,
                    f"{name}(<ratio>): a fractional DPR (1.25/1.5) must "
                    "survive as a float; rounding the ratio picks a wrong "
                    f"buffer geometry ({ast.unparse(call)})",
                )
            )
        elif name == "setDevicePixelRatio" and call.args:
            literal = _numeric_literal(call.args[0])
            if literal is not None and isinstance(
                getattr(call.args[0], "value", None), int
            ):
                hits.append(
                    (
                        call.lineno,
                        f"setDevicePixelRatio({int(literal)}) rounds the ratio "
                        "to an integer",
                    )
                )
    return hits


def _detect_ratio_hardcoded(fn: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for call in _calls(fn):
        if _call_name(call) != "setDevicePixelRatio" or not call.args:
            continue
        literal = _numeric_literal(call.args[0])
        if literal is not None:
            hits.append(
                (
                    call.lineno,
                    f"setDevicePixelRatio({literal:g}) hardcodes the ratio: read "
                    "the raster's own devicePixelRatio() instead",
                )
            )
    return hits


#: In tests, an assertion that a ratio EQUALS a numeric literal assumes the host
#: ratio; the value under test (or ``devicePixelRatioF()``) must be the other side.
_TEST_RATIO_COMPARE_RE = re.compile(
    r"\.devicePixelRatio(?:F)?\(\)\s*[=!]=\s*(?P<literal>\d+(?:\.\d+)?)\b"
    r"|(?P<literal2>\d+(?:\.\d+)?)\s*[=!]=\s*\w+\.devicePixelRatio(?:F)?\(\)"
)


def _detect_ratio_hardcoded_in_tests(text: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        match = _TEST_RATIO_COMPARE_RE.search(line)
        if match is None:
            continue
        # ``assert pixmap.devicePixelRatio() == 2.0`` right after the test set
        # that ratio itself is still an assumption about the host -- the
        # allowlist carries the reason when it is genuinely the test's input.
        hits.append(
            (
                number,
                "ratio compared to a numeric literal: assert against the value "
                "the fixture set, or against devicePixelRatioF()",
            )
        )
    return hits


# ---------------------------------------------------------------------------
# uv-flip-compensation
# ---------------------------------------------------------------------------


#: ``1.0 - vUv.y`` is a flip; ``1.0 - vTexCoord.y * 2.0`` is the standard
#: UV->NDC mapping every pixel-space quad does (measured: focus_dim.frag,
#: grid_divider.frag, slot_array.vert, base_array.vert), so the lookahead
#: excludes the ``* 2.0`` form — the convention correction there comes from the
#: clip matrix, not from the UV arithmetic.
_UV_FLIP_SHADER_RE = re.compile(
    r"1\.0\s*-\s*[\w.]+\.\s*y\b(?!\s*\*\s*2\.0)"  # 1.0 - vUv.y
    r"|\.mirrored\s*\("
)
_UV_FLIP_GATE_RE = re.compile(r"\bflipY\b|\bflip_y\b|\bmix\s*\(")
_UV_FLIP_SANCTIONED_CALL_RE = re.compile(
    r"\b(?:sampled_rt_needs_y_flip|widget_texture_needs_y_flip"
    r"|composited_scissor_needs_y_flip|sampled_rt_correction"
    r"|composited_clip_correction|composited_clip_matrix)\s*\("
)


def _is_y_flip_matrix_literal(node: ast.AST) -> bool:
    """A 16-element mat4 literal with -1 on the Y diagonal (diag(1,-1,1,1))."""
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 16:
        return False
    values = [_numeric_literal(element) for element in node.elts]
    if any(value is None for value in values):
        return False
    return values[5] == -1.0


def _detect_uv_flip_python(fn: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in _walk_own(fn):
        if isinstance(node, ast.Call) and _call_name(node) == "mirrored":
            hits.append(
                (
                    node.lineno,
                    "Qt .mirrored(): a mirror is a Y-convention decision, "
                    "route it through engine/gpu/rt_y_orientation",
                )
            )
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
            left = _numeric_literal(node.left)
            right = node.right
            if (
                left == 1.0
                and isinstance(right, ast.Attribute)
                and right.attr == "y"
            ):
                hits.append(
                    (
                        node.lineno,
                        f"{ast.unparse(node)}: a UV flip compensated in geometry; "
                        "the flip belongs to the rt_y_orientation case, not to "
                        "the arithmetic",
                    )
                )
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if (
                re.match(r"^flip_?y$", target.id)
                and _numeric_literal(node.value) is None
                and isinstance(node.value, ast.Constant)
            ):
                hits.append(
                    (
                        node.lineno,
                        f"{target.id} = {ast.unparse(node.value)}: a hardcoded "
                        "flip bit; ask widget_texture_needs_y_flip/"
                        "sampled_rt_needs_y_flip",
                    )
                )
            elif "flip" in target.id.lower() and _is_y_flip_matrix_literal(
                node.value
            ):
                hits.append(
                    (
                        node.lineno,
                        f"{target.id} = a local diag(1,-1,1,1) flip matrix: the "
                        "Y convention belongs to engine/gpu/rt_y_orientation "
                        "(sampled_rt_correction / composited_clip_correction), "
                        "and an unconditional flip is only right on one backend",
                    )
                )
    return hits


def _shader_source(text: str) -> str:
    """Source without line comments (prose about a flip is not a flip)."""
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def _detect_uv_flip_shader(text: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(_shader_source(text).splitlines(), start=1):
        if _UV_FLIP_SHADER_RE.search(line) is None:
            continue
        if _UV_FLIP_GATE_RE.search(line) or _UV_FLIP_SANCTIONED_CALL_RE.search(line):
            continue
        hits.append(
            (
                number,
                f"{line.strip()!r}: unconditional UV/geometry Y flip in a shader; "
                "a flip must be gated on the backend (see glass_blur.frag's "
                "flipY uniform) or decided by engine/gpu/rt_y_orientation",
            )
        )
    return hits


# ---------------------------------------------------------------------------
# primary-screen-grab
# ---------------------------------------------------------------------------


def _detect_primary_screen_grab(fn: ast.AST) -> list[tuple[int, str]]:
    grabs = [call for call in _calls(fn) if _call_name(call) == "grabWindow"]
    if not grabs:
        return []
    if not any(_call_name(call) in SCREEN_PRIMARY_METHODS for call in _calls(fn)):
        return []
    return [
        (
            grabs[0].lineno,
            "grabWindow() on the application's primaryScreen(): a grab must ask "
            "the TARGET's screen (windowHandle().screen() / widget.screen()) -- "
            "on a mixed-DPI desktop the primary answers the wrong geometry and "
            "the wrong pixels",
        )
    ]


# ---------------------------------------------------------------------------
# silent-downsample
# ---------------------------------------------------------------------------


def _detect_silent_downsample(fn: ast.AST) -> list[tuple[int, str]]:
    calls = _calls(fn)
    if not any(_is_grab_call(call) for call in calls):
        return []
    tainted = _device_taint(fn)
    hits: list[tuple[int, str]] = []
    for call in calls:
        if _call_name(call) not in {"resize", "scaled"} or not call.args:
            continue
        target = call.args[0]
        if _is_device_expr(target, tainted):
            continue
        hits.append(
            (
                call.lineno,
                f"a DEVICE-pixel grab resized to a logical size "
                f"({_call_name(call)}({ast.unparse(target)})): on a HiDPI host "
                "the grab is 2x and this silently halves the resolution",
            )
        )
    return hits


# ---------------------------------------------------------------------------
# The scanner
# ---------------------------------------------------------------------------

_FUNCTION_DETECTORS = (
    (RULE_CLIP_MATRIX_LITERAL, _detect_clip_matrix_literal),
    (RULE_VIEWPORT_LOGICAL, _detect_viewport_logical),
    (RULE_DOUBLE_SCALE, _detect_double_scale),
    (RULE_RASTER_LOGICAL_TAGGED, _detect_raster_logical_tagged),
    (RULE_RATIO_DROPPED_ON_COPY, _detect_ratio_dropped_on_copy),
    (RULE_RATIO_ROUNDED, _detect_ratio_rounded),
    (RULE_RATIO_HARDCODED, _detect_ratio_hardcoded),
    (RULE_UV_FLIP_COMPENSATION, _detect_uv_flip_python),
    (RULE_PRIMARY_SCREEN_GRAB, _detect_primary_screen_grab),
    (RULE_SILENT_DOWNSAMPLE, _detect_silent_downsample),
)


def scan_tree(tree: ast.Module, rel_name: str) -> list[Hit]:
    """Every static hit in one parsed module (function-scoped rules only)."""
    hits: list[Hit] = []
    seen: set[tuple[str, str, int, str]] = set()
    for function_name, node in _functions(tree):
        for rule, detector in _FUNCTION_DETECTORS:
            for line, detail in detector(node):
                marker = (rule, function_name, line, detail)
                if marker in seen:
                    continue
                seen.add(marker)
                hits.append(Hit(rule, rel_name, function_name, line, detail))
    for rule, detail in _module_level_hits(tree):
        marker = (rule, "<module>", 0, detail)
        if marker in seen:
            continue
        seen.add(marker)
        hits.append(Hit(rule, rel_name, "<module>", 0, detail))
    return hits


def _module_level_hits(tree: ast.Module) -> list[tuple[str, str]]:
    """Hits for module-scope statements (a stub context built at import time)."""
    hits: list[tuple[str, str]] = []
    for statement in tree.body:
        if isinstance(
            statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        for rule, detector in (
            (RULE_CLIP_MATRIX_LITERAL, _detect_clip_matrix_literal),
            (RULE_RATIO_HARDCODED, _detect_ratio_hardcoded),
        ):
            for _line, detail in detector(statement):
                hits.append((rule, detail))
    return hits


def scan_source(text: str, rel_name: str) -> list[Hit]:
    """Scan source *text* (used by the fixture self-test)."""
    return scan_tree(ast.parse(text), rel_name)


def scan_shader(text: str, rel_name: str) -> list[Hit]:
    return [
        Hit(RULE_UV_FLIP_COMPENSATION, rel_name, "<shader>", line, detail)
        for line, detail in _detect_uv_flip_shader(text)
    ]


def scan_path(path: Path) -> list[Hit]:
    relative = rel(path)
    if path.suffix in {".frag", ".vert"}:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable shader
            return []
        return scan_shader(text, relative)
    tree = parse(path)
    if tree is None:
        return []
    return scan_tree(tree, relative)


def scan_repository() -> list[Hit]:
    """Every static hit in the app tree and in the app's own shaders."""
    hits: list[Hit] = []
    for path in iter_py(SRC):
        hits.extend(scan_path(path))
    for suffix in ("*.frag", "*.vert"):
        for path in sorted(SRC.rglob(suffix)):
            if "__pycache__" in path.parts:
                continue
            hits.extend(scan_path(path))
    return hits


def scan_test_ratio_literals() -> list[Hit]:
    """Rule ``ratio-hardcoded`` over ``tests/`` (comparison-against-literal shape)."""
    hits: list[Hit] = []
    for path in sorted((ROOT / "tests").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if FIXTURES_DIR in path.parents:
            continue  # snippets are DATA here, not tests that run
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover
            continue
        relative = rel(path)
        for line, detail in _detect_ratio_hardcoded_in_tests(text):
            hits.append(Hit(RULE_RATIO_HARDCODED, relative, "<test>", line, detail))
    return hits


# ---------------------------------------------------------------------------
# Positive helper — the one name future tests should call
# ---------------------------------------------------------------------------


def _rect_size(rect) -> tuple[float, float]:
    if hasattr(rect, "width") and hasattr(rect, "height"):
        return float(rect.width()), float(rect.height())
    width, height = rect
    return float(width), float(height)


def assert_device_sized(raster, logical_rect, *, label: str = "raster") -> None:
    """Assert *raster* is device-px sized and logical-px tagged for *logical_rect*.

    ``assert_device_sized(pixmap, QRect(0, 0, 200, 100))`` at DPR=2 requires
    ``size() == (400, 200)`` and ``deviceIndependentSize() == (200, 100)``: both
    halves of the measured fact, in one call, so a future test does not have to
    re-derive which of the two numbers it is looking at.
    """
    ratio = float(raster.devicePixelRatio())
    width, height = _rect_size(logical_rect)
    expected_device = (round(width * ratio), round(height * ratio))
    logical = raster.deviceIndependentSize()
    logical_size = (round(float(logical.width()), 4), round(float(logical.height()), 4))
    assert logical_size == (round(width, 4), round(height, 4)), (
        f"{label} must be device-INDEPENDENT {width:g}x{height:g} logical px, "
        f"but reports {logical_size[0]:g}x{logical_size[1]:g} (ratio {ratio:g})"
    )
    actual = (int(raster.width()), int(raster.height()))
    assert actual == expected_device, (
        f"{label} must be {expected_device[0]}x{expected_device[1]} DEVICE px "
        f"(logical {width:g}x{height:g} at ratio {ratio:g}), got "
        f"{actual[0]}x{actual[1]}"
    )


# ---------------------------------------------------------------------------
# Live gates
# ---------------------------------------------------------------------------


def test_no_known_dpr_failure_mode_in_the_tree():
    """Zero *undeclared* hits across ``src/`` and its shaders.

    Two exemptions exist and they mean different things: ``DPR_ALLOWLIST`` says
    "this shape is legitimate here, and this is the measurement that proves it";
    ``KNOWN_DEFECTS`` says "this is a real bug with an owner, filed, not fixed
    in this change". Neither may grow without one of those.
    """
    hits = scan_repository()
    unallowed = [
        hit
        for hit in hits
        if hit.key not in DPR_ALLOWLIST
        and (hit.rel, hit.line, hit.rule) not in KNOWN_DEFECTS
    ]
    assert not unallowed, (
        "known DPR/Y-orientation failure modes found — every one of these has "
        "already shipped once:\n  "
        + "\n  ".join(str(hit) for hit in unallowed)
        + "\n\nEither fix it, add a measured reason to "
        "tests/contracts/dpr_catalog_allowlist.py (legitimate shape), or declare "
        "it in KNOWN_DEFECTS with a task id (known bug, someone else's fix)."
    )


def test_known_defects_are_still_present():
    """Declarations expire: fixed or moved code must delete its entry."""
    live = {(hit.rel, hit.line, hit.rule) for hit in scan_repository()}
    stale = sorted(KNOWN_DEFECTS - live)
    assert not stale, (
        "KNOWN_DEFECTS entries no longer match a hit — either the defect was "
        "fixed (delete the entry: the gate must go quiet on its own) or the code "
        "moved (re-read the site and re-declare its new line):\n  "
        + "\n  ".join(f"{rel_path}:{line} [{rule}]" for rel_path, line, rule in stale)
    )


def test_no_ratio_literal_in_tests():
    """Rule ``ratio-hardcoded`` over the test tree (assumed host ratios)."""
    hits = scan_test_ratio_literals()
    unallowed = [hit for hit in hits if hit.key not in DPR_ALLOWLIST]
    assert not unallowed, (
        "tests assume a numeric device pixel ratio:\n  "
        + "\n  ".join(str(hit) for hit in unallowed)
        + "\n\nCompare against the value the fixture set, or against "
        "devicePixelRatioF()."
    )


def test_allowlist_entries_are_alive_and_still_guilty():
    """Shrink-only ratchet: no empty reasons, no stale entries, no rot."""
    live = {(hit.rel, hit.function, hit.rule) for hit in _all_static_hits()}
    for key, reason in DPR_ALLOWLIST.items():
        relative, function_name, rule = key
        assert reason.strip(), f"{key}: allowlist entry needs a measured reason"
        assert rule in RULE_IDS, f"{key}: unknown rule id"
        assert (SRC.parent / relative).exists(), (
            f"{key} names a file that no longer exists — drop the entry"
        )
        assert key in live, (
            f"{key} no longer matches a hit — the code was fixed or renamed; "
            "delete the entry (the ratchet must shrink, not rot)"
        )


def _all_static_hits() -> list[Hit]:
    return scan_repository() + scan_test_ratio_literals()


# ---------------------------------------------------------------------------
# Self-test: the detectors must be red on the real broken code
# ---------------------------------------------------------------------------

_PROVENANCE_RE = re.compile(
    r"^#\s*provenance:\s*(?P<path>\S+):(?P<line>\d+)\s*@\s*(?P<commit>\S+)"
    r".*?$",
    re.MULTILINE,
)
_RULE_HEADER_RE = re.compile(r"^#\s*rule:\s*(?P<rule>[\w-]+)\s*$", re.MULTILINE)


def _fixture_files() -> list[Path]:
    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(
        path
        for path in FIXTURES_DIR.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )


def _fixture_metadata(path: Path) -> tuple[str, int, str, str]:
    text = path.read_text(encoding="utf-8")
    provenance = _PROVENANCE_RE.search(text)
    rule = _RULE_HEADER_RE.search(text)
    assert provenance is not None, (
        f"{path.name}: missing '# provenance: <path>:<line> @ <commit>' header — "
        "a fixture without provenance is an invented snippet"
    )
    assert rule is not None, f"{path.name}: missing '# rule: <rule-id>' header"
    return (
        provenance.group("path"),
        int(provenance.group("line")),
        provenance.group("commit"),
        rule.group("rule"),
    )


def test_every_static_rule_has_a_fixture():
    """No detector may exist without a snippet of code that it catches."""
    covered = {_fixture_metadata(path)[3] for path in _fixture_files()}
    missing = sorted(set(STATIC_RULES) - covered)
    assert not missing, (
        f"no fixture proves these detectors ever fire: {missing} — add a real "
        "broken snippet under tests/contracts/fixtures/dpr_bad_snippets/"
    )


def test_fixtures_carry_provenance():
    """Each fixture names where the broken code came from."""
    for path in _fixture_files():
        provenance_path, line, commit, rule = _fixture_metadata(path)
        assert provenance_path.startswith("src/") or provenance_path.startswith(
            "tests/"
        ), f"{path.name}: provenance must name a repo path, got {provenance_path!r}"
        assert line >= 0, f"{path.name}: provenance line must be non-negative"
        assert commit, f"{path.name}: provenance needs a commit (or 'reconstructed')"
        assert rule in RULE_IDS or rule == NONE_RULE, (
            f"{path.name}: unknown rule id {rule!r}"
        )


def test_every_behavioural_rule_has_an_executable_fixture():
    """The rules with no static hit are still falsified by real code."""
    covered = {_fixture_metadata(path)[3] for path in _fixture_files()}
    missing = sorted(BEHAVIOURAL_RULES - covered)
    assert not missing, (
        f"behavioural rules with no fixture: {missing} — a behavioural rule "
        "without a pre-fix snippet cannot show it discriminates"
    )


def test_detectors_are_red_on_the_real_broken_code():
    """The whole point: a detector that only fires on invented code is useless."""
    failures: list[str] = []
    for path in _fixture_files():
        provenance_path, line, commit, rule = _fixture_metadata(path)
        if rule == NONE_RULE:
            text = path.read_text(encoding="utf-8")
            hits = (
                scan_shader(text, provenance_path)
                if path.suffix in {".frag", ".vert"}
                else scan_source(text, provenance_path)
            )
            if hits:
                failures.append(
                    f"{path.name}: expected NO hit (legal shape), got "
                    + "; ".join(str(hit) for hit in hits)
                )
            continue
        if rule in BEHAVIOURAL_RULES:
            # Behavioural rules are falsified by loading and RUNNING the
            # fixture (see test_the_prefix_snippet_still_reproduces_the_defect).
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix in {".frag", ".vert"}:
            hits = scan_shader(text, provenance_path)
        else:
            hits = scan_source(text, provenance_path)
        if not any(hit.rule == rule for hit in hits):
            failures.append(
                f"{path.name}: {rule} did not fire (provenance "
                f"{provenance_path}:{line} @ {commit}); got "
                f"{[hit.rule for hit in hits] or 'nothing'}"
            )
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Behavioural gates
# ---------------------------------------------------------------------------


def _qt_app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _prefixed_clip_to_visible():
    """The PRE-#755 ``_clip_to_visible`` body, loaded from its fixture."""
    fixture = FIXTURES_DIR / "capture_clip_logical_rect.py"
    namespace: dict[str, object] = {}
    exec(compile(fixture.read_text(encoding="utf-8"), str(fixture), "exec"), namespace)
    return namespace["_clip_to_visible"]


def test_geometry_device_copy_keeps_the_whole_visible_rect():
    """Rule ``geometry-device-copy``: a logical rect out of a DPR=2 grab.

    Measured defect (2026-10-27): a 2560x1600 grab with a 1280x700 logical
    visible rect came back 1280x700 device px — the top-left 1/DPR² of the
    window, so the capture "lost" three quarters of the screen.
    """
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QPixmap

    from core.control import capture as capture_mod

    _qt_app()
    grab = QPixmap(2560, 1600)
    grab.setDevicePixelRatio(2.0)
    grab.fill(QColor(0, 0, 0))
    # Tag the far corner of the visible half so a "top-left quarter" crop is
    # detectable by content, not only by size.
    grab.toImage()

    clipped = capture_mod._clip_to_visible(grab, QRect(0, 0, 1280, 700))

    assert_device_sized(clipped, QRect(0, 0, 1280, 700), label="clipped grab")
    assert (clipped.width(), clipped.height()) == (2560, 1400)


def test_the_prefix_snippet_still_reproduces_the_defect():
    """Falsification: the pre-#755 body slices the logical rect as device px.

    Without this the behavioural gate above could pass on a tree where nobody
    ever wrote the bug — the fixture is the proof that the check discriminates.
    """
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QPixmap

    _qt_app()
    prefix_clip = _prefixed_clip_to_visible()
    grab = QPixmap(2560, 1600)
    grab.setDevicePixelRatio(2.0)
    grab.fill(QColor(0, 0, 0))

    clipped = prefix_clip(grab, QRect(0, 0, 1280, 700))

    assert (clipped.width(), clipped.height()) == (1280, 700), (
        "the pre-#755 snippet no longer reproduces the 1/DPR^2 crop — the "
        "fixture was edited, and this gate lost its falsification story"
    )
    assert clipped.deviceIndependentSize().toSize().toTuple() == (640, 350)


class _GrabWidget:
    """Widget shaped like the offscreen export canvas: a device-pixel grab."""

    def __init__(self, logical: tuple[int, int], ratio: float) -> None:
        from PySide6.QtGui import QColor, QImage

        self._logical = logical
        self._ratio = ratio
        self.resized: list[tuple[int, int]] = []
        image = QImage(
            round(logical[0] * ratio),
            round(logical[1] * ratio),
            QImage.Format.Format_RGBA8888,
        )
        image.fill(QColor(0, 0, 0))
        # A marker in the middle of the TOP-LEFT logical quadrant: a crop (not a
        # resize) would move it, a supersample-downscale keeps it.
        marker = QColor(255, 0, 0)
        for x in range(4):
            for y in range(4):
                image.setPixelColor(
                    round(logical[0] * ratio * 0.25) + x,
                    round(logical[1] * ratio * 0.25) + y,
                    marker,
                )
        self._image = image

    # --- QWidget surface the exporter touches ---------------------------------
    def resize(self, width: int, height: int) -> None:
        self.resized.append((width, height))

    def show(self) -> None:
        return None

    def update(self) -> None:
        return None

    def theme_revision(self) -> int:
        return 0

    # --- grab surface ---------------------------------------------------------
    def grabFramebuffer(self):
        return self._image

    def devicePixelRatioF(self) -> float:
        return self._ratio


def test_export_grab_downscale_preserves_content():
    """Rule ``silent-downsample``: the export resize is a SUPERSAMPLE, not a crop.

    At DPR=2 the offscreen canvas renders the same logical layout at twice the
    resolution; ``_render_single`` brings that back to the export raster. If
    that resize ever became a slice (or the target stopped being the export
    size), the marker leaves its logical position and this test says so.
    """
    from engine.gpu import export_tiling

    _qt_app()
    widget = _GrabWidget((400, 300), 2.0)
    exporter = export_tiling.TiledFramebufferExporter(
        widget,
        set_export_viewport=lambda _viewport: None,
        prepare_frame=lambda: None,
        query_max_texture_size=lambda: 8192,
    )

    image = exporter._render_single(400, 300)

    assert image.size == (400, 300), (
        f"the export raster is {image.size}, not the requested logical 400x300"
    )
    marker = image.getpixel((100, 75))
    assert marker[0] > 150, (
        f"the origin marker moved to {marker} — the DPR=2 grab was cropped "
        "instead of downsampled"
    )
