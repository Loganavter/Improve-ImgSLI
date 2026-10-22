"""C1 gate: every discovered render pass declares its own scene visibility.

Dogma: ``docs/dev/rendering/render-pass-contract.md`` § Scene visibility — a
pass that does not declare ``visibility`` in its **own class body** silently
inherits
``CanvasRenderPassBase.visibility = SceneVisibility.ALL``, so it paints in
export / preview frames its author never opted into (and an export-only bug
stays invisible until a user exports).

Discovery mirrors the feature registry (``ui/canvas_infra/scene/registry.py``)
over every package a tab hands it at startup:

* ``tabs.image_compare.canvas.features.<name>.passes``
* ``tabs.multi_compare.canvas.features.<name>.passes``
* ``tabs.multi_compare.scene.passes`` (its own ``RENDER_PASSES``)

``<name>`` starting with ``_`` is skipped, exactly like the registry. Every
class reachable from a discovered ``RENDER_PASSES`` list is walked — the gate
never pins one exemplar (the ``test_every_role_resolves`` disease: a class list
that silently went vacuous).

Identity is the triple ``(tab, feature_or_module, class_name)``, never the bare
class name: image_compare and multi_compare each own a ``DragDropOverlayPass``,
and a name-keyed set silently collapses them into one entry — the gate then
stops seeing half the tree.

Second half: ``render_executor._visibility_matches`` must not *swallow* a
wrong-typed visibility. It used to catch ``TypeError`` from ``&`` and fall
back to name-string matching, so ``_visibility_matches("interactive",
SceneVisibility.PREVIEW)`` yielded a verdict (or an incidental
``AttributeError`` from the fallback) instead of the deliberate ``TypeError``
a wrong type must raise — a silent mis-match in production. C2 removed that
fallback; the gate keeps the rule so it cannot come back.

Allowlist: ``canvas_gates_allowlist.ALLOWLIST[GATE]`` (empty — the executor
fallback was drained in C2).
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

from tests.contracts._framework import SRC, parse, rel
from tests.contracts.canvas_gates_allowlist import (
    Finding,
    allowlist_problems,
    format_findings,
    unexplained,
)

GATE = "test_render_visibility_declared.py"

#: The packages the canvas feature registry is handed (``tab.py``'s
#: ``register_canvas_feature_package`` calls) plus multi_compare's scene
#: package; see the registry's ``_iter_feature_modules("passes")``. Every tab
#: that registers a feature package must appear here.
FEATURE_PACKAGES: tuple[str, ...] = (
    "tabs.image_compare.canvas.features",
    "tabs.multi_compare.canvas.features",
    "tabs.multi_compare.scene.passes",
)

_MISSING = object()

_EXECUTOR = "src/ui/canvas_infra/rhi/render_executor.py"

#: Members of ``SceneVisibility`` (checked structurally, not by importing the
#: enum into the AST walk).
_VISIBILITY_MEMBERS = frozenset({"INTERACTIVE", "EXPORT", "PREVIEW", "ALL"})


@dataclass(frozen=True)
class DiscoveredPass:
    """One pass class reachable from a ``RENDER_PASSES`` list.

    ``tab``/``feature_or_module`` come from the package that declared the
    list, not from the class's defining module (a feature re-exports its pass
    classes), so they stay stable when a class moves between render folders.
    """

    tab: str
    feature_or_module: str
    cls: type

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.tab, self.feature_or_module, self.cls.__name__)


# ---------------------------------------------------------------------------
# Discovery — same module iteration the registry performs
# ---------------------------------------------------------------------------


def _pass_modules() -> list[tuple[str, ModuleType]]:
    """``(package name, passes module)`` for every feature the registry sees."""
    modules: list[tuple[str, ModuleType]] = []
    for package_name in FEATURE_PACKAGES:
        package = importlib.import_module(package_name)
        if package_name.rsplit(".", 1)[-1] == "passes":
            # A plain passes package: it owns RENDER_PASSES itself.
            modules.append((package_name, package))
            continue
        for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda i: i.name):
            if info.name.startswith("_"):
                continue
            module_name = f"{package_name}.{info.name}.passes"
            try:
                modules.append((module_name, importlib.import_module(module_name)))
            except ModuleNotFoundError as exc:
                # A feature may legitimately ship no passes.py; a *broken*
                # transitive import is the registry gate's business
                # (test_pass_discovery_raises_on_broken_import.py).
                if exc.name == module_name:
                    continue
                raise
    return modules


def _discovered_passes() -> list[DiscoveredPass]:
    """Every pass class, identified by ``(tab, feature_or_module, class_name)``.

    Two distinct classes with the same triple can only mean a module declared
    two classes with one name (impossible in Python) or a ``RENDER_PASSES``
    entry that is not an instance of its own module's class — both are gate
    blindness, so the discovery raises instead of collapsing the entry.
    """
    found: dict[tuple[str, str, str], DiscoveredPass] = {}
    for package_name, module in _pass_modules():
        declared = getattr(module, "RENDER_PASSES", None)
        if not isinstance(declared, (list, tuple)):
            continue
        parts = package_name.split(".")
        tab = parts[1]
        feature = (
            "scene.passes"
            if package_name.endswith(".scene.passes")
            else parts[parts.index("features") + 1]
        )
        for instance in declared:
            cls = type(instance)
            entry = DiscoveredPass(tab, feature, cls)
            previous = found.get(entry.identity)
            if previous is not None and previous.cls is not cls:
                raise AssertionError(
                    f"two distinct classes share the identity {entry.identity}: "
                    f"{previous.cls!r} and {cls!r}"
                )
            found[entry.identity] = entry
    return list(found.values())


# ---------------------------------------------------------------------------
# Class-body literal check
# ---------------------------------------------------------------------------


def _class_node(tree, name: str):
    return next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == name
        ),
        None,
    )


def _literal_visibility_assignment(class_node) -> bool:
    """True when the class body assigns ``visibility = SceneVisibility.<member>``."""
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "visibility"
            for target in targets
        ):
            continue
        return (
            isinstance(value, ast.Attribute)
            and value.attr in _VISIBILITY_MEMBERS
            and isinstance(value.value, ast.Name)
            and value.value.id.endswith("SceneVisibility")
        )
    return False


def _defining_file(cls: type, fallback: Path) -> Path:
    """File that actually holds *cls*'s ``class`` statement.

    ``RENDER_PASSES`` modules re-export classes (e.g.
    ``features/magnifier/passes.py`` re-exports ``MagnifierPass`` from
    ``render/magnifier_pass.py``), so the class-body check must read the
    defining module, not the re-exporting one.
    """
    module = sys.modules.get(cls.__module__)
    filename = getattr(module, "__file__", None) if module is not None else None
    return Path(filename) if filename else fallback


def declaration_findings(
    *, probe: list[tuple[Path, type]] | None = None
) -> list[Finding]:
    """Every discovered pass that does not declare visibility in its own body.

    *probe* replaces the discovery result (synthetic falsification sources).
    """
    from ui.canvas_infra.scene.pass_contract import SceneVisibility

    findings: list[Finding] = []
    if probe is not None:
        entries: list[tuple[Path, type]] = list(probe)
    else:
        entries = [
            (_defining_file(entry.cls, Path(__file__)), entry.cls)
            for entry in _discovered_passes()
        ]
    for path, cls in entries:
        path = _defining_file(cls, path)
        declared = cls.__dict__.get("visibility", _MISSING)
        where = rel(path)
        if declared is _MISSING:
            findings.append(
                Finding(
                    where,
                    cls.__name__,
                    "no `visibility` in its own class body — it inherits "
                    "SceneVisibility.ALL and paints in every frame kind",
                )
            )
            continue
        if not isinstance(declared, SceneVisibility):
            findings.append(
                Finding(
                    where,
                    cls.__name__,
                    f"`visibility = {declared!r}` is not a SceneVisibility member",
                )
            )
            continue
        tree = parse(path)
        node = _class_node(tree, cls.__name__) if tree is not None else None
        if node is None or not _literal_visibility_assignment(node):
            findings.append(
                Finding(
                    where,
                    cls.__name__,
                    "`visibility` is not a literal `SceneVisibility.<member>` "
                    "assignment in the class body (computed or inherited)",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Wrong-type fallback in the executor
# ---------------------------------------------------------------------------


def _swallows_type_error(function) -> bool:
    """True when the function catches ``TypeError`` without re-raising it."""
    for node in ast.walk(function):
        if not isinstance(node, ast.ExceptHandler):
            continue
        caught = node.type
        names = (
            [caught] if not isinstance(caught, ast.Tuple) else list(caught.elts)
        )
        if not any(
            isinstance(item, ast.Name) and item.id == "TypeError" for item in names
        ):
            continue
        if not any(isinstance(inner, ast.Raise) for inner in ast.walk(node)):
            return True
    return False


def executor_findings() -> list[Finding]:
    from ui.canvas_infra.scene.pass_contract import SceneVisibility
    from ui.canvas_infra.rhi.render_executor import _visibility_matches

    findings: list[Finding] = []
    try:
        verdict = _visibility_matches("interactive", SceneVisibility.PREVIEW)
    except TypeError:
        verdict = None
    except Exception as exc:  # noqa: BLE001 — any other exit is a fallback path
        verdict = f"raised {type(exc).__name__} from the name-matching fallback"
    if verdict is not None:
        findings.append(
            Finding(
                _EXECUTOR,
                "_visibility_matches",
                f"a wrong-typed visibility did not raise TypeError ({verdict!r}) "
                "— name-string matching still decides the verdict",
            )
        )

    tree = parse(SRC / "ui/canvas_infra/rhi/render_executor.py")
    function = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_visibility_matches"
        ),
        None,
    )
    if function is None:
        findings.append(
            Finding(_EXECUTOR, "_visibility_matches", "function disappeared — gate is blind")
        )
    elif _swallows_type_error(function):
        findings.append(
            Finding(
                _EXECUTOR,
                "_visibility_matches",
                "still catches TypeError and falls back to name-string matching "
                "instead of letting the wrong type fail loudly",
            )
        )
    return findings


def findings() -> list[Finding]:
    return declaration_findings() + executor_findings()


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_every_discovered_pass_declares_visibility():
    open_findings = unexplained(GATE, findings())
    assert not open_findings, (
        "Every class reachable from a `RENDER_PASSES` list must declare "
        "`visibility = SceneVisibility.<member>` as a literal assignment in its "
        "own class body, and `_visibility_matches` must reject a wrong-typed "
        "visibility with TypeError instead of name matching. Offenders:\n"
        + format_findings(open_findings)
        + "\n\nDeferred seams go in "
        "tests/contracts/canvas_gates_allowlist.py with a wave + precondition."
    )


def test_allowlist_entries_are_documented_and_current():
    """Both halves of the ratchet: every entry real, documented, still needed."""
    current = findings()
    problems = allowlist_problems(GATE, current)

    # Uncovered findings are reported here too, so a new violation cannot slip
    # through as "no entry needed" (this half lives in the gate test above,
    # but the currency test names it explicitly for the red-before protocol).
    for finding in unexplained(GATE, current):
        problems.append(f"{finding.key}: uncovered finding — {finding.detail}")

    assert not problems, "Allowlist problems:\n" + "\n".join(
        f"  {problem}" for problem in problems
    )


def test_correctly_typed_visibility_still_resolves():
    """Control: the gate must not pass by requiring the matcher to always raise."""
    from ui.canvas_infra.scene.pass_contract import SceneVisibility
    from ui.canvas_infra.rhi.render_executor import _visibility_matches

    assert _visibility_matches(SceneVisibility.ALL, SceneVisibility.PREVIEW) is True
    assert _visibility_matches(SceneVisibility.EXPORT, SceneVisibility.PREVIEW) is False
    assert _visibility_matches(SceneVisibility.INTERACTIVE, SceneVisibility.INTERACTIVE)

    # Full match/non-match matrix, so "resolve" means the flag algebra and not
    # an incidental truthiness of the enum.
    matches = {
        (SceneVisibility.INTERACTIVE, SceneVisibility.INTERACTIVE): True,
        (SceneVisibility.INTERACTIVE, SceneVisibility.PREVIEW): False,
        (SceneVisibility.INTERACTIVE, SceneVisibility.EXPORT): False,
        (SceneVisibility.INTERACTIVE, SceneVisibility.ALL): True,
        (SceneVisibility.EXPORT, SceneVisibility.INTERACTIVE): False,
        (SceneVisibility.EXPORT, SceneVisibility.PREVIEW): False,
        (SceneVisibility.EXPORT, SceneVisibility.EXPORT): True,
        (SceneVisibility.EXPORT, SceneVisibility.ALL): True,
        (SceneVisibility.PREVIEW, SceneVisibility.INTERACTIVE): False,
        (SceneVisibility.PREVIEW, SceneVisibility.PREVIEW): True,
        (SceneVisibility.PREVIEW, SceneVisibility.EXPORT): False,
        (SceneVisibility.PREVIEW, SceneVisibility.ALL): True,
        (SceneVisibility.ALL, SceneVisibility.INTERACTIVE): True,
        (SceneVisibility.ALL, SceneVisibility.PREVIEW): True,
        (SceneVisibility.ALL, SceneVisibility.EXPORT): True,
        (SceneVisibility.ALL, SceneVisibility.ALL): True,
    }
    for (pass_visibility, current_visibility), expected in matches.items():
        assert (
            _visibility_matches(pass_visibility, current_visibility) is expected
        ), (pass_visibility, current_visibility)


@pytest.mark.parametrize(
    "wrong",
    ["interactive", ["INTERACTIVE"], None, 1.5, object()],
    ids=["str", "list", "none", "float", "object"],
)
def test_wrong_typed_visibility_raises_type_error(wrong):
    """No name-string fallback: a wrong-typed visibility fails at the seam.

    Before C2 the ``except TypeError`` fallback turned these inputs into a
    verdict (or an incidental ``AttributeError``), i.e. a silent mis-match on
    a live frame instead of an error in the code that built the pass.
    """
    from ui.canvas_infra.scene.pass_contract import SceneVisibility
    from ui.canvas_infra.rhi.render_executor import _visibility_matches

    with pytest.raises(TypeError):
        _visibility_matches(wrong, SceneVisibility.PREVIEW)
    with pytest.raises(TypeError):
        _visibility_matches(SceneVisibility.ALL, wrong)


def test_executor_keeps_the_filter_contract_on_real_passes():
    """The strict matcher still filters a real pass list by frame kind."""
    from types import SimpleNamespace

    from ui.canvas_infra.rhi.render_executor import execute_render_passes
    from ui.canvas_infra.scene.pass_contract import (
        CanvasRenderPassBase,
        SceneVisibility,
    )
    from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

    painted: list[str] = []

    def _pass(name: str, visibility: SceneVisibility):
        return type(
            f"_Pass_{name}",
            (CanvasRenderPassBase,),
            {
                "stack_role": CanvasStackRole.HUD_LABEL,
                "visibility": visibility,
                "paint": lambda self, widget, ctx: painted.append(name),
                "should_paint": lambda self, ctx: True,
            },
        )()

    ctx = SimpleNamespace(
        render_metrics=SimpleNamespace(mode="export"),
        scene_frame=SimpleNamespace(single_image_preview=0),
    )
    execute_render_passes(
        widget=None,
        ctx=ctx,
        passes=(
            _pass("interactive", SceneVisibility.INTERACTIVE),
            _pass("export", SceneVisibility.EXPORT),
            _pass("all", SceneVisibility.ALL),
        ),
    )
    assert painted == ["export", "all"]


def test_discovery_is_not_vacuous():
    """The predicate must actually see the registered passes.

    A rename of ``RENDER_PASSES`` / a moved feature package would otherwise
    turn this gate into "no classes found, nothing violates the rule".
    """
    discovered = _discovered_passes()
    assert len(discovered) >= 12, (
        "feature pass discovery found "
        f"{len(discovered)} classes: {[e.identity for e in discovered]}"
    )
    assert {entry.tab for entry in discovered} == {"image_compare", "multi_compare"}
    declared = [
        entry.identity for entry in discovered if "visibility" in entry.cls.__dict__
    ]
    assert declared, "no discovered pass declares visibility at all — the check is blind"


def test_same_named_passes_in_both_tabs_stay_distinct():
    """The two ``DragDropOverlayPass`` classes must never collapse into one.

    A name-keyed discovery would keep only one of them and the gate would stop
    seeing half the tree (the exact failure mode this identity triple exists
    for).
    """
    same_named = [
        entry
        for entry in _discovered_passes()
        if entry.cls.__name__ == "DragDropOverlayPass"
    ]
    assert len(same_named) == 2, [entry.identity for entry in same_named]
    assert {entry.tab for entry in same_named} == {"image_compare", "multi_compare"}
    assert len({entry.cls for entry in same_named}) == 2


def test_missing_declaration_is_flagged_on_a_synthetic_pass():
    """Falsification: the class-body predicate fires on an undeclared pass."""

    class SyntheticPass:
        stack_role = None

    flagged = declaration_findings(probe=[(Path(__file__), SyntheticPass)])
    assert flagged, "an undeclared pass was not flagged"
    assert flagged[0].symbol == "SyntheticPass"
    assert flagged[0].path == rel(Path(__file__))
