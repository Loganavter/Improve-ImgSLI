"""Ratchet: chrome geometry must go through ``scaled_px`` **per site**.

Dogma source: docs/dev/CONTRACTS.md §UI Scale Contract. Chrome geometry is
authored in design px and multiplied by ``UiScale`` at exactly one boundary
(``scaled_px`` / ``UiFont``). This gate finds sites that bypass or freeze
that boundary.

Why this file was rewritten (plan ``plan-live-appearance-fixes-2026-10-19``):
the previous version skipped a whole file as soon as its text mentioned
``scaled_px``/``ui_font`` and only knew ``setFixed*``/``setMinimum*``. One
correctly scaled line therefore hid every raw literal in the file — the
owner's "plain px instead of scaled_px" class (chips/flyouts/dialogs keeping
design px after a scale change) shipped behind a green gate. The scan is now
**per finding**, never per file.

Flagged shapes:

1. ``import-time`` — a module/class-level constant (or function default) that
   evaluates ``scaled_px(...)`` at import time. It is frozen at the scale
   factor of the first import and can never follow a later scale change.
2. ``raw`` — a raw numeric literal in chrome geometry:
   ``setFixed{Width,Height,Size}``, ``setMinimum{Width,Height,Size}``,
   ``setMaximum{Width,Height,Size}``, ``resize(...)``, ``QSize(...)``,
   ``setContentsMargins(...)``, ``setSpacing(...)``. ``0``, ``1`` and
   ``16777215`` (``QWIDGETSIZE_MAX``) are structural sentinels, not design
   px, and are ignored.
3. ``double`` — ``scaled_px(...)`` passed into a toolkit ``size=`` kwarg.
   ``size=`` on toolkit widgets/overlays is a design-px channel that scales
   internally; pre-multiplying applies the factor twice (the gallery
   ``Button(size=(scaled_px(132), scaled_px(34)))`` bug).

Ratchet mechanics: every current site is listed in ``EXEMPTED_SITES`` (or a
whole file in ``EXEMPTIONS``) with a reason, and the counts are **exact** —
a new identical literal fails (count grows) and a fixed site fails until its
count is lowered in the same commit. The drain wave removes entries as it
converts sites; see plan ``plan-live-appearance-fixes-2026-10-19``.

Falsification: ``test_detector_flags_synthetic_offender`` proves the detector
is not blind to a scale-aware file, and
``test_synthetic_clean_file_is_not_flagged`` proves it does not flag
correctly scaled code.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from tests.contracts._framework import SRC, parse, rel

#: ``QWIDGETSIZE_MAX`` plus the two structural zeros Qt uses for "no
#: constraint"/"one pixel". These are layout sentinels, never design px.
_STRUCTURAL_SENTINELS = frozenset({0, 1, 16777215})

#: Geometry setters/constructors whose numeric literal arguments are design px.
_RAW_GEOMETRY_CALLS = frozenset(
    {
        "setFixedWidth",
        "setFixedHeight",
        "setFixedSize",
        "setMinimumWidth",
        "setMinimumHeight",
        "setMinimumSize",
        "setMaximumWidth",
        "setMaximumHeight",
        "setMaximumSize",
        "resize",
        "QSize",
        "setContentsMargins",
        "setSpacing",
    }
)

#: Toolkit ``size=`` kwargs take DESIGN px and scale internally (Button and
#: the overlay/bubble popups). A ``scaled_px`` value here is double-scaled.
_SELF_SCALING_KWARGS = frozenset({"size"})

#: The ``scaled_px`` symbol, plus any ``import ... as`` alias of it.
_SCALED_PX_NAME = "scaled_px"

#: Whole-file exemptions: path -> reason. Only for a module whose chrome
#: geometry is ENTIRELY out of design space (canvas/image-space minimums).
#: Prefer ``EXEMPTED_SITES`` — a whole-file entry hides future raw sites.
EXEMPTIONS: dict[str, str] = {}

_DRAIN = "design px literal not yet migrated — drain wave wraps with scaled_px()"
_IMPORT_BAKE = (
    "import-time scaled_px bake — frozen at the first import's scale factor, "
    "cannot follow a live scale change; drain wave converts to call-time helpers"
)
_DESIGN_PX_API = (
    "toolkit popup/button size= takes design px and scales internally — "
    "pre-multiplying with scaled_px() would double-scale"
)
_RASTER = "QIcon pixmap raster request in raster space, not chrome geometry"
_CANVAS_IMAGE_SPACE = "canvas image-space minimum (UI-scale plan non-goal)"

#: path -> {site key: (allowed occurrences, reason)}.
#: Seeded from this detector's run on the current tree (not hand-copied).
#: Drain wave (plan-live-appearance-fixes-2026-10-19) removes entries as it
#: converts each site; never add an entry without a real reason.
EXEMPTED_SITES: dict[str, dict[str, tuple[int, str]]] = {
    "src/tabs/image_compare/ui/primitives.py": {
        "setMinimumSize(200, 150)": (1, _CANVAS_IMAGE_SPACE),
    },
    "src/tabs/image_gallery/ui/card/context_menu/icons.py": {
        "QSize(64, 64)": (1, _RASTER),
    },
    "src/tabs/image_gallery/ui/quick_look/overlay_build/icons.py": {
        "QSize(64, 64)": (1, _RASTER),
    },
    "src/tabs/multi_compare/widget.py": {
        "setMinimumSize(400, 300)": (1, _CANVAS_IMAGE_SPACE),
    },
}


@dataclass(frozen=True)
class Finding:
    """One geometry site that bypassed or froze the UI-scale boundary."""

    path: str
    lineno: int
    kind: str  # "import-time" | "raw" | "double"
    site: str  # stable key, no line numbers (see EXEMPTED_SITES)
    detail: str = ""

    def render(self) -> str:
        return f"{self.path}:{self.lineno} [{self.kind}] {self.site}"


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _numeric_literal(node: ast.AST) -> int | float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if isinstance(node.value, bool):
            return None
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _numeric_literal(node.operand)
        return -value if value is not None else None
    return None


def _scaled_px_names(tree: ast.Module) -> set[str]:
    """Local names bound to ``scaled_px`` (plain and aliased imports)."""
    names = {_SCALED_PX_NAME}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == _SCALED_PX_NAME:
                    names.add(alias.asname or alias.name)
    return names


def _is_scaled_px_call(node: ast.AST, names: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in names
    if isinstance(func, ast.Attribute):
        return func.attr in names
    return False


def _contains_scaled_px(node: ast.AST, names: set[str]) -> bool:
    return any(_is_scaled_px_call(sub, names) for sub in ast.walk(node))


def _site_from_call(name: str, node: ast.Call) -> str:
    """Stable site key: call shape with literals, without the receiver."""
    args = ", ".join(ast.unparse(arg) for arg in node.args)
    return f"{name}({args})"


def _import_time_findings(tree: ast.Module, path: str) -> list[Finding]:
    names = _scaled_px_names(tree)
    findings: list[Finding] = []

    def visit(body: list[ast.stmt], owner: str = "") -> None:
        for node in body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if value is None or not _contains_scaled_px(value, names):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                target = ast.unparse(targets[0])
                prefix = f"{owner}." if owner else ""
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "import-time",
                        f"{prefix}{target} = {ast.unparse(value)}",
                        "evaluated once at import; cannot follow a later "
                        "UiScale change",
                    )
                )
            elif isinstance(node, ast.ClassDef):
                visit(node.body, node.name)

    visit(tree.body)

    # Defaults are evaluated when the ``def`` executes (import time for
    # module/class methods), so they are the same class of bake.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        defaults = list(node.args.defaults) + [
            d for d in node.args.kw_defaults if d is not None
        ]
        for default in defaults:
            if _contains_scaled_px(default, names):
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "import-time",
                        f"default:{node.name} = {ast.unparse(default)}",
                        "default evaluated at def time; cannot follow a later "
                        "UiScale change",
                    )
                )
    return findings


def _call_findings(tree: ast.Module, path: str) -> list[Finding]:
    names = _scaled_px_names(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name in _RAW_GEOMETRY_CALLS:
            for arg in node.args:
                value = _numeric_literal(arg)
                if value is not None and value not in _STRUCTURAL_SENTINELS:
                    findings.append(
                        Finding(
                            path,
                            node.lineno,
                            "raw",
                            _site_from_call(name, node),
                            f"raw literal {ast.unparse(arg)} — wrap design px "
                            f"with scaled_px()",
                        )
                    )
                    break
        for kw in node.keywords:
            if kw.arg in _SELF_SCALING_KWARGS and _contains_scaled_px(kw.value, names):
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "double",
                        f"{name or '<call>'}({kw.arg}={ast.unparse(kw.value)})",
                        "toolkit size= already scales design px — "
                        "scaled_px() here applies the factor twice",
                    )
                )
    return findings


def scan_source(text: str, path: str) -> list[Finding]:
    """Scan in-memory source (falsification tests use this)."""
    tree = ast.parse(text)
    return _import_time_findings(tree, path) + _call_findings(tree, path)


def iter_scan_files() -> list[Path]:
    """Every ``src/`` module the gate owns.

    The named chrome roots (``ui/``, ``plugins/``, ``tabs/``) plus the old
    gate's full-``src`` sweep: narrowing the call list must never lose
    coverage. Non-chrome hits (image-space raster/minimum sizes) are exempted
    per site with a reason.
    """
    out: list[Path] = []
    for path in sorted(SRC.rglob("*.py")):
        parts = path.parts
        if "__pycache__" in parts or "tests" in parts:
            continue
        out.append(path)
    return out


def scan_tree() -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_scan_files():
        tree = parse(path)
        assert tree is not None, f"unparsable {path}"
        findings.extend(_import_time_findings(tree, rel(path)))
        findings.extend(_call_findings(tree, rel(path)))
    return findings


def gate_problems(findings: list[Finding]) -> tuple[list[str], Counter]:
    """Return (problems, actual site counts). Empty problems == gate green.

    Exemption counts are exact in both directions: a new occurrence fails
    (over the allowance) and a fixed/renamed site fails as stale until the
    map is updated in the same commit.
    """
    counts: Counter = Counter((f.path, f.site) for f in findings)
    problems: list[str] = []

    for (path, site), found in sorted(counts.items()):
        if path in EXEMPTIONS:
            continue
        entry = EXEMPTED_SITES.get(path, {}).get(site)
        if entry is None:
            sample = next(f for f in findings if (f.path, f.site) == (path, site))
            problems.append(
                f"UN-EXEMPTED {sample.render()} (x{found}) — {sample.detail}"
            )
            continue
        allowed, _reason = entry
        if found != allowed:
            problems.append(
                f"COUNT DRIFT {path}: {site} appears x{found}, exemption "
                f"allows x{allowed} — a new site must be scaled; a fixed site "
                "must lower the count"
            )

    for path in sorted(EXEMPTIONS):
        if not any(f.path == path for f in findings):
            problems.append(
                f"STALE whole-file exemption {path} — no findings left; "
                "remove it so future raw sites are visible"
            )

    for path, sites in sorted(EXEMPTED_SITES.items()):
        for site in sorted(sites):
            if counts.get((path, site), 0) == 0:
                problems.append(
                    f"STALE site exemption {path}: {site!r} — no such finding; "
                    "remove it so a future regression is visible"
                )
    return problems, counts


def test_no_unexempted_raw_chrome_px():
    findings = scan_tree()
    problems, counts = gate_problems(findings)

    assert not problems, (
        "Chrome geometry bypasses or freezes the UiScale boundary "
        "(docs/dev/CONTRACTS.md §UI Scale Contract). The scan is per site: "
        "one scaled_px line no longer exempts the rest of a file.\n\n"
        + "\n".join(problems)
        + "\n\nFix by wrapping design px with scaled_px() at the call site "
        "(never at import). If a site is genuinely image-space or a "
        "structural sentinel, add it to EXEMPTED_SITES with a reason."
    )
    # Inventory assertion keeps the seeded size honest as the drain proceeds.
    assert counts, "detector found nothing at all — the scan is blind"


def test_exemption_reasons_are_recorded():
    reasons = list(EXEMPTIONS.values())
    for sites in EXEMPTED_SITES.values():
        reasons.extend(reason for _count, reason in sites.values())
    blank = [reason for reason in reasons if not reason.strip()]
    assert not blank, f"every exemption needs a reason; blank: {blank}"


# ---------------------------------------------------------------------------
# Falsification: the detector must flag synthetic offenders and pass clean
# code. These are the red-before probes for the per-file-skip hole.
# ---------------------------------------------------------------------------

_SYNTHETIC_OFFENDER = '''
from sli_ui_toolkit.managers import scaled_px
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout

PAD = scaled_px(8)  # module-level import-time bake


class Chip(QWidget):
    ICON = scaled_px(16)  # class-level import-time bake

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)  # raw, in a file that scales other geometry
        self.resize(120, 32)
        layout = QVBoxLayout(self)
        layout.setSpacing(scaled_px(6))  # correctly scaled
        layout.setContentsMargins(4, 4, 4, 4)
        self.setMaximumHeight(16777215)  # sentinel
        self.setMinimumWidth(0)  # sentinel
        self.setFixedSize(QSize(0, 30))  # QSize height is still raw
'''


def test_detector_flags_synthetic_offender():
    findings = scan_source(_SYNTHETIC_OFFENDER, "src/ui/synthetic_offender.py")
    sites = {f.site for f in findings}
    kinds = {f.kind for f in findings}

    # The hole this gate closes: a scaled_px mention must not blind the file.
    assert "PAD = scaled_px(8)" in sites
    assert "Chip.ICON = scaled_px(16)" in sites
    assert "setFixedHeight(24)" in sites
    assert "resize(120, 32)" in sites
    assert "setContentsMargins(4, 4, 4, 4)" in sites
    assert "QSize(0, 30)" in sites
    assert kinds == {"import-time", "raw"}
    # Sentinels are structural, not design px.
    assert "setMaximumHeight(16777215)" not in sites
    assert "setMinimumWidth(0)" not in sites
    # Correctly scaled geometry is not a finding.
    assert "setSpacing(6)" not in sites


def test_synthetic_clean_file_is_not_flagged():
    source = '''
from sli_ui_toolkit.managers import scaled_px
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

class Row(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(scaled_px(24))
        self.setMinimumSize(scaled_px(120), scaled_px(32))
        self.setFixedSize(QSize(scaled_px(22), scaled_px(22)))
        self.setContentsMargins(0, 0, 0, 0)
'''
    assert scan_source(source, "src/ui/synthetic_clean.py") == []


def test_double_scaled_size_kwarg_is_flagged():
    source = '''
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button

button = Button(text="switch", size=(scaled_px(132), scaled_px(34)))
'''
    findings = scan_source(source, "src/ui/synthetic_double.py")
    doubles = [f for f in findings if f.kind == "double"]
    assert len(doubles) == 1
    assert doubles[0].site.startswith("Button(size=")


# ---------------------------------------------------------------------------
# Legacy font-size check (unchanged scope: fonts are a separate drain).
# ---------------------------------------------------------------------------

_FONT_SIZE_CALLS = ("setPixelSize", "setPointSize")

#: Canvas/image-space or infra files where raw font-size literals are
#: intentional (app font bootstrap, canvas image-label chrome).
_FONT_ALLOWLISTED_FILES = {
    Path("services/system/paste_direction_overlay.py"),
    Path("tabs/image_compare/ui/primitives.py"),
    Path("tabs/multi_compare/widget.py"),
    Path("shared_toolkit/ui/managers/font_manager.py"),
}


def _is_numeric_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _is_numeric_literal(node.operand)
    return False


def test_no_raw_font_size_literals_outside_font_infra():
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        rel_path = path.relative_to(SRC)
        if rel_path in _FONT_ALLOWLISTED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        # Scale-aware files (e.g. toolkit Label.setPixelSize, which routes
        # through ui_font internally) are already covered; flag only files
        # with raw font-size literals that have no scaling path at all.
        # NOTE: this file-level skip is the font-size drain's known debt;
        # geometry above is scanned per site.
        if "scaled_px" in text or "ui_font" in text or "apply_ui_font" in text:
            continue
        tree = parse(path)
        assert tree is not None, f"unparsable {path}"
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name in _FONT_SIZE_CALLS and node.args and _is_numeric_literal(node.args[0]):
                offenders.append(f"{rel_path}:{node.lineno} {name}({ast.unparse(node.args[0])})")
    assert not offenders, (
        "raw setPixelSize/setPointSize bypass UiFont scaling — use "
        "ui_font()/paint_font() with design px:\n" + "\n".join(sorted(offenders))
    )
