"""ADR 009 wave A5 — the strict import boundary between the two analysis backends.

ADR 009 §2 (as amended) splits the gallery's judgment into two adapters behind
one contract, and the whole point of the split is that each adapter reads ONE
instrument. Until A5 that was a promise in docstrings plus a pile of behavioural
tests: nothing stopped the next commit from making the Algorithms adapter import
``backends.ai`` (and hand a detector number to the judge's path) or from making
a core module reach into ``backends.algorithms.profile`` instead of asking the
composition point for an adapter by id.

This module turns the promise into a mechanical gate, discovered by AST — there
is no hand-written list of files, so a new module is covered the moment it
exists:

1. ``backends/algorithms/**`` imports no AI-only surface: the AI adapter package
   (any submodule), the per-image client, the VLM profile selector request, the
   Ask-AI router, the A/B pass, and the Jev rank client. The local detectors'
   domain owns no network path, so every one of those imports is a cross-domain
   read waiting to happen.
2. ``backends/ai/**`` imports no local detector producer (the auto-discovered
   ``analysis/producers`` packages and the detector math they wrap) and no part
   of ``backends.algorithms``. The producers are the Algorithms backend's
   instrument; the judge measures what the judge scored.
3. The **core** — every module under ``src/tabs/image_gallery/`` outside
   ``backends/`` — reaches the backends ONLY through the contract surface
   (``contract``/``errors``/``registry``/``composition``/``context``/
   ``generation``/``reset``) and never through a concrete backend. The one
   exception is pinned, justified and shrink-only (see
   :data:`CORE_CONCRETE_BACKEND_IMPORTS`).
4. The walk is non-vacuous: a broken glob, a renamed package or an unparseable
   file fails loudly instead of scanning nothing and passing.

Why AST and not ``import``: importing the adapters proves nothing about the
*edges* (a lazy import inside a function is invisible to an import graph and
perfectly visible to ``ast.walk``), and the module-level graph of this tab
imports Qt. The engine seal (``test_engine_no_app_imports.py``) uses the same
idiom: walk, explicit allowlist with reasons, ratchet that only shrinks.

Red-before: the checker is exercised against deliberately leaky fixtures built
in ``tmp_path`` (absolute import, relative import, function-level lazy import,
and a core module importing a concrete backend) and must reject each one — a
boundary test that cannot fail is decoration. On the A5 base the real tree is
clean, which is why the fixtures, not the tree, are the falsification.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._framework import ROOT, rel

SRC = ROOT / "src"
GALLERY = SRC / "tabs" / "image_gallery"
BACKENDS = GALLERY / "backends"
ALGORITHMS = BACKENDS / "algorithms"
AI = BACKENDS / "ai"

_GALLERY = "tabs.image_gallery"
_BACKENDS = f"{_GALLERY}.backends"

#: The two concrete adapter packages. Reaching one from anywhere but the
#: composition point is the "whose numbers are these" defect ADR 009 removes.
_CONCRETE_BACKEND_PACKAGES = ("algorithms", "ai")

#: The backend surface the core MAY import (ADR 009 §2 as amended): the contract
#: types, the typed errors, the registry store, the composition point, the
#: series/profile bridge, the work generations and the reset helpers. None of
#: these decides *which* backend answers — the caller asks for an id.
_CORE_ALLOWED_BACKEND_MODULES: tuple[str, ...] = (
    "composition",
    "context",
    "contract",
    "errors",
    "generation",
    "registry",
    "reset",
)

#: Core modules that may import a CONCRETE backend, pinned to the exact modules
#: they import and to the reason they exist. SHRINK-ONLY:
#:
#: * a core module that is not listed here importing ``backends.algorithms`` /
#:   ``backends.ai`` fails ``test_core_does_not_import_a_concrete_backend``;
#: * an entry may not widen its scope (a new concrete import under a pinned path
#:   fails the same test);
#: * an entry whose imports are gone must be PRUNED (a stale entry fails), and
#:   the ceiling :data:`_MAX_ALLOWLISTED_CORE_MODULES` may only be lowered.
#:
#: **EMPTY, and it stays empty.** A core module that needs a backend's OWN number
#: asks the adapter through ``backends.composition.backend(id)`` — the seam
#: exists for exactly that (``AIBackend.series_quality`` is the declared call the
#: cross-series payload uses, ADR 009 §2 as amended). Re-adding an entry means
#: the core went around the composition seam; raise it with the owner, never to
#: make a new import pass.
CORE_CONCRETE_BACKEND_IMPORTS: dict[str, tuple[tuple[str, ...], str]] = {}

#: Hard ceiling on the allowlist above. Lower it when you prune an entry; raise
#: it only with an ADR amendment, never to make a new import pass.
_MAX_ALLOWLISTED_CORE_MODULES = 0

#: AI-only surface the Algorithms package must not touch: every entry spends (or
#: is fed by) a model call, which is the other backend's instrument.
_ALGORITHMS_FORBIDDEN: dict[str, str] = {
    f"{_BACKENDS}.ai": "the other backend's adapter package",
    f"{_GALLERY}.services.ai_client": "the per-image VLM scorecard call",
    f"{_GALLERY}.services.vlm": "the VLM tie-break/brief pass",
    f"{_GALLERY}.services.ask_router": "the advisory Ask-AI path",
    f"{_GALLERY}.services.jev_client": "the Jev rank transport (the AI rank path)",
    f"{_GALLERY}.use_cases.pairwise_rank": "the paid A/B refinement (an AI capability)",
    f"{_GALLERY}.use_cases.profile_ai": "the VLM profile selector",
}

#: The local detector producers: the auto-discovered ``analysis/producers``
#: packages plus the detector math they wrap (their own docstring names the three
#: services). They are the Algorithms backend's instrument, so the AI package
#: must not read them — that is exactly the "an empty AI profile fell through to
#: the detector axes" defect A3 killed.
_LOCAL_DETECTOR_PRODUCERS: dict[str, str] = {
    f"{_GALLERY}.analysis.producers": "a local (detector) producer package",
    f"{_GALLERY}.services.camera_metrics": "local camera scalars",
    f"{_GALLERY}.services.fidelity_metrics": "local source-relative deltas",
    f"{_GALLERY}.services.artifacts": "the local artifact detector",
}

#: ``backends/ai/**`` must not import these, nor the Algorithms package.
_AI_FORBIDDEN: dict[str, str] = {
    **_LOCAL_DETECTOR_PRODUCERS,
    f"{_BACKENDS}.algorithms": "the other backend's adapter package",
}

#: The only file directly under ``backends/`` that may import a concrete adapter
#: package: the ONE composition point (it registers both and nothing else).
_COMPOSITION_MODULE = "composition.py"


# ---------------------------------------------------------------------------
# The checker: path -> absolute dotted imports, relative ones resolved
# ---------------------------------------------------------------------------


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _package_parts(path: Path, root: Path) -> list[str]:
    """The dotted package *path* lives in, relative to the import root *root*."""
    parts = list(path.resolve().relative_to(root.resolve()).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        return parts[:-1]
    return parts[:-1]


def _module_exists(name: str, *, root: Path = SRC) -> bool:
    parts = name.split(".")
    return (root.joinpath(*parts).with_suffix(".py")).is_file() or (
        root.joinpath(*parts) / "__init__.py"
    ).is_file()


def imported_modules(path: Path, *, root: Path = SRC) -> list[tuple[str, int]]:
    """Every import in *path* as an ABSOLUTE dotted name.

    ``from ..ai.measure import series_quality`` resolves to
    ``tabs.image_gallery.backends.ai.measure``: the boundary is about modules,
    so a relative import is the same violation as an absolute one and must not
    slip through. ``from .. import ai`` is expanded too — but only when the
    expansion names a real module, so ``from ...backends import ProfileRequest``
    stays a symbol import and is not mistaken for the package.

    A file that does not parse raises: a SyntaxError must never be read as
    "this module imports nothing" (that is how a boundary test goes vacuous).
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:  # pragma: no cover - the tree is valid today
        raise AssertionError(f"{rel(path)} does not parse: {exc}") from exc

    package = _package_parts(path, root)
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):  # walk, not body: a lazy import is an edge too
        if isinstance(node, ast.Import):
            out.extend((alias.name, node.lineno) for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            keep = len(package) - (node.level - 1)
            if keep < 0:
                out.append(("." * node.level + (node.module or ""), node.lineno))
                continue
            base = package[:keep]
        else:
            base = []
        module = ".".join(base + (node.module.split(".") if node.module else []))
        if module:
            out.append((module, node.lineno))
        for alias in node.names:
            expanded = ".".join(part for part in (module, alias.name) if part)
            if expanded and _module_exists(expanded, root=root):
                out.append((expanded, node.lineno))
    return out


def _matches(name: str, target: str) -> bool:
    """Boundary-aware prefix test: ``services.vlm`` never matches ``vlm_cache``."""
    return name == target or name.startswith(target + ".")


def boundary_violations(
    paths: list[Path],
    forbidden: dict[str, str],
    *,
    root: Path = SRC,
) -> list[str]:
    """One line per import in *paths* that reaches a *forbidden* module."""
    out: list[str] = []
    for path in paths:
        for name, lineno in imported_modules(path, root=root):
            for target, reason in forbidden.items():
                if _matches(name, target):
                    out.append(
                        f"{rel(path)}:{lineno} imports {name!r} — {target} is "
                        f"{reason}"
                    )
                    break
    return out


def _core_files() -> list[Path]:
    """Every production module of the tab outside ``backends/``.

    ``tests/`` is excluded on purpose: a test constructs the real adapter it
    exercises (that is how the isolation tier proves behaviour), while the
    boundary this module gates is about PRODUCTION wiring.
    """
    out: list[Path] = []
    for path in _py_files(GALLERY):
        parts = path.relative_to(GALLERY).parts
        if "backends" in parts or "tests" in parts:
            continue
        out.append(path)
    return out


def _gallery_rel(path: Path) -> str:
    return path.relative_to(GALLERY).as_posix()


# ---------------------------------------------------------------------------
# 0. non-vacuity: the walk sees both packages, and the resolver sees imports
# ---------------------------------------------------------------------------


def test_the_walk_sees_both_backend_packages_and_the_core() -> None:
    algorithms = _py_files(ALGORITHMS)
    ai = _py_files(AI)
    backend_files = _py_files(BACKENDS)
    core = _core_files()

    # Floors, not exact counts: the point is that a broken glob cannot pass.
    assert len(algorithms) >= 5, algorithms
    assert len(ai) >= 5, ai
    assert len(backend_files) >= 15, backend_files
    assert len(core) >= 200, len(core)

    for required in (
        "contract.py",
        "errors.py",
        "registry.py",
        "composition.py",
        "context.py",
        "generation.py",
        "reset.py",
        "__init__.py",
    ):
        assert (BACKENDS / required).is_file(), f"backends/{required} disappeared"
    assert ALGORITHMS / "profile.py" in algorithms
    assert AI / "profile.py" in ai


def test_the_resolver_actually_reads_imports() -> None:
    seen = {name for name, _lineno in imported_modules(ALGORITHMS / "profile.py")}
    # A known-true edge of the real tree: the adapter is built on the contract.
    assert f"{_BACKENDS}.contract" in seen, sorted(seen)
    # And the lazy (function-level) edges are visible too — an import graph
    # would miss them, which is the reason this gate is AST-based.
    assert f"{_GALLERY}.use_cases.profile_select" in seen, sorted(seen)


# ---------------------------------------------------------------------------
# 1./2. the two adapter packages do not read each other's instrument
# ---------------------------------------------------------------------------


def test_algorithms_imports_no_ai_surface() -> None:
    violations = boundary_violations(_py_files(ALGORITHMS), _ALGORITHMS_FORBIDDEN)
    assert not violations, (
        "the Algorithms backend must own no model call (ADR 009 §2):"
        "\n  - " + "\n  - ".join(violations)
    )


def test_ai_imports_no_local_detector_producer() -> None:
    violations = boundary_violations(_py_files(AI), _AI_FORBIDDEN)
    assert not violations, (
        "the AI backend must read the judge's own records, never a detector "
        "producer (ADR 009 §2/A3):"
        "\n  - " + "\n  - ".join(violations)
    )


def test_the_composition_point_is_the_one_importer_of_both_backends() -> None:
    # Positive control for the two tests above: the boundary is not achieved by
    # the concrete packages being absent or unimported somewhere it matters.
    names = {name for name, _lineno in imported_modules(BACKENDS / _COMPOSITION_MODULE)}
    for package in _CONCRETE_BACKEND_PACKAGES:
        assert any(
            _matches(name, f"{_BACKENDS}.{package}") for name in names
        ), f"composition.py no longer imports backends.{package}: {sorted(names)}"


def test_only_the_composition_point_imports_a_concrete_backend() -> None:
    forbidden = {
        f"{_BACKENDS}.{package}": "a concrete adapter package"
        for package in _CONCRETE_BACKEND_PACKAGES
    }
    offenders = [
        path
        for path in _py_files(BACKENDS)
        if path.parent == BACKENDS and path.name != _COMPOSITION_MODULE
    ]
    violations = boundary_violations(offenders, forbidden)
    assert not violations, (
        "contract/errors/registry/context/generation/reset stay backend-agnostic; "
        "only composition.py names an adapter (ADR 009 §2):"
        "\n  - " + "\n  - ".join(violations)
    )


# ---------------------------------------------------------------------------
# 3. the core reaches the backends only through the contract surface
# ---------------------------------------------------------------------------


def test_core_imports_only_the_contract_surface() -> None:
    leaks: list[str] = []
    for path in _core_files():
        for name, lineno in imported_modules(path):
            if not _matches(name, _BACKENDS) or name == _BACKENDS:
                # The bare package is ``__init__``'s re-export surface: it
                # declares the contract, it decides nothing.
                continue
            head = name[len(_BACKENDS) + 1 :].split(".")[0]
            if head in _CONCRETE_BACKEND_PACKAGES:
                continue  # owned by the ratchet test below
            if head in _CORE_ALLOWED_BACKEND_MODULES:
                continue
            leaks.append(
                f"{_gallery_rel(path)}:{lineno} imports {name!r} — the core may "
                f"import only {', '.join(_CORE_ALLOWED_BACKEND_MODULES)} from "
                f"backends (ADR 009 §2)"
            )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_core_does_not_import_a_concrete_backend() -> None:
    leaks: list[str] = []
    for path in _core_files():
        key = _gallery_rel(path)
        declared = CORE_CONCRETE_BACKEND_IMPORTS.get(key)
        allowed = set(declared[0]) if declared else set()
        for name, lineno in imported_modules(path):
            if not _matches(name, _BACKENDS):
                continue
            head = name[len(_BACKENDS) + 1 :].split(".")[0]
            if head not in _CONCRETE_BACKEND_PACKAGES:
                continue
            if any(_matches(name, target) for target in allowed):
                continue
            leaks.append(
                f"{key}:{lineno} imports {name!r} — a core module must not name a "
                "concrete backend; it asks composition.backend(<id>) for the "
                "adapter and keeps the answer as an AnalysisBackend (ADR 009 §2)"
            )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_the_concrete_backend_allowlist_is_shrink_only() -> None:
    # The ceiling: entries may be pruned, never added.
    assert len(CORE_CONCRETE_BACKEND_IMPORTS) <= _MAX_ALLOWLISTED_CORE_MODULES, (
        "the core->concrete-backend allowlist grew: "
        f"{sorted(CORE_CONCRETE_BACKEND_IMPORTS)} (ceiling "
        f"{_MAX_ALLOWLISTED_CORE_MODULES}). Route the call through "
        "backends.composition instead, or amend ADR 009 §2 explicitly."
    )

    core_by_key = {_gallery_rel(path): path for path in _core_files()}
    for key, (targets, reason) in CORE_CONCRETE_BACKEND_IMPORTS.items():
        path = core_by_key.get(key)
        assert path is not None, (
            f"stale allowlist entry {key!r}: the module is gone or moved — prune "
            "the entry (the allowlist only shrinks)"
        )
        assert targets, f"{key!r}: an entry must pin the modules it may import"
        assert len(reason.strip()) >= 40, (
            f"{key!r}: the allowlist requires a REASON, not a placeholder "
            f"(got {reason!r})"
        )
        seen = {
            name
            for name, _lineno in imported_modules(path)
            if any(_matches(name, target) for target in targets)
        }
        assert seen, (
            f"stale allowlist entry {key!r}: it no longer imports "
            f"{sorted(targets)} — prune it (the allowlist only shrinks)"
        )
        for target in targets:
            head = target[len(_BACKENDS) + 1 :].split(".")[0]
            assert head in _CONCRETE_BACKEND_PACKAGES, (
                f"{key!r}: {target!r} is not a concrete backend package; the "
                "contract surface needs no allowlist entry"
            )


# ---------------------------------------------------------------------------
# 4. red-before: the checker rejects what it exists to reject
# ---------------------------------------------------------------------------


def _leaky(tmp_path: Path, relative: str, source: str) -> Path:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_the_checker_rejects_an_absolute_foreign_import(tmp_path: Path) -> None:
    leaky = _leaky(
        tmp_path,
        "tabs/image_gallery/backends/algorithms/leaky.py",
        "from tabs.image_gallery.backends.ai.measure import series_quality\n",
    )
    violations = boundary_violations([leaky], _ALGORITHMS_FORBIDDEN, root=tmp_path)
    assert violations, "the checker accepted an absolute cross-backend import"
    assert "backends.ai" in violations[0]


def test_the_checker_rejects_a_relative_foreign_import(tmp_path: Path) -> None:
    leaky = _leaky(
        tmp_path,
        "tabs/image_gallery/backends/algorithms/leaky.py",
        "from ..ai.profile import AIBackend\n",
    )
    violations = boundary_violations([leaky], _ALGORITHMS_FORBIDDEN, root=tmp_path)
    assert violations, "the checker accepted a RELATIVE cross-backend import"
    assert "backends.ai" in violations[0]


def test_the_checker_rejects_a_package_alias_import(tmp_path: Path) -> None:
    # The alias only resolves to a module when the module exists, so the fixture
    # carries the package it names — the same shape the real tree has.
    _leaky(tmp_path, "tabs/image_gallery/backends/ai/__init__.py", "")
    leaky = _leaky(
        tmp_path,
        "tabs/image_gallery/backends/algorithms/leaky.py",
        "from .. import ai\n",
    )
    violations = boundary_violations([leaky], _ALGORITHMS_FORBIDDEN, root=tmp_path)
    assert violations, "the checker accepted `from .. import ai`"


def test_the_checker_rejects_a_function_level_import(tmp_path: Path) -> None:
    leaky = _leaky(
        tmp_path,
        "tabs/image_gallery/backends/ai/leaky.py",
        "def measure(item):\n"
        "    from tabs.image_gallery.services.camera_metrics import measure_camera\n"
        "    return measure_camera(item)\n",
    )
    violations = boundary_violations([leaky], _AI_FORBIDDEN, root=tmp_path)
    assert violations, "the checker accepted a LAZY detector-producer import"
    assert "camera_metrics" in violations[0]


def test_the_checker_rejects_a_core_module_naming_a_concrete_backend(
    tmp_path: Path,
) -> None:
    leaky = _leaky(
        tmp_path,
        "tabs/image_gallery/services/leaky.py",
        "from tabs.image_gallery.backends.algorithms.profile import AlgorithmsBackend\n",
    )
    violations = boundary_violations(
        [leaky],
        {f"{_BACKENDS}.algorithms": "a concrete adapter package"},
        root=tmp_path,
    )
    assert violations, "the checker accepted a core->concrete-backend import"
    assert "backends.algorithms" in violations[0]


def test_the_checker_accepts_the_contract_surface(tmp_path: Path) -> None:
    # The control: a checker that flags everything would pass the tests above
    # for the wrong reason. An import of the ALLOWED surface must stay clean.
    clean = _leaky(
        tmp_path,
        "tabs/image_gallery/backends/algorithms/clean.py",
        "from ..contract import MeasureRequest\n"
        "from ..errors import NoProfileYet\n"
        "from tabs.image_gallery.backends.context import select_members\n",
    )
    assert boundary_violations([clean], _ALGORITHMS_FORBIDDEN, root=tmp_path) == []


def test_the_prefix_match_respects_module_boundaries() -> None:
    # ``services.vlm`` must not swallow ``services.vlm_cache``: a substring
    # match here would make the allowlist impossible to read.
    assert _matches(f"{_GALLERY}.services.vlm", f"{_GALLERY}.services.vlm")
    assert _matches(f"{_GALLERY}.services.vlm.client", f"{_GALLERY}.services.vlm")
    assert not _matches(f"{_GALLERY}.services.vlm_cache", f"{_GALLERY}.services.vlm")
    assert not _matches(f"{_GALLERY}.services.ai_client_x", f"{_GALLERY}.services.ai_client")
