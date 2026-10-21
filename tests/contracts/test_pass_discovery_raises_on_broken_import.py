"""C1 gate: pass discovery must not mistake a broken import for "no passes".

Dogma: ``ui/canvas_infra/scene/registry.py`` discovers a tab's feature packages
by importing ``<feature>.passes`` and skipping the feature when that module does
not exist. The skip is correct ONLY for a feature that genuinely ships no
``passes.py``. A ``ModuleNotFoundError`` raised *inside* an existing
``passes.py`` (a broken transitive import — a renamed engine module, a typo in
a sibling import) means the feature DOES have passes that failed to load, and
silently skipping it makes the pass vanish from every frame with no error:
the canvas renders without its overlay, and no test fails because the
registry's answer ("this feature has no passes") is indistinguishable from
the truth.

Rule (behavioural, no Qt): with a probe package of three features —

* ``a_good/passes.py`` — yielded;
* ``b_broken/passes.py`` — imports a nonexistent module; the iterator must
  PROPAGATE that ``ImportError`` (its ``exc.name`` is the missing transitive
  module, not the feature's ``passes`` module);
* ``c_absent/`` — no ``passes.py``; skipped.

Today ``_iter_feature_modules`` catches ``ModuleNotFoundError`` and continues
regardless of ``exc.name``, so ``b_broken`` is skipped like ``c_absent``.

Allowlist: one entry (the iterator — C3).
"""

from __future__ import annotations

import importlib
import sys
import textwrap
from types import ModuleType

from tests.contracts.canvas_gates_allowlist import (
    Finding,
    allowlist_problems,
    format_findings,
    unexplained,
)

GATE = "test_pass_discovery_raises_on_broken_import.py"

REGISTRY_PATH = "src/ui/canvas_infra/scene/registry.py"
REGISTRY_SYMBOL = "_iter_feature_modules"

PROBE_PACKAGE = "c1_pass_discovery_probe"
BROKEN_DEPENDENCY = "c1_missing_transitive_dependency"

_FILES = {
    f"{PROBE_PACKAGE}/__init__.py": "",
    f"{PROBE_PACKAGE}/a_good/__init__.py": "",
    f"{PROBE_PACKAGE}/a_good/passes.py": (
        "RENDER_PASSES = ['a_good']\n"
    ),
    f"{PROBE_PACKAGE}/b_broken/__init__.py": "",
    f"{PROBE_PACKAGE}/b_broken/passes.py": (
        f"import {BROKEN_DEPENDENCY}  # noqa: F401 — deliberately missing\n"
        "RENDER_PASSES = ['b_broken']\n"
    ),
    f"{PROBE_PACKAGE}/c_absent/__init__.py": "",
}


def _build_probe(tmp_path, monkeypatch) -> ModuleType:
    """Write the three-feature probe package and import it."""
    for relative, body in _FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in list(sys.modules):
        if name == PROBE_PACKAGE or name.startswith(f"{PROBE_PACKAGE}."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    return importlib.import_module(PROBE_PACKAGE)


def _registry(package: ModuleType):
    from ui.canvas_infra.scene.registry import CanvasFeatureRegistry

    registry = CanvasFeatureRegistry("probe")
    registry._packages = [package]
    return registry


def _probe(tmp_path, monkeypatch) -> tuple[list[str], BaseException | None]:
    """Iterate the probe's passes modules; ``(yielded features, raised)``."""
    package = _build_probe(tmp_path, monkeypatch)
    registry = _registry(package)
    yielded: list[str] = []
    raised: BaseException | None = None
    try:
        for _features_pkg, module_info, _module in registry._iter_feature_modules(
            "passes"
        ):
            yielded.append(module_info.name)
    except BaseException as exc:  # noqa: BLE001 — the probe records the exit path
        raised = exc
    return yielded, raised


def findings(tmp_path, monkeypatch) -> list[Finding]:
    yielded, raised = _probe(tmp_path, monkeypatch)
    findings: list[Finding] = []
    if not isinstance(raised, ImportError):
        detail = (
            "the broken feature was skipped "
            f"(yielded={yielded}): a ModuleNotFoundError inside an existing "
            "passes.py looks exactly like a feature with no passes.py, so its "
            "passes silently vanish from every frame"
        )
        if raised is not None:
            detail = f"the iterator raised {type(raised).__name__}: {raised}"
        findings.append(Finding(REGISTRY_PATH, REGISTRY_SYMBOL, detail))
    elif raised.name == f"{PROBE_PACKAGE}.b_broken.passes":
        findings.append(
            Finding(
                REGISTRY_PATH,
                REGISTRY_SYMBOL,
                "the iterator treats a broken passes.py as 'no passes.py' "
                f"(it swallowed ImportError for {raised.name!r})",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_broken_transitive_import_is_propagated(tmp_path, monkeypatch):
    open_findings = unexplained(GATE, findings(tmp_path, monkeypatch))
    assert not open_findings, (
        "Feature-module discovery must distinguish 'this feature has no "
        "passes.py' from 'this passes.py failed to import'. A broken "
        "transitive import must propagate. Offenders:\n"
        + format_findings(open_findings)
    )


def test_allowlist_entries_are_documented_and_current(tmp_path, monkeypatch):
    current = findings(tmp_path, monkeypatch)
    problems = allowlist_problems(GATE, current)
    for finding in unexplained(GATE, current):
        problems.append(f"{finding.key}: uncovered finding — {finding.detail}")
    assert not problems, "Allowlist problems:\n" + "\n".join(
        f"  {problem}" for problem in problems
    )


def test_good_feature_is_yielded(tmp_path, monkeypatch):
    """Control: the probe's healthy feature is discovered (the gate is wired)."""
    yielded, _raised = _probe(tmp_path, monkeypatch)
    assert "a_good" in yielded, f"the good feature was not yielded: {yielded}"


def test_feature_without_passes_is_skipped(tmp_path, monkeypatch):
    """Control: a feature with no passes.py is not a finding."""
    yielded, raised = _probe(tmp_path, monkeypatch)
    assert "c_absent" not in yielded, f"a feature without passes.py was yielded: {yielded}"
    if raised is not None:
        # b_broken aborts the walk before/after c_absent depending on the
        # registry's ordering; either way c_absent must never appear.
        assert isinstance(raised, ImportError)


def test_probe_is_genuinely_broken(tmp_path, monkeypatch):
    """Control: the fixture really has a broken transitive import."""
    _build_probe(tmp_path, monkeypatch)
    try:
        importlib.import_module(f"{PROBE_PACKAGE}.b_broken.passes")
    except ImportError as exc:
        assert exc.name == BROKEN_DEPENDENCY, (
            f"the probe raised {exc.name!r}, not the missing dependency"
        )
    else:  # pragma: no cover — the probe would be vacuous
        raise AssertionError("the probe's broken module imported successfully")
